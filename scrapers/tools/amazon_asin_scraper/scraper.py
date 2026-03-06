"""
Amazon ASIN Scraper for Price and BSR (Best Seller Rank) — Playwright

Scrapes live price, BSR (main + sub-categories), and seller info
from Amazon product pages.

Replaces Selenium browser mode with Playwright while keeping all
parsing logic unchanged.
"""

import re
import time
import random
from dataclasses import dataclass
from typing import Optional

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Page, BrowserContext


# ── Stealth: injected before any page JS runs ─────────────────────────────────
_STEALTH = """
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
    Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
    window.chrome = {runtime: {}};
    const origQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = p =>
        p.name === 'notifications'
            ? Promise.resolve({state: Notification.permission})
            : origQuery(p);
"""

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


@dataclass
class ProductData:
    """Data class for Amazon product information."""
    asin: str
    title: Optional[str] = None
    price: Optional[str] = None
    price_value: Optional[float] = None
    # Main category BSR
    bsr: Optional[str] = None
    bsr_value: Optional[int] = None
    bsr_category: Optional[str] = None
    # Sub-category BSR
    sub_bsr: Optional[str] = None
    sub_bsr_value: Optional[int] = None
    sub_bsr_category: Optional[str] = None
    # All BSR rankings as list
    all_bsr: Optional[list] = None
    # Seller info
    seller: Optional[str] = None
    ships_from: Optional[str] = None
    fulfilled_by: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None


class AmazonScraper:
    """Playwright-based Amazon product price and BSR scraper."""

    def __init__(self, marketplace: str = "com", debug: bool = False, headless: bool = True):
        """
        Initialize the scraper.

        Args:
            marketplace: Amazon marketplace (com, in, co.uk, de, etc.)
            debug: If True, save HTML to file for inspection
            headless: If False, show the browser window
        """
        self.marketplace = marketplace
        self.base_url = f"https://www.amazon.{marketplace}/dp/{{asin}}"
        self.debug = debug
        self.headless = headless
        self._pw = None
        self._browser = None

    # ── Browser lifecycle ─────────────────────────────────────────────────────

    def _launch(self):
        self._pw = sync_playwright().__enter__()
        self._browser = self._pw.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )

    def close(self):
        """Close the browser."""
        try:
            self._browser.close()
        except Exception:
            pass
        try:
            self._pw.__exit__(None, None, None)
        except Exception:
            pass
        self._pw = self._browser = None

    # ── Page fetching ─────────────────────────────────────────────────────────

    def _fetch_page(self, asin: str) -> Optional[str]:
        """
        Fetch the Amazon product page HTML using Playwright.

        Replicates the original Selenium browser mode behaviour:
          navigate → wait 2s → scroll to 500px → wait for #productTitle →
          wait for .a-price → wait 2s → return page HTML
        """
        if not self._browser:
            self._launch()

        url = self.base_url.format(asin=asin)

        ctx: BrowserContext = self._browser.new_context(
            user_agent=_UA,
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        try:
            page: Page = ctx.new_page()
            page.set_default_timeout(30_000)
            page.add_init_script(_STEALTH)

            page.goto(url, wait_until="domcontentloaded", timeout=30_000)

            # Initial settle — mirrors Selenium's time.sleep(2)
            page.wait_for_timeout(2_000)

            # Scroll to trigger lazy loading — mirrors Selenium's scrollTo(0, 500)
            page.evaluate("window.scrollTo(0, 500)")
            page.wait_for_timeout(1_000)

            # Wait for product title — mirrors Selenium's WebDriverWait(10) for #productTitle
            try:
                page.wait_for_selector("#productTitle", timeout=10_000)
            except Exception:
                pass

            # Wait for price element — mirrors Selenium's WebDriverWait(5) for .a-price
            try:
                page.wait_for_selector(".a-price", timeout=5_000)
            except Exception:
                pass

            # Final settle for dynamic content — mirrors Selenium's time.sleep(2)
            page.wait_for_timeout(2_000)

            html = page.content()

            if self.debug:
                fname = f"debug_{asin}.html"
                with open(fname, "w", encoding="utf-8") as f:
                    f.write(html)
                print(f"  Debug HTML -> {fname}")

            return html

        except Exception as e:
            print(f"Browser error for ASIN {asin}: {e}")
            return None
        finally:
            ctx.close()

    # ── Parsing ────────────────────────────────────────────────────────────────
    # All parsing methods are unchanged — they operate on BeautifulSoup HTML.

    def _parse_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract product title from page."""
        title_elem = soup.find("span", {"id": "productTitle"})
        if title_elem:
            return title_elem.get_text(strip=True)

        title_selectors = [
            ("h1", {"id": "title"}),
            ("h1", {"class": "a-size-large"}),
            ("span", {"class": "product-title-word-break"}),
            ("h1", {}),
        ]
        for tag, attrs in title_selectors:
            elem = soup.find(tag, attrs)
            if elem:
                text = elem.get_text(strip=True)
                if text and len(text) > 10:
                    return text

        meta_title = soup.find("meta", {"name": "title"})
        if meta_title and meta_title.get("content"):
            return meta_title["content"]

        return None

    def _parse_price(self, soup: BeautifulSoup) -> tuple[Optional[str], Optional[float]]:
        """
        Extract price from the product page.

        Returns:
            Tuple of (price_string, price_float)
        """
        # Method 1: Find all a-offscreen spans (contains hidden price text)
        offscreen_prices = soup.find_all("span", {"class": "a-offscreen"})
        for offscreen in offscreen_prices:
            price_text = offscreen.get_text(strip=True)
            if price_text and ("₹" in price_text or "$" in price_text or "£" in price_text or "€" in price_text):
                price_value = self._extract_price_value(price_text)
                if price_value and price_value > 0:
                    return price_text, price_value

        # Method 2: Look for price in specific containers
        price_containers = [
            ("div", {"id": "corePriceDisplay_desktop_feature_div"}),
            ("div", {"id": "corePrice_feature_div"}),
            ("div", {"id": "apex_desktop"}),
            ("span", {"id": "priceblock_ourprice"}),
            ("span", {"id": "priceblock_dealprice"}),
            ("span", {"id": "priceblock_saleprice"}),
            ("div", {"id": "tp_price_block_total_price_ww"}),
            ("span", {"class": "priceToPay"}),
            ("span", {"class": "a-price"}),
        ]
        for tag, attrs in price_containers:
            container = soup.find(tag, attrs)
            if container:
                offscreen = container.find("span", {"class": "a-offscreen"})
                if offscreen:
                    price_text = offscreen.get_text(strip=True)
                    price_value = self._extract_price_value(price_text)
                    if price_value and price_value > 0:
                        return price_text, price_value

        # Method 3: Build price from whole + fraction
        price_whole = soup.find("span", {"class": "a-price-whole"})
        if price_whole:
            whole = price_whole.get_text(strip=True).replace(".", "").replace(",", "")
            fraction_elem = soup.find("span", {"class": "a-price-fraction"})
            fraction = fraction_elem.get_text(strip=True) if fraction_elem else "00"
            symbol_elem = soup.find("span", {"class": "a-price-symbol"})
            symbol = symbol_elem.get_text(strip=True) if symbol_elem else "₹"
            price_text = f"{symbol}{whole}.{fraction}"
            price_value = self._extract_price_value(price_text)
            if price_value and price_value > 0:
                return price_text, price_value

        # Method 4: Search in raw HTML for price patterns
        html_str = str(soup)
        price_patterns = [
            r'₹\s?([\d,]+(?:\.\d{2})?)',
            r'"priceAmount":\s*"?([\d.]+)"?',
            r'"price":\s*"?₹?\s*([\d,]+(?:\.\d{2})?)"?',
            r'data-price="([\d.]+)"',
        ]
        for pattern in price_patterns:
            match = re.search(pattern, html_str)
            if match:
                price_num = match.group(1).replace(",", "")
                try:
                    price_value = float(price_num)
                    if price_value > 0:
                        return f"₹{match.group(1)}", price_value
                except ValueError:
                    continue

        return None, None

    def _extract_price_value(self, price_text: str) -> Optional[float]:
        """Extract numeric value from price string."""
        cleaned = re.sub(r'[^\d.,]', '', price_text)
        cleaned = cleaned.replace(",", "")
        match = re.search(r'[\d]+\.?\d*', cleaned)
        if match:
            try:
                return float(match.group())
            except ValueError:
                pass
        return None

    def _parse_bsr(self, soup: BeautifulSoup) -> dict:
        """
        Extract all Best Seller Ranks from the product page.

        Returns:
            Dict with main_bsr, main_bsr_value, main_category,
                  sub_bsr, sub_bsr_value, sub_category, all_bsr
        """
        result = {
            "main_bsr": None,
            "main_bsr_value": None,
            "main_category": None,
            "sub_bsr": None,
            "sub_bsr_value": None,
            "sub_category": None,
            "all_bsr": [],
        }

        # Pattern to find all BSR entries: #123 in Category Name
        bsr_pattern = r'#([\d,]+)\s+in\s+([^\n(]+?)(?:\s*\(|$|\n)'

        bsr_text = ""

        # Check product details section
        details_section = soup.find("div", {"id": "detailBulletsWrapper_feature_div"})
        if details_section:
            bsr_text = details_section.get_text()

        # Check product information table
        if not bsr_text:
            table = soup.find("table", {"id": "productDetails_detailBullets_sections1"})
            if table:
                bsr_text = table.get_text()

        # Check techProductInfoTable (another common location)
        if not bsr_text:
            tech_table = soup.find("div", {"id": "detailBullets_feature_div"})
            if tech_table:
                bsr_text = tech_table.get_text()

        # Fallback to entire page
        if not bsr_text:
            bsr_text = soup.get_text()

        # Find all BSR matches
        matches = re.findall(bsr_pattern, bsr_text, re.IGNORECASE)

        for rank, category in matches:
            rank_value = int(rank.replace(",", ""))
            category = category.strip()

            # Skip invalid categories
            if len(category) < 3 or category.lower() in ["see top 100", "see top"]:
                continue

            result["all_bsr"].append({
                "rank": rank_value,
                "category": category,
                "display": f"#{rank} in {category}",
            })

        # Sort by rank (lowest first)
        result["all_bsr"].sort(key=lambda x: x["rank"])

        # Main category: highest rank number (broadest)
        # Sub-category: lowest rank number (most specific)
        if result["all_bsr"]:
            main = max(result["all_bsr"], key=lambda x: x["rank"])
            result["main_bsr"] = main["display"]
            result["main_bsr_value"] = main["rank"]
            result["main_category"] = main["category"]

            sub = min(result["all_bsr"], key=lambda x: x["rank"])
            if sub != main:
                result["sub_bsr"] = sub["display"]
                result["sub_bsr_value"] = sub["rank"]
                result["sub_category"] = sub["category"]

        return result

    def _parse_seller(self, soup: BeautifulSoup) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Extract seller name, ships_from and fulfillment info.

        Returns:
            Tuple of (seller_name, ships_from, fulfilled_by)
        """
        seller = None
        ships_from = None
        fulfilled_by = None

        # Method 1: Tabular buybox (Amazon India layout)
        tabular = soup.find("div", {"id": "tabular-buybox"})
        if tabular:
            text = tabular.get_text(" ", strip=True)
            ships_match = re.search(r'Ships from\s+(.+?)(?:Sold by|Gift|Payment|$)', text, re.IGNORECASE)
            if ships_match:
                ships_from = ships_match.group(1).strip()
            sold_match = re.search(r'Sold by\s+(.+?)(?:Gift|Payment|Ships|$)', text, re.IGNORECASE)
            if sold_match:
                seller = sold_match.group(1).strip()
            fulfilled_match = re.search(r'Fulfilled by\s+(.+?)(?:\.|,|Gift|Payment|$)', text, re.IGNORECASE)
            if fulfilled_match:
                fulfilled_by = fulfilled_match.group(1).strip()

        # Method 2: Check #merchant-info div
        if not seller:
            merchant_info = soup.find("div", {"id": "merchant-info"})
            if merchant_info:
                text = merchant_info.get_text(strip=True)
                sold_match = re.search(r'Sold by\s+(.+?)(?:\s+and\s+|\s*$)', text, re.IGNORECASE)
                if sold_match:
                    seller = sold_match.group(1).strip().rstrip(".")
                fulfilled_match = re.search(r'Fulfilled by\s+(.+?)(?:\.|$)', text, re.IGNORECASE)
                if fulfilled_match:
                    fulfilled_by = fulfilled_match.group(1).strip().rstrip(".")

        # Method 3: Seller profile link
        if not seller:
            seller_link = soup.find("a", {"id": "sellerProfileTriggerId"})
            if seller_link:
                seller = seller_link.get_text(strip=True)

        # Method 4: Desktop buybox area
        if not seller:
            buybox_area = soup.find("div", {"id": "desktop_buybox"})
            if buybox_area:
                text = buybox_area.get_text(" ", strip=True)
                sold_match = re.search(r'Sold by\s+(.+?)(?:Gift|Payment|Ships|\s+and\s+|$)', text, re.IGNORECASE)
                if sold_match:
                    seller = sold_match.group(1).strip()
                if not ships_from:
                    ships_match = re.search(r'Ships from\s+(.+?)(?:Sold|Gift|Payment|$)', text, re.IGNORECASE)
                    if ships_match:
                        ships_from = ships_match.group(1).strip()

        # Method 5: Full page fallback
        if not seller:
            page_text = soup.get_text()
            sold_match = re.search(r'Sold by\s+(.+?)(?:\s+and\s+Fulfilled|\n|Gift|Payment|$)', page_text, re.IGNORECASE)
            if sold_match:
                seller = sold_match.group(1).strip()

        # Derive fulfilled_by from ships_from if not set
        if ships_from and not fulfilled_by:
            if "amazon" in ships_from.lower():
                fulfilled_by = "Amazon"

        return seller, ships_from, fulfilled_by

    # ── Public API ─────────────────────────────────────────────────────────────

    def scrape(self, asin: str) -> ProductData:
        """
        Scrape price and BSR for a given ASIN.

        Args:
            asin: Amazon Standard Identification Number

        Returns:
            ProductData object with scraped information
        """
        url = self.base_url.format(asin=asin)
        result = ProductData(asin=asin, url=url)

        html = self._fetch_page(asin)

        if not html:
            result.error = "Failed to fetch page"
            return result

        if self.debug:
            fname = f"debug_{asin}.html"
            with open(fname, "w", encoding="utf-8") as f:
                f.write(html)

        soup = BeautifulSoup(html, "lxml")

        # Check for CAPTCHA or bot detection
        if ("Enter the characters you see below" in html
                or "api-services-support@amazon.com" in html):
            result.error = "Bot detection triggered - CAPTCHA required"
            return result

        # Parse data
        result.title = self._parse_title(soup)
        result.price, result.price_value = self._parse_price(soup)

        # Parse BSR (main + sub-categories)
        bsr_data = self._parse_bsr(soup)
        result.bsr = bsr_data["main_bsr"]
        result.bsr_value = bsr_data["main_bsr_value"]
        result.bsr_category = bsr_data["main_category"]
        result.sub_bsr = bsr_data["sub_bsr"]
        result.sub_bsr_value = bsr_data["sub_bsr_value"]
        result.sub_bsr_category = bsr_data["sub_category"]
        result.all_bsr = bsr_data["all_bsr"]

        result.seller, result.ships_from, result.fulfilled_by = self._parse_seller(soup)

        return result

    def scrape_multiple(self, asins: list[str], delay: float = 2.0) -> list[ProductData]:
        """
        Scrape multiple ASINs with delay between requests.

        Args:
            asins: List of ASINs to scrape
            delay: Delay between requests in seconds

        Returns:
            List of ProductData objects
        """
        results = []
        for i, asin in enumerate(asins):
            results.append(self.scrape(asin))
            if i < len(asins) - 1:
                time.sleep(delay + random.uniform(0, 1))
        return results


def scrape_asin(asin: str, marketplace: str = "com") -> ProductData:
    """
    Convenience function to scrape a single ASIN.

    Args:
        asin: Amazon Standard Identification Number
        marketplace: Amazon marketplace (com, in, co.uk, de, etc.)

    Returns:
        ProductData object with scraped information
    """
    scraper = AmazonScraper(marketplace=marketplace)
    return scraper.scrape(asin)
