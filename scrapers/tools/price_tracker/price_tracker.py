"""
Solara Price Tracker — daily orchestrator.

Reads the product list from the 'Products' tab in Google Sheets, runs all four
price scrapers (Amazon, Zepto, Blinkit, Swiggy) in sequence, appends today's
price columns to each platform tab, and posts a Slack summary.
"""

from __future__ import annotations

import csv
import logging
import multiprocessing
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

# Directory where per-platform CSV files are saved
OUTPUT_DIR = Path(r"C:\Users\accou\SOLARA-Data")

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Slack helpers
# ---------------------------------------------------------------------------

def _slack(webhook_url: str, text: str) -> None:
    try:
        import requests
        resp = requests.post(webhook_url, json={"text": text}, timeout=10)
        if resp.status_code != 200:
            logger.warning("[PriceTracker] Slack post failed: %s", resp.text)
    except Exception as exc:
        logger.warning("[PriceTracker] Slack error: %s", exc)


def _resolve_channel_id(bot_token: str, channel: str) -> str:
    """Return the Slack channel ID for a given name or ID. Returns the input unchanged if already an ID."""
    import requests
    if channel.startswith("C") and channel.isupper() or (len(channel) > 5 and channel[0] == "C" and channel[1:].isalnum()):
        return channel  # already an ID
    headers = {"Authorization": f"Bearer {bot_token}"}
    cursor = None
    while True:
        params = {"limit": 200, "exclude_archived": "true", "types": "public_channel,private_channel"}
        if cursor:
            params["cursor"] = cursor
        try:
            r = requests.get("https://slack.com/api/conversations.list", headers=headers, params=params, timeout=30)
            data = r.json()
        except Exception as exc:
            logger.warning("[PriceTracker] conversations.list network error: %s — using channel as-is", exc)
            return channel
        if not data.get("ok"):
            logger.warning("[PriceTracker] conversations.list failed: %s", data.get("error"))
            return channel
        for ch in data.get("channels", []):
            if ch.get("name") == channel.lstrip("#"):
                return ch["id"]
        cursor = data.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
    logger.warning("[PriceTracker] Channel '%s' not found — using as-is", channel)
    return channel


def _slack_upload_files(bot_token: str, channel: str, file_paths: list[Path], report_date: date) -> None:
    """
    Upload CSV files to a Slack channel using the Slack SDK files_upload_v2.
    """
    import time
    try:
        from slack_sdk import WebClient
    except ImportError:
        logger.warning("[PriceTracker] slack_sdk not installed — skipping CSV upload. Run: pip install slack_sdk")
        return

    channel_id = _resolve_channel_id(bot_token, channel)
    client = WebClient(token=bot_token)

    for path in file_paths:
        if not path.exists():
            logger.warning("[PriceTracker] Slack upload: file not found — %s", path)
            continue
        try:
            resp = client.files_upload_v2(
                channel=channel_id,
                file=str(path),
                filename=path.name,
                title=path.name,
            )
            if resp.get("ok"):
                logger.info("[PriceTracker] Slack: uploaded %s", path.name)
            else:
                logger.warning("[PriceTracker] Slack upload failed for %s: %s", path.name, resp.get("error"))
        except Exception as exc:
            logger.warning("[PriceTracker] Slack upload error for %s: %s", path.name, exc)
        time.sleep(3)


# ---------------------------------------------------------------------------
# Per-platform scrapers
# ---------------------------------------------------------------------------

def _scrape_amazon(products: list[dict], headless: bool = True) -> list[dict[str, Any]]:
    asins = [(p["sku"], p["name"], p["asin"]) for p in products if p.get("asin")]
    if not asins:
        logger.info("[PriceTracker] Amazon: no ASINs configured — skipping")
        return []

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from amazon_asin_scraper.scraper import AmazonScraper

    scraper = AmazonScraper(marketplace="in", headless=headless)
    results = []
    try:
        for sku, name, asin in asins:
            try:
                data = scraper.scrape(asin)
                all_bsr_str = ""
                if data.all_bsr:
                    all_bsr_str = " | ".join(str(b) for b in data.all_bsr)
                results.append({
                    "sku":              sku,
                    "name":             name,
                    "asin":             asin,
                    "price":            data.price,
                    "price_value":      data.price_value,
                    "bsr_value":        data.bsr_value,
                    "bsr_category":     data.bsr_category,
                    "sub_bsr_value":    data.sub_bsr_value,
                    "sub_bsr_category": data.sub_bsr_category,
                    "all_bsr":          all_bsr_str,
                    "seller":           data.seller,
                    "ships_from":       data.ships_from,
                    "error":            data.error,
                })
                if data.error:
                    logger.warning("[Amazon] %s (%s): %s", sku, asin, data.error)
                else:
                    logger.info("[Amazon] %s (%s): price=%.2f, BSR=%s",
                                sku, asin, data.price_value or 0, data.bsr_value)
            except Exception as exc:
                logger.error("[Amazon] %s (%s) failed: %s", sku, asin, exc)
                results.append({"sku": sku, "name": name, "asin": asin, "price": None, "price_value": None, "bsr_value": None, "bsr_category": None, "sub_bsr_value": None, "sub_bsr_category": None, "all_bsr": None, "seller": None, "ships_from": None, "error": str(exc)})
            time.sleep(1)
    finally:
        scraper.close()  # Always close to free the Playwright event loop

    return results


def _is_valid_url(val: str) -> bool:
    """Return True if val looks like a real URL (not '0', empty, or placeholder)."""
    return bool(val) and val not in ("0", "N/A", "-", "n/a") and val.startswith("http")


def _scrape_zepto(products: list[dict], headless: bool = True) -> list[dict[str, Any]]:
    items = [(p["sku"], p["name"], p["zepto_url"]) for p in products if _is_valid_url(p.get("zepto_url", ""))]
    if not items:
        logger.info("[PriceTracker] Zepto: no URLs configured — skipping")
        return []

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from zepto_price_scraper.zepto_scraper import ZeptoScraper

    scraper = ZeptoScraper(headless=headless)
    results = []
    try:
        for sku, name, url in items:
            try:
                data = scraper.scrape(url)
                results.append({
                    "sku":          sku,
                    "name":         name,
                    "zepto_url":    url,
                    "price":        getattr(data, "price", None),
                    "price_value":  data.price_value,
                    "mrp":          data.mrp,
                    "mrp_value":    data.mrp_value,
                    "discount":     data.discount,
                    "brand":        data.brand,
                    "availability": data.availability or ("In Stock" if data.price_value else "Out of Stock"),
                    "pincode":      getattr(scraper, "pincode", ""),
                    "error":        data.error,
                })
                logger.info("[Zepto] %s: price=%s, mrp=%s", sku, data.price_value, data.mrp_value)
            except Exception as exc:
                logger.error("[Zepto] %s failed: %s", sku, exc)
                results.append({"sku": sku, "name": name, "zepto_url": url, "price": None, "price_value": None, "mrp": None, "mrp_value": None, "discount": None, "brand": None, "availability": None, "pincode": "", "error": str(exc)})
            time.sleep(1)
    finally:
        scraper.close()  # Always close to free the Playwright event loop

    return results


def _scrape_blinkit(products: list[dict], headless: bool = True) -> list[dict[str, Any]]:
    items = [(p["sku"], p["name"], p["blinkit_id"]) for p in products if _is_valid_url(p.get("blinkit_id", ""))]
    if not items:
        logger.info("[PriceTracker] Blinkit: no IDs configured — skipping")
        return []

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from blinkit_price_scraper.blinkit_scraper import BlinkitScraper

    scraper = BlinkitScraper(headless=headless)
    results = []
    try:
        for sku, name, product_id in items:
            try:
                data = scraper.scrape(product_id)
                results.append({
                    "sku":         sku,
                    "name":        name,
                    "blinkit_id":  product_id,
                    "price":       data.price,
                    "price_value": data.price_value,
                    "mrp":         data.mrp,
                    "mrp_value":   data.mrp_value,
                    "discount":    data.discount,
                    "brand":       data.brand,
                    "in_stock":    data.in_stock,
                    "error":       data.error,
                })
                logger.info("[Blinkit] %s: price=%s, mrp=%s", sku, data.price_value, data.mrp_value)
            except Exception as exc:
                logger.error("[Blinkit] %s failed: %s", sku, exc)
                results.append({"sku": sku, "name": name, "blinkit_id": product_id, "price": None, "price_value": None, "mrp": None, "mrp_value": None, "discount": None, "brand": None, "in_stock": False, "error": str(exc)})
            time.sleep(1)
    finally:
        scraper.close()  # Always close to free the Playwright event loop

    return results


def _scrape_swiggy(products: list[dict], headless: bool = True) -> list[dict[str, Any]]:
    items = [(p["sku"], p["name"], p["swiggy_url"]) for p in products if _is_valid_url(p.get("swiggy_url", ""))]
    if not items:
        logger.info("[PriceTracker] Swiggy: no URLs configured — skipping")
        return []

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from swiggy_price_scraper.swiggy_scraper import SwiggyInstamartScraper

    scraper = SwiggyInstamartScraper(headless=headless)
    results = []
    try:
        for sku, name, url in items:
            try:
                data = scraper.scrape(url)
                results.append({
                    "sku":          sku,
                    "name":         name,
                    "swiggy_url":   url,
                    "price":        data.price,
                    "price_value":  data.price_value,
                    "mrp":          data.mrp,
                    "mrp_value":    data.mrp_value,
                    "discount":     data.discount,
                    "brand":        data.brand,
                    "availability": data.availability or ("In Stock" if data.price_value else "Out of Stock"),
                    "pincode":      getattr(scraper, "pincode", ""),
                    "error":        data.error,
                })
                logger.info("[Swiggy] %s: price=%s, mrp=%s", sku, data.price_value, data.mrp_value)
            except Exception as exc:
                logger.error("[Swiggy] %s failed: %s", sku, exc)
                results.append({"sku": sku, "name": name, "swiggy_url": url, "price": None, "price_value": None, "mrp": None, "mrp_value": None, "discount": None, "brand": None, "availability": None, "pincode": "", "error": str(exc)})
            time.sleep(1)
    finally:
        scraper.close()  # Always close to free the Playwright event loop

    return results


# ---------------------------------------------------------------------------
# CSV export helpers
# ---------------------------------------------------------------------------

def _extract_platform_id(url: str, platform: str) -> str:
    """Extract the platform-specific product ID from a URL."""
    if not url:
        return ""
    try:
        parts = url.rstrip("/").split("/")
        if platform == "blinkit":
            # https://blinkit.com/prn/-/prid/719142
            return parts[-1]
        elif platform == "swiggy":
            # https://www.swiggy.com/instamart/item/KTXSH4R7SM
            return parts[-1]
        elif platform == "zepto":
            # https://www.zepto.com/pn/.../pvid/UUID?...
            if "pvid" in parts:
                return parts[parts.index("pvid") + 1].split("?")[0]
            return parts[-1].split("?")[0]
    except Exception:
        pass
    return url


def _save_csv(platform: str, results: list[dict], report_date: date) -> None:
    """Save scraped results to a per-platform CSV in OUTPUT_DIR."""
    if not results:
        return
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = OUTPUT_DIR / f"{platform.lower()}_prices_{report_date}.csv"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if platform == "Amazon":
        fieldnames = [
            "ASIN", "Title", "Price", "Price_Value", "BSR_Rank", "BSR_Category",
            "Sub_BSR_Rank", "Sub_BSR_Category", "All_BSR", "Seller", "Ships_From",
            "Fulfilled_By", "URL", "Error", "Scraped_At",
        ]
        rows = [
            {
                "ASIN":             r.get("asin", ""),
                "Title":            r.get("name", ""),
                "Price":            r.get("price") or "",
                "Price_Value":      r.get("price_value") or "",
                "BSR_Rank":         r.get("bsr_value") or "",
                "BSR_Category":     r.get("bsr_category") or "",
                "Sub_BSR_Rank":     r.get("sub_bsr_value") or "",
                "Sub_BSR_Category": r.get("sub_bsr_category") or "",
                "All_BSR":          r.get("all_bsr") or "",
                "Seller":           r.get("seller") or "",
                "Ships_From":       r.get("ships_from") or "",
                "Fulfilled_By":     "",
                "URL":              f"https://www.amazon.in/dp/{r.get('asin', '')}",
                "Error":            r.get("error") or "",
                "Scraped_At":       now,
            }
            for r in results
        ]

    elif platform == "Blinkit":
        fieldnames = [
            "Product_ID", "Title", "Price", "Price_Value", "MRP", "MRP_Value",
            "Discount", "Quantity", "Brand", "In_Stock", "URL", "Error", "Scraped_At",
        ]
        rows = [
            {
                "Product_ID":  _extract_platform_id(r.get("blinkit_id", ""), "blinkit"),
                "Title":       r.get("name", ""),
                "Price":       r.get("price") or "",
                "Price_Value": r.get("price_value") or "",
                "MRP":         r.get("mrp") or "",
                "MRP_Value":   r.get("mrp_value") or "",
                "Discount":    r.get("discount") or "",
                "Quantity":    "",
                "Brand":       r.get("brand") or "",
                "In_Stock":    "Yes" if r.get("in_stock") else "No",
                "URL":         r.get("blinkit_id", ""),
                "Error":       r.get("error") or "",
                "Scraped_At":  now,
            }
            for r in results
        ]

    elif platform in ("Swiggy", "Zepto"):
        url_key = "swiggy_url" if platform == "Swiggy" else "zepto_url"
        fieldnames = [
            "Product_ID", "Name", "MRP", "Selling_Price", "Discount",
            "Brand", "Quantity", "Availability", "Pincode", "URL", "Scraped_At",
        ]
        rows = [
            {
                "Product_ID":    _extract_platform_id(r.get(url_key, ""), platform.lower()),
                "Name":          r.get("name", ""),
                "MRP":           r.get("mrp") or "",
                "Selling_Price": r.get("price") or "",
                "Discount":      r.get("discount") or "",
                "Brand":         r.get("brand") or "",
                "Quantity":      "",
                "Availability":  r.get("availability") or ("In Stock" if r.get("price_value") else "Out of Stock"),
                "Pincode":       r.get("pincode") or "",
                "URL":           r.get(url_key, ""),
                "Scraped_At":    now,
            }
            for r in results
        ]
    else:
        return

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    logger.info("[PriceTracker] Saved %d rows → %s", len(rows), filename)


# ---------------------------------------------------------------------------
# Subprocess isolation (prevents asyncio event loop conflicts between scrapers)
# ---------------------------------------------------------------------------

def _run_scraper_isolated(fn, products: list[dict], headless: bool) -> list[dict]:
    """
    Run a scraper function in an isolated subprocess.

    Each Playwright scraper leaves asyncio event loop state in the process.
    Running each platform in its own subprocess guarantees a clean event loop
    for every scraper, regardless of what previous scrapers did.
    """
    with multiprocessing.Pool(processes=1) as pool:
        return pool.apply(fn, (products, headless))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run(report_date: date | None = None, headless: bool = True) -> dict:
    """
    Full price-tracker run. Returns a summary dict.
    """
    if report_date is None:
        date_str = os.environ.get("INPUT_REPORT_DATE", "").strip()
        if date_str:
            report_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        else:
            report_date = date.today()

    slack_url = os.environ.get("SLACK_WEBHOOK_URL", "")
    logger.info("[PriceTracker] Running for %s", report_date)

    # --- Connect to Sheets ---
    from sheets_client import get_sheets_client, open_or_create_sheet, read_products, append_price_columns

    client = get_sheets_client()
    spreadsheet, sheet_url = open_or_create_sheet(client)
    logger.info("[PriceTracker] Sheet: %s", sheet_url)

    # --- Read products ---
    products = read_products(spreadsheet)
    if not products:
        msg = (
            f":warning: *Price Tracker — {report_date}*\n"
            f"No products found in the Products tab.\n"
            f"Please fill in the product list: <{sheet_url}|Open Sheet>"
        )
        if slack_url:
            _slack(slack_url, msg)
        logger.warning("[PriceTracker] No products — aborting")
        return {"status": "no_products", "sheet_url": sheet_url}

    # --- Scrape each platform ---
    summary: dict[str, dict] = {}

    _only_platforms = [p.strip().lower() for p in os.environ.get("INPUT_PLATFORMS", "").split(",") if p.strip()]

    for platform, scrape_fn in [
        ("Amazon",  _scrape_amazon),
        ("Zepto",   _scrape_zepto),
        ("Blinkit", _scrape_blinkit),
        ("Swiggy",  _scrape_swiggy),
    ]:
        if _only_platforms and platform.lower() not in _only_platforms:
            continue
        logger.info("[PriceTracker] Starting %s...", platform)
        try:
            results = _run_scraper_isolated(scrape_fn, products, headless)
            errors = sum(1 for r in results if r.get("error"))
            ok = len(results) - errors
            summary[platform] = {"scraped": ok, "errors": errors, "total": len(results)}

            if results:
                append_price_columns(spreadsheet, platform, report_date, results)
                _save_csv(platform, results, report_date)

        except Exception as exc:
            logger.error("[PriceTracker] %s platform failed: %s", platform, exc)
            summary[platform] = {"scraped": 0, "errors": 0, "total": 0, "failed": str(exc)}

    # --- Slack summary ---
    lines = [f":white_check_mark: *Price Tracker \u2014 {report_date}*"]
    platform_icons = {"Amazon": ":package:", "Zepto": ":green_circle:", "Blinkit": ":yellow_circle:", "Swiggy": ":orange_circle:"}
    bullet = "\u2022"
    for platform, s in summary.items():
        icon = platform_icons.get(platform, bullet)
        if "failed" in s:
            lines.append(f"{icon} *{platform}*: failed \u2014 {s['failed'][:80]}")
        elif s["total"] == 0:
            lines.append(f"{icon} *{platform}*: skipped (no products configured)")
        else:
            err_str = f", {s['errors']} error{'s' if s['errors'] != 1 else ''}" if s["errors"] else ""
            lines.append(f"{icon} *{platform}*: {s['scraped']} scraped{err_str}")
    lines.append(f":bar_chart: <{sheet_url}|Open Sheet>")

    slack_msg = "\n".join(lines)
    logger.info("[PriceTracker] Done.\n%s", slack_msg)

    if slack_url:
        _slack(slack_url, slack_msg)

    # Upload CSVs to the price-tracker Slack channel
    bot_token = os.environ.get("SLACK_BOT_TOKEN", "")
    upload_channel = os.environ.get("SLACK_PRICE_TRACKER_CHANNEL", "amazon-solara-india")
    if bot_token:
        csv_files = [
            OUTPUT_DIR / f"amazon_prices_{report_date}.csv",
            OUTPUT_DIR / f"zepto_prices_{report_date}.csv",
            OUTPUT_DIR / f"blinkit_prices_{report_date}.csv",
            OUTPUT_DIR / f"swiggy_prices_{report_date}.csv",
        ]
        _slack_upload_files(bot_token, upload_channel, csv_files, report_date)
    else:
        logger.warning("[PriceTracker] SLACK_BOT_TOKEN not set — skipping CSV upload")

    return {"status": "success", "summary": summary, "sheet_url": sheet_url}
