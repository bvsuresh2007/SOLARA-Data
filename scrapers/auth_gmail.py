"""
Gmail OAuth authorization helper.

Run this script once (locally, with a browser) to generate token.json, which
is used by gmail_otp.py to fetch OTPs for Swiggy, Blinkit, and other scrapers.

Prerequisites:
  1. Download OAuth 2.0 credentials from Google Cloud Console:
       APIs & Services → Credentials → Create Credentials → OAuth client ID
       Application type: Desktop app
     Save the downloaded file as  credentials.json  in the project root.
  2. Ensure the Gmail API is enabled for the project.

Usage:
    python scrapers/auth_gmail.py

After running:
  - token.json is written to the project root.
  - Follow the printed instructions to update the GOOGLE_TOKEN_JSON
    GitHub secret so CI workflows can use the new token.
"""

import base64
import sys
from pathlib import Path

# Project root is one level up from scrapers/
_ROOT = Path(__file__).resolve().parent.parent
_CREDENTIALS_PATH = _ROOT / "credentials.json"
_TOKEN_PATH = _ROOT / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.file",
]


def main():
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("ERROR: google-auth-oauthlib is not installed.")
        print("Run:  pip install google-auth-oauthlib")
        sys.exit(1)

    if not _CREDENTIALS_PATH.exists():
        print(f"ERROR: credentials.json not found at {_CREDENTIALS_PATH}")
        print()
        print("To fix:")
        print("  1. Go to https://console.cloud.google.com/apis/credentials")
        print("  2. Create an OAuth 2.0 Client ID (Desktop app type)")
        print("  3. Download the JSON and save it as credentials.json in the project root")
        sys.exit(1)

    print("Opening browser for Google authorization...")
    print("Sign in with the automation@solara.in account.\n")

    flow = InstalledAppFlow.from_client_secrets_file(str(_CREDENTIALS_PATH), SCOPES)
    creds = flow.run_local_server(port=0)

    _TOKEN_PATH.write_text(creds.to_json())
    print(f"\ntoken.json saved to: {_TOKEN_PATH}")

    # Print the base64-encoded value ready to paste into GitHub secrets
    b64 = base64.b64encode(_TOKEN_PATH.read_bytes()).decode()
    print()
    print("=" * 60)
    print("Next step — update the GitHub secret:")
    print("=" * 60)
    print()
    print("1. Go to: https://github.com/bvsuresh2007/SOLARA-Data/settings/secrets/actions")
    print("2. Edit the secret named:  GOOGLE_TOKEN_JSON")
    print("3. Paste the value below (the entire line):")
    print()
    print(b64)
    print()
    print("=" * 60)
    print("Done. Re-run the failed scraper workflows after updating the secret.")


if __name__ == "__main__":
    main()
