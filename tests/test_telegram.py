"""Tests for Telegram Agent - message sending and HTTP server."""

from unittest.mock import MagicMock, patch

import pytest

from a2a.protocol import Role, create_message, create_send_message_request, data_part, text_part
from agents.telegram.agent import TelegramAgent


# ---------------------------------------------------------------------------
# agent.py - TelegramAgent tests
# ---------------------------------------------------------------------------


class TestTelegramAgent:
    def _make_agent(self) -> TelegramAgent:
        return TelegramAgent(bot_token="test-token", chat_id="12345")

    @patch("agents.telegram.agent.requests.post")
    def test_send_message_success(self, mock_post) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ok": True,
            "result": {"message_id": 42},
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        agent = self._make_agent()
        result = agent.send_message("Hello!")

        assert result["message_id"] == 42
        assert result["chat_id"] == "12345"
        assert "sent_at" in result
        assert "error" not in result
        mock_post.assert_called_once()

    @patch("agents.telegram.agent.requests.post")
    def test_send_message_api_error(self, mock_post) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "ok": False,
            "description": "Bad Request: chat not found",
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        agent = self._make_agent()
        result = agent.send_message("Hello!")

        assert "error" in result
        assert "chat not found" in result["error"]

    @patch("agents.telegram.agent.requests.post")
    def test_send_message_timeout(self, mock_post) -> None:
        import requests as req

        mock_post.side_effect = req.Timeout("Connection timed out")

        agent = self._make_agent()
        result = agent.send_message("Hello!")

        assert "error" in result
        assert "timed out" in result["error"]

    @patch("agents.telegram.agent.requests.post")
    def test_send_message_connection_error(self, mock_post) -> None:
        import requests as req

        mock_post.side_effect = req.ConnectionError("Connection refused")

        agent = self._make_agent()
        result = agent.send_message("Hello!")

        assert "error" in result


# ---------------------------------------------------------------------------
# server.py - HTTP endpoint tests
# ---------------------------------------------------------------------------


class TestTelegramServer:
    @pytest.fixture
    def client(self):
        from agents.telegram.server import app
        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

    def test_agent_card_endpoint(self, client) -> None:
        response = client.get("/.well-known/agent.json")
        assert response.status_code == 200
        card = response.get_json()
        assert card["name"] == "Telegram Agent"
        assert card["skills"][0]["id"] == "send_telegram_message"

    def test_get_task_not_found(self, client) -> None:
        response = client.get("/tasks/nonexistent-id")
        assert response.status_code == 404

    def test_send_message_invalid_request(self, client) -> None:
        response = client.post(
            "/message/send",
            json={"message": {"role": "user"}},
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_send_message_no_params(self, client) -> None:
        msg = create_message(Role.USER, [text_part("just text")])
        req = create_send_message_request(msg)

        response = client.post("/message/send", json=req, content_type="application/json")
        assert response.status_code == 200
        assert response.get_json()["task"]["status"]["state"] == "failed"

    @patch("agents.telegram.server._get_agent")
    def test_send_message_success(self, mock_get_agent, client) -> None:
        mock_agent = MagicMock()
        mock_agent.send_message.return_value = {
            "message_id": 42,
            "chat_id": "12345",
            "sent_at": "2025-02-16T20:00:00+00:00",
        }
        mock_get_agent.return_value = mock_agent

        msg = create_message(
            Role.USER,
            [data_part({
                "action": "send_telegram_message",
                "parameters": {"text": "Hello from test!"},
            })],
        )
        req = create_send_message_request(msg)

        response = client.post("/message/send", json=req, content_type="application/json")
        assert response.status_code == 200

        data = response.get_json()
        task = data["task"]
        assert task["status"]["state"] == "completed"
        assert len(task["artifacts"]) == 1

    @patch("agents.telegram.server._get_agent")
    def test_send_message_empty_text(self, mock_get_agent, client) -> None:
        mock_get_agent.return_value = MagicMock()

        msg = create_message(
            Role.USER,
            [data_part({
                "action": "send_telegram_message",
                "parameters": {"text": ""},
            })],
        )
        req = create_send_message_request(msg)

        response = client.post("/message/send", json=req, content_type="application/json")
        assert response.status_code == 200
        assert response.get_json()["task"]["status"]["state"] == "failed"

    @patch("agents.telegram.server._get_agent")
    def test_send_message_agent_error(self, mock_get_agent, client) -> None:
        mock_agent = MagicMock()
        mock_agent.send_message.return_value = {"error": "Connection refused"}
        mock_get_agent.return_value = mock_agent

        msg = create_message(
            Role.USER,
            [data_part({
                "action": "send_telegram_message",
                "parameters": {"text": "Hello!"},
            })],
        )
        req = create_send_message_request(msg)

        response = client.post("/message/send", json=req, content_type="application/json")
        assert response.status_code == 200
        assert response.get_json()["task"]["status"]["state"] == "failed"
