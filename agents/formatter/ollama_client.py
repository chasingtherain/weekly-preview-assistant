"""Ollama API wrapper.

Handles communication with a local Ollama instance for LLM-based text
generation. Isolates all Ollama-specific code so the formatter agent
logic stays clean.
"""

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 60  # Ollama can be slow on first load


def generate(
    prompt: str,
    model: str,
    host: str = "http://localhost:11434",
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Generate text using Ollama's /api/generate endpoint.

    Args:
        prompt: The prompt to send to the model.
        model: Ollama model name (e.g. "llama3.2").
        host: Ollama server URL.
        timeout: Request timeout in seconds.

    Returns:
        The generated text response.

    Raises:
        requests.RequestException: If the Ollama server is unreachable.
        ValueError: If the response is malformed.
    """
    url = f"{host.rstrip('/')}/api/generate"
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }

    logger.info("Sending prompt to Ollama (%s, model=%s)", host, model)
    logger.debug("Prompt length: %d chars", len(prompt))

    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()

    data = response.json()
    text = data.get("response", "")

    if not text:
        raise ValueError("Ollama returned an empty response.")

    logger.info("Received response from Ollama (%d chars)", len(text))
    return text
