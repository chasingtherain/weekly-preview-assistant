"""Integration Tests - End-to-end A2A message flows.

These tests spin up real Flask test clients for multiple agents and
verify that A2A messages flow correctly between them. Unlike unit tests
(which mock the agent internals), these test the actual HTTP endpoints
and A2A protocol interactions.

What we're testing:
- Agent Card discovery works across agents
- SendMessageRequest flows through the full Task lifecycle
- Data passes correctly between agents via Parts and Artifacts
- Error cases propagate properly through the A2A chain
- The orchestrator correctly chains Calendar → Formatter
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from a2a.protocol import (
    Role,
    TaskState,
    create_artifact,
    create_message,
    create_send_message_request,
    create_task,
    create_task_status,
    data_part,
    text_part,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def calendar_client():
    """Flask test client for Calendar Agent."""
    from agents.calendar.server import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def formatter_client():
    """Flask test client for Formatter Agent."""
    from agents.formatter.server import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def orchestrator_client():
    """Flask test client for Orchestrator Agent."""
    from agents.orchestrator.server import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


# ---------------------------------------------------------------------------
# Test 1: Agent Card Discovery across all agents
# ---------------------------------------------------------------------------


class TestAgentCardDiscovery:
    """Verify all three agents serve valid Agent Cards."""

    def test_all_agents_serve_agent_cards(
        self, calendar_client, formatter_client, orchestrator_client
    ) -> None:
        """Each agent should respond to GET /.well-known/agent.json with a valid card."""
        agents = [
            (calendar_client, "Calendar Agent", "fetch_week_events"),
            (formatter_client, "Formatter Agent", "format_weekly_preview"),
            (orchestrator_client, "Orchestrator Agent", "generate_weekly_preview"),
        ]

        for client, expected_name, expected_skill in agents:
            response = client.get("/.well-known/agent.json")
            assert response.status_code == 200, f"{expected_name} Agent Card failed"

            card = response.get_json()
            assert card["name"] == expected_name
            assert len(card["skills"]) >= 1
            assert card["skills"][0]["id"] == expected_skill
            assert card["supported_interfaces"][0]["protocol_binding"] == "HTTP+JSON"

    def test_agent_cards_have_consistent_structure(
        self, calendar_client, formatter_client, orchestrator_client
    ) -> None:
        """All Agent Cards should share the same structural fields."""
        required_fields = {"name", "description", "version", "supported_interfaces", "capabilities", "skills"}

        for client in [calendar_client, formatter_client, orchestrator_client]:
            card = client.get("/.well-known/agent.json").get_json()
            assert required_fields.issubset(set(card.keys()))


# ---------------------------------------------------------------------------
# Test 2: Calendar Agent A2A flow
# ---------------------------------------------------------------------------


class TestCalendarAgentA2AFlow:
    """Test complete A2A message flow through the Calendar Agent."""

    @patch("agents.calendar.server._get_agent")
    def test_full_task_lifecycle(self, mock_get_agent, calendar_client) -> None:
        """SendMessage should create a Task that goes through SUBMITTED → WORKING → COMPLETED."""
        mock_agent = MagicMock()
        mock_agent.fetch_week_events.return_value = {
            "events": [
                {"day": "Monday", "date": "2025-02-17", "time": "9:00 AM",
                 "title": "Standup", "duration": "30 min", "attendees": 5,
                 "location": "Zoom", "calendar_source": "You", "is_all_day": False},
                {"day": "Tuesday", "date": "2025-02-18", "time": "2:00 PM",
                 "title": "1:1", "duration": "30 min", "attendees": 2,
                 "location": "", "calendar_source": "You", "is_all_day": False},
            ],
            "conflicts": [],
            "total_events": 2,
            "busiest_day": "Monday",
        }
        mock_get_agent.return_value = mock_agent

        # Build A2A request
        msg = create_message(
            Role.USER,
            [data_part({
                "action": "fetch_week_events",
                "parameters": {
                    "start_date": "2025-02-17",
                    "end_date": "2025-02-23",
                    "calendars": [{"calendar_id": "primary", "label": "You"}],
                },
            })],
        )
        req = create_send_message_request(msg)

        # Send via A2A
        response = calendar_client.post("/message/send", json=req, content_type="application/json")
        assert response.status_code == 200

        data = response.get_json()
        task = data["task"]

        # Verify Task lifecycle reached COMPLETED
        assert task["status"]["state"] == "completed"
        assert "id" in task
        assert "context_id" in task

        # Verify Artifact contains the event data
        assert len(task["artifacts"]) == 1
        artifact = task["artifacts"][0]
        assert "artifact_id" in artifact

        event_data = artifact["parts"][0]["data"]
        assert event_data["total_events"] == 2
        assert len(event_data["events"]) == 2
        assert event_data["events"][0]["title"] == "Standup"

        # Verify Task is retrievable via GetTask
        task_id = task["id"]
        get_response = calendar_client.get(f"/tasks/{task_id}")
        assert get_response.status_code == 200
        assert get_response.get_json()["status"]["state"] == "completed"


# ---------------------------------------------------------------------------
# Test 3: Formatter Agent A2A flow
# ---------------------------------------------------------------------------


class TestFormatterAgentA2AFlow:
    """Test complete A2A message flow through the Formatter Agent."""

    @patch("agents.formatter.server._get_agent")
    def test_full_task_lifecycle(self, mock_get_agent, formatter_client) -> None:
        """SendMessage should produce a TextPart artifact with the formatted preview."""
        mock_agent = MagicMock()
        mock_agent.format_weekly_preview.return_value = {
            "formatted_summary": "# WEEK OF FEBRUARY 17-23, 2025\n\n## WEEK AT A GLANCE\n- 2 events",
            "format": "markdown",
            "word_count": 10,
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

        response = formatter_client.post("/message/send", json=req, content_type="application/json")
        assert response.status_code == 200

        task = response.get_json()["task"]
        assert task["status"]["state"] == "completed"

        # Verify artifact structure: TextPart (summary) + DataPart (metadata)
        artifact = task["artifacts"][0]
        assert len(artifact["parts"]) == 2

        text_artifact = artifact["parts"][0]
        assert text_artifact["type"] == "text"
        assert "WEEK OF FEBRUARY" in text_artifact["text"]

        data_artifact = artifact["parts"][1]
        assert data_artifact["type"] == "data"
        assert data_artifact["data"]["word_count"] == 10


# ---------------------------------------------------------------------------
# Test 4: Cross-agent data flow (Calendar → Formatter)
# ---------------------------------------------------------------------------


class TestCrossAgentDataFlow:
    """Test that data produced by Calendar Agent can be consumed by Formatter Agent."""

    @patch("agents.formatter.server._get_agent")
    @patch("agents.calendar.server._get_agent")
    def test_calendar_output_feeds_formatter_input(
        self, mock_cal_agent, mock_fmt_agent, calendar_client, formatter_client
    ) -> None:
        """The Calendar Agent's artifact data should be directly usable as Formatter input."""
        # Set up Calendar Agent mock
        calendar_data = {
            "events": [
                {"day": "Monday", "date": "2025-02-17", "time": "9:00 AM",
                 "title": "Standup", "duration": "30 min", "attendees": 5,
                 "location": "Zoom", "calendar_source": "You", "is_all_day": False},
                {"day": "Monday", "date": "2025-02-17", "time": "3:00 PM",
                 "title": "Soccer", "duration": "1 hour", "attendees": 0,
                 "location": "Park", "calendar_source": "Partner", "is_all_day": False},
            ],
            "conflicts": [],
            "total_events": 2,
            "busiest_day": "Monday",
        }
        mock_cal = MagicMock()
        mock_cal.fetch_week_events.return_value = calendar_data
        mock_cal_agent.return_value = mock_cal

        # Step 1: Get data from Calendar Agent
        cal_msg = create_message(
            Role.USER,
            [data_part({
                "action": "fetch_week_events",
                "parameters": {
                    "start_date": "2025-02-17",
                    "end_date": "2025-02-23",
                    "calendars": [
                        {"calendar_id": "primary", "label": "You"},
                        {"calendar_id": "partner@gmail.com", "label": "Partner"},
                    ],
                },
            })],
        )
        cal_req = create_send_message_request(cal_msg)
        cal_response = calendar_client.post("/message/send", json=cal_req, content_type="application/json")
        cal_task = cal_response.get_json()["task"]

        # Extract calendar data from artifact
        cal_artifact_data = cal_task["artifacts"][0]["parts"][0]["data"]

        # Set up Formatter Agent mock
        mock_fmt = MagicMock()
        mock_fmt.format_weekly_preview.return_value = {
            "formatted_summary": "# WEEK OF FEB 17-23\n\nFormatted preview with both calendars.",
            "format": "markdown",
            "word_count": 8,
        }
        mock_fmt_agent.return_value = mock_fmt

        # Step 2: Feed calendar data to Formatter Agent
        fmt_msg = create_message(
            Role.USER,
            [data_part({
                "action": "format_weekly_preview",
                "parameters": {
                    "events": cal_artifact_data["events"],
                    "conflicts": cal_artifact_data["conflicts"],
                    "week_start": "2025-02-17",
                    "total_events": cal_artifact_data["total_events"],
                    "busiest_day": cal_artifact_data["busiest_day"],
                },
            })],
        )
        fmt_req = create_send_message_request(fmt_msg)
        fmt_response = formatter_client.post("/message/send", json=fmt_req, content_type="application/json")
        fmt_task = fmt_response.get_json()["task"]

        assert fmt_task["status"]["state"] == "completed"
        summary = fmt_task["artifacts"][0]["parts"][0]["text"]
        assert "WEEK OF FEB" in summary

        # Verify formatter received the correct data
        call_args = mock_fmt.format_weekly_preview.call_args
        assert call_args.kwargs["total_events"] == 2
        assert len(call_args.kwargs["events"]) == 2
        assert call_args.kwargs["events"][1]["calendar_source"] == "Partner"


# ---------------------------------------------------------------------------
# Test 5: Error propagation through A2A
# ---------------------------------------------------------------------------


class TestErrorPropagation:
    """Test that errors propagate correctly through A2A messages."""

    def test_invalid_request_returns_400(self, calendar_client, formatter_client) -> None:
        """Malformed SendMessageRequests should return 400."""
        bad_request = {"message": {"role": "user"}}  # Missing required fields

        for client in [calendar_client, formatter_client]:
            response = client.post("/message/send", json=bad_request, content_type="application/json")
            assert response.status_code == 400
            assert "error" in response.get_json()

    def test_missing_action_returns_failed_task(self, calendar_client) -> None:
        """A valid request without action params should return a FAILED task."""
        msg = create_message(Role.USER, [text_part("hello")])
        req = create_send_message_request(msg)

        response = calendar_client.post("/message/send", json=req, content_type="application/json")
        assert response.status_code == 200

        task = response.get_json()["task"]
        assert task["status"]["state"] == "failed"

    @patch("agents.calendar.server._get_agent")
    def test_agent_exception_returns_failed_task(self, mock_get_agent, calendar_client) -> None:
        """If the agent raises an exception, the task should be FAILED."""
        mock_agent = MagicMock()
        mock_agent.fetch_week_events.side_effect = RuntimeError("Google API down")
        mock_get_agent.return_value = mock_agent

        msg = create_message(
            Role.USER,
            [data_part({
                "action": "fetch_week_events",
                "parameters": {
                    "start_date": "2025-02-17", "end_date": "2025-02-23",
                    "calendars": [{"calendar_id": "primary", "label": "You"}],
                },
            })],
        )
        req = create_send_message_request(msg)

        response = calendar_client.post("/message/send", json=req, content_type="application/json")
        task = response.get_json()["task"]

        assert task["status"]["state"] == "failed"
        # Error message should be in the status message
        error_text = task["status"]["message"]["parts"][0]["text"]
        assert "Google API down" in error_text

    def test_get_nonexistent_task(self, calendar_client, formatter_client, orchestrator_client) -> None:
        """GET /tasks/<id> for unknown ID should return 404 on all agents."""
        for client in [calendar_client, formatter_client, orchestrator_client]:
            response = client.get("/tasks/does-not-exist")
            assert response.status_code == 404
            assert response.get_json()["error"]["code"] == "TaskNotFoundError"


# ---------------------------------------------------------------------------
# Test 6: Task history and message tracking
# ---------------------------------------------------------------------------


class TestTaskHistory:
    """Verify that Tasks maintain message history for auditability."""

    @patch("agents.calendar.server._get_agent")
    def test_task_records_incoming_message(self, mock_get_agent, calendar_client) -> None:
        """The Task's history should contain the original user message."""
        mock_agent = MagicMock()
        mock_agent.fetch_week_events.return_value = {
            "events": [], "conflicts": [], "total_events": 0, "busiest_day": "",
        }
        mock_get_agent.return_value = mock_agent

        msg = create_message(
            Role.USER,
            [data_part({
                "action": "fetch_week_events",
                "parameters": {
                    "start_date": "2025-02-17", "end_date": "2025-02-23",
                    "calendars": [{"calendar_id": "primary", "label": "You"}],
                },
            })],
        )
        original_message_id = msg["message_id"]
        req = create_send_message_request(msg)

        response = calendar_client.post("/message/send", json=req, content_type="application/json")
        task = response.get_json()["task"]

        # Task history should contain the original message
        assert len(task["history"]) >= 1
        assert task["history"][0]["message_id"] == original_message_id
        assert task["history"][0]["role"] == "user"


# ---------------------------------------------------------------------------
# Test 7: Multi-calendar data flow
# ---------------------------------------------------------------------------


class TestMultiCalendarFlow:
    """Test that multi-calendar data flows correctly through the A2A chain."""

    @patch("agents.calendar.server._get_agent")
    def test_multiple_calendars_in_response(self, mock_get_agent, calendar_client) -> None:
        """Calendar Agent should return events from multiple sources."""
        mock_agent = MagicMock()
        mock_agent.fetch_week_events.return_value = {
            "events": [
                {"day": "Monday", "date": "2025-02-17", "time": "9:00 AM",
                 "title": "My Meeting", "duration": "1 hour", "attendees": 3,
                 "location": "", "calendar_source": "You", "is_all_day": False},
                {"day": "Monday", "date": "2025-02-17", "time": "3:00 PM",
                 "title": "Partner Yoga", "duration": "1 hour", "attendees": 0,
                 "location": "Studio", "calendar_source": "Partner", "is_all_day": False},
            ],
            "conflicts": [],
            "total_events": 2,
            "busiest_day": "Monday",
        }
        mock_get_agent.return_value = mock_agent

        msg = create_message(
            Role.USER,
            [data_part({
                "action": "fetch_week_events",
                "parameters": {
                    "start_date": "2025-02-17",
                    "end_date": "2025-02-23",
                    "calendars": [
                        {"calendar_id": "primary", "label": "You"},
                        {"calendar_id": "partner@gmail.com", "label": "Partner"},
                    ],
                },
            })],
        )
        req = create_send_message_request(msg)

        response = calendar_client.post("/message/send", json=req, content_type="application/json")
        task = response.get_json()["task"]
        events = task["artifacts"][0]["parts"][0]["data"]["events"]

        sources = {e["calendar_source"] for e in events}
        assert "You" in sources
        assert "Partner" in sources


# ---------------------------------------------------------------------------
# Test 8: Orchestrator end-to-end (mocked downstream agents)
# ---------------------------------------------------------------------------


class TestOrchestratorEndToEnd:
    """Test the orchestrator's full workflow with mocked downstream A2A calls."""

    @patch("agents.orchestrator.server._get_agent")
    def test_orchestrator_sends_correct_a2a_structure(
        self, mock_get_agent, orchestrator_client
    ) -> None:
        """The orchestrator's SendMessage endpoint should return a proper Task."""
        mock_agent = MagicMock()
        mock_agent.generate_weekly_preview.return_value = {
            "summary": "# Weekly Preview\n\nContent here.",
            "file_path": "output/summaries/2025-02-17.md",
            "week_start": "2025-02-17",
            "week_end": "2025-02-23",
            "total_events": 5,
        }
        mock_get_agent.return_value = mock_agent

        msg = create_message(
            Role.USER,
            [data_part({
                "action": "generate_weekly_preview",
                "parameters": {"next_week": False},
            })],
        )
        req = create_send_message_request(msg)

        response = orchestrator_client.post("/message/send", json=req, content_type="application/json")
        assert response.status_code == 200

        task = response.get_json()["task"]
        assert task["status"]["state"] == "completed"

        # Verify artifact has both TextPart and DataPart
        parts = task["artifacts"][0]["parts"]
        types = [p["type"] for p in parts]
        assert "text" in types
        assert "data" in types

        # Verify metadata
        data_parts = [p for p in parts if p["type"] == "data"]
        assert data_parts[0]["data"]["total_events"] == 5
        assert data_parts[0]["data"]["week_start"] == "2025-02-17"
