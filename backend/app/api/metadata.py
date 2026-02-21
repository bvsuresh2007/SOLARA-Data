from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.metadata import Portal, City, Warehouse
from ..models.inventory import ImportLog
from ..schemas.metadata import PortalOut, CityOut, WarehouseOut
from ..schemas.inventory import ImportLogOut

router = APIRouter()


@router.get("/portals", response_model=List[PortalOut])
def list_portals(active_only: bool = True, db: Session = Depends(get_db)):
    q = db.query(Portal)
    if active_only:
        q = q.filter(Portal.is_active == True)
    return q.order_by(Portal.name).all()


@router.get("/cities", response_model=List[CityOut])
def list_cities(
    active_only: bool = True,
    region: str = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(City)
    if active_only:
        q = q.filter(City.is_active == True)
    if region:
        q = q.filter(City.region == region)
    return q.order_by(City.name).all()


@router.get("/warehouses", response_model=List[WarehouseOut])
def list_warehouses(
    portal_id: int = Query(None),
    city_id: int = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Warehouse).filter(Warehouse.is_active == True)
    if portal_id:
        q = q.filter(Warehouse.portal_id == portal_id)
    if city_id:
        q = q.filter(Warehouse.city_id == city_id)
    return q.order_by(Warehouse.name).all()


@router.get("/scraping-logs", response_model=List[ImportLogOut])
def list_scraping_logs(
    portal_id: int = Query(None),
    status: str = Query(None),
    limit: int = Query(50, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(ImportLog)
    if portal_id:
        q = q.filter(ImportLog.portal_id == portal_id)
    if status:
        q = q.filter(ImportLog.status == status)
    return q.order_by(ImportLog.created_at.desc()).limit(limit).all()
