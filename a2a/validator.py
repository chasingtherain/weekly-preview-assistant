"""A2A Message Validator - Google A2A spec aligned.

Validates that Messages, Tasks, SendMessageRequests, and Agent Cards
conform to the A2A protocol schema.

A2A Concept: Validation ensures agents speak the same language. A malformed
message is caught early rather than causing confusing downstream failures.
"""

from a2a.protocol import Role, TaskState


# ---------------------------------------------------------------------------
# Part validation
# ---------------------------------------------------------------------------


def validate_part(part: dict) -> tuple[bool, str]:
    """Validate a Part dict.

    A Part must have a "type" field and the corresponding content field.

    Args:
        part: The Part dict to validate.

    Returns:
        (is_valid, error_description).
    """
    if not isinstance(part, dict):
        return False, "Part must be a dict."

    part_type = part.get("type")
    if part_type == "text":
        if "text" not in part:
            return False, "TextPart must include 'text' field."
    elif part_type == "data":
        if "data" not in part:
            return False, "DataPart must include 'data' field."
    elif part_type == "file":
        if "url" not in part and "raw" not in part:
            return False, "FilePart must include 'url' or 'raw' field."
    else:
        return False, f"Unknown part type: {part_type}"

    return True, ""


# ---------------------------------------------------------------------------
# Message validation
# ---------------------------------------------------------------------------


def validate_message(message: dict) -> tuple[bool, str]:
    """Validate an A2A Message.

    Required fields: message_id, role, parts (non-empty).

    Args:
        message: The Message dict to validate.

    Returns:
        (is_valid, error_description).
    """
    if not isinstance(message, dict):
        return False, "Message must be a dict."

    if "message_id" not in message:
        return False, "Message must include 'message_id'."

    role = message.get("role")
    valid_roles = {r.value for r in Role}
    if role not in valid_roles:
        return False, f"Message 'role' must be one of {valid_roles}, got: {role}"

    parts = message.get("parts")
    if not isinstance(parts, list) or len(parts) == 0:
        return False, "Message 'parts' must be a non-empty list."

    for i, part in enumerate(parts):
        is_valid, err = validate_part(part)
        if not is_valid:
            return False, f"parts[{i}]: {err}"

    return True, ""


# ---------------------------------------------------------------------------
# TaskStatus validation
# ---------------------------------------------------------------------------


def validate_task_status(status: dict) -> tuple[bool, str]:
    """Validate a TaskStatus dict.

    Required fields: state, timestamp.

    Args:
        status: The TaskStatus dict to validate.

    Returns:
        (is_valid, error_description).
    """
    if not isinstance(status, dict):
        return False, "TaskStatus must be a dict."

    state = status.get("state")
    valid_states = {s.value for s in TaskState}
    if state not in valid_states:
        return False, f"TaskStatus 'state' must be one of {valid_states}, got: {state}"

    if "timestamp" not in status:
        return False, "TaskStatus must include 'timestamp'."

    return True, ""


# ---------------------------------------------------------------------------
# Task validation
# ---------------------------------------------------------------------------


def validate_task(task: dict) -> tuple[bool, str]:
    """Validate a Task dict.

    Required fields: id, context_id, status.

    Args:
        task: The Task dict to validate.

    Returns:
        (is_valid, error_description).
    """
    if not isinstance(task, dict):
        return False, "Task must be a dict."

    if "id" not in task:
        return False, "Task must include 'id'."
    if "context_id" not in task:
        return False, "Task must include 'context_id'."

    status = task.get("status")
    if not status:
        return False, "Task must include 'status'."
    is_valid, err = validate_task_status(status)
    if not is_valid:
        return False, f"Task status: {err}"

    return True, ""


# ---------------------------------------------------------------------------
# SendMessageRequest validation
# ---------------------------------------------------------------------------


def validate_send_message_request(request: dict) -> tuple[bool, str]:
    """Validate a SendMessageRequest dict.

    Required: message (a valid Message).

    Args:
        request: The SendMessageRequest dict to validate.

    Returns:
        (is_valid, error_description).
    """
    if not isinstance(request, dict):
        return False, "SendMessageRequest must be a dict."

    msg = request.get("message")
    if not msg:
        return False, "SendMessageRequest must include 'message'."

    return validate_message(msg)


# ---------------------------------------------------------------------------
# Agent Card validation
# ---------------------------------------------------------------------------


def validate_agent_card(card: dict) -> tuple[bool, str]:
    """Validate an AgentCard dict.

    Required fields: name, description, version, supported_interfaces, skills.

    Args:
        card: The AgentCard dict to validate.

    Returns:
        (is_valid, error_description).
    """
    if not isinstance(card, dict):
        return False, "AgentCard must be a dict."

    for field in ("name", "description", "version"):
        if not card.get(field):
            return False, f"AgentCard must include '{field}'."

    interfaces = card.get("supported_interfaces")
    if not isinstance(interfaces, list) or len(interfaces) == 0:
        return False, "AgentCard must include non-empty 'supported_interfaces'."

    for i, iface in enumerate(interfaces):
        for field in ("url", "protocol_binding", "protocol_version"):
            if not iface.get(field):
                return False, f"supported_interfaces[{i}] must include '{field}'."

    skills = card.get("skills")
    if not isinstance(skills, list):
        return False, "AgentCard must include 'skills' list."

    for i, skill in enumerate(skills):
        for field in ("id", "name", "description", "tags"):
            if field not in skill:
                return False, f"skills[{i}] must include '{field}'."

    return True, ""
