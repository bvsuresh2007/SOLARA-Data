"""
Swiggy Instamart Product Scraper

Scrapes product data from individual Swiggy Instamart product pages.
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
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False


# Pincode to lat/lng mapping for common Bangalore pincodes
PINCODE_COORDS = {
    "560103": {"lat": 12.9352, "lng": 77.6245, "area": "Koramangala"},
    "560001": {"lat": 12.9716, "lng": 77.5946, "area": "MG Road"},
    "560034": {"lat": 12.9698, "lng": 77.7500, "area": "Marathahalli"},
    "560037": {"lat": 12.9081, "lng": 77.6476, "area": "BTM Layout"},
    "560102": {"lat": 12.9081, "lng": 77.6476, "area": "Jayanagar"},
    "560095": {"lat": 12.9784, "lng": 77.6408, "area": "Indiranagar"},
    "560066": {"lat": 12.9121, "lng": 77.6446, "area": "Bannerghatta Road"},
    "560068": {"lat": 13.0358, "lng": 77.5970, "area": "Hebbal"},
    "560085": {"lat": 12.9063, "lng": 77.5857, "area": "JP Nagar"},
    "560004": {"lat": 12.9969, "lng": 77.5913, "area": "Sadashivanagar"},
    "560038": {"lat": 12.9698, "lng": 77.6100, "area": "Shivajinagar"},
    "560071": {"lat": 12.9141, "lng": 77.6368, "area": "HSR Layout"},
    "560078": {"lat": 12.9277, "lng": 77.6277, "area": "Ejipura"},
    "560076": {"lat": 12.8880, "lng": 77.6174, "area": "Arekere"},
    "560100": {"lat": 12.9165, "lng": 77.6101, "area": "Banashankari"},
}


@dataclass
class SwiggyProductData:
    """Data class for Swiggy Instamart product information."""
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


class SwiggyInstamartScraper:
    """Scraper for Swiggy Instamart product pages. Supports Selenium (browser) and requests modes."""

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

    def __init__(self, headless: bool = True, debug: bool = False,
                 use_browser: bool = True, pincode: Optional[str] = "560103"):
        """
        Initialize the Swiggy Instamart scraper.

        Args:
            headless: Run Chrome in headless mode (default True)
            debug: Save page source to file for inspection
            use_browser: Use Selenium browser (default True). Falls back to requests if False
                         or if Selenium/Chrome is not available.
            pincode: Delivery pincode to set location (default: 560103)
        """
        self.headless = headless
        self.debug = debug
        self.use_browser = use_browser
        self.pincode = pincode
        self.coords = PINCODE_COORDS.get(pincode or "560103", PINCODE_COORDS["560103"])
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
        """Set delivery pincode on Swiggy Instamart via browser interaction."""
        if not self.pincode or self._location_set:
            return

        area = self.coords.get("area", "Koramangala")
        lat = self.coords["lat"]
        lng = self.coords["lng"]

        print(f"  Setting delivery location to {area}, Bangalore - {self.pincode}...")
        try:
            # Go to Swiggy Instamart homepage to trigger location modal
            self.driver.get("https://www.swiggy.com/instamart")
            time.sleep(3)

            # Set location via cookies first
            for name, value in [("lat", str(lat)), ("lng", str(lng))]:
                try:
                    self.driver.add_cookie({
                        "name": name, "value": value,
                        "domain": ".swiggy.com"
                    })
                except Exception:
                    pass

            try:
                self.driver.add_cookie({
                    "name": "userLocation",
                    "value": json.dumps({
                        "lat": lat, "lng": lng,
                        "address": f"{area}, Bangalore, Karnataka {self.pincode}",
                        "area": area
                    }),
                    "domain": ".swiggy.com"
                })
            except Exception:
                pass

            # Strategy 1: Look for location/pincode input in modal
            input_selectors = [
                "input[placeholder*='area' i]",
                "input[placeholder*='Search for area' i]",
                "input[placeholder*='location' i]",
                "input[placeholder*='search' i]",
                "input[data-testid*='location' i]",
                "input[data-testid='location-search-input']",
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
                    "[data-testid='address-name']",
                    "[data-testid='search-location']",
                    "[data-testid*='location' i]",
                    "[data-testid*='address' i]",
                    "button[aria-label*='location' i]",
                    ".location-text",
                    "._2vML0",
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
                input_elem.send_keys(f"{area}, Bangalore {self.pincode}")
                time.sleep(2)

                # Try to click the first suggestion/result
                suggestion_selectors = [
                    "._11n32:nth-child(1)",
                    "[data-testid='address-suggestion']:first-child",
                    "[data-testid*='suggestion']",
                    "[data-testid*='result']",
                    ".pac-item",
                    "[role='option']",
                    "[role='listbox'] > *",
                    "[class*='suggestion']:first-child",
                    "[class*='LocationSuggestion']:first-child",
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
                        "._2xPHa",
                        "button[class*='confirm' i]",
                        "[data-testid='confirm-location']",
                        "button[data-testid*='confirm' i]",
                        "button[data-testid*='continue' i]",
                        "button[data-testid*='save' i]",
                        "button:not([disabled])",
                    ]
                    for selector in confirm_selectors:
                        try:
                            btns = self.driver.find_elements(By.CSS_SELECTOR, selector)
                            for btn in btns:
                                text = btn.text.strip().lower()
                                if btn.is_displayed() and text and any(
                                    kw in text for kw in
                                    ["confirm", "continue", "save", "deliver", "yes", "done"]
                                ):
                                    btn.click()
                                    time.sleep(2)
                                    break
                        except Exception:
                            continue

                self._location_set = True
                print(f"  Location set: {area}, Bangalore - {self.pincode}")
            else:
                # Fallback: set location via localStorage/cookie
                self.driver.execute_script(f"""
                    try {{
                        localStorage.setItem('userLocation', JSON.stringify({{
                            lat: {lat}, lng: {lng},
                            address: "{area}, Bangalore, Karnataka {self.pincode}",
                            area: "{area}"
                        }}));
                        localStorage.setItem('lat', '{lat}');
                        localStorage.setItem('lng', '{lng}');
                    }} catch(e) {{}}
                """)
                self._location_set = True
                print(f"  Location set via localStorage: {area} - {self.pincode}")

        except Exception as e:
            print(f"  Warning: Could not set pincode ({e}), continuing without it")

    def _extract_product_id(self, url: str) -> Optional[str]:
        """Extract product/item ID from Swiggy Instamart URL."""
        # Swiggy Instamart URLs patterns:
        #   /instamart/item/<slug>/<id>
        #   /instamart/product/<slug>/<id>
        #   /instamart/...?productId=<id>
        for pattern in [
            r'/item/[^/]+/([a-zA-Z0-9_-]+)(?:\?|$)',
            r'/product/[^/]+/([a-zA-Z0-9_-]+)(?:\?|$)',
            r'[?&]productId=([a-zA-Z0-9_-]+)',
            r'/instamart/[^/]+/[^/]+/([a-zA-Z0-9_-]+)(?:\?|$)',
            # Last resort: last path segment
            r'/([a-zA-Z0-9_-]+)(?:\?|$)',
        ]:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def _try_next_data(self) -> Optional[dict]:
        """Try to extract data from __NEXT_DATA__ script tag."""
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

    def _extract_from_json_ld(self, ld_data: dict, result: SwiggyProductData) -> None:
        """Populate result from JSON-LD structured data."""
        result.name = ld_data.get("name")
        result.description = ld_data.get("description")
        result.brand = (
            ld_data.get("brand", {}).get("name")
            if isinstance(ld_data.get("brand"), dict)
            else ld_data.get("brand")
        )
        result.image_url = ld_data.get("image")
        if isinstance(result.image_url, list) and result.image_url:
            result.image_url = result.image_url[0]

        # Category
        if ld_data.get("category"):
            result.category = ld_data["category"]

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

    def _extract_from_next_data(self, next_data: dict, result: SwiggyProductData) -> bool:
        """Try to extract product info from __NEXT_DATA__. Returns True if data found."""
        try:
            props = next_data.get("props", {}).get("pageProps", {})

            # Try various keys where product data might be
            product = None
            product_keys = [
                "product", "productData", "data", "itemData",
                "productInfo", "item", "productDetails",
            ]
            for key in product_keys:
                if props.get(key) and isinstance(props[key], dict):
                    product = props[key]
                    break

            if not product:
                # Search deeper in pageProps
                for key, val in props.items():
                    if isinstance(val, dict) and ("name" in val or "productName" in val):
                        product = val
                        break

            # Also search in nested data structures
            if not product:
                product = self._find_product_in_json(props)

            if not product:
                return False

            result.name = (
                product.get("name") or product.get("productName")
                or product.get("display_name") or product.get("displayName")
            )
            result.brand = (
                product.get("brand") or product.get("brandName")
                or product.get("brand_name")
            )
            result.description = product.get("description")
            result.category = (
                product.get("category") or product.get("categoryName")
                or product.get("category_name")
            )
            result.quantity = (
                product.get("quantity") or product.get("packSize")
                or product.get("pack_size") or product.get("weight")
                or product.get("unit")
            )

            # Price
            price = (
                product.get("offer_price") or product.get("offerPrice")
                or product.get("sellingPrice") or product.get("selling_price")
                or product.get("price") or product.get("salePrice")
                or product.get("finalPrice")
            )
            if price:
                result.price_value = float(price)
                result.price = f"₹{result.price_value:,.2f}"

            mrp = (
                product.get("mrp") or product.get("maxRetailPrice")
                or product.get("marked_price") or product.get("markedPrice")
                or product.get("originalPrice")
            )
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

            # Availability — only mark out-of-stock if explicitly false
            avail = product.get("available", product.get("in_stock", product.get("inStock")))
            if avail is False:
                result.availability = "Out of Stock"
            elif result.price_value:
                # If we have a price, assume in stock (location-dependent stock
                # data in JSON may not reflect the user's actual pincode)
                result.availability = "In Stock"

            # Image
            images = product.get("images") or product.get("imageUrls")
            if images and isinstance(images, list) and images:
                result.image_url = images[0] if isinstance(images[0], str) else images[0].get("url")
            elif product.get("image") or product.get("imageUrl") or product.get("image_url"):
                result.image_url = (
                    product.get("image") or product.get("imageUrl")
                    or product.get("image_url")
                )

            return True
        except Exception:
            return False

    def _find_product_in_json(self, data, depth: int = 0) -> Optional[dict]:
        """Recursively find a product-like dict in nested JSON."""
        if depth > 8:
            return None

        if isinstance(data, dict):
            # Check if this dict looks like a product
            name_keys = ["name", "display_name", "displayName", "productName"]
            price_keys = ["price", "offer_price", "offerPrice", "selling_price",
                          "sellingPrice", "finalPrice", "mrp"]
            has_name = any(k in data and data[k] for k in name_keys)
            has_price = any(k in data and data[k] for k in price_keys)
            if has_name and has_price:
                return data

            for value in data.values():
                if isinstance(value, (dict, list)):
                    result = self._find_product_in_json(value, depth + 1)
                    if result:
                        return result

        elif isinstance(data, list):
            for item in data:
                if isinstance(item, (dict, list)):
                    result = self._find_product_in_json(item, depth + 1)
                    if result:
                        return result

        return None

    def _get_product_container(self):
        """Find the main product detail container on the page.

        Walks up from the h1 (product name) to find the enclosing section
        so that price/MRP extraction is scoped to the product — not the
        whole page (which may contain delivery fees, related products, etc.).
        """
        # Try to find the product name element first
        name_elem = None
        for sel in ["h1", "[data-testid='product-title']",
                     "[data-testid='pdp-product-name']",
                     "[data-testid='item-name']"]:
            try:
                elem = self.driver.find_element(By.CSS_SELECTOR, sel)
                if elem.is_displayed() and elem.text.strip():
                    name_elem = elem
                    break
            except Exception:
                continue

        if not name_elem:
            return None

        # Walk up the DOM to find a container that also has price info
        container = name_elem
        for _ in range(6):
            try:
                container = container.find_element(By.XPATH, "..")
                text = container.text or ""
                # A good container has both the product name AND a ₹ price
                if "₹" in text and len(text) > 50:
                    return container
            except Exception:
                break

        return None

    def _extract_prices_from_container(self, container, result: SwiggyProductData) -> None:
        """Extract selling price and MRP from the product container text.

        Finds all ₹ amounts in the container, then determines which is
        the selling price and which is the MRP based on:
        - Strikethrough elements (del/s) → MRP
        - Smaller value when two prices exist → selling price
        - Larger value → MRP
        - If only one price + discount %, calculates the other
        """
        if container:
            # Strategy 1: Look for strikethrough (MRP) within the container
            for sel in ["del", "s", "[style*='line-through']"]:
                try:
                    elems = container.find_elements(By.CSS_SELECTOR, sel)
                    for elem in elems:
                        text = elem.text.strip()
                        val = self._parse_price_value(text)
                        if val and val > 0:
                            result.mrp = text if "₹" in text else f"₹{val:,.0f}"
                            result.mrp_value = val
                            break
                    if result.mrp_value:
                        break
                except Exception:
                    continue

            # Strategy 2: Collect ALL visible ₹ amounts from the container text
            try:
                container_text = container.text or ""
                all_prices = re.findall(r'₹\s?([\d,]+(?:\.\d{1,2})?)', container_text)
                # Parse to floats and deduplicate
                price_values = []
                seen = set()
                for p in all_prices:
                    val = self._parse_price_value(f"₹{p}")
                    if val and val > 0 and val not in seen:
                        seen.add(val)
                        price_values.append(val)

                if len(price_values) >= 2:
                    # Two distinct prices: smaller = selling, larger = MRP
                    price_values.sort()
                    selling = price_values[0]
                    mrp = price_values[-1]

                    if not result.price_value:
                        result.price_value = selling
                        result.price = f"₹{selling:,.0f}"
                    if not result.mrp_value:
                        result.mrp_value = mrp
                        result.mrp = f"₹{mrp:,.0f}"

                elif len(price_values) == 1:
                    # Single price — it's the selling price
                    if not result.price_value:
                        result.price_value = price_values[0]
                        result.price = f"₹{price_values[0]:,.0f}"

            except Exception:
                pass

        # Strategy 3: If we have discount % and one price, calculate the other
        # (works even without a container)
        if result.discount and (result.price_value or result.mrp_value):
            pct_match = re.search(r'(\d+)\s*%', result.discount)
            if pct_match:
                pct = float(pct_match.group(1)) / 100.0
                if result.price_value and not result.mrp_value and pct > 0 and pct < 1:
                    mrp = result.price_value / (1 - pct)
                    result.mrp_value = round(mrp, 2)
                    result.mrp = f"₹{result.mrp_value:,.0f}"
                elif result.mrp_value and not result.price_value and pct > 0 and pct < 1:
                    selling = result.mrp_value * (1 - pct)
                    result.price_value = round(selling, 2)
                    result.price = f"₹{result.price_value:,.0f}"

    def _extract_from_dom(self, result: SwiggyProductData) -> None:
        """Extract product data by parsing the rendered DOM.

        Uses a scoped approach: first finds the product container (via h1),
        then extracts prices only from within that container to avoid
        picking up delivery fees, related products, etc.
        """
        # Product name
        name_selectors = [
            "h1",
            "[data-testid='product-title']",
            "[data-testid='pdp-product-name']",
            "[data-testid='item-name']",
            "[class*='ProductName']",
            "[class*='product-name']",
            "[class*='product-title']",
            ".novMV",
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

        # Find the product container to scope price extraction
        product_container = self._get_product_container()

        # Price — try specific selectors first (page-wide is OK for data-testid)
        price_selectors = [
            "[data-testid='product-price']",
            "[data-testid='selling-price']",
            "[data-testid='item-offer-price']",
            "[data-testid='pdp-product-price']",
        ]
        for selector in price_selectors:
            try:
                elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                if elem.is_displayed():
                    text = elem.text.strip()
                    if text and "₹" in text:
                        result.price = text
                        result.price_value = self._parse_price_value(text)
                        break
            except Exception:
                continue

        # MRP — try specific selectors first
        mrp_selectors = [
            "[data-testid='product-mrp']",
            "[data-testid='item-mrp-price']",
            "[data-testid='mrp']",
        ]
        for selector in mrp_selectors:
            try:
                elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                if elem.is_displayed():
                    text = elem.text.strip()
                    if text and "₹" in text:
                        result.mrp = text
                        result.mrp_value = self._parse_price_value(text)
                        break
            except Exception:
                continue

        # Discount — try specific selectors
        discount_selectors = [
            "[data-testid='discount']",
            "[data-testid='discount-percentage']",
            "[data-testid='item-offer-label-discount-text']",
        ]
        for selector in discount_selectors:
            try:
                elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                if elem.is_displayed():
                    text = elem.text.strip()
                    if text and ("%" in text or "OFF" in text.upper()):
                        result.discount = text
                        break
            except Exception:
                continue

        # Fallback: extract prices from the SCOPED product container
        if not result.price_value or not result.mrp_value:
            self._extract_prices_from_container(product_container, result)

        # If still no discount, try broader selectors within container
        if not result.discount:
            search_in = product_container or self.driver
            try:
                container_text = search_in.text or ""
                disc_match = re.search(r'(\d+%\s*OFF)', container_text, re.IGNORECASE)
                if disc_match:
                    result.discount = disc_match.group(1)
            except Exception:
                pass

        # Calculate discount if we have both prices but no discount text
        if not result.discount and result.price_value and result.mrp_value:
            if result.mrp_value > result.price_value:
                pct = ((result.mrp_value - result.price_value) / result.mrp_value) * 100
                result.discount = f"{pct:.0f}% OFF"

        # Brand
        if not result.brand:
            brand_selectors = [
                "[data-testid='product-brand']",
                "[data-testid='brand-name']",
                "[class*='brand-name']",
                "[class*='BrandName']",
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
                "[class*='quantity']",
                "[class*='weight']",
                "[class*='variant']",
                ".pack-size",
                ".quantity",
            ]
            for selector in qty_selectors:
                try:
                    elem = self.driver.find_element(By.CSS_SELECTOR, selector)
                    text = elem.text.strip()
                    if text and len(text) < 30:
                        result.quantity = text
                        break
                except Exception:
                    continue

        # Try extracting quantity from name
        if not result.quantity and result.name:
            qty_match = re.search(
                r'(\d+(?:\.\d+)?\s*(?:g|kg|ml|l|L|pcs?|pack|units?|piece|no|nos))\b',
                result.name, re.IGNORECASE
            )
            if qty_match:
                result.quantity = qty_match.group(1)

        # Description
        if not result.description:
            desc_selectors = [
                "[data-testid='product-description']",
                "[data-testid='pdp-description']",
                "[class*='product-description']",
                "[class*='ProductDescription']",
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
                "[class*='product-image'] img",
                "[class*='ProductImage'] img",
                "picture img",
                "img[alt*='product' i]",
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

        # Availability — check for visible "Add" button first, then sold-out
        if not result.availability:
            add_btn_selectors = [
                "button[data-testid*='add' i]",
                "button[class*='add' i]",
                "button[aria-label*='add' i]",
                "[data-testid*='add-to-cart' i]",
                "[data-testid*='addButton' i]",
            ]
            for selector in add_btn_selectors:
                try:
                    btns = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for btn in btns:
                        if btn.is_displayed():
                            result.availability = "In Stock"
                            break
                    if result.availability:
                        break
                except Exception:
                    continue

            if not result.availability:
                sold_out_selectors = [
                    "[data-testid='sold-out']",
                    "[data-testid='out-of-stock']",
                ]
                for selector in sold_out_selectors:
                    try:
                        elems = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        for elem in elems:
                            if elem.is_displayed():
                                result.availability = "Out of Stock"
                                break
                        if result.availability:
                            break
                    except Exception:
                        continue

            if not result.availability and result.name:
                result.availability = "In Stock"

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

    def _extract_from_soup(self, soup: BeautifulSoup, result: SwiggyProductData) -> None:
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

        # Try embedded JSON in script tags
        for script in soup.find_all("script"):
            if script.string and "window.__" in (script.string or ""):
                json_match = re.search(
                    r'window\.__\w+__\s*=\s*({.+?});?\s*(?:</script>|$)',
                    script.string, re.DOTALL
                )
                if json_match:
                    try:
                        data = json.loads(json_match.group(1))
                        product = self._find_product_in_json(data)
                        if product:
                            dummy = SwiggyProductData(url=result.url)
                            if self._extract_from_next_data(
                                {"props": {"pageProps": product}}, dummy
                            ):
                                # Copy fields over
                                for field_name in [
                                    "name", "brand", "price", "price_value",
                                    "mrp", "mrp_value", "discount", "quantity",
                                    "description", "category", "image_url", "availability",
                                ]:
                                    val = getattr(dummy, field_name)
                                    if val and not getattr(result, field_name):
                                        setattr(result, field_name, val)
                                if result.name:
                                    print("  [Source: Embedded JSON]")
                                    return
                    except (json.JSONDecodeError, TypeError):
                        continue

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

    def _scrape_requests(self, url: str, result: SwiggyProductData) -> None:
        """Scrape using requests + BeautifulSoup."""
        html = self._fetch_page_requests(url)
        if not html:
            result.error = "Failed to fetch page (HTTP request failed)"
            return

        if self.debug:
            debug_file = f"debug_swiggy_{result.product_id or 'page'}.html"
            with open(debug_file, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"  Debug HTML saved to: {debug_file}")

        soup = BeautifulSoup(html, "lxml")
        self._extract_from_soup(soup, result)

        if not result.name:
            result.error = "Could not extract product data - page may require browser mode"

    def _scrape_browser(self, url: str, result: SwiggyProductData) -> None:
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
                debug_file = f"debug_swiggy_{result.product_id or 'page'}.html"
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

            # Supplement missing price from DOM even if name was found via JSON
            if result.name and not result.price:
                self._extract_from_dom(result)

            if not result.name:
                result.error = "Could not extract product data - page may not have loaded"

        except Exception as e:
            result.error = f"Browser scraping failed: {str(e)}"

    def scrape(self, url: str) -> SwiggyProductData:
        """
        Scrape a Swiggy Instamart product page.

        Args:
            url: Full Swiggy Instamart product URL

        Returns:
            SwiggyProductData with scraped information
        """
        result = SwiggyProductData(url=url)
        result.product_id = self._extract_product_id(url)

        if self.use_browser:
            self._scrape_browser(url, result)
        else:
            self._scrape_requests(url, result)

        return result

    def scrape_multiple(self, urls: list[str], delay: float = 3.0) -> list[SwiggyProductData]:
        """
        Scrape multiple Swiggy Instamart product URLs.

        Args:
            urls: List of Swiggy Instamart product URLs
            delay: Delay between requests in seconds

        Returns:
            List of SwiggyProductData objects
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
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
