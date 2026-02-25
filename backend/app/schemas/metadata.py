from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class PortalOut(BaseModel):
    id: int
    name: str
    display_name: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class CityOut(BaseModel):
    id: int
    name: str
    state: Optional[str]
    region: Optional[str]
    is_active: bool

    class Config:
        from_attributes = True


class WarehouseOut(BaseModel):
    id: int
    name: str
    code: Optional[str]
    portal_id: Optional[int]
    city_id: Optional[int]
    is_active: bool

    class Config:
        from_attributes = True


class PortalImportHealth(BaseModel):
    portal_name: str
    display_name: str
    last_import_at: Optional[datetime] = None
    last_status: Optional[str] = None
    total_imports: int
    failed_runs: int


class PortalCoverage(BaseModel):
    portal_name: str
    display_name: str
    mapped_products: int
    total_products: int
    gap: int


class UnmappedProduct(BaseModel):
    product_id: int
    sku_code: str
    product_name: str
    missing_portals: str        # comma-separated display names (for display)
    missing_portal_slugs: str   # comma-separated slugs (for API calls)
    missing_count: int


class PortalSkuGap(BaseModel):
    portal: str
    portal_sku: str
    portal_name: str
    matched_sol_sku: str   # empty for UNMATCHED
    matched_name: str      # empty for UNMATCHED
    score: float
    status: str   # 'UNMATCHED' | 'LOW_CONFIDENCE'


class ActionItemsResponse(BaseModel):
    total_products: int
    import_health: List[PortalImportHealth]
    portal_coverage: List[PortalCoverage]
    unmapped_products: List[UnmappedProduct]
    portal_sku_gaps: List[PortalSkuGap]


# ---------- Mutation schemas ----------

class ImportFailure(BaseModel):
    id: int
    portal_name: Optional[str]
    display_name: Optional[str]
    file_name: Optional[str]
    import_date: str
    start_time: str
    error_message: Optional[str]
    source_type: str


class CreatePortalMappingRequest(BaseModel):
    portal_name: str
    portal_sku: str
    portal_product_name: Optional[str] = None
    # Option A — link to existing product
    product_id: Optional[int] = None
    # Option B — create new product first
    new_sku_code: Optional[str] = None
    new_product_name: Optional[str] = None
