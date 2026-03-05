"""
Google Sheets client for the Solara Price Tracker.

Handles:
  - OAuth authentication (reuses token.json, auto-refreshes)
  - Creating the Price Tracker spreadsheet on first run
  - Reading the Products master list
  - Appending daily price columns to each platform tab
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date
from pathlib import Path
from typing import Any

import gspread
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets",
]

# Static (left-most) columns per tab — these never move
STATIC_COLS = {
    "Products": ["SKU", "Product Name", "ASIN", "Zepto URL", "Blinkit ID", "Swiggy URL"],
    "Amazon":   ["SKU", "Product Name", "ASIN"],
    "Zepto":    ["SKU", "Product Name", "Zepto URL"],
    "Blinkit":  ["SKU", "Product Name", "Blinkit ID"],
    "Swiggy":   ["SKU", "Product Name", "Swiggy URL"],
}

# How many date-columns are appended per run per tab
DATE_COLS = {
    "Amazon":  ["Price", "BSR"],
    "Zepto":   ["Price", "MRP", "Disc%"],
    "Blinkit": ["Price", "MRP", "Disc%"],
    "Swiggy":  ["Price", "MRP", "Disc%"],
}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _get_credentials() -> Credentials:
    token_json = os.environ.get("GMAIL_TOKEN_JSON")
    if token_json:
        creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
    else:
        token_path = Path(__file__).resolve().parents[3] / "token.json"
        if not token_path.exists():
            raise FileNotFoundError(f"token.json not found at {token_path}")
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        logger.info("[Sheets] Token refreshed")

    return creds


def get_sheets_client() -> gspread.Client:
    creds = _get_credentials()
    return gspread.authorize(creds)


# ---------------------------------------------------------------------------
# Sheet setup
# ---------------------------------------------------------------------------

def open_or_create_sheet(client: gspread.Client) -> tuple[gspread.Spreadsheet, str]:
    """
    Open the existing sheet (PRICE_TRACKER_SHEET_ID env var) or create a new one.
    Returns (spreadsheet, url).
    """
    sheet_id = os.environ.get("PRICE_TRACKER_SHEET_ID", "").strip()

    if sheet_id:
        logger.info("[Sheets] Opening existing sheet: %s", sheet_id)
        spreadsheet = client.open_by_key(sheet_id)
        return spreadsheet, spreadsheet.url

    # --- First run: create the sheet ---
    logger.info("[Sheets] Creating new 'Solara Price Tracker' spreadsheet...")
    spreadsheet = client.create("Solara Price Tracker")

    # Rename default Sheet1 to "Products"
    ws_products = spreadsheet.sheet1
    ws_products.update_title("Products")
    ws_products.append_row(STATIC_COLS["Products"], value_input_option="RAW")
    # Freeze header row
    spreadsheet.batch_update({"requests": [
        {"updateSheetProperties": {
            "properties": {"sheetId": ws_products.id, "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount"
        }}
    ]})

    # Add platform tabs
    for tab in ["Amazon", "Zepto", "Blinkit", "Swiggy"]:
        ws = spreadsheet.add_worksheet(title=tab, rows=500, cols=200)
        ws.append_row(STATIC_COLS[tab], value_input_option="RAW")
        spreadsheet.batch_update({"requests": [
            {"updateSheetProperties": {
                "properties": {"sheetId": ws.id, "gridProperties": {"frozenRowCount": 1, "frozenColumnCount": len(STATIC_COLS[tab])}},
                "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount"
            }}
        ]})

    logger.info("[Sheets] Sheet created: %s", spreadsheet.url)
    return spreadsheet, spreadsheet.url


# ---------------------------------------------------------------------------
# Read products
# ---------------------------------------------------------------------------

def read_products(spreadsheet: gspread.Spreadsheet) -> list[dict[str, str]]:
    """
    Read the Products tab and return a list of dicts, one per non-empty row.
    Keys: sku, name, asin, zepto_url, blinkit_id, swiggy_url
    """
    ws = spreadsheet.worksheet("Products")
    rows = ws.get_all_records(empty2zero=False, default_blank="")
    products = []
    for row in rows:
        sku = str(row.get("SKU", "")).strip()
        if not sku:
            continue
        products.append({
            "sku":        sku,
            "name":       str(row.get("Product Name", "")).strip(),
            "asin":       str(row.get("ASIN", "")).strip(),
            "zepto_url":  str(row.get("Zepto URL", "")).strip(),
            "blinkit_id": str(row.get("Blinkit ID", "")).strip(),
            "swiggy_url": str(row.get("Swiggy URL", "")).strip(),
        })
    logger.info("[Sheets] Read %d products from Products tab", len(products))
    return products


# ---------------------------------------------------------------------------
# Append daily price columns
# ---------------------------------------------------------------------------

def append_price_columns(
    spreadsheet: gspread.Spreadsheet,
    platform: str,
    report_date: date,
    results: list[dict[str, Any]],
) -> None:
    """
    Append today's price data columns to a platform tab.

    results: list of dicts, each with keys:
        sku, and one of:
        - Amazon:  price_value, bsr_value
        - Others:  price_value, mrp_value, discount
    """
    ws = spreadsheet.worksheet(platform)
    date_str = report_date.strftime("%Y-%m-%d")
    col_labels = [f"{date_str} {c}" for c in DATE_COLS[platform]]
    n_static = len(STATIC_COLS[platform])

    # --- Read current sheet state ---
    all_values = ws.get_all_values()
    if not all_values:
        return

    header_row = all_values[0]

    # Find or create the date columns
    col_indices = []
    for label in col_labels:
        if label in header_row:
            col_indices.append(header_row.index(label))
        else:
            # Append new header
            next_col = len(header_row) + len(col_indices) - sum(1 for l in col_labels if l in header_row)
            header_row.append(label)
            col_indices.append(len(header_row) - 1)

    # Build SKU → row index map (1-based, row 1 = header)
    sku_to_row: dict[str, int] = {}
    for i, row in enumerate(all_values[1:], start=2):
        if row:
            sku_to_row[str(row[0]).strip()] = i

    # --- Write header updates (new columns only) ---
    # Rewrite entire header row to capture appended columns
    ws.update("1:1", [header_row], value_input_option="RAW")

    # --- Pass 1: collect new rows + build updates ---
    new_static_rows: list[list] = []  # batch-append in one API call
    updates: list[dict] = []

    for item in results:
        sku = item.get("sku", "")
        row_idx = sku_to_row.get(sku)
        if row_idx is None:
            # SKU not in sheet yet — collect for batch append
            if platform == "Amazon":
                new_row = [sku, item.get("name", ""), item.get("asin", "")]
            elif platform == "Zepto":
                new_row = [sku, item.get("name", ""), item.get("zepto_url", "")]
            elif platform == "Blinkit":
                new_row = [sku, item.get("name", ""), item.get("blinkit_id", "")]
            else:
                new_row = [sku, item.get("name", ""), item.get("swiggy_url", "")]
            row_idx = len(all_values) + len(new_static_rows) + 1
            new_static_rows.append(new_row[:n_static])
            sku_to_row[sku] = row_idx

        # Build cell values for this date's columns
        if platform == "Amazon":
            vals = [
                item.get("price_value") or "",
                item.get("bsr_value") or "",
            ]
        else:
            price = item.get("price_value") or ""
            mrp   = item.get("mrp_value") or ""
            disc  = item.get("discount") or ""
            if price and mrp and not disc:
                try:
                    disc = round((1 - float(price) / float(mrp)) * 100, 1)
                except (TypeError, ZeroDivisionError):
                    disc = ""
            vals = [price, mrp, disc]

        for ci, val in zip(col_indices, vals):
            col_letter = _col_letter(ci + 1)
            updates.append({
                "range": f"{col_letter}{row_idx}",
                "values": [[val]],
            })

    # Single API call for all new rows (was 1 call per row — hit quota fast)
    if new_static_rows:
        ws.append_rows(new_static_rows, value_input_option="RAW")

    if updates:
        ws.batch_update(updates, value_input_option="USER_ENTERED")

    logger.info("[Sheets] %s: wrote %d rows for %s", platform, len(results), date_str)


def _col_letter(n: int) -> str:
    """Convert 1-based column index to A1-notation letter (e.g. 1→A, 27→AA)."""
    result = ""
    while n:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result
