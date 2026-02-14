"""Weekly Preview Assistant - Entry Point.

Starts all agent servers, registers them, and triggers the weekly preview workflow.
"""

import argparse


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

    # TODO: Phase 4 - Start agents, register, trigger workflow
    week_label = "following week" if args.next_week else "current week"
    print(f"Weekly Preview Assistant - generating preview for {week_label}")
    print("(Not yet implemented - agents will be wired up in Phase 4)")


if __name__ == "__main__":
    main()
