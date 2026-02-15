"""Telegram Agent HTTP Server.

A2A-compliant Flask server that:
- Serves its Agent Card at GET /.well-known/agent.json (discovery)
- Handles POST /message/send (SendMessage RPC)
- Handles GET /tasks/<id> (GetTask RPC)

Receives formatted text via A2A DataPart and sends it to a Telegram chat.
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
from agents.telegram.agent import TelegramAgent
from config.settings import load_settings

logger = logging.getLogger(__name__)

app = Flask(__name__)

# In-memory task store (task_id → Task dict)
_tasks: dict[str, dict[str, Any]] = {}

# Agent instance (initialized on startup)
_agent: TelegramAgent | None = None

AGENT_ID = "telegram-001"


def _get_agent() -> TelegramAgent:
    """Get or initialize the TelegramAgent instance."""
    global _agent
    if _agent is None:
        settings = load_settings()
        _agent = TelegramAgent(
            bot_token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
        )
    return _agent


def _build_agent_card() -> dict[str, Any]:
    """Build the Agent Card for this agent."""
    settings = load_settings()
    return create_agent_card(
        name="Telegram Agent",
        description="Sends formatted text messages to a Telegram chat via Bot API.",
        url=f"http://localhost:{settings.telegram_port}",
        skills=[
            create_skill(
                skill_id="send_telegram_message",
                name="Send Telegram Message",
                description="Send a text message to a configured Telegram chat.",
                tags=["telegram", "delivery", "notification"],
                examples=["Send weekly preview to Telegram"],
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
    - action: "send_telegram_message"
    - parameters: {text: "..."}

    Returns a Task with a DataPart artifact containing delivery result.
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
        message=create_message(Role.AGENT, [text_part("Sending Telegram message...")]),
    )

    # Process the request
    try:
        agent = _get_agent()
        text = params.get("text", "")
        if not text:
            raise ValueError("No text provided to send")

        result = agent.send_message(text)

        if "error" in result:
            raise RuntimeError(result["error"])

        # Create artifact with delivery result
        artifact = create_artifact(
            parts=[data_part(result)],
            name="telegram-delivery",
            description="Telegram message delivery result",
        )
        task["artifacts"] = [artifact]

        # Update to COMPLETED
        task["status"] = create_task_status(
            TaskState.COMPLETED,
            message=create_message(
                Role.AGENT,
                [text_part(f"Message sent to Telegram (message_id: {result['message_id']}).")],
            ),
        )

    except Exception as e:
        logger.error("Failed to send Telegram message: %s", e)
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
    print(f"Telegram Agent starting on port {settings.telegram_port}...")
    app.run(host="0.0.0.0", port=settings.telegram_port, debug=False)
