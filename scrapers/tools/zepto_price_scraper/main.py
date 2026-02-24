#!/usr/bin/env python3
"""
Zepto Product Scraper CLI

Usage:
    python main.py <URL>                                           # Single product
    python main.py -p 400093 -o results.csv <URL>                  # With pincode + CSV
    python main.py -p 400093 -f urls.txt -o results.csv            # Bulk + pincode
    python main.py --no-headless <URL>                             # Visible browser
"""

import sys
import csv
import json
import argparse
from dataclasses import asdict
from datetime import datetime

from zepto_scraper import ZeptoScraper, ZeptoProductData


def print_result(data: ZeptoProductData, index: int = None, total: int = None) -> None:
    """Print product data in a formatted way."""
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
        if data.category:
            print(f"Category: {data.category}")
        if data.availability:
            print(f"Status:   {data.availability}")
        if data.rating:
            rating_str = f"{data.rating}"
            if data.rating_count:
                rating_str += f" ({data.rating_count} ratings)"
            print(f"Rating:   {rating_str}")
        if data.description:
            desc = data.description[:120] + "..." if len(data.description) > 120 else data.description
            print(f"Desc:     {desc}")
        if data.highlights:
            print(f"Highlights:")
            for h in data.highlights[:5]:
                print(f"  - {h}")
        if data.image_url:
            print(f"Image:    {data.image_url[:80]}...")

    print("=" * 60)


def load_urls_from_file(filepath: str) -> list[str]:
    """Load URLs from a text file (one per line) or CSV."""
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


def save_to_csv(results: list[ZeptoProductData], filepath: str,
                pincode: str = None) -> None:
    """Save results to CSV file with Product_ID, Name, MRP columns."""
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Product_ID", "Name", "MRP", "Selling_Price", "Discount",
            "Brand", "Quantity", "Availability",
            "Pincode", "URL", "Scraped_At"
        ])
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for r in results:
            writer.writerow([
                r.product_id or "",
                r.name or "",
                r.mrp or r.price or "",
                r.price or "",
                r.discount or "",
                r.brand or "",
                r.quantity or "",
                r.availability or "",
                pincode or "",
                r.url,
                timestamp
            ])
    print(f"\nResults saved to: {filepath}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Scrape product data from Zepto product pages"
    )
    parser.add_argument(
        "urls", nargs="*",
        help="One or more Zepto product URLs to scrape"
    )
    parser.add_argument(
        "-f", "--file",
        help="File containing URLs (one per line or CSV)"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output CSV file for results"
    )
    parser.add_argument(
        "-p", "--pincode",
        help="Delivery pincode for location-based pricing (e.g. 400093)"
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Save page HTML to file for inspection"
    )
    parser.add_argument(
        "--no-headless", action="store_true",
        help="Show browser window (not headless)"
    )
    parser.add_argument(
        "--no-browser", action="store_true",
        help="Use requests mode instead of browser (faster, but may get less data)"
    )
    parser.add_argument(
        "--delay", type=float, default=3.0,
        help="Delay between requests in seconds (default: 3)"
    )

    args = parser.parse_args()

    # Collect URLs
    urls = list(args.urls) if args.urls else []
    if args.file:
        file_urls = load_urls_from_file(args.file)
        urls.extend(file_urls)
        print(f"Loaded {len(file_urls)} URLs from {args.file}")

    if not urls:
        print("Error: No URLs provided. Use positional arguments or -f/--file option.")
        print("\nExample:")
        print("  python main.py https://www.zepto.com/pn/product-name/pvid/product-id")
        sys.exit(1)

    # Remove duplicates preserving order
    seen = set()
    unique_urls = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    urls = unique_urls

    headless = not args.no_headless
    use_browser = not args.no_browser
    if use_browser:
        mode = "headless browser" if headless else "visible browser"
    else:
        mode = "requests"
    print(f"\nScraping {len(urls)} Zepto product(s) in {mode} mode...")
    if args.pincode:
        print(f"Pincode: {args.pincode}")
    print(f"Delay between requests: {args.delay}s")

    scraper = ZeptoScraper(
        headless=headless, debug=args.debug,
        use_browser=use_browser, pincode=args.pincode
    )

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

        # Save CSV
        if args.output:
            save_to_csv(results, args.output, pincode=args.pincode)

        # Summary
        successful = sum(1 for r in results if not r.error)
        print(f"\n{'='*60}")
        print(f"DONE: {successful}/{len(results)} products scraped successfully")
        print(f"{'='*60}")

        # JSON output if no CSV
        if not args.output:
            print("\nJSON Output:")
            print(json.dumps([asdict(r) for r in results], indent=2))

    finally:
        scraper.close()


if __name__ == "__main__":
    main()
