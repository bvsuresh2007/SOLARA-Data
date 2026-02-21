"""
Phase 2: Import daily sales, inventory, targets, and ad spend from the master Excel.
Populates:
  - daily_sales
  - inventory_snapshots
  - monthly_targets  (Amazon only)
  - monthly_ad_spend

All operations use upsert — safe to re-run.
New monthly Excel files can be added at any time; old data is not disturbed.

Usage:
    python scripts/import_excel_sales.py --file "data/source/SOLARA - Daily Sales Tracking FY 25-26.xlsx"
"""
import argparse
import logging
import math
import os
import sys
from datetime import datetime, date

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.db_utils import (
    get_session,
    get_portal_id,
    get_product_id_by_sku,
    upsert,
    log_import,
)
from scripts.excel_reader import (
    iter_sheets,
    get_snapshot_date,
    clean_sku,
    _float,
    SheetData,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

TODAY = datetime.today().date()


# ---------------------------------------------------------------------------
# Model stubs for upsert (use table name strings)
# ---------------------------------------------------------------------------

from sqlalchemy import Table, MetaData
from scripts.db_utils import engine

_metadata = MetaData()
_metadata.reflect(bind=engine, only=["daily_sales", "inventory_snapshots", "monthly_targets", "monthly_ad_spend"])

DailySalesTable       = _metadata.tables["daily_sales"]
InventoryTable        = _metadata.tables["inventory_snapshots"]
MonthlyTargetsTable   = _metadata.tables["monthly_targets"]
MonthlyAdSpendTable   = _metadata.tables["monthly_ad_spend"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _nan_none(v) -> float | None:
    """Convert NaN/NaT/None/string-nan to None, else return float."""
    f = _float(v)
    if f is None:
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _round2(v: float | None) -> float | None:
    return round(v, 2) if v is not None else None


# ---------------------------------------------------------------------------
# Sales importer
# ---------------------------------------------------------------------------

def import_daily_sales(session, sd: SheetData, portal_id: int, product_cache: dict) -> int:
    """
    Extract daily unit sales from date columns and upsert into daily_sales.
    Returns count of rows upserted.
    """
    cm = sd.col_map
    rows = []

    for _, row in sd.sku_rows.iterrows():
        sku_code = clean_sku(row.iloc[cm.sku_col])
        if not sku_code:
            continue

        product_id = product_cache.get(sku_code)
        if product_id is None:
            logger.debug(f"  Product not found (no seed?): {sku_code}")
            continue

        asp = _nan_none(row.iloc[cm.asp_col])

        for col_idx, col_date in sd.date_columns:
            # Skip future dates that have no data yet
            if col_date > TODAY:
                continue

            units = _nan_none(row.iloc[col_idx])
            if units is None:
                continue  # no data for this day

            revenue = _round2(units * asp) if (asp is not None and asp > 0) else None

            rows.append({
                "portal_id":  portal_id,
                "product_id": product_id,
                "sale_date":  col_date,
                "units_sold": units,
                "asp":        asp,
                "revenue":    revenue,
                "data_source": "excel",
            })

    if not rows:
        return 0

    # Deduplicate within batch — ON CONFLICT only handles DB-level conflicts,
    # not duplicates within the same INSERT values list.
    # Keep last occurrence for each (portal_id, product_id, sale_date).
    seen: dict[tuple, dict] = {}
    for r in rows:
        key = (r["portal_id"], r["product_id"], r["sale_date"])
        seen[key] = r
    rows = list(seen.values())

    from sqlalchemy.dialects.postgresql import insert as pg_insert
    stmt = pg_insert(DailySalesTable).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["portal_id", "product_id", "sale_date"],
        set_={
            "units_sold":  stmt.excluded.units_sold,
            "asp":         stmt.excluded.asp,
            "revenue":     stmt.excluded.revenue,
            "imported_at": datetime.now(),
        },
    )
    session.execute(stmt)
    return len(rows)


# ---------------------------------------------------------------------------
# Inventory importer
# ---------------------------------------------------------------------------

def import_inventory(session, sd: SheetData, portal_id: int, product_cache: dict) -> int:
    """
    Extract inventory snapshot from each SKU row and upsert into inventory_snapshots.
    Returns count of rows upserted.
    """
    cm = sd.col_map
    if not cm.inv_cols:
        return 0  # Shopify has no inventory

    snapshot_date = get_snapshot_date(sd)
    rows = []

    for _, row in sd.sku_rows.iterrows():
        sku_code = clean_sku(row.iloc[cm.sku_col])
        if not sku_code:
            continue

        product_id = product_cache.get(sku_code)
        if product_id is None:
            continue

        inv_data = {
            "portal_id":    portal_id,
            "product_id":   product_id,
            "snapshot_date": snapshot_date,
            "portal_stock":    None,
            "backend_stock":   None,
            "frontend_stock":  None,
            "solara_stock":    None,
            "amazon_fc_stock": None,
            "open_po":         None,
            "doc":             None,
        }

        for inv_key, col_idx in cm.inv_cols.items():
            if col_idx < len(row):
                v = _nan_none(row.iloc[col_idx])
                if inv_key == "portal":
                    inv_data["portal_stock"] = v
                elif inv_key == "backend":
                    inv_data["backend_stock"] = v
                elif inv_key == "frontend":
                    inv_data["frontend_stock"] = v
                elif inv_key == "solara":
                    inv_data["solara_stock"] = v
                elif inv_key == "amazon_fc":
                    inv_data["amazon_fc_stock"] = v

        if cm.doc_col is not None and cm.doc_col < len(row):
            inv_data["doc"] = _nan_none(row.iloc[cm.doc_col])

        if cm.open_po_col is not None and cm.open_po_col < len(row):
            inv_data["open_po"] = _nan_none(row.iloc[cm.open_po_col])

        rows.append(inv_data)

    if not rows:
        return 0

    # Deduplicate within batch
    seen: dict[tuple, dict] = {}
    for r in rows:
        key = (r["portal_id"], r["product_id"], r["snapshot_date"])
        seen[key] = r
    rows = list(seen.values())

    from sqlalchemy.dialects.postgresql import insert as pg_insert
    stmt = pg_insert(InventoryTable).values(rows)
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
            "imported_at":     datetime.now(),
        },
    )
    session.execute(stmt)
    return len(rows)


# ---------------------------------------------------------------------------
# Amazon targets importer
# ---------------------------------------------------------------------------

def import_amazon_targets(session, sd: SheetData, portal_id: int, product_cache: dict) -> int:
    """
    Extract monthly targets from Amazon sheets and upsert into monthly_targets.
    """
    if sd.portal != "amazon":
        return 0

    cm = sd.col_map
    rows = []

    for _, row in sd.sku_rows.iterrows():
        sku_code = clean_sku(row.iloc[cm.sku_col])
        if not sku_code:
            continue

        product_id = product_cache.get(sku_code)
        if product_id is None:
            continue

        def col_val(col_attr):
            idx = getattr(cm, col_attr, None)
            if idx is None or idx >= len(row):
                return None
            return _nan_none(row.iloc[idx])

        rows.append({
            "portal_id":      portal_id,
            "product_id":     product_id,
            "year":           sd.year,
            "month":          sd.month,
            "target_units":   col_val("target_units_col"),
            "target_revenue": col_val("target_revenue_col"),
            "target_drr":     col_val("target_drr_col"),
            "achievement_pct": col_val("achievement_col"),
        })

    if not rows:
        return 0

    # Deduplicate within batch
    seen: dict[tuple, dict] = {}
    for r in rows:
        key = (r["portal_id"], r["product_id"], r["year"], r["month"])
        seen[key] = r
    rows = list(seen.values())

    from sqlalchemy.dialects.postgresql import insert as pg_insert
    stmt = pg_insert(MonthlyTargetsTable).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["portal_id", "product_id", "year", "month"],
        set_={
            "target_units":    stmt.excluded.target_units,
            "target_revenue":  stmt.excluded.target_revenue,
            "target_drr":      stmt.excluded.target_drr,
            "achievement_pct": stmt.excluded.achievement_pct,
        },
    )
    session.execute(stmt)
    return len(rows)


# ---------------------------------------------------------------------------
# Ad spend importer
# ---------------------------------------------------------------------------

def import_ad_spend(session, sd: SheetData, portal_id: int) -> int:
    """
    Extract total revenue and ad spend from the bottom metadata rows.
    """
    if sd.ad_spend_row is None:
        return 0

    # Find MTD / latest date column value from the ad_spend_row
    # Ad spend rows store the monthly total in the last non-empty date column
    total_ad_spend = None
    total_revenue = None

    for col_idx, col_date in reversed(sd.date_columns):
        if col_date > TODAY:
            continue
        v = _nan_none(sd.ad_spend_row.iloc[col_idx])
        if v is not None and v > 0:
            total_ad_spend = v
            break

    # Try to find total revenue from the 'Total Revenue' row (just before ad spend)
    # We stored only ad_spend_row; approximate from MTD units × ASP sum if needed.
    # For now, store what we have; total_revenue can be derived from daily_sales.

    tacos = None
    if total_revenue and total_ad_spend and total_revenue > 0:
        tacos = round(total_ad_spend / total_revenue * 100, 4)

    rows = [{
        "portal_id":     portal_id,
        "year":          sd.year,
        "month":         sd.month,
        "total_revenue": total_revenue,
        "ad_spend":      total_ad_spend,
        "tacos_pct":     tacos,
    }]

    from sqlalchemy.dialects.postgresql import insert as pg_insert
    stmt = pg_insert(MonthlyAdSpendTable).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["portal_id", "year", "month"],
        set_={
            "ad_spend":      stmt.excluded.ad_spend,
            "tacos_pct":     stmt.excluded.tacos_pct,
        },
    )
    session.execute(stmt)
    return 1


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

def import_from_excel(file_path: str) -> None:
    logger.info(f"Opening: {file_path}")
    xl = pd.ExcelFile(file_path)
    sheets = iter_sheets(xl)
    logger.info(f"Portal sheets to import: {len(sheets)}")

    total_sales = 0
    total_inv = 0
    total_targets = 0
    start_time = datetime.now()

    with get_session() as session:
        # Pre-build product cache (sku_code → product_id) for speed
        from sqlalchemy import text
        rows = session.execute(text("SELECT sku_code, id FROM products")).fetchall()
        product_cache = {r[0]: r[1] for r in rows}
        logger.info(f"Product cache loaded: {len(product_cache)} products")

        for sd in sheets:
            portal_id = get_portal_id(session, sd.portal)
            if portal_id is None:
                logger.warning(f"Skipping {sd.sheet_name!r} — no portal ID for {sd.portal!r}")
                continue

            logger.info(f"Processing: {sd.sheet_name!r} ({sd.portal}, {sd.year}-{sd.month:02d}, "
                        f"{len(sd.sku_rows)} SKUs, {len(sd.date_columns)} date cols)")

            sheet_log_start = datetime.now()
            sheet_sales = 0
            sheet_inv = 0
            sheet_targets = 0
            error_msg = None

            try:
                sheet_sales   = import_daily_sales(session, sd, portal_id, product_cache)
                sheet_inv     = import_inventory(session, sd, portal_id, product_cache)
                sheet_targets = import_amazon_targets(session, sd, portal_id, product_cache)
                import_ad_spend(session, sd, portal_id)
                session.commit()
                status = "success"
            except Exception as e:
                session.rollback()
                error_msg = str(e)
                status = "failed"
                logger.error(f"  ERROR on {sd.sheet_name!r}: {e}")

            total_sales   += sheet_sales
            total_inv     += sheet_inv
            total_targets += sheet_targets

            log_import(
                session,
                source_type="excel_import",
                portal_id=portal_id,
                sheet_name=sd.sheet_name,
                file_name=os.path.basename(file_path),
                import_date=datetime.now().date(),
                status=status,
                records_imported=sheet_sales + sheet_inv,
                start_time=sheet_log_start,
                error_message=error_msg,
            )
            session.commit()

            logger.info(f"  → sales={sheet_sales}, inventory={sheet_inv}, "
                        f"targets={sheet_targets}, status={status}")

    logger.info("Phase 2 complete.")
    logger.info(f"  Daily sales rows  : {total_sales}")
    logger.info(f"  Inventory rows    : {total_inv}")
    logger.info(f"  Target rows       : {total_targets}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import daily sales and inventory from master Excel.")
    parser.add_argument("--file", required=True, help="Path to master Excel file")
    args = parser.parse_args()
    import_from_excel(args.file)
