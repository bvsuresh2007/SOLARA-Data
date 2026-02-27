"""
Populate product_categories and products.category_id from all 'AZ IN *' sheets
in SOLARA - Daily Sales Tracking FY 25-26.xlsx.

Sheet layout (header on row 2, 0-indexed row 1):
  Col A  — Category       (L1, e.g. "Kitchen")
  Col B  — SKU ID         (e.g. "SOL-AF-001")
  Col C  — Product Category (L2, e.g. "Air Fryer")
  Col D  — Product Tittle (product display name)
  Col J  — BAU ASP        (default selling price)

When --sheet is omitted, ALL sheets whose name starts with "AZ IN" are
processed (oldest first so the latest month's data wins on conflict).

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

# Month ordering so oldest sheet is processed first (latest wins on upsert)
_MONTH_ORDER = [
    "April-25", "May-25", "June-25", "July-25",
    "Aug-25", "Sep-25", "Oct-25", "Nov-25", "Dec-25",
    "Jan-26", "Feb-26", "Mar-26",
]


def _month_sort_key(sheet_name: str) -> int:
    """Return sort index for an 'AZ IN Month-YY' sheet name."""
    suffix = sheet_name[len("AZ IN "):].strip()  # e.g. "FEB-26" or "July-25"
    for i, m in enumerate(_MONTH_ORDER):
        if suffix.lower() == m.lower():
            return i
    return 999  # unknown months go last


def discover_az_in_sheets(file_path: str) -> list[str]:
    """Return all 'AZ IN *' sheet names from the workbook, oldest first."""
    xl = pd.ExcelFile(file_path)
    sheets = [s for s in xl.sheet_names if str(s).startswith("AZ IN")]
    sheets.sort(key=_month_sort_key)
    return sheets


def _build_col_map(df: pd.DataFrame) -> dict[str, str]:
    col_map: dict[str, str] = {}
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
    return col_map


def seed_sheet(session, file_path: str, sheet_name: str) -> tuple[int, int, int]:
    """
    Process a single sheet. Returns (categories_upserted, products_upserted, skipped).
    Raises ValueError if required columns are missing.
    """
    logger.info("  Reading sheet: %s", sheet_name)

    df = pd.read_excel(file_path, sheet_name=sheet_name, header=1, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]

    col_map = _build_col_map(df)

    missing = [k for k in ("l1", "l2", "sku") if k not in col_map]
    if missing:
        raise ValueError(
            f"Sheet '{sheet_name}' missing required columns {missing}. "
            f"Available: {list(df.columns[:15])}"
        )

    total_categories = 0
    total_products   = 0
    skipped          = 0

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

    return total_categories, total_products, skipped


def seed_categories(file_path: str, sheet_name: str | None) -> None:
    if sheet_name:
        sheets = [sheet_name]
    else:
        sheets = discover_az_in_sheets(file_path)
        if not sheets:
            logger.error("No 'AZ IN *' sheets found in %s", file_path)
            sys.exit(1)
        logger.info("Found %d AZ IN sheets (processing oldest→newest): %s", len(sheets), sheets)

    grand_categories = 0
    grand_products   = 0
    grand_skipped    = 0
    start_time       = datetime.now()

    with get_session() as session:
        for sname in sheets:
            try:
                cats, prods, skipped = seed_sheet(session, file_path, sname)
                grand_categories += cats
                grand_products   += prods
                grand_skipped    += skipped
                logger.info(
                    "    → %d products, %d skipped", prods, skipped
                )
            except ValueError as exc:
                logger.warning("Skipping sheet — %s", exc)
                continue

        session.commit()

        processed_label = sheet_name if sheet_name else f"{len(sheets)} sheets"
        log_import(
            session,
            source_type="category_seed",
            portal_id=None,
            sheet_name=processed_label,
            file_name=os.path.basename(file_path),
            import_date=datetime.now().date(),
            status="success",
            records_imported=grand_products,
            start_time=start_time,
        )
        session.commit()

    logger.info("Done.")
    logger.info("  Sheets processed    : %d", len(sheets))
    logger.info("  Categories upserted : %d", grand_categories)
    logger.info("  Products upserted   : %d", grand_products)
    logger.info("  Rows skipped        : %d", grand_skipped)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Seed product categories from SOLARA Daily Sales Tracking sheets"
    )
    parser.add_argument(
        "--file",
        default=_DEFAULT_FILE,
        help="Path to the tracking Excel file",
    )
    parser.add_argument(
        "--sheet",
        default=None,
        help="Single sheet name to process (default: all 'AZ IN *' sheets)",
    )
    args = parser.parse_args()
    seed_categories(args.file, args.sheet)
