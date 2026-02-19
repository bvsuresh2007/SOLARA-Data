from sqlalchemy import (
    Column, Integer, String, Boolean, Date, DateTime,
    Decimal, ForeignKey, func, UniqueConstraint, CheckConstraint,
)
from sqlalchemy.orm import relationship
from ..database import Base


class Product(Base):
    __tablename__ = "products"

    id           = Column(Integer, primary_key=True)
    sku_code     = Column(String(100), unique=True, nullable=False)
    product_name = Column(String(255), nullable=False)
    category_id  = Column(Integer, ForeignKey("product_categories.id", ondelete="SET NULL"))
    unit_type    = Column(String(50))
    created_at   = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at   = Column(DateTime, onupdate=func.now())

    category  = relationship("ProductCategory", back_populates="products")
    sales     = relationship("SalesData",            back_populates="product")
    inventory = relationship("InventoryData",         back_populates="product")
    mappings  = relationship("ProductPortalMapping",  back_populates="product")


class ProductPortalMapping(Base):
    __tablename__ = "product_portal_mapping"

    id                  = Column(Integer, primary_key=True)
    product_id          = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    portal_id           = Column(Integer, ForeignKey("portals.id",  ondelete="CASCADE"), nullable=False)
    portal_product_id   = Column(String(200), nullable=False)
    portal_product_name = Column(String(255))
    is_active           = Column(Boolean, default=True, nullable=False)
    created_at          = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at          = Column(DateTime, onupdate=func.now())

    __table_args__ = (UniqueConstraint("portal_id", "portal_product_id"),)

    product = relationship("Product", back_populates="mappings")
    portal  = relationship("Portal",  back_populates="mappings")


class SalesData(Base):
    __tablename__ = "sales_data"

    id              = Column(Integer, primary_key=True)
    portal_id       = Column(Integer, ForeignKey("portals.id"),   nullable=False)
    city_id         = Column(Integer, ForeignKey("cities.id"))
    product_id      = Column(Integer, ForeignKey("products.id"),  nullable=False)
    sale_date       = Column(Date, nullable=False)
    quantity_sold   = Column(Decimal(12, 2), nullable=False, default=0)
    revenue         = Column(Decimal(12, 2), nullable=False, default=0)
    discount_amount = Column(Decimal(12, 2), nullable=False, default=0)
    net_revenue     = Column(Decimal(12, 2), nullable=False, default=0)
    order_count     = Column(Integer, default=0)
    created_at      = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at      = Column(DateTime, onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("portal_id", "city_id", "product_id", "sale_date"),
        CheckConstraint("quantity_sold >= 0"),
        CheckConstraint("revenue >= 0"),
    )

    portal  = relationship("Portal",  back_populates="sales")
    city    = relationship("City",    back_populates="sales")
    product = relationship("Product", back_populates="sales")
