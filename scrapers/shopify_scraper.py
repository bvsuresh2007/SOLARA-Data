"""
Shopify scraper — uses Shopify Admin REST API with OAuth client credentials.

Fetches orders for a given date and saves them as CSV.
Auth: client_credentials grant → short-lived shpat_ token (24h).
No browser / Playwright needed.
"""
import csv
import os
from datetime import date, timedelta
from pathlib import Path

import requests

from .base_scraper import logger


class ShopifyScraper:
    """
    Fetches Shopify orders via REST API using OAuth client credentials.
    Replaces the EasyEcom path for Shopify sales data.
    """
    portal_name = "shopify"

    def __init__(self, raw_data_path: str = None):
        self.raw_data_path = Path(raw_data_path or os.getenv("RAW_DATA_PATH", "./data/raw"))
        self.portal_data_path = self.raw_data_path / self.portal_name
        self.portal_data_path.mkdir(parents=True, exist_ok=True)

        self.client_id = os.environ.get("SHOPIFY_CLIENT_ID") or os.environ.get("SHOPIFY_API_KEY")
        self.client_secret = os.environ.get("SHOPIFY_CLIENT_SECRET") or os.environ.get("SHOPIFY_API_SECRET")
        self.store_url = os.getenv("SHOPIFY_STORE_URL", "dev-solara.myshopify.com").rstrip("/")
        self.api_version = "2024-01"
        self._token: str | None = os.environ.get("SHOPIFY_ACCESS_TOKEN")

    def _fetch_token_from_atlas(self) -> str | None:
        """Fetch the latest Shopify access token from Atlas (ERPNext)."""
        erpnext_url = os.environ.get("ERPNEXT_URL", "").rstrip("/")
        api_key = os.environ.get("ERPNEXT_API_KEY", "")
        api_secret = os.environ.get("ERPNEXT_API_SECRET", "")
        if not all([erpnext_url, api_key, api_secret]):
            return None

        try:
            resp = requests.post(
                f"{erpnext_url}/api/method/frappe.client.get_password",
                headers={
                    "Authorization": f"token {api_key}:{api_secret}",
                    "Content-Type": "application/json",
                },
                json={
                    "doctype": "Shopify Setting",
                    "name": "Shopify Setting",
                    "fieldname": "password",
                },
                timeout=30,
            )
            resp.raise_for_status()
            token = resp.json().get("message", "")
            if token and token.startswith("shpat_"):
                logger.info("[Shopify] Fresh token fetched from Atlas")
                return token
        except Exception as exc:
            logger.warning("[Shopify] Failed to fetch token from Atlas: %s", exc)
        return None

    def _get_token(self) -> str:
        """Get access token. Priority: env var → Atlas → client_credentials grant."""
        if self._token:
            return self._token

        # Try Atlas (ERPNext) — always has the latest auto-refreshed token
        atlas_token = self._fetch_token_from_atlas()
        if atlas_token:
            self._token = atlas_token
            return self._token

        # Fall back to client credentials grant
        if not self.client_id or not self.client_secret:
            raise RuntimeError(
                "No SHOPIFY_ACCESS_TOKEN, no Atlas credentials (ERPNEXT_URL/KEY/SECRET), "
                "and no client credentials (SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET) configured"
            )

        url = f"https://{self.store_url}/admin/oauth/access_token"
        resp = requests.post(url, data={
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }, timeout=30)
        resp.raise_for_status()
        self._token = resp.json()["access_token"]
        logger.info("[Shopify] Token acquired via client credentials (expires in %ss)",
                    resp.json().get("expires_in", "?"))
        return self._token

    def _api_get(self, endpoint: str, params: dict = None) -> requests.Response:
        """Make authenticated GET request to Shopify Admin API."""
        url = f"https://{self.store_url}/admin/api/{self.api_version}/{endpoint}"
        headers = {"X-Shopify-Access-Token": self._get_token()}
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp

    def _get_orders(self, created_at_min: str, created_at_max: str) -> list[dict]:
        """Fetch all orders in the time range with pagination."""
        orders = []
        params = {
            "status": "any",
            "created_at_min": created_at_min,
            "created_at_max": created_at_max,
            "limit": 250,
            "fields": "id,created_at,line_items,subtotal_price,total_price,"
                      "total_discounts,total_tax,shipping_lines,"
                      "billing_address,shipping_address,financial_status",
        }
        url = f"https://{self.store_url}/admin/api/{self.api_version}/orders.json"
        headers = {"X-Shopify-Access-Token": self._get_token()}

        while url:
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            orders.extend(data.get("orders", []))
            # Pagination via Link header
            url = None
            params = None  # params already baked into the next URL
            link = resp.headers.get("Link", "")
            for part in link.split(","):
                if 'rel="next"' in part:
                    url = part.split(";")[0].strip().strip("<>")
        return orders

    def _flatten_orders(self, orders: list[dict]) -> list[dict]:
        """Flatten orders into one row per line item."""
        rows = []
        for order in orders:
            # Skip cancelled/voided orders
            financial_status = order.get("financial_status", "")
            if financial_status in ("voided", "refunded"):
                continue

            shipping = sum(float(s.get("price", 0)) for s in order.get("shipping_lines", []))
            city = (
                order.get("shipping_address") or order.get("billing_address") or {}
            ).get("city", "")

            for item in order.get("line_items", []):
                sku = item.get("sku", "")
                if not sku:
                    continue  # skip items without SKU

                quantity = int(item.get("quantity", 0))
                price = float(item.get("price", 0))
                line_discount = sum(
                    float(d.get("amount", 0))
                    for d in item.get("discount_allocations", [])
                )
                subtotal = price * quantity

                rows.append({
                    "Created at": order["created_at"],
                    "Lineitem sku": sku,
                    "Lineitem quantity": quantity,
                    "Subtotal": subtotal,
                    "Total": float(order.get("total_price", 0)),
                    "Discount Amount": line_discount,
                    "Taxes": float(order.get("total_tax", 0)),
                    "Shipping": shipping,
                    "Billing City": city,
                    "Financial Status": financial_status,
                })
        return rows

    def run(self, report_date: date = None) -> dict:
        if report_date is None:
            report_date = date.today() - timedelta(days=1)

        result = {
            "portal": self.portal_name,
            "date": report_date,
            "file": None,
            "status": "failed",
            "error": None,
        }
        try:
            start = f"{report_date}T00:00:00+05:30"
            end = f"{report_date}T23:59:59+05:30"
            logger.info("[Shopify] Fetching orders for %s", report_date)

            orders = self._get_orders(start, end)
            logger.info("[Shopify] Got %d orders", len(orders))

            rows = self._flatten_orders(orders)

            output_path = self.portal_data_path / f"shopify_sales_{report_date}.csv"
            if rows:
                with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                    writer.writeheader()
                    writer.writerows(rows)

            result.update({
                "file": str(output_path),
                "status": "success",
                "records": len(rows),
                "orders": len(orders),
            })
            logger.info("[Shopify] Saved %d line items from %d orders to %s",
                        len(rows), len(orders), output_path)
        except Exception as exc:
            logger.error("[Shopify] Failed: %s", exc)
            result["error"] = str(exc)
        return result
