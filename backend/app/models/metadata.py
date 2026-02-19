from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from ..database import Base


class Portal(Base):
    __tablename__ = "portals"

    id           = Column(Integer, primary_key=True)
    name         = Column(String(50), unique=True, nullable=False)
    display_name = Column(String(100), nullable=False)
    is_active    = Column(Boolean, default=True, nullable=False)
    created_at   = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at   = Column(DateTime, onupdate=func.now())

    sales      = relationship("SalesData",      back_populates="portal")
    inventory  = relationship("InventoryData",  back_populates="portal")
    warehouses = relationship("Warehouse",      back_populates="portal")
    logs       = relationship("ScrapingLog",    back_populates="portal")
    mappings   = relationship("ProductPortalMapping", back_populates="portal")


class City(Base):
    __tablename__ = "cities"

    id         = Column(Integer, primary_key=True)
    name       = Column(String(100), nullable=False)
    state      = Column(String(100))
    region     = Column(String(50))
    is_active  = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now())

    sales     = relationship("SalesData",     back_populates="city")
    inventory = relationship("InventoryData", back_populates="city")


class Warehouse(Base):
    __tablename__ = "warehouses"

    id         = Column(Integer, primary_key=True)
    name       = Column(String(200), nullable=False)
    code       = Column(String(100))
    portal_id  = Column(Integer, ForeignKey("portals.id", ondelete="SET NULL"))
    city_id    = Column(Integer, ForeignKey("cities.id",  ondelete="SET NULL"))
    is_active  = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now())

    portal    = relationship("Portal", back_populates="warehouses")
    inventory = relationship("InventoryData", back_populates="warehouse")


class ProductCategory(Base):
    __tablename__ = "product_categories"

    id         = Column(Integer, primary_key=True)
    l1_name    = Column(String(100), nullable=False)
    l2_name    = Column(String(100))
    l3_name    = Column(String(100))
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    products = relationship("Product", back_populates="category")
