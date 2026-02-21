"""
One-time setup: create the "SolaraDashboard Profiles" Google Drive folder.

This folder lives at the root of My Drive, separate from "SolaraDashboard Reports".
It stores browser profile ZIPs (blinkit_profile.zip, easyecom_profile.zip, …)
so that scrapers running on CI can download the authenticated profile, use it,
and upload the refreshed profile back.

Run once:
    python scripts/setup_profiles_drive_folder.py

Then copy the printed folder ID into your .env file:
    PROFILE_STORAGE_DRIVE_FOLDER_ID=<id>
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

PROFILES_FOLDER_NAME = "SolaraDashboard Profiles"


def main() -> str:
    from scrapers.google_drive_upload import _get_drive_service

    logger.info("Connecting to Google Drive…")
    service = _get_drive_service()

    # Check whether the folder already exists at the root of My Drive
    results = (
        service.files()
        .list(
            q=(
                f"name='{PROFILES_FOLDER_NAME}' "
                f"and mimeType='application/vnd.google-apps.folder' "
                f"and 'root' in parents "
                f"and trashed=false"
            ),
            fields="files(id, name)",
            spaces="drive",
        )
        .execute()
        .get("files", [])
    )

    if results:
        folder_id = results[0]["id"]
        logger.info("Folder already exists — reusing it.")
    else:
        meta = {
            "name": PROFILES_FOLDER_NAME,
            "mimeType": "application/vnd.google-apps.folder",
        }
        folder = service.files().create(body=meta, fields="id").execute()
        folder_id = folder["id"]
        logger.info("Created new folder: %s", PROFILES_FOLDER_NAME)

    folder_url = f"https://drive.google.com/drive/folders/{folder_id}"

    print("\n" + "=" * 60)
    print(f"  Drive folder : {folder_url}")
    print(f"  Folder ID   : {folder_id}")
    print("=" * 60)
    print("\nAdd this line to your .env file:\n")
    print(f"  PROFILE_STORAGE_DRIVE_FOLDER_ID={folder_id}")
    print()

    return folder_id


if __name__ == "__main__":
    main()
