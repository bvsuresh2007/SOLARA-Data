"""
File-upload-oriented parsers for portal CSVs and master Excel.

Each parse_* function:
  - Accepts a bytes object (content of the uploaded file) and the original filename.
  - Writes to a NamedTemporaryFile, reads with pandas.
  - Returns list[dict] of raw rows (no DB calls).
  - Raises ColumnMismatchError if required columns are missing — this is surfaced to
    the user as a 422 so they know the file format may have changed.
"""

import logging
import os
import tempfile
from datetime import date, datetime
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


# =============================================================================
# Exceptions
# =============================================================================

class ColumnMismatchError(ValueError):
    """Raised when a required column is absent from the uploaded file."""

    def __init__(self, missing: list[str], found: list[str], file_type: str):
        self.missing = missing
        self.found = found
        self.file_type = file_type
        super().__init__(
            f"[{file_type}] Missing required columns: {missing}. "
            f"Columns found in file: {found}"
        )


# =============================================================================
# Internal helpers (shared with scrapers/excel_parser.py logic)
# =============================================================================

def _write_temp(content: bytes, suffix: str) -> str:
    """Write bytes to a temp file and return its path."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
    except Exception:
        os.unlink(path)
        raise
    return path


def _read_file(path: str, sheet_name=0, skiprows=0) -> pd.DataFrame:
    # Detect real format by magic bytes — portals sometimes save XLSX as .csv
    with open(path, "rb") as fh:
        magic = fh.read(4)
    is_xlsx = magic[:2] == b"PK"          # ZIP container → xlsx
    is_xls  = magic[:2] == b"\xd0\xcf"   # BIFF container → legacy xls

    if is_xlsx:
        return pd.read_excel(path, sheet_name=sheet_name, skiprows=skiprows, dtype=str, engine="openpyxl")
    if is_xls:
        return pd.read_excel(path, sheet_name=sheet_name, skiprows=skiprows, dtype=str, engine="xlrd")

    suffix = os.path.splitext(path)[1].lower()
    if suffix in (".xlsx", ".xls"):
        return pd.read_excel(path, sheet_name=sheet_name, skiprows=skiprows, dtype=str)
    # Plain CSV — try common encodings in order
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return pd.read_csv(path, dtype=str, encoding=enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Could not decode {os.path.basename(path)} — tried utf-8, utf-8-sig, latin-1")


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).strip() for c in df.columns]
    return df.where(pd.notna(df), None)


def _require_columns(df: pd.DataFrame, required: list[str], file_type: str) -> None:
    """Raise ColumnMismatchError if any required column is absent."""
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ColumnMismatchError(
            missing=missing,
            found=sorted(df.columns.tolist()),
            file_type=file_type,
        )


def _parse_date_ymd(val: Any) -> date | None:
    try:
        return datetime.strptime(str(val).strip(), "%Y-%m-%d").date()
    except Exception:
        return None


def _parse_date_dmy(val: Any) -> date | None:
    try:
        return datetime.strptime(str(val).strip(), "%d-%m-%Y").date()
    except Exception:
        return None


def _parse_iso(val: Any) -> date | None:
    try:
        return datetime.fromisoformat(str(val).strip()[:19]).date()
    except Exception:
        return None


def _f(val: Any, default: float = 0.0) -> float:
    try:
        return float(str(val).replace(",", "").replace("₹", "").strip())
    except Exception:
        return default


def _i(val: Any, default: int = 0) -> int:
    try:
        return int(float(str(val).replace(",", "").strip()))
    except Exception:
        return default


# =============================================================================
# Blinkit
# =============================================================================

BLINKIT_SALES_REQUIRED = ["item_id", "date"]
BLINKIT_INV_REQUIRED = ["item_id", "date"]


def parse_blinkit_sales(content: bytes, filename: str) -> list[dict]:
    suffix = os.path.splitext(filename)[1] or ".csv"
    path = _write_temp(content, suffix)
    try:
        df = _clean(_read_file(path))
        _require_columns(df, BLINKIT_SALES_REQUIRED, "blinkit_sales")
        rows = []
        for row in df.to_dict("records"):
            # city column: new exports use city_name, old exports used city
            city = str(row.get("city_name", row.get("city", ""))).strip()
            rows.append({
                "portal": "blinkit",
                "sale_date": _parse_date_ymd(row.get("date")),
                "portal_product_id": str(row.get("item_id", "")).strip(),
                "city": city,
                "revenue": _f(row.get("mrp", row.get("revenue", 0))),
                "quantity_sold": _f(row.get("qty_sold", row.get("quantity", 0))),
                "order_count": _i(row.get("orders", 0)),
                "discount_amount": 0.0,
            })
        return rows
    finally:
        os.unlink(path)


def parse_blinkit_inventory(content: bytes, filename: str) -> list[dict]:
    suffix = os.path.splitext(filename)[1] or ".csv"
    path = _write_temp(content, suffix)
    try:
        df = _clean(_read_file(path))
        _require_columns(df, BLINKIT_INV_REQUIRED, "blinkit_inventory")
        rows = []
        for row in df.to_dict("records"):
            rows.append({
                "portal": "blinkit",
                "snapshot_date": _parse_date_ymd(row.get("date", row.get("created_at"))),
                "portal_product_id": str(row.get("item_id", "")).strip(),
                "warehouse_name": str(row.get("facility_name", "")).strip(),
                "city": str(row.get("city", "")).strip(),
                "backend_stock": _f(row.get("backend_inv_qty", 0)),
                "frontend_stock": _f(row.get("frontend_inv_qty", 0)),
            })
        return rows
    finally:
        os.unlink(path)


# =============================================================================
# Swiggy
# =============================================================================

SWIGGY_SALES_REQUIRED = ["item_code"]   # date col checked separately (two known names)
SWIGGY_INV_REQUIRED   = ["item_code"]


def _swiggy_parse_date(row: dict) -> date | None:
    """Parse Swiggy date from either 'date' (YYYY-MM-DD) or 'ordered_date' (YYYY-MM-DD HH:MM:SS)."""
    raw = row.get("date") or row.get("ordered_date")
    if not raw:
        return None
    val = str(raw).strip()[:10]   # take YYYY-MM-DD prefix regardless of time part
    return _parse_date_ymd(val)


def parse_swiggy_sales(content: bytes, filename: str) -> list[dict]:
    suffix = os.path.splitext(filename)[1] or ".csv"
    path = _write_temp(content, suffix)
    try:
        df = _clean(_read_file(path))
        # Normalise to lowercase so both old (area_name) and new (AREA_NAME) formats work
        df.columns = [c.lower() for c in df.columns]
        if "date" not in df.columns and "ordered_date" not in df.columns:
            raise ColumnMismatchError(
                missing=["date (or ordered_date)"],
                found=sorted(df.columns.tolist()),
                file_type="swiggy_sales",
            )
        _require_columns(df, SWIGGY_SALES_REQUIRED, "swiggy_sales")
        rows = []
        for row in df.to_dict("records"):
            rows.append({
                "portal": "swiggy",
                "sale_date": _swiggy_parse_date(row),
                "portal_product_id": str(row.get("item_code", "")).strip(),
                "city": str(row.get("area_name", row.get("city", ""))).strip(),
                "revenue": _f(row.get("gmv", 0)),
                "quantity_sold": _f(row.get("units_sold", row.get("quantity_sold", row.get("qty", 0)))),
                "order_count": _i(row.get("order_count", 0)),
                "discount_amount": 0.0,
            })
        return rows
    finally:
        os.unlink(path)


def parse_swiggy_inventory(content: bytes, filename: str) -> list[dict]:
    suffix = os.path.splitext(filename)[1] or ".csv"
    path = _write_temp(content, suffix)
    try:
        df = _clean(_read_file(path))
        _require_columns(df, SWIGGY_INV_REQUIRED, "swiggy_inventory")
        rows = []
        for row in df.to_dict("records"):
            rows.append({
                "portal": "swiggy",
                "snapshot_date": _parse_date_ymd(row.get("date")),
                "portal_product_id": str(row.get("ITEM_CODE", "")).strip(),
                "warehouse_name": str(row.get("facility_name", "")).strip(),
                "city": str(row.get("area_name", "")).strip(),
                "backend_stock": _f(row.get("backend_inv_qty", 0)),
                "frontend_stock": _f(row.get("frontend_inv_qty", 0)),
            })
        return rows
    finally:
        os.unlink(path)


# =============================================================================
# Zepto
# =============================================================================

ZEPTO_SALES_REQUIRED = ["SKU Number", "Date"]
ZEPTO_INV_REQUIRED = ["SKU Number", "Date"]


def parse_zepto_sales(content: bytes, filename: str) -> list[dict]:
    suffix = os.path.splitext(filename)[1] or ".csv"
    path = _write_temp(content, suffix)
    try:
        df = _clean(_read_file(path))
        _require_columns(df, ZEPTO_SALES_REQUIRED, "zepto_sales")
        rows = []
        for row in df.to_dict("records"):
            # Use EAN as portal_product_id — matches product_portal_mapping seeded from
            # Sku_mapping.xlsx EAN CODE column. Skip rows with no EAN.
            ean = str(row.get("EAN", "")).strip()
            if not ean or ean in ("0", "nan", ""):
                continue
            mrp = _f(row.get("MRP", 0))
            # Selling Price: new exports use "Gross Selling Value", old used "Selling Price"
            selling_price = _f(row.get("Gross Selling Value", row.get("Selling Price", mrp)))
            # GMV: new exports use "Gross Merchandise Value", old used "GMV"
            gmv = _f(row.get("Gross Merchandise Value", row.get("GMV", 0)))
            discount = round(mrp - selling_price, 2) if mrp > selling_price else 0.0
            rows.append({
                "portal": "zepto",
                "sale_date": _parse_date_dmy(row.get("Date")),
                "portal_product_id": ean,
                "city": str(row.get("City", "")).strip(),
                "revenue": gmv,
                # Units: new exports use "Sales (Qty) - Units", old used "Units"
                "quantity_sold": _f(row.get("Sales (Qty) - Units", row.get("Units", 0))),
                "order_count": _i(row.get("Orders", 0)),
                "discount_amount": discount,
            })
        return rows
    finally:
        os.unlink(path)


def parse_zepto_inventory(content: bytes, filename: str) -> list[dict]:
    suffix = os.path.splitext(filename)[1] or ".csv"
    path = _write_temp(content, suffix)
    try:
        df = _clean(_read_file(path))
        _require_columns(df, ZEPTO_INV_REQUIRED, "zepto_inventory")
        rows = []
        for row in df.to_dict("records"):
            stock = _f(row.get("Units", 0))
            rows.append({
                "portal": "zepto",
                "snapshot_date": _parse_date_dmy(row.get("Date")),
                "portal_product_id": str(row.get("SKU Number", "")).strip(),
                "city": str(row.get("City", "")).strip(),
                "warehouse_name": "",
                "backend_stock": stock,
                "frontend_stock": stock,
            })
        return rows
    finally:
        os.unlink(path)


# =============================================================================
# EasyEcom
# =============================================================================

EASYECOM_SALES_REQUIRED = ["SKU", "Order Date", "Item Quantity"]
_EASYECOM_CANCELLED = {"cancelled", "CANCELLED"}

# Maps EasyEcom "MP Name" (lowercased + stripped) to portal slug.
# None = skip row (handled by another scraper or not tracked here).
EASYECOM_MP_MAP: dict[str, str | None] = {
    "amazon.in":               None,          # Amazon comes from Amazon PI scraper
    "vendor central dropship": None,          # Skip
    "flipkart":                None,          # Skip — handled separately
    "myntra ppmp":             None,          # Skip — handled separately
    "shopify":                 "shopify",
    "meesho-api":              "meesho",
    "nykaa fashion":           "nykaa_fashion",
    "cred-api":                "cred",
    "vaaree":                  "vaaree",
    "offline":                 "offline",
}


def parse_easyecom_sales(content: bytes, filename: str) -> list[dict]:
    """
    EasyEcom mini sales report (CSV extracted from ZIP download).

    Rows are split by MP Name → portal slug using EASYECOM_MP_MAP.
    Marketplaces mapped to None (Amazon, Vendor Central, Flipkart, Myntra) are
    skipped. Unknown MP Names are also skipped (logged as warnings).

    Key columns: SKU, Order Date, Shipping City, Selling Price, Item Quantity,
                 Order Status, MP Name.
    - Cancelled orders are excluded.
    - SKU may have a leading backtick (artifact from EasyEcom export) — stripped.
    - Selling Price is the line-item total (not per-unit price).
    - Order Date is ISO-format timestamp (YYYY-MM-DD HH:MM:SS or YYYY-MM-DD).
    """
    suffix = os.path.splitext(filename)[1] or ".csv"
    path = _write_temp(content, suffix)
    try:
        df = _clean(_read_file(path))
        _require_columns(df, EASYECOM_SALES_REQUIRED, "easyecom_sales")
        if "MP Name" not in df.columns:
            logger.warning("EasyEcom file %s has no 'MP Name' column — cannot split by marketplace", filename)
            return []
        rows = []
        for row in df.to_dict("records"):
            status = str(row.get("Order Status", "")).strip()
            if status in _EASYECOM_CANCELLED:
                continue
            sku = str(row.get("SKU", "")).strip().lstrip("`")
            if not sku:
                continue
            mp_name = str(row.get("MP Name", "")).strip().lower()
            if mp_name not in EASYECOM_MP_MAP:
                logger.warning("EasyEcom: unknown MP Name %r — skipping row", mp_name)
                continue
            portal = EASYECOM_MP_MAP[mp_name]
            if portal is None:
                continue  # explicitly skipped marketplace
            revenue = _f(row.get("Selling Price", 0))
            rows.append({
                "portal": portal,
                "sale_date": _parse_iso(row.get("Order Date")),
                "portal_product_id": sku,
                "city": str(row.get("Shipping City", "")).strip(),
                "revenue": revenue,
                "quantity_sold": _f(row.get("Item Quantity", 1)),
                "order_count": 1,
                "discount_amount": 0.0,
            })
        return rows
    finally:
        os.unlink(path)


# =============================================================================
# Amazon PI
# =============================================================================

AMAZON_PI_REQUIRED = ["asin"]


def parse_amazon_pi(content: bytes, filename: str) -> list[dict]:
    """
    Amazon PI ASIN-wise revenue and unit sales report.

    Handles two formats (both are case-insensitive on column names):
      1. Long format  — one row per order with orderYear/orderMonth/orderDay columns
                        (actual format from Amazon PI Download Center)
      2. Wide format  — date columns as headers (legacy / SBG pivot export)
    """
    suffix = os.path.splitext(filename)[1] or ".xlsx"
    path = _write_temp(content, suffix)
    try:
        df = _clean(_read_file(path))
        # Normalise all column names to lowercase so matching is case-insensitive
        df.columns = [c.lower() for c in df.columns]
        _require_columns(df, AMAZON_PI_REQUIRED, "amazon_pi")

        rows = []

        # ── Format 1: long format with orderYear / orderMonth / orderDay ──────
        if all(c in df.columns for c in ("orderyear", "ordermonth", "orderday")):
            for row in df.to_dict("records"):
                asin = str(row.get("asin", "") or "").strip()
                if not asin:
                    continue
                try:
                    sale_date = date(
                        int(float(row["orderyear"])),
                        int(float(row["ordermonth"])),
                        int(float(row["orderday"])),
                    )
                except (ValueError, TypeError, KeyError):
                    continue
                rows.append({
                    "portal": "amazon",
                    "sale_date": sale_date,
                    "portal_product_id": asin,
                    "city": str(row.get("statename", "") or "").strip(),
                    "revenue": _f(row.get("orderamt", 0)),
                    "quantity_sold": _f(row.get("orderquantity", 0)),
                    "order_count": 1,
                    "discount_amount": 0.0,
                })
            return rows

        # ── Format 2: wide format with date-header columns ────────────────────
        non_date_cols = {
            "asin", "product name", "category", "brand", "sub category",
            "itemname", "lbrbrandname", "subcategory", "statename", "postalcode",
        }
        date_cols = []
        for col in df.columns:
            if col in non_date_cols:
                continue
            parsed = _parse_date_ymd(col)
            if parsed is None:
                try:
                    parsed = datetime.strptime(str(col).strip(), "%d-%m-%Y").date()
                except Exception:
                    try:
                        parsed = datetime.strptime(str(col).strip(), "%d/%m/%Y").date()
                    except Exception:
                        continue
            date_cols.append((col, parsed))

        if not date_cols:
            # Last-resort: single date column
            if "date" in df.columns or "orderdate" in df.columns:
                date_col = "date" if "date" in df.columns else "orderdate"
                for row in df.to_dict("records"):
                    rows.append({
                        "portal": "amazon",
                        "sale_date": _parse_date_ymd(row.get(date_col)),
                        "portal_product_id": str(row.get("asin", "") or "").strip(),
                        "city": str(row.get("statename", "") or "").strip(),
                        "revenue": _f(row.get("revenue", row.get("orderamt", 0))),
                        "quantity_sold": _f(row.get("units", row.get("orderquantity", 0))),
                        "order_count": _i(row.get("orders", row.get("ordercount", 1))),
                        "discount_amount": 0.0,
                    })
                return rows
            raise ColumnMismatchError(
                missing=["date columns (YYYY-MM-DD format) or orderyear/ordermonth/orderday"],
                found=sorted(df.columns.tolist()),
                file_type="amazon_pi",
            )

        for row in df.to_dict("records"):
            asin = str(row.get("asin", "") or "").strip()
            if not asin:
                continue
            for col_name, sale_date in date_cols:
                val = row.get(col_name)
                if val is None:
                    continue
                qty = _f(val)
                if qty == 0:
                    continue
                rows.append({
                    "portal": "amazon",
                    "sale_date": sale_date,
                    "portal_product_id": asin,
                    "city": "",
                    "revenue": 0.0,
                    "quantity_sold": qty,
                    "order_count": 0,
                    "discount_amount": 0.0,
                })
        return rows
    finally:
        os.unlink(path)


# =============================================================================
# Shopify
# =============================================================================

SHOPIFY_SALES_REQUIRED = ["Lineitem sku", "Created at", "Lineitem quantity"]


def parse_shopify_sales(content: bytes, filename: str) -> list[dict]:
    suffix = os.path.splitext(filename)[1] or ".csv"
    path = _write_temp(content, suffix)
    try:
        df = _clean(_read_file(path))
        _require_columns(df, SHOPIFY_SALES_REQUIRED, "shopify_sales")
        rows = []
        for row in df.to_dict("records"):
            subtotal = _f(row.get("Subtotal", 0))
            total = _f(row.get("Total", subtotal))
            discount = _f(row.get("Discount Amount", 0))
            taxes = _f(row.get("Taxes", 0))
            shipping = _f(row.get("Shipping", 0))
            rows.append({
                "portal": "shopify",
                "sale_date": _parse_iso(row.get("Created at", row.get("Paid at"))),
                "portal_product_id": str(row.get("Lineitem sku", "")).strip(),
                "city": str(row.get("Billing City", row.get("Shipping City", ""))).strip(),
                "revenue": subtotal,
                "quantity_sold": _f(row.get("Lineitem quantity", 1)),
                "order_count": 1,
                "discount_amount": discount,
                "net_revenue": total - taxes - shipping,
            })
        return rows
    finally:
        os.unlink(path)


# =============================================================================
# Master Excel — uses scripts/excel_reader.iter_sheets()
# =============================================================================

def _ensure_scripts_on_path() -> None:
    """Add project root to sys.path so scripts/ is importable from the backend."""
    import sys
    # backend/app/utils/excel_parsers.py → go up 4 levels to project root
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    )
    if project_root not in sys.path:
        sys.path.insert(0, project_root)


def parse_master_excel(content: bytes, filename: str) -> list[dict]:
    """
    Parse the SOLARA master Excel workbook.

    Uses scripts/excel_reader.iter_sheets() to handle all known cross-month
    column inconsistencies.  Returns a flat list of dicts, one per (SKU, date) cell
    that has data.  Each dict includes:
        portal, sku_code, sale_date, units_sold, asp, revenue

    The upload pipeline uses sku_code (SOL-XXXX) to resolve product_id directly
    from the products table (not via product_portal_mapping).

    Raises ValueError if the workbook has no parseable portal sheets.
    """
    suffix = os.path.splitext(filename)[1] or ".xlsx"
    path = _write_temp(content, suffix)
    try:
        _ensure_scripts_on_path()
        try:
            import pandas as _pd
            from scripts.excel_reader import iter_sheets, clean_sku, _float  # type: ignore
        except ImportError as exc:
            raise ValueError(
                f"Could not import scripts/excel_reader.py: {exc}. "
                "Ensure the project root is on PYTHONPATH."
            ) from exc

        from datetime import datetime as _dt
        today = _dt.today().date()

        xl = _pd.ExcelFile(path)
        sheets = iter_sheets(xl)
        if not sheets:
            raise ValueError(
                "Master Excel file produced no parseable sheets. "
                "The workbook structure may have changed — expected portal tab names "
                "like 'Blinkit FEB-26', 'Zepto MAR-26', 'AZ IN APR-26', etc."
            )

        rows: list[dict] = []
        for sd in sheets:
            cm = sd.col_map
            for _, row in sd.sku_rows.iterrows():
                sku_code = clean_sku(row.iloc[cm.sku_col] if cm.sku_col < len(row) else None)
                if not sku_code:
                    continue

                asp_raw = _float(row.iloc[cm.asp_col] if cm.asp_col < len(row) else None)

                for col_idx, col_date in sd.date_columns:
                    if col_date > today:
                        continue
                    units_raw = _float(row.iloc[col_idx] if col_idx < len(row) else None)
                    if units_raw is None:
                        continue
                    revenue = round(units_raw * asp_raw, 2) if (asp_raw and asp_raw > 0) else None
                    rows.append({
                        "portal": sd.portal,
                        "sku_code": sku_code,
                        "sale_date": col_date,
                        "units_sold": units_raw,
                        "asp": asp_raw,
                        "revenue": revenue,
                    })

        return rows
    finally:
        os.unlink(path)


# =============================================================================
# Registry
# =============================================================================

PARSER_REGISTRY: dict[str, Any] = {
    "blinkit_sales": parse_blinkit_sales,
    "blinkit_inventory": parse_blinkit_inventory,
    "swiggy_sales": parse_swiggy_sales,
    "swiggy_inventory": parse_swiggy_inventory,
    "zepto_sales": parse_zepto_sales,
    "zepto_inventory": parse_zepto_inventory,
    "easyecom_sales": parse_easyecom_sales,
    "amazon_pi": parse_amazon_pi,
    "shopify_sales": parse_shopify_sales,
    "master_excel": parse_master_excel,
}


def parse_file(file_type: str, content: bytes, filename: str) -> list[dict]:
    """Entry point used by the upload API."""
    parser = PARSER_REGISTRY.get(file_type)
    if parser is None:
        raise ValueError(f"Unknown file_type: {file_type!r}")
    return parser(content, filename)
