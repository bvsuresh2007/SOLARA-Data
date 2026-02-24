"""
Blinkit Product Scraper for Price and Product Details
"""

import re
import time
import random
from typing import Optional
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

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
class BlinkitProductData:
    """Data class for Blinkit product information."""
    product_id: str
    title: Optional[str] = None
    price: Optional[str] = None
    price_value: Optional[float] = None
    mrp: Optional[str] = None
    mrp_value: Optional[float] = None
    discount: Optional[str] = None
    quantity: Optional[str] = None
    category: Optional[str] = None
    brand: Optional[str] = None
    in_stock: bool = True
    url: Optional[str] = None
    error: Optional[str] = None


class BlinkitScraper:
    """Scraper for Blinkit product price and details."""

    BASE_URL = "https://blinkit.com/prn/-/prid/{product_id}"
    API_URL = "https://blinkit.com/v2/product/{product_id}"

    def __init__(self, pincode: str = "110001", debug: bool = False, use_browser: bool = False):
        """
        Initialize the scraper.

        Args:
            pincode: Delivery pincode for location-based pricing
            debug: If True, save HTML/JSON to file for inspection
            use_browser: If True, use Selenium browser instead of API requests
        """
        self.pincode = pincode
        self.debug = debug
        self.use_browser = use_browser
        self.driver = None
        self.session = requests.Session()

        if use_browser:
            if not SELENIUM_AVAILABLE:
                raise ImportError("Selenium not installed. Run: pip install selenium webdriver-manager")
            self._init_browser()

    def _get_headers(self) -> dict:
        """Generate request headers."""
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Referer": "https://blinkit.com/",
            "Origin": "https://blinkit.com",
            "lat": "28.4594965",
            "lon": "77.0266383",
        }

    def _init_browser(self):
        """Initialize Chrome browser with anti-detection options."""
        options = Options()
        options.add_argument("--headless=new")
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

    @staticmethod
    def extract_product_id(url_or_id: str) -> str:
        """Extract product ID from a Blinkit URL or return as-is if already an ID."""
        url_or_id = url_or_id.strip()
        # If it's a URL, extract prid
        match = re.search(r'/prid/(\d+)', url_or_id)
        if match:
            return match.group(1)
        # If it's just a number, return as-is
        if url_or_id.isdigit():
            return url_or_id
        return url_or_id

    def _fetch_page_browser(self, product_id: str, url: str = None) -> Optional[str]:
        """Fetch page using Selenium browser."""
        if not url:
            url = self.BASE_URL.format(product_id=product_id)

        try:
            # First visit homepage to establish session/cookies
            self.driver.get("https://blinkit.com")
            time.sleep(2)

            # Now visit product page
            self.driver.get(url)
            # Wait for initial page load
            time.sleep(4)

            # Scroll down to trigger lazy loading
            self.driver.execute_script("window.scrollTo(0, 500);")
            time.sleep(2)

            # Wait for product content to appear
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "[class*='Product'], [class*='product'], h1, script#__NEXT_DATA__"))
                )
            except:
                pass

            # Additional wait for dynamic content
            time.sleep(2)

            return self.driver.page_source
        except Exception as e:
            print(f"Browser error for product {product_id}: {e}")
            return None

    def _fetch_api(self, product_id: str) -> Optional[dict]:
        """Fetch product data from Blinkit API."""
        # Try multiple API endpoints
        api_endpoints = [
            f"https://blinkit.com/v2/product/{product_id}",
            f"https://blinkit.com/v1/layout/product/{product_id}",
        ]

        for api_url in api_endpoints:
            try:
                response = self.session.get(
                    api_url,
                    headers=self._get_headers(),
                    timeout=15
                )
                if response.status_code == 200:
                    return response.json()
            except Exception as e:
                if self.debug:
                    print(f"API error for {api_url}: {e}")
                continue

        return None

    def _fetch_page_requests(self, product_id: str) -> Optional[str]:
        """Fetch page using requests."""
        url = self.BASE_URL.format(product_id=product_id)
        try:
            response = self.session.get(
                url,
                headers=self._get_headers(),
                timeout=15
            )
            if response.status_code == 200:
                return response.text
        except Exception as e:
            if self.debug:
                print(f"Request error for product {product_id}: {e}")
        return None

    def close(self):
        """Close the browser if open."""
        if self.driver:
            self.driver.quit()
            self.driver = None

    def _parse_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract product title from page."""
        # Try various selectors for product name
        title_selectors = [
            ("h1", {}),
            ("div", {"class": re.compile(r"ProductName", re.I)}),
            ("span", {"class": re.compile(r"ProductName", re.I)}),
            ("h1", {"class": re.compile(r"name", re.I)}),
        ]

        for tag, attrs in title_selectors:
            elem = soup.find(tag, attrs)
            if elem:
                text = elem.get_text(strip=True)
                if text and len(text) > 3:
                    return text

        # Try meta tag
        meta_title = soup.find("meta", {"property": "og:title"})
        if meta_title and meta_title.get("content"):
            return meta_title["content"]

        return None

    def _parse_price(self, soup: BeautifulSoup) -> tuple[Optional[str], Optional[float]]:
        """
        Extract selling price from the product page.

        Returns:
            Tuple of (price_string, price_float)
        """
        # Method 1: Look for price in specific containers
        price_selectors = [
            ("div", {"class": re.compile(r"Price__PriceContainer", re.I)}),
            ("div", {"class": re.compile(r"ProductPrice", re.I)}),
            ("span", {"class": re.compile(r"Price", re.I)}),
            ("div", {"class": re.compile(r"selling-price", re.I)}),
        ]

        for tag, attrs in price_selectors:
            containers = soup.find_all(tag, attrs)
            for container in containers:
                price_text = container.get_text(strip=True)
                if "₹" in price_text:
                    # Extract first price (usually selling price)
                    price_match = re.search(r'₹\s*([\d,]+(?:\.\d{2})?)', price_text)
                    if price_match:
                        price_str = f"₹{price_match.group(1)}"
                        price_value = self._extract_price_value(price_str)
                        if price_value and price_value > 0:
                            return price_str, price_value

        # Method 2: Search in raw HTML for price patterns
        html_str = str(soup)
        price_patterns = [
            r'"sellingPrice"\s*:\s*"?(\d+(?:\.\d{2})?)"?',
            r'"price"\s*:\s*"?(\d+(?:\.\d{2})?)"?',
            r'₹\s*([\d,]+(?:\.\d{2})?)',
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

    def _parse_mrp(self, soup: BeautifulSoup) -> tuple[Optional[str], Optional[float]]:
        """
        Extract MRP (Maximum Retail Price) from the product page.

        Returns:
            Tuple of (mrp_string, mrp_float)
        """
        # Look for MRP/strikethrough price
        mrp_selectors = [
            ("div", {"class": re.compile(r"MRP|mrp|OriginalPrice", re.I)}),
            ("span", {"class": re.compile(r"MRP|mrp|OriginalPrice", re.I)}),
            ("del", {}),
            ("s", {}),
        ]

        for tag, attrs in mrp_selectors:
            elements = soup.find_all(tag, attrs)
            for elem in elements:
                mrp_text = elem.get_text(strip=True)
                if "₹" in mrp_text or mrp_text.replace(",", "").replace(".", "").isdigit():
                    mrp_match = re.search(r'₹?\s*([\d,]+(?:\.\d{2})?)', mrp_text)
                    if mrp_match:
                        mrp_str = f"₹{mrp_match.group(1)}"
                        mrp_value = self._extract_price_value(mrp_str)
                        if mrp_value and mrp_value > 0:
                            return mrp_str, mrp_value

        # Search in raw HTML
        html_str = str(soup)
        mrp_patterns = [
            r'"mrp"\s*:\s*"?(\d+(?:\.\d{2})?)"?',
            r'"originalPrice"\s*:\s*"?(\d+(?:\.\d{2})?)"?',
        ]

        for pattern in mrp_patterns:
            match = re.search(pattern, html_str)
            if match:
                mrp_num = match.group(1).replace(",", "")
                try:
                    mrp_value = float(mrp_num)
                    if mrp_value > 0:
                        return f"₹{match.group(1)}", mrp_value
                except ValueError:
                    continue

        return None, None

    def _parse_quantity(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract product quantity/weight from page."""
        qty_selectors = [
            ("div", {"class": re.compile(r"quantity|weight|size|variant", re.I)}),
            ("span", {"class": re.compile(r"quantity|weight|size|variant", re.I)}),
        ]

        for tag, attrs in qty_selectors:
            elem = soup.find(tag, attrs)
            if elem:
                text = elem.get_text(strip=True)
                # Look for common quantity patterns
                qty_match = re.search(r'(\d+(?:\.\d+)?\s*(?:g|kg|ml|l|pc|pcs|piece|pieces|pack))', text, re.I)
                if qty_match:
                    return qty_match.group(1)

        return None

    def _extract_price_value(self, price_text: str) -> Optional[float]:
        """Extract numeric value from price string."""
        # Remove currency symbols and whitespace
        cleaned = re.sub(r'[^\d.,]', '', price_text)
        # Remove commas
        cleaned = cleaned.replace(",", "")
        # Extract the number
        match = re.search(r'[\d]+\.?\d*', cleaned)
        if match:
            try:
                return float(match.group())
            except ValueError:
                pass
        return None

    def _check_stock(self, soup: BeautifulSoup) -> bool:
        """Check if product is in stock."""
        html_str = str(soup).lower()
        out_of_stock_indicators = [
            "out of stock",
            "currently unavailable",
            "not available",
            "notify me",
            "sold out"
        ]
        for indicator in out_of_stock_indicators:
            if indicator in html_str:
                return False
        return True

    def _parse_next_data(self, soup: BeautifulSoup, product_id: str) -> Optional[BlinkitProductData]:
        """Parse product data from __NEXT_DATA__ script tag (Next.js apps)."""
        import json

        script = soup.find("script", {"id": "__NEXT_DATA__"})
        if not script:
            return None

        try:
            data = json.loads(script.string)

            # Navigate to product data - structure may vary
            props = data.get("props", {})
            page_props = props.get("pageProps", {})

            # Try different paths to find product data
            product = None
            for key in ["product", "productData", "data", "initialData"]:
                if key in page_props:
                    product = page_props[key]
                    if isinstance(product, dict) and ("name" in product or "product_name" in product):
                        break
                    if isinstance(product, dict) and "product" in product:
                        product = product["product"]
                        break

            if not product:
                # Try to find product in nested structures
                def find_product(obj, depth=0):
                    if depth > 5:
                        return None
                    if isinstance(obj, dict):
                        if "name" in obj and ("price" in obj or "mrp" in obj or "selling_price" in obj):
                            return obj
                        for v in obj.values():
                            result = find_product(v, depth + 1)
                            if result:
                                return result
                    elif isinstance(obj, list):
                        for item in obj[:5]:  # Limit search
                            result = find_product(item, depth + 1)
                            if result:
                                return result
                    return None

                product = find_product(page_props)

            if not product:
                return None

            url = self.BASE_URL.format(product_id=product_id)
            result = BlinkitProductData(product_id=product_id, url=url)

            # Extract fields
            result.title = product.get("name") or product.get("product_name") or product.get("title")

            # Price
            price = product.get("price") or product.get("selling_price") or product.get("offer_price")
            if price:
                result.price_value = float(price)
                result.price = f"₹{price}"

            # MRP
            mrp = product.get("mrp") or product.get("max_price") or product.get("original_price")
            if mrp:
                result.mrp_value = float(mrp)
                result.mrp = f"₹{mrp}"

            # Other fields
            result.quantity = product.get("unit") or product.get("quantity") or product.get("variant")
            result.brand = product.get("brand") or product.get("brand_name")
            result.category = product.get("category") or product.get("category_name")
            result.in_stock = product.get("in_stock", True)
            if "inventory" in product:
                result.in_stock = product.get("inventory", 0) > 0

            # Calculate discount
            if result.price_value and result.mrp_value and result.mrp_value > result.price_value:
                discount_pct = round((1 - result.price_value / result.mrp_value) * 100)
                result.discount = f"{discount_pct}%"

            return result

        except Exception as e:
            if self.debug:
                print(f"Error parsing __NEXT_DATA__: {e}")
            return None

    def _parse_api_response(self, data: dict, product_id: str) -> BlinkitProductData:
        """Parse product data from API response."""
        url = self.BASE_URL.format(product_id=product_id)
        result = BlinkitProductData(product_id=product_id, url=url)

        try:
            # Handle different API response structures
            product = data.get("product", data)
            if "products" in data:
                products = data.get("products", [])
                product = products[0] if products else data

            # Extract fields
            result.title = product.get("name") or product.get("product_name")

            # Price extraction
            price = product.get("price") or product.get("selling_price") or product.get("offer_price")
            if price:
                result.price_value = float(price)
                result.price = f"₹{price}"

            # MRP extraction
            mrp = product.get("mrp") or product.get("max_price") or product.get("original_price")
            if mrp:
                result.mrp_value = float(mrp)
                result.mrp = f"₹{mrp}"

            # Other fields
            result.quantity = product.get("unit") or product.get("quantity") or product.get("variant")
            result.brand = product.get("brand") or product.get("brand_name")
            result.category = product.get("category") or product.get("category_name")
            result.in_stock = product.get("in_stock", True) or product.get("inventory", 0) > 0

            # Calculate discount
            if result.price_value and result.mrp_value and result.mrp_value > result.price_value:
                discount_pct = round((1 - result.price_value / result.mrp_value) * 100)
                result.discount = f"{discount_pct}%"

        except Exception as e:
            if self.debug:
                print(f"Error parsing API response: {e}")

        return result

    def scrape(self, url_or_id: str) -> BlinkitProductData:
        """
        Scrape price and details for a given product ID or URL.

        Args:
            url_or_id: Blinkit product ID (prid) or full product URL

        Returns:
            BlinkitProductData object with scraped information
        """
        # Extract product ID from URL if needed
        product_id = self.extract_product_id(url_or_id)
        # Keep original URL if provided, otherwise construct it
        original_url = url_or_id.strip() if url_or_id.startswith("http") else None
        url = original_url or self.BASE_URL.format(product_id=product_id)
        result = BlinkitProductData(product_id=product_id, url=url)

        # Try API first (faster and more reliable)
        api_data = self._fetch_api(product_id)
        if api_data:
            if self.debug:
                import json
                with open(f"debug_blinkit_{product_id}.json", "w", encoding="utf-8") as f:
                    json.dump(api_data, f, indent=2)
            api_result = self._parse_api_response(api_data, product_id)
            api_result.url = url
            return api_result

        # Fall back to HTML scraping
        if self.use_browser:
            html = self._fetch_page_browser(product_id, url=original_url)
        else:
            html = self._fetch_page_requests(product_id)

        if not html:
            result.error = "Failed to fetch page (API and HTML both failed)"
            return result

        # Save HTML for debugging
        if self.debug:
            with open(f"debug_blinkit_{product_id}.html", "w", encoding="utf-8") as f:
                f.write(html)

        soup = BeautifulSoup(html, "lxml")

        # Check for errors
        if "page not found" in html.lower():
            result.error = "Product not found"
            return result

        # Try parsing from __NEXT_DATA__ first (most reliable for Next.js sites)
        next_data_result = self._parse_next_data(soup, product_id)
        if next_data_result and next_data_result.title:
            return next_data_result

        # Fall back to HTML element parsing
        result.title = self._parse_title(soup)
        result.price, result.price_value = self._parse_price(soup)
        result.mrp, result.mrp_value = self._parse_mrp(soup)
        result.quantity = self._parse_quantity(soup)
        result.in_stock = self._check_stock(soup)

        # Calculate discount
        if result.price_value and result.mrp_value and result.mrp_value > result.price_value:
            discount_pct = round((1 - result.price_value / result.mrp_value) * 100)
            result.discount = f"{discount_pct}%"

        return result

    def scrape_multiple(self, product_ids: list[str], delay: float = 2.0) -> list[BlinkitProductData]:
        """
        Scrape multiple product IDs with delay between requests.

        Args:
            product_ids: List of product IDs to scrape
            delay: Delay between requests in seconds

        Returns:
            List of BlinkitProductData objects
        """
        results = []
        for i, product_id in enumerate(product_ids):
            result = self.scrape(product_id)
            results.append(result)

            # Add delay between requests (with some randomization)
            if i < len(product_ids) - 1:
                time.sleep(delay + random.uniform(0, 1))

        return results


def scrape_blinkit_product(product_id: str, pincode: str = "110001", use_browser: bool = False) -> BlinkitProductData:
    """
    Convenience function to scrape a single Blinkit product.

    Args:
        product_id: Blinkit product ID
        pincode: Delivery pincode
        use_browser: If True, use Selenium browser

    Returns:
        BlinkitProductData object with scraped information
    """
    scraper = BlinkitScraper(pincode=pincode, use_browser=use_browser)
    try:
        return scraper.scrape(product_id)
    finally:
        scraper.close()
