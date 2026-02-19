from fastapi import APIRouter
from .metadata import router as metadata_router
from .sales import router as sales_router
from .inventory import router as inventory_router

api_router = APIRouter()
api_router.include_router(metadata_router, prefix="/metadata", tags=["Metadata"])
api_router.include_router(sales_router,    prefix="/sales",    tags=["Sales"])
api_router.include_router(inventory_router, prefix="/inventory", tags=["Inventory"])
