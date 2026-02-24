"""
Monthly Drive folder setup script.

Run on the 1st of each month to:
  1. Create the YYYY-MM folder under SolaraDashboard Reports in Google Drive
  2. Create one subfolder per active portal
  3. Post the folder link to Slack

Called by .github/workflows/monthly-drive-setup.yml.
Can also be run manually:
    python scripts/setup_monthly_drive_folder.py
    python scripts/setup_monthly_drive_folder.py --month 2026-03
"""
import argparse
import logging
import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Portal display names — must match the folder names used by upload_to_drive()
PORTAL_FOLDERS = [
    "EasyEcom",
    "Zepto",
    "Blinkit",
    "Amazon PI",
    "Swiggy",
    "Myntra",
    "Flipkart",
    "Shopify",
]


def main(target_date: date = None) -> None:
    from scrapers.google_drive_upload import setup_monthly_folders
    from backend.app.utils.slack import notify_monthly_drive_folder

    result = setup_monthly_folders(portals=PORTAL_FOLDERS, target_date=target_date)
    if result is None:
        logger.error("Drive folder setup failed.")
        sys.exit(1)

    folder_url, month_label = result
    logger.info("Folder URL: %s", folder_url)

    try:
        notify_monthly_drive_folder(month_label=month_label, folder_url=folder_url)
        logger.info("Slack notification sent.")
    except Exception as exc:
        logger.warning("Slack notification failed (non-fatal): %s", exc)

    print(folder_url)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Set up monthly Google Drive folder")
    parser.add_argument(
        "--month",
        help="Target month as YYYY-MM (defaults to current month)",
        default=None,
    )
    args = parser.parse_args()

    target = None
    if args.month:
        target = datetime.strptime(args.month, "%Y-%m").date()

    main(target_date=target)
