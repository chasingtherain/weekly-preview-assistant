"""Formatter Agent HTTP Server.

A2A-compliant Flask server that:
- Serves its Agent Card at GET /.well-known/agent.json (discovery)
- Handles POST /message/send (SendMessage RPC)
- Handles GET /tasks/<id> (GetTask RPC)

A2A Concept: Second A2A agent in the system. Receives calendar data
via a DataPart, processes it through an LLM (Ollama), and returns the
formatted weekly preview as a TextPart artifact.
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
from agents.formatter.agent import FormatterAgent
from config.settings import load_settings

logger = logging.getLogger(__name__)

app = Flask(__name__)

# In-memory task store (task_id → Task dict)
_tasks: dict[str, dict[str, Any]] = {}

# Agent instance (initialized on startup)
_agent: FormatterAgent | None = None

AGENT_ID = "formatter-001"


def _get_agent() -> FormatterAgent:
    """Get or initialize the FormatterAgent instance."""
    global _agent
    if _agent is None:
        settings = load_settings()
        _agent = FormatterAgent(
            ollama_host=settings.ollama_host,
            ollama_model=settings.ollama_model,
        )
    return _agent


def _build_agent_card() -> dict[str, Any]:
    """Build the Agent Card for this agent."""
    settings = load_settings()
    return create_agent_card(
        name="Formatter Agent",
        description="Formats structured calendar data into a human-friendly weekly preview "
        "using a local LLM (Ollama). Groups events by day and calendar source.",
        url=f"http://localhost:{settings.formatter_port}",
        skills=[
            create_skill(
                skill_id="format_weekly_preview",
                name="Format Weekly Preview",
                description="Generate a formatted markdown weekly preview from calendar event data.",
                tags=["formatter", "summary", "markdown", "llm", "ollama"],
                examples=["Format my weekly calendar", "Generate a weekly preview"],
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
    """Handle a SendMessage request.

    Expects a DataPart with:
    - action: "format_weekly_preview"
    - parameters: {events, conflicts, week_start, total_events, busiest_day}

    Returns a Task with a TextPart artifact containing the formatted summary.
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

    # Extract action parameters from the message parts
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
        result = agent.format_weekly_preview(
            events=params.get("events", []),
            conflicts=params.get("conflicts", []),
            week_start=params.get("week_start", ""),
            total_events=params.get("total_events", 0),
            busiest_day=params.get("busiest_day", ""),
        )

        # Create artifact with the formatted summary
        artifact = create_artifact(
            parts=[
                text_part(result["formatted_summary"]),
                data_part({
                    "format": result["format"],
                    "word_count": result["word_count"],
                }),
            ],
            name="weekly-preview",
            description=f"Weekly preview for week of {params.get('week_start')}",
        )
        task["artifacts"] = [artifact]

        # Update to COMPLETED
        task["status"] = create_task_status(
            TaskState.COMPLETED,
            message=create_message(
                Role.AGENT,
                [text_part(f"Generated weekly preview ({result['word_count']} words).")],
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
    """Extract action parameters from a Message's DataParts.

    Looks for a DataPart containing "action" and "parameters" keys.

    Args:
        message: An A2A Message dict.

    Returns:
        The parameters dict, or None if not found.
    """
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
    print(f"Formatter Agent starting on port {settings.formatter_port}...")
    app.run(host="0.0.0.0", port=settings.formatter_port, debug=False)
