"""Formatter Agent - Core logic.

Builds an LLM prompt from structured calendar data and uses Ollama to
generate a human-friendly weekly preview. The prompt enforces the output
format defined in the PRD: events grouped by calendar source per day,
"NA" for empty days, bullet points, and inline conflict markers.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from agents.formatter.ollama_client import generate

logger = logging.getLogger(__name__)


class FormatterAgent:
    """Formats calendar data into a weekly preview using a local LLM."""

    def __init__(self, ollama_host: str, ollama_model: str) -> None:
        """Initialize the FormatterAgent.

        Args:
            ollama_host: Ollama server URL (e.g. "http://localhost:11434").
            ollama_model: Model name (e.g. "llama3").
        """
        self.ollama_host = ollama_host
        self.ollama_model = ollama_model

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
        prompt = build_prompt(events, conflicts, week_start, total_events, busiest_day)
        logger.info("Built prompt for week of %s (%d chars)", week_start, len(prompt))

        summary = generate(
            prompt=prompt,
            model=self.ollama_model,
            host=self.ollama_host,
        )

        word_count = len(summary.split())

        return {
            "formatted_summary": summary,
            "format": "markdown",
            "word_count": word_count,
        }


def build_prompt(
    events: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
    week_start: str,
    total_events: int,
    busiest_day: str,
) -> str:
    """Build the LLM prompt from calendar data.

    Structures the data into a clear format so the LLM can produce
    the weekly preview matching the PRD output spec.

    Args:
        events: List of event dicts.
        conflicts: List of conflict dicts.
        week_start: Start date (YYYY-MM-DD, a Monday).
        total_events: Total number of events.
        busiest_day: Name of the busiest day.

    Returns:
        The complete prompt string.
    """
    # Build the structured data section
    data_section = _build_data_section(events, conflicts, week_start, total_events, busiest_day)

    prompt = f"""You are a personal assistant that creates weekly calendar previews.

Given the calendar data below, generate a well-formatted markdown summary following this EXACT structure:

1. **WEEK AT A GLANCE** — Total events, busiest day, light days
2. **DAY BY DAY** — Each day Monday through Sunday with:
   - Events grouped under **My events:** and **Partner's events:** (or whatever the calendar source labels are)
   - If a calendar has no events for that day, show "* NA"
   - Each event as a bullet: "* TIME - TITLE (DURATION)" with optional location
   - Inline conflict markers: "⚠️ CONFLICT: Overlaps with EVENT_NAME"
   - Busy day markers in the day heading: "⚠️ BUSY DAY"
3. **INSIGHTS** — 3-5 actionable observations about the week
4. **CONFLICTS** — List all scheduling conflicts (if any)

IMPORTANT RULES:
- Use the exact calendar source labels from the data (e.g., "You", "Partner")
- Show EVERY day Monday through Sunday, even if both calendars have no events
- Group events by calendar source within each day
- Mark conflicts inline next to the conflicting events
- Keep the tone friendly and helpful
- Do NOT invent or add events that aren't in the data

{data_section}

Generate the weekly preview now:"""

    return prompt


def _build_data_section(
    events: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
    week_start: str,
    total_events: int,
    busiest_day: str,
) -> str:
    """Build the structured data section of the prompt.

    Groups events by day and calendar source so the LLM can easily
    parse them.

    Args:
        events: List of event dicts.
        conflicts: List of conflict dicts.
        week_start: Start date (YYYY-MM-DD).
        total_events: Total number of events.
        busiest_day: Name of the busiest day.

    Returns:
        Formatted data string.
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

    # Format week end date
    end = start + timedelta(days=6)
    week_end_display = end.strftime("%B %d").replace(" 0", " ")
    week_start_display = start.strftime("%B %d").replace(" 0", " ")
    year = start.strftime("%Y")

    lines = [
        "--- CALENDAR DATA ---",
        f"Week: {week_start_display} - {week_end_display}, {year}",
        f"Total events: {total_events}",
        f"Busiest day: {busiest_day}",
        "",
    ]

    # Group events by day
    for day in days:
        lines.append(f"### {day['name'].upper()}, {day['display'].upper()}")

        day_events = [e for e in events if e.get("date") == day["date"]]

        for source in sources:
            source_events = [e for e in day_events if e.get("calendar_source") == source]
            possessive = "Your" if source == "You" else f"{source}'s"
            lines.append(f"  {possessive} events:")
            if source_events:
                for ev in source_events:
                    line = f"    - {ev['time']} - {ev['title']} ({ev['duration']})"
                    if ev.get("location"):
                        line += f" - {ev['location']}"
                    if ev.get("attendees", 0) > 0:
                        line += f" [{ev['attendees']} attendees]"
                    # Check for conflicts
                    conflict_msg = conflict_lookup.get((day["date"], ev["title"]))
                    if conflict_msg:
                        line += f" ⚠️ CONFLICT: {conflict_msg}"
                    lines.append(line)
            else:
                lines.append("    - NA")

        lines.append("")

    # Add conflicts section
    if conflicts:
        lines.append("--- CONFLICTS ---")
        for c in conflicts:
            event_names = " & ".join(c["events"])
            lines.append(f"  - {c['time']}: {event_names} ({c['calendar_source']})")
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
