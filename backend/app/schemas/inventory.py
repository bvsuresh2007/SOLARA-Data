from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel


class InventorySnapshotOut(BaseModel):
    id: int
    portal_id: int
    product_id: int
    snapshot_date: date
    portal_stock: Optional[Decimal]
    backend_stock: Optional[Decimal]
    frontend_stock: Optional[Decimal]
    solara_stock: Optional[Decimal]
    amazon_fc_stock: Optional[Decimal]
    open_po: Optional[Decimal]
    doc: Optional[Decimal]
    imported_at: datetime

    class Config:
        from_attributes = True


# Keep old name as alias so existing imports don't break immediately
InventoryDataOut = InventorySnapshotOut


class InventorySummary(BaseModel):
    product_id: int
    product_name: str
    sku_code: str
    total_portal_stock: Optional[Decimal]
    portal_count: int


class ImportLogOut(BaseModel):
    id: int
    source_type: str
    portal_id: Optional[int]
    sheet_name: Optional[str]
    file_name: Optional[str]
    import_date: date
    start_time: datetime
    end_time: Optional[datetime]
    status: str
    records_imported: int
    error_message: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# Keep old name as alias so existing imports don't break immediately
ScrapingLogOut = ImportLogOut
