#!/usr/bin/env python3
"""
ASIN Price and BSR Scraper CLI

Usage:
    python main.py <ASIN>
    python main.py B09T9FBR6D
    python main.py B09T9FBR6D B08N5WRWNW  # Multiple ASINs
    python main.py -m in B09T9FBR6D       # Use amazon.in
    python main.py --browser B09T9FBR6D   # Use browser to avoid CAPTCHA
    python main.py -m in --browser B09T9FBR6D
"""

import sys
import json
import argparse
from dataclasses import asdict

from src.scraper import AmazonScraper, ProductData


def print_result(data: ProductData) -> None:
    """Print product data in a formatted way."""
    print("\n" + "=" * 60)
    print(f"ASIN: {data.asin}")
    print(f"URL:  {data.url}")
    print("-" * 60)

    if data.error:
        print(f"ERROR: {data.error}")
    else:
        print(f"Title:    {data.title or 'N/A'}")
        print(f"Price:    {data.price or 'N/A'}")
        if data.price_value:
            print(f"          (${data.price_value:.2f})")
        print(f"BSR:      {data.bsr or 'N/A'}")
        if data.bsr_value:
            print(f"          (Rank: {data.bsr_value:,})")
        if data.bsr_category:
            print(f"Category: {data.bsr_category}")

    print("=" * 60)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Scrape Amazon product price and BSR data"
    )
    parser.add_argument(
        "asins",
        nargs="+",
        help="One or more ASINs to scrape"
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

    args = parser.parse_args()

    mode = "browser" if args.browser else "requests"
    print(f"\nScraping {len(args.asins)} ASIN(s) from amazon.{args.marketplace} using {mode}...")

    scraper = AmazonScraper(
        marketplace=args.marketplace,
        debug=args.debug,
        use_browser=args.browser
    )

    try:
        if len(args.asins) == 1:
            result = scraper.scrape(args.asins[0])
            if args.debug:
                print(f"\nDebug HTML saved to: debug_{args.asins[0]}.html")
            print_result(result)

            # Also output as JSON for programmatic use
            print("\nJSON Output:")
            print(json.dumps(asdict(result), indent=2))
        else:
            results = scraper.scrape_multiple(args.asins)
            for result in results:
                print_result(result)

            # Output all as JSON
            print("\nJSON Output:")
            print(json.dumps([asdict(r) for r in results], indent=2))
    finally:
        # Close browser if open
        scraper.close()


if __name__ == "__main__":
    main()
