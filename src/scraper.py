"""
Amazon ASIN Scraper for Price and BSR (Best Seller Rank)
"""

import re
import time
import random
from typing import Optional
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

# Selenium imports (optional, for browser mode)
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False


@dataclass
class ProductData:
    """Data class for Amazon product information."""
    asin: str
    title: Optional[str] = None
    price: Optional[str] = None
    price_value: Optional[float] = None
    bsr: Optional[str] = None
    bsr_value: Optional[int] = None
    bsr_category: Optional[str] = None
    seller: Optional[str] = None
    fulfilled_by: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None


class AmazonScraper:
    """Scraper for Amazon product price and BSR data."""

    BASE_URL = "https://www.amazon.com/dp/{asin}"

    def __init__(self, marketplace: str = "com", debug: bool = False, use_browser: bool = False):
        """
        Initialize the scraper.

        Args:
            marketplace: Amazon marketplace (com, co.uk, de, etc.)
            debug: If True, save HTML to file for inspection
            use_browser: If True, use Selenium browser instead of requests
        """
        self.marketplace = marketplace
        self.base_url = f"https://www.amazon.{marketplace}/dp/{{asin}}"
        self.ua = UserAgent()
        self.session = requests.Session()
        self.debug = debug
        self.use_browser = use_browser
        self.driver = None

        if use_browser:
            if not SELENIUM_AVAILABLE:
                raise ImportError("Selenium not installed. Run: pip install selenium webdriver-manager")
            self._init_browser()

    def _init_browser(self):
        """Initialize Chrome browser with anti-detection options."""
        options = Options()
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)

        # Remove webdriver flag
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    def _fetch_page_browser(self, asin: str) -> Optional[str]:
        """Fetch page using Selenium browser."""
        url = self.base_url.format(asin=asin)

        try:
            self.driver.get(url)
            # Wait for initial page load
            time.sleep(2)

            # Scroll down to trigger lazy loading
            self.driver.execute_script("window.scrollTo(0, 500);")
            time.sleep(1)

            # Wait for product title to appear
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.ID, "productTitle"))
                )
            except:
                pass

            # Try to wait for price element
            try:
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "a-price"))
                )
            except:
                pass

            # Additional wait for dynamic content
            time.sleep(2)

            return self.driver.page_source
        except Exception as e:
            print(f"Browser error for ASIN {asin}: {e}")
            return None

    def close(self):
        """Close the browser if open."""
        if self.driver:
            self.driver.quit()
            self.driver = None

    def _get_headers(self) -> dict:
        """Generate request headers with random user agent."""
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }

    def _fetch_page(self, asin: str) -> Optional[str]:
        """
        Fetch the Amazon product page HTML.

        Args:
            asin: Amazon Standard Identification Number

        Returns:
            HTML content or None if request fails
        """
        url = self.base_url.format(asin=asin)

        try:
            response = self.session.get(
                url,
                headers=self._get_headers(),
                timeout=15
            )
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            print(f"Error fetching page for ASIN {asin}: {e}")
            return None

    def _parse_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract product title from page."""
        # Try primary selector
        title_elem = soup.find("span", {"id": "productTitle"})
        if title_elem:
            return title_elem.get_text(strip=True)

        # Try alternate selectors
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

        # Try meta tag
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
                # Look for offscreen price first
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
                        price_text = f"₹{match.group(1)}"
                        return price_text, price_value
                except ValueError:
                    continue

        return None, None

    def _extract_price_value(self, price_text: str) -> Optional[float]:
        """Extract numeric value from price string."""
        # Remove currency symbols and whitespace
        cleaned = re.sub(r'[^\d.,]', '', price_text)
        # Remove commas (handles both 1,000 and 1,00,000 formats)
        cleaned = cleaned.replace(",", "")
        # Extract the number
        match = re.search(r'[\d]+\.?\d*', cleaned)
        if match:
            try:
                return float(match.group())
            except ValueError:
                pass
        return None

    def _parse_bsr(self, soup: BeautifulSoup) -> tuple[Optional[str], Optional[int], Optional[str]]:
        """
        Extract Best Seller Rank from the product page.

        Returns:
            Tuple of (bsr_string, bsr_value, category)
        """
        bsr_patterns = [
            r'#([\d,]+)\s+in\s+([^(\n]+)',
            r'Best Sellers Rank[:\s]*#?([\d,]+)\s+in\s+([^(\n]+)',
        ]

        # Check product details section
        details_section = soup.find("div", {"id": "detailBulletsWrapper_feature_div"})
        if details_section:
            text = details_section.get_text()
            for pattern in bsr_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    bsr_str = f"#{match.group(1)} in {match.group(2).strip()}"
                    bsr_value = int(match.group(1).replace(",", ""))
                    category = match.group(2).strip()
                    return bsr_str, bsr_value, category

        # Check product information table
        tables = soup.find_all("table", {"id": "productDetails_detailBullets_sections1"})
        for table in tables:
            text = table.get_text()
            for pattern in bsr_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    bsr_str = f"#{match.group(1)} in {match.group(2).strip()}"
                    bsr_value = int(match.group(1).replace(",", ""))
                    category = match.group(2).strip()
                    return bsr_str, bsr_value, category

        # Check entire page as fallback
        page_text = soup.get_text()
        for pattern in bsr_patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                bsr_str = f"#{match.group(1)} in {match.group(2).strip()}"
                bsr_value = int(match.group(1).replace(",", ""))
                category = match.group(2).strip()
                return bsr_str, bsr_value, category

        return None, None, None

    def _parse_seller(self, soup: BeautifulSoup) -> tuple[Optional[str], Optional[str]]:
        """
        Extract seller name and fulfillment info from the product page.

        Returns:
            Tuple of (seller_name, fulfilled_by)
        """
        seller = None
        fulfilled_by = None

        # Method 1: Check #merchant-info div (common on Amazon India)
        merchant_info = soup.find("div", {"id": "merchant-info"})
        if merchant_info:
            text = merchant_info.get_text(strip=True)
            # Extract seller name: "Sold by <seller> and Fulfilled by <fulfiller>"
            sold_match = re.search(r'Sold by\s+(.+?)(?:\s+and\s+|\s*$)', text, re.IGNORECASE)
            if sold_match:
                seller = sold_match.group(1).strip().rstrip(".")
            fulfilled_match = re.search(r'Fulfilled by\s+(.+?)(?:\.|$)', text, re.IGNORECASE)
            if fulfilled_match:
                fulfilled_by = fulfilled_match.group(1).strip().rstrip(".")

        # Method 2: Check seller profile link
        if not seller:
            seller_link = soup.find("a", {"id": "sellerProfileTriggerId"})
            if seller_link:
                seller = seller_link.get_text(strip=True)

        # Method 3: Check tabular-buybox (newer layout)
        if not seller:
            buybox = soup.find("div", {"id": "tabular-buybox"})
            if buybox:
                text = buybox.get_text()
                sold_match = re.search(r'Sold by\s*(.+?)(?:Fulfilled|Ships|$)', text, re.IGNORECASE)
                if sold_match:
                    seller = sold_match.group(1).strip()
                fulfilled_match = re.search(r'Fulfilled by\s*(.+?)(?:\n|$)', text, re.IGNORECASE)
                if fulfilled_match:
                    fulfilled_by = fulfilled_match.group(1).strip()

        # Method 4: Search in buybox area
        if not seller:
            buybox_area = soup.find("div", {"id": "buyBoxAccordion"})
            if not buybox_area:
                buybox_area = soup.find("div", {"id": "desktop_buybox"})
            if buybox_area:
                text = buybox_area.get_text()
                sold_match = re.search(r'Sold by\s+(.+?)(?:\s+and\s+|\n|$)', text, re.IGNORECASE)
                if sold_match:
                    seller = sold_match.group(1).strip()

        # Method 5: Regex on full page as fallback
        if not seller:
            page_text = soup.get_text()
            sold_match = re.search(r'Sold by\s+(.+?)(?:\s+and\s+Fulfilled|\n|$)', page_text, re.IGNORECASE)
            if sold_match:
                seller = sold_match.group(1).strip()
            if not fulfilled_by:
                fulfilled_match = re.search(r'Fulfilled by\s+(.+?)(?:\.|,|\n|$)', page_text, re.IGNORECASE)
                if fulfilled_match:
                    fulfilled_by = fulfilled_match.group(1).strip()

        return seller, fulfilled_by

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

        # Use browser or requests based on setting
        if self.use_browser:
            html = self._fetch_page_browser(asin)
        else:
            html = self._fetch_page(asin)

        if not html:
            result.error = "Failed to fetch page"
            return result

        # Save HTML for debugging
        if self.debug:
            with open(f"debug_{asin}.html", "w", encoding="utf-8") as f:
                f.write(html)

        soup = BeautifulSoup(html, "lxml")

        # Check for CAPTCHA or bot detection
        if "Enter the characters you see below" in html or "api-services-support@amazon.com" in html:
            result.error = "Bot detection triggered - CAPTCHA required"
            return result

        # Parse data
        result.title = self._parse_title(soup)
        result.price, result.price_value = self._parse_price(soup)
        result.bsr, result.bsr_value, result.bsr_category = self._parse_bsr(soup)
        result.seller, result.fulfilled_by = self._parse_seller(soup)

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
            result = self.scrape(asin)
            results.append(result)

            # Add delay between requests (with some randomization)
            if i < len(asins) - 1:
                time.sleep(delay + random.uniform(0, 1))

        return results


def scrape_asin(asin: str, marketplace: str = "com") -> ProductData:
    """
    Convenience function to scrape a single ASIN.

    Args:
        asin: Amazon Standard Identification Number
        marketplace: Amazon marketplace (com, co.uk, de, etc.)

    Returns:
        ProductData object with scraped information
    """
    scraper = AmazonScraper(marketplace=marketplace)
    return scraper.scrape(asin)
