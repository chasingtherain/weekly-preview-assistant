"""Google Calendar API wrapper.

Handles OAuth token loading, API client initialization, and event fetching.
This module isolates all Google-specific code so the agent logic stays clean.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def load_credentials(credentials_path: str, token_path: str) -> Credentials:
    """Load or refresh Google OAuth credentials.

    Args:
        credentials_path: Path to the OAuth client credentials JSON file.
        token_path: Path to the saved token JSON file.

    Returns:
        Valid Credentials object.

    Raises:
        FileNotFoundError: If the token file doesn't exist (user needs to run setup_calendar.py).
        ValueError: If the token is expired and can't be refreshed.
    """
    token_file = Path(token_path)
    if not token_file.exists():
        raise FileNotFoundError(
            f"Token file not found at {token_path}. "
            "Run 'python setup_calendar.py' to authenticate."
        )

    creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        logger.info("Refreshing expired token...")
        creds.refresh(Request())
        token_file.write_text(creds.to_json())
        logger.info("Token refreshed and saved.")
    elif not creds or not creds.valid:
        raise ValueError(
            "Token is invalid and cannot be refreshed. "
            "Run 'python setup_calendar.py' to re-authenticate."
        )

    return creds


def fetch_events(
    creds: Credentials,
    calendar_id: str,
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    """Fetch events from a Google Calendar for a date range.

    Args:
        creds: Valid Google OAuth credentials.
        calendar_id: Calendar ID (e.g. "primary" or "partner@gmail.com").
        start_date: Start date in YYYY-MM-DD format.
        end_date: End date in YYYY-MM-DD format.

    Returns:
        List of raw event dicts from the Google Calendar API.
    """
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    time_min = f"{start_date}T00:00:00Z"
    time_max = f"{end_date}T23:59:59Z"

    logger.info("Fetching events from calendar '%s' (%s to %s)", calendar_id, start_date, end_date)

    events_result = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    events = events_result.get("items", [])
    logger.info("Retrieved %d events from calendar '%s'", len(events), calendar_id)
    return events


def parse_event(raw_event: dict[str, Any], timezone: str) -> dict[str, Any]:
    """Parse a raw Google Calendar event into our simplified format.

    Args:
        raw_event: A raw event dict from the Google Calendar API.
        timezone: The user's timezone string (e.g. "America/Los_Angeles").

    Returns:
        A simplified event dict with the fields our system uses.
    """
    start = raw_event.get("start", {})
    end = raw_event.get("end", {})

    # All-day events use "date", timed events use "dateTime"
    is_all_day = "date" in start and "dateTime" not in start

    if is_all_day:
        start_str = start.get("date", "")
        date_obj = datetime.strptime(start_str, "%Y-%m-%d")
        time_str = "All day"
        duration = "All day"
    else:
        start_dt_str = start.get("dateTime", "")
        end_dt_str = end.get("dateTime", "")
        # Parse ISO datetime (e.g. "2025-02-17T09:00:00-08:00")
        start_dt = datetime.fromisoformat(start_dt_str)
        end_dt = datetime.fromisoformat(end_dt_str)
        date_obj = start_dt
        time_str = start_dt.strftime("%-I:%M %p")
        delta = end_dt - start_dt
        total_minutes = int(delta.total_seconds() / 60)
        if total_minutes >= 60:
            hours = total_minutes // 60
            mins = total_minutes % 60
            duration = f"{hours} hour{'s' if hours > 1 else ''}"
            if mins:
                duration += f" {mins} min"
        else:
            duration = f"{total_minutes} min"

    attendees = raw_event.get("attendees", [])

    return {
        "day": date_obj.strftime("%A"),
        "date": date_obj.strftime("%Y-%m-%d"),
        "time": time_str,
        "title": raw_event.get("summary", "(No title)"),
        "duration": duration,
        "attendees": len(attendees),
        "location": raw_event.get("location", ""),
        "is_all_day": is_all_day,
    }
