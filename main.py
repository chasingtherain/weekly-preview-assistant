"""Weekly Preview Assistant - Entry Point.

Starts the Calendar and Formatter agent servers in background threads,
discovers them via A2A Agent Cards, runs the orchestrator workflow,
and saves the formatted weekly preview.

Usage:
    python main.py          # Current week (Monday-Sunday)
    python main.py --next   # Following week
"""

import argparse
import logging
import sys
import time
from threading import Thread

from agents.calendar.server import app as calendar_app
from agents.formatter.server import app as formatter_app
from agents.orchestrator.agent import OrchestratorAgent, calculate_week_range
from config.settings import load_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


def start_agent_server(app, port: int, name: str) -> Thread:
    """Start a Flask agent server in a background daemon thread.

    Args:
        app: The Flask application to run.
        port: Port number to bind to.
        name: Human-readable name for logging.

    Returns:
        The started Thread.
    """
    def run():
        # Suppress Flask/Werkzeug request logs in production
        log = logging.getLogger("werkzeug")
        log.setLevel(logging.WARNING)
        app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)

    thread = Thread(target=run, name=name, daemon=True)
    thread.start()
    return thread


def wait_for_agents(urls: list[str], timeout: int = 10) -> bool:
    """Wait until all agent servers are responding.

    Args:
        urls: List of agent base URLs to check.
        timeout: Max seconds to wait.

    Returns:
        True if all agents are ready, False if timeout.
    """
    import requests

    start = time.time()
    ready = set()

    while time.time() - start < timeout:
        for url in urls:
            if url in ready:
                continue
            try:
                resp = requests.get(f"{url}/.well-known/agent.json", timeout=2)
                if resp.status_code == 200:
                    ready.add(url)
            except requests.RequestException:
                pass

        if len(ready) == len(urls):
            return True
        time.sleep(0.3)

    return False


def main() -> None:
    """Parse arguments and run the weekly preview workflow."""
    parser = argparse.ArgumentParser(description="Generate a weekly calendar preview.")
    parser.add_argument(
        "--next",
        action="store_true",
        dest="next_week",
        help="Generate preview for the following week instead of the current week.",
    )
    args = parser.parse_args()

    settings = load_settings()

    print("Starting Weekly Preview Assistant...")
    print()

    # Start agent servers
    calendar_url = f"http://127.0.0.1:{settings.calendar_port}"
    formatter_url = f"http://127.0.0.1:{settings.formatter_port}"
    telegram_url = ""

    start_agent_server(calendar_app, settings.calendar_port, "Calendar Agent")
    print(f"  Calendar Agent started on port {settings.calendar_port}")

    start_agent_server(formatter_app, settings.formatter_port, "Formatter Agent")
    print(f"  Formatter Agent started on port {settings.formatter_port}")

    agent_urls = [calendar_url, formatter_url]

    # Start Telegram agent only if configured
    if settings.telegram_bot_token:
        from agents.telegram.server import app as telegram_app

        telegram_url = f"http://127.0.0.1:{settings.telegram_port}"
        start_agent_server(telegram_app, settings.telegram_port, "Telegram Agent")
        print(f"  Telegram Agent started on port {settings.telegram_port}")
        agent_urls.append(telegram_url)

    # Wait for agents to be ready
    print("  Waiting for agents to be ready...")
    if not wait_for_agents(agent_urls):
        print("  ERROR: Agents failed to start within timeout. Exiting.")
        sys.exit(1)

    print("  All agents ready")
    print()

    # Calculate and display date range
    start_date, end_date = calculate_week_range(args.next_week)
    print(f"Generating preview for: {start_date} to {end_date}")
    print()

    # Build orchestrator and run workflow
    calendars = [
        {"calendar_id": c.calendar_id, "label": c.label}
        for c in settings.calendars
    ]

    orchestrator = OrchestratorAgent(
        calendar_url=calendar_url,
        formatter_url=formatter_url,
        calendars=calendars,
        timezone=settings.user_timezone,
        telegram_url=telegram_url,
    )

    print("Fetching calendar events...")
    result = orchestrator.generate_weekly_preview(next_week=args.next_week)

    if "error" in result:
        print(f"  ERROR: {result['error']}")
        sys.exit(1)

    print(f"  Retrieved {result['total_events']} events")
    if result.get("telegram_sent"):
        print("  Sent to Telegram")
    print()
    print(f"Weekly preview saved to: {result['file_path']}")


if __name__ == "__main__":
    main()
