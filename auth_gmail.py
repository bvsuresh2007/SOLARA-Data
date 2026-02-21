"""
One-time Gmail + Drive OAuth setup.

Reads credentials.json from the project root, opens a browser for Google
account consent, and saves token.json to the project root.

Run once:
    python auth_gmail.py

After this, all scrapers and Drive upload utilities will use token.json
automatically. Re-run if the token ever expires or is revoked.
"""
import os
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.file",
]

_ROOT         = Path(__file__).resolve().parent
_CREDS_PATH   = _ROOT / "credentials.json"
_TOKEN_PATH   = _ROOT / "token.json"


def main():
    if not _CREDS_PATH.exists():
        print(f"ERROR: credentials.json not found at {_CREDS_PATH}")
        print("Download it from Google Cloud Console → APIs & Services → Credentials.")
        sys.exit(1)

    print("Opening browser for Google OAuth consent…")
    flow = InstalledAppFlow.from_client_secrets_file(str(_CREDS_PATH), SCOPES)
    creds = flow.run_local_server(port=0)

    _TOKEN_PATH.write_text(creds.to_json())
    print(f"\ntoken.json saved to: {_TOKEN_PATH}")
    print("You can now run scrapers and Drive utilities.")


if __name__ == "__main__":
    main()
