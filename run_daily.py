"""SOLARA full daily scraper pipeline.

This is the pipeline the "SOLARA Daily Scraper" Windows task runs (via
run_scrapers.bat). It reproduces the manual dailyrun that had been run by hand
while run_scrapers.bat was missing.

Pipeline (NO EasyEcom — standing rule; WH stock is authoritative from Atlas):
  1. Amazon SP-API real-time sales (settled)  -> daily_sales
  2. Shopify re-pull (settles the target day) -> daily_sales + city_daily_sales
  3. Blinkit / Swiggy / Zepto sales + SOH      -> daily_sales + inventory_snapshots
  4. Atlas WH stock (ERPNext Bin, live)        -> inventory_snapshots.solara_stock (easyecom portal)
  5. Amazon PI city                             -> city_daily_sales
  6. Data Kiosk FC inventory (today-2, ~34h lag)-> inventory_snapshots.amazon_fc_stock

Design:
  - Each step is isolated: one step failing never aborts the rest.
  - Blinkit gets a SINGLE attempt (partnersbiz.com is behind Cloudflare and
    blocks on repeated fresh logins).
  - Target date defaults to yesterday (IST machine clock). FC targets today-2.
  - Logs to data/logs/daily_run_<date>.log; prints a one-line SUMMARY.

Usage:
  python run_daily.py                # yesterday
  python run_daily.py 2026-10-16     # explicit target date
  python run_daily.py --check        # validate imports + print plan; run nothing
"""
import importlib
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

os.chdir(Path(__file__).resolve().parent)
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv
load_dotenv(".env", override=True)

_args = sys.argv[1:]
CHECK = "--check" in _args
_dates = [a for a in _args if not a.startswith("--")]
D = date.fromisoformat(_dates[0]) if _dates else (date.today() - timedelta(days=1))
FC_DATE = date.today() - timedelta(days=2)  # Data Kiosk lags ~34h

Path("data/logs").mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[logging.FileHandler(f"data/logs/daily_run_{D}.log", encoding="utf-8")],
)
log = logging.getLogger("daily_run")
results: dict[str, str] = {}


def _say(msg):
    """print() that survives a closed stdout (some scraper imports close fd1)."""
    try:
        print(msg, flush=True)
    except Exception:
        pass
    log.info("%s", msg)


def step(name, fn):
    if CHECK:
        _say(f"  [plan] {name}")
        return
    log.info("=== STEP: %s (target %s) ===", name, D)
    try:
        results[name] = fn() or "OK"
        log.info("STEP %s -> %s", name, results[name])
    except Exception as e:  # never let one step abort the pipeline
        results[name] = f"ERR {e}"
        log.exception("STEP %s FAILED", name)


# ---------------- step implementations ----------------
def _amazon_sales():
    from scrapers.amazon_sp_api_scraper import AmazonSPAPIScraper
    from ingest_daily import ingest_amazon_sp_api
    r = AmazonSPAPIScraper().run(D)
    if r.get("status") == "success":
        ingest_amazon_sp_api(D)
        return f"OK {r.get('total_units')}u INR{r.get('total_revenue', 0) / 1e5:.1f}L"
    return f"scrape {r.get('status')}: {r.get('error')}"


def _shopify():
    from scrapers.hourly_shopify_sync import sync
    sync(D)
    return "OK"


def _qcomm(portal, ScraperCls, soh_ingest_name):
    def run():
        from ingest_daily import ingest as ingest_sales
        soh_fn = getattr(importlib.import_module("ingest_daily"), soh_ingest_name)
        r = ScraperCls(headless=True).run(D)
        parts = [f"scrape={r.get('status')}"]

        def _find(kind, exts):
            for e in exts:
                p = Path(f"data/raw/{portal}/{portal}_{kind}_{D}.{e}")
                if p.exists():
                    return p
            return None

        sp = _find("sales", ["xlsx", "csv"])
        parts.append("sales=OK" if sp and (ingest_sales(portal, str(sp)) or True) else "sales=NOFILE")
        shp = _find("soh", ["csv", "xlsx"])
        parts.append("soh=OK" if shp and (soh_fn(str(shp), D) or True) else "soh=NOFILE")
        return " ".join(parts)
    return run


def _atlas():
    from scrapers.atlas_wh_stock_sync import sync
    r = sync()
    return f"OK {r.get('rows')}SKUs {int(r.get('total_units', 0))}u" if isinstance(r, dict) else "OK"


def _amazon_pi():
    from scrapers.amazon_pi_scraper import AmazonPIScraper
    from ingest_daily import ingest_amazon_pi
    try:
        from scrapers.profile_sync import download_profile, upload_profile
    except ImportError:
        from profile_sync import download_profile, upload_profile
    sc = AmazonPIScraper(headless=False)
    ok = False
    try:
        download_profile("amazon_pi")
        sc._init_browser()
        sc.login()
        ok = True
        sc.download_report(D)
    finally:
        try:
            sc._close_browser()
        except Exception:
            pass
        if ok:
            try:
                upload_profile("amazon_pi")
            except Exception:
                pass
    ingest_amazon_pi(D)
    return "OK"


def _fc():
    from scrapers.amazon_inventory_sync import sync
    r = sync(FC_DATE)
    return str(r.get("status")) if isinstance(r, dict) else "OK"


if CHECK:
    _say(f"DAILY RUN plan - target {D}, FC target {FC_DATE}")
    for m in ("scrapers.amazon_sp_api_scraper", "scrapers.hourly_shopify_sync",
              "scrapers.blinkit_scraper", "scrapers.swiggy_scraper", "scrapers.zepto_scraper",
              "scrapers.atlas_wh_stock_sync", "scrapers.amazon_pi_scraper",
              "scrapers.amazon_inventory_sync", "ingest_daily"):
        try:
            importlib.import_module(m)
            _say(f"  import OK: {m}")
        except Exception as e:
            _say(f"  import FAIL: {m} :: {e}")

log.info("######## DAILY RUN target=%s FC=%s ########", D, FC_DATE)
step("amazon_sales", _amazon_sales)
step("shopify", _shopify)
from scrapers.blinkit_scraper import BlinkitScraper
from scrapers.swiggy_scraper import SwiggyScraper
from scrapers.zepto_scraper import ZeptoScraper
step("blinkit", _qcomm("blinkit", BlinkitScraper, "ingest_blinkit_soh"))
step("swiggy", _qcomm("swiggy", SwiggyScraper, "ingest_swiggy_soh"))
step("zepto", _qcomm("zepto", ZeptoScraper, "ingest_zepto_soh"))
step("atlas_wh", _atlas)
step("amazon_pi", _amazon_pi)
step("datakiosk_fc", _fc)

summary = " | ".join(f"{k}={v}" for k, v in results.items())
if not CHECK:
    log.info("SUMMARY %s: %s", D, summary)
    try:
        Path(f"data/logs/daily_run_{D}_summary.txt").write_text(f"{D}: {summary}\n", encoding="utf-8")
    except Exception:
        pass
_say(f"DAILY_RUN {D} COMPLETE :: {summary or '(check mode - nothing run)'}")
