"""Calendar Agent - Core logic.

Fetches events from multiple Google Calendars, tags each event with its
calendar source label, merges them chronologically, and detects scheduling
conflicts (overlapping time blocks within the same calendar).
"""

import logging
from datetime import datetime
from typing import Any

from agents.calendar.google_client import fetch_events, load_credentials, parse_event

logger = logging.getLogger(__name__)


class CalendarAgent:
    """Handles calendar event fetching and conflict detection."""

    def __init__(self, credentials_path: str, token_path: str, timezone: str) -> None:
        """Initialize the CalendarAgent.

        Args:
            credentials_path: Path to Google OAuth credentials.json.
            token_path: Path to saved OAuth token.json.
            timezone: User's IANA timezone string.
        """
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.timezone = timezone

    def fetch_week_events(
        self,
        start_date: str,
        end_date: str,
        calendars: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Fetch and merge events from multiple calendars.

        Args:
            start_date: Start date in YYYY-MM-DD format.
            end_date: End date in YYYY-MM-DD format.
            calendars: List of dicts with "calendar_id" and "label" keys.

        Returns:
            Result dict with "events", "conflicts", "total_events", and "busiest_day".
        """
        creds = load_credentials(self.credentials_path, self.token_path)

        all_events: list[dict[str, Any]] = []

        for cal in calendars:
            cal_id = cal["calendar_id"]
            label = cal["label"]
            try:
                raw_events = fetch_events(creds, cal_id, start_date, end_date)
                for raw in raw_events:
                    parsed = parse_event(raw, self.timezone)
                    parsed["calendar_source"] = label
                    all_events.append(parsed)
            except Exception as e:
                logger.error("Failed to fetch from calendar '%s' (%s): %s", label, cal_id, e)

        # Sort chronologically
        all_events.sort(key=_event_sort_key)

        # Detect conflicts within same calendar
        conflicts = _detect_conflicts(all_events)

        # Find busiest day
        busiest_day = _find_busiest_day(all_events)

        return {
            "events": all_events,
            "conflicts": conflicts,
            "total_events": len(all_events),
            "busiest_day": busiest_day,
        }


def _event_sort_key(event: dict[str, Any]) -> tuple[str, str]:
    """Sort key: date first, then time (all-day events first)."""
    time = event.get("time", "")
    if time == "All day":
        time_key = "00:00"
    else:
        try:
            time_key = datetime.strptime(time, "%I:%M %p").strftime("%H:%M")
        except ValueError:
            time_key = "99:99"
    return (event.get("date", ""), time_key)


def _detect_conflicts(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect overlapping time blocks within the same calendar.

    Only checks timed events (not all-day). Two events conflict if they
    are on the same date, from the same calendar, and their time blocks overlap.

    Args:
        events: Sorted list of event dicts.

    Returns:
        List of conflict dicts with "time", "events", and "calendar_source".
    """
    conflicts: list[dict[str, Any]] = []
    timed = [e for e in events if not e.get("is_all_day", False)]

    for i, ev1 in enumerate(timed):
        for ev2 in timed[i + 1 :]:
            if ev1["date"] != ev2["date"]:
                break
            if ev1["calendar_source"] != ev2["calendar_source"]:
                continue
            if _times_overlap(ev1, ev2):
                conflict_desc = {
                    "time": f"{ev1['day']} {ev1['time']}",
                    "events": [ev1["title"], ev2["title"]],
                    "calendar_source": ev1["calendar_source"],
                }
                conflicts.append(conflict_desc)

    return conflicts


def _times_overlap(ev1: dict[str, Any], ev2: dict[str, Any]) -> bool:
    """Check if two timed events on the same date overlap.

    Uses start time + duration to determine end time, then checks overlap.
    """
    try:
        start1 = datetime.strptime(ev1["time"], "%I:%M %p")
        start2 = datetime.strptime(ev2["time"], "%I:%M %p")
    except ValueError:
        return False

    dur1_mins = _parse_duration_minutes(ev1["duration"])
    dur2_mins = _parse_duration_minutes(ev2["duration"])

    from datetime import timedelta

    end1 = start1 + timedelta(minutes=dur1_mins)
    end2 = start2 + timedelta(minutes=dur2_mins)

    return start1 < end2 and start2 < end1


def _parse_duration_minutes(duration: str) -> int:
    """Parse a duration string like '1 hour 30 min' into minutes."""
    minutes = 0
    parts = duration.lower().split()
    i = 0
    while i < len(parts):
        try:
            num = int(parts[i])
            if i + 1 < len(parts):
                unit = parts[i + 1]
                if "hour" in unit:
                    minutes += num * 60
                elif "min" in unit:
                    minutes += num
                i += 2
            else:
                minutes += num
                i += 1
        except ValueError:
            i += 1
    return minutes if minutes > 0 else 30  # Default to 30 min if unparseable


def _find_busiest_day(events: list[dict[str, Any]]) -> str:
    """Find the day with the most events.

    Args:
        events: List of event dicts.

    Returns:
        Day name (e.g. "Tuesday") or empty string if no events.
    """
    if not events:
        return ""
    day_counts: dict[str, int] = {}
    for event in events:
        day = event.get("day", "")
        day_counts[day] = day_counts.get(day, 0) + 1
    return max(day_counts, key=day_counts.get)
