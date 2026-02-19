from sqlalchemy import (
    Column, Integer, String, Date, DateTime, Decimal,
    ForeignKey, Text, func, UniqueConstraint, CheckConstraint,
)
from sqlalchemy.orm import relationship
from ..database import Base


class InventoryData(Base):
    __tablename__ = "inventory_data"

    id                 = Column(Integer, primary_key=True)
    portal_id          = Column(Integer, ForeignKey("portals.id"),    nullable=False)
    city_id            = Column(Integer, ForeignKey("cities.id"))
    warehouse_id       = Column(Integer, ForeignKey("warehouses.id"))
    product_id         = Column(Integer, ForeignKey("products.id"),   nullable=False)
    snapshot_date      = Column(Date,    nullable=False)
    stock_quantity     = Column(Decimal(12, 2), nullable=False, default=0)
    reserved_quantity  = Column(Decimal(12, 2), nullable=False, default=0)
    available_quantity = Column(Decimal(12, 2), nullable=False, default=0)
    unsellable_units   = Column(Decimal(12, 2))
    aged_90_plus_units = Column(Decimal(12, 2))
    oos_percentage     = Column(Decimal(5, 2))
    lead_time_days     = Column(Integer)
    created_at         = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at         = Column(DateTime, onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("portal_id", "warehouse_id", "product_id", "snapshot_date"),
        CheckConstraint("stock_quantity >= 0"),
        CheckConstraint("available_quantity >= 0"),
    )

    portal    = relationship("Portal",    back_populates="inventory")
    city      = relationship("City",      back_populates="inventory")
    warehouse = relationship("Warehouse", back_populates="inventory")
    product   = relationship("Product",   back_populates="inventory")


class ScrapingLog(Base):
    __tablename__ = "scraping_logs"

    id                = Column(Integer, primary_key=True)
    portal_id         = Column(Integer, ForeignKey("portals.id"))
    scrape_date       = Column(Date, nullable=False)
    start_time        = Column(DateTime, server_default=func.now(), nullable=False)
    end_time          = Column(DateTime)
    status            = Column(String(20), nullable=False, default="running")
    records_processed = Column(Integer, default=0)
    error_message     = Column(Text)
    file_path         = Column(String(500))
    created_at        = Column(DateTime, server_default=func.now(), nullable=False)

    portal = relationship("Portal", back_populates="logs")
