"""
Swiggy Instamart Product Scraper

Scrapes product data from individual Swiggy Instamart product pages.
Uses three strategies in order of reliability:
  1. Network interception: Captures Swiggy's internal API JSON responses via CDP
  2. JavaScript extraction: Runs JS in the browser to extract data from the rendered page
  3. Meta tags + DOM fallback: Extracts from og: tags, page title, visible prices
"""

import re
import json
import time
import random
from typing import Optional
from dataclasses import dataclass, field

import requests as http_requests
from bs4 import BeautifulSoup

# Try undetected_chromedriver first (best anti-detection), fall back to regular Selenium
UNDETECTED_AVAILABLE = False
SELENIUM_AVAILABLE = False
EDGE_AVAILABLE = False

try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    UNDETECTED_AVAILABLE = True
    SELENIUM_AVAILABLE = True
except ImportError:
    pass

if not UNDETECTED_AVAILABLE:
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
        pass

# Try Edge browser support
try:
    from selenium import webdriver as _wb
    from selenium.webdriver.edge.service import Service as EdgeService
    from selenium.webdriver.edge.options import Options as EdgeOptions
    # Also import common Selenium if not already done
    if not SELENIUM_AVAILABLE:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
    EDGE_AVAILABLE = True
    SELENIUM_AVAILABLE = True
except ImportError:
    pass


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
    """Scraper for Swiggy Instamart product pages.

    Uses Chrome DevTools Protocol to intercept API responses,
    plus JS-based DOM extraction as a fallback.
    """

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
    }

    def __init__(self, headless: bool = True, debug: bool = False,
                 use_browser: bool = True, pincode: Optional[str] = "560103",
                 browser_type: str = "chrome"):
        self.headless = headless
        self.debug = debug
        self.use_browser = use_browser
        self.pincode = pincode
        self.coords = PINCODE_COORDS.get(pincode or "560103", PINCODE_COORDS["560103"])
        self.driver = None
        self._browser_type = browser_type  # "chrome" or "edge"
        self.session = http_requests.Session()
        self._location_set = False

        if use_browser:
            if not SELENIUM_AVAILABLE:
                print("Warning: Selenium not available, falling back to requests mode.")
                print("  Install with: pip install selenium webdriver-manager")
                self.use_browser = False
            else:
                try:
                    self.open_browser(browser_type)
                except Exception as e:
                    print(f"Warning: Could not start browser ({e}), falling back to requests mode.")
                    self.use_browser = False

    def open_browser(self, browser_type: str = "chrome"):
        """Open a fresh browser instance. Closes existing one first.

        Args:
            browser_type: "chrome" or "edge"
        """
        self.close()
        self._browser_type = browser_type
        self._location_set = False

        if browser_type == "edge" and EDGE_AVAILABLE:
            self._init_edge_browser()
        elif UNDETECTED_AVAILABLE and browser_type == "chrome":
            self._init_undetected_browser()
        elif SELENIUM_AVAILABLE:
            self._init_selenium_browser()
        else:
            raise RuntimeError(f"No browser driver available for {browser_type}")

    def _init_undetected_browser(self):
        """Initialize using undetected_chromedriver (bypasses bot detection)."""
        options = uc.ChromeOptions()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")

        # Enable performance logging for network interception
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

        self.driver = uc.Chrome(options=options, headless=self.headless)
        print("  [Browser: undetected_chromedriver (Chrome)]")

    def _init_selenium_browser(self):
        """Initialize using regular Selenium Chrome with stealth patches."""
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
            "Chrome/131.0.0.0 Safari/537.36"
        )
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        # Enable performance logging for network interception
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)

        # Apply CDP stealth patches
        self._apply_stealth_scripts()
        print("  [Browser: Selenium Chrome + stealth]")

    def _init_edge_browser(self):
        """Initialize using Microsoft Edge browser."""
        options = EdgeOptions()
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
            "Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
        )
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        # Enable performance logging for network interception
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

        self.driver = _wb.Edge(options=options)

        # Apply CDP stealth patches
        self._apply_stealth_scripts()
        print("  [Browser: Microsoft Edge + stealth]")

    def _apply_stealth_scripts(self):
        """Apply CDP-based stealth scripts to avoid bot detection."""
        stealth_js = """
            // Override navigator.webdriver
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

            // Override navigator.plugins (headless Chrome has empty plugins)
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });

            // Override navigator.languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });

            // Override chrome.runtime (headless doesn't have this)
            window.chrome = { runtime: {} };

            // Override permissions query
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) =>
                parameters.name === 'notifications'
                    ? Promise.resolve({state: Notification.permission})
                    : originalQuery(parameters);
        """
        try:
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": stealth_js
            })
        except Exception:
            # Fallback: execute directly
            try:
                self.driver.execute_script(stealth_js)
            except Exception:
                pass

    def _set_pincode_browser(self):
        """Set delivery pincode on Swiggy Instamart via cookies and localStorage."""
        if not self.pincode or self._location_set:
            return

        area = self.coords.get("area", "Koramangala")
        lat = self.coords["lat"]
        lng = self.coords["lng"]

        print(f"  Setting delivery location to {area}, Bangalore - {self.pincode}...")
        try:
            self.driver.get("https://www.swiggy.com/instamart")
            time.sleep(3)

            # Set location via cookies
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

            # Set via localStorage
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

            # Try to interact with location modal if visible
            self._try_set_location_ui(area)

            self._location_set = True
            print(f"  Location set: {area}, Bangalore - {self.pincode}")

        except Exception as e:
            print(f"  Warning: Could not set pincode ({e}), continuing without it")

    def _try_set_location_ui(self, area: str):
        """Try to set location through Swiggy's UI modal."""
        try:
            # Look for any visible text input
            inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='search']")
            input_elem = None
            for inp in inputs:
                if inp.is_displayed():
                    input_elem = inp
                    break

            if not input_elem:
                # Try clicking location-related buttons to open modal
                buttons = self.driver.find_elements(By.CSS_SELECTOR, "div[role='button'], button")
                for btn in buttons:
                    try:
                        text = btn.text.strip().lower()
                        if btn.is_displayed() and any(kw in text for kw in
                            ["location", "deliver", "address", "detect"]):
                            btn.click()
                            time.sleep(2)
                            # Look for input again
                            inputs = self.driver.find_elements(By.CSS_SELECTOR,
                                "input[type='text'], input[type='search']")
                            for inp in inputs:
                                if inp.is_displayed():
                                    input_elem = inp
                                    break
                            if input_elem:
                                break
                    except Exception:
                        continue

            if input_elem:
                input_elem.clear()
                input_elem.send_keys(f"{area}, Bangalore {self.pincode}")
                time.sleep(2)

                # Click first suggestion
                suggestions = self.driver.find_elements(By.CSS_SELECTOR,
                    "[role='option'], [role='listbox'] > *, li")
                for sug in suggestions:
                    try:
                        if sug.is_displayed() and sug.text.strip():
                            sug.click()
                            time.sleep(2)
                            break
                    except Exception:
                        continue

                # Click confirm/continue button
                buttons = self.driver.find_elements(By.CSS_SELECTOR, "button")
                for btn in buttons:
                    try:
                        text = btn.text.strip().lower()
                        if btn.is_displayed() and text and any(kw in text for kw in
                            ["confirm", "continue", "save", "deliver", "done"]):
                            btn.click()
                            time.sleep(2)
                            break
                    except Exception:
                        continue

        except Exception:
            pass

    def _extract_product_id(self, url: str) -> Optional[str]:
        """Extract product/item ID from Swiggy Instamart URL."""
        for pattern in [
            r'/item/[^/]+/([a-zA-Z0-9_-]+)(?:\?|$)',
            r'/product/[^/]+/([a-zA-Z0-9_-]+)(?:\?|$)',
            r'[?&]productId=([a-zA-Z0-9_-]+)',
            r'/instamart/[^/]+/[^/]+/([a-zA-Z0-9_-]+)(?:\?|$)',
            r'/([a-zA-Z0-9_-]+)(?:\?|$)',
        ]:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    # ─── Strategy 1: Network Interception via CDP ───────────────────

    def _capture_api_responses(self) -> list[dict]:
        """Capture JSON API responses from Chrome performance logs.

        After page load, examines all network responses for JSON containing
        product data (name + price). Returns list of parsed JSON objects.
        """
        product_jsons = []
        try:
            logs = self.driver.get_log("performance")
        except Exception:
            return product_jsons

        # Collect all response request IDs for JSON/API calls
        api_requests = []
        for entry in logs:
            try:
                message = json.loads(entry["message"])["message"]
                method = message.get("method", "")

                if method == "Network.responseReceived":
                    params = message.get("params", {})
                    response = params.get("response", {})
                    url = response.get("url", "")
                    mime = response.get("mimeType", "")
                    request_id = params.get("requestId")

                    # Look for JSON API responses from Swiggy
                    if request_id and ("json" in mime or "api" in url.lower()
                            or "instamart" in url.lower()
                            or "dapi" in url.lower()
                            or "product" in url.lower()
                            or "item" in url.lower()):
                        api_requests.append((request_id, url))
            except Exception:
                continue

        # Fetch response bodies and look for product data
        for request_id, url in api_requests:
            try:
                body = self.driver.execute_cdp_cmd(
                    "Network.getResponseBody", {"requestId": request_id}
                )
                body_text = body.get("body", "")
                if not body_text:
                    continue

                data = json.loads(body_text)
                # Check if this response contains product-like data
                product = self._find_product_in_json(data)
                if product:
                    product_jsons.append(product)
                    if self.debug:
                        print(f"  [CDP] Found product data in: {url[:80]}")
            except Exception:
                continue

        return product_jsons

    def _extract_from_api_json(self, product: dict, result: SwiggyProductData) -> bool:
        """Extract product data from an API JSON object. Returns True if name found."""
        # Name — try many common keys
        name_keys = [
            "name", "display_name", "displayName", "productName",
            "product_name", "title", "itemName", "item_name",
        ]
        for key in name_keys:
            val = product.get(key)
            if val and isinstance(val, str) and len(val) > 2:
                result.name = val
                break

        # Brand
        brand_keys = ["brand", "brandName", "brand_name", "manufacturer"]
        for key in brand_keys:
            val = product.get(key)
            if val and isinstance(val, str):
                result.brand = val
                break
            if isinstance(val, dict):
                result.brand = val.get("name") or val.get("displayName")
                break

        # Price (selling/offer price)
        price_keys = [
            "offer_price", "offerPrice", "sellingPrice", "selling_price",
            "price", "salePrice", "finalPrice", "offer_applied_price",
            "discountedPrice", "discounted_price",
        ]
        for key in price_keys:
            val = product.get(key)
            if val is not None:
                try:
                    fval = float(val)
                    if fval > 0:
                        result.price_value = fval
                        result.price = f"₹{fval:,.2f}"
                        break
                except (ValueError, TypeError):
                    pass

        # MRP
        mrp_keys = [
            "mrp", "maxRetailPrice", "max_retail_price",
            "marked_price", "markedPrice", "originalPrice",
            "original_price", "basePrice", "base_price",
        ]
        for key in mrp_keys:
            val = product.get(key)
            if val is not None:
                try:
                    fval = float(val)
                    if fval > 0:
                        result.mrp_value = fval
                        result.mrp = f"₹{fval:,.2f}"
                        break
                except (ValueError, TypeError):
                    pass

        # If we only got one price, check for nested price objects
        if not result.price_value or not result.mrp_value:
            for key in ["pricing", "priceInfo", "price_info", "priceDetails"]:
                nested = product.get(key)
                if isinstance(nested, dict):
                    if not result.price_value:
                        for pk in price_keys:
                            val = nested.get(pk)
                            if val is not None:
                                try:
                                    fval = float(val)
                                    if fval > 0:
                                        result.price_value = fval
                                        result.price = f"₹{fval:,.2f}"
                                        break
                                except (ValueError, TypeError):
                                    pass
                    if not result.mrp_value:
                        for mk in mrp_keys:
                            val = nested.get(mk)
                            if val is not None:
                                try:
                                    fval = float(val)
                                    if fval > 0:
                                        result.mrp_value = fval
                                        result.mrp = f"₹{fval:,.2f}"
                                        break
                                except (ValueError, TypeError):
                                    pass

        # Discount
        discount_keys = ["discount", "discountPercent", "discount_percent",
                         "discountPercentage", "offer_discount"]
        for key in discount_keys:
            val = product.get(key)
            if val:
                val_str = str(val)
                if "%" not in val_str:
                    val_str = f"{val_str}%"
                result.discount = val_str
                break

        # Calculate discount if we have both prices
        if not result.discount and result.price_value and result.mrp_value:
            if result.mrp_value > result.price_value:
                pct = ((result.mrp_value - result.price_value) / result.mrp_value) * 100
                result.discount = f"{pct:.0f}% OFF"

        # Quantity/pack size
        qty_keys = [
            "quantity", "packSize", "pack_size", "weight", "unit",
            "variant", "size", "pack_desc", "packDesc",
        ]
        for key in qty_keys:
            val = product.get(key)
            if val and isinstance(val, str) and len(val) < 50:
                result.quantity = val
                break

        # Description
        desc_keys = ["description", "long_description", "longDescription",
                     "shortDescription", "short_description", "desc"]
        for key in desc_keys:
            val = product.get(key)
            if val and isinstance(val, str) and len(val) > 5:
                result.description = val
                break

        # Category
        cat_keys = ["category", "categoryName", "category_name",
                    "categoryTitle", "department"]
        for key in cat_keys:
            val = product.get(key)
            if val and isinstance(val, str):
                result.category = val
                break

        # Images
        for key in ["images", "imageUrls", "image_urls"]:
            imgs = product.get(key)
            if isinstance(imgs, list) and imgs:
                img = imgs[0]
                result.image_url = img if isinstance(img, str) else img.get("url")
                break
        if not result.image_url:
            for key in ["image", "imageUrl", "image_url", "thumbnail",
                        "productImage", "product_image"]:
                val = product.get(key)
                if val and isinstance(val, str) and val.startswith("http"):
                    result.image_url = val
                    break

        # Availability
        avail_keys = ["available", "in_stock", "inStock", "is_available",
                      "isAvailable", "inventory"]
        for key in avail_keys:
            val = product.get(key)
            if val is False or val == 0 or val == "false":
                result.availability = "Out of Stock"
                break
            elif val is True or val == 1 or val == "true":
                result.availability = "In Stock"
                break

        if not result.availability and result.name:
            result.availability = "In Stock"

        # Highlights
        for key in ["highlights", "features", "key_features", "keyFeatures"]:
            val = product.get(key)
            if isinstance(val, list):
                result.highlights = [str(h) for h in val if h][:10]
                break

        return bool(result.name)

    def _find_product_in_json(self, data, depth: int = 0) -> Optional[dict]:
        """Recursively find a product-like dict in nested JSON."""
        if depth > 10:
            return None

        if isinstance(data, dict):
            # Check if this dict looks like a product
            name_keys = ["name", "display_name", "displayName", "productName",
                         "product_name", "title", "itemName"]
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

    # ─── Strategy 2: JavaScript-based Extraction ────────────────────

    def _extract_via_javascript(self, result: SwiggyProductData) -> bool:
        """Extract product data by executing JavaScript in the browser.

        This is more reliable than Selenium element queries because it
        can access the full DOM, handle shadow DOMs, and traverse text
        nodes efficiently.
        """
        js_code = """
        return (function() {
            var data = {};

            // 1. Try __NEXT_DATA__
            var nextScript = document.getElementById('__NEXT_DATA__');
            if (nextScript) {
                try {
                    data.__next_data = JSON.parse(nextScript.textContent);
                } catch(e) {}
            }

            // 2. Try JSON-LD
            var ldScripts = document.querySelectorAll('script[type="application/ld+json"]');
            ldScripts.forEach(function(s) {
                try {
                    var ld = JSON.parse(s.textContent);
                    if (ld && ld['@type'] === 'Product') {
                        data.json_ld = ld;
                    }
                    if (Array.isArray(ld)) {
                        ld.forEach(function(item) {
                            if (item && item['@type'] === 'Product') {
                                data.json_ld = item;
                            }
                        });
                    }
                } catch(e) {}
            });

            // 3. Try window.__INITIAL_STATE__ or similar global state
            var stateKeys = ['__INITIAL_STATE__', '__PRELOADED_STATE__',
                             '__APP_DATA__', '__APOLLO_STATE__'];
            stateKeys.forEach(function(key) {
                if (window[key]) {
                    try {
                        data['global_' + key] = window[key];
                    } catch(e) {}
                }
            });

            // 4. Scan ALL script tags for embedded JSON with product data
            var scripts = document.querySelectorAll('script:not([src])');
            scripts.forEach(function(s) {
                var text = s.textContent || '';
                if (text.length > 100 && text.length < 500000) {
                    // Look for JSON assignments
                    var patterns = [
                        /window\.__\w+__\s*=\s*(\{.+\})\s*;/s,
                        /window\.\w+\s*=\s*(\{.+\})\s*;/s,
                        /__NEXT_DATA__\s*=\s*(\{.+\})/s,
                    ];
                    patterns.forEach(function(pat) {
                        var match = text.match(pat);
                        if (match) {
                            try {
                                var parsed = JSON.parse(match[1]);
                                data.embedded_json = data.embedded_json || [];
                                data.embedded_json.push(parsed);
                            } catch(e) {}
                        }
                    });
                }
            });

            // 5. Extract meta tags
            var metas = {};
            ['og:title', 'og:description', 'og:image', 'og:url',
             'twitter:title', 'twitter:description', 'twitter:image',
             'description', 'product:price:amount', 'product:price:currency',
             'product:brand', 'product:availability'].forEach(function(name) {
                var el = document.querySelector('meta[property="' + name + '"]') ||
                         document.querySelector('meta[name="' + name + '"]');
                if (el) {
                    metas[name] = el.getAttribute('content');
                }
            });
            data.meta = metas;

            // 6. Page title
            data.page_title = document.title || '';

            // 7. h1 text
            var h1 = document.querySelector('h1');
            data.h1 = h1 ? h1.textContent.trim() : '';

            // 8. Find ALL visible prices on the page (₹ amounts)
            var bodyText = document.body ? document.body.innerText : '';
            var priceMatches = bodyText.match(/₹\\s?[\\d,]+(?:\\.\\d{1,2})?/g);
            data.all_prices = priceMatches || [];

            // 9. Find discount text from body
            var discountMatch = bodyText.match(/(\\d+%\\s*OFF)/i);
            data.discount_text = discountMatch ? discountMatch[1] : '';

            // 10. TEXT-POSITION approach: find ₹ prices near h1 text in body innerText.
            //     The body.innerText preserves visual order, so product prices appear
            //     right after the product name, while delivery fees appear later.
            data.nearby_prices = [];
            data.price_elements = [];
            if (h1 && bodyText) {
                var h1Text = h1.textContent.trim();
                var h1Pos = bodyText.indexOf(h1Text);
                if (h1Pos === -1 && h1Text.length > 20) {
                    // Try partial match (first 20 chars)
                    h1Pos = bodyText.indexOf(h1Text.substring(0, 20));
                }
                if (h1Pos >= 0) {
                    // Get text after h1 (next 800 chars should cover prices)
                    var afterH1 = bodyText.substring(h1Pos + h1Text.length, h1Pos + h1Text.length + 800);
                    var nearbyMatches = afterH1.match(/₹\\s?[\\d,]+(?:\\.\\d{1,2})?/g);
                    if (nearbyMatches) {
                        var seenVals = {};
                        for (var nm = 0; nm < nearbyMatches.length && data.nearby_prices.length < 5; nm++) {
                            var nmMatch = nearbyMatches[nm].match(/₹\\s?([\\d,]+(?:\\.\\d{1,2})?)/);
                            if (nmMatch) {
                                var nmVal = parseFloat(nmMatch[1].replace(/,/g, ''));
                                if (nmVal > 0 && !seenVals[nmVal]) {
                                    seenVals[nmVal] = true;
                                    data.nearby_prices.push({text: nearbyMatches[nm], value: nmVal});
                                }
                            }
                        }
                    }
                    data._debug_after_h1 = afterH1.substring(0, 200);
                }
            }

            // 11. Also try Selenium-style: find all elements with ₹ and check
            //     proximity to h1 via DOM position (getBoundingClientRect).
            if (h1 && data.nearby_prices.length === 0) {
                try {
                    var h1Rect = h1.getBoundingClientRect();
                    var allEls = document.querySelectorAll('*');
                    var seenVals2 = {};
                    for (var ae = 0; ae < allEls.length; ae++) {
                        var el = allEls[ae];
                        if (el.children.length > 0) continue; // only leaf elements
                        var tc = (el.textContent || '').trim();
                        if (tc.length >= 2 && tc.length < 20 && /₹|\\d{3,}/.test(tc)) {
                            var elRect = el.getBoundingClientRect();
                            // Check if this element is near h1 (within 500px vertically)
                            if (elRect.top > h1Rect.bottom - 50 && elRect.top < h1Rect.bottom + 500) {
                                // Walk up to find the full price text (₹ + digits may be in siblings)
                                var parent = el.parentElement;
                                var parentText = parent ? (parent.textContent || '').trim() : tc;
                                if (parentText.length < 30) {
                                    var pm2 = parentText.match(/₹\\s?([\\d,]+(?:\\.\\d{1,2})?)/);
                                    if (pm2) {
                                        var val2 = parseFloat(pm2[1].replace(/,/g, ''));
                                        if (val2 > 0 && !seenVals2[val2]) {
                                            seenVals2[val2] = true;
                                            // Check strikethrough
                                            var isStrike2 = false;
                                            var checkEl = el;
                                            for (var up2 = 0; up2 < 5; up2++) {
                                                if (!checkEl) break;
                                                var tag2 = (checkEl.tagName || '').toLowerCase();
                                                if (tag2 === 'del' || tag2 === 's' || tag2 === 'strike') {
                                                    isStrike2 = true; break;
                                                }
                                                try {
                                                    var cs2 = window.getComputedStyle(checkEl);
                                                    if ((cs2.textDecorationLine || cs2.textDecoration || '').indexOf('line-through') !== -1) {
                                                        isStrike2 = true; break;
                                                    }
                                                } catch(ex) {}
                                                checkEl = checkEl.parentElement;
                                            }
                                            var elColor2 = '';
                                            try { elColor2 = window.getComputedStyle(parent || el).color || ''; } catch(ex2) {}
                                            data.nearby_prices.push({text: parentText, value: val2, strike: isStrike2, color: elColor2});
                                        }
                                    }
                                }
                            }
                        }
                    }
                } catch(domErr) {}
            }

            // 12. Look for "Add" or "Add to cart" button (availability indicator)
            var addBtns = document.querySelectorAll('button');
            data.has_add_button = false;
            for (var j = 0; j < addBtns.length; j++) {
                var btnText = (addBtns[j].textContent || '').trim().toLowerCase();
                if (addBtns[j].offsetParent !== null &&
                    (btnText === 'add' || btnText.includes('add to') ||
                     btnText.includes('add item') || /^\\+$/.test(btnText) ||
                     btnText.includes('notify'))) {
                    data.has_add_button = true;
                    break;
                }
            }

            // 13. Check for sold out ONLY near the product area, not the whole page
            data.has_sold_out = false;
            if (h1) {
                var stockContainer = h1.parentElement;
                for (var s = 0; s < 5; s++) {
                    if (!stockContainer) break;
                    var sText = stockContainer.innerText || '';
                    if (/sold\\s*out|out\\s*of\\s*stock|currently\\s*unavailable|not\\s*available/i.test(sText)) {
                        data.has_sold_out = true;
                        break;
                    }
                    stockContainer = stockContainer.parentElement;
                }
            }

            // 14. Find all images that might be product images
            var imgs = document.querySelectorAll('img');
            var productImgs = [];
            imgs.forEach(function(img) {
                var src = img.src || img.getAttribute('data-src') || '';
                var alt = img.alt || '';
                if (src && !src.startsWith('data:') && src.startsWith('http')) {
                    // Heuristic: large images or images with product-related alt
                    var w = img.naturalWidth || img.width || 0;
                    var h_val = img.naturalHeight || img.height || 0;
                    if (w > 100 || h_val > 100 || alt.length > 5) {
                        productImgs.push({src: src, alt: alt, w: w, h: h_val});
                    }
                }
            });
            data.images = productImgs;

            return JSON.stringify(data);
        })();
        """

        try:
            raw = self.driver.execute_script(js_code)
            if not raw:
                return False
            js_data = json.loads(raw)
        except Exception as e:
            if self.debug:
                print(f"  [JS] Extraction failed: {e}")
            return False

        if self.debug:
            debug_file = f"debug_swiggy_jsdata_{result.product_id or 'page'}.json"
            with open(debug_file, "w", encoding="utf-8") as f:
                json.dump(js_data, f, indent=2, ensure_ascii=False)
            print(f"  [JS] Data saved to: {debug_file}")

        # Process __NEXT_DATA__
        next_data = js_data.get("__next_data")
        if next_data:
            product = self._find_product_in_json(next_data)
            if product and self._extract_from_api_json(product, result):
                print("  [Source: __NEXT_DATA__]")
                # Don't return early — continue to nearby_prices which can
                # override wrong prices (JSON APIs often return delivery fees)

        # Process JSON-LD
        json_ld = js_data.get("json_ld")
        if json_ld:
            self._extract_from_json_ld(json_ld, result)
            if result.name:
                print("  [Source: JSON-LD]")

        # Process embedded JSON
        for embedded in js_data.get("embedded_json", []):
            if not result.name:
                product = self._find_product_in_json(embedded)
                if product and self._extract_from_api_json(product, result):
                    print("  [Source: Embedded JSON]")
                    break

        # Process global state objects
        for key, val in js_data.items():
            if key.startswith("global_") and isinstance(val, dict) and not result.name:
                product = self._find_product_in_json(val)
                if product and self._extract_from_api_json(product, result):
                    print(f"  [Source: {key}]")
                    break

        # ── Name extraction (prefer h1 > og:title > page title) ──
        meta = js_data.get("meta", {})

        # h1 is the best source for clean product name
        h1_text = js_data.get("h1", "")
        if not result.name and h1_text and len(h1_text) > 3:
            result.name = h1_text

        # Fallback: meta tags (clean up "Buy...Online At Best Price" patterns)
        if not result.name:
            og_title = meta.get("og:title") or meta.get("twitter:title")
            if og_title:
                cleaned = re.sub(
                    r'^Buy\s+', '', og_title, flags=re.IGNORECASE
                )
                cleaned = re.sub(
                    r'\s*[\|–-]\s*(Swiggy|Instamart).*$', '',
                    cleaned, flags=re.IGNORECASE
                )
                cleaned = re.sub(
                    r'\s+Online\s*(\([^)]*\))?\s*(At\s+Best\s+Price)?.*$', '',
                    cleaned, flags=re.IGNORECASE
                ).strip()
                if cleaned and len(cleaned) > 3:
                    result.name = cleaned

        # Fallback: page title
        if not result.name:
            page_title = js_data.get("page_title", "")
            if page_title:
                cleaned = re.sub(r'^Buy\s+', '', page_title, flags=re.IGNORECASE)
                cleaned = re.sub(
                    r'\s*[\|–-]\s*(Swiggy|Instamart).*$', '',
                    cleaned, flags=re.IGNORECASE
                )
                cleaned = re.sub(
                    r'\s+Online\s*(\([^)]*\))?\s*(At\s+Best\s+Price)?.*$', '',
                    cleaned, flags=re.IGNORECASE
                ).strip()
                if cleaned and len(cleaned) > 3:
                    result.name = cleaned

        if not result.description:
            result.description = meta.get("og:description") or meta.get("description")
        if not result.image_url:
            result.image_url = meta.get("og:image") or meta.get("twitter:image")

        # ── Price extraction ──
        # The rendered page prices are MORE reliable than JSON-LD/API prices
        # (which often return delivery fees like ₹49 instead of product price).
        # We collect prices from multiple sources and pick the best.
        nearby_prices = js_data.get("nearby_prices", [])
        all_prices = js_data.get("all_prices", [])
        meta = js_data.get("meta", {})

        # Debug output
        debug_after_h1 = js_data.get("_debug_after_h1", "")
        print(f"  [Debug] nearby_prices: {nearby_prices}")
        print(f"  [Debug] all_prices: {all_prices[:8]}")
        if debug_after_h1:
            print(f"  [Debug] Text after h1: {debug_after_h1[:200]}")

        # Save the JSON-LD/API price to compare later
        json_ld_price = result.price_value

        # Source A: og:description — contains "at Rs. 3199" which is the real price
        desc_price = None
        desc = meta.get("og:description") or meta.get("description") or ""
        desc_price_match = re.search(r'(?:Rs\.?|₹)\s?([\d,]+(?:\.\d{1,2})?)', desc)
        if desc_price_match:
            desc_price = float(desc_price_match.group(1).replace(",", ""))
            print(f"  [Debug] Price from og:description: ₹{desc_price}")

        # Source B: nearby_prices (text near h1 in body innerText)
        # Source C: all_prices (all ₹ amounts on the page)

        # Decision logic: pick the best selling price
        best_selling = None
        best_mrp = None

        # Priority 1: nearby_prices (most reliable — near product name)
        if nearby_prices:
            strike_vals = [p for p in nearby_prices if p.get("strike") and p.get("value", 0) > 0]
            non_strike_vals = [p for p in nearby_prices if not p.get("strike") and p.get("value", 0) > 0]
            if strike_vals and non_strike_vals:
                best_mrp = max(p["value"] for p in strike_vals)
                selling_candidates = [p["value"] for p in non_strike_vals if p["value"] <= best_mrp]
                best_selling = max(selling_candidates) if selling_candidates else non_strike_vals[0]["value"]
            else:
                vals = [p.get("value", 0) for p in nearby_prices if p.get("value", 0) > 0]
                if len(vals) >= 2:
                    best_selling = min(vals[0], vals[1])
                    best_mrp = max(vals[0], vals[1])
                elif vals:
                    best_selling = vals[0]
            if best_selling:
                print(f"  [Price source] nearby_prices: selling=₹{best_selling}, mrp=₹{best_mrp}")

        # Priority 2: og:description price (very reliable for selling price)
        if not best_selling and desc_price and desc_price > 0:
            best_selling = desc_price
            # Find MRP from all_prices: any unique price > selling price
            for p_text in all_prices:
                val = self._parse_price_value(p_text)
                if val and val > best_selling:
                    best_mrp = val
                    break
            print(f"  [Price source] og:description: selling=₹{best_selling}, mrp=₹{best_mrp}")

        # Priority 3: all_prices with smart filtering
        if not best_selling and all_prices:
            parsed = []
            seen_vals = set()
            for p_text in all_prices:
                val = self._parse_price_value(p_text)
                if val and val > 0 and val not in seen_vals:
                    seen_vals.add(val)
                    parsed.append(val)
            if parsed:
                parsed.sort()
                # If we have the JSON-LD price and it's suspiciously small,
                # skip it and use larger prices
                if json_ld_price and len(parsed) >= 3:
                    # Skip the smallest price (likely delivery fee)
                    bigger = [v for v in parsed if v > json_ld_price * 5]
                    if bigger:
                        best_selling = bigger[0]
                        if len(bigger) >= 2:
                            best_mrp = bigger[-1]
                if not best_selling:
                    if len(parsed) >= 2:
                        best_selling = parsed[0]
                        best_mrp = parsed[-1]
                    else:
                        best_selling = parsed[0]
            if best_selling:
                print(f"  [Price source] all_prices: selling=₹{best_selling}, mrp=₹{best_mrp}")

        # Priority 4: JSON-LD/API price (least reliable for Swiggy)
        if not best_selling and json_ld_price:
            best_selling = json_ld_price
            print(f"  [Price source] JSON-LD: selling=₹{best_selling}")

        # Apply the best prices — clear old JSON-LD values first
        # so the discount calculation doesn't use wrong ₹49
        if best_selling and best_selling > 0:
            result.price_value = best_selling
            result.price = f"₹{best_selling:,.2f}"
            result.mrp_value = None
            result.mrp = None
            result.discount = None
            print(f"  [Price FINAL] selling=₹{best_selling}")
        if best_mrp and best_mrp > 0:
            result.mrp_value = best_mrp
            result.mrp = f"₹{best_mrp:,.2f}"
            print(f"  [Price FINAL] mrp=₹{best_mrp}")

        # ── Discount ──
        if not result.discount:
            disc_text = js_data.get("discount_text", "")
            if disc_text:
                result.discount = disc_text

        if not result.discount and result.price_value and result.mrp_value:
            if result.mrp_value > result.price_value:
                pct = ((result.mrp_value - result.price_value) / result.mrp_value) * 100
                result.discount = f"{pct:.0f}% OFF"

        # Calculate missing price from discount %
        if result.discount and (result.price_value or result.mrp_value):
            pct_match = re.search(r'(\d+)\s*%', result.discount)
            if pct_match:
                pct = float(pct_match.group(1)) / 100.0
                if result.price_value and not result.mrp_value and 0 < pct < 1:
                    mrp = result.price_value / (1 - pct)
                    result.mrp_value = round(mrp, 2)
                    result.mrp = f"₹{result.mrp_value:,.2f}"
                elif result.mrp_value and not result.price_value and 0 < pct < 1:
                    selling = result.mrp_value * (1 - pct)
                    result.price_value = round(selling, 2)
                    result.price = f"₹{result.price_value:,.2f}"

        # ── Availability ──
        # Having a selling price is a strong signal for in-stock.
        # "sold out" text in the container area can be a false positive
        # (e.g. description text, footer links).
        if not result.availability:
            if result.price_value and result.price_value > 0:
                # Product has a selling price displayed — it's in stock
                result.availability = "In Stock"
            elif js_data.get("has_add_button"):
                result.availability = "In Stock"
            elif js_data.get("has_sold_out") and not result.price_value:
                result.availability = "Out of Stock"
            elif result.name:
                result.availability = "In Stock"

        # Image from page images (pick largest)
        if not result.image_url:
            images = js_data.get("images", [])
            if images:
                # Sort by size, pick largest
                images.sort(key=lambda x: (x.get("w", 0) * x.get("h", 0)), reverse=True)
                for img in images:
                    src = img.get("src", "")
                    if src and "logo" not in src.lower() and "icon" not in src.lower():
                        result.image_url = src
                        break

        # Extract quantity from product name
        if not result.quantity and result.name:
            qty_match = re.search(
                r'(\d+(?:\.\d+)?\s*(?:g|kg|ml|l|L|pcs?|pack|units?|piece|no|nos))\b',
                result.name, re.IGNORECASE
            )
            if qty_match:
                result.quantity = qty_match.group(1)

        return bool(result.name)

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

        if ld_data.get("category"):
            result.category = ld_data["category"]

        offers = ld_data.get("offers")
        if isinstance(offers, dict):
            # NOTE: Do NOT set price from JSON-LD offers — Swiggy's JSON-LD
            # often has wrong price (e.g. delivery fee ₹49 instead of product
            # price ₹3199). Prices are extracted from the rendered page instead.
            availability = offers.get("availability", "")
            if "InStock" in availability:
                result.availability = "In Stock"
            elif "OutOfStock" in availability:
                result.availability = "Out of Stock"
        elif isinstance(offers, list) and offers:
            # Skip price from offers list (same unreliable data)
            pass

        rating_data = ld_data.get("aggregateRating")
        if rating_data:
            result.rating = str(rating_data.get("ratingValue", ""))
            result.rating_count = str(rating_data.get("ratingCount", ""))

    # ─── Strategy 3: Requests mode (non-browser) ───────────────────

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
                product = self._find_product_in_json(next_data)
                if product and self._extract_from_api_json(product, result):
                    print("  [Source: __NEXT_DATA__]")
                    return
            except (json.JSONDecodeError, Exception):
                pass

        # Try embedded JSON in script tags
        for script in soup.find_all("script"):
            script_text = script.string or ""
            if len(script_text) > 100:
                for pattern in [
                    r'window\.__\w+__\s*=\s*({.+?});?\s*$',
                    r'window\.\w+\s*=\s*({.+?});?\s*$',
                ]:
                    json_match = re.search(pattern, script_text, re.DOTALL)
                    if json_match:
                        try:
                            data = json.loads(json_match.group(1))
                            product = self._find_product_in_json(data)
                            if product and self._extract_from_api_json(product, result):
                                print("  [Source: Embedded JSON]")
                                return
                        except (json.JSONDecodeError, TypeError):
                            continue

        # Fallback: parse HTML elements
        h1 = soup.find("h1")
        if h1:
            text = h1.get_text(strip=True)
            if text and len(text) > 3:
                result.name = text

        if not result.name:
            meta_title = soup.find("meta", {"property": "og:title"})
            if meta_title and meta_title.get("content"):
                result.name = meta_title["content"]

        if not result.description:
            meta_desc = soup.find("meta", {"property": "og:description"})
            if meta_desc and meta_desc.get("content"):
                result.description = meta_desc["content"]

        if not result.image_url:
            meta_img = soup.find("meta", {"property": "og:image"})
            if meta_img and meta_img.get("content"):
                result.image_url = meta_img["content"]

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

    # ─── Browser scraping with retry ────────────────────────────────

    def _wait_for_page_render(self, timeout: int = 10) -> bool:
        """Wait for the product page to render."""
        # Wait for h1 or any content indicator
        try:
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.find_element(By.CSS_SELECTOR, "h1").text.strip()
            )
            return True
        except Exception:
            pass

        # Wait for any ₹ price in body
        try:
            WebDriverWait(self.driver, 5).until(
                lambda d: "₹" in (d.find_element(By.TAG_NAME, "body").text or "")
            )
            return True
        except Exception:
            pass

        return False

    def _dismiss_popups(self) -> None:
        """Dismiss any popups or modals that may block the page."""
        try:
            buttons = self.driver.find_elements(By.CSS_SELECTOR, "button")
            for btn in buttons:
                try:
                    if btn.is_displayed():
                        text = btn.text.strip().lower()
                        aria = (btn.get_attribute("aria-label") or "").lower()
                        if any(kw in text or kw in aria for kw in
                               ["close", "dismiss", "×", "✕", "got it", "ok"]):
                            btn.click()
                            time.sleep(0.5)
                            break
                except Exception:
                    continue
        except Exception:
            pass

    def _print_page_diagnostic(self):
        """Print diagnostic info about the current page state."""
        try:
            title = self.driver.title or "(empty)"
            current_url = self.driver.current_url or "(empty)"
            body_text = self.driver.find_element(By.TAG_NAME, "body").text or ""
            text_len = len(body_text)
            snippet = body_text[:300].replace("\n", " ").strip()
            has_rupee = "₹" in body_text
            has_h1 = bool(self.driver.find_elements(By.CSS_SELECTOR, "h1"))

            print(f"  [Diagnostic] Title: {title[:80]}")
            print(f"  [Diagnostic] URL: {current_url[:80]}")
            print(f"  [Diagnostic] Body text length: {text_len} chars")
            print(f"  [Diagnostic] Has ₹: {has_rupee}, Has h1: {has_h1}")
            if snippet:
                print(f"  [Diagnostic] Text preview: {snippet[:200]}...")
        except Exception as e:
            print(f"  [Diagnostic] Error reading page: {e}")

    # Names that indicate the page didn't load the actual product
    BAD_NAMES = {
        "instamart", "swiggy", "swiggy instamart", "home", "instamart home",
        "swiggy instamart - online grocery shopping",
    }

    def _is_error_page(self) -> bool:
        """Check if Swiggy is showing an error/rate-limit page."""
        try:
            body_text = self.driver.find_element(By.TAG_NAME, "body").text or ""
            error_phrases = [
                "something went wrong",
                "our best minds are on this",
                "please refresh or come back later",
                "try again",
                "too many requests",
                "access denied",
            ]
            body_lower = body_text.lower()
            return any(phrase in body_lower for phrase in error_phrases) and len(body_text) < 500
        except Exception:
            return False

    def _is_bad_name(self, name: str) -> bool:
        """Check if a scraped name is a generic page title, not a product name."""
        if not name:
            return True
        return name.strip().lower() in self.BAD_NAMES

    def _scrape_browser(self, url: str, result: SwiggyProductData) -> None:
        """Scrape using Selenium browser with network interception + retry."""
        max_attempts = 4
        timeouts = [10, 15, 20, 25]
        # Backoff delays: wait longer on each retry (rate-limit recovery)
        retry_delays = [8, 15, 30]

        try:
            # Set pincode/location before first scrape
            if self.pincode and not self._location_set:
                self._set_pincode_browser()

            for attempt in range(max_attempts):
                try:
                    if attempt > 0:
                        backoff = retry_delays[min(attempt - 1, len(retry_delays) - 1)]
                        jitter = random.uniform(0, 3)
                        wait_time = backoff + jitter
                        print(f"  Retrying (attempt {attempt + 1}/{max_attempts}) after {wait_time:.0f}s backoff...")
                        time.sleep(wait_time)

                    # Clear previous state
                    if attempt > 0:
                        self.driver.get("about:blank")
                        time.sleep(1)
                        # Clear result for retry
                        for attr in ["name", "brand", "price", "price_value", "mrp",
                                     "mrp_value", "discount", "quantity", "description",
                                     "category", "image_url", "availability", "rating",
                                     "rating_count", "error"]:
                            setattr(result, attr, None)
                        result.highlights = []

                    # Load the page
                    self.driver.get(url)

                    # Wait longer — Swiggy SPA needs time to render
                    rendered = self._wait_for_page_render(timeout=timeouts[attempt])
                    if not rendered:
                        # Extra wait for slow-loading SPAs
                        time.sleep(5)

                    # Check for Swiggy error/rate-limit page
                    if self._is_error_page():
                        print("  [!] Swiggy error page detected (rate-limited). Will retry with longer backoff.")
                        if attempt < max_attempts - 1:
                            continue
                        else:
                            result.error = "Swiggy rate-limited: 'Something went wrong' after all retries"
                            return

                    # Scroll to trigger lazy content
                    self.driver.execute_script("window.scrollTo(0, 300);")
                    time.sleep(2)
                    self._dismiss_popups()

                    # Print diagnostic info (always, to help debug)
                    if attempt == 0:
                        self._print_page_diagnostic()

                    # Save debug files
                    if self.debug and attempt == 0:
                        try:
                            page_source = self.driver.page_source
                            debug_file = f"debug_swiggy_{result.product_id or 'page'}.html"
                            with open(debug_file, "w", encoding="utf-8") as f:
                                f.write(page_source)
                            print(f"  Debug HTML saved to: {debug_file}")
                        except Exception:
                            pass

                    # Strategy 1: Capture API responses from network logs
                    api_products = self._capture_api_responses()
                    if api_products:
                        best = api_products[0]
                        if self._extract_from_api_json(best, result):
                            print("  [Source: Network API]")
                            # Don't return — continue to JS extraction which uses
                            # nearby_prices to override potentially wrong API prices

                    # Strategy 2: JavaScript-based extraction (always run —
                    # nearby_prices can override wrong prices from API/JSON-LD)
                    self._extract_via_javascript(result)

                    # Filter out bad names (generic page titles like "Instamart")
                    if self._is_bad_name(result.name):
                        print(f"  [!] Bad name '{result.name}' — page didn't load product. Retrying...")
                        result.name = None
                        if attempt < max_attempts - 1:
                            continue

                    # If we got a name but no price, try once more with a longer wait
                    if result.name and not result.price_value and attempt < max_attempts - 1:
                        continue

                    # If we got a name, we have something — return it
                    if result.name:
                        return

                except KeyboardInterrupt:
                    raise  # Let KeyboardInterrupt propagate to outer handler
                except Exception as attempt_err:
                    print(f"  [!] Attempt {attempt + 1} error: {attempt_err}")
                    if attempt >= max_attempts - 1:
                        result.error = f"All {max_attempts} attempts failed. Last error: {attempt_err}"
                        return

            # All attempts failed without error but no data extracted
            if not result.error:
                result.error = (
                    "Could not extract product data after all attempts - "
                    "page may not have loaded or URL may be invalid. "
                    "Try: pip install undetected-chromedriver  OR  --no-headless"
                )

        except KeyboardInterrupt:
            print("  Interrupted during scraping — recording partial result.")
            if not result.error:
                result.error = "Interrupted by user (Ctrl+C)"
        except Exception as e:
            result.error = f"Browser scraping failed: {str(e)}"

    # ─── Utility ────────────────────────────────────────────────────

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

    # ─── Public API ─────────────────────────────────────────────────

    def scrape(self, url: str) -> SwiggyProductData:
        """Scrape a Swiggy Instamart product page."""
        result = SwiggyProductData(url=url)
        result.product_id = self._extract_product_id(url)

        if self.use_browser:
            self._scrape_browser(url, result)
        else:
            self._scrape_requests(url, result)

        return result

    def scrape_multiple(self, urls: list[str], delay: float = 3.0) -> list[SwiggyProductData]:
        """Scrape multiple Swiggy Instamart product URLs."""
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
