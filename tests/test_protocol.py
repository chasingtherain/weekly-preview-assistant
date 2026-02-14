"""Tests for A2A protocol - Google A2A spec aligned."""

import uuid

from a2a.protocol import (
    Role,
    TaskState,
    TERMINAL_STATES,
    create_agent_card,
    create_artifact,
    create_message,
    create_send_message_request,
    create_skill,
    create_task,
    create_task_status,
    data_part,
    generate_id,
    text_part,
)


def _is_valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


class TestParts:
    def test_text_part(self) -> None:
        part = text_part("hello")
        assert part["type"] == "text"
        assert part["text"] == "hello"
        assert "metadata" not in part

    def test_text_part_with_metadata(self) -> None:
        part = text_part("hello", metadata={"source": "test"})
        assert part["metadata"]["source"] == "test"

    def test_data_part(self) -> None:
        part = data_part({"events": [1, 2, 3]})
        assert part["type"] == "data"
        assert part["data"]["events"] == [1, 2, 3]
        assert part["media_type"] == "application/json"

    def test_data_part_custom_media_type(self) -> None:
        part = data_part({"x": 1}, media_type="application/xml")
        assert part["media_type"] == "application/xml"


class TestMessage:
    def test_create_user_message(self) -> None:
        msg = create_message(Role.USER, [text_part("fetch events")])
        assert _is_valid_uuid(msg["message_id"])
        assert msg["role"] == "user"
        assert len(msg["parts"]) == 1
        assert msg["parts"][0]["text"] == "fetch events"

    def test_create_agent_message(self) -> None:
        msg = create_message(Role.AGENT, [data_part({"events": []})])
        assert msg["role"] == "agent"
        assert msg["parts"][0]["type"] == "data"

    def test_optional_fields(self) -> None:
        msg = create_message(Role.USER, [text_part("hi")])
        assert "task_id" not in msg
        assert "context_id" not in msg

        msg = create_message(
            Role.USER, [text_part("hi")], task_id="t-1", context_id="c-1"
        )
        assert msg["task_id"] == "t-1"
        assert msg["context_id"] == "c-1"

    def test_unique_ids(self) -> None:
        msg1 = create_message(Role.USER, [text_part("a")])
        msg2 = create_message(Role.USER, [text_part("b")])
        assert msg1["message_id"] != msg2["message_id"]


class TestTaskStatus:
    def test_create_status(self) -> None:
        status = create_task_status(TaskState.WORKING)
        assert status["state"] == "working"
        assert status["timestamp"].endswith("Z")
        assert "message" not in status

    def test_status_with_message(self) -> None:
        msg = create_message(Role.AGENT, [text_part("processing...")])
        status = create_task_status(TaskState.WORKING, message=msg)
        assert status["message"]["role"] == "agent"


class TestTask:
    def test_create_task_defaults(self) -> None:
        task = create_task()
        assert _is_valid_uuid(task["id"])
        assert _is_valid_uuid(task["context_id"])
        assert task["status"]["state"] == "submitted"
        assert task["artifacts"] == []
        assert task["history"] == []

    def test_create_task_with_state(self) -> None:
        task = create_task(state=TaskState.WORKING)
        assert task["status"]["state"] == "working"

    def test_create_task_with_ids(self) -> None:
        task = create_task(task_id="my-task", context_id="my-ctx")
        assert task["id"] == "my-task"
        assert task["context_id"] == "my-ctx"


class TestArtifact:
    def test_create_artifact(self) -> None:
        artifact = create_artifact(
            parts=[text_part("# Weekly Summary...")],
            name="weekly-summary",
        )
        assert _is_valid_uuid(artifact["artifact_id"])
        assert artifact["name"] == "weekly-summary"
        assert artifact["parts"][0]["text"] == "# Weekly Summary..."


class TestSendMessageRequest:
    def test_create_request(self) -> None:
        msg = create_message(Role.USER, [text_part("fetch events")])
        req = create_send_message_request(msg)
        assert req["message"]["role"] == "user"
        assert "configuration" not in req

    def test_create_request_with_config(self) -> None:
        msg = create_message(Role.USER, [text_part("fetch events")])
        req = create_send_message_request(
            msg, configuration={"blocking": True, "history_length": 5}
        )
        assert req["configuration"]["blocking"] is True


class TestAgentCard:
    def test_create_agent_card(self) -> None:
        card = create_agent_card(
            name="Calendar Agent",
            description="Fetches calendar events",
            url="http://localhost:5001",
            skills=[
                create_skill(
                    skill_id="fetch_events",
                    name="Fetch Events",
                    description="Fetch calendar events for a date range",
                    tags=["calendar", "events"],
                )
            ],
        )
        assert card["name"] == "Calendar Agent"
        assert card["supported_interfaces"][0]["url"] == "http://localhost:5001"
        assert card["supported_interfaces"][0]["protocol_binding"] == "HTTP+JSON"
        assert len(card["skills"]) == 1
        assert card["skills"][0]["id"] == "fetch_events"

    def test_create_skill(self) -> None:
        skill = create_skill("fmt", "Format", "Formats data", ["format"], examples=["format this"])
        assert skill["id"] == "fmt"
        assert skill["examples"] == ["format this"]


class TestEnums:
    def test_terminal_states(self) -> None:
        assert TaskState.COMPLETED in TERMINAL_STATES
        assert TaskState.FAILED in TERMINAL_STATES
        assert TaskState.WORKING not in TERMINAL_STATES

    def test_task_state_values(self) -> None:
        assert TaskState.SUBMITTED.value == "submitted"
        assert TaskState.AUTH_REQUIRED.value == "auth_required"

    def test_role_values(self) -> None:
        assert Role.USER.value == "user"
        assert Role.AGENT.value == "agent"
