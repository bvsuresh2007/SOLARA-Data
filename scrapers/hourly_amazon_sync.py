"""
Hourly Amazon SP-API Real-Time Sales Sync

Pulls the latest hourly sales data via GET_VENDOR_REAL_TIME_SALES_REPORT,
aggregates to daily per ASIN (IST-aligned), and upserts into daily_sales.

Designed to be run every hour via cron/Task Scheduler.

Usage:
    python -m scrapers.hourly_amazon_sync              # today (IST)
    python -m scrapers.hourly_amazon_sync 2026-03-31   # specific date
"""

import logging
import sys
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("scrapers.hourly_amazon_sync")


def sync(report_date: date | str | None = None):
    if report_date is None:
        report_date = date.today()
    if isinstance(report_date, str):
        report_date = date.fromisoformat(report_date)

    logger.info("=== Hourly Amazon sync for %s ===", report_date)

    # Step 1: Pull real-time sales
    from scrapers.amazon_sp_api_scraper import AmazonSPAPIScraper
    scraper = AmazonSPAPIScraper()
    result = scraper.run(report_date)

    if result["status"] != "success":
        logger.error("SP-API pull failed: %s", result.get("error"))
        return result

    logger.info("SP-API: %d ASINs, %d units, INR %.1fL",
                result["rows"], result.get("total_units", 0),
                result.get("total_revenue", 0) / 100_000)

    # Step 2: Ingest into DB
    from ingest_daily import ingest_amazon_sp_api
    ingest_amazon_sp_api(report_date)

    logger.info("=== Hourly sync complete for %s ===", report_date)
    return result


if __name__ == "__main__":
    d = None
    if len(sys.argv) > 1:
        d = sys.argv[1]
    sync(d)
