from datetime import datetime
from typing import Optional
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
