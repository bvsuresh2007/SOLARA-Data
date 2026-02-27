from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict
from pydantic import BaseModel


class ProductOut(BaseModel):
    id: int
    sku_code: str
    product_name: str
    unit_type: Optional[str]

    class Config:
        from_attributes = True


class SalesDataOut(BaseModel):
    id: int
    portal_id: int
    city_id: Optional[int] = None
    product_id: int
    sale_date: date
    units_sold: Decimal
    asp: Optional[Decimal] = None
    revenue: Optional[Decimal] = None
    discount_amount: Optional[Decimal] = None
    net_revenue: Optional[Decimal] = None
    order_count: Optional[int] = None
    imported_at: datetime

    class Config:
        from_attributes = True


class SalesSummary(BaseModel):
    total_revenue: float
    total_net_revenue: Optional[float] = None   # not yet in DB schema
    total_quantity: float
    total_orders: Optional[int] = None          # not yet in DB schema
    total_discount: Optional[float] = None      # not yet in DB schema
    record_count: int


class SalesByDimension(BaseModel):
    dimension_id: int
    dimension_name: str
    sku_code: Optional[str] = None              # populated for product queries only
    total_revenue: float
    total_net_revenue: Optional[float] = None   # not yet in DB schema
    total_quantity: float
    total_orders: Optional[int] = None          # not yet in DB schema
    record_count: Optional[int] = None          # not yet in DB schema


class SalesTrend(BaseModel):
    date: str
    total_revenue: float
    total_quantity: float
    avg_asp: float


class SalesByCategory(BaseModel):
    category: str
    total_revenue: float
    total_quantity: float
    product_count: int


class TargetAchievement(BaseModel):
    portal_name: str
    target_revenue: float
    actual_revenue: float
    achievement_pct: float
    target_units: float
    actual_units: float


class PortalDailyRow(BaseModel):
    sku_code: str
    product_name: str
    category: str
    portal_sku: str
    bau_asp: Optional[float]
    wh_stock: Optional[float]
    daily_units: Dict[str, Optional[int]]   # "2026-02-01" → units (None = no sale)
    mtd_units: int
    mtd_value: float


class PortalDailyResponse(BaseModel):
    portal_name: str
    dates: List[str]            # ordered date strings in the requested range
    rows: List[PortalDailyRow]
