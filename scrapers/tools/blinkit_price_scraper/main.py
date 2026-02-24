#!/usr/bin/env python3
"""
Blinkit Product Price Scraper CLI — Playwright

Usage:
    python main.py 627046                                        # Single product
    python main.py 627046 628123                                 # Multiple products
    python main.py -f products.txt                               # From file (IDs or URLs)
    python main.py -f products.txt -o results.csv                # Export to CSV
    python main.py -p 122009 -f products.txt -o results.csv      # Specific pincode
    python main.py --no-headless 627046                          # Show browser window
"""

import sys
import csv
import json
import argparse
from dataclasses import asdict
from datetime import datetime

# Windows terminal: force UTF-8 so ₹ and other unicode prints correctly
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from blinkit_scraper import BlinkitScraper, BlinkitProductData


def print_result(data: BlinkitProductData, index: int = None, total: int = None) -> None:
    progress = f"[{index}/{total}] " if index and total else ""
    print(f"\n{progress}" + "=" * 60)
    print(f"Product ID: {data.product_id}")
    print("-" * 60)
    if data.error:
        print(f"ERROR: {data.error}")
    else:
        title = data.title[:55] + "..." if data.title and len(data.title) > 55 else data.title
        print(f"Title:      {title or 'N/A'}")
        print(f"Price:      {data.price or 'N/A'}")
        print(f"MRP:        {data.mrp or 'N/A'}")
        print(f"Discount:   {data.discount or 'N/A'}")
        print(f"Quantity:   {data.quantity or 'N/A'}")
        print(f"In Stock:   {'Yes' if data.in_stock else 'No'}")
        print(f"URL:        {data.url}")
    print("=" * 60)


def load_entries_from_file(filepath: str) -> list[str]:
    entries = []
    with open(filepath, "r", encoding="utf-8") as f:
        if filepath.endswith(".csv"):
            import csv as _csv
            reader = _csv.reader(f)
            for row in reader:
                if row and row[0].strip():
                    entry = row[0].strip()
                    if entry.upper() not in ("PRODUCT_ID", "PRODUCTID", "PID", "ID", "URL", "SKU"):
                        entries.append(entry)
        else:
            for line in f:
                entry = line.strip()
                if entry and not entry.startswith("#"):
                    entries.append(entry)
    return entries


def save_to_csv(results: list[BlinkitProductData], filepath: str) -> None:
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Product_ID", "Title", "Price", "Price_Value",
            "MRP", "MRP_Value", "Discount", "Quantity",
            "Brand", "In_Stock", "URL", "Error", "Scraped_At",
        ])
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for r in results:
            writer.writerow([
                r.product_id, r.title or "", r.price or "", r.price_value or "",
                r.mrp or "", r.mrp_value or "", r.discount or "", r.quantity or "",
                r.brand or "", "Yes" if r.in_stock else "No",
                r.url, r.error or "", timestamp,
            ])
    print(f"\nResults saved to: {filepath}")


def main():
    parser = argparse.ArgumentParser(description="Scrape Blinkit product prices (Playwright)")
    parser.add_argument("product_ids", nargs="*",
                        help="Product IDs or Blinkit URLs to scrape")
    parser.add_argument("-f", "--file",
                        help="File containing product IDs or URLs (one per line or CSV)")
    parser.add_argument("-o", "--output", help="Output CSV file")
    parser.add_argument("-p", "--pincode", default="122009",
                        help="Delivery pincode (default: 122009 Gurugram)")
    parser.add_argument("--no-headless", action="store_true",
                        help="Show browser window")
    parser.add_argument("--debug", action="store_true",
                        help="Save page HTML for inspection")
    parser.add_argument("--delay", type=float, default=3.0,
                        help="Delay between requests in seconds (default: 3)")
    args = parser.parse_args()

    entries = list(args.product_ids) if args.product_ids else []
    if args.file:
        file_entries = load_entries_from_file(args.file)
        entries.extend(file_entries)
        print(f"Loaded {len(file_entries)} entries from {args.file}")

    if not entries:
        print("Error: No product IDs or URLs provided.")
        sys.exit(1)

    # Deduplicate
    seen, unique = set(), []
    for e in entries:
        key = BlinkitScraper.extract_product_id(e)
        if key not in seen:
            seen.add(key)
            unique.append(e)
    entries = unique

    headless = not args.no_headless
    print(f"\nScraping {len(entries)} product(s) from Blinkit (Playwright)...")
    print(f"Pincode: {args.pincode}  |  Headless: {headless}")

    scraper = BlinkitScraper(pincode=args.pincode, debug=args.debug, headless=headless)
    results = []
    try:
        for i, entry in enumerate(entries, 1):
            pid = BlinkitScraper.extract_product_id(entry)
            print(f"\n[{i}/{len(entries)}] Scraping product {pid}...")
            result = scraper.scrape(entry)
            results.append(result)
            print_result(result, i, len(entries))

            if i < len(entries):
                import time
                time.sleep(args.delay)

        if args.output:
            save_to_csv(results, args.output)

        successful = sum(1 for r in results if not r.error and r.price)
        print(f"\n{'='*60}")
        print(f"SUMMARY: {successful}/{len(results)} products scraped successfully")
        print(f"{'='*60}")

        if not args.output:
            print("\nJSON Output:")
            print(json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False))

    finally:
        scraper.close()


if __name__ == "__main__":
    main()
