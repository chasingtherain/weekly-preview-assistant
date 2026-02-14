"""A2A Agent Discovery - Agent Card based discovery.

In the Google A2A spec, agents are discovered by fetching their Agent Card
from GET /.well-known/agent.json. There is no central registry — each agent
self-describes its capabilities and endpoint.

A2A Concept (Principle 2 - Agent Discovery): Instead of a central phone
directory, each agent publishes its own business card at a known URL.
The orchestrator fetches these cards to learn what each agent can do
and where to send messages.

For our MVP, the orchestrator knows the base URLs of agents from config
and fetches their Agent Cards on startup.
"""

import logging
from typing import Any

import requests

from a2a.validator import validate_agent_card

logger = logging.getLogger(__name__)

AGENT_CARD_PATH = "/.well-known/agent.json"


def fetch_agent_card(base_url: str, timeout: int = 5) -> dict[str, Any] | None:
    """Fetch an Agent Card from an agent's well-known endpoint.

    Args:
        base_url: The agent's base URL (e.g. "http://localhost:5001").
        timeout: Request timeout in seconds.

    Returns:
        The AgentCard dict if successful and valid, None otherwise.
    """
    url = f"{base_url}{AGENT_CARD_PATH}"
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        card = response.json()

        is_valid, err = validate_agent_card(card)
        if not is_valid:
            logger.error("Invalid Agent Card from %s: %s", url, err)
            return None

        logger.info("Discovered agent: %s at %s", card.get("name"), base_url)
        return card

    except requests.RequestException as e:
        logger.warning("Failed to fetch Agent Card from %s: %s", url, e)
        return None


def discover_agents(base_urls: list[str]) -> list[dict[str, Any]]:
    """Discover all agents by fetching their Agent Cards.

    Args:
        base_urls: List of agent base URLs to query.

    Returns:
        List of valid AgentCard dicts for reachable agents.
    """
    cards = []
    for url in base_urls:
        card = fetch_agent_card(url)
        if card:
            cards.append(card)
    return cards


def find_agent_by_skill(cards: list[dict[str, Any]], skill_id: str) -> dict[str, Any] | None:
    """Find an agent that has a specific skill.

    Args:
        cards: List of AgentCard dicts.
        skill_id: The skill ID to search for.

    Returns:
        The matching AgentCard, or None if not found.
    """
    for card in cards:
        for skill in card.get("skills", []):
            if skill.get("id") == skill_id:
                return card
    return None


def get_agent_url(card: dict[str, Any]) -> str | None:
    """Extract the agent's base URL from its Agent Card.

    Args:
        card: An AgentCard dict.

    Returns:
        The URL string from the first supported interface, or None.
    """
    interfaces = card.get("supported_interfaces", [])
    if interfaces:
        return interfaces[0].get("url")
    return None
