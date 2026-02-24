#!/usr/bin/env python3
"""
Zepto Product Scraper CLI — Playwright

Usage:
    python main.py <URL>                                           # Single product
    python main.py -p 400093 -o results.csv <URL>                  # With pincode + CSV
    python main.py -p 400093 -f urls.txt -o results.csv            # Bulk + pincode
    python main.py --no-headless <URL>                             # Show browser window
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

from zepto_scraper import ZeptoScraper, ZeptoProductData


def print_result(data: ZeptoProductData, index: int = None, total: int = None) -> None:
    progress = f"[{index}/{total}] " if index and total else ""
    print(f"\n{progress}" + "=" * 60)
    if data.error:
        print(f"URL:   {data.url}")
        print(f"ERROR: {data.error}")
    else:
        print(f"Name:     {data.name or 'N/A'}")
        if data.brand:
            print(f"Brand:    {data.brand}")
        print(f"Price:    {data.price or 'N/A'}")
        if data.mrp:
            print(f"MRP:      {data.mrp}")
        if data.discount:
            print(f"Discount: {data.discount}")
        if data.quantity:
            print(f"Quantity: {data.quantity}")
        if data.availability:
            print(f"Status:   {data.availability}")
        if data.rating:
            rating_str = data.rating
            if data.rating_count:
                rating_str += f" ({data.rating_count} ratings)"
            print(f"Rating:   {rating_str}")
    print("=" * 60)


def load_urls_from_file(filepath: str) -> list[str]:
    urls = []
    with open(filepath, "r", encoding="utf-8") as f:
        if filepath.endswith(".csv"):
            reader = csv.reader(f)
            for row in reader:
                if row and row[0].strip():
                    url = row[0].strip()
                    if url.lower() != "url" and url.startswith("http"):
                        urls.append(url)
        else:
            for line in f:
                url = line.strip()
                if url and not url.startswith("#") and url.startswith("http"):
                    urls.append(url)
    return urls


def save_to_csv(results: list[ZeptoProductData], filepath: str, pincode: str = None) -> None:
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Product_ID", "Name", "MRP", "Selling_Price", "Discount",
            "Brand", "Quantity", "Availability", "Pincode", "URL", "Scraped_At",
        ])
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for r in results:
            writer.writerow([
                r.product_id or "", r.name or "",
                r.mrp or r.price or "", r.price or "",
                r.discount or "", r.brand or "", r.quantity or "",
                r.availability or "", pincode or "", r.url, timestamp,
            ])
    print(f"\nResults saved to: {filepath}")


def main():
    parser = argparse.ArgumentParser(description="Scrape Zepto product prices (Playwright)")
    parser.add_argument("urls", nargs="*", help="Zepto product URLs to scrape")
    parser.add_argument("-f", "--file", help="File containing URLs (one per line or CSV)")
    parser.add_argument("-o", "--output", help="Output CSV file")
    parser.add_argument("-p", "--pincode", help="Delivery pincode (e.g. 400093)")
    parser.add_argument("--no-headless", action="store_true", help="Show browser window")
    parser.add_argument("--debug", action="store_true", help="Save page HTML for inspection")
    parser.add_argument("--delay", type=float, default=3.0,
                        help="Delay between requests in seconds (default: 3)")
    args = parser.parse_args()

    urls = list(args.urls) if args.urls else []
    if args.file:
        file_urls = load_urls_from_file(args.file)
        urls.extend(file_urls)
        print(f"Loaded {len(file_urls)} URLs from {args.file}")

    if not urls:
        print("Error: No URLs provided.")
        print("\nExample:")
        print("  python main.py https://www.zepto.com/pn/product-name/pvid/product-id")
        sys.exit(1)

    # Deduplicate
    seen, unique = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    urls = unique

    headless = not args.no_headless
    print(f"\nScraping {len(urls)} Zepto product(s) (Playwright)...")
    if args.pincode:
        print(f"Pincode: {args.pincode}")
    print(f"Headless: {headless}  |  Delay: {args.delay}s")

    scraper = ZeptoScraper(headless=headless, debug=args.debug, pincode=args.pincode)
    results = []
    try:
        for i, url in enumerate(urls, 1):
            print(f"\n[{i}/{len(urls)}] Scraping: {url[:80]}...")
            result = scraper.scrape(url)
            results.append(result)
            print_result(result, i, len(urls))

            if i < len(urls):
                import time
                time.sleep(args.delay)

        if args.output:
            save_to_csv(results, args.output, pincode=args.pincode)

        successful = sum(1 for r in results if not r.error)
        print(f"\n{'='*60}")
        print(f"DONE: {successful}/{len(results)} products scraped successfully")
        print(f"{'='*60}")

        if not args.output:
            print("\nJSON Output:")
            print(json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False))

    finally:
        scraper.close()


if __name__ == "__main__":
    main()
