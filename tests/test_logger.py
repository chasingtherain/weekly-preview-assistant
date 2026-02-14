"""Tests for A2A message logger."""

import json

from a2a.logger import LOG_DIR, log_a2a_message


class TestA2ALogger:
    def test_log_creates_file_and_writes_ndjson(self, tmp_path, monkeypatch) -> None:
        # Redirect log dir to tmp
        monkeypatch.setattr("a2a.logger.LOG_DIR", tmp_path)

        message = {
            "message_id": "test-123",
            "from_agent": "orchestrator-main",
            "to_agent": "calendar-001",
            "message_type": "task_request",
        }

        log_a2a_message(message, direction="outgoing", agent_id="orchestrator-main")

        # Find the log file (named by today's date)
        log_files = list(tmp_path.glob("*.log"))
        assert len(log_files) == 1

        lines = log_files[0].read_text().strip().split("\n")
        assert len(lines) == 1

        entry = json.loads(lines[0])
        assert entry["direction"] == "outgoing"
        assert entry["logged_by"] == "orchestrator-main"
        assert entry["message"]["message_id"] == "test-123"
        assert entry["logged_at"].endswith("Z")

    def test_multiple_logs_append(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr("a2a.logger.LOG_DIR", tmp_path)

        for i in range(3):
            log_a2a_message(
                {"message_id": f"msg-{i}", "from_agent": "a"},
                direction="outgoing",
            )

        log_files = list(tmp_path.glob("*.log"))
        lines = log_files[0].read_text().strip().split("\n")
        assert len(lines) == 3

    def test_logged_by_falls_back_to_from_agent(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr("a2a.logger.LOG_DIR", tmp_path)

        log_a2a_message(
            {"message_id": "x", "from_agent": "calendar-001"},
            direction="incoming",
        )

        log_files = list(tmp_path.glob("*.log"))
        entry = json.loads(log_files[0].read_text().strip())
        assert entry["logged_by"] == "calendar-001"
