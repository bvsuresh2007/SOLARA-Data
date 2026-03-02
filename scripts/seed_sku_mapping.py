"""
Seed product_portal_mapping and product_portal_exclusions from data/Sku_mapping.xlsx.

For each SOL-SKU row:
  - Upserts the product into the products table
  - For Amazon, Blinkit, Swiggy columns:
      non-zero value → product_portal_mapping (the product exists on this portal)
      zero / empty   → product_portal_exclusions (product not listed on this portal)
  - FSN (Flipkart) and Myntra are skipped — those portals are excluded from
    dashboard queries and the mapping file shows them as already excluded.
  - EAN CODE is a barcode, not a portal — skipped.

Safe to re-run: all operations are upserts / INSERT … ON CONFLICT DO NOTHING.

Usage:
    python scripts/seed_sku_mapping.py [--file data/Sku_mapping.xlsx]
"""

import argparse
import logging
import os
import sys
from datetime import datetime

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.db_utils import (
    get_session,
    get_portal_id,
    get_or_create_product,
    upsert_portal_mapping,
    upsert_portal_exclusion,
    log_import,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Mapping: column name in xlsx → portal slug in DB
_PORTAL_COLUMNS = {
    "ASIN":              "amazon",
    "STYLE ID(Blinkit)": "blinkit",
    "SWIGGY CODE":       "swiggy",
    "EAN CODE":          "zepto",   # Zepto sales files identify products by EAN barcode
}

# Sentinel values that mean "not listed on this portal"
_NOT_LISTED = {"0", "not listed", "n/a", "", "nan", "none"}


def _is_not_listed(value) -> bool:
    """Return True if the portal ID cell means the product is not on this portal."""
    v = str(value).strip().lower()
    return v in _NOT_LISTED


def _clean_portal_sku(value) -> str:
    """Normalise a portal SKU value — strip whitespace, remove float suffix."""
    s = str(value).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s


def seed_sku_mapping(file_path: str) -> None:
    logger.info(f"Reading: {file_path}")
    df = pd.read_excel(file_path, dtype=str)
    df.columns = [c.strip() for c in df.columns]
    logger.info(f"Rows: {len(df)}, Columns: {list(df.columns)}")

    total_products   = 0
    total_mappings   = 0
    total_exclusions = 0
    start_time       = datetime.now()

    with get_session() as session:
        # Pre-fetch portal IDs
        portal_ids: dict[str, int] = {}
        for col, slug in _PORTAL_COLUMNS.items():
            pid = get_portal_id(session, slug)
            if pid is None:
                logger.error(f"Portal '{slug}' not found in DB — aborting.")
                return
            portal_ids[slug] = pid

        for _, row in df.iterrows():
            sku_code = str(row.get("SKU CODE", "")).strip()
            if not sku_code or sku_code.lower() in ("nan", "none", ""):
                continue

            # Upsert product (sku_code as fallback name; existing name preserved via COALESCE)
            product_id = get_or_create_product(
                session,
                sku_code=sku_code,
                product_name=sku_code,   # fallback; existing rows keep their real name
                category_id=None,
                default_asp=None,
            )
            total_products += 1

            for col, slug in _PORTAL_COLUMNS.items():
                raw_val = row.get(col, "0")
                portal_id = portal_ids[slug]

                if _is_not_listed(raw_val):
                    # Product does not exist on this portal
                    upsert_portal_exclusion(session, product_id, portal_id)
                    total_exclusions += 1
                else:
                    portal_sku = _clean_portal_sku(raw_val)
                    upsert_portal_mapping(session, product_id, portal_id, portal_sku, None)
                    total_mappings += 1

        session.commit()

        log_import(
            session,
            source_type="sku_mapping_seed",
            portal_id=None,
            sheet_name="Sheet1",
            file_name=os.path.basename(file_path),
            import_date=datetime.now().date(),
            status="success",
            records_imported=total_products + total_mappings + total_exclusions,
            start_time=start_time,
        )
        session.commit()

    logger.info("Done.")
    logger.info(f"  Products upserted  : {total_products}")
    logger.info(f"  Portal mappings    : {total_mappings}")
    logger.info(f"  Portal exclusions  : {total_exclusions}")


def _resolve_default_path() -> str:
    """Find Sku_mapping.xlsx — check data/ first, then repo root."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.path.join(root, "data", "Sku_mapping.xlsx"),
        os.path.join(root, "Sku_mapping.xlsx"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    # Fallback to data/ even if missing — let the caller report the error
    return candidates[0]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed portal mappings from Sku_mapping.xlsx")
    parser.add_argument(
        "--file",
        default=_resolve_default_path(),
        help="Path to Sku_mapping.xlsx (default: data/Sku_mapping.xlsx or repo root)",
    )
    args = parser.parse_args()
    seed_sku_mapping(args.file)
