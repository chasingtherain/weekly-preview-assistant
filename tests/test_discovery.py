"""Tests for A2A Agent Card discovery."""

from unittest.mock import patch, MagicMock

from a2a.discovery import discover_agents, fetch_agent_card, find_agent_by_skill, get_agent_url
from a2a.protocol import create_agent_card, create_skill


def _sample_card(name: str, url: str, skill_id: str) -> dict:
    return create_agent_card(
        name=name,
        description=f"{name} agent",
        url=url,
        skills=[create_skill(skill_id, name, f"Does {skill_id}", [skill_id])],
    )


class TestFetchAgentCard:
    @patch("a2a.discovery.requests.get")
    def test_successful_fetch(self, mock_get) -> None:
        card = _sample_card("Calendar", "http://localhost:5001", "fetch_events")
        mock_response = MagicMock()
        mock_response.json.return_value = card
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = fetch_agent_card("http://localhost:5001")
        assert result is not None
        assert result["name"] == "Calendar"
        mock_get.assert_called_once_with(
            "http://localhost:5001/.well-known/agent.json", timeout=5
        )

    @patch("a2a.discovery.requests.get")
    def test_returns_none_on_network_error(self, mock_get) -> None:
        import requests

        mock_get.side_effect = requests.ConnectionError("refused")
        result = fetch_agent_card("http://localhost:9999")
        assert result is None

    @patch("a2a.discovery.requests.get")
    def test_returns_none_on_invalid_card(self, mock_get) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"name": ""}  # Invalid: empty name
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = fetch_agent_card("http://localhost:5001")
        assert result is None


class TestDiscoverAgents:
    @patch("a2a.discovery.fetch_agent_card")
    def test_discovers_multiple_agents(self, mock_fetch) -> None:
        card1 = _sample_card("Calendar", "http://localhost:5001", "fetch_events")
        card2 = _sample_card("Formatter", "http://localhost:5002", "format_summary")
        mock_fetch.side_effect = [card1, card2]

        cards = discover_agents(["http://localhost:5001", "http://localhost:5002"])
        assert len(cards) == 2

    @patch("a2a.discovery.fetch_agent_card")
    def test_skips_unreachable_agents(self, mock_fetch) -> None:
        card1 = _sample_card("Calendar", "http://localhost:5001", "fetch_events")
        mock_fetch.side_effect = [card1, None]  # second agent unreachable

        cards = discover_agents(["http://localhost:5001", "http://localhost:5002"])
        assert len(cards) == 1
        assert cards[0]["name"] == "Calendar"


class TestFindAgentBySkill:
    def test_finds_matching_skill(self) -> None:
        cards = [
            _sample_card("Calendar", "http://localhost:5001", "fetch_events"),
            _sample_card("Formatter", "http://localhost:5002", "format_summary"),
        ]
        result = find_agent_by_skill(cards, "format_summary")
        assert result is not None
        assert result["name"] == "Formatter"

    def test_returns_none_when_not_found(self) -> None:
        cards = [_sample_card("Calendar", "http://localhost:5001", "fetch_events")]
        result = find_agent_by_skill(cards, "nonexistent")
        assert result is None


class TestGetAgentUrl:
    def test_extracts_url(self) -> None:
        card = _sample_card("Calendar", "http://localhost:5001", "fetch_events")
        assert get_agent_url(card) == "http://localhost:5001"

    def test_returns_none_for_empty_interfaces(self) -> None:
        card = _sample_card("Calendar", "http://localhost:5001", "fetch_events")
        card["supported_interfaces"] = []
        assert get_agent_url(card) is None
