"""Tests for Formatter Agent - chat format building and HTTP server."""

import json
from unittest.mock import MagicMock, patch

import pytest

from a2a.protocol import Role, create_message, create_send_message_request, data_part, text_part
from agents.formatter.agent import (
    FormatterAgent,
    _build_conflict_lookup,
    _duration_minutes,
    _format_duration_compact,
    _format_time_compact,
    _get_calendar_sources,
    build_chat_format,
    build_markdown,
)


# ---------------------------------------------------------------------------
# ollama_client.py tests (kept for the module itself)
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
            generate("Say hello", model="llama3")

    @patch("agents.formatter.ollama_client.requests.post")
    def test_generate_connection_error(self, mock_post) -> None:
        import requests as req
        from agents.formatter.ollama_client import generate

        mock_post.side_effect = req.ConnectionError("Connection refused")

        with pytest.raises(req.ConnectionError):
            generate("Say hello", model="llama3")


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


# ---------------------------------------------------------------------------
# agent.py - build_markdown tests
# ---------------------------------------------------------------------------


class TestBuildMarkdown:
    def test_includes_all_seven_days(self) -> None:
        md = build_markdown([], [], "2025-02-17")
        for day in ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]:
            assert day in md

    def test_shows_na_for_empty_days(self) -> None:
        md = build_markdown([], [], "2025-02-17")
        assert "* NA" in md

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
        md = build_markdown(events, [], "2025-02-17")
        assert "Your events:" in md
        assert "Partner's events:" in md
        assert "Standup" in md
        assert "Soccer" in md

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
        md = build_markdown(events, conflicts, "2025-02-17")
        assert "CONFLICT" in md
        assert "Overlaps with Client Call" in md

    def test_week_header(self) -> None:
        md = build_markdown([], [], "2025-02-17")
        assert "## Week of February 17 - February 23, 2025" in md

    def test_no_llm_sections(self) -> None:
        md = build_markdown([], [], "2025-02-17")
        assert "CALENDAR DATA" not in md
        assert "Total events:" not in md
        assert "Busiest day:" not in md
        assert "INSIGHTS" not in md

    def test_includes_location(self) -> None:
        events = [
            {
                "date": "2025-02-17", "day": "Monday", "time": "9:00 AM",
                "title": "Meeting", "duration": "1 hour", "attendees": 0,
                "location": "Zoom", "calendar_source": "You", "is_all_day": False,
            },
        ]
        md = build_markdown(events, [], "2025-02-17")
        assert "Zoom" in md

    def test_includes_attendees(self) -> None:
        events = [
            {
                "date": "2025-02-17", "day": "Monday", "time": "9:00 AM",
                "title": "Meeting", "duration": "1 hour", "attendees": 5,
                "location": "", "calendar_source": "You", "is_all_day": False,
            },
        ]
        md = build_markdown(events, [], "2025-02-17")
        assert "[5 attendees]" in md


# ---------------------------------------------------------------------------
# agent.py - build_chat_format tests
# ---------------------------------------------------------------------------


class TestBuildChatFormat:
    def test_skips_empty_days(self) -> None:
        events = [
            {
                "date": "2025-02-17", "day": "Monday", "time": "9:00 AM",
                "title": "Standup", "duration": "30 min", "attendees": 5,
                "location": "Zoom", "calendar_source": "You", "is_all_day": False,
            },
            {
                "date": "2025-02-19", "day": "Wednesday", "time": "2:00 PM",
                "title": "Sync", "duration": "1 hour", "attendees": 0,
                "location": "", "calendar_source": "You", "is_all_day": False,
            },
        ]
        output = build_chat_format(events, [], "2025-02-17")
        assert "Mon" in output
        assert "Wed" in output
        assert "Tue" not in output
        assert "Thu" not in output
        assert "NA" not in output

    def test_emoji_mapping(self) -> None:
        events = [
            {
                "date": "2025-02-17", "day": "Monday", "time": "9:00 AM",
                "title": "Meeting", "duration": "30 min", "attendees": 0,
                "location": "", "calendar_source": "JP", "is_all_day": False,
            },
            {
                "date": "2025-02-17", "day": "Monday", "time": "3:00 PM",
                "title": "Soccer", "duration": "1 hour", "attendees": 0,
                "location": "", "calendar_source": "VT", "is_all_day": False,
            },
        ]
        output = build_chat_format(events, [], "2025-02-17")
        assert "🔵 JP:" in output
        assert "🟢 VT:" in output

    def test_compact_time(self) -> None:
        events = [
            {
                "date": "2025-02-17", "day": "Monday", "time": "9:00 AM",
                "title": "Standup", "duration": "30 min", "attendees": 0,
                "location": "", "calendar_source": "You", "is_all_day": False,
            },
        ]
        output = build_chat_format(events, [], "2025-02-17")
        assert "(9am)" in output
        assert "9:00 AM" not in output

    def test_all_day_event(self) -> None:
        events = [
            {
                "date": "2025-02-17", "day": "Monday", "time": "All day",
                "title": "Birthday", "duration": "All day", "attendees": 0,
                "location": "", "calendar_source": "You", "all_day": True,
            },
        ]
        output = build_chat_format(events, [], "2025-02-17")
        assert "(all day)" in output

    def test_duration_shown_when_notable(self) -> None:
        events = [
            {
                "date": "2025-02-17", "day": "Monday", "time": "12:00 PM",
                "title": "Long Meeting", "duration": "2 hours", "attendees": 0,
                "location": "", "calendar_source": "You", "is_all_day": False,
            },
            {
                "date": "2025-02-17", "day": "Monday", "time": "3:00 PM",
                "title": "Quick Chat", "duration": "30 min", "attendees": 0,
                "location": "", "calendar_source": "You", "is_all_day": False,
            },
        ]
        output = build_chat_format(events, [], "2025-02-17")
        assert "(12pm, 2hrs)" in output
        assert "(3pm)" in output

    def test_whatsapp_bold_format(self) -> None:
        output = build_chat_format([], [], "2025-02-17")
        # Single asterisk bold, no markdown ** or ###
        assert "📅 *Week of" in output
        assert "**" not in output
        assert "###" not in output

    def test_conflict_marker(self) -> None:
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
        output = build_chat_format(events, conflicts, "2025-02-17")
        assert "⚠️" in output

    def test_week_header_same_month(self) -> None:
        output = build_chat_format([], [], "2025-02-17")
        assert "📅 *Week of 17-23 Feb*" in output

    def test_week_header_cross_month(self) -> None:
        output = build_chat_format([], [], "2025-02-24")
        assert "📅 *Week of 24 Feb - 2 Mar*" in output

    def test_no_events_produces_header_only(self) -> None:
        output = build_chat_format([], [], "2025-02-17")
        assert output == "📅 *Week of 17-23 Feb*"


class TestFormatTimeCompact:
    def test_on_the_hour(self) -> None:
        assert _format_time_compact("9:00 AM") == "9am"
        assert _format_time_compact("12:00 PM") == "12pm"

    def test_with_minutes(self) -> None:
        assert _format_time_compact("9:30 AM") == "9:30am"

    def test_all_day(self) -> None:
        assert _format_time_compact("All day") == ""
        assert _format_time_compact("") == ""

    def test_unparseable(self) -> None:
        assert _format_time_compact("noon") == "noon"


class TestDurationMinutes:
    def test_hours(self) -> None:
        assert _duration_minutes("2 hours") == 120
        assert _duration_minutes("1 hour") == 60

    def test_minutes(self) -> None:
        assert _duration_minutes("30 min") == 30

    def test_combined(self) -> None:
        assert _duration_minutes("1 hour 30 min") == 90

    def test_all_day(self) -> None:
        assert _duration_minutes("All day") == 0

    def test_empty(self) -> None:
        assert _duration_minutes("") == 0


class TestFormatDurationCompact:
    def test_whole_hours(self) -> None:
        assert _format_duration_compact("2 hours") == "2hrs"

    def test_fractional(self) -> None:
        assert _format_duration_compact("1 hour 30 min") == "1.5hrs"


# ---------------------------------------------------------------------------
# agent.py - FormatterAgent tests
# ---------------------------------------------------------------------------


class TestFormatterAgent:
    def test_format_weekly_preview_chat_format(self) -> None:
        agent = FormatterAgent()
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

        assert result["format"] == "chat"
        assert result["word_count"] > 0
        assert "Standup" in result["formatted_summary"]
        assert "Mon" in result["formatted_summary"]

    def test_format_weekly_preview_no_events(self) -> None:
        agent = FormatterAgent()
        result = agent.format_weekly_preview(
            events=[], conflicts=[], week_start="2025-02-17",
            total_events=0, busiest_day="",
        )

        assert result["format"] == "chat"
        assert "NA" not in result["formatted_summary"]


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

    def test_send_message_success(self, client) -> None:
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
        assert "Standup" in task["artifacts"][0]["parts"][0]["text"]

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
    def test_send_message_agent_error(self, mock_get_agent, client) -> None:
        mock_agent = MagicMock()
        mock_agent.format_weekly_preview.side_effect = Exception("Unexpected error")
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
