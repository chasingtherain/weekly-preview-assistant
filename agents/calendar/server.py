"""Calendar Agent HTTP Server.

A2A-compliant Flask server that:
- Serves its Agent Card at GET /.well-known/agent.json (discovery)
- Handles POST /message/send (SendMessage RPC)
- Handles GET /tasks/<id> (GetTask RPC)

A2A Concept: This is a complete A2A agent implementation. It self-describes
via its Agent Card, receives Messages, creates Tasks, processes them through
the lifecycle (submitted → working → completed/failed), and returns results
as Artifacts.
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
from agents.calendar.agent import CalendarAgent
from config.settings import load_settings

logger = logging.getLogger(__name__)

app = Flask(__name__)

# In-memory task store (task_id → Task dict)
_tasks: dict[str, dict[str, Any]] = {}

# Agent instance (initialized on startup)
_agent: CalendarAgent | None = None

AGENT_ID = "calendar-001"


def _get_agent() -> CalendarAgent:
    """Get or initialize the CalendarAgent instance."""
    global _agent
    if _agent is None:
        settings = load_settings()
        _agent = CalendarAgent(
            credentials_path=settings.google_credentials_path,
            token_path=settings.google_token_path,
            timezone=settings.user_timezone,
        )
    return _agent


def _build_agent_card() -> dict[str, Any]:
    """Build the Agent Card for this agent."""
    settings = load_settings()
    return create_agent_card(
        name="Calendar Agent",
        description="Fetches events from Google Calendar for a date range, "
        "supports multiple calendars with source labeling and conflict detection.",
        url=f"http://localhost:{settings.calendar_port}",
        skills=[
            create_skill(
                skill_id="fetch_week_events",
                name="Fetch Week Events",
                description="Fetch calendar events for a given week from configured calendars.",
                tags=["calendar", "events", "google", "schedule"],
                examples=["Get my events for next week", "What's on my calendar?"],
            ),
        ],
    )


# ---------------------------------------------------------------------------
# A2A Endpoints
# ---------------------------------------------------------------------------


@app.route("/.well-known/agent.json", methods=["GET"])
def agent_card() -> Response:
    """Serve the Agent Card for discovery.

    A2A Concept: Any client can discover this agent's capabilities
    by fetching this endpoint. No central registry needed.
    """
    return jsonify(_build_agent_card())


@app.route("/message/send", methods=["POST"])
def send_message() -> tuple[Response, int]:
    """Handle a SendMessage request.

    A2A Concept: This is the main RPC. The client sends a Message
    (role=user) with instructions. We create a Task, process it
    through the lifecycle, and return the completed Task with Artifacts.

    Task lifecycle for this request:
    1. Receive Message → Create Task (SUBMITTED)
    2. Start processing → Update Task (WORKING)
    3. Fetch events → Update Task (COMPLETED) with Artifacts
    4. On error → Update Task (FAILED)
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
        message=create_message(Role.AGENT, [text_part("Fetching calendar events...")]),
    )

    # Process the request
    try:
        agent = _get_agent()
        result = agent.fetch_week_events(
            start_date=params.get("start_date", ""),
            end_date=params.get("end_date", ""),
            calendars=params.get("calendars", []),
        )

        # Create artifact with the result
        artifact = create_artifact(
            parts=[data_part(result)],
            name="calendar-events",
            description=f"Calendar events for {params.get('start_date')} to {params.get('end_date')}",
        )
        task["artifacts"] = [artifact]

        # Update to COMPLETED
        task["status"] = create_task_status(
            TaskState.COMPLETED,
            message=create_message(
                Role.AGENT,
                [text_part(f"Retrieved {result['total_events']} events.")],
            ),
        )

    except Exception as e:
        logger.error("Failed to fetch events: %s", e)
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
    """Get the current state of a task.

    A2A Concept: Clients can check on task progress by polling this
    endpoint with the task ID they received from SendMessage.
    """
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
    print(f"Calendar Agent starting on port {settings.calendar_port}...")
    app.run(host="0.0.0.0", port=settings.calendar_port, debug=False)
