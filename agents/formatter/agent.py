"""Formatter Agent - Core logic.

Builds a deterministic weekly preview from structured calendar data.
Output uses a compact chat format optimised for messaging apps (Telegram,
WhatsApp): emoji dots per calendar source, one line per event, empty days
skipped, and single-asterisk bold for WhatsApp compatibility.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


class FormatterAgent:
    """Formats calendar data into a weekly preview deterministically."""

    def format_weekly_preview(
        self,
        events: list[dict[str, Any]],
        conflicts: list[dict[str, Any]],
        week_start: str,
        total_events: int,
        busiest_day: str,
    ) -> dict[str, Any]:
        """Generate a formatted weekly preview from calendar data.

        Args:
            events: List of event dicts from the calendar agent.
            conflicts: List of conflict dicts from the calendar agent.
            week_start: Start date of the week (YYYY-MM-DD, a Monday).
            total_events: Total number of events.
            busiest_day: Name of the busiest day.

        Returns:
            Result dict with "formatted_summary", "format", and "word_count".
        """
        summary = build_chat_format(events, conflicts, week_start)
        logger.info("Built chat format for week of %s (%d chars)", week_start, len(summary))

        word_count = len(summary.split())

        return {
            "formatted_summary": summary,
            "format": "chat",
            "word_count": word_count,
        }


SOURCE_EMOJIS = ["🔵", "🟢", "🟡", "🔴", "🟣", "🟠"]


def build_chat_format(
    events: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
    week_start: str,
) -> str:
    """Build a compact chat-friendly summary from calendar data.

    Designed for Telegram/WhatsApp: emoji dots per calendar source,
    one line per event, empty days skipped entirely, single-asterisk
    bold for WhatsApp compatibility.

    Args:
        events: List of event dicts.
        conflicts: List of conflict dicts.
        week_start: Start date (YYYY-MM-DD, a Monday).

    Returns:
        Compact chat-formatted string.
    """
    start = datetime.strptime(week_start, "%Y-%m-%d")
    end = start + timedelta(days=6)

    # Build source → emoji mapping
    sources = _get_calendar_sources(events)
    emoji_map = {src: SOURCE_EMOJIS[i % len(SOURCE_EMOJIS)] for i, src in enumerate(sources)}

    # Build conflict lookup
    conflict_lookup = _build_conflict_lookup(conflicts)

    # Week header
    start_day = start.day
    end_day = end.day
    month = start.strftime("%b")
    end_month = end.strftime("%b")
    if month == end_month:
        header = f"📅 *Week of {start_day}-{end_day} {month}*"
    else:
        header = f"📅 *Week of {start_day} {month} - {end_day} {end_month}*"

    lines = [header]

    # Generate each day
    for i in range(7):
        day_date = start + timedelta(days=i)
        date_str = day_date.strftime("%Y-%m-%d")
        day_events = [e for e in events if e.get("date") == date_str]

        if not day_events:
            continue

        day_header = day_date.strftime("%a %-d %b")
        lines.append("")
        lines.append(f"*{day_header}*")

        for ev in day_events:
            source = ev.get("calendar_source", "Unknown")
            emoji = emoji_map.get(source, "⚪")
            title = ev.get("title", "Untitled")
            time_str = _format_time_compact(ev.get("time", ""))
            duration = ev.get("duration", "")
            is_all_day = ev.get("all_day", False) or time_str == ""

            if is_all_day:
                time_part = "(all day)"
            elif _duration_minutes(duration) > 60:
                time_part = f"({time_str}, {_format_duration_compact(duration)})"
            else:
                time_part = f"({time_str})"

            line = f"{emoji} {source}: {title} {time_part}"

            # Conflict marker
            if conflict_lookup.get((date_str, title)):
                line += " ⚠️"

            lines.append(line)

    return "\n".join(lines)


def _format_time_compact(time_str: str) -> str:
    """Convert '9:00 AM' to '9am', '12:00 PM' to '12pm'.

    Args:
        time_str: Time string like '9:00 AM' or 'All day'.

    Returns:
        Compact time string, or empty string if unparseable.
    """
    if not time_str or time_str.lower() in ("all day", ""):
        return ""
    try:
        parsed = datetime.strptime(time_str.strip(), "%I:%M %p")
        hour = parsed.strftime("%-I")
        minute = parsed.strftime("%M")
        ampm = parsed.strftime("%p").lower()
        if minute == "00":
            return f"{hour}{ampm}"
        return f"{hour}:{minute}{ampm}"
    except ValueError:
        return time_str


def _duration_minutes(duration: str) -> int:
    """Parse a duration string into total minutes.

    Handles formats like '1 hour', '30 min', '2 hours', '1 hour 30 min',
    'All day'.

    Args:
        duration: Duration string from calendar agent.

    Returns:
        Total minutes, or 0 if unparseable.
    """
    if not duration or "all day" in duration.lower():
        return 0
    total = 0
    lower = duration.lower()
    parts = lower.replace(",", " ").split()
    i = 0
    while i < len(parts):
        try:
            num = int(parts[i])
            if i + 1 < len(parts):
                unit = parts[i + 1]
                if "hour" in unit:
                    total += num * 60
                elif "min" in unit:
                    total += num
                i += 2
            else:
                i += 1
        except ValueError:
            i += 1
    return total


def _format_duration_compact(duration: str) -> str:
    """Convert '2 hours' to '2hrs', '1 hour 30 min' to '1.5hrs'.

    Args:
        duration: Duration string.

    Returns:
        Compact duration string.
    """
    minutes = _duration_minutes(duration)
    if minutes <= 0:
        return duration
    hours = minutes / 60
    if hours == int(hours):
        return f"{int(hours)}hrs"
    return f"{hours:.1f}hrs".replace(".0hrs", "hrs")


def build_markdown(
    events: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
    week_start: str,
) -> str:
    """Build the final markdown summary from calendar data.

    Groups events by day and calendar source, adds inline conflict
    markers, and shows "NA" for empty source/day combinations.

    Args:
        events: List of event dicts.
        conflicts: List of conflict dicts.
        week_start: Start date (YYYY-MM-DD, a Monday).

    Returns:
        Complete markdown string ready to save to file.
    """
    # Parse week start and generate all 7 days
    start = datetime.strptime(week_start, "%Y-%m-%d")
    days = []
    for i in range(7):
        day_date = start + timedelta(days=i)
        days.append({
            "name": day_date.strftime("%A"),
            "date": day_date.strftime("%Y-%m-%d"),
            "display": day_date.strftime("%B %d").replace(" 0", " "),
        })

    # Collect all unique calendar sources
    sources = _get_calendar_sources(events)

    # Build conflict lookup: (date, title) → conflict description
    conflict_lookup = _build_conflict_lookup(conflicts)

    # Week header
    end = start + timedelta(days=6)
    week_start_display = start.strftime("%B %d").replace(" 0", " ")
    week_end_display = end.strftime("%B %d").replace(" 0", " ")
    year = start.strftime("%Y")

    lines = [
        f"## Week of {week_start_display} - {week_end_display}, {year}",
        "",
    ]

    # Group events by day
    for day in days:
        lines.append(f"### {day['name'].upper()}, {day['display'].upper()}")
        lines.append("")

        day_events = [e for e in events if e.get("date") == day["date"]]

        for source in sources:
            source_events = [
                e for e in day_events if e.get("calendar_source") == source
            ]
            possessive = "Your" if source == "You" else f"{source}'s"
            lines.append(f"**{possessive} events:**")
            if source_events:
                for ev in source_events:
                    line = f"* {ev['time']} - {ev['title']} ({ev['duration']})"
                    if ev.get("location"):
                        line += f" - {ev['location']}"
                    if ev.get("attendees", 0) > 0:
                        line += f" [{ev['attendees']} attendees]"
                    # Check for conflicts
                    conflict_msg = conflict_lookup.get(
                        (day["date"], ev["title"])
                    )
                    if conflict_msg:
                        line += f" ⚠️ CONFLICT: {conflict_msg}"
                    lines.append(line)
            else:
                lines.append("* NA")

            lines.append("")

    return "\n".join(lines)


def _get_calendar_sources(events: list[dict[str, Any]]) -> list[str]:
    """Extract unique calendar source labels, preserving order.

    Args:
        events: List of event dicts.

    Returns:
        Ordered list of unique source labels.
    """
    seen: set[str] = set()
    sources: list[str] = []
    for ev in events:
        source = ev.get("calendar_source", "Unknown")
        if source not in seen:
            seen.add(source)
            sources.append(source)
    # Default to at least "You" if no events
    return sources if sources else ["You"]


def _build_conflict_lookup(
    conflicts: list[dict[str, Any]],
) -> dict[tuple[str, str], str]:
    """Build a lookup from (date, event_title) to conflict description.

    Args:
        conflicts: List of conflict dicts from calendar agent. Each dict
            must include "date" (YYYY-MM-DD), "events", and "calendar_source".

    Returns:
        Dict mapping (YYYY-MM-DD date, title) to a conflict message string.
    """
    lookup: dict[tuple[str, str], str] = {}
    for conflict in conflicts:
        date_str = conflict.get("date", "")
        event_names = conflict.get("events", [])
        for name in event_names:
            other_names = [n for n in event_names if n != name]
            if other_names:
                lookup_key = (date_str, name)
                lookup[lookup_key] = f"Overlaps with {', '.join(other_names)}"
    return lookup
