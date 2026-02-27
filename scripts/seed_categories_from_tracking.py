"""
Populate product_categories and products.category_id from the
'AZ IN FEB-26' sheet in SOLARA - Daily Sales Tracking FY 25-26.xlsx.

Sheet layout (header on row 2, 0-indexed row 1):
  Col A  — Category       (L1, e.g. "Kitchen")
  Col B  — SKU ID         (e.g. "SOL-AF-001")
  Col C  — Product Category (L2, e.g. "Air Fryer")
  Col D  — Product Tittle (product display name)
  Col J  — BAU ASP        (default selling price)

Safe to re-run — all DB operations are upserts.

Usage:
    python scripts/seed_categories_from_tracking.py
    python scripts/seed_categories_from_tracking.py --file "data/source/SOLARA - Daily Sales Tracking FY 25-26.xlsx"
    python scripts/seed_categories_from_tracking.py --sheet "AZ IN JAN-26"
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
    get_or_create_category,
    get_or_create_product,
    log_import,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

_DEFAULT_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "source", "SOLARA - Daily Sales Tracking FY 25-26.xlsx",
)
_DEFAULT_SHEET = "AZ IN FEB-26"


def seed_categories(file_path: str, sheet_name: str) -> None:
    logger.info("Reading %s — sheet: %s", file_path, sheet_name)

    # Header is on Excel row 2 (0-indexed row 1)
    df = pd.read_excel(file_path, sheet_name=sheet_name, header=1, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]

    logger.info("Columns: %s", list(df.columns[:15]))
    logger.info("Total rows: %d", len(df))

    # Normalise to expected column names (handle minor typo variants)
    col_map = {}
    for col in df.columns:
        cl = col.strip().lower()
        if cl == "category":
            col_map["l1"] = col
        elif cl in ("product category", "product category "):
            col_map["l2"] = col
        elif cl in ("sku id", "sku_id", "sku code", "sku_code"):
            col_map["sku"] = col
        elif cl in ("product tittle", "product title", "product name"):
            col_map["name"] = col
        elif cl in ("bau asp", "asp"):
            col_map["asp"] = col

    missing = [k for k in ("l1", "l2", "sku") if k not in col_map]
    if missing:
        logger.error("Could not find required columns %s in sheet. Aborting.", missing)
        logger.error("Available columns: %s", list(df.columns))
        sys.exit(1)

    logger.info("Column mapping: %s", col_map)

    total_categories = 0
    total_products   = 0
    skipped          = 0
    start_time       = datetime.now()

    with get_session() as session:
        for _, row in df.iterrows():
            sku_code = str(row.get(col_map["sku"], "")).strip()
            if not sku_code or sku_code.lower() in ("nan", "none", ""):
                skipped += 1
                continue

            l1 = str(row.get(col_map["l1"], "")).strip()
            l2 = str(row.get(col_map["l2"], "")).strip()
            if not l1 or l1.lower() in ("nan", "none", ""):
                l1 = "Uncategorised"

            product_name = sku_code  # fallback
            if "name" in col_map:
                n = str(row.get(col_map["name"], "")).strip()
                if n and n.lower() not in ("nan", "none", ""):
                    product_name = n

            default_asp = None
            if "asp" in col_map:
                try:
                    v = str(row.get(col_map["asp"], "")).strip()
                    if v and v.lower() not in ("nan", "none", ""):
                        default_asp = float(v)
                except (ValueError, TypeError):
                    pass

            category_id = get_or_create_category(session, l1, l2 or None)
            total_categories += 1

            get_or_create_product(
                session,
                sku_code=sku_code,
                product_name=product_name,
                category_id=category_id,
                default_asp=default_asp,
            )
            total_products += 1

        session.commit()

        log_import(
            session,
            source_type="category_seed",
            portal_id=None,
            sheet_name=sheet_name,
            file_name=os.path.basename(file_path),
            import_date=datetime.now().date(),
            status="success",
            records_imported=total_products,
            start_time=start_time,
        )
        session.commit()

    logger.info("Done.")
    logger.info("  Categories upserted : %d", total_categories)
    logger.info("  Products upserted   : %d", total_products)
    logger.info("  Rows skipped        : %d", skipped)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Seed product categories from SOLARA Daily Sales Tracking sheet"
    )
    parser.add_argument(
        "--file",
        default=_DEFAULT_FILE,
        help="Path to the tracking Excel file",
    )
    parser.add_argument(
        "--sheet",
        default=_DEFAULT_SHEET,
        help="Sheet name to read (default: AZ IN FEB-26)",
    )
    args = parser.parse_args()
    seed_categories(args.file, args.sheet)
