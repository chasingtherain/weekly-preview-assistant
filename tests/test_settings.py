"""Tests for global settings."""

from config.settings import load_settings


class TestLoadSettings:
    def test_defaults(self, monkeypatch) -> None:
        # Clear any existing env vars
        for var in [
            "CALENDAR_IDS", "CALENDAR_LABELS", "OLLAMA_HOST", "OLLAMA_MODEL",
            "USER_TIMEZONE", "ORCHESTRATOR_PORT", "CALENDAR_PORT", "FORMATTER_PORT",
        ]:
            monkeypatch.delenv(var, raising=False)

        settings = load_settings()
        assert len(settings.calendars) == 1
        assert settings.calendars[0].calendar_id == "primary"
        assert settings.calendars[0].label == "You"
        assert settings.ollama_host == "http://localhost:11434"
        assert settings.orchestrator_port == 5000

    def test_multi_calendar_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("CALENDAR_IDS", "primary,partner@gmail.com")
        monkeypatch.setenv("CALENDAR_LABELS", "You,Partner")

        settings = load_settings()
        assert len(settings.calendars) == 2
        assert settings.calendars[0].calendar_id == "primary"
        assert settings.calendars[0].label == "You"
        assert settings.calendars[1].calendar_id == "partner@gmail.com"
        assert settings.calendars[1].label == "Partner"

    def test_labels_shorter_than_ids_uses_id_as_fallback(self, monkeypatch) -> None:
        monkeypatch.setenv("CALENDAR_IDS", "primary,partner@gmail.com,work@company.com")
        monkeypatch.setenv("CALENDAR_LABELS", "You")

        settings = load_settings()
        assert len(settings.calendars) == 3
        assert settings.calendars[0].label == "You"
        assert settings.calendars[1].label == "partner@gmail.com"
        assert settings.calendars[2].label == "work@company.com"

    def test_custom_ports(self, monkeypatch) -> None:
        monkeypatch.setenv("ORCHESTRATOR_PORT", "8000")
        monkeypatch.setenv("CALENDAR_PORT", "8001")
        monkeypatch.setenv("FORMATTER_PORT", "8002")

        settings = load_settings()
        assert settings.orchestrator_port == 8000
        assert settings.calendar_port == 8001
        assert settings.formatter_port == 8002
