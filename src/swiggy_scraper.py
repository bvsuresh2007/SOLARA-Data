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
                 use_browser: bool = True, pincode: Optional[str] = "560103"):
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
        """Initialize Chrome browser with performance logging for network interception."""
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

        # Enable performance logging to capture network requests
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

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
        (function() {
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

            // 9. Find strikethrough/deleted prices (usually MRP)
            var strikeEls = document.querySelectorAll('del, s, [style*="line-through"]');
            var strikePrices = [];
            strikeEls.forEach(function(el) {
                var t = el.textContent.trim();
                if (t && /₹/.test(t)) {
                    strikePrices.push(t);
                }
            });
            data.strike_prices = strikePrices;

            // 10. Find discount text
            var discountMatch = bodyText.match(/(\\d+%\\s*OFF)/i);
            data.discount_text = discountMatch ? discountMatch[1] : '';

            // 11. Scoped price extraction: find prices near the h1 product name
            if (h1) {
                // Walk up to find a container with prices
                var container = h1;
                for (var i = 0; i < 6; i++) {
                    container = container.parentElement;
                    if (!container) break;
                    var cText = container.innerText || '';
                    if (/₹/.test(cText) && cText.length > 50 && cText.length < 5000) {
                        var scopedPrices = cText.match(/₹\\s?[\\d,]+(?:\\.\\d{1,2})?/g);
                        data.scoped_prices = scopedPrices || [];
                        data.scoped_container_text = cText.substring(0, 2000);
                        break;
                    }
                }
            }

            // 12. Look for "Add" or "Add to cart" button (availability indicator)
            var addBtns = document.querySelectorAll('button');
            data.has_add_button = false;
            for (var j = 0; j < addBtns.length; j++) {
                var btnText = (addBtns[j].textContent || '').trim().toLowerCase();
                if (addBtns[j].offsetParent !== null &&
                    (btnText === 'add' || btnText.includes('add to') ||
                     btnText.includes('add item'))) {
                    data.has_add_button = true;
                    break;
                }
            }

            // 13. Look for any "out of stock" or "sold out" text
            data.has_sold_out = /sold\\s*out|out\\s*of\\s*stock|currently\\s*unavailable/i.test(bodyText);

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
                return True

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

        # Extract from meta tags
        meta = js_data.get("meta", {})
        if not result.name:
            result.name = meta.get("og:title") or meta.get("twitter:title")
            # Clean up — remove " | Swiggy Instamart" suffix
            if result.name:
                result.name = re.sub(r'\s*[\|–-]\s*(Swiggy|Instamart).*$', '',
                                     result.name, flags=re.IGNORECASE).strip()
        if not result.description:
            result.description = meta.get("og:description") or meta.get("description")
        if not result.image_url:
            result.image_url = meta.get("og:image") or meta.get("twitter:image")

        # Product name from h1
        h1_text = js_data.get("h1", "")
        if not result.name and h1_text and len(h1_text) > 3:
            result.name = h1_text

        # Product name from page title
        if not result.name:
            page_title = js_data.get("page_title", "")
            if page_title and "Swiggy" in page_title:
                cleaned = re.sub(r'\s*[\|–-]\s*(Swiggy|Instamart|Buy).*$', '',
                                 page_title, flags=re.IGNORECASE).strip()
                if cleaned and len(cleaned) > 3:
                    result.name = cleaned

        # Extract prices — prefer scoped prices (near the product name)
        scoped_prices = js_data.get("scoped_prices", [])
        all_prices = js_data.get("all_prices", [])
        strike_prices = js_data.get("strike_prices", [])

        # Use scoped prices if available, otherwise fall back to all prices
        price_source = scoped_prices if scoped_prices else all_prices

        if not result.price_value and price_source:
            # Parse all price values
            parsed = []
            seen = set()
            for p_text in price_source:
                val = self._parse_price_value(p_text)
                if val and val > 0 and val not in seen:
                    seen.add(val)
                    parsed.append(val)

            if parsed:
                parsed.sort()
                if len(parsed) >= 2:
                    # Two distinct prices: smaller = selling, larger = MRP
                    result.price_value = parsed[0]
                    result.price = f"₹{parsed[0]:,.2f}"
                    result.mrp_value = parsed[-1]
                    result.mrp = f"₹{parsed[-1]:,.2f}"
                elif len(parsed) == 1:
                    result.price_value = parsed[0]
                    result.price = f"₹{parsed[0]:,.2f}"

        # MRP from strikethrough elements
        if not result.mrp_value and strike_prices:
            for sp in strike_prices:
                val = self._parse_price_value(sp)
                if val and val > 0:
                    result.mrp_value = val
                    result.mrp = f"₹{val:,.2f}"
                    break

        # Discount
        if not result.discount:
            disc_text = js_data.get("discount_text", "")
            if disc_text:
                result.discount = disc_text

        # Calculate discount from prices
        if not result.discount and result.price_value and result.mrp_value:
            if result.mrp_value > result.price_value:
                pct = ((result.mrp_value - result.price_value) / result.mrp_value) * 100
                result.discount = f"{pct:.0f}% OFF"

        # Calculate missing price from discount
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

        # Availability
        if not result.availability:
            if js_data.get("has_add_button"):
                result.availability = "In Stock"
            elif js_data.get("has_sold_out"):
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
            price = offers.get("price")
            if price:
                result.price_value = float(price)
                result.price = f"₹{result.price_value:,.2f}"
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
                result.price = f"₹{result.price_value:,.2f}"

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

    def _scrape_browser(self, url: str, result: SwiggyProductData) -> None:
        """Scrape using Selenium browser with network interception + retry."""
        max_attempts = 3
        timeouts = [10, 12, 15]

        try:
            # Set pincode/location before first scrape
            if self.pincode and not self._location_set:
                self._set_pincode_browser()

            for attempt in range(max_attempts):
                if attempt > 0:
                    print(f"  Retrying (attempt {attempt + 1}/{max_attempts})...")

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
                self._wait_for_page_render(timeout=timeouts[attempt])

                # Scroll to trigger lazy content
                self.driver.execute_script("window.scrollTo(0, 300);")
                time.sleep(1)
                self._dismiss_popups()

                # Save debug HTML on first attempt
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
                        return

                # Strategy 2: JavaScript-based extraction
                if self._extract_via_javascript(result):
                    return

                # If we got a name but no price, try once more with a longer wait
                if result.name and not result.price_value and attempt < max_attempts - 1:
                    continue

                # If we got a name, we have something — return it
                if result.name:
                    return

            # All attempts failed
            result.error = (
                "Could not extract product data after 3 attempts - "
                "page may not have loaded or URL may be invalid"
            )

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
