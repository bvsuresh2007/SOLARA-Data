#!/usr/bin/env python3
"""
Blinkit Product Price Scraper CLI

Usage:
    python blinkit_main.py <product_id>                    # Single product
    python blinkit_main.py 627046 628123                   # Multiple products
    python blinkit_main.py -f products.txt                 # From file (one ID per line)
    python blinkit_main.py -f products.txt -o results.csv  # Export to CSV
    python blinkit_main.py --pincode 560001 627046         # Specific pincode
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


def load_product_ids_from_file(filepath: str) -> list[str]:
    """Load product IDs from a text file (one per line) or CSV."""
    product_ids = []
    with open(filepath, "r", encoding="utf-8") as f:
        # Check if it's a CSV
        if filepath.endswith(".csv"):
            reader = csv.reader(f)
            for row in reader:
                if row and row[0].strip():
                    pid = row[0].strip()
                    # Skip header rows
                    if pid.upper() not in ("PRODUCT_ID", "PRODUCTID", "PID", "ID", "PRID"):
                        product_ids.append(pid)
        else:
            # Plain text file
            for line in f:
                pid = line.strip()
                if pid and not pid.startswith("#"):
                    product_ids.append(pid)
    return product_ids


def save_to_csv(results: list[BlinkitProductData], filepath: str) -> None:
    """Save results to CSV file."""
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        # Write header
        writer.writerow([
            "Product_ID", "Title", "Price", "Price_Value",
            "MRP", "MRP_Value", "Discount", "Quantity",
            "In_Stock", "URL", "Error", "Scraped_At"
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
        help="One or more product IDs to scrape"
    )
    parser.add_argument(
        "-f", "--file",
        help="File containing product IDs (one per line or CSV)"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output CSV file for results"
    )
    parser.add_argument(
        "-p", "--pincode",
        default="110001",
        help="Delivery pincode for location-based pricing. Default: 110001 (Delhi)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Save HTML to debug file for inspection"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=3.0,
        help="Delay between requests in seconds (default: 3)"
    )

    args = parser.parse_args()

    # Collect product IDs from arguments and/or file
    product_ids = list(args.product_ids) if args.product_ids else []

    if args.file:
        file_ids = load_product_ids_from_file(args.file)
        product_ids.extend(file_ids)
        print(f"Loaded {len(file_ids)} product IDs from {args.file}")

    if not product_ids:
        print("Error: No product IDs provided. Use positional arguments or -f/--file option.")
        sys.exit(1)

    # Remove duplicates while preserving order
    seen = set()
    unique_ids = []
    for pid in product_ids:
        if pid not in seen:
            seen.add(pid)
            unique_ids.append(pid)
    product_ids = unique_ids

    print(f"\nScraping {len(product_ids)} product(s) from Blinkit...")
    print(f"Pincode: {args.pincode}")
    print(f"Delay between requests: {args.delay}s")

    scraper = BlinkitScraper(
        pincode=args.pincode,
        debug=args.debug
    )

    results = []
    try:
        for i, pid in enumerate(product_ids, 1):
            print(f"\n[{i}/{len(product_ids)}] Scraping product {pid}...")
            result = scraper.scrape(pid)
            results.append(result)
            print_result(result, i, len(product_ids))

            # Delay between requests (except for last one)
            if i < len(product_ids):
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
