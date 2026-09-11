"""
Pre-create Amazon Data Kiosk inventory query.

Run at 2 AM via Task Scheduler — by DailyRun time (11 AM+),
the query is DONE and inventory sync just downloads the result (~15s).

Saves the query ID to a JSON file that amazon_inventory_sync.py reads.

Usage:
    python -m scrapers.amazon_inventory_precreate              # auto (today - 2)
    python -m scrapers.amazon_inventory_precreate 2026-04-07   # specific date
"""

import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("scrapers.amazon_inventory_precreate")

# Task Scheduler discards stderr, so also log to a file - otherwise the nightly
# failures are invisible (observed: LastTaskResult=1 with no log anywhere).
_LOG_DIR = Path("data/logs")
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_fh = logging.FileHandler(_LOG_DIR / "inventory_precreate.log", encoding="utf-8")
_fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s"))
logger.addHandler(_fh)

QUERY_STATE_FILE = Path("data/raw/amazon_sp_api/.inventory_query_state.json")


def precreate(report_date: date | str | None = None):
    """Create the Data Kiosk query and save query ID + date to state file."""
    try:
        if report_date is None:
            report_date = date.today() - timedelta(days=2)
        if isinstance(report_date, str):
            report_date = date.fromisoformat(report_date)

        from scrapers.amazon_sp_api_scraper import AmazonSPAPIScraper

        scraper = AmazonSPAPIScraper()
        query = scraper._build_sales_query(report_date, report_date)

        logger.info("Pre-creating Data Kiosk query for %s", report_date)
        query_id = scraper._create_query(query)
        logger.info("Query submitted: %s for date %s", query_id, report_date)

        # Save state
        QUERY_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "query_id": query_id,
            "report_date": report_date.isoformat(),
            "created_at": date.today().isoformat(),
            "status": "submitted",
        }
        QUERY_STATE_FILE.write_text(json.dumps(state, indent=2))
        logger.info("Saved query state to %s", QUERY_STATE_FILE)

        return state
    except Exception:
        # Task Scheduler discards stderr, so without this the nightly failures are
        # invisible (observed LastTaskResult=1 with no log). Record the full
        # traceback, then re-raise so the task still exits non-zero.
        logger.exception("Pre-create FAILED for report_date=%s", report_date)
        raise


if __name__ == "__main__":
    d = None
    if len(sys.argv) > 1:
        d = sys.argv[1]
    result = precreate(d)
    print(result)
