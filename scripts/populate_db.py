"""
CLI: populate Postgres from a locally downloaded scraper file.

Usage:
  python scripts/populate_db.py --portal swiggy
  python scripts/populate_db.py --portal amazon_pi --date 2026-02-24
  python scripts/populate_db.py --portal easyecom --date 2026-02-24 --data-dir ./data/raw
"""
import argparse
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)


def main():
    parser = argparse.ArgumentParser(description="Populate Postgres DB from downloaded scraper data")
    parser.add_argument("--portal", required=True, help="Portal name (swiggy, blinkit, zepto, easyecom, amazon_pi)")
    parser.add_argument("--date", dest="report_date", default="", help="Report date YYYY-MM-DD (default: yesterday)")
    parser.add_argument("--data-dir", default="./data/raw", help="Root data directory (default: ./data/raw)")
    args = parser.parse_args()

    if args.report_date:
        report_date = datetime.strptime(args.report_date, "%Y-%m-%d").date()
    else:
        report_date = date.today() - timedelta(days=1)

    from scrapers.orchestrator import populate_portal_data
    result = populate_portal_data(
        portal_name=args.portal,
        report_date=report_date,
        data_dir=Path(args.data_dir),
    )

    msg = f"DB populate result: {result}"
    if result["status"] == "failed":
        msg += "\nWARNING: DB populate failed but scraper data is in Drive. See import_logs for details."

    # stdout can sometimes be closed by Windows/SQLAlchemy atexit handlers; fall back to stderr
    try:
        print(msg)
        sys.stdout.flush()
    except (ValueError, OSError):
        sys.stderr.write(msg + "\n")
        sys.stderr.flush()


if __name__ == "__main__":
    main()
