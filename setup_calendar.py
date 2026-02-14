"""Google Calendar OAuth Setup.

Run this once to authenticate with Google Calendar and save a token.
Opens your browser for the OAuth consent flow, then saves token.json
for future use by the Calendar Agent.

Usage:
    python setup_calendar.py
"""

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
CREDENTIALS_PATH = "credentials.json"
TOKEN_PATH = "token.json"


def main() -> None:
    """Run the OAuth flow and save the token."""
    print("Starting Google Calendar authentication...")
    print(f"Using credentials from: {CREDENTIALS_PATH}")
    print()

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
    creds = flow.run_local_server(port=0)

    with open(TOKEN_PATH, "w") as f:
        f.write(creds.to_json())

    print()
    print(f"Token saved to: {TOKEN_PATH}")
    print("You can now run: python main.py")


if __name__ == "__main__":
    main()
