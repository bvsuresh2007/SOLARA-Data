from datetime import date
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, Field


# ─── Request bodies ──────────────────────────────────────────────────────────

class DailySalesRow(BaseModel):
    portal_id:  int
    product_id: int
    sale_date:  date
    units_sold: Decimal = Field(ge=0)
    asp:        Optional[Decimal] = None
    revenue:    Optional[Decimal] = None
    data_source: str = "excel_upload"


class DailySalesImportIn(BaseModel):
    rows: List[DailySalesRow]


class InventorySnapshotRow(BaseModel):
    portal_id:      int
    product_id:     int
    snapshot_date:  date
    portal_stock:   Optional[Decimal] = None
    backend_stock:  Optional[Decimal] = None
    frontend_stock: Optional[Decimal] = None
    solara_stock:   Optional[Decimal] = None
    amazon_fc_stock: Optional[Decimal] = None
    open_po:        Optional[Decimal] = None
    doc:            Optional[Decimal] = None


class InventoryImportIn(BaseModel):
    rows: List[InventorySnapshotRow]


# ─── Response bodies ──────────────────────────────────────────────────────────

class DuplicateKey(BaseModel):
    portal_id:  int
    product_id: int
    date:       date


class ImportResult(BaseModel):
    inserted:   int
    duplicates: List[DuplicateKey] = []
