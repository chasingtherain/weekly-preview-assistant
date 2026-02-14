"""Tests for Calendar Agent - core logic and HTTP server."""

import json
from unittest.mock import MagicMock, patch

import pytest

from a2a.protocol import Role, create_message, create_send_message_request, data_part, text_part
from agents.calendar.agent import (
    CalendarAgent,
    _detect_conflicts,
    _event_sort_key,
    _find_busiest_day,
    _parse_duration_minutes,
    _times_overlap,
)
from agents.calendar.google_client import parse_event


# ---------------------------------------------------------------------------
# google_client.py - parse_event tests
# ---------------------------------------------------------------------------


class TestParseEvent:
    def test_timed_event(self) -> None:
        raw = {
            "summary": "Team Standup",
            "start": {"dateTime": "2025-02-17T09:00:00-08:00"},
            "end": {"dateTime": "2025-02-17T09:30:00-08:00"},
            "attendees": [{"email": "a@a.com"}, {"email": "b@b.com"}],
            "location": "Zoom",
        }
        event = parse_event(raw, "America/Los_Angeles")
        assert event["title"] == "Team Standup"
        assert event["date"] == "2025-02-17"
        assert event["day"] == "Monday"
        assert event["time"] == "9:00 AM"
        assert event["duration"] == "30 min"
        assert event["attendees"] == 2
        assert event["location"] == "Zoom"
        assert event["is_all_day"] is False

    def test_all_day_event(self) -> None:
        raw = {
            "summary": "Holiday",
            "start": {"date": "2025-02-17"},
            "end": {"date": "2025-02-18"},
        }
        event = parse_event(raw, "America/Los_Angeles")
        assert event["time"] == "All day"
        assert event["duration"] == "All day"
        assert event["is_all_day"] is True

    def test_multi_hour_event(self) -> None:
        raw = {
            "summary": "Workshop",
            "start": {"dateTime": "2025-02-17T14:00:00-08:00"},
            "end": {"dateTime": "2025-02-17T16:30:00-08:00"},
        }
        event = parse_event(raw, "America/Los_Angeles")
        assert event["duration"] == "2 hours 30 min"

    def test_one_hour_event(self) -> None:
        raw = {
            "summary": "Meeting",
            "start": {"dateTime": "2025-02-17T10:00:00-08:00"},
            "end": {"dateTime": "2025-02-17T11:00:00-08:00"},
        }
        event = parse_event(raw, "America/Los_Angeles")
        assert event["duration"] == "1 hour"

    def test_no_title(self) -> None:
        raw = {
            "start": {"dateTime": "2025-02-17T10:00:00-08:00"},
            "end": {"dateTime": "2025-02-17T10:30:00-08:00"},
        }
        event = parse_event(raw, "America/Los_Angeles")
        assert event["title"] == "(No title)"


# ---------------------------------------------------------------------------
# agent.py - helper function tests
# ---------------------------------------------------------------------------


class TestParseDurationMinutes:
    def test_minutes_only(self) -> None:
        assert _parse_duration_minutes("30 min") == 30

    def test_hours_only(self) -> None:
        assert _parse_duration_minutes("2 hours") == 120

    def test_hours_and_minutes(self) -> None:
        assert _parse_duration_minutes("1 hour 30 min") == 90

    def test_unparseable_defaults_to_30(self) -> None:
        assert _parse_duration_minutes("All day") == 30


class TestTimesOverlap:
    def _make_event(self, time: str, duration: str) -> dict:
        return {"time": time, "duration": duration, "date": "2025-02-17"}

    def test_overlapping(self) -> None:
        ev1 = self._make_event("2:00 PM", "1 hour")
        ev2 = self._make_event("2:30 PM", "1 hour")
        assert _times_overlap(ev1, ev2) is True

    def test_not_overlapping(self) -> None:
        ev1 = self._make_event("9:00 AM", "30 min")
        ev2 = self._make_event("2:00 PM", "1 hour")
        assert _times_overlap(ev1, ev2) is False

    def test_adjacent_not_overlapping(self) -> None:
        ev1 = self._make_event("9:00 AM", "1 hour")
        ev2 = self._make_event("10:00 AM", "1 hour")
        assert _times_overlap(ev1, ev2) is False


class TestDetectConflicts:
    def test_same_calendar_overlap(self) -> None:
        events = [
            {"date": "2025-02-17", "day": "Monday", "time": "2:00 PM", "duration": "1 hour",
             "title": "Meeting A", "calendar_source": "You", "is_all_day": False},
            {"date": "2025-02-17", "day": "Monday", "time": "2:30 PM", "duration": "1 hour",
             "title": "Meeting B", "calendar_source": "You", "is_all_day": False},
        ]
        conflicts = _detect_conflicts(events)
        assert len(conflicts) == 1
        assert "Meeting A" in conflicts[0]["events"]
        assert "Meeting B" in conflicts[0]["events"]
        assert conflicts[0]["calendar_source"] == "You"

    def test_different_calendar_no_conflict(self) -> None:
        events = [
            {"date": "2025-02-17", "day": "Monday", "time": "2:00 PM", "duration": "1 hour",
             "title": "My Meeting", "calendar_source": "You", "is_all_day": False},
            {"date": "2025-02-17", "day": "Monday", "time": "2:00 PM", "duration": "1 hour",
             "title": "Partner Meeting", "calendar_source": "Partner", "is_all_day": False},
        ]
        conflicts = _detect_conflicts(events)
        assert len(conflicts) == 0

    def test_all_day_events_ignored(self) -> None:
        events = [
            {"date": "2025-02-17", "day": "Monday", "time": "All day", "duration": "All day",
             "title": "Holiday", "calendar_source": "You", "is_all_day": True},
            {"date": "2025-02-17", "day": "Monday", "time": "9:00 AM", "duration": "1 hour",
             "title": "Standup", "calendar_source": "You", "is_all_day": False},
        ]
        conflicts = _detect_conflicts(events)
        assert len(conflicts) == 0


class TestFindBusiestDay:
    def test_finds_busiest(self) -> None:
        events = [
            {"day": "Monday"}, {"day": "Monday"}, {"day": "Monday"},
            {"day": "Tuesday"}, {"day": "Tuesday"},
            {"day": "Wednesday"},
        ]
        assert _find_busiest_day(events) == "Monday"

    def test_empty_events(self) -> None:
        assert _find_busiest_day([]) == ""


class TestEventSortKey:
    def test_sort_order(self) -> None:
        events = [
            {"date": "2025-02-17", "time": "2:00 PM"},
            {"date": "2025-02-17", "time": "All day"},
            {"date": "2025-02-17", "time": "9:00 AM"},
            {"date": "2025-02-18", "time": "8:00 AM"},
        ]
        sorted_events = sorted(events, key=_event_sort_key)
        assert sorted_events[0]["time"] == "All day"
        assert sorted_events[1]["time"] == "9:00 AM"
        assert sorted_events[2]["time"] == "2:00 PM"
        assert sorted_events[3]["date"] == "2025-02-18"


# ---------------------------------------------------------------------------
# server.py - HTTP endpoint tests
# ---------------------------------------------------------------------------


class TestCalendarServer:
    @pytest.fixture
    def client(self):
        from agents.calendar.server import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

    def test_agent_card_endpoint(self, client) -> None:
        response = client.get("/.well-known/agent.json")
        assert response.status_code == 200
        card = response.get_json()
        assert card["name"] == "Calendar Agent"
        assert card["skills"][0]["id"] == "fetch_week_events"
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

    @patch("agents.calendar.server._get_agent")
    def test_send_message_success(self, mock_get_agent, client) -> None:
        # Mock the agent to return fake events
        mock_agent = MagicMock()
        mock_agent.fetch_week_events.return_value = {
            "events": [
                {"day": "Monday", "date": "2025-02-17", "time": "9:00 AM",
                 "title": "Standup", "duration": "30 min", "attendees": 5,
                 "location": "Zoom", "calendar_source": "You", "is_all_day": False},
            ],
            "conflicts": [],
            "total_events": 1,
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
                    ],
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
        assert task["artifacts"][0]["parts"][0]["data"]["total_events"] == 1

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
