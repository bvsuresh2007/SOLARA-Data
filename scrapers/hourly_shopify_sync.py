"""
Hourly Shopify Sales Sync

Pulls today's orders via Shopify REST API, saves CSV, and upserts into
daily_sales + city_daily_sales.

Designed to be run every hour via Task Scheduler.

Usage:
    python -m scrapers.hourly_shopify_sync              # today (IST)
    python -m scrapers.hourly_shopify_sync 2026-04-05   # specific date
"""

import logging
import os
import sys
from datetime import date
from dotenv import load_dotenv

load_dotenv()

# Ensure store URL is set (fallback for .env with old placeholder)
if os.environ.get("SHOPIFY_STORE_URL", "").startswith("your-"):
    os.environ["SHOPIFY_STORE_URL"] = "dev-solara.myshopify.com"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("scrapers.hourly_shopify_sync")


def sync(report_date: date | str | None = None):
    if report_date is None:
        report_date = date.today()
    if isinstance(report_date, str):
        report_date = date.fromisoformat(report_date)

    logger.info("=== Hourly Shopify sync for %s ===", report_date)

    # Step 1: Pull orders via API
    from scrapers.shopify_scraper import ShopifyScraper
    scraper = ShopifyScraper()
    result = scraper.run(report_date)

    if result["status"] != "success":
        logger.error("Shopify pull failed: %s", result.get("error"))
        return result

    logger.info("Shopify: %d orders, %d line items",
                result.get("orders", 0), result.get("records", 0))

    if result.get("records", 0) == 0:
        logger.info("No line items — skipping DB ingest")
        return result

    # Step 2: Ingest into DB
    from ingest_daily import ingest
    csv_path = f"data/raw/shopify/shopify_sales_{report_date}.csv"
    ingest("shopify", csv_path)

    logger.info("=== Hourly Shopify sync complete for %s ===", report_date)
    return result


if __name__ == "__main__":
    dt = sys.argv[1] if len(sys.argv) > 1 else None
    sync(dt)
