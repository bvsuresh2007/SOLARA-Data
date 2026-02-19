"""
Shopify scraper — uses Shopify Admin API (no Playwright needed).
Fetches orders for a given date and saves them as CSV.
"""
import csv
import os
from datetime import date, timedelta
from pathlib import Path

import requests

from .base_scraper import logger


class ShopifyScraper:
    """
    Shopify uses REST API instead of browser automation.
    No BaseScraper inheritance needed.
    """
    portal_name = "shopify"

    def __init__(self, raw_data_path: str = None):
        self.raw_data_path = Path(raw_data_path or os.getenv("RAW_DATA_PATH", "./data/raw"))
        self.portal_data_path = self.raw_data_path / self.portal_name
        self.portal_data_path.mkdir(parents=True, exist_ok=True)

        self.api_key     = os.environ["SHOPIFY_API_KEY"]
        self.api_secret  = os.environ["SHOPIFY_API_SECRET"]
        self.store_url   = os.environ["SHOPIFY_STORE_URL"].rstrip("/")
        self.api_version = "2024-04"

    @property
    def _base_url(self) -> str:
        return f"https://{self.api_key}:{self.api_secret}@{self.store_url}/admin/api/{self.api_version}"

    def _get_orders(self, created_at_min: str, created_at_max: str) -> list[dict]:
        orders = []
        url = f"{self._base_url}/orders.json"
        params = {
            "status": "any",
            "created_at_min": created_at_min,
            "created_at_max": created_at_max,
            "limit": 250,
            "fields": "id,created_at,line_items,subtotal_price,total_price,total_discounts,total_tax,shipping_lines,billing_address,shipping_address,financial_status",
        }
        while url:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            orders.extend(data.get("orders", []))
            # Pagination via Link header
            link = resp.headers.get("Link", "")
            url = None
            params = None
            for part in link.split(","):
                if 'rel="next"' in part:
                    url = part.split(";")[0].strip().strip("<>")
        return orders

    def _flatten_orders(self, orders: list[dict]) -> list[dict]:
        rows = []
        for order in orders:
            shipping = sum(float(s.get("price", 0)) for s in order.get("shipping_lines", []))
            city = (order.get("billing_address") or order.get("shipping_address") or {}).get("city", "")
            for item in order.get("line_items", []):
                rows.append({
                    "Created at": order["created_at"],
                    "Lineitem sku": item.get("sku", ""),
                    "Lineitem quantity": item.get("quantity", 0),
                    "Subtotal": order.get("subtotal_price", 0),
                    "Total": order.get("total_price", 0),
                    "Discount Amount": order.get("total_discounts", 0),
                    "Taxes": order.get("total_tax", 0),
                    "Shipping": shipping,
                    "Billing City": city,
                    "Financial Status": order.get("financial_status", ""),
                })
        return rows

    def run(self, report_date: date = None) -> dict:
        if report_date is None:
            report_date = date.today() - timedelta(days=1)

        result = {"portal": self.portal_name, "date": report_date, "file": None, "status": "failed", "error": None}
        try:
            start = f"{report_date}T00:00:00+05:30"
            end   = f"{report_date}T23:59:59+05:30"
            logger.info("[Shopify] Fetching orders for %s", report_date)
            orders = self._get_orders(start, end)
            rows   = self._flatten_orders(orders)

            output_path = self.portal_data_path / f"shopify_sales_{report_date}.csv"
            if rows:
                with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                    writer.writeheader()
                    writer.writerows(rows)

            result.update({"file": output_path, "status": "success", "records": len(rows)})
            logger.info("[Shopify] Saved %d rows to %s", len(rows), output_path)
        except Exception as exc:
            logger.error("[Shopify] Failed: %s", exc)
            result["error"] = str(exc)
        return result
