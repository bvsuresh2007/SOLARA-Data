#!/usr/bin/env python3
"""
ASIN Price and BSR Scraper CLI

Usage:
    python main.py <ASIN>                           # Single ASIN
    python main.py B09T9FBR6D B08N5WRWNW            # Multiple ASINs
    python main.py -f asins.txt                     # From file (one ASIN per line)
    python main.py -f asins.txt -o results.csv     # Export to CSV
    python main.py --browser -m in -f asins.txt    # Browser mode for Amazon India
"""

import sys
import csv
import json
import argparse
from dataclasses import asdict
from datetime import datetime

from src.scraper import AmazonScraper, ProductData


def print_result(data: ProductData, index: int = None, total: int = None) -> None:
    """Print product data in a formatted way."""
    progress = f"[{index}/{total}] " if index and total else ""
    print(f"\n{progress}" + "=" * 50)
    print(f"ASIN: {data.asin}")
    print("-" * 50)

    if data.error:
        print(f"ERROR: {data.error}")
    else:
        title = data.title[:50] + "..." if data.title and len(data.title) > 50 else data.title
        print(f"Title:    {title or 'N/A'}")
        print(f"Price:    {data.price or 'N/A'}")
        print(f"BSR:      {data.bsr or 'N/A'}")
        print(f"Seller:   {data.seller or 'N/A'}")
        if data.fulfilled_by:
            print(f"Ships:    Fulfilled by {data.fulfilled_by}")

    print("=" * 50)


def load_asins_from_file(filepath: str) -> list[str]:
    """Load ASINs from a text file (one per line) or CSV."""
    asins = []
    with open(filepath, "r", encoding="utf-8") as f:
        # Check if it's a CSV
        if filepath.endswith(".csv"):
            reader = csv.reader(f)
            for row in reader:
                if row and row[0].strip():
                    asin = row[0].strip()
                    # Skip header rows
                    if asin.upper() != "ASIN":
                        asins.append(asin)
        else:
            # Plain text file
            for line in f:
                asin = line.strip()
                if asin and not asin.startswith("#"):
                    asins.append(asin)
    return asins


def save_to_csv(results: list[ProductData], filepath: str) -> None:
    """Save results to CSV file."""
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        # Write header
        writer.writerow([
            "ASIN", "Title", "Price", "Price_Value",
            "BSR_Rank", "BSR_Category", "Seller", "Fulfilled_By",
            "URL", "Error", "Scraped_At"
        ])
        # Write data
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
        "asins",
        nargs="*",
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
        "-m", "--marketplace",
        default="com",
        help="Amazon marketplace (com, in, co.uk, de, etc.). Default: com"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Save HTML to debug.html for inspection"
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Use browser (Selenium) to avoid CAPTCHA detection"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=3.0,
        help="Delay between requests in seconds (default: 3)"
    )
    parser.add_argument(
        "-s", "--seller",
        help="Filter results by seller name (e.g. 'RetailEZ')"
    )

    args = parser.parse_args()

    # Collect ASINs from arguments and/or file
    asins = list(args.asins) if args.asins else []

    if args.file:
        file_asins = load_asins_from_file(args.file)
        asins.extend(file_asins)
        print(f"Loaded {len(file_asins)} ASINs from {args.file}")

    if not asins:
        print("Error: No ASINs provided. Use positional arguments or -f/--file option.")
        sys.exit(1)

    # Remove duplicates while preserving order
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

            # Delay between requests (except for last one)
            if i < len(asins):
                import time
                time.sleep(args.delay)

        # Filter by seller if specified
        if args.seller:
            seller_filter = args.seller.lower()
            matched = [r for r in results if r.seller and seller_filter in r.seller.lower()]
            not_matched = [r for r in results if not r.seller or seller_filter not in r.seller.lower()]

            print(f"\n{'='*50}")
            print(f"SELLER FILTER: '{args.seller}'")
            print(f"Matched:     {len(matched)}/{len(results)}")
            print(f"Not matched: {len(not_matched)}/{len(results)}")
            print(f"{'='*50}")

            if not_matched:
                print("\nASINs NOT sold by this seller:")
                for r in not_matched:
                    print(f"  {r.asin} - Sold by: {r.seller or 'N/A'}")

            # Save only matched results to CSV
            if args.output:
                save_to_csv(matched, args.output)
                print(f"(Only {len(matched)} matching results saved to CSV)")
        else:
            # Save all results to CSV
            if args.output:
                save_to_csv(results, args.output)

        # Print summary
        successful = sum(1 for r in results if not r.error and r.price)
        print(f"\n{'='*50}")
        print(f"SUMMARY: {successful}/{len(results)} products scraped successfully")
        print(f"{'='*50}")

        # Also output JSON if not saving to CSV
        if not args.output:
            print("\nJSON Output:")
            print(json.dumps([asdict(r) for r in results], indent=2))

    finally:
        scraper.close()


if __name__ == "__main__":
    main()
