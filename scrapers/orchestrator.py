"""
Scraping orchestrator.
Runs all portal scrapers sequentially, parses the downloaded files,
transforms the data, upserts into PostgreSQL, and sends Slack notifications.

Usage:
  python -m scrapers.orchestrator                    # Yesterday's data
  python -m scrapers.orchestrator --date 2026-02-08  # Specific date
"""
import argparse
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

# Ensure project root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
load_dotenv()

from scrapers.swiggy_scraper   import SwiggyScraper
from scrapers.blinkit_scraper  import BlinkitScraper
from scrapers.amazon_scraper   import AmazonScraper
from scrapers.zepto_scraper    import ZeptoScraper
from scrapers.shopify_scraper  import ShopifyScraper
from scrapers.excel_parser     import get_parser
from scrapers.data_transformer import DataTransformer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("orchestrator")


SCRAPERS = [
    SwiggyScraper,
    BlinkitScraper,
    AmazonScraper,
    ZeptoScraper,
    ShopifyScraper,
]


def _get_db():
    from backend.app.database import SessionLocal
    return SessionLocal()


def _upsert_sales(db, rows: list[dict]) -> int:
    from sqlalchemy.dialects.postgresql import insert
    from backend.app.models.sales import CityDailySales
    if not rows:
        return 0
    stmt = insert(CityDailySales).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["portal_id", "product_id", "city_id", "sale_date"],
        set_={
            "units_sold": stmt.excluded.units_sold,
            "revenue": stmt.excluded.revenue,
            "discount_amount": stmt.excluded.discount_amount,
            "net_revenue": stmt.excluded.net_revenue,
            "order_count": stmt.excluded.order_count,
        },
    )
    db.execute(stmt)
    db.commit()
    return len(rows)


def _upsert_daily_sales(db, city_rows: list[dict]) -> int:
    """
    Aggregate city-level sales rows to (portal_id, product_id, sale_date) grain
    and upsert into daily_sales. This is the table the dashboard reads from.
    """
    from collections import defaultdict
    from sqlalchemy.dialects.postgresql import insert
    from backend.app.models.sales import DailySales
    if not city_rows:
        return 0

    agg: dict[tuple, dict] = defaultdict(lambda: {"units_sold": 0.0, "revenue": 0.0})
    for row in city_rows:
        key = (row["portal_id"], row["product_id"], row["sale_date"])
        agg[key]["units_sold"] += float(row.get("units_sold", 0) or 0)
        agg[key]["revenue"]    += float(row.get("revenue", 0) or 0)

    daily_rows = []
    for (portal_id, product_id, sale_date), totals in agg.items():
        units   = totals["units_sold"]
        revenue = totals["revenue"]
        asp     = round(revenue / units, 2) if units > 0 else None
        daily_rows.append({
            "portal_id":   portal_id,
            "product_id":  product_id,
            "sale_date":   sale_date,
            "units_sold":  units,
            "revenue":     revenue,
            "asp":         asp,
            "data_source": "portal_scraper",
        })

    stmt = insert(DailySales).values(daily_rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["portal_id", "product_id", "sale_date"],
        set_={
            "units_sold":  stmt.excluded.units_sold,
            "revenue":     stmt.excluded.revenue,
            "asp":         stmt.excluded.asp,
            "data_source": stmt.excluded.data_source,
        },
    )
    db.execute(stmt)
    db.commit()
    return len(daily_rows)


def _upsert_inventory(db, rows: list[dict]) -> int:
    from sqlalchemy.dialects.postgresql import insert
    from backend.app.models.inventory import InventorySnapshot
    if not rows:
        return 0
    stmt = insert(InventorySnapshot).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["portal_id", "product_id", "snapshot_date"],
        set_={
            "portal_stock":    stmt.excluded.portal_stock,
            "backend_stock":   stmt.excluded.backend_stock,
            "frontend_stock":  stmt.excluded.frontend_stock,
            "solara_stock":    stmt.excluded.solara_stock,
            "amazon_fc_stock": stmt.excluded.amazon_fc_stock,
            "open_po":         stmt.excluded.open_po,
            "doc":             stmt.excluded.doc,
        },
    )
    db.execute(stmt)
    db.commit()
    return len(rows)


def _log_scrape(db, portal_name: str, scrape_date: date, status: str, records: int, error: str = None):
    from backend.app.models.inventory import ImportLog
    from backend.app.models.metadata import Portal
    portal = db.query(Portal).filter_by(name=portal_name).first()
    log = ImportLog(
        source_type="portal_scraper",
        portal_id=portal.id if portal else None,
        import_date=scrape_date,
        status=status,
        records_imported=records,
        error_message=error,
        end_time=datetime.now(),
    )
    db.add(log)
    db.commit()


def populate_portal_data(
    portal_name: str,
    report_date: date,
    data_dir: Path = None,
) -> dict:
    """
    Parse downloaded file(s) for a portal and upsert into Postgres.

    Returns a dict with keys: status, records_imported, error, file(s).
    Status values: "success", "failed", "no_parser", "no_file".

    DB failures do NOT raise — the caller should log the result and continue.
    """
    if data_dir is None:
        data_dir = Path("./data/raw")
    data_dir = Path(data_dir)

    # --- Auto-detect file(s) ---
    portal_dir = data_dir / portal_name
    if portal_name == "amazon_pi":
        date_dir = portal_dir / report_date.strftime("%Y-%m-%d")
        files = sorted(date_dir.glob("*.xlsx")) if date_dir.exists() else []
    else:
        files = sorted(portal_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
        files = [f for f in files if f.is_file() and f.suffix.lower() in (".csv", ".xlsx", ".xls")]
        files = files[:1]  # latest only

    if not files:
        logger.warning("[%s] No files found in %s", portal_name, portal_dir)
        return {"status": "no_file", "records_imported": 0, "error": f"No files in {portal_dir}"}

    # --- Get parser ---
    try:
        parser = get_parser(portal_name)
    except ValueError as exc:
        logger.warning("[%s] %s", portal_name, exc)
        return {"status": "no_parser", "records_imported": 0, "error": str(exc)}

    db = _get_db()
    transformer = DataTransformer(db)
    total_records = 0
    error_msg = None

    try:
        for file in files:
            logger.info("[%s] Parsing %s", portal_name, file.name)

            sales_rows = parser.parse_sales(file)
            transformed_sales = transformer.transform_sales_rows(sales_rows)
            total_records += _upsert_sales(db, transformed_sales)
            total_records += _upsert_daily_sales(db, transformed_sales)

            if hasattr(parser, "parse_inventory"):
                inv_rows = parser.parse_inventory(file)
                transformed_inv = transformer.transform_inventory_rows(inv_rows)
                total_records += _upsert_inventory(db, transformed_inv)

        _log_scrape(db, portal_name, report_date, "success", total_records)
        logger.info("[%s] DB populate success — %d records", portal_name, total_records)
        return {"status": "success", "records_imported": total_records, "files": [str(f) for f in files]}

    except Exception as exc:
        error_msg = str(exc)
        logger.error("[%s] DB populate failed: %s", portal_name, error_msg, exc_info=True)
        try:
            _log_scrape(db, portal_name, report_date, "failed", total_records, error_msg)
        except Exception:
            pass
        return {"status": "failed", "records_imported": total_records, "error": error_msg}

    finally:
        db.close()


def run(report_date: date):
    logger.info("=" * 60)
    logger.info("SolaraDashboard Orchestrator — %s", report_date)
    logger.info("=" * 60)

    results = []
    db = _get_db()
    transformer = DataTransformer(db)

    for ScraperClass in SCRAPERS:
        scraper = ScraperClass()
        result = scraper.run(report_date)
        total_records = 0

        if result["status"] == "success" and result.get("file"):
            try:
                parser = get_parser(scraper.portal_name)

                # Parse & upsert sales
                sales_rows = parser.parse_sales(result["file"])
                transformed_sales = transformer.transform_sales_rows(sales_rows)
                total_records += _upsert_sales(db, transformed_sales)

                # Parse & upsert inventory (if supported)
                if hasattr(parser, "parse_inventory"):
                    inv_rows = parser.parse_inventory(result["file"])
                    transformed_inv = transformer.transform_inventory_rows(inv_rows)
                    total_records += _upsert_inventory(db, transformed_inv)

            except Exception as exc:
                logger.error("[%s] Data processing failed: %s", scraper.portal_name, exc)
                result["status"] = "partial"
                result["error"] = str(exc)

        _log_scrape(db, scraper.portal_name, report_date, result["status"], total_records, result.get("error"))
        result["records"] = total_records
        results.append(result)
        logger.info("[%s] %s — %d records", scraper.portal_name, result["status"], total_records)

    db.close()

    # Slack notification — daily summary
    try:
        from backend.app.utils.slack import notify_scraping_complete
        notify_scraping_complete(report_date, results)
    except Exception as exc:
        logger.warning("Slack notification failed: %s", exc)

    # On the 1st of each month, post the Drive reports folder link
    if report_date.day == 1:
        folder_url = os.environ.get("REPORTS_DRIVE_FOLDER_URL", "")
        if folder_url:
            try:
                from backend.app.utils.slack import notify_monthly_drive_folder
                notify_monthly_drive_folder(report_date.strftime("%B %Y"), folder_url)
            except Exception as exc:
                logger.warning("Monthly Drive folder notification failed: %s", exc)

    logger.info("Orchestrator complete. Total portals: %d", len(results))
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SolaraDashboard Scraping Orchestrator")
    parser.add_argument("--date", type=str, help="Report date (YYYY-MM-DD). Defaults to yesterday.")
    args = parser.parse_args()

    if args.date:
        report_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        report_date = date.today().__class__.today() - __import__("datetime").timedelta(days=1)

    run(report_date)
