"""
Atlas Main-Warehouse Stock Sync  →  WH Stock column on the dashboard.

Pulls live physical stock (Bin.actual_qty) for "Main Warehouse - WTBBPL" from
Atlas (ERPNext) and upserts it into inventory_snapshots.solara_stock for the
EasyEcom portal — the exact slot the dashboard's "WH Stock" column reads
(backend/app/api/sales.py builds inv_map from the latest solara_stock per
product for the EasyEcom portal).

This REPLACES the old EasyecomInventoryScraper as the WH-Stock source: Atlas
Main Warehouse actual_qty is the authoritative on-hand figure, vs EasyEcom's
lagging 'old_quantity' snapshot. No backend/frontend change needed — same
table/column/conflict-target, just a better-sourced number.

Run as part of the daily run (after sales scrapers, any time — it's API-only,
no browser, no Chrome-profile contention):

    python -m scrapers.atlas_wh_stock_sync               # stamp today's date
    python -m scrapers.atlas_wh_stock_sync 2026-06-18    # stamp a specific dailyrun date
"""

import os
import sys
import json
import logging
from datetime import date

import requests
from dotenv import load_dotenv
from sqlalchemy.dialects.postgresql import insert as pg_insert

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("scrapers.atlas_wh_stock_sync")

WAREHOUSE = "Main Warehouse - WTBBPL"
QTY_FIELD = "actual_qty"          # physical on-hand; see module docstring
PORTAL_NAME = "easyecom"          # solara_stock is read for this portal by the dashboard


def _atlas_headers() -> dict:
    key = os.environ.get("ERPNEXT_API_KEY", "")
    sec = os.environ.get("ERPNEXT_API_SECRET", "")
    if not (key and sec):
        raise RuntimeError("ERPNEXT_API_KEY / ERPNEXT_API_SECRET not set in .env")
    return {"Authorization": f"token {key}:{sec}"}


def fetch_main_wh_stock() -> dict[str, float]:
    """Return {item_code: actual_qty} for every Bin row in Main Warehouse."""
    url = os.environ.get("ERPNEXT_URL", "").rstrip("/")
    if not url:
        raise RuntimeError("ERPNEXT_URL not set in .env")

    params = {
        "filters": json.dumps([["warehouse", "=", WAREHOUSE]]),
        "fields": json.dumps(["item_code", QTY_FIELD]),
        "limit_page_length": 0,   # 0 = return all rows
    }
    r = requests.get(f"{url}/api/resource/Bin", headers=_atlas_headers(), params=params, timeout=60)
    r.raise_for_status()
    data = r.json().get("data", [])
    stock = {}
    for row in data:
        sku = (row.get("item_code") or "").strip()
        if not sku:
            continue
        qty = row.get(QTY_FIELD)
        stock[sku] = float(qty) if qty is not None else 0.0
    logger.info("Fetched %d Bin rows from '%s'", len(stock), WAREHOUSE)
    return stock


def sync(report_date: date | str | None = None) -> dict:
    if report_date is None:
        report_date = date.today()
    if isinstance(report_date, str):
        report_date = date.fromisoformat(report_date)

    logger.info("=== Atlas Main-WH stock sync for %s ===", report_date)

    stock = fetch_main_wh_stock()
    if not stock:
        logger.warning("No Bin rows returned — aborting (no write)")
        return {"status": "no_data", "date": report_date, "rows": 0}

    from backend.app.database import SessionLocal
    from backend.app.models.inventory import InventorySnapshot
    from backend.app.models.metadata import Portal
    from backend.app.models.sales import Product

    db = SessionLocal()
    try:
        portal = db.query(Portal).filter_by(name=PORTAL_NAME).first()
        if not portal:
            logger.error("'%s' portal not found in DB — aborting", PORTAL_NAME)
            return {"status": "error", "date": report_date, "rows": 0,
                    "error": f"portal '{PORTAL_NAME}' not found"}
        portal_id = portal.id

        # Map item_code (SKU) → product_id
        prods = db.query(Product.id, Product.sku_code).filter(
            Product.sku_code.in_(list(stock.keys()))
        ).all()
        sku_to_pid = {p.sku_code: p.id for p in prods}
        matched = len(sku_to_pid)
        logger.info("Matched %d / %d Main-WH SKUs to product_ids", matched, len(stock))

        unmatched = [s for s in stock if s not in sku_to_pid]
        if unmatched:
            logger.info("Unmatched SKUs (not in products table, skipped): %d e.g. %s",
                        len(unmatched), unmatched[:10])

        rows = []
        for sku, pid in sku_to_pid.items():
            rows.append({
                "portal_id":     portal_id,
                "product_id":    pid,
                "snapshot_date": report_date,
                "solara_stock":  stock[sku],
            })
        if not rows:
            logger.warning("No SKUs matched products — nothing to upsert")
            return {"status": "no_match", "date": report_date, "rows": 0}

        BATCH = 500
        for i in range(0, len(rows), BATCH):
            batch = rows[i:i + BATCH]
            stmt = pg_insert(InventorySnapshot).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=["portal_id", "product_id", "snapshot_date"],
                set_={"solara_stock": stmt.excluded.solara_stock},
            )
            db.execute(stmt)
        db.commit()

        total_units = sum(r["solara_stock"] for r in rows)
        logger.info("Upserted %d WH-stock rows (%.0f total units) for %s",
                    len(rows), total_units, report_date)
        logger.info("=== Atlas Main-WH stock sync complete ===")
        return {
            "status": "success",
            "date": report_date,
            "rows": len(rows),
            "matched": matched,
            "fetched": len(stock),
            "total_units": total_units,
        }
    except Exception as exc:
        db.rollback()
        logger.exception("DB upsert failed")
        return {"status": "error", "date": report_date, "rows": 0, "error": str(exc)}
    finally:
        db.close()


if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else None
    result = sync(d)
    print(f"ATLAS_WH_STOCK_RESULT: {result}")
