from sqlalchemy import (
    Column, Integer, String, SmallInteger, Date, DateTime,
    Numeric, ForeignKey, Text, func, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from ..database import Base


class InventorySnapshot(Base):
    """
    Grain: (portal, product, snapshot_date)
    One snapshot per portal per SKU per month-end.
    Covers: portal WH stock, Solara WH, Amazon FC, Blinkit backend/frontend, DOC, open PO.
    """
    __tablename__ = "inventory_snapshots"

    id              = Column(Integer, primary_key=True)
    portal_id       = Column(Integer, ForeignKey("portals.id"),   nullable=False)
    product_id      = Column(Integer, ForeignKey("products.id"),  nullable=False)
    snapshot_date   = Column(Date, nullable=False)
    # Portal warehouse stock
    portal_stock    = Column(Numeric(12, 2))    # Zepto / Swiggy / Myntra / Flipkart
    backend_stock   = Column(Numeric(12, 2))    # Blinkit backend inventory
    frontend_stock  = Column(Numeric(12, 2))    # Blinkit frontend inventory
    # Solara's own warehouse
    solara_stock    = Column(Numeric(12, 2))    # Inventory in Solara WH
    amazon_fc_stock = Column(Numeric(12, 2))    # Amazon FC inventory
    # Planning metrics
    open_po         = Column(Numeric(12, 2))    # Open purchase orders (units)
    doc             = Column(Numeric(8, 2))     # Days of coverage
    imported_at     = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("portal_id", "product_id", "snapshot_date"),
    )

    portal  = relationship("Portal",  back_populates="inventory")
    product = relationship("Product", back_populates="inventory")


class MonthlyTargets(Base):
    """
    Monthly sales targets per portal per product.
    Primarily populated from Amazon AZ IN sheets; extensible to other portals.
    """
    __tablename__ = "monthly_targets"

    id              = Column(Integer, primary_key=True)
    portal_id       = Column(Integer, ForeignKey("portals.id"),   nullable=False)
    product_id      = Column(Integer, ForeignKey("products.id"),  nullable=False)
    year            = Column(SmallInteger, nullable=False)
    month           = Column(SmallInteger, nullable=False)
    target_units    = Column(Numeric(12, 2))
    target_revenue  = Column(Numeric(14, 2))
    target_drr      = Column(Numeric(10, 2))    # target daily run rate
    achievement_pct = Column(Numeric(8, 4))     # actual / target (e.g. 1.048 = 104.8%)

    __table_args__ = (
        UniqueConstraint("portal_id", "product_id", "year", "month"),
    )

    portal  = relationship("Portal",  back_populates="targets")
    product = relationship("Product", back_populates="targets")


class MonthlyAdSpend(Base):
    """
    Ad spend and TACOS at (portal, month) grain.
    Sourced from the 'Total Ad Spend' / 'TACOS' metadata rows in each portal sheet.
    """
    __tablename__ = "monthly_ad_spend"

    id            = Column(Integer, primary_key=True)
    portal_id     = Column(Integer, ForeignKey("portals.id"), nullable=False)
    year          = Column(SmallInteger, nullable=False)
    month         = Column(SmallInteger, nullable=False)
    total_revenue = Column(Numeric(14, 2))
    ad_spend      = Column(Numeric(14, 2))
    tacos_pct     = Column(Numeric(8, 4))    # TACOS %

    __table_args__ = (
        UniqueConstraint("portal_id", "year", "month"),
    )

    portal = relationship("Portal", back_populates="ad_spend")


class ImportLog(Base):
    """
    Audit log for all data import operations (Excel imports, scraper runs, CSV uploads).
    Replaces the old scraping_logs table.
    """
    __tablename__ = "import_logs"

    id               = Column(Integer, primary_key=True)
    source_type      = Column(String(30), nullable=False)   # 'excel_import' | 'portal_scraper' | 'portal_csv'
    portal_id        = Column(Integer, ForeignKey("portals.id"))
    sheet_name       = Column(String(200))     # which Excel sheet
    file_name        = Column(String(500))
    import_date      = Column(Date, nullable=False)
    start_time       = Column(DateTime, server_default=func.now(), nullable=False)
    end_time         = Column(DateTime)
    status           = Column(String(20), nullable=False, default="running")
    records_imported = Column(Integer, default=0)
    error_message    = Column(Text)
    created_at       = Column(DateTime, server_default=func.now(), nullable=False)

    portal = relationship("Portal", back_populates="import_logs")
