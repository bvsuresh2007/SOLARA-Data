"""
Daily Amazon Inventory & Open PO Sync via SP-API Data Kiosk

Two modes:
  1. FAST (pre-created query): If amazon_inventory_precreate.py ran earlier
     (e.g. at 2 AM via Task Scheduler), the query is already DONE.
     We just download the result — takes ~15 seconds.
  2. SLOW (fallback): If no pre-created query exists, creates a new query
     and polls until complete — takes 15-30 minutes.

Run once daily — inventory data doesn't need real-time updates.
Uses date = 2 days ago by default (Data Kiosk lag).

Usage:
    python -m scrapers.amazon_inventory_sync              # auto (today - 2)
    python -m scrapers.amazon_inventory_sync 2026-03-29   # specific date
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
logger = logging.getLogger("scrapers.amazon_inventory_sync")

QUERY_STATE_FILE = Path("data/raw/amazon_sp_api/.inventory_query_state.json")


def _load_precreated_query(report_date: date) -> str | None:
    """Check if a pre-created query exists for this date. Returns query_id or None."""
    if not QUERY_STATE_FILE.exists():
        return None

    try:
        state = json.loads(QUERY_STATE_FILE.read_text())
        if state.get("report_date") == report_date.isoformat():
            query_id = state.get("query_id")
            logger.info("Found pre-created query %s for %s", query_id, report_date)
            return query_id
        else:
            logger.info("Pre-created query is for %s, not %s — will create new",
                        state.get("report_date"), report_date)
            return None
    except Exception as e:
        logger.warning("Failed to read query state file: %s", e)
        return None


def _cleanup_state_file():
    """Remove the state file after successful download."""
    try:
        if QUERY_STATE_FILE.exists():
            QUERY_STATE_FILE.unlink()
    except Exception:
        pass


def sync(report_date: date | str | None = None):
    if report_date is None:
        # Data Kiosk has ~34h lag, so default to 2 days ago
        report_date = date.today() - timedelta(days=2)
    if isinstance(report_date, str):
        report_date = date.fromisoformat(report_date)

    logger.info("=== Amazon Inventory/Open PO sync for %s ===", report_date)

    from scrapers.amazon_sp_api_scraper import AmazonSPAPIScraper
    scraper = AmazonSPAPIScraper()

    # Check for pre-created query first (fast path)
    precreated_id = _load_precreated_query(report_date)

    if precreated_id:
        # Fast path: just poll (should be DONE already) and download
        logger.info("Using pre-created query %s (fast path)", precreated_id)
        try:
            result_data = scraper._poll_query(precreated_id, max_polls=20, interval=15)
            doc_id = result_data.get("dataDocumentId")
            if doc_id:
                content = scraper._download_document(doc_id)
                rows = scraper._parse_datakiosk_response(content)
                logger.info("Fast path: %d ASINs from pre-created query", len(rows))
                _cleanup_state_file()
                return _save_and_ingest(scraper, rows, report_date)
            else:
                logger.warning("Pre-created query has no dataDocumentId, falling back")
        except TimeoutError:
            logger.warning("Pre-created query not ready after 20 polls, falling back to new query")
        except Exception as e:
            logger.warning("Pre-created query failed: %s, falling back", e)

    # Slow path: create new query from scratch
    logger.info("Creating new Data Kiosk query (slow path ~15-30 min)")
    result = scraper.pull_inventory(report_date)

    if result["status"] != "success":
        logger.error("Inventory pull failed: %s", result)
        return result

    logger.info("Inventory: %d ASINs (%d with stock, %d with open PO), "
                "%d SOH units, %d open PO units",
                result["asins"], result["with_stock"], result["with_open_po"],
                result["total_soh"], result["total_open_po"])

    # Ingest into DB
    from ingest_daily import ingest_amazon_inventory
    ingest_amazon_inventory(report_date)

    _cleanup_state_file()
    logger.info("=== Inventory sync complete for %s ===", report_date)
    return result


def _save_and_ingest(scraper, rows, report_date):
    """Save CSV and ingest into DB (used by fast path)."""
    import csv
    from pathlib import Path

    RAW_DIR = Path("data/raw/amazon_sp_api")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / f"amazon_inventory_{report_date}.csv"
    headers = ["date", "asin", "product_title", "sellable_on_hand",
               "soh_value", "open_po_qty"]

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for r in rows:
            writer.writerow({h: r.get(h, 0) for h in headers})

    total_soh = sum(r["sellable_on_hand"] for r in rows)
    total_po = sum(r["open_po_qty"] for r in rows)
    with_stock = sum(1 for r in rows if r["sellable_on_hand"] > 0)
    with_po = sum(1 for r in rows if r["open_po_qty"] > 0)

    logger.info("Inventory saved: %d ASINs (%d with stock, %d with open PO), "
                "%d SOH units, %d open PO units → %s",
                len(rows), with_stock, with_po, total_soh, total_po, out_path)

    # Ingest into DB
    from ingest_daily import ingest_amazon_inventory
    ingest_amazon_inventory(report_date)

    logger.info("=== Inventory sync complete for %s ===", report_date)

    return {
        "portal": "amazon_sp_api",
        "date": report_date,
        "type": "inventory",
        "file": str(out_path),
        "status": "success",
        "source": "precreated_query",
        "asins": len(rows),
        "with_stock": with_stock,
        "with_open_po": with_po,
        "total_soh": total_soh,
        "total_open_po": total_po,
    }


if __name__ == "__main__":
    d = None
    if len(sys.argv) > 1:
        d = sys.argv[1]
    sync(d)
