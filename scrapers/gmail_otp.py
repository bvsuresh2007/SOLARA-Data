"""
Generic Gmail OTP fetcher.

Connects to automation@solara.in via the Gmail API and fetches the latest
OTP from a specified sender. Used by all portal scrapers that receive
OTP codes by email.

Usage:
    from scrapers.gmail_otp import fetch_latest_otp

    otp = fetch_latest_otp(sender="noreply@rmo.flipkart.com")
    otp = fetch_latest_otp(sender="noreply@zepto.co.in")
"""

import base64
import html as html_module
import json
import logging
import os
import re
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.file",
]

# Anchor token.json to the project root (two levels up from scrapers/)
_TOKEN_PATH = Path(__file__).resolve().parent.parent / "token.json"


def _get_gmail_service():
    """Authenticate and return a Gmail API service object."""
    token_json = os.environ.get("GMAIL_TOKEN_JSON")

    if token_json:
        creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
    elif _TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN_PATH), SCOPES)
    else:
        raise FileNotFoundError(
            "No Gmail token found. Run auth_gmail.py first to generate token.json."
        )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        if _TOKEN_PATH.exists():
            _TOKEN_PATH.write_text(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def _get_message_subject(service, message_id: str) -> str:
    message = service.users().messages().get(
        userId="me", id=message_id, format="metadata",
        metadataHeaders=["Subject"]
    ).execute()
    headers = message.get("payload", {}).get("headers", [])
    for h in headers:
        if h["name"] == "Subject":
            return h["value"]
    return ""


def _strip_html(raw: str) -> str:
    """Strip <style>/<script> blocks and HTML tags, returning visible text."""
    # Remove style and script blocks (contain CSS color codes like #333333)
    raw = re.sub(r"<style[^>]*>.*?</style>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    raw = re.sub(r"<script[^>]*>.*?</script>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    # Remove all remaining HTML tags
    raw = re.sub(r"<[^>]+>", " ", raw)
    # Decode HTML entities (e.g. &nbsp; -> space)
    return html_module.unescape(raw)


def _collect_parts(part) -> list:
    """Recursively collect all leaf parts from a MIME tree."""
    mime = part.get("mimeType", "")
    if mime.startswith("multipart/"):
        result = []
        for sub in part.get("parts", []):
            result.extend(_collect_parts(sub))
        return result
    return [part]


def _get_message_body(service, message_id: str) -> str:
    message = service.users().messages().get(
        userId="me", id=message_id, format="full"
    ).execute()

    payload = message.get("payload", {})

    # Collect all leaf MIME parts (handles arbitrary nesting depth)
    if payload.get("parts"):
        leaf_parts = []
        for p in payload["parts"]:
            leaf_parts.extend(_collect_parts(p))
    else:
        leaf_parts = [payload]

    def _decode(part):
        data = part.get("body", {}).get("data", "")
        if not data:
            return ""
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

    # Prefer plain text
    for part in leaf_parts:
        if part.get("mimeType") == "text/plain":
            text = _decode(part)
            if text.strip():
                return text

    # Fallback: any HTML part
    for part in leaf_parts:
        if part.get("mimeType") == "text/html":
            raw = _decode(part)
            if raw.strip():
                return _strip_html(raw)

    return ""


def _extract_otp(text: str) -> str | None:
    """Extract a 4–8 digit OTP from text."""
    match = re.search(r"\b(\d{4,8})\b", text)
    return match.group(1) if match else None


def fetch_latest_otp(sender: str, after_epoch: int = None) -> str | None:
    """
    Fetch the most recent email from `sender` and extract the OTP.

    Checks the subject line first (most portals embed OTP there),
    then falls back to the email body.

    Args:
        sender:      Exact sender email address, e.g. "mailer@zeptonow.com"
        after_epoch: Unix timestamp (seconds). If provided, only emails
                     received after this time are considered. Use this to
                     avoid picking up OTPs from previous login sessions.

    Returns:
        OTP string (e.g. "483921") or None if not found.
    """
    service = _get_gmail_service()

    query = f"from:{sender}"
    if after_epoch:
        query += f" after:{after_epoch}"

    result = service.users().messages().list(
        userId="me", q=query, maxResults=1
    ).execute()

    messages = result.get("messages", [])
    if not messages:
        return None

    msg_id = messages[0]["id"]
    subject = _get_message_subject(service, msg_id)
    body = _get_message_body(service, msg_id)

    return _extract_otp(subject) or _extract_otp(body)
