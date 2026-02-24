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
    suffix = os.path.splitext(path)[1].lower()
    if suffix in (".xlsx", ".xls"):
        return pd.read_excel(path, sheet_name=sheet_name, skiprows=skiprows, dtype=str)
    elif suffix == ".csv":
        return pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    raise ValueError(f"Unsupported file extension: {suffix!r}. Expected .xlsx, .xls, or .csv")


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

BLINKIT_SALES_REQUIRED = ["item_id", "date", "city"]
BLINKIT_INV_REQUIRED = ["item_id", "date"]


def parse_blinkit_sales(content: bytes, filename: str) -> list[dict]:
    suffix = os.path.splitext(filename)[1] or ".csv"
    path = _write_temp(content, suffix)
    try:
        df = _clean(_read_file(path))
        _require_columns(df, BLINKIT_SALES_REQUIRED, "blinkit_sales")
        rows = []
        for _, row in df.iterrows():
            rows.append({
                "portal": "blinkit",
                "sale_date": _parse_date_ymd(row.get("date")),
                "portal_product_id": str(row.get("item_id", "")).strip(),
                "city": str(row.get("city", "")).strip(),
                "revenue": _f(row.get("mrp", row.get("revenue", 0))),
                "quantity_sold": _f(row.get("quantity", row.get("qty_sold", 0))),
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
        for _, row in df.iterrows():
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

SWIGGY_SALES_REQUIRED = ["date", "ITEM_CODE"]
SWIGGY_INV_REQUIRED = ["date", "ITEM_CODE"]


def parse_swiggy_sales(content: bytes, filename: str) -> list[dict]:
    suffix = os.path.splitext(filename)[1] or ".csv"
    path = _write_temp(content, suffix)
    try:
        df = _clean(_read_file(path))
        _require_columns(df, SWIGGY_SALES_REQUIRED, "swiggy_sales")
        rows = []
        for _, row in df.iterrows():
            rows.append({
                "portal": "swiggy",
                "sale_date": _parse_date_ymd(row.get("date")),
                "portal_product_id": str(row.get("ITEM_CODE", "")).strip(),
                "city": str(row.get("area_name", "")).strip(),
                "revenue": _f(row.get("GMV", 0)),
                "quantity_sold": _f(row.get("quantity_sold", row.get("UNITS_SOLD", row.get("qty", 0)))),
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
        for _, row in df.iterrows():
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

ZEPTO_SALES_REQUIRED = ["SKU Number", "Date", "Units"]
ZEPTO_INV_REQUIRED = ["SKU Number", "Date"]


def parse_zepto_sales(content: bytes, filename: str) -> list[dict]:
    suffix = os.path.splitext(filename)[1] or ".csv"
    path = _write_temp(content, suffix)
    try:
        df = _clean(_read_file(path))
        _require_columns(df, ZEPTO_SALES_REQUIRED, "zepto_sales")
        rows = []
        for _, row in df.iterrows():
            mrp = _f(row.get("MRP", 0))
            selling_price = _f(row.get("Selling Price", mrp))
            gmv = _f(row.get("GMV", 0))
            discount = round(mrp - selling_price, 2) if mrp > selling_price else 0.0
            rows.append({
                "portal": "zepto",
                "sale_date": _parse_date_dmy(row.get("Date")),
                "portal_product_id": str(row.get("SKU Number", "")).strip(),
                "city": str(row.get("City", "")).strip(),
                "revenue": gmv,
                "quantity_sold": _f(row.get("Units", 0)),
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
        for _, row in df.iterrows():
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
# Amazon PI
# =============================================================================

AMAZON_PI_REQUIRED = ["ASIN"]


def parse_amazon_pi(content: bytes, filename: str) -> list[dict]:
    """
    Amazon PI ASIN-wise revenue and unit sales report.
    Date columns are the report's date range columns (not a 'date' column).
    Returns one row per ASIN per date column that has data.
    """
    suffix = os.path.splitext(filename)[1] or ".xlsx"
    path = _write_temp(content, suffix)
    try:
        df = _clean(_read_file(path))
        _require_columns(df, AMAZON_PI_REQUIRED, "amazon_pi")

        # Date columns: all columns that parse as dates (YYYY-MM-DD or similar)
        # Non-date metadata columns to skip
        non_date_cols = {"ASIN", "Product Name", "Category", "Brand", "Sub Category"}
        date_cols = []
        for col in df.columns:
            if col in non_date_cols:
                continue
            # Try to parse as date
            parsed = _parse_date_ymd(col)
            if parsed is None:
                # Try other formats
                try:
                    parsed = datetime.strptime(str(col).strip(), "%d-%m-%Y").date()
                except Exception:
                    try:
                        parsed = datetime.strptime(str(col).strip(), "%d/%m/%Y").date()
                    except Exception:
                        continue
            date_cols.append((col, parsed))

        if not date_cols:
            # Fallback: look for standard columns
            if "date" in df.columns or "orderDate" in df.columns:
                date_col = "date" if "date" in df.columns else "orderDate"
                rows = []
                for _, row in df.iterrows():
                    rows.append({
                        "portal": "amazon",
                        "sale_date": _parse_date_ymd(row.get(date_col)),
                        "portal_product_id": str(row.get("ASIN", "")).strip(),
                        "city": "",
                        "revenue": _f(row.get("Revenue", row.get("orderAmt", 0))),
                        "quantity_sold": _f(row.get("Units", row.get("orderQuantity", 0))),
                        "order_count": _i(row.get("Orders", row.get("orderCount", 1))),
                        "discount_amount": 0.0,
                    })
                return rows
            raise ColumnMismatchError(
                missing=["date columns (YYYY-MM-DD format) or a 'date' column"],
                found=sorted(df.columns.tolist()),
                file_type="amazon_pi",
            )

        rows = []
        for _, row in df.iterrows():
            asin = str(row.get("ASIN", "")).strip()
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
                    "revenue": 0.0,  # PI report has units only; revenue derived from ASP
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
        for _, row in df.iterrows():
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
