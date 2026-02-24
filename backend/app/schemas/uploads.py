"""
Pydantic schemas for the file upload API.
"""
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class UploadFileType(str, Enum):
    MASTER_EXCEL = "master_excel"
    BLINKIT_SALES = "blinkit_sales"
    BLINKIT_INVENTORY = "blinkit_inventory"
    SWIGGY_SALES = "swiggy_sales"
    SWIGGY_INVENTORY = "swiggy_inventory"
    ZEPTO_SALES = "zepto_sales"
    ZEPTO_INVENTORY = "zepto_inventory"
    AMAZON_PI = "amazon_pi"
    SHOPIFY_SALES = "shopify_sales"


FILE_TYPE_META: dict[str, dict] = {
    UploadFileType.MASTER_EXCEL: {
        "label": "Master Excel (All Portals)",
        "description": "SOLARA Daily Sales Tracking FY 25-26.xlsx — multi-sheet workbook covering all portals",
        "target_tables": ["daily_sales", "inventory_snapshots", "monthly_targets", "monthly_ad_spend"],
    },
    UploadFileType.BLINKIT_SALES: {
        "label": "Blinkit Sales CSV",
        "description": "Blinkit portal daily sales export with item_id, date, quantity, city columns",
        "target_tables": ["city_daily_sales", "daily_sales"],
    },
    UploadFileType.BLINKIT_INVENTORY: {
        "label": "Blinkit Inventory CSV",
        "description": "Blinkit portal inventory snapshot with item_id, backend/frontend stock columns",
        "target_tables": ["inventory_snapshots"],
    },
    UploadFileType.SWIGGY_SALES: {
        "label": "Swiggy Sales CSV",
        "description": "Swiggy portal sales export with ITEM_CODE, date, GMV, area_name columns",
        "target_tables": ["city_daily_sales", "daily_sales"],
    },
    UploadFileType.SWIGGY_INVENTORY: {
        "label": "Swiggy Inventory CSV",
        "description": "Swiggy portal inventory snapshot with ITEM_CODE, date, stock columns",
        "target_tables": ["inventory_snapshots"],
    },
    UploadFileType.ZEPTO_SALES: {
        "label": "Zepto Sales CSV",
        "description": "Zepto portal sales export with SKU Number, Date (DD-MM-YYYY), Units, GMV, City columns",
        "target_tables": ["city_daily_sales", "daily_sales"],
    },
    UploadFileType.ZEPTO_INVENTORY: {
        "label": "Zepto Inventory CSV",
        "description": "Zepto portal inventory snapshot with SKU Number, Date, Units, City columns",
        "target_tables": ["inventory_snapshots"],
    },
    UploadFileType.AMAZON_PI: {
        "label": "Amazon PI ASIN Revenue Report",
        "description": "Amazon PI ASIN-wise revenue and unit sales report (xlsx/csv)",
        "target_tables": ["daily_sales"],
    },
    UploadFileType.SHOPIFY_SALES: {
        "label": "Shopify Orders CSV",
        "description": "Shopify orders export with Lineitem sku, Created at, Lineitem quantity, Subtotal columns",
        "target_tables": ["daily_sales"],
    },
}


class FileTypeInfo(BaseModel):
    value: str
    label: str
    description: str
    target_tables: list[str]


class UploadError(BaseModel):
    row: int
    reason: str


class UploadResult(BaseModel):
    file_type: str
    file_name: str
    rows_parsed: int
    inserted: int
    skipped: int
    errors: list[UploadError]
    import_log_id: Optional[int] = None
