"""A2A HTTP Client - Google A2A spec aligned.

Implements the client side of the A2A protocol over HTTP+JSON:
- POST /message/send (SendMessage)
- GET /tasks/{id} (GetTask)

Includes retry logic with exponential backoff and message logging.

A2A Concept: This is the transport layer. The client sends a
SendMessageRequest containing a Message, and receives back either
a Task or a Message in the SendMessageResponse.
"""

import logging
import time
from typing import Any

import requests

from a2a.logger import log_a2a_message
from a2a.protocol import ERROR_REQUEST_FAILED, ERROR_TIMEOUT
from a2a.validator import validate_send_message_request

logger = logging.getLogger(__name__)


def send_message(
    agent_url: str,
    request: dict[str, Any],
    timeout: int = 15,
    max_retries: int = 2,
    caller: str = "client",
) -> dict[str, Any]:
    """Send a SendMessageRequest to an agent's /message/send endpoint.

    Args:
        agent_url: The agent's base URL (e.g. "http://localhost:5001").
        request: A SendMessageRequest dict.
        timeout: Request timeout in seconds.
        max_retries: Number of retries on failure.
        caller: Identifier for the calling agent (for logging).

    Returns:
        The SendMessageResponse dict (containing a Task or Message),
        or an error dict if the request failed.
    """
    # Validate before sending
    is_valid, error_desc = validate_send_message_request(request)
    if not is_valid:
        logger.error("Outgoing request validation failed: %s", error_desc)
        return {"error": {"code": "InvalidMessageError", "message": error_desc}}

    # Log outgoing
    log_a2a_message(request, direction="outgoing", agent_id=caller)

    url = f"{agent_url}/message/send"

    for attempt in range(max_retries + 1):
        try:
            response = requests.post(url, json=request, timeout=timeout)
            response.raise_for_status()
            response_data = response.json()

            # Log incoming response
            log_a2a_message(response_data, direction="incoming", agent_id=caller)
            return response_data

        except requests.Timeout:
            logger.warning(
                "Timeout calling %s (attempt %d/%d)", url, attempt + 1, max_retries + 1
            )
            if attempt < max_retries:
                wait_time = 2 ** (attempt + 1)
                logger.info("Retrying in %ds...", wait_time)
                time.sleep(wait_time)
            else:
                logger.error("Failed after %d retries: timeout", max_retries)
                return {"error": {"code": ERROR_TIMEOUT, "message": f"Timeout calling {url}"}}

        except requests.RequestException as e:
            logger.warning(
                "Request to %s failed (attempt %d/%d): %s",
                url,
                attempt + 1,
                max_retries + 1,
                e,
            )
            if attempt < max_retries:
                wait_time = 2 ** (attempt + 1)
                logger.info("Retrying in %ds...", wait_time)
                time.sleep(wait_time)
            else:
                logger.error("Failed after %d retries: %s", max_retries, e)
                return {
                    "error": {"code": ERROR_REQUEST_FAILED, "message": str(e)},
                }

    return {"error": {"code": ERROR_REQUEST_FAILED, "message": "Unexpected retry exhaustion"}}


def get_task(
    agent_url: str,
    task_id: str,
    timeout: int = 10,
    caller: str = "client",
) -> dict[str, Any]:
    """Get the current state of a task from an agent.

    Args:
        agent_url: The agent's base URL.
        task_id: The task ID to query.
        timeout: Request timeout in seconds.
        caller: Identifier for the calling agent (for logging).

    Returns:
        The Task dict, or an error dict if the request failed.
    """
    url = f"{agent_url}/tasks/{task_id}"

    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        task_data = response.json()

        log_a2a_message(task_data, direction="incoming", agent_id=caller)
        return task_data

    except requests.RequestException as e:
        logger.error("Failed to get task %s from %s: %s", task_id, url, e)
        return {"error": {"code": ERROR_REQUEST_FAILED, "message": str(e)}}
