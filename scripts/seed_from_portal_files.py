"""
Build product catalog and portal mappings from individual portal CSV files.
No master Excel needed.

Sources (in order of reliability):
  EasyEcom CSVs  → SOL-SKU product catalog + easyecom mapping
  Shopify CSVs   → confirm/extend shopify mapping (Lineitem sku = SOL-SKU)
  Amazon PI CSVs → ASIN → product name  → name-matched to EasyEcom
  Zepto CSVs     → EAN  → SKU Name      → name-matched to EasyEcom
  Blinkit CSVs   → item_id → item_name  → name-matched to EasyEcom
  Swiggy CSVs    → ITEM_CODE → PRODUCT_NAME → name-matched to EasyEcom

Name matching:
  Uses token-based overlap coefficient after normalisation (lowercase, strip
  punctuation, drop brand word "solara").  score = |A∩B| / min(|A|,|B|).
  This handles the common case where the portal name is shorter than the
  EasyEcom name — Jaccard would penalise the extra tokens in the longer name.
  Match threshold = 0.55.  All matches < 0.70 are flagged as LOW_CONFIDENCE.

Output:
  - Upserts products + product_portal_mapping into Supabase
  - Writes data/source/mapping_gaps.csv with unmatched / low-confidence items

Usage:
    python scripts/seed_from_portal_files.py
    python scripts/seed_from_portal_files.py --data-dir ./data/raw --report ./mapping_gaps.csv
"""
import argparse
import glob
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Name normalisation & matching
# ---------------------------------------------------------------------------

_STOPWORDS = {"solara", "for", "with", "and", "the", "a", "an", "of", "in",
              "to", "by", "is", "on", "at", "box", "pack", "set", "piece",
              "pieces", "pcs", "upto", "up", "use", "uses", "high", "speed",
              "circulation", "air", "capacity", "preset", "menus", "touch",
              "control", "digital", "home", "kitchen", "cooking", "less",
              "fat", "warranty", "year", "1", "2", "3", "4", "5", "6",
              "grill", "roast", "bake", "reheat", "fry"}

def _tokens(name: str) -> set[str]:
    """Normalise a product name into a set of meaningful tokens."""
    name = str(name).lower()
    name = re.sub(r"[^\w\s]", " ", name)   # remove punctuation
    name = re.sub(r"\s+", " ", name).strip()
    tokens = set(name.split()) - _STOPWORDS
    # Also keep numeric tokens that appear as part of larger strings (e.g. "4.5l")
    tokens = {re.sub(r"[^0-9a-z]", "", t) for t in tokens if t}
    tokens.discard("")
    return tokens


def _overlap(a: str, b: str) -> tuple[float, int]:
    """
    Token overlap coefficient: |A∩B| / min(|A|, |B|).
    Also returns raw intersection size as a tiebreaker.
    """
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0, 0
    inter = len(ta & tb)
    return inter / min(len(ta), len(tb)), inter


def best_match(query: str, candidates: dict[str, str], threshold: float = 0.55
               ) -> tuple[str | None, float]:
    """
    Find the candidate key whose value best matches the query name.
    Uses overlap coefficient; ties broken by raw intersection size.
    Returns (best_key, score) or (None, 0.0) if nothing passes threshold.
    """
    best_key, best_score, best_inter = None, 0.0, 0
    for key, name in candidates.items():
        score, inter = _overlap(query, name)
        if score > best_score or (score == best_score and inter > best_inter):
            best_key, best_score, best_inter = key, score, inter
    if best_score < threshold:
        return None, best_score
    return best_key, best_score


# ---------------------------------------------------------------------------
# File readers
# ---------------------------------------------------------------------------

def _read(path: str | Path, **kwargs) -> pd.DataFrame:
    """Auto-detect CSV vs real XLSX by magic bytes."""
    path = Path(path)
    with open(path, "rb") as fh:
        magic = fh.read(2)
    if magic == b"PK":
        return pd.read_excel(path, dtype=str, **kwargs)
    for enc in ("utf-8-sig", "latin1", "cp1252"):
        try:
            return pd.read_csv(path, dtype=str, encoding=enc, **kwargs)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Cannot read file: {path}")


def _latest_files(portal_dir: Path, exts=(".csv", ".xlsx", ".xls")) -> list[Path]:
    """Return the single most-recently-modified sales file for a portal dir."""
    files = [f for f in portal_dir.iterdir()
             if f.is_file() and f.suffix.lower() in exts]
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return files


# ---------------------------------------------------------------------------
# Source 1 – EasyEcom: build product catalog
# ---------------------------------------------------------------------------

def load_easyecom_products(data_dir: Path) -> dict[str, dict]:
    """
    Returns {sku_code: {"name": ..., "category": ...}} from all EasyEcom CSVs.
    """
    ee_dir = data_dir / "easyecom"
    files = _latest_files(ee_dir) if ee_dir.exists() else []
    if not files:
        logger.warning("No EasyEcom files found in %s", ee_dir)
        return {}

    dfs = []
    for f in files:
        try:
            df = _read(f)
            df = df[df["Order Status"].fillna("").str.upper() != "CANCELLED"]
            dfs.append(df)
        except Exception as e:
            logger.warning("Could not read %s: %s", f.name, e)

    if not dfs:
        return {}

    df = pd.concat(dfs, ignore_index=True)
    # Strip leading backticks that EasyEcom adds to some SKUs
    df["SKU"] = df["SKU"].str.strip().str.lstrip("`")

    products: dict[str, dict] = {}
    for _, row in df.iterrows():
        sku = str(row.get("SKU", "")).strip()
        if not sku or not sku.upper().startswith("SOL-"):
            continue
        if sku not in products:
            name = str(row.get("Product Name", "")).strip()
            category = str(row.get("Category", "")).strip()
            products[sku] = {"name": name, "category": category}
    logger.info("EasyEcom: %d unique SOL-SKUs loaded", len(products))
    return products


# ---------------------------------------------------------------------------
# Source 2 – Amazon PI: ASIN → product name
# ---------------------------------------------------------------------------

def load_amazon_pi_skus(data_dir: Path) -> dict[str, str]:
    """Returns {asin: item_name} from all Amazon PI XLSX files."""
    amz_dir = data_dir / "amazon_pi"
    result: dict[str, str] = {}
    if not amz_dir.exists():
        return result

    # Amazon PI files are in date subdirs
    for date_dir in sorted(amz_dir.iterdir()):
        if not date_dir.is_dir():
            continue
        for f in date_dir.glob("*.xlsx"):
            try:
                df = _read(f)
                for _, row in df.iterrows():
                    asin = str(row.get("asin", "")).strip()
                    name = str(row.get("itemName", "")).strip()
                    if asin and name and asin not in result:
                        result[asin] = name
            except Exception as e:
                logger.warning("Amazon PI read error %s: %s", f.name, e)

    logger.info("Amazon PI: %d unique ASINs loaded", len(result))
    return result


# ---------------------------------------------------------------------------
# Source 3 – Zepto: EAN → SKU Name
# ---------------------------------------------------------------------------

def load_zepto_skus(data_dir: Path) -> dict[str, str]:
    """Returns {ean: sku_name}."""
    zepto_dir = data_dir / "zepto"
    result: dict[str, str] = {}
    if not zepto_dir.exists():
        return result

    for f in _latest_files(zepto_dir):
        try:
            df = _read(f)
            for _, row in df.iterrows():
                ean = str(row.get("EAN", "")).strip()
                name = str(row.get("SKU Name", "")).strip()
                if ean and name and ean not in result:
                    result[ean] = name
        except Exception as e:
            logger.warning("Zepto read error %s: %s", f.name, e)
        break  # only latest file

    logger.info("Zepto: %d unique EANs loaded", len(result))
    return result


# ---------------------------------------------------------------------------
# Source 4 – Blinkit: item_id → item_name
# ---------------------------------------------------------------------------

def load_blinkit_skus(data_dir: Path) -> dict[str, str]:
    """Returns {item_id: item_name}."""
    bl_dir = data_dir / "blinkit"
    result: dict[str, str] = {}
    if not bl_dir.exists():
        return result

    for f in _latest_files(bl_dir):
        try:
            df = _read(f)
            for _, row in df.iterrows():
                item_id = str(row.get("item_id", "")).strip()
                if item_id.endswith(".0"):
                    item_id = item_id[:-2]
                name = str(row.get("item_name", "")).strip()
                if item_id and name and item_id not in result:
                    result[item_id] = name
        except Exception as e:
            logger.warning("Blinkit read error %s: %s", f.name, e)
        break

    logger.info("Blinkit: %d unique item_ids loaded", len(result))
    return result


# ---------------------------------------------------------------------------
# Source 5 – Swiggy: ITEM_CODE → PRODUCT_NAME
# ---------------------------------------------------------------------------

def load_swiggy_skus(data_dir: Path) -> dict[str, str]:
    """Returns {item_code: product_name}."""
    sw_dir = data_dir / "swiggy"
    result: dict[str, str] = {}
    if not sw_dir.exists():
        return result

    for f in _latest_files(sw_dir):
        try:
            df = _read(f)
            for _, row in df.iterrows():
                code = str(row.get("ITEM_CODE", "")).strip()
                if code.endswith(".0"):
                    code = code[:-2]
                name = str(row.get("PRODUCT_NAME", "")).strip()
                if code and name and code not in result:
                    result[code] = name
        except Exception as e:
            logger.warning("Swiggy read error %s: %s", f.name, e)
        break

    logger.info("Swiggy: %d unique ITEM_CODEs loaded", len(result))
    return result


# ---------------------------------------------------------------------------
# DB operations
# ---------------------------------------------------------------------------

def _seed_products_and_mappings(
    products: dict[str, dict],
    portal_skus: dict[str, dict[str, str]],  # {portal_name: {portal_sku: sku_code}}
    report_rows: list[dict],
) -> None:
    from scripts.db_utils import get_session, get_or_create_category, get_or_create_product, \
        get_portal_id, upsert_portal_mapping
    from sqlalchemy import text

    with get_session() as session:
        # 1. Ensure easyecom + amazon_pi portals exist
        session.execute(text("""
            INSERT INTO portals (name, display_name) VALUES
                ('easyecom',  'EasyEcom'),
                ('amazon_pi', 'Amazon PI')
            ON CONFLICT (name) DO NOTHING
        """))
        session.commit()

        # 2. Upsert products
        sku_to_id: dict[str, int] = {}
        for sku, data in products.items():
            cat_id = get_or_create_category(session, "Kitchen & Dining", data.get("category") or None)
            product_id = get_or_create_product(
                session,
                sku_code=sku,
                product_name=data["name"],
                category_id=cat_id,
                default_asp=None,
            )
            sku_to_id[sku] = product_id
        session.commit()
        logger.info("Upserted %d products.", len(sku_to_id))

        # 3. Upsert portal mappings
        total_mapped = 0
        for portal_name, mappings in portal_skus.items():
            portal_id = get_portal_id(session, portal_name)
            if portal_id is None:
                logger.warning("Portal '%s' not found in DB — skipping.", portal_name)
                continue
            for portal_sku, sku_code in mappings.items():
                product_id = sku_to_id.get(sku_code)
                if product_id is None:
                    logger.warning("[%s] No product_id for SOL-SKU %s", portal_name, sku_code)
                    continue
                upsert_portal_mapping(
                    session, product_id, portal_id,
                    portal_sku=portal_sku,
                    portal_product_name=products[sku_code]["name"],
                )
                total_mapped += 1
        session.commit()
        logger.info("Upserted %d portal mappings total.", total_mapped)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(data_dir: Path, report_path: Path) -> None:
    data_dir = Path(data_dir)

    # ── Step 1: Build product catalog from EasyEcom ──────────────────────
    ee_products = load_easyecom_products(data_dir)
    if not ee_products:
        logger.error("No EasyEcom products found — cannot build catalog. Aborting.")
        return

    # Lookup table: sku_code → name (for matching)
    ee_name_lookup: dict[str, str] = {sku: d["name"] for sku, d in ee_products.items()}

    # ── Step 2: Build portal mapping dicts ───────────────────────────────
    #   portal_skus[portal_name] = {portal_sku: sku_code}
    portal_skus: dict[str, dict[str, str]] = {
        "easyecom": {},
        "shopify":  {},
        "amazon":   {},
        "amazon_pi":{},
        "zepto":    {},
        "blinkit":  {},
        "swiggy":   {},
    }

    # EasyEcom: self-mapping (SOL-SKU → SOL-SKU)
    for sku in ee_products:
        portal_skus["easyecom"][sku] = sku
        portal_skus["shopify"][sku] = sku   # Shopify also uses SOL-SKU

    report_rows: list[dict] = []

    def _match_and_add(portal_name: str, portal_sku_map: dict[str, str],
                       threshold_warn: float = 0.70) -> None:
        """Match portal_sku_map {portal_sku: product_name} against EasyEcom names."""
        for portal_sku, pname in portal_sku_map.items():
            best_sku, score = best_match(pname, ee_name_lookup)
            if best_sku:
                portal_skus[portal_name][portal_sku] = best_sku
                if score < threshold_warn:
                    report_rows.append({
                        "portal": portal_name,
                        "portal_sku": portal_sku,
                        "portal_name": pname,
                        "matched_sol_sku": best_sku,
                        "matched_name": ee_name_lookup[best_sku],
                        "score": round(score, 3),
                        "status": "LOW_CONFIDENCE",
                    })
            else:
                report_rows.append({
                    "portal": portal_name,
                    "portal_sku": portal_sku,
                    "portal_name": pname,
                    "matched_sol_sku": "",
                    "matched_name": "",
                    "score": round(score, 3),
                    "status": "UNMATCHED",
                })

    # Amazon PI: ASIN → product name → match
    amz_skus = load_amazon_pi_skus(data_dir)
    _match_and_add("amazon", amz_skus)
    # Amazon PI mirrors amazon ASIN mappings
    portal_skus["amazon_pi"] = dict(portal_skus["amazon"])

    # Zepto: EAN → SKU name → match
    zepto_skus = load_zepto_skus(data_dir)
    _match_and_add("zepto", zepto_skus)

    # Blinkit: item_id → item_name → match
    bl_skus = load_blinkit_skus(data_dir)
    _match_and_add("blinkit", bl_skus)

    # Swiggy: ITEM_CODE → PRODUCT_NAME → match
    sw_skus = load_swiggy_skus(data_dir)
    _match_and_add("swiggy", sw_skus)

    # ── Step 3: Summary ──────────────────────────────────────────────────
    for portal, mapping in portal_skus.items():
        logger.info("  %-12s → %d mappings", portal, len(mapping))

    unmatched = [r for r in report_rows if r["status"] == "UNMATCHED"]
    low_conf = [r for r in report_rows if r["status"] == "LOW_CONFIDENCE"]
    logger.info("Matching gaps: %d unmatched, %d low-confidence", len(unmatched), len(low_conf))

    # ── Step 4: Write to DB ──────────────────────────────────────────────
    _seed_products_and_mappings(ee_products, portal_skus, report_rows)

    # ── Step 5: Save gaps report ─────────────────────────────────────────
    if report_rows:
        report_path = Path(report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(report_rows).to_csv(report_path, index=False)
        logger.info("Gaps report saved to %s (%d items)", report_path, len(report_rows))
    else:
        logger.info("All products matched with high confidence.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed product mappings from individual portal files.")
    parser.add_argument("--data-dir", default="./data/raw", help="Root data directory")
    parser.add_argument("--report", default="data/source/mapping_gaps.csv", help="Path for gaps report CSV")
    args = parser.parse_args()
    run(Path(args.data_dir), Path(args.report))
