"""Tests for Orchestrator Agent - core logic, date calculation, and HTTP server."""

import json
import os
from datetime import datetime
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
from agents.orchestrator.agent import (
    OrchestratorAgent,
    calculate_week_range,
    save_summary,
)


# ---------------------------------------------------------------------------
# calculate_week_range tests
# ---------------------------------------------------------------------------


class TestCalculateWeekRange:
    @patch("agents.orchestrator.agent.datetime")
    def test_current_week_from_wednesday(self, mock_dt) -> None:
        # Wednesday Feb 19, 2025
        mock_dt.now.return_value = datetime(2025, 2, 19)
        start, end = calculate_week_range(next_week=False)
        assert start == "2025-02-17"  # Monday
        assert end == "2025-02-23"    # Sunday

    @patch("agents.orchestrator.agent.datetime")
    def test_current_week_from_monday(self, mock_dt) -> None:
        # Monday Feb 17, 2025
        mock_dt.now.return_value = datetime(2025, 2, 17)
        start, end = calculate_week_range(next_week=False)
        assert start == "2025-02-17"
        assert end == "2025-02-23"

    @patch("agents.orchestrator.agent.datetime")
    def test_current_week_from_sunday(self, mock_dt) -> None:
        # Sunday Feb 23, 2025
        mock_dt.now.return_value = datetime(2025, 2, 23)
        start, end = calculate_week_range(next_week=False)
        assert start == "2025-02-17"
        assert end == "2025-02-23"

    @patch("agents.orchestrator.agent.datetime")
    def test_next_week(self, mock_dt) -> None:
        # Wednesday Feb 19, 2025 → next week
        mock_dt.now.return_value = datetime(2025, 2, 19)
        start, end = calculate_week_range(next_week=True)
        assert start == "2025-02-24"  # Next Monday
        assert end == "2025-03-02"    # Next Sunday


# ---------------------------------------------------------------------------
# save_summary tests
# ---------------------------------------------------------------------------


class TestSaveSummary:
    def test_creates_file(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        file_path = save_summary("# My Preview", "2025-02-17")
        assert os.path.exists(file_path)
        with open(file_path) as f:
            assert f.read() == "# My Preview"

    def test_creates_output_directory(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        save_summary("content", "2025-02-17")
        assert os.path.isdir(tmp_path / "output" / "summaries")

    def test_filename_includes_week_start_and_creation_timestamp(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        file_path = save_summary("content", "2025-03-10")
        # Filename: {week_start}_created-{YYYY-MM-DD-HHMMSS}.md
        filename = os.path.basename(file_path)
        assert filename.startswith("2025-03-10_created-")
        assert filename.endswith(".md")
        # Extract creation timestamp
        created_part = filename.replace("2025-03-10_created-", "").replace(".md", "")
        # Should be YYYY-MM-DD-HHMMSS (17 chars)
        assert len(created_part) == 17


# ---------------------------------------------------------------------------
# OrchestratorAgent tests
# ---------------------------------------------------------------------------


def _make_calendar_response(events, conflicts, total, busiest_day):
    """Helper to build a mock Calendar Agent A2A response."""
    task = create_task(state=TaskState.COMPLETED)
    task["artifacts"] = [
        create_artifact(parts=[data_part({
            "events": events,
            "conflicts": conflicts,
            "total_events": total,
            "busiest_day": busiest_day,
        })])
    ]
    task["status"] = create_task_status(TaskState.COMPLETED)
    return {"task": task}


def _make_formatter_response(summary, word_count):
    """Helper to build a mock Formatter Agent A2A response."""
    task = create_task(state=TaskState.COMPLETED)
    task["artifacts"] = [
        create_artifact(parts=[
            text_part(summary),
            data_part({"format": "markdown", "word_count": word_count}),
        ])
    ]
    task["status"] = create_task_status(TaskState.COMPLETED)
    return {"task": task}


def _make_failed_response(error_msg):
    """Helper to build a mock failed A2A response."""
    task = create_task(state=TaskState.FAILED)
    task["status"] = create_task_status(
        TaskState.FAILED,
        message=create_message(Role.AGENT, [text_part(error_msg)]),
    )
    return {"task": task}


class TestOrchestratorAgent:
    def _make_agent(self) -> OrchestratorAgent:
        return OrchestratorAgent(
            calendar_url="http://localhost:5001",
            formatter_url="http://localhost:5002",
            calendars=[{"calendar_id": "primary", "label": "You"}],
            timezone="America/Los_Angeles",
        )

    @patch("agents.orchestrator.agent.discover_agents")
    def test_discover_returns_skill_map(self, mock_discover) -> None:
        mock_discover.return_value = [
            {
                "name": "Calendar Agent",
                "skills": [{"id": "fetch_week_events", "name": "Fetch"}],
                "supported_interfaces": [{"url": "http://localhost:5001"}],
            },
            {
                "name": "Formatter Agent",
                "skills": [{"id": "format_weekly_preview", "name": "Format"}],
                "supported_interfaces": [{"url": "http://localhost:5002"}],
            },
        ]
        agent = self._make_agent()
        skill_map = agent.discover()

        assert "fetch_week_events" in skill_map
        assert "format_weekly_preview" in skill_map

    @patch("agents.orchestrator.agent.send_message")
    @patch("agents.orchestrator.agent.discover_agents")
    @patch("agents.orchestrator.agent.calculate_week_range")
    def test_generate_weekly_preview_success(
        self, mock_range, mock_discover, mock_send, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        mock_range.return_value = ("2025-02-17", "2025-02-23")

        mock_discover.return_value = [
            {
                "name": "Calendar Agent",
                "skills": [{"id": "fetch_week_events"}],
                "supported_interfaces": [{"url": "http://localhost:5001"}],
            },
            {
                "name": "Formatter Agent",
                "skills": [{"id": "format_weekly_preview"}],
                "supported_interfaces": [{"url": "http://localhost:5002"}],
            },
        ]

        events = [
            {"day": "Monday", "date": "2025-02-17", "time": "9:00 AM",
             "title": "Standup", "duration": "30 min", "attendees": 5,
             "location": "Zoom", "calendar_source": "You", "is_all_day": False},
        ]

        # First call = Calendar Agent, Second call = Formatter Agent
        mock_send.side_effect = [
            _make_calendar_response(events, [], 1, "Monday"),
            _make_formatter_response("# WEEK OF FEB 17-23\n\nPreview content.", 5),
        ]

        agent = self._make_agent()
        result = agent.generate_weekly_preview(next_week=False)

        assert "error" not in result
        assert result["total_events"] == 1
        assert result["week_start"] == "2025-02-17"
        assert result["week_end"] == "2025-02-23"
        assert result["telegram_sent"] is False
        assert os.path.exists(result["file_path"])
        assert mock_send.call_count == 2

    @patch("agents.orchestrator.agent.discover_agents")
    def test_missing_calendar_agent(self, mock_discover) -> None:
        mock_discover.return_value = [
            {
                "name": "Formatter Agent",
                "skills": [{"id": "format_weekly_preview"}],
                "supported_interfaces": [{"url": "http://localhost:5002"}],
            },
        ]
        agent = self._make_agent()
        result = agent.generate_weekly_preview()
        assert "error" in result
        assert "Calendar Agent" in result["error"]

    @patch("agents.orchestrator.agent.discover_agents")
    def test_missing_formatter_agent(self, mock_discover) -> None:
        mock_discover.return_value = [
            {
                "name": "Calendar Agent",
                "skills": [{"id": "fetch_week_events"}],
                "supported_interfaces": [{"url": "http://localhost:5001"}],
            },
        ]
        agent = self._make_agent()
        result = agent.generate_weekly_preview()
        assert "error" in result
        assert "Formatter Agent" in result["error"]

    @patch("agents.orchestrator.agent.send_message")
    @patch("agents.orchestrator.agent.discover_agents")
    def test_calendar_agent_failure(self, mock_discover, mock_send) -> None:
        mock_discover.return_value = [
            {"name": "Cal", "skills": [{"id": "fetch_week_events"}],
             "supported_interfaces": [{"url": "http://localhost:5001"}]},
            {"name": "Fmt", "skills": [{"id": "format_weekly_preview"}],
             "supported_interfaces": [{"url": "http://localhost:5002"}]},
        ]
        mock_send.return_value = {"error": {"code": "TimeoutError", "message": "Timeout"}}

        agent = self._make_agent()
        result = agent.generate_weekly_preview()
        assert "error" in result
        assert "Calendar Agent" in result["error"]

    @patch("agents.orchestrator.agent.send_message")
    @patch("agents.orchestrator.agent.discover_agents")
    def test_calendar_agent_task_failed(self, mock_discover, mock_send) -> None:
        mock_discover.return_value = [
            {"name": "Cal", "skills": [{"id": "fetch_week_events"}],
             "supported_interfaces": [{"url": "http://localhost:5001"}]},
            {"name": "Fmt", "skills": [{"id": "format_weekly_preview"}],
             "supported_interfaces": [{"url": "http://localhost:5002"}]},
        ]
        mock_send.return_value = _make_failed_response("Token expired")

        agent = self._make_agent()
        result = agent.generate_weekly_preview()
        assert "error" in result
        assert "failed" in result["error"]

    @patch("agents.orchestrator.agent.send_message")
    @patch("agents.orchestrator.agent.discover_agents")
    def test_formatter_agent_failure(self, mock_discover, mock_send) -> None:
        mock_discover.return_value = [
            {"name": "Cal", "skills": [{"id": "fetch_week_events"}],
             "supported_interfaces": [{"url": "http://localhost:5001"}]},
            {"name": "Fmt", "skills": [{"id": "format_weekly_preview"}],
             "supported_interfaces": [{"url": "http://localhost:5002"}]},
        ]
        # Calendar succeeds, Formatter fails
        mock_send.side_effect = [
            _make_calendar_response([], [], 0, ""),
            {"error": {"code": "TimeoutError", "message": "Timeout"}},
        ]

        agent = self._make_agent()
        result = agent.generate_weekly_preview()
        assert "error" in result
        assert "Formatter Agent" in result["error"]

    @patch("agents.orchestrator.agent.send_message")
    @patch("agents.orchestrator.agent.discover_agents")
    @patch("agents.orchestrator.agent.calculate_week_range")
    def test_generate_with_telegram(
        self, mock_range, mock_discover, mock_send, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        mock_range.return_value = ("2025-02-17", "2025-02-23")

        mock_discover.return_value = [
            {"name": "Cal", "skills": [{"id": "fetch_week_events"}],
             "supported_interfaces": [{"url": "http://localhost:5001"}]},
            {"name": "Fmt", "skills": [{"id": "format_weekly_preview"}],
             "supported_interfaces": [{"url": "http://localhost:5002"}]},
            {"name": "Telegram", "skills": [{"id": "send_telegram_message"}],
             "supported_interfaces": [{"url": "http://localhost:5003"}]},
        ]

        telegram_response = create_task(state=TaskState.COMPLETED)
        telegram_response["artifacts"] = [
            create_artifact(parts=[data_part({"message_id": 123, "chat_id": "456"})])
        ]
        telegram_response["status"] = create_task_status(TaskState.COMPLETED)

        mock_send.side_effect = [
            _make_calendar_response([], [], 0, ""),
            _make_formatter_response("Preview text", 2),
            {"task": telegram_response},
        ]

        agent = OrchestratorAgent(
            calendar_url="http://localhost:5001",
            formatter_url="http://localhost:5002",
            calendars=[{"calendar_id": "primary", "label": "You"}],
            timezone="America/Los_Angeles",
            telegram_url="http://localhost:5003",
        )
        result = agent.generate_weekly_preview()

        assert "error" not in result
        assert result["telegram_sent"] is True
        assert mock_send.call_count == 3

    @patch("agents.orchestrator.agent.send_message")
    @patch("agents.orchestrator.agent.discover_agents")
    @patch("agents.orchestrator.agent.calculate_week_range")
    def test_telegram_failure_does_not_block_workflow(
        self, mock_range, mock_discover, mock_send, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        mock_range.return_value = ("2025-02-17", "2025-02-23")

        mock_discover.return_value = [
            {"name": "Cal", "skills": [{"id": "fetch_week_events"}],
             "supported_interfaces": [{"url": "http://localhost:5001"}]},
            {"name": "Fmt", "skills": [{"id": "format_weekly_preview"}],
             "supported_interfaces": [{"url": "http://localhost:5002"}]},
            {"name": "Telegram", "skills": [{"id": "send_telegram_message"}],
             "supported_interfaces": [{"url": "http://localhost:5003"}]},
        ]

        mock_send.side_effect = [
            _make_calendar_response([], [], 0, ""),
            _make_formatter_response("Preview text", 2),
            {"error": {"code": "TimeoutError", "message": "Timeout"}},
        ]

        agent = OrchestratorAgent(
            calendar_url="http://localhost:5001",
            formatter_url="http://localhost:5002",
            calendars=[{"calendar_id": "primary", "label": "You"}],
            timezone="America/Los_Angeles",
            telegram_url="http://localhost:5003",
        )
        result = agent.generate_weekly_preview()

        assert "error" not in result
        assert result["telegram_sent"] is False
        assert os.path.exists(result["file_path"])


# ---------------------------------------------------------------------------
# server.py - HTTP endpoint tests
# ---------------------------------------------------------------------------


class TestOrchestratorServer:
    @pytest.fixture
    def client(self):
        from agents.orchestrator.server import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

    def test_agent_card_endpoint(self, client) -> None:
        response = client.get("/.well-known/agent.json")
        assert response.status_code == 200
        card = response.get_json()
        assert card["name"] == "Orchestrator Agent"
        assert card["skills"][0]["id"] == "generate_weekly_preview"

    def test_get_task_not_found(self, client) -> None:
        response = client.get("/tasks/nonexistent-id")
        assert response.status_code == 404

    def test_send_message_invalid_request(self, client) -> None:
        response = client.post(
            "/message/send",
            json={"message": {"role": "user"}},
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_send_message_no_params(self, client) -> None:
        msg = create_message(Role.USER, [text_part("just text")])
        req = create_send_message_request(msg)

        response = client.post("/message/send", json=req, content_type="application/json")
        assert response.status_code == 200
        assert response.get_json()["task"]["status"]["state"] == "failed"

    @patch("agents.orchestrator.server._get_agent")
    def test_send_message_success(self, mock_get_agent, client, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        mock_agent = MagicMock()
        mock_agent.generate_weekly_preview.return_value = {
            "summary": "# Preview\nContent",
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

        response = client.post("/message/send", json=req, content_type="application/json")
        assert response.status_code == 200

        data = response.get_json()
        task = data["task"]
        assert task["status"]["state"] == "completed"
        assert len(task["artifacts"]) == 1

    @patch("agents.orchestrator.server._get_agent")
    def test_send_message_workflow_error(self, mock_get_agent, client) -> None:
        mock_agent = MagicMock()
        mock_agent.generate_weekly_preview.return_value = {
            "error": "Calendar Agent not available",
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

        response = client.post("/message/send", json=req, content_type="application/json")
        assert response.status_code == 200
        assert response.get_json()["task"]["status"]["state"] == "failed"
