"""Global Settings - Loads configuration from environment variables.

Centralizes all configuration so agents don't read env vars directly.
"""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass
class CalendarConfig:
    """Configuration for a single calendar source."""

    calendar_id: str
    label: str


@dataclass
class Settings:
    """Application-wide settings loaded from environment variables."""

    # Google Calendar
    google_credentials_path: str = ""
    google_token_path: str = ""

    # Multi-calendar: list of (calendar_id, label) pairs
    calendars: list[CalendarConfig] = field(default_factory=list)

    # Ollama
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    # User preferences
    user_timezone: str = "America/Los_Angeles"

    # Agent ports
    orchestrator_port: int = 5000
    calendar_port: int = 5001
    formatter_port: int = 5002


def load_settings() -> Settings:
    """Load settings from environment variables with sensible defaults.

    Environment variables:
        GOOGLE_CALENDAR_CREDENTIALS_PATH: Path to Google OAuth credentials.json
        GOOGLE_CALENDAR_TOKEN_PATH: Path to saved OAuth token.json
        CALENDAR_IDS: Comma-separated calendar IDs (default: "primary")
        CALENDAR_LABELS: Comma-separated labels matching IDs (default: "You")
        OLLAMA_HOST: Ollama server URL
        OLLAMA_MODEL: Model name for Ollama
        USER_TIMEZONE: IANA timezone string
        ORCHESTRATOR_PORT, CALENDAR_PORT, FORMATTER_PORT: Agent ports

    Returns:
        A populated Settings instance.
    """
    calendar_ids = os.getenv("CALENDAR_IDS", "primary").split(",")
    calendar_labels = os.getenv("CALENDAR_LABELS", "You").split(",")

    # Pair IDs with labels; if labels list is shorter, default to the ID itself
    calendars = []
    for i, cal_id in enumerate(calendar_ids):
        label = calendar_labels[i].strip() if i < len(calendar_labels) else cal_id.strip()
        calendars.append(CalendarConfig(calendar_id=cal_id.strip(), label=label))

    return Settings(
        google_credentials_path=os.getenv("GOOGLE_CALENDAR_CREDENTIALS_PATH", "credentials.json"),
        google_token_path=os.getenv("GOOGLE_CALENDAR_TOKEN_PATH", "token.json"),
        calendars=calendars,
        ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        ollama_model=os.getenv("OLLAMA_MODEL", "llama3.2"),
        user_timezone=os.getenv("USER_TIMEZONE", "America/Los_Angeles"),
        orchestrator_port=int(os.getenv("ORCHESTRATOR_PORT", "5000")),
        calendar_port=int(os.getenv("CALENDAR_PORT", "5001")),
        formatter_port=int(os.getenv("FORMATTER_PORT", "5002")),
    )
