"""Orchestrator Agent HTTP Server.

A2A-compliant Flask server that:
- Serves its Agent Card at GET /.well-known/agent.json (discovery)
- Handles POST /message/send (SendMessage RPC) to trigger the workflow
- Handles GET /tasks/<id> (GetTask RPC)

A2A Concept: The orchestrator is both an A2A server (it can receive
messages) and an A2A client (it sends messages to other agents). This
makes it a fully peer-to-peer participant in the A2A network.
"""

import logging
from typing import Any

from flask import Flask, Response, jsonify, request

from a2a.logger import log_a2a_message
from a2a.protocol import (
    Role,
    TaskState,
    create_agent_card,
    create_artifact,
    create_message,
    create_skill,
    create_task,
    create_task_status,
    data_part,
    text_part,
)
from a2a.validator import validate_send_message_request
from agents.orchestrator.agent import OrchestratorAgent
from config.settings import load_settings

logger = logging.getLogger(__name__)

app = Flask(__name__)

# In-memory task store (task_id → Task dict)
_tasks: dict[str, dict[str, Any]] = {}

# Agent instance (initialized on startup)
_agent: OrchestratorAgent | None = None

AGENT_ID = "orchestrator-main"


def _get_agent() -> OrchestratorAgent:
    """Get or initialize the OrchestratorAgent instance."""
    global _agent
    if _agent is None:
        settings = load_settings()
        calendars = [
            {"calendar_id": c.calendar_id, "label": c.label}
            for c in settings.calendars
        ]
        _agent = OrchestratorAgent(
            calendar_url=f"http://localhost:{settings.calendar_port}",
            formatter_url=f"http://localhost:{settings.formatter_port}",
            calendars=calendars,
            timezone=settings.user_timezone,
        )
    return _agent


def _build_agent_card() -> dict[str, Any]:
    """Build the Agent Card for this agent."""
    settings = load_settings()
    return create_agent_card(
        name="Orchestrator Agent",
        description="Coordinates the weekly preview workflow by discovering and "
        "delegating to Calendar and Formatter agents via A2A protocol.",
        url=f"http://localhost:{settings.orchestrator_port}",
        skills=[
            create_skill(
                skill_id="generate_weekly_preview",
                name="Generate Weekly Preview",
                description="Orchestrate calendar fetch and formatting to produce a weekly preview.",
                tags=["orchestrator", "workflow", "weekly", "preview"],
                examples=["Generate my weekly preview", "What's my week look like?"],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# A2A Endpoints
# ---------------------------------------------------------------------------


@app.route("/.well-known/agent.json", methods=["GET"])
def agent_card() -> Response:
    """Serve the Agent Card for discovery."""
    return jsonify(_build_agent_card())


@app.route("/message/send", methods=["POST"])
def send_message() -> tuple[Response, int]:
    """Handle a SendMessage request to trigger the weekly preview workflow.

    Expects a DataPart with:
    - action: "generate_weekly_preview"
    - parameters: {next_week: bool}
    """
    incoming = request.json
    log_a2a_message(incoming, direction="incoming", agent_id=AGENT_ID)

    # Validate the incoming request
    is_valid, err = validate_send_message_request(incoming)
    if not is_valid:
        logger.error("Invalid SendMessageRequest: %s", err)
        return jsonify({"error": {"code": "InvalidMessageError", "message": err}}), 400

    # Create a new Task
    msg = incoming["message"]
    context_id = msg.get("context_id")
    task = create_task(context_id=context_id)
    task["history"].append(msg)
    _tasks[task["id"]] = task

    # Extract action parameters
    params = _extract_params(msg)
    if params is None:
        task["status"] = create_task_status(
            TaskState.FAILED,
            message=create_message(Role.AGENT, [text_part("No action parameters found in message.")]),
        )
        _tasks[task["id"]] = task
        response = {"task": task}
        log_a2a_message(response, direction="outgoing", agent_id=AGENT_ID)
        return jsonify(response), 200

    # Update to WORKING
    task["status"] = create_task_status(
        TaskState.WORKING,
        message=create_message(Role.AGENT, [text_part("Generating weekly preview...")]),
    )

    # Process the request
    try:
        agent = _get_agent()
        result = agent.generate_weekly_preview(
            next_week=params.get("next_week", False),
        )

        if "error" in result:
            task["status"] = create_task_status(
                TaskState.FAILED,
                message=create_message(Role.AGENT, [text_part(result["error"])]),
            )
        else:
            artifact = create_artifact(
                parts=[
                    text_part(result["summary"]),
                    data_part({
                        "file_path": result["file_path"],
                        "week_start": result["week_start"],
                        "week_end": result["week_end"],
                        "total_events": result["total_events"],
                    }),
                ],
                name="weekly-preview",
                description=f"Weekly preview for {result['week_start']} to {result['week_end']}",
            )
            task["artifacts"] = [artifact]
            task["status"] = create_task_status(
                TaskState.COMPLETED,
                message=create_message(
                    Role.AGENT,
                    [text_part(f"Weekly preview saved to {result['file_path']}")],
                ),
            )

    except Exception as e:
        logger.error("Failed to generate preview: %s", e)
        task["status"] = create_task_status(
            TaskState.FAILED,
            message=create_message(Role.AGENT, [text_part(f"Error: {e}")]),
        )

    _tasks[task["id"]] = task
    response = {"task": task}
    log_a2a_message(response, direction="outgoing", agent_id=AGENT_ID)
    return jsonify(response), 200


@app.route("/tasks/<task_id>", methods=["GET"])
def get_task(task_id: str) -> tuple[Response, int]:
    """Get the current state of a task."""
    task = _tasks.get(task_id)
    if task is None:
        return jsonify({"error": {"code": "TaskNotFoundError", "message": f"Task {task_id} not found"}}), 404
    return jsonify(task), 200


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_params(message: dict[str, Any]) -> dict[str, Any] | None:
    """Extract action parameters from a Message's DataParts."""
    for part in message.get("parts", []):
        if part.get("type") == "data" and isinstance(part.get("data"), dict):
            data = part["data"]
            if "action" in data and "parameters" in data:
                return data["parameters"]
    return None


# ---------------------------------------------------------------------------
# Standalone run
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    settings = load_settings()
    print(f"Orchestrator Agent starting on port {settings.orchestrator_port}...")
    app.run(host="0.0.0.0", port=settings.orchestrator_port, debug=False)
