"""
Google Drive upload utility for scrapers.

Uploads downloaded report files to a structured Google Drive folder:
  SolaraDashboard Reports/
    └── YYYY-MM/
        └── <Portal>/
            └── <filename>

Uses the same OAuth token as Gmail (token.json / GMAIL_TOKEN_JSON secret).
The drive.file scope allows the app to manage only files it creates.

Usage:
    from scrapers.google_drive_upload import upload_to_drive
    from pathlib import Path
    from datetime import date

    link = upload_to_drive(
        portal="Zepto",
        report_date=date(2026, 2, 18),
        file_path=Path("data/raw/zepto/zepto_sales_2026-02-18.xlsx"),
    )
    print(link)  # https://drive.google.com/file/d/xxxx/view
"""

import json
import logging
import os
from datetime import date
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Suppress harmless file_cache warning from google-api-python-client
logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.file",
]

ROOT_FOLDER_NAME = "SolaraDashboard Reports"

# Set GOOGLE_DRIVE_ROOT_FOLDER_ID in .env to use an existing Drive folder as root
# (paste the folder ID from the Drive URL). If not set, falls back to creating /
# finding a folder named ROOT_FOLDER_NAME in My Drive.
_ROOT_FOLDER_ID_ENV = "GOOGLE_DRIVE_ROOT_FOLDER_ID"

MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MIME_CSV  = "text/csv"
MIME_DIR  = "application/vnd.google-apps.folder"


def _get_drive_service():
    token_json = os.environ.get("GMAIL_TOKEN_JSON")
    if token_json:
        creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
    elif Path("token.json").exists():
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    else:
        raise FileNotFoundError(
            "No token found. Run auth_gmail.py to generate token.json."
        )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        if Path("token.json").exists():
            with open("token.json", "w") as f:
                f.write(creds.to_json())

    return build("drive", "v3", credentials=creds)


def _get_or_create_folder(service, name: str, parent_id: str = None) -> str:
    """Return folder ID, creating it if it doesn't exist."""
    query = f"name='{name}' and mimeType='{MIME_DIR}' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"

    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])

    if files:
        return files[0]["id"]

    # Create the folder
    metadata = {"name": name, "mimeType": MIME_DIR}
    if parent_id:
        metadata["parents"] = [parent_id]

    folder = service.files().create(body=metadata, fields="id").execute()
    logger.info("[Drive] Created folder: %s", name)
    return folder["id"]


def upload_to_drive(
    portal: str,
    report_date: date,
    file_path: Path,
) -> str | None:
    """
    Upload a report file to Google Drive under:
      SolaraDashboard Reports / YYYY-MM / <Portal> / <filename>

    Args:
        portal:      Portal name, e.g. "Zepto"
        report_date: Date the report covers
        file_path:   Local path to the file

    Returns:
        Shareable Drive link (str) or None if upload failed.
    """
    if not file_path.exists():
        logger.error("[Drive] File not found: %s", file_path)
        return None

    try:
        service = _get_drive_service()

        # Build folder path: Root / YYYY-MM / Portal
        # Root: use GOOGLE_DRIVE_ROOT_FOLDER_ID env var if set, else find/create by name
        month_label = report_date.strftime("%Y-%m")
        env_root_id = os.environ.get(_ROOT_FOLDER_ID_ENV)
        root_id     = env_root_id or _get_or_create_folder(service, ROOT_FOLDER_NAME)
        month_id    = _get_or_create_folder(service, month_label, parent_id=root_id)
        portal_id   = _get_or_create_folder(service, portal, parent_id=month_id)

        # Upload file (replace if same name already exists)
        mime = MIME_XLSX if file_path.suffix == ".xlsx" else MIME_CSV
        existing = service.files().list(
            q=f"name='{file_path.name}' and '{portal_id}' in parents and trashed=false",
            fields="files(id)"
        ).execute().get("files", [])

        media = MediaFileUpload(str(file_path), mimetype=mime, resumable=False)

        if existing:
            # Update existing file
            file_id = existing[0]["id"]
            service.files().update(
                fileId=file_id,
                media_body=media,
            ).execute()
            logger.info("[Drive] Updated existing file: %s", file_path.name)
        else:
            # Create new file
            file_meta = {"name": file_path.name, "parents": [portal_id]}
            result = service.files().create(
                body=file_meta, media_body=media, fields="id"
            ).execute()
            file_id = result["id"]
            logger.info("[Drive] Uploaded new file: %s", file_path.name)

        # Make it readable by anyone with the link
        service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()

        link = f"https://drive.google.com/file/d/{file_id}/view"
        logger.info("[Drive] Shareable link: %s", link)
        return link

    except Exception as exc:
        logger.error("[Drive] Upload failed: %s", exc)
        return None


def get_month_folder_link(report_date: date) -> str | None:
    """
    Return the shareable link to the YYYY-MM folder for a given date.
    Useful for posting a single monthly folder link to Slack.
    """
    try:
        service   = _get_drive_service()
        month_label = report_date.strftime("%Y-%m")
        env_root_id = os.environ.get(_ROOT_FOLDER_ID_ENV)
        root_id   = env_root_id or _get_or_create_folder(service, ROOT_FOLDER_NAME)
        month_id  = _get_or_create_folder(service, month_label, parent_id=root_id)

        service.permissions().create(
            fileId=month_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()

        return f"https://drive.google.com/drive/folders/{month_id}"
    except Exception as exc:
        logger.error("[Drive] Could not get month folder link: %s", exc)
        return None
