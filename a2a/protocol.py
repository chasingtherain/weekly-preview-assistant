"""A2A Protocol - Google A2A spec-aligned schemas and helpers.

Implements the core subset of the Google A2A protocol specification:
- Task: The unit of work, with lifecycle states
- Message: Communication between client and agent, containing Parts
- Part: Content container (text, data)
- AgentCard: Agent discovery metadata served at /.well-known/agent.json
- TaskState: Lifecycle enum (submitted → working → completed/failed)

Reference: https://github.com/google/A2A (a2a.proto)

MVP scope: We implement SendMessage, GetTask, and Agent Card discovery.
We skip streaming, push notifications, security schemes, and pagination.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums (from a2a.proto)
# ---------------------------------------------------------------------------


class TaskState(str, Enum):
    """Lifecycle states for a Task.

    Terminal states: COMPLETED, FAILED, CANCELED, REJECTED
    Interrupted states: INPUT_REQUIRED, AUTH_REQUIRED
    Active states: SUBMITTED, WORKING
    """

    SUBMITTED = "submitted"
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    INPUT_REQUIRED = "input_required"
    REJECTED = "rejected"
    AUTH_REQUIRED = "auth_required"


TERMINAL_STATES = {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED, TaskState.REJECTED}


class Role(str, Enum):
    """Identifies the sender of a Message."""

    USER = "user"
    AGENT = "agent"


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def generate_id() -> str:
    """Generate a unique ID (UUID v4)."""
    return str(uuid.uuid4())


def now_iso() -> str:
    """Return current UTC time in ISO-8601 format with Z suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Part constructors
# ---------------------------------------------------------------------------


def text_part(text: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a TextPart.

    Args:
        text: The text content.
        metadata: Optional metadata dict.

    Returns:
        A Part dict with type "text".
    """
    part: dict[str, Any] = {"type": "text", "text": text}
    if metadata:
        part["metadata"] = metadata
    return part


def data_part(
    data: dict[str, Any],
    media_type: str = "application/json",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a DataPart for structured data (JSON).

    Args:
        data: The structured data.
        media_type: MIME type (default: application/json).
        metadata: Optional metadata dict.

    Returns:
        A Part dict with type "data".
    """
    part: dict[str, Any] = {"type": "data", "data": data, "media_type": media_type}
    if metadata:
        part["metadata"] = metadata
    return part


# ---------------------------------------------------------------------------
# Message constructors
# ---------------------------------------------------------------------------


def create_message(
    role: Role,
    parts: list[dict[str, Any]],
    task_id: str | None = None,
    context_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create an A2A Message.

    Args:
        role: The sender role (USER or AGENT).
        parts: List of Part dicts (created via text_part / data_part).
        task_id: Optional task ID this message belongs to.
        context_id: Optional context ID for conversation grouping.
        metadata: Optional metadata dict.

    Returns:
        A Message dict per the A2A spec.
    """
    message: dict[str, Any] = {
        "message_id": generate_id(),
        "role": role.value,
        "parts": parts,
    }
    if task_id:
        message["task_id"] = task_id
    if context_id:
        message["context_id"] = context_id
    if metadata:
        message["metadata"] = metadata
    return message


# ---------------------------------------------------------------------------
# TaskStatus constructors
# ---------------------------------------------------------------------------


def create_task_status(
    state: TaskState, message: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Create a TaskStatus object.

    Args:
        state: The current TaskState.
        message: Optional Message associated with the status update.

    Returns:
        A TaskStatus dict.
    """
    status: dict[str, Any] = {
        "state": state.value,
        "timestamp": now_iso(),
    }
    if message:
        status["message"] = message
    return status


# ---------------------------------------------------------------------------
# Task constructors
# ---------------------------------------------------------------------------


def create_task(
    task_id: str | None = None,
    context_id: str | None = None,
    state: TaskState = TaskState.SUBMITTED,
    message: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a new Task object.

    In the A2A spec, task IDs are server-generated. The server (agent)
    creates a Task when it receives a SendMessage request.

    Args:
        task_id: Task ID (server-generated, defaults to new UUID).
        context_id: Context ID for grouping related tasks.
        state: Initial task state (default: SUBMITTED).
        message: Optional status message.

    Returns:
        A Task dict per the A2A spec.
    """
    return {
        "id": task_id or generate_id(),
        "context_id": context_id or generate_id(),
        "status": create_task_status(state, message),
        "artifacts": [],
        "history": [],
        "metadata": {},
    }


# ---------------------------------------------------------------------------
# Artifact constructors
# ---------------------------------------------------------------------------


def create_artifact(
    parts: list[dict[str, Any]],
    name: str | None = None,
    description: str | None = None,
    artifact_id: str | None = None,
) -> dict[str, Any]:
    """Create an Artifact (task output).

    Args:
        parts: List of Part dicts containing the artifact content.
        name: Optional human-readable name.
        description: Optional description.
        artifact_id: Optional ID (defaults to new UUID).

    Returns:
        An Artifact dict per the A2A spec.
    """
    artifact: dict[str, Any] = {
        "artifact_id": artifact_id or generate_id(),
        "parts": parts,
    }
    if name:
        artifact["name"] = name
    if description:
        artifact["description"] = description
    return artifact


# ---------------------------------------------------------------------------
# SendMessageRequest constructor
# ---------------------------------------------------------------------------


def create_send_message_request(
    message: dict[str, Any],
    configuration: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a SendMessageRequest.

    This is what the client sends to POST /message/send.

    Args:
        message: The Message dict to send.
        configuration: Optional SendMessageConfiguration.
        metadata: Optional request-level metadata.

    Returns:
        A SendMessageRequest dict.
    """
    request: dict[str, Any] = {"message": message}
    if configuration:
        request["configuration"] = configuration
    if metadata:
        request["metadata"] = metadata
    return request


# ---------------------------------------------------------------------------
# Agent Card constructors
# ---------------------------------------------------------------------------


def create_agent_card(
    name: str,
    description: str,
    url: str,
    version: str = "1.0.0",
    skills: list[dict[str, Any]] | None = None,
    capabilities: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create an Agent Card for discovery.

    Served at GET /.well-known/agent.json so other agents can
    discover this agent's capabilities and endpoint.

    Args:
        name: Human-readable agent name.
        description: What the agent does.
        url: The base URL where this agent is running.
        version: Agent version string.
        skills: List of AgentSkill dicts.
        capabilities: AgentCapabilities dict.

    Returns:
        An AgentCard dict per the A2A spec.
    """
    return {
        "name": name,
        "description": description,
        "version": version,
        "supported_interfaces": [
            {
                "url": url,
                "protocol_binding": "HTTP+JSON",
                "protocol_version": "0.3",
            }
        ],
        "capabilities": capabilities or {"streaming": False, "push_notifications": False},
        "default_input_modes": ["application/json"],
        "default_output_modes": ["application/json"],
        "skills": skills or [],
    }


def create_skill(
    skill_id: str,
    name: str,
    description: str,
    tags: list[str],
    examples: list[str] | None = None,
) -> dict[str, Any]:
    """Create an AgentSkill for an Agent Card.

    Args:
        skill_id: Unique skill identifier.
        name: Human-readable name.
        description: What this skill does.
        tags: Keywords describing the skill.
        examples: Optional example prompts.

    Returns:
        An AgentSkill dict.
    """
    skill: dict[str, Any] = {
        "id": skill_id,
        "name": name,
        "description": description,
        "tags": tags,
    }
    if examples:
        skill["examples"] = examples
    return skill


# ---------------------------------------------------------------------------
# Error constants
# ---------------------------------------------------------------------------

# A2A spec error codes
ERROR_TASK_NOT_FOUND = "TaskNotFoundError"
ERROR_UNSUPPORTED_OPERATION = "UnsupportedOperationError"
ERROR_CONTENT_TYPE_NOT_SUPPORTED = "ContentTypeNotSupportedError"
ERROR_INTERNAL = "InternalError"

# Transport-layer error codes (for our HTTP client)
ERROR_TIMEOUT = "TimeoutError"
ERROR_REQUEST_FAILED = "RequestFailedError"
ERROR_INVALID_MESSAGE = "InvalidMessageError"
ERROR_AGENT_UNAVAILABLE = "AgentUnavailableError"
