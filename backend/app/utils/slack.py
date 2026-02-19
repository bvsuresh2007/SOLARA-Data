"""
Slack notification utilities for SolaraDashboard.
Handles daily scraping reports, weekly summaries, low-stock alerts, and failure alerts.
"""
import json
import logging
from datetime import date
from typing import Optional
import requests

from ..config import settings

logger = logging.getLogger(__name__)


def _post(payload: dict) -> bool:
    if not settings.slack_webhook_url:
        logger.warning("SLACK_WEBHOOK_URL not configured; skipping notification")
        return False
    try:
        resp = requests.post(
            settings.slack_webhook_url,
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.error("Slack notification failed: %s", exc)
        return False


def notify_scraping_complete(
    scrape_date: date,
    results: list[dict],  # [{"portal": str, "records": int, "status": str, "duration_s": float}]
) -> bool:
    success = [r for r in results if r["status"] == "success"]
    failed  = [r for r in results if r["status"] != "success"]
    total   = sum(r.get("records", 0) for r in success)
    icon    = "✅" if not failed else "⚠️"

    lines = [
        f"{icon} *Daily Scraping Complete — {scrape_date}*",
        f"Portals Processed: {len(success)}/{len(results)}",
    ]
    for r in results:
        status_icon = "✓" if r["status"] == "success" else "✗"
        lines.append(f"  ├─ {r['portal']}: {r.get('records', 0):,} records {status_icon}")

    lines += [
        f"Total Records: {total:,}",
        f"Status: {'All Success ✓' if not failed else f'{len(failed)} portal(s) failed ✗'}",
    ]

    return _post({"text": "\n".join(lines)})


def notify_low_stock(
    portal: str,
    city: str,
    product_name: str,
    sku: str,
    available: float,
    threshold: float,
) -> bool:
    text = (
        f"⚠️ *Low Stock Alert*\n"
        f"Product: {product_name} (`{sku}`)\n"
        f"Portal: {portal} | City: {city}\n"
        f"Available Stock: {available:.0f} (Threshold: {threshold:.0f})\n"
        f"*Action Required: Restock immediately*"
    )
    return _post({"text": text})


def notify_scraping_failure(portal: str, scrape_date: date, error: str) -> bool:
    text = (
        f"🚨 *Scraping Failure*\n"
        f"Portal: {portal}\n"
        f"Date: {scrape_date}\n"
        f"Error: {error}"
    )
    return _post({"text": text})


def notify_weekly_summary(
    week_label: str,
    total_revenue: float,
    wow_pct: Optional[float],
    top_products: list[dict],
    top_cities: list[dict],
) -> bool:
    wow_str = f"+{wow_pct:.1f}% 📈" if wow_pct and wow_pct >= 0 else (f"{wow_pct:.1f}% 📉" if wow_pct else "N/A")
    lines = [
        f"📊 *Weekly Sales Report — {week_label}*",
        f"Total Revenue: ₹{total_revenue:,.0f}",
        f"Week-over-Week: {wow_str}",
        "",
        "*Top Products:*",
    ]
    for i, p in enumerate(top_products[:5], 1):
        lines.append(f"{i}. {p['name']} — ₹{p['revenue']:,.0f}")
    lines += ["", "*Top Cities:*"]
    for i, c in enumerate(top_cities[:5], 1):
        lines.append(f"{i}. {c['name']} — ₹{c['revenue']:,.0f}")

    return _post({"text": "\n".join(lines)})
