#!/usr/bin/env python3
"""
Blinkit Product Price Scraper CLI

Usage:
    python blinkit_main.py <product_id_or_url>                           # Single product
    python blinkit_main.py 627046 628123                                 # Multiple products
    python blinkit_main.py -f products.txt                               # From file (URLs or IDs, one per line)
    python blinkit_main.py -f products.txt -o resultsblinkit.csv         # Export to CSV
    python blinkit_main.py -p 122009 -f products.txt -o results.csv     # Specific pincode
    python blinkit_main.py --browser -f products.txt -o results.csv     # Browser mode (recommended)
"""

import sys
import csv
import json
import argparse
from dataclasses import asdict
from datetime import datetime

from src.blinkit_scraper import BlinkitScraper, BlinkitProductData


def print_result(data: BlinkitProductData, index: int = None, total: int = None) -> None:
    """Print product data in a formatted way."""
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
    """Load product IDs or URLs from a text file (one per line) or CSV."""
    entries = []
    with open(filepath, "r", encoding="utf-8") as f:
        # Check if it's a CSV
        if filepath.endswith(".csv"):
            reader = csv.reader(f)
            for row in reader:
                if row and row[0].strip():
                    entry = row[0].strip()
                    # Skip header rows
                    if entry.upper() not in ("PRODUCT_ID", "PRODUCTID", "PID", "ID", "PRID", "URL", "LINK", "SKU"):
                        entries.append(entry)
        else:
            # Plain text file - each line can be a URL or product ID
            for line in f:
                entry = line.strip()
                if entry and not entry.startswith("#"):
                    entries.append(entry)
    return entries


def save_to_csv(results: list[BlinkitProductData], filepath: str) -> None:
    """Save results to CSV file."""
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        # Write header
        writer.writerow([
            "Product_ID", "Title", "Price", "Price_Value",
            "MRP", "MRP_Value", "Discount", "Quantity",
            "Brand", "In_Stock", "URL", "Error", "Scraped_At"
        ])
        # Write data
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for r in results:
            writer.writerow([
                r.product_id,
                r.title or "",
                r.price or "",
                r.price_value or "",
                r.mrp or "",
                r.mrp_value or "",
                r.discount or "",
                r.quantity or "",
                r.brand or "",
                "Yes" if r.in_stock else "No",
                r.url,
                r.error or "",
                timestamp
            ])
    print(f"\nResults saved to: {filepath}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Scrape Blinkit product price and details"
    )
    parser.add_argument(
        "product_ids",
        nargs="*",
        help="One or more product IDs or Blinkit URLs to scrape"
    )
    parser.add_argument(
        "-f", "--file",
        help="File containing product URLs or IDs (one per line or CSV)"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output CSV file for results"
    )
    parser.add_argument(
        "-p", "--pincode",
        default="122009",
        help="Delivery pincode for location-based pricing. Default: 122009 (Gurgaon)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Save HTML to debug file for inspection"
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Use Selenium browser to bypass anti-bot protection (recommended)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=3.0,
        help="Delay between requests in seconds (default: 3)"
    )

    args = parser.parse_args()

    # Collect entries from arguments and/or file
    entries = list(args.product_ids) if args.product_ids else []

    if args.file:
        file_entries = load_entries_from_file(args.file)
        entries.extend(file_entries)
        print(f"Loaded {len(file_entries)} entries from {args.file}")

    if not entries:
        print("Error: No product IDs or URLs provided. Use positional arguments or -f/--file option.")
        sys.exit(1)

    # Remove duplicates while preserving order
    seen = set()
    unique_entries = []
    for entry in entries:
        key = BlinkitScraper.extract_product_id(entry)
        if key not in seen:
            seen.add(key)
            unique_entries.append(entry)
    entries = unique_entries

    mode = "browser" if args.browser else "requests"
    print(f"\nScraping {len(entries)} product(s) from Blinkit using {mode} mode...")
    print(f"Pincode: {args.pincode}")
    print(f"Delay between requests: {args.delay}s")

    scraper = BlinkitScraper(
        pincode=args.pincode,
        debug=args.debug,
        use_browser=args.browser
    )

    results = []
    try:
        for i, entry in enumerate(entries, 1):
            pid = BlinkitScraper.extract_product_id(entry)
            print(f"\n[{i}/{len(entries)}] Scraping product {pid}...")
            result = scraper.scrape(entry)
            results.append(result)
            print_result(result, i, len(entries))

            # Delay between requests (except for last one)
            if i < len(entries):
                import time
                time.sleep(args.delay)

        # Save to CSV if output specified
        if args.output:
            save_to_csv(results, args.output)

        # Print summary
        successful = sum(1 for r in results if not r.error and r.price)
        print(f"\n{'='*60}")
        print(f"SUMMARY: {successful}/{len(results)} products scraped successfully")
        print(f"{'='*60}")

        # Also output JSON if not saving to CSV
        if not args.output:
            print("\nJSON Output:")
            print(json.dumps([asdict(r) for r in results], indent=2))

    finally:
        scraper.close()


if __name__ == "__main__":
    main()
