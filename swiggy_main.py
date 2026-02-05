#!/usr/bin/env python3
"""
Swiggy Instamart Product Scraper CLI

Usage:
    python swiggy_main.py <URL>                                          # Single product
    python swiggy_main.py -p 560103 -o results.csv <URL>                 # With pincode + CSV
    python swiggy_main.py -p 560103 -f urls.txt -o results.csv           # Bulk from file
    python swiggy_main.py --no-headless <URL>                            # Visible browser
    python swiggy_main.py --no-browser -f urls.txt -o results.csv        # Requests mode (faster)
"""

import sys
import csv
import json
import random
import argparse
from dataclasses import asdict
from datetime import datetime

from src.swiggy_scraper import SwiggyInstamartScraper, SwiggyProductData


def print_result(data: SwiggyProductData, index: int = None, total: int = None) -> None:
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


def save_to_csv(results: list[SwiggyProductData], filepath: str,
                pincode: str = None, quiet: bool = False) -> None:
    """Save results to CSV file with UTF-8 BOM for Excel compatibility."""
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
    if not quiet:
        print(f"\nResults saved to: {filepath}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Scrape product data from Swiggy Instamart product pages"
    )
    parser.add_argument(
        "urls", nargs="*",
        help="One or more Swiggy Instamart product URLs to scrape"
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
        "-p", "--pincode", default="560103",
        help="Delivery pincode for location-based pricing (default: 560103)"
    )
    parser.add_argument(
        "--debug", action="store_true", default=True,
        help="Save page HTML to file for inspection (enabled by default)"
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
        "--delay", type=float, default=15.0,
        help="Delay between requests in seconds (default: 15)"
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
        print("  python swiggy_main.py https://www.swiggy.com/instamart/item/product-name/product-id")
        print("  python swiggy_main.py -f urls.txt -o results.csv")
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
    print(f"\nScraping {len(urls)} Swiggy Instamart product(s) in {mode} mode...")
    print(f"Pincode: {args.pincode}")
    print(f"Delay between requests: {args.delay}s")
    if use_browser:
        print(f"Browser strategy: Chrome -> Edge -> Firefox (2 attempts each)")
        print(f"  If rate-limited: 90s cooldown before next browser")
        print(f"Fresh browser + pincode for EACH attempt")

    # Create scraper without opening browser yet (we open per-URL)
    scraper = SwiggyInstamartScraper(
        headless=headless, debug=args.debug,
        use_browser=False,  # Don't open browser in constructor
        pincode=args.pincode
    )
    scraper.use_browser = use_browser  # Restore flag after constructor

    # Browser order: try Chrome first, then Edge, then Firefox
    browsers = ["chrome", "edge", "firefox"]
    RATE_LIMIT_COOLDOWN = 90  # seconds to wait when rate-limited

    results = []
    try:
        for i, url in enumerate(urls, 1):
            print(f"\n[{i}/{len(urls)}] Scraping: {url[:80]}...")

            result = None
            user_interrupted = False

            if use_browser:
                # Try each browser (2 attempts each = 6 total per URL)
                for browser_idx, browser_type in enumerate(browsers):
                    print(f"\n  === Trying {browser_type.title()} browser (2 attempts) [{browser_idx + 1}/{len(browsers)}] ===")

                    # Open fresh browser
                    try:
                        print(f"  Opening fresh {browser_type.title()} browser...")
                        scraper.open_browser(browser_type)
                    except Exception as e:
                        print(f"  ERROR opening {browser_type}: {e}")
                        continue  # Try the next browser

                    # Scrape with this browser (2 attempts inside _scrape_browser)
                    try:
                        result = scraper.scrape(url)
                    except KeyboardInterrupt:
                        print("\n\n  Interrupted by user. Saving results collected so far...")
                        scraper.close()
                        user_interrupted = True
                        break
                    except Exception as e:
                        print(f"  ERROR during scrape: {e}")
                        result = SwiggyProductData(url=url, error=str(e))

                    # Close browser after attempt
                    print(f"  Closing {browser_type.title()} browser...")
                    scraper.close()

                    # Check if scrape was successful (has name and no error)
                    if result and result.name and not result.error:
                        print(f"  SUCCESS with {browser_type.title()}!")
                        break  # Got good result, no need to try other browser

                    # Failed — check WHY
                    error_msg = result.error if result else "Unknown error"
                    is_rate_limited = result and result.error and "rate-limit" in result.error.lower()
                    print(f"  FAILED with {browser_type.title()}: {error_msg}")

                    if browser_idx < len(browsers) - 1:
                        next_browser = browsers[browser_idx + 1]
                        if is_rate_limited:
                            # Rate-limited = IP blocked. Must wait a long time
                            # before trying again (different browser, same IP).
                            import time
                            cooldown = RATE_LIMIT_COOLDOWN + random.uniform(0, 15)
                            print(f"\n  [!] RATE-LIMITED — Swiggy blocked this IP.")
                            print(f"  [!] Cooling down for {cooldown:.0f}s before trying {next_browser.title()}...")
                            time.sleep(cooldown)
                        else:
                            # Non-rate-limit error — quick switch to next browser
                            import time
                            print(f"  Will try {next_browser.title()} browser next...")
                            time.sleep(3)

                if user_interrupted:
                    break

                # If all browsers failed, create error result
                if not result or (not result.name and not result.error):
                    result = SwiggyProductData(
                        url=url,
                        error="Failed to extract data after 6 attempts (2 Chrome + 2 Edge + 2 Firefox)"
                    )

            else:
                # Non-browser mode (requests)
                try:
                    result = scraper.scrape(url)
                except KeyboardInterrupt:
                    print("\n\n  Interrupted by user. Saving results collected so far...")
                    break
                except Exception as e:
                    print(f"  ERROR: {e}")
                    result = SwiggyProductData(url=url, error=str(e))

            results.append(result)
            print_result(result, i, len(urls))

            # Check if this URL was rate-limited
            was_rate_limited = result and result.error and "rate-limit" in (result.error or "").lower()

            # Save partial results after each URL (so nothing is lost on crash)
            if args.output and results:
                save_to_csv(results, args.output, pincode=args.pincode, quiet=True)

            if i < len(urls):
                import time
                if was_rate_limited:
                    # Extra long wait after a rate-limited URL before trying next one
                    cooldown = RATE_LIMIT_COOLDOWN + random.uniform(0, 15)
                    print(f"  [!] Rate-limited on previous URL. Waiting {cooldown:.0f}s before next URL...")
                    time.sleep(cooldown)
                else:
                    # Normal delay with jitter
                    jitter = args.delay * random.uniform(-0.3, 0.3)
                    wait = max(5, args.delay + jitter)
                    print(f"  Waiting {wait:.1f}s before next request...")
                    time.sleep(wait)

    except KeyboardInterrupt:
        print("\n\n  Interrupted by user.")

    finally:
        # Always save results (even partial) and close browser
        if args.output and results:
            save_to_csv(results, args.output, pincode=args.pincode)

        successful = sum(1 for r in results if not r.error)
        print(f"\n{'='*60}")
        print(f"DONE: {successful}/{len(results)} products scraped successfully")
        if len(results) < len(urls):
            print(f"  ({len(urls) - len(results)} URLs were not attempted)")
        print(f"{'='*60}")

        if not args.output and results:
            print("\nJSON Output:")
            print(json.dumps([asdict(r) for r in results], indent=2))

        scraper.close()


if __name__ == "__main__":
    main()
