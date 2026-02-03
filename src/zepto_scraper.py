"""
Zepto Product Scraper

Scrapes product data from Zepto product pages.
Supports two modes:
  - Browser mode (Selenium): Renders the full SPA, most reliable
  - Requests mode: Direct HTTP + BeautifulSoup, faster but may get less data
"""

import re
import json
import time
from typing import Optional
from dataclasses import dataclass, field

import requests as http_requests
from bs4 import BeautifulSoup

# Selenium imports (optional)
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
class ZeptoProductData:
    """Data class for Zepto product information."""
    url: str
    product_id: Optional[str] = None
    name: Optional[str] = None
    brand: Optional[str] = None
    price: Optional[str] = None
    price_value: Optional[float] = None
    mrp: Optional[str] = None
    mrp_value: Optional[float] = None
    discount: Optional[str] = None
    quantity: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    image_url: Optional[str] = None
    availability: Optional[str] = None
    rating: Optional[str] = None
    rating_count: Optional[str] = None
    highlights: list[str] = field(default_factory=list)
    error: Optional[str] = None


class ZeptoScraper:
    """Scraper for Zepto product pages. Supports Selenium (browser) and requests modes."""

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }

    def __init__(self, headless: bool = True, debug: bool = False, use_browser: bool = True,
                 pincode: Optional[str] = None):
        """
        Initialize the Zepto scraper.

        Args:
            headless: Run Chrome in headless mode (default True)
            debug: Save page source to file for inspection
            use_browser: Use Selenium browser (default True). Falls back to requests if False
                         or if Selenium/Chrome is not available.
            pincode: Delivery pincode to set location (e.g. '400093')
        """
        self.headless = headless
        self.debug = debug
        self.use_browser = use_browser
        self.pincode = pincode
        self.driver = None
        self.session = http_requests.Session()
        self._location_set = False

        if use_browser:
            if not SELENIUM_AVAILABLE:
                print("Warning: Selenium not available, falling back to requests mode.")
                print("  Install with: pip install selenium webdriver-manager")
                self.use_browser = False
            else:
                try:
                    self._init_browser()
                except Exception as e:
                    print(f"Warning: Could not start browser ({e}), falling back to requests mode.")
                    self.use_browser = False

    def _init_browser(self):
        """Initialize Chrome browser with anti-detection options."""
        options = Options()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

    def _set_pincode_browser(self):
        """Set delivery pincode on Zepto via browser interaction."""
        if not self.pincode or self._location_set:
            return

        print(f"  Setting delivery pincode to {self.pincode}...")
        try:
            # Go to Zepto homepage first to trigger location modal
            self.driver.get("https://www.zepto.com")
            time.sleep(3)

            # Strategy 1: Look for location/pincode input in modal
            input_selectors = [
                "input[placeholder*='pincode' i]",
                "input[placeholder*='area' i]",
                "input[placeholder*='location' i]",
                "input[placeholder*='delivery' i]",
                "input[placeholder*='search' i]",
                "input[data-testid*='location' i]",
                "input[data-testid*='pincode' i]",
                "input[data-testid*='address' i]",
                "input[type='text']",
                "input[type='search']",
            ]

            input_elem = None
            for selector in input_selectors:
                try:
                    elems = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for elem in elems:
                        if elem.is_displayed():
                            input_elem = elem
                            break
                    if input_elem:
                        break
                except Exception:
                    continue

            # Strategy 2: Click a location button first to open modal
            if not input_elem:
                location_btn_selectors = [
                    "[data-testid*='location' i]",
                    "[data-testid*='address' i]",
                    "button[aria-label*='location' i]",
                    "button[aria-label*='address' i]",
                    ".location-button",
                    ".address-button",
                ]
                for selector in location_btn_selectors:
                    try:
                        btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                        if btn.is_displayed():
                            btn.click()
                            time.sleep(2)
                            # Now look for input again
                            for inp_sel in input_selectors:
                                try:
                                    elems = self.driver.find_elements(By.CSS_SELECTOR, inp_sel)
                                    for elem in elems:
                                        if elem.is_displayed():
                                            input_elem = elem
                                            break
                                    if input_elem:
                                        break
                                except Exception:
                                    continue
                            break
                    except Exception:
                        continue

            if input_elem:
                input_elem.clear()
                input_elem.send_keys(self.pincode)
                time.sleep(2)

                # Try to click the first suggestion/result
                suggestion_selectors = [
                    "[data-testid*='suggestion']",
                    "[data-testid*='result']",
                    ".pac-item",                     # Google Places autocomplete
                    "[role='option']",
                    "[role='listbox'] > *",
                    ".suggestion",
                    ".search-result",
                    "ul[role='listbox'] li",
                    "li[data-testid]",
                ]
                clicked = False
                for selector in suggestion_selectors:
                    try:
                        suggestions = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        for sug in suggestions:
                            if sug.is_displayed() and sug.text.strip():
                                sug.click()
                                clicked = True
                                break
                        if clicked:
                            break
                    except Exception:
                        continue

                if clicked:
                    time.sleep(2)
                    # Look for confirm/continue button
                    confirm_selectors = [
                        "button[data-testid*='confirm' i]",
                        "button[data-testid*='continue' i]",
                        "button[data-testid*='save' i]",
                        "button[data-testid*='deliver' i]",
                        "button:not([disabled])",
                    ]
                    for selector in confirm_selectors:
                        try:
                            btns = self.driver.find_elements(By.CSS_SELECTOR, selector)
                            for btn in btns:
                                text = btn.text.strip().lower()
                                if btn.is_displayed() and text and any(
                                    kw in text for kw in
                                    ["confirm", "continue", "save", "deliver here", "yes", "done"]
                                ):
                                    btn.click()
                                    time.sleep(2)
                                    break
                        except Exception:
                            continue

                self._location_set = True
                print(f"  Pincode {self.pincode} set successfully")
            else:
                # Fallback: set pincode via localStorage/cookie
                self.driver.execute_script(f"""
                    try {{
                        localStorage.setItem('pincode', '{self.pincode}');
                        localStorage.setItem('userPincode', '{self.pincode}');
                        localStorage.setItem('deliveryPincode', '{self.pincode}');
                    }} catch(e) {{}}
                """)
                self._location_set = True
                print(f"  Pincode {self.pincode} set via localStorage (modal not found)")

        except Exception as e:
            print(f"  Warning: Could not set pincode ({e}), continuing without it")

    def _extract_product_id(self, url: str) -> Optional[str]:
        """Extract product variant ID from URL."""
        match = re.search(r'/pvid/([a-f0-9-]+)', url)
        return match.group(1) if match else None

    def _try_next_data(self) -> Optional[dict]:
        """Try to extract product data from __NEXT_DATA__ script tag."""
        try:
            script = self.driver.find_element(By.ID, "__NEXT_DATA__")
            if script:
                data = json.loads(script.get_attribute("innerHTML"))
                return data
        except Exception:
            pass
        return None

    def _try_json_ld(self) -> Optional[dict]:
        """Try to extract structured data from JSON-LD script tags."""
        try:
            scripts = self.driver.find_elements(
                By.CSS_SELECTOR, 'script[type="application/ld+json"]'
            )
            for script in scripts:
                try:
                    data = json.loads(script.get_attribute("innerHTML"))
                    if isinstance(data, dict) and data.get("@type") == "Product":
                        return data
                    if isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and item.get("@type") == "Product":
                                return item
                except (json.JSONDecodeError, Exception):
                    continue
        except Exception:
            pass
        return None

    def _extract_from_json_ld(self, ld_data: dict, result: ZeptoProductData) -> None:
        """Populate result from JSON-LD structured data."""
        result.name = ld_data.get("name")
        result.description = ld_data.get("description")
        result.brand = ld_data.get("brand", {}).get("name") if isinstance(
            ld_data.get("brand"), dict
        ) else ld_data.get("brand")
        result.image_url = ld_data.get("image")
        if isinstance(result.image_url, list) and result.image_url:
            result.image_url = result.image_url[0]

        # Price from offers
        offers = ld_data.get("offers")
        if isinstance(offers, dict):
            price = offers.get("price")
            if price:
                result.price_value = float(price)
                currency = offers.get("priceCurrency", "INR")
                symbol = "₹" if currency == "INR" else currency
                result.price = f"{symbol}{result.price_value:,.2f}"
            availability = offers.get("availability", "")
            if "InStock" in availability:
                result.availability = "In Stock"
            elif "OutOfStock" in availability:
                result.availability = "Out of Stock"
        elif isinstance(offers, list) and offers:
            offer = offers[0]
            price = offer.get("price")
            if price:
                result.price_value = float(price)
                currency = offer.get("priceCurrency", "INR")
                symbol = "₹" if currency == "INR" else currency
                result.price = f"{symbol}{result.price_value:,.2f}"

        # Rating
        rating_data = ld_data.get("aggregateRating")
        if rating_data:
            result.rating = str(rating_data.get("ratingValue", ""))
            result.rating_count = str(rating_data.get("ratingCount", ""))

    def _extract_from_next_data(self, next_data: dict, result: ZeptoProductData) -> bool:
        """Try to extract product info from __NEXT_DATA__. Returns True if data found."""
        try:
            props = next_data.get("props", {}).get("pageProps", {})
            product = props.get("product") or props.get("productData") or props.get("data")
            if not product:
                # Search deeper
                for key, val in props.items():
                    if isinstance(val, dict) and ("name" in val or "productName" in val):
                        product = val
                        break

            if not product:
                return False

            result.name = product.get("name") or product.get("productName")
            result.brand = product.get("brand") or product.get("brandName")
            result.description = product.get("description")
            result.category = product.get("category") or product.get("categoryName")
            result.quantity = product.get("quantity") or product.get("packSize")

            # Price
            price = product.get("sellingPrice") or product.get("price") or product.get("salePrice")
            if price:
                result.price_value = float(price)
                result.price = f"₹{result.price_value:,.2f}"

            mrp = product.get("mrp") or product.get("maxRetailPrice") or product.get("originalPrice")
            if mrp:
                result.mrp_value = float(mrp)
                result.mrp = f"₹{result.mrp_value:,.2f}"

            # Discount
            discount = product.get("discount") or product.get("discountPercent")
            if discount:
                result.discount = f"{discount}%"
            elif result.price_value and result.mrp_value and result.mrp_value > result.price_value:
                pct = ((result.mrp_value - result.price_value) / result.mrp_value) * 100
                result.discount = f"{pct:.0f}%"

            # Image
            images = product.get("images") or product.get("imageUrls")
            if images and isinstance(images, list) and images:
                result.image_url = images[0] if isinstance(images[0], str) else images[0].get("url")
            elif product.get("image") or product.get("imageUrl"):
                result.image_url = product.get("image") or product.get("imageUrl")

            return True
        except Exception:
            return False

    def _extract_from_dom(self, result: ZeptoProductData) -> None:
        """Extract product data by parsing the rendered DOM."""
        # Product name - try multiple selectors
        name_selectors = [
            "h1",
            "[data-testid='product-title']",
            "[data-testid='pdp-product-name']",
            ".product-title",
            ".product-name",
        ]
        for selector in name_selectors:
            try:
                elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                text = elem.text.strip()
                if text and len(text) > 3:
                    result.name = text
                    break
            except Exception:
                continue

        # Price - try multiple selectors
        price_selectors = [
            "[data-testid='product-price']",
            "[data-testid='selling-price']",
            "[data-testid='pdp-product-price']",
            ".selling-price",
            ".product-price",
        ]
        for selector in price_selectors:
            try:
                elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                text = elem.text.strip()
                if text and "₹" in text:
                    result.price = text
                    result.price_value = self._parse_price_value(text)
                    break
            except Exception:
                continue

        # If price not found, search for ₹ patterns in the page
        if not result.price:
            try:
                page_text = self.driver.find_element(By.TAG_NAME, "body").text
                # Find price patterns like ₹4,599 or ₹ 4,599
                prices = re.findall(r'₹\s?([\d,]+(?:\.\d{1,2})?)', page_text)
                if prices:
                    # First price is usually selling price
                    result.price = f"₹{prices[0]}"
                    result.price_value = self._parse_price_value(result.price)
                    if len(prices) > 1:
                        # Second distinct price is usually MRP
                        mrp_val = self._parse_price_value(f"₹{prices[1]}")
                        if mrp_val and result.price_value and mrp_val > result.price_value:
                            result.mrp = f"₹{prices[1]}"
                            result.mrp_value = mrp_val
            except Exception:
                pass

        # MRP
        if not result.mrp:
            mrp_selectors = [
                "[data-testid='product-mrp']",
                "[data-testid='mrp']",
                ".mrp",
                ".original-price",
                "del",  # strikethrough price
            ]
            for selector in mrp_selectors:
                try:
                    elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    text = elem.text.strip()
                    if text and "₹" in text:
                        result.mrp = text
                        result.mrp_value = self._parse_price_value(text)
                        break
                except Exception:
                    continue

        # Discount
        if not result.discount:
            discount_selectors = [
                "[data-testid='discount']",
                "[data-testid='discount-percentage']",
                ".discount",
                ".discount-tag",
            ]
            for selector in discount_selectors:
                try:
                    elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    text = elem.text.strip()
                    if text and "%" in text:
                        result.discount = text
                        break
                except Exception:
                    continue

        # Calculate discount if we have both prices but no discount
        if not result.discount and result.price_value and result.mrp_value:
            if result.mrp_value > result.price_value:
                pct = ((result.mrp_value - result.price_value) / result.mrp_value) * 100
                result.discount = f"{pct:.0f}% off"

        # Brand
        if not result.brand:
            brand_selectors = [
                "[data-testid='product-brand']",
                "[data-testid='brand-name']",
                ".brand-name",
                ".brand",
            ]
            for selector in brand_selectors:
                try:
                    elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    text = elem.text.strip()
                    if text:
                        result.brand = text
                        break
                except Exception:
                    continue

        # Quantity / Pack size
        if not result.quantity:
            qty_selectors = [
                "[data-testid='product-quantity']",
                "[data-testid='pack-size']",
                ".pack-size",
                ".quantity",
            ]
            for selector in qty_selectors:
                try:
                    elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    text = elem.text.strip()
                    if text:
                        result.quantity = text
                        break
                except Exception:
                    continue

        # Description
        if not result.description:
            desc_selectors = [
                "[data-testid='product-description']",
                "[data-testid='pdp-description']",
                ".product-description",
                ".description",
            ]
            for selector in desc_selectors:
                try:
                    elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    text = elem.text.strip()
                    if text and len(text) > 10:
                        result.description = text
                        break
                except Exception:
                    continue

        # Highlights / Key features
        if not result.highlights:
            highlight_selectors = [
                "[data-testid='product-highlights'] li",
                "[data-testid='key-features'] li",
                ".highlights li",
                ".key-features li",
            ]
            for selector in highlight_selectors:
                try:
                    elems = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for elem in elems:
                        text = elem.text.strip()
                        if text:
                            result.highlights.append(text)
                    if result.highlights:
                        break
                except Exception:
                    continue

        # Image
        if not result.image_url:
            img_selectors = [
                "[data-testid='product-image'] img",
                "[data-testid='pdp-image'] img",
                ".product-image img",
                "img[alt*='product']",
                "picture img",
            ]
            for selector in img_selectors:
                try:
                    elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    src = elem.get_attribute("src")
                    if src and not src.startswith("data:"):
                        result.image_url = src
                        break
                except Exception:
                    continue

    def _parse_price_value(self, text: str) -> Optional[float]:
        """Extract numeric value from price string like ₹4,599."""
        cleaned = re.sub(r'[^\d.,]', '', text)
        cleaned = cleaned.replace(",", "")
        match = re.search(r'[\d]+\.?\d*', cleaned)
        if match:
            try:
                return float(match.group())
            except ValueError:
                pass
        return None

    def _fetch_page_requests(self, url: str) -> Optional[str]:
        """Fetch page HTML using requests library."""
        try:
            response = self.session.get(url, headers=self.HEADERS, timeout=15)
            response.raise_for_status()
            return response.text
        except http_requests.RequestException as e:
            print(f"  Request error: {e}")
            return None

    def _extract_from_soup(self, soup: BeautifulSoup, result: ZeptoProductData) -> None:
        """Extract product data from BeautifulSoup parsed HTML (requests mode)."""
        # Try JSON-LD
        for script in soup.find_all("script", {"type": "application/ld+json"}):
            try:
                data = json.loads(script.string or "")
                if isinstance(data, dict) and data.get("@type") == "Product":
                    self._extract_from_json_ld(data, result)
                    if result.name:
                        print("  [Source: JSON-LD]")
                        return
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get("@type") == "Product":
                            self._extract_from_json_ld(item, result)
                            if result.name:
                                print("  [Source: JSON-LD]")
                                return
            except (json.JSONDecodeError, Exception):
                continue

        # Try __NEXT_DATA__
        next_script = soup.find("script", {"id": "__NEXT_DATA__"})
        if next_script and next_script.string:
            try:
                next_data = json.loads(next_script.string)
                if self._extract_from_next_data(next_data, result) and result.name:
                    print("  [Source: __NEXT_DATA__]")
                    return
            except (json.JSONDecodeError, Exception):
                pass

        # Fallback: parse HTML elements
        # Title from h1
        h1 = soup.find("h1")
        if h1:
            text = h1.get_text(strip=True)
            if text and len(text) > 3:
                result.name = text

        # Title from meta
        if not result.name:
            meta_title = soup.find("meta", {"property": "og:title"})
            if meta_title and meta_title.get("content"):
                result.name = meta_title["content"]

        # Description from meta
        if not result.description:
            meta_desc = soup.find("meta", {"property": "og:description"})
            if meta_desc and meta_desc.get("content"):
                result.description = meta_desc["content"]

        # Image from meta
        if not result.image_url:
            meta_img = soup.find("meta", {"property": "og:image"})
            if meta_img and meta_img.get("content"):
                result.image_url = meta_img["content"]

        # Price from page text
        if not result.price:
            page_text = soup.get_text()
            prices = re.findall(r'₹\s?([\d,]+(?:\.\d{1,2})?)', page_text)
            if prices:
                result.price = f"₹{prices[0]}"
                result.price_value = self._parse_price_value(result.price)
                if len(prices) > 1:
                    mrp_val = self._parse_price_value(f"₹{prices[1]}")
                    if mrp_val and result.price_value and mrp_val > result.price_value:
                        result.mrp = f"₹{prices[1]}"
                        result.mrp_value = mrp_val

        if result.name:
            print("  [Source: HTML]")

    def _scrape_requests(self, url: str, result: ZeptoProductData) -> None:
        """Scrape using requests + BeautifulSoup."""
        html = self._fetch_page_requests(url)
        if not html:
            result.error = "Failed to fetch page (HTTP request failed)"
            return

        if self.debug:
            debug_file = f"debug_zepto_{result.product_id or 'page'}.html"
            with open(debug_file, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"  Debug HTML saved to: {debug_file}")

        soup = BeautifulSoup(html, "lxml")
        self._extract_from_soup(soup, result)

        if not result.name:
            result.error = "Could not extract product data - page may require browser mode"

    def _scrape_browser(self, url: str, result: ZeptoProductData) -> None:
        """Scrape using Selenium browser."""
        try:
            # Set pincode/location before first scrape
            if self.pincode and not self._location_set:
                self._set_pincode_browser()

            self.driver.get(url)
            time.sleep(3)
            self.driver.execute_script("window.scrollTo(0, 300);")
            time.sleep(1)

            if self.debug:
                page_source = self.driver.page_source
                debug_file = f"debug_zepto_{result.product_id or 'page'}.html"
                with open(debug_file, "w", encoding="utf-8") as f:
                    f.write(page_source)
                print(f"  Debug HTML saved to: {debug_file}")

            # Strategy 1: JSON-LD
            ld_data = self._try_json_ld()
            if ld_data:
                self._extract_from_json_ld(ld_data, result)
                if result.name:
                    print("  [Source: JSON-LD]")

            # Strategy 2: __NEXT_DATA__
            if not result.name:
                next_data = self._try_next_data()
                if next_data:
                    if self._extract_from_next_data(next_data, result) and result.name:
                        print("  [Source: __NEXT_DATA__]")

            # Strategy 3: DOM
            if not result.name:
                self._extract_from_dom(result)
                if result.name:
                    print("  [Source: DOM]")

            # Supplement missing price from DOM
            if result.name and not result.price:
                self._extract_from_dom(result)

            if not result.name:
                result.error = "Could not extract product data - page may not have loaded"

        except Exception as e:
            result.error = f"Browser scraping failed: {str(e)}"

    def scrape(self, url: str) -> ZeptoProductData:
        """
        Scrape a Zepto product page.

        Args:
            url: Full Zepto product URL

        Returns:
            ZeptoProductData with scraped information
        """
        result = ZeptoProductData(url=url)
        result.product_id = self._extract_product_id(url)

        if self.use_browser:
            self._scrape_browser(url, result)
        else:
            self._scrape_requests(url, result)

        return result

    def scrape_multiple(self, urls: list[str], delay: float = 3.0) -> list[ZeptoProductData]:
        """
        Scrape multiple Zepto product URLs.

        Args:
            urls: List of Zepto product URLs
            delay: Delay between requests in seconds

        Returns:
            List of ZeptoProductData objects
        """
        results = []
        for i, url in enumerate(urls, 1):
            print(f"\n[{i}/{len(urls)}] Scraping: {url[:80]}...")
            result = self.scrape(url)
            results.append(result)
            if i < len(urls):
                time.sleep(delay)
        return results

    def close(self):
        """Close the browser."""
        if self.driver:
            self.driver.quit()
            self.driver = None
