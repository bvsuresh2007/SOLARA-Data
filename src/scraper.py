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
    # Subcategory BSR fields
    sub_bsr: Optional[str] = None
    sub_bsr_value: Optional[int] = None
    sub_bsr_category: Optional[str] = None
    # All BSR entries as list (for multiple subcategories)
    all_bsr: Optional[list] = None
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

    def _parse_bsr(self, soup: BeautifulSoup) -> dict:
        """
        Extract all Best Seller Ranks from the product page (main + subcategories).

        Returns:
            Dict with keys: bsr, bsr_value, bsr_category, sub_bsr, sub_bsr_value,
                           sub_bsr_category, all_bsr
        """
        result = {
            'bsr': None, 'bsr_value': None, 'bsr_category': None,
            'sub_bsr': None, 'sub_bsr_value': None, 'sub_bsr_category': None,
            'all_bsr': []
        }

        bsr_pattern = r'#([\d,]+)\s+in\s+([^(\n<]+)'
        all_bsr_entries = []

        # Method 1: Check product details section (detailBulletsWrapper)
        details_section = soup.find("div", {"id": "detailBulletsWrapper_feature_div"})
        if details_section:
            # Find all BSR entries
            text = details_section.get_text(separator="\n")
            matches = re.findall(bsr_pattern, text, re.IGNORECASE)
            for match in matches:
                rank = int(match[0].replace(",", ""))
                category = match[1].strip()
                # Clean up category name
                category = re.sub(r'\s+', ' ', category).strip()
                if category and rank > 0:
                    all_bsr_entries.append({
                        'rank': rank,
                        'category': category,
                        'string': f"#{match[0]} in {category}"
                    })

        # Method 2: Check product information table
        if not all_bsr_entries:
            tables = soup.find_all("table", {"id": "productDetails_detailBullets_sections1"})
            for table in tables:
                # Find BSR row
                rows = table.find_all("tr")
                for row in rows:
                    header = row.find("th")
                    if header and "Best Sellers Rank" in header.get_text():
                        cell = row.find("td")
                        if cell:
                            # Extract all BSR entries from the cell
                            text = cell.get_text(separator="\n")
                            matches = re.findall(bsr_pattern, text, re.IGNORECASE)
                            for match in matches:
                                rank = int(match[0].replace(",", ""))
                                category = match[1].strip()
                                category = re.sub(r'\s+', ' ', category).strip()
                                if category and rank > 0:
                                    all_bsr_entries.append({
                                        'rank': rank,
                                        'category': category,
                                        'string': f"#{match[0]} in {category}"
                                    })

        # Method 3: Check for BSR in span elements (Amazon India format)
        if not all_bsr_entries:
            bsr_spans = soup.find_all("span", string=re.compile(r"Best Sellers Rank", re.I))
            for span in bsr_spans:
                parent = span.find_parent("li") or span.find_parent("tr") or span.find_parent("div")
                if parent:
                    text = parent.get_text(separator="\n")
                    matches = re.findall(bsr_pattern, text, re.IGNORECASE)
                    for match in matches:
                        rank = int(match[0].replace(",", ""))
                        category = match[1].strip()
                        category = re.sub(r'\s+', ' ', category).strip()
                        if category and rank > 0:
                            all_bsr_entries.append({
                                'rank': rank,
                                'category': category,
                                'string': f"#{match[0]} in {category}"
                            })

        # Method 4: Search entire page as fallback
        if not all_bsr_entries:
            page_text = soup.get_text(separator="\n")
            # Look for BSR section
            bsr_section_match = re.search(
                r'Best Sellers Rank[:\s]*(.*?)(?=Customer Reviews|Product details|$)',
                page_text, re.IGNORECASE | re.DOTALL
            )
            if bsr_section_match:
                section_text = bsr_section_match.group(1)
                matches = re.findall(bsr_pattern, section_text, re.IGNORECASE)
                for match in matches:
                    rank = int(match[0].replace(",", ""))
                    category = match[1].strip()
                    category = re.sub(r'\s+', ' ', category).strip()
                    if category and rank > 0:
                        all_bsr_entries.append({
                            'rank': rank,
                            'category': category,
                            'string': f"#{match[0]} in {category}"
                        })

        # Remove duplicates and sort by rank (higher rank number = less popular, so main category usually has higher number)
        seen = set()
        unique_entries = []
        for entry in all_bsr_entries:
            key = (entry['rank'], entry['category'])
            if key not in seen:
                seen.add(key)
                unique_entries.append(entry)

        # Sort: main category (higher rank) first, then subcategories (lower ranks)
        unique_entries.sort(key=lambda x: x['rank'], reverse=True)

        if unique_entries:
            # First entry is main category (usually has highest rank number)
            main = unique_entries[0]
            result['bsr'] = main['string']
            result['bsr_value'] = main['rank']
            result['bsr_category'] = main['category']

            # Second entry is primary subcategory
            if len(unique_entries) > 1:
                sub = unique_entries[1]
                result['sub_bsr'] = sub['string']
                result['sub_bsr_value'] = sub['rank']
                result['sub_bsr_category'] = sub['category']

            # All entries
            result['all_bsr'] = unique_entries

        return result

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

        # Parse all BSR data (main + subcategories)
        bsr_data = self._parse_bsr(soup)
        result.bsr = bsr_data['bsr']
        result.bsr_value = bsr_data['bsr_value']
        result.bsr_category = bsr_data['bsr_category']
        result.sub_bsr = bsr_data['sub_bsr']
        result.sub_bsr_value = bsr_data['sub_bsr_value']
        result.sub_bsr_category = bsr_data['sub_bsr_category']
        result.all_bsr = bsr_data['all_bsr']

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
