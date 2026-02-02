#!/usr/bin/env python3
"""
ASIN Price and BSR Scraper CLI

Usage:
    python main.py <ASIN>
    python main.py B09T9FBR6D
    python main.py B09T9FBR6D B08N5WRWNW  # Multiple ASINs
"""

import sys
import json
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
    if len(sys.argv) < 2:
        print("Usage: python main.py <ASIN> [ASIN2] [ASIN3] ...")
        print("Example: python main.py B09T9FBR6D")
        sys.exit(1)

    asins = sys.argv[1:]
    print(f"\nScraping {len(asins)} ASIN(s)...")

    scraper = AmazonScraper(marketplace="com")

    if len(asins) == 1:
        result = scraper.scrape(asins[0])
        print_result(result)

        # Also output as JSON for programmatic use
        print("\nJSON Output:")
        print(json.dumps(asdict(result), indent=2))
    else:
        results = scraper.scrape_multiple(asins)
        for result in results:
            print_result(result)

        # Output all as JSON
        print("\nJSON Output:")
        print(json.dumps([asdict(r) for r in results], indent=2))


if __name__ == "__main__":
    main()
