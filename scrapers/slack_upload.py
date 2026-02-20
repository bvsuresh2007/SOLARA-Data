"""
Slack file upload utility for scrapers.

Uploads a downloaded report Excel to the configured Slack channel
and posts a notification message. Uses the Slack Bot Token from .env.

Usage:
    from scrapers.slack_upload import upload_report_to_slack
    from pathlib import Path
    from datetime import date

    upload_report_to_slack(
        portal="Zepto",
        report_date=date.today(),
        file_path=Path("data/raw/zepto/zepto_sales_2026-02-18.xlsx"),
    )
"""

import logging
import os
from datetime import date
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

SLACK_API_MESSAGE = "https://slack.com/api/chat.postMessage"


def post_message(text: str) -> bool:
    """Post a plain text message to the configured Slack channel."""
    token      = os.environ.get("SLACK_BOT_TOKEN")
    channel_id = os.environ.get("SLACK_CHANNEL_ID")

    if not token or not channel_id:
        logger.warning("[Slack] SLACK_BOT_TOKEN or SLACK_CHANNEL_ID not set — skipping")
        return False

    try:
        resp = requests.post(
            SLACK_API_MESSAGE,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"channel": channel_id, "text": text},
            timeout=10,
        )
        result = resp.json()
        if result.get("ok"):
            logger.info("[Slack] Message posted successfully")
            return True
        logger.error("[Slack] Message failed: %s", result.get("error"))
        return False
    except Exception as exc:
        logger.error("[Slack] Message exception: %s", exc)
        return False


def notify_monthly_folder(month_label: str, folder_url: str) -> bool:
    """Post the Google Drive monthly folder link to Slack (call on 1st of each month)."""
    text = (
        f"*SolaraDashboard Reports — {month_label}*\n"
        f"All daily sales reports for this month are stored here:\n"
        f"{folder_url}\n"
        f"_(Anyone with the link can view and download)_"
    )
    return post_message(text)


