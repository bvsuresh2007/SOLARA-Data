"""
Amazon SP-API Vendor Central Sales Scraper

Two data sources:
  1. Reports API — GET_VENDOR_REAL_TIME_SALES_REPORT (hourly, near real-time)
     Used for ordered units & revenue. Available ~5 min after each hour closes.
  2. Data Kiosk API — manufacturingView (daily, ~34h lag)
     Used for inventory (sellableOnHandInventory), open POs, shipped data.
     Falls back to this if real-time report is unavailable.

Usage:
    python -m scrapers.amazon_sp_api_scraper              # defaults to yesterday
    python -m scrapers.amazon_sp_api_scraper 2026-03-30   # specific date
"""

import os
import csv
import json
import time
import logging
import requests
import gzip
from datetime import date, datetime, timedelta, timezone
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
    """Pull Vendor Central sales data via SP-API."""

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

    # ── Reports API (Real-Time Sales) ────────────────────────────────────────

    def _create_report(self, report_type: str, start_time: str, end_time: str) -> str:
        """Create a report request. Returns report ID."""
        url = f"{SP_API_ENDPOINT}/reports/2021-06-30/reports"
        body = {
            "reportType": report_type,
            "dataStartTime": start_time,
            "dataEndTime": end_time,
            "marketplaceIds": [MARKETPLACE_ID],
        }
        resp = requests.post(url, headers=self._headers(), json=body)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 60))
            logger.warning("Rate limited on createReport, waiting %ds", retry_after)
            time.sleep(retry_after)
            resp = requests.post(url, headers=self._headers(), json=body)
        if not resp.ok:
            logger.error("createReport failed %d: %s", resp.status_code, resp.text)
        resp.raise_for_status()
        report_id = resp.json()["reportId"]
        logger.info("Report requested: %s (type=%s)", report_id, report_type)
        return report_id

    def _poll_report(self, report_id: str, max_polls: int = 40, interval: int = 15) -> dict:
        """Poll until report is done. Returns report response."""
        url = f"{SP_API_ENDPOINT}/reports/2021-06-30/reports/{report_id}"
        for i in range(1, max_polls + 1):
            resp = requests.get(url, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            status = data.get("processingStatus", "UNKNOWN")
            logger.info("Report poll %d/%d: %s", i, max_polls, status)

            if status == "DONE":
                return data
            elif status in ("FATAL", "CANCELLED"):
                raise RuntimeError(f"Report {report_id} failed: {status} — {data}")

            time.sleep(interval)

        raise TimeoutError(f"Report {report_id} did not complete in {max_polls * interval}s")

    def _download_report_document(self, report_document_id: str) -> str:
        """Download a report document. Returns content as string."""
        url = f"{SP_API_ENDPOINT}/reports/2021-06-30/documents/{report_document_id}"
        resp = requests.get(url, headers=self._headers())
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 60))
            logger.warning("Rate limited on report document download, waiting %ds", retry_after)
            time.sleep(retry_after)
            resp = requests.get(url, headers=self._headers())
        resp.raise_for_status()
        doc_info = resp.json()

        doc_url = doc_info["url"]
        compression = doc_info.get("compressionAlgorithm")

        logger.info("Downloading report document: %s (compression=%s)", report_document_id, compression)
        doc_resp = requests.get(doc_url)
        doc_resp.raise_for_status()

        if compression == "GZIP":
            content = gzip.decompress(doc_resp.content).decode("utf-8")
        else:
            content = doc_resp.text

        return content

    def _parse_realtime_sales(self, content: str, report_date: date) -> list[dict]:
        """
        Parse GET_VENDOR_REAL_TIME_SALES_REPORT JSON.
        Format: {"reportSpecification": {...}, "reportData": [
            {"startTime": "...", "endTime": "...", "asin": "B0...",
             "orderedUnits": N, "orderedRevenue": N.NN}, ...
        ]}
        Hourly rows per ASIN — aggregate to daily totals.
        """
        data = json.loads(content)
        report_data = data.get("reportData", [])

        # Aggregate hourly rows to daily per ASIN
        asin_totals: dict[str, dict] = {}

        for item in report_data:
            asin = item.get("asin", "")
            if not asin:
                continue

            units = item.get("orderedUnits", 0) or 0
            rev_amount = float(item.get("orderedRevenue", 0) or 0)

            if asin in asin_totals:
                asin_totals[asin]["ordered_units"] += units
                asin_totals[asin]["ordered_revenue"] += rev_amount
            else:
                asin_totals[asin] = {
                    "date": report_date.isoformat(),
                    "asin": asin,
                    "product_title": "",
                    "ordered_units": units,
                    "ordered_revenue": rev_amount,
                    "shipped_units": 0,
                    "shipped_revenue": 0,
                    "unfilled_units": 0,
                    "avg_selling_price": 0,
                    "sellable_on_hand": 0,
                    "soh_value": 0,
                    "open_po_qty": 0,
                }

        rows = list(asin_totals.values())
        logger.info("Parsed real-time sales: %d ASINs from %d hourly rows", len(rows), len(report_data))
        return rows

    # ── Data Kiosk API (Fallback / Inventory+PO) ─────────────────────────────

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
                error_doc_id = data.get("errorDocumentId")
                raise RuntimeError(f"Query {query_id} failed: {status} — error_doc={error_doc_id} — {data}")

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
            "          sourcing {"
            "            openPurchaseOrderQuantity"
            "          }"
            "        }"
            "      }"
            "    }"
            "  }"
            "}"
        )

    def _parse_datakiosk_response(self, content: str) -> list[dict]:
        """Parse the Data Kiosk manufacturingView response into flat rows."""
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

            sourcing = m["metrics"].get("sourcing", {}) or {}
            open_po = sourcing.get("openPurchaseOrderQuantity") or 0

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
                "open_po_qty": open_po,
            })

        return rows

    # ── Save ─────────────────────────────────────────────────────────────────

    def _save_csv(self, rows: list[dict], report_date: date) -> Path:
        """Save parsed results to CSV."""
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        out_path = RAW_DIR / f"amazon_sp_api_sales_{report_date}.csv"

        headers = [
            "date", "asin", "product_title", "ordered_units", "ordered_revenue",
            "shipped_units", "shipped_revenue", "unfilled_units", "avg_selling_price",
            "sellable_on_hand", "soh_value", "open_po_qty",
        ]

        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)

        logger.info("Saved %d rows to %s", len(rows), out_path)
        return out_path

    # ── Main Entry Point ──────────────────────────────────────────────────────

    def run(self, report_date) -> dict:
        """
        Pull Vendor Central sales data for a given date.

        Strategy:
          1. Try GET_VENDOR_REAL_TIME_SALES_REPORT (Reports API) — hourly,
             near real-time. Aggregates hourly rows to daily per ASIN.
          2. If real-time fails, fall back to Data Kiosk manufacturingView
             (DAY granularity, ~34h lag).
        """
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        )

        if isinstance(report_date, str):
            report_date = date.fromisoformat(report_date)

        logger.info("Starting SP-API sales pull for %s", report_date)

        try:
            rows = self._pull_realtime_sales(report_date)
            source = "realtime_report"
        except Exception as rt_err:
            logger.warning("Real-time sales report failed: %s — falling back to Data Kiosk", rt_err)
            try:
                rows = self._pull_datakiosk_sales(report_date)
                source = "datakiosk"
            except Exception as dk_err:
                logger.exception("Both real-time and Data Kiosk failed for %s", report_date)
                return {
                    "portal": "amazon_sp_api",
                    "date": report_date,
                    "file": None,
                    "status": "error",
                    "rows": 0,
                    "error": f"Real-time: {rt_err} | DataKiosk: {dk_err}",
                }

        out_path = self._save_csv(rows, report_date)

        with_orders = sum(1 for r in rows if r["ordered_units"] > 0)
        total_units = sum(r["ordered_units"] for r in rows)
        total_rev = sum(r["ordered_revenue"] for r in rows)
        total_soh = sum(r["sellable_on_hand"] for r in rows)
        total_open_po = sum(r["open_po_qty"] for r in rows)

        logger.info(
            "Done (%s): %d ASINs (%d with orders), %d units, INR %.1fL revenue, "
            "%d SOH units, %d open PO units",
            source, len(rows), with_orders, total_units, total_rev / 100_000,
            total_soh, total_open_po,
        )

        return {
            "portal": "amazon_sp_api",
            "date": report_date,
            "file": out_path,
            "status": "success",
            "source": source,
            "rows": len(rows),
            "asins_with_orders": with_orders,
            "total_units": total_units,
            "total_revenue": round(total_rev, 2),
            "error": None,
        }

    def _pull_realtime_sales(self, report_date: date) -> list[dict]:
        """Pull via GET_VENDOR_REAL_TIME_SALES_REPORT (Reports API).

        Aligns to IST day: IST 00:00 = UTC previous day 18:30,
        IST 23:59:59 = UTC current day 18:29:59.
        """
        # IST = UTC + 5:30 → IST midnight = previous day 18:30 UTC
        ist_start_utc = datetime(report_date.year, report_date.month, report_date.day,
                                 tzinfo=timezone.utc) - timedelta(hours=5, minutes=30)
        ist_end_utc = ist_start_utc + timedelta(hours=24) - timedelta(seconds=1)

        now_utc = datetime.now(timezone.utc)
        if now_utc < ist_end_utc:
            # Day not yet complete — use last completed hour
            end_dt = now_utc.replace(minute=0, second=0, microsecond=0)
            if end_dt <= ist_start_utc:
                raise RuntimeError(f"No completed IST hours yet for {report_date}")
            ist_end_utc = end_dt

        start_time = ist_start_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_time = ist_end_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

        logger.info("Requesting real-time sales report: %s to %s", start_time, end_time)
        report_id = self._create_report(
            "GET_VENDOR_REAL_TIME_SALES_REPORT",
            start_time,
            end_time,
        )

        result = self._poll_report(report_id, max_polls=40, interval=15)
        doc_id = result.get("reportDocumentId")
        if not doc_id:
            raise RuntimeError("No reportDocumentId in completed report")

        content = self._download_report_document(doc_id)

        # Save raw JSON for debugging
        raw_path = RAW_DIR / f"amazon_realtime_raw_{report_date}.json"
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        with open(raw_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("Saved raw real-time report to %s", raw_path)

        rows = self._parse_realtime_sales(content, report_date)
        if not rows:
            raise RuntimeError("Real-time report returned 0 ASINs")

        return rows

    def _pull_datakiosk_sales(self, report_date: date) -> list[dict]:
        """Pull via Data Kiosk manufacturingView (fallback)."""
        query = self._build_sales_query(report_date, report_date)
        query_id = self._create_query(query)
        result = self._poll_query(query_id, max_polls=100, interval=15)

        doc_id = result.get("dataDocumentId")
        if not doc_id:
            logger.warning("No dataDocumentId — no data for %s via Data Kiosk", report_date)
            return []

        content = self._download_document(doc_id)
        rows = self._parse_datakiosk_response(content)

        total_open_po = sum(r["open_po_qty"] for r in rows)
        total_soh = sum(r["sellable_on_hand"] for r in rows)
        logger.info("Data Kiosk: %d ASINs, %d open PO units, %d SOH units",
                     len(rows), total_open_po, total_soh)

        return rows

    def pull_inventory(self, report_date: date | str | None = None) -> dict:
        """
        Pull inventory (FC stock) and Open PO data via Data Kiosk.
        ~34h lag — query date should be 2 days ago for reliable data.

        Returns dict with status, file path, and counts.
        """
        if report_date is None:
            report_date = date.today() - timedelta(days=2)
        if isinstance(report_date, str):
            report_date = date.fromisoformat(report_date)

        logger.info("Pulling inventory/open PO for %s via Data Kiosk", report_date)

        rows = self._pull_datakiosk_sales(report_date)
        if not rows:
            return {
                "portal": "amazon_sp_api",
                "date": report_date,
                "type": "inventory",
                "file": None,
                "status": "no_data",
                "asins": 0,
            }

        # Save inventory-specific CSV
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        out_path = RAW_DIR / f"amazon_inventory_{report_date}.csv"
        headers = ["date", "asin", "product_title", "sellable_on_hand",
                    "soh_value", "open_po_qty"]

        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for r in rows:
                writer.writerow({h: r.get(h, 0) for h in headers})

        total_soh = sum(r["sellable_on_hand"] for r in rows)
        total_po = sum(r["open_po_qty"] for r in rows)
        with_stock = sum(1 for r in rows if r["sellable_on_hand"] > 0)
        with_po = sum(1 for r in rows if r["open_po_qty"] > 0)

        logger.info("Inventory saved: %d ASINs (%d with stock, %d with open PO), "
                     "%d SOH units, %d open PO units → %s",
                     len(rows), with_stock, with_po, total_soh, total_po, out_path)

        return {
            "portal": "amazon_sp_api",
            "date": report_date,
            "type": "inventory",
            "file": str(out_path),
            "status": "success",
            "asins": len(rows),
            "with_stock": with_stock,
            "with_open_po": with_po,
            "total_soh": total_soh,
            "total_open_po": total_po,
        }


if __name__ == "__main__":
    import sys
    d = date.today() - timedelta(days=1)
    if len(sys.argv) > 1:
        d = date.fromisoformat(sys.argv[1])
    scraper = AmazonSPAPIScraper()
    result = scraper.run(d)
    print(result)
