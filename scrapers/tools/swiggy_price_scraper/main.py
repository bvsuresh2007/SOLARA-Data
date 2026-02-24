#!/usr/bin/env python3
"""
Swiggy Instamart Product Scraper CLI

Usage:
    python main.py <URL>                                          # Single product
    python main.py -p 560103 -o results.csv <URL>                 # With pincode + CSV
    python main.py -p 560103 -f urls.txt -o results.csv           # Bulk from file
    python main.py --no-headless <URL>                            # Visible browser
    python main.py --no-browser -f urls.txt -o results.csv        # Requests mode (faster)
"""

import sys
import csv
import json
import time
import random
import argparse
from dataclasses import asdict
from datetime import datetime

from swiggy_scraper import SwiggyInstamartScraper, SwiggyProductData


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
        "--delay", type=float, default=25.0,
        help="Delay between requests in seconds (default: 25)"
    )
    parser.add_argument(
        "--proxy",
        help="Proxy URL for rotating IP (e.g. http://user:pass@host:port)"
    )
    parser.add_argument(
        "--batch-size", type=int, default=3,
        help="Number of URLs per batch before long pause (default: 3)"
    )
    parser.add_argument(
        "--batch-pause", type=int, default=480,
        help="Seconds to pause between batches for rate-limit reset (default: 480 = 8 min)"
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
        print("  python main.py https://www.swiggy.com/instamart/item/product-name/product-id")
        print("  python main.py -f urls.txt -o results.csv")
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

    num_batches = (len(urls) + args.batch_size - 1) // args.batch_size

    print(f"\nScraping {len(urls)} Swiggy Instamart product(s) in {mode} mode...")
    print(f"Pincode: {args.pincode}")
    print(f"Delay between requests: {args.delay}s")
    print(f"Batch size: {args.batch_size} URLs per batch ({num_batches} batches total)")
    print(f"Batch pause: {args.batch_pause}s ({args.batch_pause // 60} min) between batches")
    if args.proxy:
        print(f"Proxy: {args.proxy}")
    if use_browser:
        from swiggy_scraper import STEALTH_AVAILABLE, UNDETECTED_AVAILABLE
        if UNDETECTED_AVAILABLE:
            print(f"Browser: Chrome via undetected_chromedriver (best stealth)")
        elif STEALTH_AVAILABLE:
            print(f"Browser: Chrome + selenium-stealth (good stealth)")
        else:
            print(f"Browser: Chrome + basic CDP stealth (install selenium-stealth for better results)")
            print(f"  Run: pip install selenium-stealth")
        print(f"2 attempts per URL, fresh browser each time")

    # Create scraper without opening browser yet (we open per-URL)
    scraper = SwiggyInstamartScraper(
        headless=headless, debug=args.debug,
        use_browser=False,  # Don't open browser in constructor
        pincode=args.pincode,
        proxy=args.proxy
    )
    scraper.use_browser = use_browser  # Restore flag after constructor

    # Use Chrome as primary browser (most reliable with undetected_chromedriver)
    browser_type = "chrome"

    results = []
    try:
        for i, url in enumerate(urls, 1):
            # Check if this is the start of a new batch (after the first batch)
            url_in_batch = (i - 1) % args.batch_size  # 0-indexed position within batch
            batch_num = (i - 1) // args.batch_size + 1

            if url_in_batch == 0:
                if i > 1:
                    # Pause between batches
                    pause = args.batch_pause + random.uniform(0, 30)
                    print(f"\n{'*'*60}")
                    print(f"  BATCH {batch_num - 1} COMPLETE — {args.batch_size} URLs done")
                    print(f"  Pausing {pause:.0f}s ({pause/60:.1f} min) to reset rate-limit...")
                    print(f"  Remaining: {len(urls) - i + 1} URLs in {num_batches - batch_num + 1} batches")
                    print(f"{'*'*60}")

                    # Save results before long pause
                    if args.output and results:
                        save_to_csv(results, args.output, pincode=args.pincode, quiet=True)

                    time.sleep(pause)

                print(f"\n--- Batch {batch_num}/{num_batches} (URLs {i}-{min(i + args.batch_size - 1, len(urls))}) ---")

            print(f"\n[{i}/{len(urls)}] Scraping: {url[:80]}...")

            result = None

            if use_browser:
                # Open fresh browser
                try:
                    print(f"  Opening fresh {browser_type.title()} browser...")
                    scraper.open_browser(browser_type)
                except Exception as e:
                    print(f"  ERROR opening {browser_type}: {e}")
                    result = SwiggyProductData(url=url, error=f"Browser launch failed: {e}")

                if not result:
                    # Scrape with this browser (2 attempts inside _scrape_browser)
                    try:
                        result = scraper.scrape(url)
                    except KeyboardInterrupt:
                        print("\n\n  Interrupted by user. Saving results collected so far...")
                        scraper.close()
                        break
                    except Exception as e:
                        print(f"  ERROR during scrape: {e}")
                        result = SwiggyProductData(url=url, error=str(e))

                    # Close browser after each URL
                    print(f"  Closing browser...")
                    scraper.close()

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

            # Save partial results after each URL
            if args.output and results:
                save_to_csv(results, args.output, pincode=args.pincode, quiet=True)

            # Delay before next URL (within same batch)
            if i < len(urls):
                next_url_in_batch = i % args.batch_size  # position of NEXT url
                if next_url_in_batch != 0:
                    # Normal delay within batch
                    jitter = args.delay * random.uniform(-0.3, 0.3)
                    wait = max(5, args.delay + jitter)
                    print(f"  Waiting {wait:.1f}s before next request...")
                    time.sleep(wait)
                # else: batch boundary — the long pause happens at the top of the loop

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
