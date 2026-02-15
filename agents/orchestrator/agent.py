"""Orchestrator Agent - Core logic.

Coordinates the weekly preview workflow by discovering agents via their
Agent Cards, sending A2A messages to the Calendar Agent and Formatter Agent,
and saving the final output.

A2A Concept: The orchestrator is an A2A *client* — it discovers agents,
sends SendMessageRequests, and reads Task results. It does NOT call agent
functions directly; all communication goes through A2A messages over HTTP.
"""

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from a2a.client import send_message
from a2a.discovery import discover_agents, find_agent_by_skill, get_agent_url
from a2a.protocol import Role, create_message, create_send_message_request, data_part

logger = logging.getLogger(__name__)

AGENT_ID = "orchestrator-main"


class OrchestratorAgent:
    """Coordinates the weekly preview workflow via A2A protocol."""

    def __init__(
        self,
        calendar_url: str,
        formatter_url: str,
        calendars: list[dict[str, str]],
        timezone: str,
        telegram_url: str = "",
    ) -> None:
        """Initialize the OrchestratorAgent.

        Args:
            calendar_url: Base URL of the Calendar Agent.
            formatter_url: Base URL of the Formatter Agent.
            calendars: List of calendar configs with "calendar_id" and "label".
            timezone: User's IANA timezone string.
            telegram_url: Base URL of the Telegram Agent (optional).
        """
        self.calendar_url = calendar_url
        self.formatter_url = formatter_url
        self.telegram_url = telegram_url
        self.calendars = calendars
        self.timezone = timezone

    def discover(self) -> dict[str, dict[str, Any]]:
        """Discover available agents via Agent Card endpoints.

        A2A Concept: The orchestrator fetches Agent Cards from known URLs
        to verify agents are running and confirm their capabilities.

        Returns:
            Dict mapping skill IDs to their Agent Cards.
        """
        urls = [self.calendar_url, self.formatter_url]
        if self.telegram_url:
            urls.append(self.telegram_url)
        cards = discover_agents(urls)
        logger.info("Discovered %d agent(s)", len(cards))

        skill_map: dict[str, dict[str, Any]] = {}
        for card in cards:
            for skill in card.get("skills", []):
                skill_map[skill["id"]] = card

        return skill_map

    def generate_weekly_preview(self, next_week: bool = False) -> dict[str, Any]:
        """Run the full weekly preview workflow.

        Steps:
        1. Calculate date range (current or next week, Monday-Sunday)
        2. Discover agents
        3. Send A2A message to Calendar Agent → get events
        4. Send A2A message to Formatter Agent → get formatted summary
        5. Send via Telegram (if available, non-blocking on failure)
        6. Save summary to file

        Args:
            next_week: If True, generate for the following week.

        Returns:
            Result dict with "summary", "file_path", "week_start", "week_end",
            "total_events", and "telegram_sent". Contains "error" key on failure.
        """
        # Step 1: Calculate date range
        start_date, end_date = calculate_week_range(next_week)
        logger.info("Generating preview for %s to %s", start_date, end_date)

        # Step 2: Discover agents
        skill_map = self.discover()

        if "fetch_week_events" not in skill_map:
            return {"error": "Calendar Agent not available (fetch_week_events skill not found)"}
        if "format_weekly_preview" not in skill_map:
            return {"error": "Formatter Agent not available (format_weekly_preview skill not found)"}

        # Step 3: Fetch calendar events via A2A
        calendar_result = self._fetch_calendar_events(start_date, end_date)
        if "error" in calendar_result:
            return calendar_result

        events = calendar_result["events"]
        conflicts = calendar_result["conflicts"]
        total_events = calendar_result["total_events"]
        busiest_day = calendar_result["busiest_day"]

        logger.info("Retrieved %d events, %d conflicts", total_events, len(conflicts))

        # Step 4: Format via A2A
        format_result = self._format_preview(
            events=events,
            conflicts=conflicts,
            week_start=start_date,
            total_events=total_events,
            busiest_day=busiest_day,
        )
        if "error" in format_result:
            return format_result

        summary = format_result["formatted_summary"]

        # Step 5: Send via Telegram (optional, non-blocking on failure)
        telegram_sent = False
        if "send_telegram_message" in skill_map:
            telegram_result = self._send_telegram(summary)
            telegram_sent = "error" not in telegram_result
            if not telegram_sent:
                logger.warning("Telegram delivery failed: %s", telegram_result.get("error"))
        else:
            logger.info("Telegram Agent not discovered, skipping delivery")

        # Step 6: Save to file
        file_path = save_summary(summary, start_date)
        logger.info("Summary saved to %s", file_path)

        return {
            "summary": summary,
            "file_path": file_path,
            "week_start": start_date,
            "week_end": end_date,
            "total_events": total_events,
            "telegram_sent": telegram_sent,
        }

    def _fetch_calendar_events(
        self, start_date: str, end_date: str
    ) -> dict[str, Any]:
        """Send A2A message to Calendar Agent to fetch events.

        Args:
            start_date: Start date (YYYY-MM-DD).
            end_date: End date (YYYY-MM-DD).

        Returns:
            Calendar result dict, or error dict on failure.
        """
        msg = create_message(
            Role.USER,
            [data_part({
                "action": "fetch_week_events",
                "parameters": {
                    "start_date": start_date,
                    "end_date": end_date,
                    "calendars": self.calendars,
                },
            })],
        )
        req = create_send_message_request(msg)

        logger.info("Sending fetch_week_events to Calendar Agent at %s", self.calendar_url)
        response = send_message(
            agent_url=self.calendar_url,
            request=req,
            timeout=15,
            caller=AGENT_ID,
        )

        if "error" in response:
            logger.error("Calendar Agent error: %s", response["error"])
            return {"error": f"Calendar Agent failed: {response['error'].get('message', 'unknown')}"}

        task = response.get("task", {})
        state = task.get("status", {}).get("state")

        if state != "completed":
            error_msg = task.get("status", {}).get("message", {}).get("parts", [{}])
            msg_text = error_msg[0].get("text", "unknown error") if error_msg else "unknown error"
            return {"error": f"Calendar Agent task {state}: {msg_text}"}

        # Extract result from artifact's DataPart
        artifacts = task.get("artifacts", [])
        if not artifacts:
            return {"error": "Calendar Agent returned no artifacts"}

        for part in artifacts[0].get("parts", []):
            if part.get("type") == "data":
                return part["data"]

        return {"error": "Calendar Agent artifact has no DataPart"}

    def _format_preview(
        self,
        events: list[dict[str, Any]],
        conflicts: list[dict[str, Any]],
        week_start: str,
        total_events: int,
        busiest_day: str,
    ) -> dict[str, Any]:
        """Send A2A message to Formatter Agent to generate the preview.

        Args:
            events: List of event dicts from calendar agent.
            conflicts: List of conflict dicts.
            week_start: Start date (YYYY-MM-DD).
            total_events: Total event count.
            busiest_day: Name of busiest day.

        Returns:
            Format result dict with "formatted_summary", or error dict.
        """
        msg = create_message(
            Role.USER,
            [data_part({
                "action": "format_weekly_preview",
                "parameters": {
                    "events": events,
                    "conflicts": conflicts,
                    "week_start": week_start,
                    "total_events": total_events,
                    "busiest_day": busiest_day,
                },
            })],
        )
        req = create_send_message_request(msg)

        logger.info("Sending format_weekly_preview to Formatter Agent at %s", self.formatter_url)
        response = send_message(
            agent_url=self.formatter_url,
            request=req,
            timeout=30,
            caller=AGENT_ID,
        )

        if "error" in response:
            logger.error("Formatter Agent error: %s", response["error"])
            return {"error": f"Formatter Agent failed: {response['error'].get('message', 'unknown')}"}

        task = response.get("task", {})
        state = task.get("status", {}).get("state")

        if state != "completed":
            error_msg = task.get("status", {}).get("message", {}).get("parts", [{}])
            msg_text = error_msg[0].get("text", "unknown error") if error_msg else "unknown error"
            return {"error": f"Formatter Agent task {state}: {msg_text}"}

        # Extract summary from artifact's TextPart
        artifacts = task.get("artifacts", [])
        if not artifacts:
            return {"error": "Formatter Agent returned no artifacts"}

        result: dict[str, Any] = {}
        for part in artifacts[0].get("parts", []):
            if part.get("type") == "text":
                result["formatted_summary"] = part["text"]
            elif part.get("type") == "data":
                result.update(part["data"])

        if "formatted_summary" not in result:
            return {"error": "Formatter Agent artifact has no TextPart"}

        return result

    def _send_telegram(self, text: str) -> dict[str, Any]:
        """Send A2A message to Telegram Agent to deliver the summary.

        Args:
            text: The formatted summary text to send.

        Returns:
            Delivery result dict, or error dict on failure.
        """
        msg = create_message(
            Role.USER,
            [data_part({
                "action": "send_telegram_message",
                "parameters": {"text": text},
            })],
        )
        req = create_send_message_request(msg)

        logger.info("Sending send_telegram_message to Telegram Agent at %s", self.telegram_url)
        response = send_message(
            agent_url=self.telegram_url,
            request=req,
            timeout=15,
            caller=AGENT_ID,
        )

        if "error" in response:
            logger.error("Telegram Agent error: %s", response["error"])
            return {"error": f"Telegram Agent failed: {response['error'].get('message', 'unknown')}"}

        task = response.get("task", {})
        state = task.get("status", {}).get("state")

        if state != "completed":
            error_msg = task.get("status", {}).get("message", {}).get("parts", [{}])
            msg_text = error_msg[0].get("text", "unknown error") if error_msg else "unknown error"
            return {"error": f"Telegram Agent task {state}: {msg_text}"}

        # Extract result from artifact's DataPart
        artifacts = task.get("artifacts", [])
        if not artifacts:
            return {"error": "Telegram Agent returned no artifacts"}

        for part in artifacts[0].get("parts", []):
            if part.get("type") == "data":
                return part["data"]

        return {"error": "Telegram Agent artifact has no DataPart"}


def calculate_week_range(next_week: bool = False) -> tuple[str, str]:
    """Calculate the Monday-Sunday date range for the target week.

    Args:
        next_week: If True, return next week's range instead of current.

    Returns:
        Tuple of (start_date, end_date) in YYYY-MM-DD format.
    """
    today = datetime.now()
    # Monday is weekday 0
    monday = today - timedelta(days=today.weekday())

    if next_week:
        monday = monday + timedelta(weeks=1)

    sunday = monday + timedelta(days=6)

    return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")


def save_summary(summary: str, week_start: str) -> str:
    """Save the formatted summary to a markdown file.

    Args:
        summary: The formatted markdown summary.
        week_start: Start date (YYYY-MM-DD) used in filename.

    Returns:
        The file path where the summary was saved.
    """
    output_dir = Path("output/summaries")
    output_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    created_at = now.strftime("%Y-%m-%d-%H%M%S")
    file_path = output_dir / f"{week_start}_created-{created_at}.md"
    file_path.write_text(summary, encoding="utf-8")

    return str(file_path)
