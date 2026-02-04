#!/usr/bin/env python3
"""
Swiggy Instamart Product Scraper CLI

Usage:
    python swiggy_main.py                                    # Scrape all categories
    python swiggy_main.py -s milk bread eggs                 # Search specific items
    python swiggy_main.py -p 560103 -o results.csv           # Custom pincode + CSV
    python swiggy_main.py -s rice --slack                    # Search + Slack notify
    python swiggy_main.py --no-headless -s milk --debug      # Visible browser + debug
"""

import sys
import csv
import json
import argparse
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime

import requests as req

from src.swiggy_scraper import SwiggyInstamartScraper, SwiggyProduct, PINCODE_COORDS
from src.slack_notifier import save_webhook, load_webhook


def print_result(product: SwiggyProduct, index: int = None, total: int = None) -> None:
    """Print a single product in a compact formatted line."""
    progress = f"[{index}/{total}] " if index and total else ""
    name = (product.name[:45] + "...") if len(product.name) > 48 else product.name
    print(f"{progress}{name}", end="")

    if product.error:
        print(f"  ERROR: {product.error}")
    else:
        price_str = f"₹{product.price:.0f}" if product.price else "N/A"
        mrp_str = f"₹{product.mrp:.0f}" if product.mrp else ""
        discount_str = product.discount or ""
        qty_str = product.quantity or ""
        avail_str = "" if product.available else " [OUT OF STOCK]"

        print(f"  {price_str}", end="")
        if mrp_str and product.mrp != product.price:
            print(f" (MRP: {mrp_str})", end="")
        if discount_str:
            print(f" [{discount_str}]", end="")
        if qty_str:
            print(f" - {qty_str}", end="")
        print(avail_str)


def print_category_report(results: list[SwiggyProduct]) -> None:
    """Print a category-level summary report."""
    cat_groups = defaultdict(list)
    for r in results:
        if r.error:
            cat_groups["[ERROR]"].append(r)
        else:
            cat_groups[r.category or "[UNCATEGORIZED]"].append(r)

    print(f"\n{'#' * 60}")
    print(f"  CATEGORY REPORT")
    print(f"{'#' * 60}")

    for cat, items in sorted(cat_groups.items()):
        prices = [r.price for r in items if r.price]
        in_stock = sum(1 for r in items if r.available)

        print(f"\n  Category:  {cat}")
        print(f"  Products:  {len(items)} ({in_stock} in stock)")

        if prices:
            avg_price = sum(prices) / len(prices)
            min_price = min(prices)
            max_price = max(prices)
            print(f"  Prices:    Avg ₹{avg_price:,.0f} | Min ₹{min_price:,.0f} | Max ₹{max_price:,.0f}")

    print(f"\n{'#' * 60}")


def save_to_csv(results: list[SwiggyProduct], filepath: str) -> None:
    """Save results to CSV file with UTF-8 BOM for Excel compatibility."""
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Name", "Brand", "Price", "MRP", "Discount",
            "Quantity", "Category", "Available",
            "Image_URL", "Delivery_Time", "Scraped_At"
        ])
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for r in results:
            writer.writerow([
                r.name,
                r.brand or "",
                r.price or "",
                r.mrp or "",
                r.discount or "",
                r.quantity or "",
                r.category or "",
                "Yes" if r.available else "No",
                r.image_url or "",
                r.delivery_time or "",
                timestamp,
            ])
    print(f"\nResults saved to: {filepath}")


def format_swiggy_slack_message(results: list[SwiggyProduct], pincode: str) -> str:
    """Format Swiggy Instamart results for Slack."""
    with_price = [r for r in results if not r.error and r.price]
    failed = [r for r in results if r.error]
    in_stock = sum(1 for r in results if r.available and not r.error)

    lines = []
    lines.append(f"*Swiggy Instamart Scraper Report — Pincode {pincode}*")
    lines.append(
        f"Total: {len(results)} | With Price: {len(with_price)} "
        f"| In Stock: {in_stock} | Failed: {len(failed)}"
    )
    lines.append("")

    # Table of products (capped at 50 for Slack message limits)
    lines.append("```")
    lines.append(f"{'Product':<30} {'Price':>8} {'MRP':>8} {'Discount':>10}")
    lines.append("-" * 60)

    for r in with_price[:50]:
        name = (r.name[:28] + "..") if len(r.name) > 30 else r.name
        price = f"₹{r.price:.0f}" if r.price else "N/A"
        mrp = f"₹{r.mrp:.0f}" if r.mrp else ""
        discount = r.discount or ""
        lines.append(f"{name:<30} {price:>8} {mrp:>8} {discount:>10}")

    if len(with_price) > 50:
        lines.append(f"... and {len(with_price) - 50} more products")

    lines.append("```")

    if failed:
        lines.append(f"\n*Failed ({len(failed)}):*")
        for r in failed[:10]:
            lines.append(f"  `{r.name}` — {r.error}")

    return "\n".join(lines)


def post_swiggy_to_slack(webhook_url: str, results: list[SwiggyProduct],
                         pincode: str, csv_path: str = None) -> bool:
    """Post Swiggy Instamart results to Slack via incoming webhook."""
    message = format_swiggy_slack_message(results, pincode)

    if csv_path:
        message += f"\n\nCSV saved: `{csv_path}`"

    payload = {"text": message}

    try:
        response = req.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        if response.status_code == 200:
            print("Results posted to Slack successfully!")
            return True
        else:
            print(f"Slack error: {response.status_code} - {response.text}")
            return False
    except req.RequestException as e:
        print(f"Failed to post to Slack: {e}")
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Scrape Swiggy Instamart product data"
    )
    parser.add_argument(
        "-s", "--search", nargs="+",
        help="Search terms (e.g., -s milk bread eggs)"
    )
    parser.add_argument(
        "-p", "--pincode", default="560103",
        help="Delivery pincode (default: 560103 — Koramangala, Bangalore)"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output CSV file path"
    )
    parser.add_argument(
        "--max-products", type=int, default=500,
        help="Maximum number of products to scrape (default: 500)"
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Save HTML pages to debug_*.html for inspection"
    )
    parser.add_argument(
        "--no-headless", action="store_true",
        help="Show the browser window (default: headless)"
    )
    parser.add_argument(
        "--slack", action="store_true",
        help="Post results to Slack after scraping"
    )
    parser.add_argument(
        "--slack-setup", metavar="WEBHOOK_URL",
        help="Save Slack webhook URL for future use"
    )

    args = parser.parse_args()

    # Handle Slack webhook setup
    if args.slack_setup:
        save_webhook(args.slack_setup)
        print("Slack webhook configured! Use --slack to post results.")
        if not args.search:
            sys.exit(0)

    # Show configuration
    area = PINCODE_COORDS.get(args.pincode, {}).get("area", "Unknown area")
    print(f"\nSwiggy Instamart Scraper")
    print(f"{'=' * 55}")
    print(f"Pincode:      {args.pincode} ({area})")
    if args.search:
        print(f"Search:       {', '.join(args.search)}")
    else:
        print("Mode:         Browse all categories")
    print(f"Max products: {args.max_products}")
    print(f"Browser:      {'visible' if args.no_headless else 'headless'}")
    print(f"{'=' * 55}")

    scraper = SwiggyInstamartScraper(
        pincode=args.pincode,
        debug=args.debug,
        headless=not args.no_headless,
    )

    results = []
    try:
        results = scraper.scrape_all(
            search_terms=args.search,
            max_products=args.max_products,
        )

        # Print results
        print(f"\n{'=' * 60}")
        print(f"  RESULTS: {len(results)} products found")
        print(f"{'=' * 60}")

        for i, product in enumerate(results, 1):
            print_result(product, i, len(results))

        # Category report
        print_category_report(results)

        # Summary stats
        with_price = sum(1 for r in results if r.price)
        in_stock = sum(1 for r in results if r.available)
        avg_price = (
            sum(r.price for r in results if r.price) / with_price
            if with_price else 0
        )

        print(f"\n{'=' * 60}")
        print(f"DONE: {len(results)} products | {with_price} with price | {in_stock} in stock")
        if avg_price:
            print(f"Average price: ₹{avg_price:,.0f}")
        print(f"{'=' * 60}")

        # Save to CSV
        if args.output:
            save_to_csv(results, args.output)

        # Post to Slack
        if args.slack:
            webhook_url = load_webhook()
            if webhook_url:
                post_swiggy_to_slack(
                    webhook_url, results,
                    pincode=args.pincode,
                    csv_path=args.output,
                )
            else:
                print("No Slack webhook configured. Run:")
                print("  python swiggy_main.py --slack-setup "
                      "https://hooks.slack.com/services/YOUR/WEBHOOK/URL")

        # JSON output if no CSV
        if not args.output:
            print("\nJSON Output:")
            json_results = [asdict(r) for r in results[:20]]
            print(json.dumps(json_results, indent=2, default=str))
            if len(results) > 20:
                print(f"... ({len(results) - 20} more products)")

    finally:
        scraper.close()


if __name__ == "__main__":
    main()
