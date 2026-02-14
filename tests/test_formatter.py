"""Tests for Formatter Agent - core logic, prompt building, and HTTP server."""

import json
from unittest.mock import MagicMock, patch

import pytest

from a2a.protocol import Role, create_message, create_send_message_request, data_part, text_part
from agents.formatter.agent import (
    FormatterAgent,
    _build_conflict_lookup,
    _build_data_section,
    _get_calendar_sources,
    build_prompt,
)


# ---------------------------------------------------------------------------
# ollama_client.py tests
# ---------------------------------------------------------------------------


class TestOllamaClient:
    @patch("agents.formatter.ollama_client.requests.post")
    def test_generate_success(self, mock_post) -> None:
        from agents.formatter.ollama_client import generate

        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "Hello, world!"}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        result = generate("Say hello", model="llama3", host="http://localhost:11434")
        assert result == "Hello, world!"
        mock_post.assert_called_once()

    @patch("agents.formatter.ollama_client.requests.post")
    def test_generate_empty_response_raises(self, mock_post) -> None:
        from agents.formatter.ollama_client import generate

        mock_response = MagicMock()
        mock_response.json.return_value = {"response": ""}
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        with pytest.raises(ValueError, match="empty response"):
            generate("Say hello")

    @patch("agents.formatter.ollama_client.requests.post")
    def test_generate_connection_error(self, mock_post) -> None:
        import requests as req
        from agents.formatter.ollama_client import generate

        mock_post.side_effect = req.ConnectionError("Connection refused")

        with pytest.raises(req.ConnectionError):
            generate("Say hello")


# ---------------------------------------------------------------------------
# agent.py - helper function tests
# ---------------------------------------------------------------------------


class TestGetCalendarSources:
    def test_extracts_unique_sources_in_order(self) -> None:
        events = [
            {"calendar_source": "You"},
            {"calendar_source": "Partner"},
            {"calendar_source": "You"},
            {"calendar_source": "Partner"},
        ]
        assert _get_calendar_sources(events) == ["You", "Partner"]

    def test_empty_events_defaults_to_you(self) -> None:
        assert _get_calendar_sources([]) == ["You"]

    def test_single_source(self) -> None:
        events = [{"calendar_source": "Work"}]
        assert _get_calendar_sources(events) == ["Work"]


class TestBuildConflictLookup:
    def test_creates_lookup_entries(self) -> None:
        conflicts = [
            {
                "date": "2025-02-18",
                "time": "Tuesday 2:00 PM",
                "events": ["Budget Review", "Client Call"],
                "calendar_source": "You",
            }
        ]
        lookup = _build_conflict_lookup(conflicts)
        assert ("2025-02-18", "Budget Review") in lookup
        assert "Client Call" in lookup[("2025-02-18", "Budget Review")]
        assert ("2025-02-18", "Client Call") in lookup
        assert "Budget Review" in lookup[("2025-02-18", "Client Call")]

    def test_empty_conflicts(self) -> None:
        assert _build_conflict_lookup([]) == {}


class TestBuildDataSection:
    def test_includes_all_seven_days(self) -> None:
        section = _build_data_section([], [], "2025-02-17", 0, "")
        # Monday through Sunday
        for day in ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]:
            assert day in section

    def test_shows_na_for_empty_days(self) -> None:
        section = _build_data_section([], [], "2025-02-17", 0, "")
        assert "- NA" in section

    def test_groups_events_by_source(self) -> None:
        events = [
            {
                "date": "2025-02-17", "day": "Monday", "time": "9:00 AM",
                "title": "Standup", "duration": "30 min", "attendees": 5,
                "location": "Zoom", "calendar_source": "You", "is_all_day": False,
            },
            {
                "date": "2025-02-17", "day": "Monday", "time": "3:00 PM",
                "title": "Soccer", "duration": "1 hour", "attendees": 0,
                "location": "Park", "calendar_source": "Partner", "is_all_day": False,
            },
        ]
        section = _build_data_section(events, [], "2025-02-17", 2, "Monday")
        assert "Your events:" in section
        assert "Partner's events:" in section
        assert "Standup" in section
        assert "Soccer" in section

    def test_includes_conflict_markers(self) -> None:
        events = [
            {
                "date": "2025-02-18", "day": "Tuesday", "time": "2:00 PM",
                "title": "Budget Review", "duration": "1 hour", "attendees": 0,
                "location": "", "calendar_source": "You", "is_all_day": False,
            },
        ]
        conflicts = [
            {
                "date": "2025-02-18",
                "time": "Tuesday 2:00 PM",
                "events": ["Budget Review", "Client Call"],
                "calendar_source": "You",
            },
        ]
        section = _build_data_section(events, conflicts, "2025-02-17", 1, "Tuesday")
        assert "CONFLICT" in section
        assert "Overlaps with Client Call" in section

    def test_week_header_info(self) -> None:
        section = _build_data_section([], [], "2025-02-17", 5, "Tuesday")
        assert "Total events: 5" in section
        assert "Busiest day: Tuesday" in section


class TestBuildPrompt:
    def test_prompt_contains_instructions(self) -> None:
        prompt = build_prompt([], [], "2025-02-17", 0, "")
        assert "WEEK AT A GLANCE" in prompt
        assert "DAY BY DAY" in prompt
        assert "INSIGHTS" in prompt
        assert "CONFLICTS" in prompt
        assert "calendar source" in prompt.lower() or "calendar source" in prompt

    def test_prompt_contains_data(self) -> None:
        events = [
            {
                "date": "2025-02-17", "day": "Monday", "time": "9:00 AM",
                "title": "Team Standup", "duration": "30 min", "attendees": 3,
                "location": "", "calendar_source": "You", "is_all_day": False,
            },
        ]
        prompt = build_prompt(events, [], "2025-02-17", 1, "Monday")
        assert "Team Standup" in prompt
        assert "MONDAY" in prompt


# ---------------------------------------------------------------------------
# agent.py - FormatterAgent tests
# ---------------------------------------------------------------------------


class TestFormatterAgent:
    @patch("agents.formatter.agent.generate")
    def test_format_weekly_preview_success(self, mock_generate) -> None:
        mock_generate.return_value = "# WEEK OF FEBRUARY 17-23\n\nSome preview content here."

        agent = FormatterAgent(ollama_host="http://localhost:11434", ollama_model="llama3")
        result = agent.format_weekly_preview(
            events=[
                {
                    "date": "2025-02-17", "day": "Monday", "time": "9:00 AM",
                    "title": "Standup", "duration": "30 min", "attendees": 5,
                    "location": "Zoom", "calendar_source": "You", "is_all_day": False,
                },
            ],
            conflicts=[],
            week_start="2025-02-17",
            total_events=1,
            busiest_day="Monday",
        )

        assert result["format"] == "markdown"
        assert result["word_count"] > 0
        assert "WEEK OF FEBRUARY" in result["formatted_summary"]
        mock_generate.assert_called_once()

    @patch("agents.formatter.agent.generate")
    def test_format_weekly_preview_passes_correct_model(self, mock_generate) -> None:
        mock_generate.return_value = "Preview content."

        agent = FormatterAgent(ollama_host="http://myhost:11434", ollama_model="mistral")
        agent.format_weekly_preview(
            events=[], conflicts=[], week_start="2025-02-17",
            total_events=0, busiest_day="",
        )

        _, kwargs = mock_generate.call_args
        assert kwargs["model"] == "mistral"
        assert kwargs["host"] == "http://myhost:11434"


# ---------------------------------------------------------------------------
# server.py - HTTP endpoint tests
# ---------------------------------------------------------------------------


class TestFormatterServer:
    @pytest.fixture
    def client(self):
        from agents.formatter.server import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

    def test_agent_card_endpoint(self, client) -> None:
        response = client.get("/.well-known/agent.json")
        assert response.status_code == 200
        card = response.get_json()
        assert card["name"] == "Formatter Agent"
        assert card["skills"][0]["id"] == "format_weekly_preview"
        assert card["supported_interfaces"][0]["protocol_binding"] == "HTTP+JSON"

    def test_get_task_not_found(self, client) -> None:
        response = client.get("/tasks/nonexistent-id")
        assert response.status_code == 404
        data = response.get_json()
        assert data["error"]["code"] == "TaskNotFoundError"

    def test_send_message_invalid_request(self, client) -> None:
        response = client.post(
            "/message/send",
            json={"message": {"role": "user"}},  # missing message_id and parts
            content_type="application/json",
        )
        assert response.status_code == 400

    @patch("agents.formatter.server._get_agent")
    def test_send_message_success(self, mock_get_agent, client) -> None:
        mock_agent = MagicMock()
        mock_agent.format_weekly_preview.return_value = {
            "formatted_summary": "# WEEK OF FEB 17-23\n\nGreat week ahead!",
            "format": "markdown",
            "word_count": 6,
        }
        mock_get_agent.return_value = mock_agent

        msg = create_message(
            Role.USER,
            [data_part({
                "action": "format_weekly_preview",
                "parameters": {
                    "events": [
                        {"day": "Monday", "date": "2025-02-17", "time": "9:00 AM",
                         "title": "Standup", "duration": "30 min", "attendees": 5,
                         "location": "Zoom", "calendar_source": "You", "is_all_day": False},
                    ],
                    "conflicts": [],
                    "week_start": "2025-02-17",
                    "total_events": 1,
                    "busiest_day": "Monday",
                },
            })],
        )
        req = create_send_message_request(msg)

        response = client.post("/message/send", json=req, content_type="application/json")
        assert response.status_code == 200

        data = response.get_json()
        task = data["task"]
        assert task["status"]["state"] == "completed"
        assert len(task["artifacts"]) == 1
        # First part is TextPart with the summary
        assert "WEEK OF FEB" in task["artifacts"][0]["parts"][0]["text"]
        # Second part is DataPart with metadata
        assert task["artifacts"][0]["parts"][1]["data"]["word_count"] == 6

        # Verify we can also fetch the task by ID
        task_id = task["id"]
        get_response = client.get(f"/tasks/{task_id}")
        assert get_response.status_code == 200
        assert get_response.get_json()["id"] == task_id

    def test_send_message_no_params(self, client) -> None:
        msg = create_message(Role.USER, [text_part("just some text, no action")])
        req = create_send_message_request(msg)

        response = client.post("/message/send", json=req, content_type="application/json")
        assert response.status_code == 200

        data = response.get_json()
        assert data["task"]["status"]["state"] == "failed"

    @patch("agents.formatter.server._get_agent")
    def test_send_message_ollama_error(self, mock_get_agent, client) -> None:
        mock_agent = MagicMock()
        mock_agent.format_weekly_preview.side_effect = Exception("Ollama connection refused")
        mock_get_agent.return_value = mock_agent

        msg = create_message(
            Role.USER,
            [data_part({
                "action": "format_weekly_preview",
                "parameters": {
                    "events": [], "conflicts": [], "week_start": "2025-02-17",
                    "total_events": 0, "busiest_day": "",
                },
            })],
        )
        req = create_send_message_request(msg)

        response = client.post("/message/send", json=req, content_type="application/json")
        assert response.status_code == 200

        data = response.get_json()
        assert data["task"]["status"]["state"] == "failed"
