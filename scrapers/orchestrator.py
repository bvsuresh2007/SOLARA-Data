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

# Ensure project root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

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
    from backend.app.models.sales import SalesData
    if not rows:
        return 0
    stmt = insert(SalesData).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["portal_id", "city_id", "product_id", "sale_date"],
        set_={
            "quantity_sold": stmt.excluded.quantity_sold,
            "revenue": stmt.excluded.revenue,
            "discount_amount": stmt.excluded.discount_amount,
            "net_revenue": stmt.excluded.net_revenue,
            "order_count": stmt.excluded.order_count,
        },
    )
    db.execute(stmt)
    db.commit()
    return len(rows)


def _upsert_inventory(db, rows: list[dict]) -> int:
    from sqlalchemy.dialects.postgresql import insert
    from backend.app.models.inventory import InventoryData
    if not rows:
        return 0
    stmt = insert(InventoryData).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["portal_id", "warehouse_id", "product_id", "snapshot_date"],
        set_={
            "stock_quantity": stmt.excluded.stock_quantity,
            "available_quantity": stmt.excluded.available_quantity,
            "reserved_quantity": stmt.excluded.reserved_quantity,
        },
    )
    db.execute(stmt)
    db.commit()
    return len(rows)


def _log_scrape(db, portal_name: str, scrape_date: date, status: str, records: int, error: str = None):
    from backend.app.models.inventory import ScrapingLog
    from backend.app.models.metadata import Portal
    portal = db.query(Portal).filter_by(name=portal_name).first()
    log = ScrapingLog(
        portal_id=portal.id if portal else None,
        scrape_date=scrape_date,
        status=status,
        records_processed=records,
        error_message=error,
        end_time=datetime.now(),
    )
    db.add(log)
    db.commit()


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

    # Slack notification
    try:
        from backend.app.utils.slack import notify_scraping_complete
        notify_scraping_complete(report_date, results)
    except Exception as exc:
        logger.warning("Slack notification failed: %s", exc)

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
