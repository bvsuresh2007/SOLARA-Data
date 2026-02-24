"""
Portal-specific Excel/CSV parsers.
Each parser reads a downloaded file and returns a list of raw row dicts.
"""
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


# =============================================================================
# Helpers
# =============================================================================

def _read_file(path: Path, sheet_name=0, skiprows=0) -> pd.DataFrame:
    # Detect real format by magic bytes (portals sometimes save CSVs with .xlsx extension)
    with open(path, "rb") as fh:
        magic = fh.read(4)
    is_real_xlsx = magic[:2] == b"PK"           # ZIP container → real xlsx
    is_real_xls  = magic[:2] == b"\xd0\xcf"    # BIFF container → legacy xls

    suffix = path.suffix.lower()
    if is_real_xlsx or is_real_xls:
        engine = "openpyxl" if is_real_xlsx else "xlrd"
        return pd.read_excel(path, sheet_name=sheet_name, skiprows=skiprows, dtype=str, engine=engine)
    elif suffix == ".csv" or not (is_real_xlsx or is_real_xls):
        # Treat as CSV (handles the case where portal serves CSV with .xlsx extension)
        return pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    raise ValueError(f"Unsupported file type: {suffix}")


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).strip() for c in df.columns]
    return df.where(pd.notna(df), None)


def _parse_date_ymd(val: Any) -> date | None:
    """YYYY-MM-DD → date"""
    try:
        return datetime.strptime(str(val).strip(), "%Y-%m-%d").date()
    except Exception:
        return None


def _parse_date_dmy(val: Any) -> date | None:
    """DD-MM-YYYY → date"""
    try:
        return datetime.strptime(str(val).strip(), "%d-%m-%Y").date()
    except Exception:
        return None


def _parse_iso(val: Any) -> date | None:
    """ISO 8601 timestamp → date (strips time & timezone)"""
    try:
        return datetime.fromisoformat(str(val).strip()[:19]).date()
    except Exception:
        return None


def _f(val: Any, default=0.0) -> float:
    try:
        return float(str(val).replace(",", "").replace("₹", "").strip())
    except Exception:
        return default


def _i(val: Any, default=0) -> int:
    try:
        return int(float(str(val).replace(",", "").strip()))
    except Exception:
        return default


# =============================================================================
# Swiggy
# =============================================================================

class SwiggyParser:
    """
    Swiggy sales & inventory Excel parser.
    Expected columns: date, ITEM_CODE, L1, L2, L3, BASE_MRP, GMV, area_name, ...
    """

    def parse_sales(self, path: Path) -> list[dict]:
        df = _clean(_read_file(path))
        rows = []
        for _, row in df.iterrows():
            rows.append({
                "portal": "swiggy",
                "sale_date": _parse_date_ymd(row.get("date")),
                "portal_product_id": str(row.get("ITEM_CODE", "")).strip(),
                "city": str(row.get("area_name", "")).strip(),
                "l1_category": str(row.get("L1", "")).strip(),
                "l2_category": str(row.get("L2", "")).strip(),
                "l3_category": str(row.get("L3", "")).strip(),
                "revenue": _f(row.get("GMV")),
                "base_mrp": _f(row.get("BASE_MRP")),
                "quantity_sold": _f(row.get("quantity_sold", row.get("qty", 0))),
                "order_count": _i(row.get("order_count", 0)),
                "discount_amount": 0.0,
                "net_revenue": _f(row.get("GMV")),
            })
        return rows

    def parse_inventory(self, path: Path) -> list[dict]:
        df = _clean(_read_file(path))
        rows = []
        for _, row in df.iterrows():
            rows.append({
                "portal": "swiggy",
                "snapshot_date": _parse_date_ymd(row.get("date")),
                "portal_product_id": str(row.get("ITEM_CODE", "")).strip(),
                "warehouse_name": str(row.get("facility_name", "")).strip(),
                "city": str(row.get("area_name", "")).strip(),
                "stock_quantity": _f(row.get("backend_inv_qty", 0)),
                "available_quantity": _f(row.get("frontend_inv_qty", 0)),
                "reserved_quantity": 0.0,
            })
        return rows


# =============================================================================
# Blinkit
# =============================================================================

class BlinkitParser:
    def parse_sales(self, path: Path) -> list[dict]:
        df = _clean(_read_file(path))
        rows = []
        for _, row in df.iterrows():
            revenue = _f(row.get("mrp", 0))
            rows.append({
                "portal": "blinkit",
                "sale_date": _parse_date_ymd(row.get("date")),
                "portal_product_id": str(row.get("item_id", "")).strip(),
                # Blinkit CSV uses "city_name" (not "city")
                "city": str(row.get("city_name", row.get("city", ""))).strip(),
                "l1_category": str(row.get("category", row.get("l1_category", ""))).strip(),
                "l2_category": str(row.get("l2_category", "")).strip(),
                "l3_category": "",
                "revenue": revenue,
                # Blinkit CSV uses "qty_sold" (not "quantity")
                "quantity_sold": _f(row.get("qty_sold", row.get("quantity", 0))),
                "order_count": _i(row.get("orders", row.get("qty_sold", 0))),
                "discount_amount": 0.0,
                "net_revenue": revenue,
            })
        return rows

    def parse_inventory(self, path: Path) -> list[dict]:
        # The daily Blinkit sales CSV does not contain inventory columns.
        # A separate inventory export would be needed.
        return []


# =============================================================================
# Zepto
# =============================================================================

class ZeptoParser:
    def parse_sales(self, path: Path) -> list[dict]:
        df = _clean(_read_file(path))
        rows = []
        for _, row in df.iterrows():
            mrp = _f(row.get("MRP", 0))
            selling_price = _f(row.get("Selling Price", mrp))
            # Zepto CSV uses full names: "Gross Merchandise Value" / "Gross Selling Value"
            gmv = _f(row.get("Gross Merchandise Value", row.get("GMV", 0)))
            gsv = _f(row.get("Gross Selling Value", row.get("GSV", gmv)))
            discount = round(mrp - selling_price, 2) if mrp > selling_price else 0.0
            rows.append({
                "portal": "zepto",
                "sale_date": _parse_date_dmy(row.get("Date")),
                "portal_product_id": str(row.get("SKU Number", "")).strip(),
                "city": str(row.get("City", "")).strip(),
                # Zepto CSV uses "SKU Category" / "SKU Sub Category"
                "l1_category": str(row.get("SKU Category", row.get("Category", ""))).strip(),
                "l2_category": str(row.get("SKU Sub Category", row.get("Sub Category", ""))).strip(),
                "l3_category": "",
                "revenue": gmv,
                # Zepto CSV uses "Sales (Qty) - Units" (not "Units")
                "quantity_sold": _f(row.get("Sales (Qty) - Units", row.get("Units", 0))),
                "order_count": _i(row.get("Orders", 0)),
                "discount_amount": discount,
                "net_revenue": gsv,
            })
        return rows

    def parse_inventory(self, path: Path) -> list[dict]:
        # The Zepto daily sales CSV does not contain inventory/stock columns.
        # A separate inventory export would be needed.
        return []


# =============================================================================
# Amazon
# =============================================================================

class AmazonParser:
    def parse_sales(self, path: Path) -> list[dict]:
        df = _clean(_read_file(path))
        rows = []
        for _, row in df.iterrows():
            # Build date from separate fields if needed
            try:
                sale_date = date(
                    int(row.get("orderYear", 2000)),
                    int(row.get("orderMonth", 1)),
                    int(row.get("orderDay", 1)),
                )
            except Exception:
                sale_date = _parse_date_ymd(row.get("date", row.get("orderDate")))

            revenue = _f(row.get("orderAmt", 0))
            rows.append({
                "portal": "amazon",
                "sale_date": sale_date,
                "portal_product_id": str(row.get("ASIN", row.get("asin", ""))).strip(),
                "city": str(row.get("city", "")).strip(),
                "l1_category": str(row.get("category", "")).strip(),
                "l2_category": str(row.get("subcategory", "")).strip(),
                "l3_category": "",
                "revenue": revenue,
                "quantity_sold": _f(row.get("orderQuantity", 0)),
                "order_count": _i(row.get("orderCount", 1)),
                "discount_amount": 0.0,
                "net_revenue": revenue,
            })
        return rows

    def parse_inventory(self, path: Path) -> list[dict]:
        df = _clean(_read_file(path))
        rows = []
        for _, row in df.iterrows():
            rows.append({
                "portal": "amazon",
                "snapshot_date": _parse_date_ymd(row.get("date", row.get("snapshotDate"))),
                "portal_product_id": str(row.get("ASIN", row.get("asin", ""))).strip(),
                "warehouse_name": str(row.get("warehouse", "Amazon FBA")).strip(),
                "city": "",
                "stock_quantity": _f(row.get("Sellable Units", 0)),
                "available_quantity": _f(row.get("Sellable Units", 0)),
                "reserved_quantity": 0.0,
                "unsellable_units": _f(row.get("Unsellable Units", 0)),
                "aged_90_plus_units": _f(row.get("Aged 90+", 0)),
                "oos_percentage": _f(row.get("OOS%", 0)),
                "lead_time_days": _i(row.get("Lead Time", 0)),
            })
        return rows


# =============================================================================
# Shopify
# =============================================================================

class ShopifyParser:
    def parse_sales(self, path: Path) -> list[dict]:
        df = _clean(_read_file(path))
        rows = []
        for _, row in df.iterrows():
            subtotal  = _f(row.get("Subtotal", 0))
            total     = _f(row.get("Total", subtotal))
            discount  = _f(row.get("Discount Amount", 0))
            taxes     = _f(row.get("Taxes", 0))
            shipping  = _f(row.get("Shipping", 0))
            net       = total - taxes - shipping
            rows.append({
                "portal": "shopify",
                "sale_date": _parse_iso(row.get("Created at", row.get("Paid at"))),
                "portal_product_id": str(row.get("Lineitem sku", "")).strip(),
                "city": str(row.get("Billing City", row.get("Shipping City", ""))).strip(),
                "l1_category": "",
                "l2_category": "",
                "l3_category": "",
                "revenue": subtotal,
                "quantity_sold": _f(row.get("Lineitem quantity", 1)),
                "order_count": 1,
                "discount_amount": discount,
                "net_revenue": net,
            })
        return rows

    def parse_inventory(self, path: Path) -> list[dict]:
        return []  # Shopify has no inventory export


# =============================================================================
# EasyEcom
# =============================================================================

class EasyEcomParser:
    # TODO: Map real columns once a sample CSV is available.
    # EasyEcom miniSalesReport columns are unknown until a file is inspected.
    def parse_sales(self, path: Path) -> list[dict]:
        return []

    def parse_inventory(self, path: Path) -> list[dict]:
        return []


# =============================================================================
# Amazon PI
# =============================================================================

class AmazonPIParser:
    # TODO: Map real columns once a sample XLSX is available.
    # Amazon PI "ASIN wise revenue and unit sales" report columns are unknown
    # until a file is inspected.
    def parse_sales(self, path: Path) -> list[dict]:
        return []

    def parse_inventory(self, path: Path) -> list[dict]:
        return []


# =============================================================================
# Registry
# =============================================================================

PARSERS: dict[str, type] = {
    "swiggy":    SwiggyParser,
    "blinkit":   BlinkitParser,
    "zepto":     ZeptoParser,
    "amazon":    AmazonParser,
    "shopify":   ShopifyParser,
    "easyecom":  EasyEcomParser,
    "amazon_pi": AmazonPIParser,
}


def get_parser(portal_name: str):
    cls = PARSERS.get(portal_name.lower())
    if not cls:
        raise ValueError(f"No parser for portal: {portal_name}")
    return cls()
