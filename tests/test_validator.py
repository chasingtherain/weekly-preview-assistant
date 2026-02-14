"""Tests for A2A validator - Google A2A spec aligned."""

from a2a.protocol import (
    Role,
    TaskState,
    create_agent_card,
    create_message,
    create_send_message_request,
    create_skill,
    create_task,
    data_part,
    text_part,
)
from a2a.validator import (
    validate_agent_card,
    validate_message,
    validate_part,
    validate_send_message_request,
    validate_task,
    validate_task_status,
)


class TestPartValidation:
    def test_valid_text_part(self) -> None:
        valid, err = validate_part(text_part("hello"))
        assert valid

    def test_valid_data_part(self) -> None:
        valid, err = validate_part(data_part({"x": 1}))
        assert valid

    def test_missing_text_field(self) -> None:
        valid, err = validate_part({"type": "text"})
        assert not valid
        assert "text" in err

    def test_missing_data_field(self) -> None:
        valid, err = validate_part({"type": "data"})
        assert not valid
        assert "data" in err

    def test_unknown_type(self) -> None:
        valid, err = validate_part({"type": "banana"})
        assert not valid
        assert "Unknown part type" in err

    def test_not_a_dict(self) -> None:
        valid, err = validate_part("string")
        assert not valid


class TestMessageValidation:
    def test_valid_message(self) -> None:
        msg = create_message(Role.USER, [text_part("hi")])
        valid, err = validate_message(msg)
        assert valid

    def test_not_a_dict(self) -> None:
        valid, err = validate_message("string")
        assert not valid

    def test_missing_message_id(self) -> None:
        msg = create_message(Role.USER, [text_part("hi")])
        del msg["message_id"]
        valid, err = validate_message(msg)
        assert not valid
        assert "message_id" in err

    def test_invalid_role(self) -> None:
        msg = create_message(Role.USER, [text_part("hi")])
        msg["role"] = "robot"
        valid, err = validate_message(msg)
        assert not valid
        assert "role" in err

    def test_empty_parts(self) -> None:
        msg = create_message(Role.USER, [text_part("hi")])
        msg["parts"] = []
        valid, err = validate_message(msg)
        assert not valid
        assert "parts" in err

    def test_invalid_part_inside_message(self) -> None:
        msg = create_message(Role.USER, [text_part("hi")])
        msg["parts"] = [{"type": "banana"}]
        valid, err = validate_message(msg)
        assert not valid
        assert "parts[0]" in err


class TestTaskStatusValidation:
    def test_valid_status(self) -> None:
        from a2a.protocol import create_task_status

        status = create_task_status(TaskState.WORKING)
        valid, err = validate_task_status(status)
        assert valid

    def test_invalid_state(self) -> None:
        valid, err = validate_task_status({"state": "flying", "timestamp": "2025-01-01T00:00:00Z"})
        assert not valid
        assert "state" in err

    def test_missing_timestamp(self) -> None:
        valid, err = validate_task_status({"state": "working"})
        assert not valid
        assert "timestamp" in err


class TestTaskValidation:
    def test_valid_task(self) -> None:
        task = create_task()
        valid, err = validate_task(task)
        assert valid

    def test_missing_id(self) -> None:
        task = create_task()
        del task["id"]
        valid, err = validate_task(task)
        assert not valid
        assert "id" in err

    def test_missing_context_id(self) -> None:
        task = create_task()
        del task["context_id"]
        valid, err = validate_task(task)
        assert not valid
        assert "context_id" in err

    def test_missing_status(self) -> None:
        task = create_task()
        del task["status"]
        valid, err = validate_task(task)
        assert not valid
        assert "status" in err

    def test_invalid_status_state(self) -> None:
        task = create_task()
        task["status"]["state"] = "invalid"
        valid, err = validate_task(task)
        assert not valid
        assert "state" in err


class TestSendMessageRequestValidation:
    def test_valid_request(self) -> None:
        msg = create_message(Role.USER, [text_part("hi")])
        req = create_send_message_request(msg)
        valid, err = validate_send_message_request(req)
        assert valid

    def test_missing_message(self) -> None:
        valid, err = validate_send_message_request({})
        assert not valid
        assert "message" in err

    def test_invalid_message_inside(self) -> None:
        req = {"message": {"role": "user"}}  # missing message_id and parts
        valid, err = validate_send_message_request(req)
        assert not valid


class TestAgentCardValidation:
    def test_valid_card(self) -> None:
        card = create_agent_card(
            name="Test Agent",
            description="A test agent",
            url="http://localhost:5001",
            skills=[create_skill("s1", "Skill 1", "Does stuff", ["test"])],
        )
        valid, err = validate_agent_card(card)
        assert valid

    def test_valid_card_no_skills(self) -> None:
        card = create_agent_card(
            name="Test", description="Test", url="http://localhost:5001"
        )
        valid, err = validate_agent_card(card)
        assert valid

    def test_missing_name(self) -> None:
        card = create_agent_card(name="Test", description="Test", url="http://localhost:5001")
        card["name"] = ""
        valid, err = validate_agent_card(card)
        assert not valid
        assert "name" in err

    def test_missing_interfaces(self) -> None:
        card = create_agent_card(name="Test", description="Test", url="http://localhost:5001")
        card["supported_interfaces"] = []
        valid, err = validate_agent_card(card)
        assert not valid
        assert "supported_interfaces" in err

    def test_interface_missing_url(self) -> None:
        card = create_agent_card(name="Test", description="Test", url="http://localhost:5001")
        card["supported_interfaces"][0]["url"] = ""
        valid, err = validate_agent_card(card)
        assert not valid
        assert "url" in err

    def test_skill_missing_required_field(self) -> None:
        card = create_agent_card(
            name="Test",
            description="Test",
            url="http://localhost:5001",
            skills=[{"id": "s1", "name": "S1"}],  # missing description and tags
        )
        valid, err = validate_agent_card(card)
        assert not valid
        assert "skills[0]" in err
