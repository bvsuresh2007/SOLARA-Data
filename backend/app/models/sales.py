from sqlalchemy import (
    Column, Integer, String, Boolean, Date, DateTime,
    Numeric, ForeignKey, func, UniqueConstraint, CheckConstraint,
)
from sqlalchemy.orm import relationship
from ..database import Base


class Product(Base):
    __tablename__ = "products"

    id           = Column(Integer, primary_key=True)
    sku_code     = Column(String(100), unique=True, nullable=False)
    product_name = Column(String(500), nullable=False)
    category_id  = Column(Integer, ForeignKey("product_categories.id", ondelete="SET NULL"))
    default_asp  = Column(Numeric(10, 2))           # BAU ASP from master Excel
    unit_type    = Column(String(50), default="pieces")
    created_at   = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at   = Column(DateTime, onupdate=func.now())

    category      = relationship("ProductCategory",    back_populates="products")
    daily_sales   = relationship("DailySales",         back_populates="product")
    city_sales    = relationship("CityDailySales",     back_populates="product")
    inventory     = relationship("InventorySnapshot",  back_populates="product")
    targets       = relationship("MonthlyTargets",     back_populates="product")
    mappings      = relationship("ProductPortalMapping", back_populates="product")


class ProductPortalMapping(Base):
    __tablename__ = "product_portal_mapping"

    id                  = Column(Integer, primary_key=True)
    product_id          = Column(Integer, ForeignKey("products.id",  ondelete="CASCADE"), nullable=False)
    portal_id           = Column(Integer, ForeignKey("portals.id",   ondelete="CASCADE"), nullable=False)
    portal_sku          = Column(String(500), nullable=False)   # ASIN / Swiggy Code / Style ID / FSN / EAN
    portal_product_name = Column(String(500))
    is_active           = Column(Boolean, default=True, nullable=False)
    created_at          = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at          = Column(DateTime, onupdate=func.now())

    __table_args__ = (UniqueConstraint("portal_id", "portal_sku"),)

    product = relationship("Product", back_populates="mappings")
    portal  = relationship("Portal",  back_populates="mappings")


class DailySales(Base):
    """
    Grain: (portal, product, date)
    Source: master Excel daily columns.
    Primary sales table — no city breakdown.
    """
    __tablename__ = "daily_sales"

    id          = Column(Integer, primary_key=True)
    portal_id   = Column(Integer, ForeignKey("portals.id"),   nullable=False)
    product_id  = Column(Integer, ForeignKey("products.id"),  nullable=False)
    sale_date   = Column(Date, nullable=False)
    units_sold  = Column(Numeric(12, 2), nullable=False, default=0)
    asp         = Column(Numeric(10, 2))          # average selling price
    revenue     = Column(Numeric(14, 2))          # units_sold × asp (stored explicitly)
    data_source = Column(String(30), nullable=False, default="excel")
    imported_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("portal_id", "product_id", "sale_date"),
        CheckConstraint("units_sold >= 0"),
    )

    portal  = relationship("Portal",  back_populates="daily_sales")
    product = relationship("Product", back_populates="daily_sales")


class CityDailySales(Base):
    """
    Grain: (portal, product, city, date)
    Source: portal CSV exports (city-level detail).
    Supplementary table for geographic breakdown.
    """
    __tablename__ = "city_daily_sales"

    id              = Column(Integer, primary_key=True)
    portal_id       = Column(Integer, ForeignKey("portals.id"),   nullable=False)
    product_id      = Column(Integer, ForeignKey("products.id"),  nullable=False)
    city_id         = Column(Integer, ForeignKey("cities.id"),    nullable=False)
    sale_date       = Column(Date, nullable=False)
    units_sold      = Column(Numeric(12, 2), nullable=False, default=0)
    mrp             = Column(Numeric(10, 2))
    selling_price   = Column(Numeric(10, 2))
    revenue         = Column(Numeric(14, 2))          # GMV
    discount_amount = Column(Numeric(12, 2), default=0)
    net_revenue     = Column(Numeric(14, 2))
    order_count     = Column(Integer, default=0)
    data_source     = Column(String(30), nullable=False, default="portal_csv")
    imported_at     = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("portal_id", "product_id", "city_id", "sale_date"),
        CheckConstraint("units_sold >= 0"),
    )

    portal  = relationship("Portal",  back_populates="city_sales")
    product = relationship("Product", back_populates="city_sales")
    city    = relationship("City",    back_populates="city_sales")
