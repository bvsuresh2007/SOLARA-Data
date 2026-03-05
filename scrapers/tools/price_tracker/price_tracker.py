"""
Solara Price Tracker — daily orchestrator.

Reads the product list from the 'Products' tab in Google Sheets, runs all four
price scrapers (Amazon, Zepto, Blinkit, Swiggy) in sequence, appends today's
price columns to each platform tab, and posts a Slack summary.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Slack helper
# ---------------------------------------------------------------------------

def _slack(webhook_url: str, text: str) -> None:
    try:
        import requests
        resp = requests.post(webhook_url, json={"text": text}, timeout=10)
        if resp.status_code != 200:
            logger.warning("[PriceTracker] Slack post failed: %s", resp.text)
    except Exception as exc:
        logger.warning("[PriceTracker] Slack error: %s", exc)


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
                results.append({
                    "sku":         sku,
                    "name":        name,
                    "asin":        asin,
                    "price_value": data.price_value,
                    "bsr_value":   data.bsr_value,
                    "error":       data.error,
                })
                logger.info("[Amazon] %s (%s): price=%.2f, BSR=%s",
                            sku, asin, data.price_value or 0, data.bsr_value)
            except Exception as exc:
                logger.error("[Amazon] %s (%s) failed: %s", sku, asin, exc)
                results.append({"sku": sku, "name": name, "asin": asin, "error": str(exc)})
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
                    "sku":         sku,
                    "name":        name,
                    "zepto_url":   url,
                    "price_value": data.price_value,
                    "mrp_value":   data.mrp_value,
                    "discount":    data.discount,
                    "error":       data.error,
                })
                logger.info("[Zepto] %s: price=%s, mrp=%s", sku, data.price_value, data.mrp_value)
            except Exception as exc:
                logger.error("[Zepto] %s failed: %s", sku, exc)
                results.append({"sku": sku, "name": name, "zepto_url": url, "error": str(exc)})
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
                    "price_value": data.price_value,
                    "mrp_value":   data.mrp_value,
                    "discount":    data.discount,
                    "error":       data.error,
                })
                logger.info("[Blinkit] %s: price=%s, mrp=%s", sku, data.price_value, data.mrp_value)
            except Exception as exc:
                logger.error("[Blinkit] %s failed: %s", sku, exc)
                results.append({"sku": sku, "name": name, "blinkit_id": product_id, "error": str(exc)})
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
                    "sku":         sku,
                    "name":        name,
                    "swiggy_url":  url,
                    "price_value": data.price_value,
                    "mrp_value":   data.mrp_value,
                    "discount":    data.discount,
                    "error":       data.error,
                })
                logger.info("[Swiggy] %s: price=%s, mrp=%s", sku, data.price_value, data.mrp_value)
            except Exception as exc:
                logger.error("[Swiggy] %s failed: %s", sku, exc)
                results.append({"sku": sku, "name": name, "swiggy_url": url, "error": str(exc)})
            time.sleep(1)
    finally:
        scraper.close()  # Always close to free the Playwright event loop

    return results


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

    for platform, scrape_fn in [
        ("Amazon",  _scrape_amazon),
        ("Zepto",   _scrape_zepto),
        ("Blinkit", _scrape_blinkit),
        ("Swiggy",  _scrape_swiggy),
    ]:
        logger.info("[PriceTracker] Starting %s...", platform)
        try:
            results = scrape_fn(products, headless=headless)
            errors = sum(1 for r in results if r.get("error"))
            ok = len(results) - errors
            summary[platform] = {"scraped": ok, "errors": errors, "total": len(results)}

            if results:
                append_price_columns(spreadsheet, platform, report_date, results)

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

    return {"status": "success", "summary": summary, "sheet_url": sheet_url}
