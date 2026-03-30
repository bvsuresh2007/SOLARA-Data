"""
Amazon SP-API Vendor Central Sales Scraper
Uses the Data Kiosk API (GraphQL) to pull ASIN-level daily sales data.

Usage:
    python -m scrapers.amazon_sp_api_scraper              # defaults to 2 days ago
    python -m scrapers.amazon_sp_api_scraper 2026-03-27   # specific date
"""

import os
import csv
import json
import time
import logging
import requests
import gzip
from datetime import date, timedelta
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("scrapers.amazon_sp_api")

# ── SP-API Configuration ─────────────────────────────────────────────────────

LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"
SP_API_ENDPOINT = "https://sellingpartnerapi-eu.amazon.com"
MARKETPLACE_ID = os.getenv("SP_API_MARKETPLACE_ID", "A21TJRUUN4KGV")

RAW_DIR = Path("data/raw/amazon_sp_api")


class AmazonSPAPIScraper:
    """Pull Vendor Central sales data via SP-API Data Kiosk."""

    def __init__(self):
        self._client_id = os.environ["SP_API_LWA_CLIENT_ID"]
        self._client_secret = os.environ["SP_API_LWA_CLIENT_SECRET"]
        self._refresh_token = os.environ["SP_API_REFRESH_TOKEN"]
        self._access_token: str | None = None
        self._token_expiry: float = 0

    # ── Auth ──────────────────────────────────────────────────────────────────

    def _get_access_token(self) -> str:
        """Exchange refresh token for LWA access token (cached for 1 hour)."""
        if self._access_token and time.time() < self._token_expiry - 60:
            return self._access_token

        resp = requests.post(LWA_TOKEN_URL, data={
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        })
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data["access_token"]
        self._token_expiry = time.time() + data.get("expires_in", 3600)
        logger.info("LWA access token obtained (expires in %ds)", data.get("expires_in", 3600))
        return self._access_token

    def _headers(self) -> dict:
        return {
            "x-amz-access-token": self._get_access_token(),
            "Content-Type": "application/json",
        }

    # ── Data Kiosk API ────────────────────────────────────────────────────────

    def _create_query(self, graphql_query: str) -> str:
        """Submit a Data Kiosk query. Returns query ID."""
        url = f"{SP_API_ENDPOINT}/dataKiosk/2023-11-15/queries"
        body = {"query": graphql_query}
        resp = requests.post(url, headers=self._headers(), json=body)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 60))
            logger.warning("Rate limited on createQuery, waiting %ds", retry_after)
            time.sleep(retry_after)
            resp = requests.post(url, headers=self._headers(), json=body)
        if not resp.ok:
            logger.error("createQuery failed %d: %s", resp.status_code, resp.text)
        resp.raise_for_status()
        query_id = resp.json()["queryId"]
        logger.info("Query submitted: %s", query_id)
        return query_id

    def _poll_query(self, query_id: str, max_polls: int = 60, interval: int = 15) -> dict:
        """Poll until query completes. Returns query response."""
        url = f"{SP_API_ENDPOINT}/dataKiosk/2023-11-15/queries/{query_id}"
        for i in range(1, max_polls + 1):
            resp = requests.get(url, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            status = data.get("processingStatus", "UNKNOWN")
            logger.info("Poll %d/%d: %s", i, max_polls, status)

            if status == "DONE":
                return data
            elif status in ("FATAL", "CANCELLED"):
                raise RuntimeError(f"Query {query_id} failed: {status} — {data}")

            time.sleep(interval)

        raise TimeoutError(f"Query {query_id} did not complete in {max_polls * interval}s")

    def _download_document(self, document_id: str) -> str:
        """Download the result document. Returns content as string."""
        url = f"{SP_API_ENDPOINT}/dataKiosk/2023-11-15/documents/{document_id}"
        resp = requests.get(url, headers=self._headers())
        resp.raise_for_status()
        doc_info = resp.json()

        doc_url = doc_info["documentUrl"]
        compression = doc_info.get("compressionAlgorithm")

        logger.info("Downloading document: %s (compression=%s)", document_id, compression)
        doc_resp = requests.get(doc_url)
        doc_resp.raise_for_status()

        if compression == "GZIP":
            content = gzip.decompress(doc_resp.content).decode("utf-8")
        else:
            content = doc_resp.text

        return content

    # ── Query Builder ─────────────────────────────────────────────────────────

    def _build_sales_query(self, start_date: date, end_date: date) -> str:
        """Build GraphQL query for Vendor Analytics ASIN-level daily sales."""
        return (
            "{"
            "  analytics_vendorAnalytics_2024_09_30 {"
            "    manufacturingView("
            f'      startDate: "{start_date.isoformat()}"'
            f'      endDate: "{end_date.isoformat()}"'
            "      aggregateBy: DAY"
            '      currencyCode: "INR"'
            "    ) {"
            "      startDate"
            "      endDate"
            "      marketplaceId"
            "      metrics {"
            "        groupByKey {"
            "          asin"
            "          productTitle"
            "        }"
            "        metrics {"
            "          orders {"
            "            orderedUnitsWithRevenue {"
            "              units"
            "              value {"
            "                amount"
            "                currencyCode"
            "              }"
            "            }"
            "            unfilledOrderedUnits"
            "          }"
            "          shippedOrders {"
            "            shippedUnitsWithRevenue {"
            "              units"
            "              value {"
            "                amount"
            "                currencyCode"
            "              }"
            "            }"
            "            averageSellingPrice {"
            "              amount"
            "              currencyCode"
            "            }"
            "          }"
            "          productAvailability {"
            "            sellableOnHandInventory {"
            "              units"
            "              value {"
            "                amount"
            "                currencyCode"
            "              }"
            "            }"
            "          }"
            "        }"
            "      }"
            "    }"
            "  }"
            "}"
        )

    # ── Parse + Save ──────────────────────────────────────────────────────────

    def _parse_response(self, content: str) -> list[dict]:
        """
        Parse the Data Kiosk response into flat rows.
        Response is a single JSON object with nested metrics array.
        """
        data = json.loads(content)
        metrics = data.get("metrics", [])
        sale_date = data.get("startDate", "")
        rows = []

        for m in metrics:
            asin = m["groupByKey"]["asin"]
            title = m["groupByKey"].get("productTitle", "")
            orders = m["metrics"].get("orders", {})
            shipped = m["metrics"].get("shippedOrders", {})

            ordered_uwr = orders.get("orderedUnitsWithRevenue", {}) or {}
            ordered_units = ordered_uwr.get("units") or 0
            ordered_value = (ordered_uwr.get("value") or {}).get("amount") or 0

            shipped_uwr = shipped.get("shippedUnitsWithRevenue", {}) or {}
            shipped_units = shipped_uwr.get("units") or 0
            shipped_value = (shipped_uwr.get("value") or {}).get("amount") or 0

            unfilled = orders.get("unfilledOrderedUnits") or 0

            asp_data = shipped.get("averageSellingPrice", {}) or {}
            asp = asp_data.get("amount") or 0

            pa = m["metrics"].get("productAvailability", {}) or {}
            soh_data = pa.get("sellableOnHandInventory", {}) or {}
            soh_units = soh_data.get("units") or 0
            soh_value = (soh_data.get("value") or {}).get("amount") or 0

            rows.append({
                "date": sale_date,
                "asin": asin,
                "product_title": title,
                "ordered_units": ordered_units,
                "ordered_revenue": ordered_value,
                "shipped_units": shipped_units,
                "shipped_revenue": shipped_value,
                "unfilled_units": unfilled,
                "avg_selling_price": asp,
                "sellable_on_hand": soh_units,
                "soh_value": soh_value,
            })

        return rows

    def _save_csv(self, rows: list[dict], report_date: date) -> Path:
        """Save parsed results to CSV."""
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        out_path = RAW_DIR / f"amazon_sp_api_sales_{report_date}.csv"

        headers = [
            "date", "asin", "product_title", "ordered_units", "ordered_revenue",
            "shipped_units", "shipped_revenue", "unfilled_units", "avg_selling_price",
            "sellable_on_hand", "soh_value",
        ]

        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)

        logger.info("Saved %d rows to %s", len(rows), out_path)
        return out_path

    # ── Main Entry Point ──────────────────────────────────────────────────────

    def run(self, report_date: date) -> dict:
        """
        Pull Vendor Central sales data for a given date.
        Data Kiosk has a 2-day lag — data for date D is available on D+2 at 10 AM local.
        """
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        )

        logger.info("Starting SP-API sales pull for %s", report_date)

        try:
            query = self._build_sales_query(report_date, report_date)
            query_id = self._create_query(query)
            result = self._poll_query(query_id, max_polls=40, interval=15)

            doc_id = result.get("dataDocumentId")
            if not doc_id:
                logger.warning("No dataDocumentId — possibly no data for %s", report_date)
                out_path = self._save_csv([], report_date)
                return {
                    "portal": "amazon_sp_api",
                    "date": report_date,
                    "file": out_path,
                    "status": "success",
                    "rows": 0,
                    "error": "No data returned (possibly too recent — 2-day lag applies)",
                }

            content = self._download_document(doc_id)
            rows = self._parse_response(content)
            out_path = self._save_csv(rows, report_date)

            with_orders = sum(1 for r in rows if r["ordered_units"] > 0)
            total_units = sum(r["ordered_units"] for r in rows)
            total_rev = sum(r["ordered_revenue"] for r in rows)
            logger.info(
                "Done: %d ASINs (%d with orders), %d units, INR %.1fL revenue",
                len(rows), with_orders, total_units, total_rev / 100_000,
            )

            return {
                "portal": "amazon_sp_api",
                "date": report_date,
                "file": out_path,
                "status": "success",
                "rows": len(rows),
                "asins_with_orders": with_orders,
                "total_units": total_units,
                "total_revenue": round(total_rev, 2),
                "error": None,
            }

        except Exception as e:
            logger.exception("SP-API scraper failed for %s", report_date)
            return {
                "portal": "amazon_sp_api",
                "date": report_date,
                "file": None,
                "status": "error",
                "rows": 0,
                "error": str(e),
            }


if __name__ == "__main__":
    import sys
    d = date.today() - timedelta(days=2)  # 2-day lag
    if len(sys.argv) > 1:
        d = date.fromisoformat(sys.argv[1])
    scraper = AmazonSPAPIScraper()
    result = scraper.run(d)
    print(result)
