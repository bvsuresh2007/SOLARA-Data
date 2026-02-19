"""
Slack integration for posting scraper results.
"""

import json
import os
from typing import Optional

import requests

from src.scraper import ProductData

# Config file to store webhook URL
CONFIG_FILE = "slack_config.json"


def save_webhook(webhook_url: str) -> None:
    """Save Slack webhook URL to config file."""
    with open(CONFIG_FILE, "w") as f:
        json.dump({"webhook_url": webhook_url}, f)
    print(f"Slack webhook saved to {CONFIG_FILE}")


def load_webhook() -> Optional[str]:
    """Load Slack webhook URL from config file."""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
            return config.get("webhook_url")
    return None


def format_message(results: list[ProductData], seller_filter: str = None) -> str:
    """Format results into a Slack message."""
    successful = [r for r in results if not r.error and r.price]
    failed = [r for r in results if r.error]

    lines = []
    lines.append("*ASIN Scraper Report*")
    lines.append(f"Total: {len(results)} | Success: {len(successful)} | Failed: {len(failed)}")
    lines.append("")

    if seller_filter:
        matched = [r for r in successful if r.seller and seller_filter.lower() in r.seller.lower()]
        lines.append(f"*Seller Filter:* `{seller_filter}` — {len(matched)} matched")
        lines.append("")

    # Table header
    lines.append("```")
    lines.append(f"{'ASIN':<12} {'Price':>10} {'Main BSR':>10} {'Sub BSR':>10}")
    lines.append("-" * 50)

    for r in successful:
        price = r.price or "N/A"
        main_bsr = f"#{r.bsr_value:,}" if r.bsr_value else "N/A"
        sub_bsr = f"#{r.sub_bsr_value:,}" if r.sub_bsr_value else "-"
        lines.append(f"{r.asin:<12} {price:>10} {main_bsr:>10} {sub_bsr:>10}")

    lines.append("```")

    if failed:
        lines.append(f"\n*Failed ({len(failed)}):*")
        for r in failed:
            lines.append(f"  `{r.asin}` — {r.error}")

    return "\n".join(lines)


def post_to_slack(webhook_url: str, results: list[ProductData],
                  csv_path: str = None, seller_filter: str = None) -> bool:
    """
    Post scraper results to Slack.

    Args:
        webhook_url: Slack incoming webhook URL
        results: List of ProductData results
        csv_path: Path to CSV file (mentioned in message)
        seller_filter: Seller name filter applied

    Returns:
        True if posted successfully
    """
    message = format_message(results, seller_filter)

    if csv_path:
        message += f"\n\nCSV saved: `{csv_path}`"

    payload = {"text": message}

    try:
        response = requests.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        if response.status_code == 200:
            print("Results posted to Slack successfully!")
            return True
        else:
            print(f"Slack error: {response.status_code} - {response.text}")
            return False
    except requests.RequestException as e:
        print(f"Failed to post to Slack: {e}")
        return False


def upload_file_to_slack(token: str, channel: str, filepath: str, message: str = "") -> bool:
    """
    Upload a file to Slack using Bot token (optional, requires bot token).

    Args:
        token: Slack Bot OAuth token
        channel: Channel ID
        filepath: Path to file to upload
        message: Initial comment

    Returns:
        True if uploaded successfully
    """
    try:
        with open(filepath, "rb") as f:
            response = requests.post(
                "https://slack.com/api/files.upload",
                headers={"Authorization": f"Bearer {token}"},
                data={"channels": channel, "initial_comment": message},
                files={"file": f},
                timeout=30
            )
            result = response.json()
            if result.get("ok"):
                print("CSV file uploaded to Slack!")
                return True
            else:
                print(f"Slack upload error: {result.get('error')}")
                return False
    except Exception as e:
        print(f"Failed to upload to Slack: {e}")
        return False
