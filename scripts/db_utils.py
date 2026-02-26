"""
Shared database utilities for the importer scripts.
Uses the existing backend SessionLocal and config.
"""
import sys
import os
import logging
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import insert as pg_insert

# ---------------------------------------------------------------------------
# Build DB URL directly from environment / .env file
# Does NOT go through the backend Pydantic Settings (avoids extra-field errors
# and lru_cache stale-value issues).
# ---------------------------------------------------------------------------

def _load_env(project_root: str) -> None:
    """Load .env file into os.environ if not already set."""
    env_path = os.path.join(project_root, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.split("#")[0].strip()  # strip inline comments
            if key and key not in os.environ:
                os.environ[key] = val

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_load_env(_PROJECT_ROOT)

_DB_URL = os.environ.get("DATABASE_URL", "").strip()
if not _DB_URL:
    _pg_password = os.environ.get("POSTGRES_PASSWORD")
    if not _pg_password:
        raise RuntimeError(
            "POSTGRES_PASSWORD is not set. Add it to your .env file or environment."
        )
    _DB_URL = (
        f"postgresql://"
        f"{os.environ.get('POSTGRES_USER', 'solara_user')}:"
        f"{_pg_password}@"
        f"{os.environ.get('POSTGRES_HOST', 'localhost')}:"
        f"{os.environ.get('POSTGRES_PORT', '5432')}/"
        f"{os.environ.get('POSTGRES_DB', 'solara_dashboard')}"
    )

engine = create_engine(_DB_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

logger = logging.getLogger(__name__)


@contextmanager
def get_session():
    """Yield a SQLAlchemy session and ensure it is closed on exit."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def upsert(session, model, rows: list[dict], conflict_cols: list[str], update_cols: list[str]) -> int:
    """
    Bulk upsert rows into a SQLAlchemy model table.
    Uses PostgreSQL INSERT … ON CONFLICT DO UPDATE.
    Returns the number of rows processed.
    """
    if not rows:
        return 0

    stmt = pg_insert(model.__table__).values(rows)
    update_dict = {col: getattr(stmt.excluded, col) for col in update_cols}
    stmt = stmt.on_conflict_do_update(
        index_elements=conflict_cols,
        set_=update_dict,
    )
    session.execute(stmt)
    return len(rows)


# ---------------------------------------------------------------------------
# Cached lookup helpers
# ---------------------------------------------------------------------------

_portal_cache: dict[str, int] = {}
_category_cache: dict[tuple, int] = {}


def get_portal_id(session, name: str) -> int | None:
    """Return portal.id for a given portal name slug (cached)."""
    name = name.lower().strip()
    if name in _portal_cache:
        return _portal_cache[name]
    row = session.execute(
        text("SELECT id FROM portals WHERE name = :name"), {"name": name}
    ).fetchone()
    if row:
        _portal_cache[name] = row[0]
        return row[0]
    logger.warning(f"Portal not found: {name!r}")
    return None


def get_or_create_category(session, l1: str, l2: str | None = None) -> int:
    """
    Return product_categories.id for (l1_name, l2_name).
    Creates the row if it does not exist.
    """
    l1 = (l1 or "Uncategorised").strip()
    l2 = l2.strip() if l2 and str(l2).strip() not in ("", "nan", "None") else None
    key = (l1, l2)
    if key in _category_cache:
        return _category_cache[key]

    row = session.execute(
        text("""
            INSERT INTO product_categories (l1_name, l2_name)
            VALUES (:l1, :l2)
            ON CONFLICT (l1_name, COALESCE(l2_name, ''))
            DO UPDATE SET l1_name = EXCLUDED.l1_name
            RETURNING id
        """),
        {"l1": l1, "l2": l2},
    ).fetchone()
    session.flush()
    _category_cache[key] = row[0]
    return row[0]


def get_or_create_product(
    session,
    sku_code: str,
    product_name: str,
    category_id: int | None,
    default_asp: float | None,
) -> int:
    """
    Upsert a product row and return its id.
    Updates product_name, category_id, default_asp if the row already exists.
    """
    row = session.execute(
        text("""
            INSERT INTO products (sku_code, product_name, category_id, default_asp, updated_at)
            VALUES (:sku, :name, :cat, :asp, NOW())
            ON CONFLICT (sku_code)
            DO UPDATE SET
                product_name = EXCLUDED.product_name,
                category_id  = COALESCE(EXCLUDED.category_id, products.category_id),
                default_asp  = COALESCE(EXCLUDED.default_asp,  products.default_asp),
                updated_at   = NOW()
            RETURNING id
        """),
        {"sku": sku_code, "name": product_name, "cat": category_id, "asp": default_asp},
    ).fetchone()
    session.flush()
    return row[0]


def upsert_portal_mapping(
    session,
    product_id: int,
    portal_id: int,
    portal_sku: str,
    portal_product_name: str | None,
) -> None:
    """Upsert a product_portal_mapping row."""
    session.execute(
        text("""
            INSERT INTO product_portal_mapping
                (product_id, portal_id, portal_sku, portal_product_name, updated_at)
            VALUES (:pid, :portal, :sku, :name, NOW())
            ON CONFLICT (portal_id, portal_sku)
            DO UPDATE SET
                product_id          = EXCLUDED.product_id,
                portal_product_name = COALESCE(EXCLUDED.portal_product_name,
                                               product_portal_mapping.portal_product_name),
                updated_at          = NOW()
        """),
        {
            "pid": product_id,
            "portal": portal_id,
            "sku": portal_sku,
            "name": portal_product_name,
        },
    )


def upsert_portal_exclusion(session, product_id: int, portal_id: int) -> None:
    """Record that a product intentionally does not exist on a portal."""
    session.execute(
        text("""
            INSERT INTO product_portal_exclusions (product_id, portal_id)
            VALUES (:pid, :portal)
            ON CONFLICT (product_id, portal_id) DO NOTHING
        """),
        {"pid": product_id, "portal": portal_id},
    )


def get_product_id_by_sku(session, sku_code: str) -> int | None:
    """Look up products.id by sku_code. Returns None if not found."""
    row = session.execute(
        text("SELECT id FROM products WHERE sku_code = :sku"), {"sku": sku_code}
    ).fetchone()
    return row[0] if row else None


def log_import(
    session,
    source_type: str,
    portal_id: int | None,
    sheet_name: str | None,
    file_name: str,
    import_date: date,
    status: str,
    records_imported: int,
    start_time: datetime,
    error_message: str | None = None,
) -> None:
    """Write a row to import_logs."""
    session.execute(
        text("""
            INSERT INTO import_logs
                (source_type, portal_id, sheet_name, file_name, import_date,
                 start_time, end_time, status, records_imported, error_message)
            VALUES
                (:src, :portal, :sheet, :file, :idate,
                 :start, NOW(), :status, :records, :err)
        """),
        {
            "src": source_type,
            "portal": portal_id,
            "sheet": sheet_name,
            "file": file_name,
            "idate": import_date,
            "start": start_time,
            "status": status,
            "records": records_imported,
            "err": error_message,
        },
    )
