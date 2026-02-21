"""
Phase 1: Seed master data from the master Excel workbook.
Populates:
  - product_categories
  - products
  - product_portal_mapping

Safe to re-run — all operations use upsert logic.
New months can be added at any time; existing data is updated, not duplicated.

Usage:
    python scripts/seed_master_data.py --file "data/source/SOLARA - Daily Sales Tracking FY 25-26.xlsx"
"""
import argparse
import logging
import sys
import os
from datetime import datetime
from typing import Any

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.db_utils import (
    get_session,
    get_portal_id,
    get_or_create_category,
    get_or_create_product,
    upsert_portal_mapping,
    log_import,
)
from scripts.excel_reader import iter_sheets, clean_sku, _float, SheetData

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-row extraction
# ---------------------------------------------------------------------------

def extract_product_row(sd: SheetData, row: pd.Series) -> dict | None:
    """
    Extract product info from a single SKU row.
    Returns a dict with keys: sku_code, product_name, l2_category, asp, portal_sku, portal_name
    Returns None if the row is invalid.
    """
    cm = sd.col_map
    cols = list(row.index)

    def val(idx: int) -> Any:
        return row.iloc[idx] if idx < len(row) else None

    sku_code = clean_sku(val(cm.sku_col))
    if not sku_code:
        return None

    product_name = str(val(cm.name_col) or "").strip()
    if not product_name or product_name.lower() in ("nan", "none"):
        product_name = sku_code  # fallback

    l2_category = str(val(cm.category_col) or "").strip()
    if l2_category.lower() in ("nan", "none", ""):
        l2_category = None

    asp = _float(val(cm.asp_col))

    # Portal-specific identifier
    portal_id_val = val(cm.portal_id_col)
    if portal_id_val is None or str(portal_id_val).strip().lower() in ("nan", "none", ""):
        portal_sku = sku_code  # fallback to internal SKU (e.g., Shopify)
    else:
        portal_sku = str(portal_id_val).strip()
        # Remove float suffixes for numeric IDs like '10265533.0'
        if portal_sku.endswith(".0"):
            portal_sku = portal_sku[:-2]

    return {
        "sku_code": sku_code,
        "product_name": product_name,
        "l2_category": l2_category,
        "asp": asp,
        "portal_sku": portal_sku,
    }


# ---------------------------------------------------------------------------
# Main seeder
# ---------------------------------------------------------------------------

def seed_from_excel(file_path: str) -> None:
    logger.info(f"Opening: {file_path}")
    xl = pd.ExcelFile(file_path)
    sheets = iter_sheets(xl)
    logger.info(f"Sheets to process: {len(sheets)}")

    # L1 category — all Solara products are currently in Kitchen & Dining
    L1 = "Kitchen & Dining"

    total_products = 0
    total_mappings = 0
    start_time = datetime.now()

    with get_session() as session:
        # Gather all unique products across all sheets first (latest ASP wins)
        product_registry: dict[str, dict] = {}   # sku_code → {name, l2, asp}
        # portal mappings: (sku_code, portal_name) → portal_sku
        mapping_registry: dict[tuple, str] = {}

        for sd in sheets:
            portal_id = get_portal_id(session, sd.portal)
            if portal_id is None:
                logger.warning(f"  No portal ID for {sd.portal!r} — skipping {sd.sheet_name!r}")
                continue

            for _, row in sd.sku_rows.iterrows():
                extracted = extract_product_row(sd, row)
                if not extracted:
                    continue

                sku = extracted["sku_code"]

                # Keep latest data (sheets are processed oldest→newest, so later ones win)
                product_registry[sku] = {
                    "product_name": extracted["product_name"],
                    "l2_category":  extracted["l2_category"],
                    "asp":          extracted["asp"],
                }
                mapping_registry[(sku, sd.portal)] = extracted["portal_sku"]

        logger.info(f"Unique SKUs found: {len(product_registry)}")
        logger.info(f"Portal mappings found: {len(mapping_registry)}")

        # Upsert products
        sku_to_id: dict[str, int] = {}
        for sku_code, data in product_registry.items():
            cat_id = get_or_create_category(session, L1, data["l2_category"])
            product_id = get_or_create_product(
                session,
                sku_code=sku_code,
                product_name=data["product_name"],
                category_id=cat_id,
                default_asp=data["asp"],
            )
            sku_to_id[sku_code] = product_id
            total_products += 1

        session.commit()
        logger.info(f"Upserted {total_products} products.")

        # Upsert portal mappings
        for (sku_code, portal_name), portal_sku in mapping_registry.items():
            product_id = sku_to_id.get(sku_code)
            portal_id = get_portal_id(session, portal_name)
            if product_id is None or portal_id is None:
                continue
            # Look up portal_product_name from product_registry
            portal_product_name = product_registry.get(sku_code, {}).get("product_name")
            upsert_portal_mapping(session, product_id, portal_id, portal_sku, portal_product_name)
            total_mappings += 1

        session.commit()
        logger.info(f"Upserted {total_mappings} portal mappings.")

        # Log the import
        log_import(
            session,
            source_type="excel_import",
            portal_id=None,
            sheet_name="ALL (master data seed)",
            file_name=os.path.basename(file_path),
            import_date=datetime.now().date(),
            status="success",
            records_imported=total_products + total_mappings,
            start_time=start_time,
        )
        session.commit()

    logger.info("Phase 1 complete.")
    logger.info(f"  Products upserted : {total_products}")
    logger.info(f"  Mappings upserted : {total_mappings}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed products and portal mappings from master Excel.")
    parser.add_argument("--file", required=True, help="Path to master Excel file")
    args = parser.parse_args()
    seed_from_excel(args.file)
