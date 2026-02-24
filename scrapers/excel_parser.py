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
    Swiggy sales CSV parser.
    Actual columns: ORDERED_DATE, ITEM_CODE, CITY, AREA_NAME, L1_CATEGORY,
    L2_CATEGORY, L3_CATEGORY, BASE_MRP, GMV, UNITS_SOLD, ...
    """

    def parse_sales(self, path: Path) -> list[dict]:
        df = _clean(_read_file(path))
        rows = []
        for _, row in df.iterrows():
            gmv = _f(row.get("GMV"))
            rows.append({
                "portal": "swiggy",
                # Swiggy CSV uses "ORDERED_DATE" (YYYY-MM-DD), not "date"
                "sale_date": _parse_date_ymd(row.get("ORDERED_DATE", row.get("date"))),
                "portal_product_id": str(row.get("ITEM_CODE", "")).strip(),
                # Swiggy CSV uses "CITY" (not "area_name")
                "city": str(row.get("CITY", row.get("area_name", ""))).strip(),
                # Swiggy CSV uses "L1_CATEGORY" etc. (not "L1")
                "l1_category": str(row.get("L1_CATEGORY", row.get("L1", ""))).strip(),
                "l2_category": str(row.get("L2_CATEGORY", row.get("L2", ""))).strip(),
                "l3_category": str(row.get("L3_CATEGORY", row.get("L3", ""))).strip(),
                "revenue": gmv,
                "base_mrp": _f(row.get("BASE_MRP")),
                # Swiggy CSV uses "UNITS_SOLD" (not "quantity_sold")
                "quantity_sold": _f(row.get("UNITS_SOLD", row.get("quantity_sold", row.get("qty", 0)))),
                "order_count": _i(row.get("order_count", 0)),
                "discount_amount": 0.0,
                "net_revenue": gmv,
            })
        return rows

    def parse_inventory(self, path: Path) -> list[dict]:
        # The daily Swiggy sales CSV does not contain inventory columns.
        # A separate inventory export would be needed.
        return []


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
                # Zepto CSV uses "EAN" as the stable product identifier;
                # "SKU Number" is a UUID that changes and is NOT in product_portal_mapping.
                "portal_product_id": str(row.get("EAN", row.get("SKU Number", ""))).strip(),
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
    """
    EasyEcom mini sales report parser.
    Key columns: SKU, Order Date, Shipping City, Selling Price, Item Quantity,
                 Order Status, Category, MP Name.
    portal_product_id = SKU (SOL-prefixed internal code = self-mapping).
    Cancelled orders are excluded.
    """
    _CANCELLED = {"cancelled", "CANCELLED"}

    def parse_sales(self, path: Path) -> list[dict]:
        df = _clean(_read_file(path))
        rows = []
        for _, row in df.iterrows():
            status = str(row.get("Order Status", "")).strip()
            if status in self._CANCELLED:
                continue
            sku = str(row.get("SKU", "")).strip().lstrip("`")
            if not sku:
                continue
            # Selling Price is already the line-item total (not per-unit)
            revenue = _f(row.get("Selling Price", 0))
            rows.append({
                "portal": "easyecom",
                "sale_date": _parse_iso(row.get("Order Date")),
                "portal_product_id": sku,
                "city": str(row.get("Shipping City", "")).strip(),
                "l1_category": str(row.get("Category", "")).strip(),
                "l2_category": "",
                "l3_category": "",
                "revenue": revenue,
                "quantity_sold": _f(row.get("Item Quantity", 1)),
                "order_count": 1,
                "discount_amount": 0.0,
                "net_revenue": revenue,
            })
        return rows

    def parse_inventory(self, path: Path) -> list[dict]:
        return []


# =============================================================================
# Amazon PI
# =============================================================================

class AmazonPIParser:
    """
    Amazon PI (Vendor/PI dashboard) ASIN revenue report parser.
    Actual columns: asin, itemName, lbrBrandName, orderMonth, orderDay,
                    orderYear, orderAmt, orderQuantity, category, subcategory,
                    stateName, postalCode.
    City-level data is not available; stateName is used as a location proxy.
    portal_product_id = asin.
    """

    def parse_sales(self, path: Path) -> list[dict]:
        df = _clean(_read_file(path))
        rows = []
        for _, row in df.iterrows():
            asin = str(row.get("asin", "")).strip()
            if not asin or asin.lower() == "nan":
                continue
            try:
                sale_date = date(
                    int(float(str(row.get("orderYear", 2000)))),
                    int(float(str(row.get("orderMonth", 1)))),
                    int(float(str(row.get("orderDay", 1)))),
                )
            except Exception:
                sale_date = None
            revenue = _f(row.get("orderAmt", 0))
            qty = _f(row.get("orderQuantity", 0))
            rows.append({
                "portal": "amazon_pi",
                "sale_date": sale_date,
                "portal_product_id": asin,
                # stateName (e.g. "GUJARAT") used as location; no city-level data
                "city": str(row.get("stateName", "")).strip(),
                "l1_category": str(row.get("category", "")).strip(),
                "l2_category": str(row.get("subcategory", "")).strip(),
                "l3_category": "",
                "revenue": revenue,
                "quantity_sold": qty,
                "order_count": _i(row.get("orderQuantity", 1)),
                "discount_amount": 0.0,
                "net_revenue": revenue,
            })
        return rows

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
