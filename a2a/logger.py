"""A2A Message Logger.

Logs every A2A message to daily log files as newline-delimited JSON (NDJSON).
This is steps 3 (outgoing) and 7 (incoming) of the Message Lifecycle.

A2A Concept: Double logging is critical for debugging. The sender logs
"I sent X at time T" and the receiver logs "I received X at time T".
If only one log exists, you know exactly where the failure occurred.
Together they form a complete audit trail of every interaction.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Directory for A2A message logs
LOG_DIR = Path(__file__).parent.parent / "logs" / "a2a_messages"

# Standard Python logger for error-level events
_error_logger = logging.getLogger("a2a.errors")


def _ensure_log_dir() -> None:
    """Create the log directory if it doesn't exist."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def log_a2a_message(
    message: dict[str, Any],
    direction: str,
    agent_id: str | None = None,
) -> None:
    """Log an A2A message to the daily log file.

    Each log entry is a JSON object on its own line (NDJSON format),
    which makes it easy to filter with jq.

    Args:
        message: The A2A message dict to log.
        direction: Either "outgoing" or "incoming".
        agent_id: The agent performing the logging (for context).
    """
    _ensure_log_dir()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_file = LOG_DIR / f"{today}.log"

    log_entry = {
        "logged_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "direction": direction,
        "logged_by": agent_id or message.get("from_agent", "unknown"),
        "message": message,
    }

    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, default=str) + "\n")
    except OSError as e:
        _error_logger.error("Failed to write A2A log: %s", e)
