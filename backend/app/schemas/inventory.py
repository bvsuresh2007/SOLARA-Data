from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel


class InventoryDataOut(BaseModel):
    id: int
    portal_id: int
    city_id: Optional[int]
    warehouse_id: Optional[int]
    product_id: int
    snapshot_date: date
    stock_quantity: Decimal
    reserved_quantity: Decimal
    available_quantity: Decimal
    unsellable_units: Optional[Decimal]
    aged_90_plus_units: Optional[Decimal]
    oos_percentage: Optional[Decimal]
    lead_time_days: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class InventorySummary(BaseModel):
    product_id: int
    product_name: str
    sku_code: str
    total_stock: Decimal
    total_available: Decimal
    total_reserved: Decimal
    portal_count: int


class ScrapingLogOut(BaseModel):
    id: int
    portal_id: Optional[int]
    scrape_date: date
    start_time: datetime
    end_time: Optional[datetime]
    status: str
    records_processed: int
    error_message: Optional[str]
    file_path: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
