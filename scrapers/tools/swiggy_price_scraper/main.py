#!/usr/bin/env python3
"""
Swiggy Instamart Product Scraper CLI — Playwright

Usage:
    python main.py <URL>                                          # Single product
    python main.py -p 560103 -o results.csv <URL>                 # With pincode + CSV
    python main.py -p 560103 -f urls.txt -o results.csv           # Bulk from file
    python main.py --no-headless <URL>                            # Show browser window
    python main.py --batch-size 3 --batch-pause 480 -f urls.txt   # Batched (rate-limit safe)
"""

import sys
import csv
import json
import time
import random
import argparse
from dataclasses import asdict
from datetime import datetime

# Windows terminal: force UTF-8 so ₹ and other unicode prints correctly
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from swiggy_scraper import SwiggyInstamartScraper, SwiggyProductData


def print_result(data: SwiggyProductData, index: int = None, total: int = None) -> None:
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


def save_to_csv(results: list[SwiggyProductData], filepath: str,
                pincode: str = None, quiet: bool = False) -> None:
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
    if not quiet:
        print(f"\nResults saved to: {filepath}")


def main():
    parser = argparse.ArgumentParser(
        description="Scrape Swiggy Instamart product prices (Playwright)"
    )
    parser.add_argument("urls", nargs="*", help="Swiggy Instamart product URLs to scrape")
    parser.add_argument("-f", "--file", help="File containing URLs (one per line or CSV)")
    parser.add_argument("-o", "--output", help="Output CSV file")
    parser.add_argument("-p", "--pincode", default="560103",
                        help="Delivery pincode (default: 560103 Whitefield)")
    parser.add_argument("--no-headless", action="store_true", help="Show browser window")
    parser.add_argument("--debug", action="store_true", help="Save page HTML for inspection")
    parser.add_argument("--delay", type=float, default=25.0,
                        help="Delay between requests in seconds (default: 25)")
    parser.add_argument("--proxy", help="Proxy URL (e.g. http://user:pass@host:port)")
    parser.add_argument("--batch-size", type=int, default=3,
                        help="URLs per batch before rate-limit pause (default: 3)")
    parser.add_argument("--batch-pause", type=int, default=480,
                        help="Seconds to pause between batches (default: 480 = 8 min)")
    args = parser.parse_args()

    urls = list(args.urls) if args.urls else []
    if args.file:
        file_urls = load_urls_from_file(args.file)
        urls.extend(file_urls)
        print(f"Loaded {len(file_urls)} URLs from {args.file}")

    if not urls:
        print("Error: No URLs provided.")
        print("\nExample:")
        print("  python main.py https://www.swiggy.com/instamart/item/product-name/id")
        sys.exit(1)

    # Deduplicate
    seen, unique = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    urls = unique

    headless = not args.no_headless
    num_batches = (len(urls) + args.batch_size - 1) // args.batch_size
    print(f"\nScraping {len(urls)} Swiggy Instamart product(s) (Playwright)...")
    print(f"Pincode: {args.pincode}  |  Headless: {headless}")
    print(f"Delay: {args.delay}s  |  Batch: {args.batch_size} URLs × {num_batches} batches")
    print(f"Batch pause: {args.batch_pause}s ({args.batch_pause // 60} min) between batches")

    scraper = SwiggyInstamartScraper(
        pincode=args.pincode,
        headless=headless,
        debug=args.debug,
        proxy=args.proxy,
    )

    results = []
    try:
        for i, url in enumerate(urls, 1):
            url_in_batch = (i - 1) % args.batch_size
            batch_num = (i - 1) // args.batch_size + 1

            # Batch boundary: pause before starting a new batch (except the first)
            if url_in_batch == 0 and i > 1:
                pause = args.batch_pause + random.uniform(0, 30)
                print(f"\n{'*'*60}")
                print(f"  BATCH {batch_num - 1} COMPLETE — pausing {pause:.0f}s for rate-limit reset...")
                print(f"  Remaining: {len(urls) - i + 1} URLs")
                print(f"{'*'*60}")
                if args.output and results:
                    save_to_csv(results, args.output, pincode=args.pincode, quiet=True)
                time.sleep(pause)

            if url_in_batch == 0:
                print(f"\n--- Batch {batch_num}/{num_batches} ---")

            print(f"\n[{i}/{len(urls)}] Scraping: {url[:80]}...")
            try:
                result = scraper.scrape(url)
            except KeyboardInterrupt:
                print("\n  Interrupted by user.")
                break
            except Exception as e:
                result = SwiggyProductData(url=url, error=str(e))

            results.append(result)
            print_result(result, i, len(urls))

            # Save after every URL (partial results)
            if args.output:
                save_to_csv(results, args.output, pincode=args.pincode, quiet=True)

            # Delay within batch
            if i < len(urls) and (i % args.batch_size) != 0:
                jitter = args.delay * random.uniform(-0.3, 0.3)
                wait = max(5.0, args.delay + jitter)
                print(f"  Waiting {wait:.1f}s...")
                time.sleep(wait)

    except KeyboardInterrupt:
        print("\n  Interrupted by user.")
    finally:
        scraper.close()
        if args.output and results:
            save_to_csv(results, args.output, pincode=args.pincode)

        successful = sum(1 for r in results if not r.error)
        print(f"\n{'='*60}")
        print(f"DONE: {successful}/{len(results)} products scraped successfully")
        print(f"{'='*60}")

        if not args.output and results:
            print("\nJSON Output:")
            print(json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
