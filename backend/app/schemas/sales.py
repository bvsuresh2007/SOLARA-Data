from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List
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
    city_id: Optional[int]
    product_id: int
    sale_date: date
    units_sold: Decimal
    revenue: Optional[Decimal]
    discount_amount: Optional[Decimal]
    net_revenue: Optional[Decimal]
    order_count: Optional[int]
    imported_at: datetime

    class Config:
        from_attributes = True


class SalesSummary(BaseModel):
    total_revenue: Decimal
    total_net_revenue: Decimal
    total_quantity: Decimal
    total_orders: int
    total_discount: Decimal
    record_count: int


class SalesByDimension(BaseModel):
    dimension_id: int
    dimension_name: str
    total_revenue: Decimal
    total_net_revenue: Decimal
    total_quantity: Decimal
    total_orders: int
    record_count: int
