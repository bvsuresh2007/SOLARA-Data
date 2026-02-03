#!/usr/bin/env python3
"""
ASIN Price and BSR Scraper CLI

Usage:
    python main.py <ASIN>                                # Single ASIN
    python main.py -f asins.txt -o results.csv           # Bulk from file
    python main.py --browser -m in -f asins.txt          # Browser mode
    python main.py --browser -m in -s RetailEZ -f asins.txt -o results.csv
"""

import sys
import csv
import json
import argparse
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime

from src.scraper import AmazonScraper, ProductData


def print_result(data: ProductData, index: int = None, total: int = None) -> None:
    """Print product data in a formatted way."""
    progress = f"[{index}/{total}] " if index and total else ""
    print(f"\n{progress}" + "=" * 55)
    print(f"ASIN: {data.asin}")
    print("-" * 55)

    if data.error:
        print(f"ERROR: {data.error}")
    else:
        title = data.title[:50] + "..." if data.title and len(data.title) > 50 else data.title
        print(f"Title:      {title or 'N/A'}")
        print(f"Price:      {data.price or 'N/A'}")
        print(f"BSR:        {data.bsr or 'N/A'}")
        print(f"Sold by:    {data.seller or 'N/A'}")
        print(f"Ships from: {data.ships_from or 'N/A'}")
        if data.fulfilled_by:
            print(f"Fulfilled:  {data.fulfilled_by}")

    print("=" * 55)


def print_seller_report(results: list[ProductData]) -> None:
    """Print a seller-level summary report."""
    # Group by seller
    seller_groups = defaultdict(list)
    for r in results:
        if r.error:
            seller_groups["[ERROR]"].append(r)
        else:
            seller_name = r.seller or "[UNKNOWN]"
            seller_groups[seller_name].append(r)

    print(f"\n{'#' * 55}")
    print(f"  SELLER-LEVEL REPORT")
    print(f"{'#' * 55}")

    for seller, items in sorted(seller_groups.items()):
        prices = [r.price_value for r in items if r.price_value]
        bsr_values = [r.bsr_value for r in items if r.bsr_value]

        print(f"\n  Seller: {seller}")
        print(f"  ASINs:  {len(items)}")

        if prices:
            avg_price = sum(prices) / len(prices)
            min_price = min(prices)
            max_price = max(prices)
            print(f"  Prices: Avg ₹{avg_price:,.0f} | Min ₹{min_price:,.0f} | Max ₹{max_price:,.0f}")

        if bsr_values:
            avg_bsr = sum(bsr_values) / len(bsr_values)
            best_bsr = min(bsr_values)
            print(f"  BSR:    Avg #{avg_bsr:,.0f} | Best #{best_bsr:,}")

        # List ASINs under this seller
        for r in items:
            price_str = r.price or "N/A"
            bsr_str = f"#{r.bsr_value:,}" if r.bsr_value else "N/A"
            print(f"    - {r.asin}  {price_str:>12}  BSR: {bsr_str}")

    print(f"\n{'#' * 55}")


def load_asins_from_file(filepath: str) -> list[str]:
    """Load ASINs from a text file (one per line) or CSV."""
    asins = []
    with open(filepath, "r", encoding="utf-8") as f:
        if filepath.endswith(".csv"):
            reader = csv.reader(f)
            for row in reader:
                if row and row[0].strip():
                    asin = row[0].strip()
                    if asin.upper() != "ASIN":
                        asins.append(asin)
        else:
            for line in f:
                asin = line.strip()
                if asin and not asin.startswith("#"):
                    asins.append(asin)
    return asins


def save_to_csv(results: list[ProductData], filepath: str) -> None:
    """Save results to CSV file."""
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "ASIN", "Title", "Price", "Price_Value",
            "BSR_Rank", "BSR_Category",
            "Seller", "Ships_From", "Fulfilled_By",
            "URL", "Error", "Scraped_At"
        ])
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for r in results:
            writer.writerow([
                r.asin,
                r.title or "",
                r.price or "",
                r.price_value or "",
                r.bsr_value or "",
                r.bsr_category or "",
                r.seller or "",
                r.ships_from or "",
                r.fulfilled_by or "",
                r.url,
                r.error or "",
                timestamp
            ])
    print(f"\nResults saved to: {filepath}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Scrape Amazon product price and BSR data"
    )
    parser.add_argument(
        "asins", nargs="*",
        help="One or more ASINs to scrape"
    )
    parser.add_argument(
        "-f", "--file",
        help="File containing ASINs (one per line or CSV)"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output CSV file for results"
    )
    parser.add_argument(
        "-m", "--marketplace", default="com",
        help="Amazon marketplace (com, in, co.uk, de, etc.). Default: com"
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Save HTML to debug.html for inspection"
    )
    parser.add_argument(
        "--browser", action="store_true",
        help="Use browser (Selenium) to avoid CAPTCHA detection"
    )
    parser.add_argument(
        "--delay", type=float, default=3.0,
        help="Delay between requests in seconds (default: 3)"
    )
    parser.add_argument(
        "-s", "--seller",
        help="Filter results by seller name (e.g. 'RetailEZ')"
    )

    args = parser.parse_args()

    # Collect ASINs
    asins = list(args.asins) if args.asins else []
    if args.file:
        file_asins = load_asins_from_file(args.file)
        asins.extend(file_asins)
        print(f"Loaded {len(file_asins)} ASINs from {args.file}")

    if not asins:
        print("Error: No ASINs provided. Use positional arguments or -f/--file option.")
        sys.exit(1)

    # Remove duplicates
    seen = set()
    unique_asins = []
    for asin in asins:
        if asin not in seen:
            seen.add(asin)
            unique_asins.append(asin)
    asins = unique_asins

    mode = "browser" if args.browser else "requests"
    print(f"\nScraping {len(asins)} ASIN(s) from amazon.{args.marketplace} using {mode}...")
    print(f"Delay between requests: {args.delay}s")
    if args.seller:
        print(f"Seller filter: '{args.seller}'")

    scraper = AmazonScraper(
        marketplace=args.marketplace,
        debug=args.debug,
        use_browser=args.browser
    )

    results = []
    try:
        for i, asin in enumerate(asins, 1):
            print(f"\n[{i}/{len(asins)}] Scraping {asin}...")
            result = scraper.scrape(asin)
            results.append(result)
            print_result(result, i, len(asins))

            if i < len(asins):
                import time
                time.sleep(args.delay)

        # Seller-level report
        print_seller_report(results)

        # Filter by seller if specified
        if args.seller:
            seller_filter = args.seller.lower()
            matched = [r for r in results if r.seller and seller_filter in r.seller.lower()]
            not_matched = [r for r in results if not r.seller or seller_filter not in r.seller.lower()]

            print(f"\nSELLER FILTER: '{args.seller}'")
            print(f"  Matched:     {len(matched)}/{len(results)}")
            print(f"  Not matched: {len(not_matched)}/{len(results)}")

            if not_matched:
                print(f"\n  ASINs NOT sold by '{args.seller}':")
                for r in not_matched:
                    print(f"    {r.asin} -> Sold by: {r.seller or 'N/A'}")

            # Save only matched to CSV
            if args.output:
                save_to_csv(matched, args.output)
                print(f"  (Only {len(matched)} matching results saved to CSV)")
        else:
            if args.output:
                save_to_csv(results, args.output)

        # Summary
        successful = sum(1 for r in results if not r.error and r.price)
        print(f"\n{'='*55}")
        print(f"DONE: {successful}/{len(results)} products scraped with price data")
        print(f"{'='*55}")

        # JSON if no CSV output
        if not args.output:
            print("\nJSON Output:")
            print(json.dumps([asdict(r) for r in results], indent=2))

    finally:
        scraper.close()


if __name__ == "__main__":
    main()
