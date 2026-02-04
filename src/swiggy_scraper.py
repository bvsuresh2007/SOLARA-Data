"""
Swiggy Instamart Product Scraper

Scrapes product data (name, price, MRP, discount, brand, availability)
from Swiggy Instamart for a given pincode/location.

Uses Selenium browser automation since Swiggy Instamart is a React SPA
that requires JavaScript rendering. Intercepts API responses and
extracts product data from both DOM and JSON payloads.
"""

import re
import time
import json
import random
from typing import Optional
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

# Selenium imports
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
class SwiggyProduct:
    """Data class for Swiggy Instamart product information."""
    name: str
    brand: Optional[str] = None
    price: Optional[float] = None
    mrp: Optional[float] = None
    discount: Optional[str] = None
    quantity: Optional[str] = None
    category: Optional[str] = None
    available: bool = True
    image_url: Optional[str] = None
    delivery_time: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None


class SwiggyInstamartScraper:
    """Scraper for Swiggy Instamart product data using Selenium."""

    BASE_URL = "https://www.swiggy.com"
    INSTAMART_URL = "https://www.swiggy.com/instamart"
    SEARCH_URL = "https://www.swiggy.com/instamart/search"

    def __init__(self, pincode: str = "560103", debug: bool = False, headless: bool = True):
        """
        Initialize the Swiggy Instamart scraper.

        Args:
            pincode: Delivery pincode (default: 560103 - Koramangala, Bangalore)
            debug: If True, save HTML to files for inspection
            headless: If True, run browser in headless mode
        """
        self.pincode = pincode
        self.debug = debug
        self.headless = headless
        self.coords = PINCODE_COORDS.get(pincode, PINCODE_COORDS["560103"])
        self.ua = UserAgent()
        self.driver = None
        self.location_set = False

        if not SELENIUM_AVAILABLE:
            raise ImportError(
                "Selenium is required for Swiggy scraper. "
                "Run: pip install selenium webdriver-manager"
            )

        self._init_browser()

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
        options.add_argument(f"user-agent={self.ua.random}")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        # Enable performance logging for API interception
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)

        # Remove webdriver flag
        self.driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

    def _set_location(self) -> bool:
        """Set delivery location on Swiggy Instamart for the configured pincode."""
        if self.location_set:
            return True

        area = self.coords.get("area", "Koramangala")
        lat = self.coords["lat"]
        lng = self.coords["lng"]

        try:
            # Navigate to Swiggy Instamart
            self.driver.get(self.INSTAMART_URL)
            time.sleep(3)

            # Set location via cookies
            self.driver.add_cookie({
                "name": "userLocation",
                "value": json.dumps({
                    "lat": lat, "lng": lng,
                    "address": f"{area}, Bangalore, Karnataka {self.pincode}",
                    "area": area
                }),
                "domain": ".swiggy.com"
            })

            # Set individual lat/lng cookies
            for name, value in [("lat", str(lat)), ("lng", str(lng))]:
                try:
                    self.driver.add_cookie({
                        "name": name, "value": value,
                        "domain": ".swiggy.com"
                    })
                except Exception:
                    pass

            # Try UI-based location setting
            self._set_location_via_ui(area)

            # Reload with location set
            self.driver.get(self.INSTAMART_URL)
            time.sleep(4)

            if self.debug:
                with open("debug_swiggy_home.html", "w", encoding="utf-8") as f:
                    f.write(self.driver.page_source)

            self.location_set = True
            print(f"  Location set: {area}, Bangalore - {self.pincode}")
            return True

        except Exception as e:
            print(f"  Error setting location: {e}")
            return False

    def _set_location_via_ui(self, area: str):
        """Try to set location through Swiggy's UI elements."""
        try:
            # Click on address/location button
            addr_selectors = [
                "[data-testid='address-name']",
                "[data-testid='search-location']",
                ".location-text",
                "._2vML0",
            ]
            for sel in addr_selectors:
                try:
                    btn = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
                    )
                    btn.click()
                    time.sleep(1)
                    break
                except Exception:
                    continue

            # Type in search field
            input_selectors = [
                "input[placeholder*='Search for area']",
                "input[placeholder*='search']",
                "input[placeholder*='area']",
                "input[data-testid='location-search-input']",
            ]
            for sel in input_selectors:
                try:
                    search_input = WebDriverWait(self.driver, 3).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                    )
                    search_input.clear()
                    search_input.send_keys(f"{area}, Bangalore {self.pincode}")
                    time.sleep(2)

                    # Click first suggestion
                    suggestion_selectors = [
                        "._11n32:nth-child(1)",
                        "[data-testid='address-suggestion']:first-child",
                        ".pac-item:first-child",
                        "[class*='suggestion']:first-child",
                        "[class*='LocationSuggestion']:first-child",
                    ]
                    for sug_sel in suggestion_selectors:
                        try:
                            suggestion = WebDriverWait(self.driver, 3).until(
                                EC.element_to_be_clickable((By.CSS_SELECTOR, sug_sel))
                            )
                            suggestion.click()
                            time.sleep(2)
                            break
                        except Exception:
                            continue

                    # Confirm location
                    confirm_selectors = [
                        "._2xPHa",
                        "button[class*='confirm']",
                        "[data-testid='confirm-location']",
                        "button[class*='Confirm']",
                    ]
                    for conf_sel in confirm_selectors:
                        try:
                            confirm_btn = WebDriverWait(self.driver, 3).until(
                                EC.element_to_be_clickable((By.CSS_SELECTOR, conf_sel))
                            )
                            confirm_btn.click()
                            time.sleep(2)
                            break
                        except Exception:
                            continue

                    break
                except Exception:
                    continue

        except Exception:
            pass  # Location via cookies will be used as fallback

    def _extract_api_responses(self) -> list[dict]:
        """Extract API responses from browser network performance logs."""
        responses = []
        try:
            logs = self.driver.get_log("performance")
            for log in logs:
                try:
                    message = json.loads(log["message"])["message"]
                    if message["method"] == "Network.responseReceived":
                        url = message["params"]["response"]["url"]
                        if any(k in url for k in ["instamart", "category", "search", "layout"]):
                            try:
                                request_id = message["params"]["requestId"]
                                body = self.driver.execute_cdp_cmd(
                                    "Network.getResponseBody",
                                    {"requestId": request_id}
                                )
                                if body.get("body"):
                                    data = json.loads(body["body"])
                                    responses.append({"url": url, "data": data})
                            except Exception:
                                pass
                except Exception:
                    continue
        except Exception:
            pass
        return responses

    def get_categories(self) -> list[dict]:
        """Get all product categories from the Instamart home page."""
        self._set_location()

        categories = []

        # Try extracting from intercepted API responses
        api_responses = self._extract_api_responses()
        for resp in api_responses:
            data = resp.get("data", {})
            if isinstance(data, dict) and "data" in data:
                widgets = data.get("data", {}).get("widgets", [])
                for widget in widgets:
                    if "category" in str(widget.get("widgetType", "")).lower():
                        items = widget.get("data", [])
                        for item in items:
                            cat = {
                                "name": item.get("displayName", item.get("name", "")),
                                "id": item.get("id", ""),
                                "url": item.get("deeplink", ""),
                            }
                            if cat["name"]:
                                categories.append(cat)

        # Fallback: Extract categories from the DOM
        if not categories:
            categories = self._extract_categories_from_dom()

        return categories

    def _extract_categories_from_dom(self) -> list[dict]:
        """Extract category links from the page DOM."""
        categories = []
        try:
            cat_selectors = [
                "a[href*='category-listing']",
                "a[href*='instamart'][href*='listing']",
                "[data-testid*='category']",
                "a[href*='categoryName']",
                "a[href*='/instamart/']",
            ]

            seen = set()
            for sel in cat_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, sel)
                    for elem in elements:
                        name = elem.text.strip()
                        href = elem.get_attribute("href") or ""
                        if (name and name not in seen
                                and 2 < len(name) < 50
                                and href
                                and "instamart" in href):
                            seen.add(name)
                            categories.append({"name": name, "url": href})
                except Exception:
                    continue
        except Exception as e:
            if self.debug:
                print(f"  Error extracting categories from DOM: {e}")

        return categories

    def search_products(self, query: str, max_scroll: int = 3) -> list[SwiggyProduct]:
        """
        Search for products on Swiggy Instamart.

        Args:
            query: Search query (e.g., "milk", "bread")
            max_scroll: Number of scroll iterations for loading more results

        Returns:
            List of SwiggyProduct objects
        """
        encoded_query = requests.utils.quote(query)
        search_url = f"{self.SEARCH_URL}?custom_back=true&query={encoded_query}"

        try:
            self.driver.get(search_url)
            time.sleep(3)

            # Wait for product cards to appear
            self._wait_for_products()

            # Scroll to load more products
            for i in range(max_scroll):
                self.driver.execute_script(
                    "window.scrollTo(0, document.body.scrollHeight);"
                )
                time.sleep(1.5)

            if self.debug:
                safe_name = query.replace(" ", "_")[:20]
                with open(f"debug_swiggy_search_{safe_name}.html", "w", encoding="utf-8") as f:
                    f.write(self.driver.page_source)

            # Extract products from DOM
            products = self._extract_products_from_dom(category=f"Search: {query}")

            # Try API response extraction if DOM extraction returned nothing
            if not products:
                products = self._extract_products_from_api(category=f"Search: {query}")

            # Final fallback: parse embedded JSON from page source
            if not products:
                products = self._extract_products_from_page_json(category=f"Search: {query}")

            return products

        except Exception as e:
            print(f"  Error searching for '{query}': {e}")
            return [SwiggyProduct(name=query, error=str(e))]

    def browse_category(self, category_url: str, category_name: str = "",
                        max_scroll: int = 5) -> list[SwiggyProduct]:
        """
        Browse products in a specific category.

        Args:
            category_url: Full URL of the category page
            category_name: Human-readable category name
            max_scroll: Number of scroll iterations

        Returns:
            List of SwiggyProduct objects
        """
        try:
            self.driver.get(category_url)
            time.sleep(3)

            self._wait_for_products()

            for _ in range(max_scroll):
                self.driver.execute_script(
                    "window.scrollTo(0, document.body.scrollHeight);"
                )
                time.sleep(1.5)

            if self.debug:
                safe_name = category_name.replace(" ", "_")[:20]
                with open(f"debug_swiggy_cat_{safe_name}.html", "w", encoding="utf-8") as f:
                    f.write(self.driver.page_source)

            products = self._extract_products_from_dom(category=category_name)

            if not products:
                products = self._extract_products_from_api(category=category_name)

            if not products:
                products = self._extract_products_from_page_json(category=category_name)

            return products

        except Exception as e:
            print(f"  Error browsing category '{category_name}': {e}")
            return []

    def _wait_for_products(self, timeout: int = 10):
        """Wait for product elements to load on the page."""
        product_selectors = [
            "[data-testid='default_container_ux4']",
            "[data-testid='item-name']",
            "[class*='ProductCard']",
            "[class*='product-info']",
            "._2MiLl",
        ]
        for sel in product_selectors:
            try:
                WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                )
                return
            except Exception:
                continue

        # Also check for loading indicators disappearing
        try:
            WebDriverWait(self.driver, 5).until_not(
                EC.presence_of_element_located((By.CSS_SELECTOR,
                    ".loading, .shimmer, .skeleton, [class*='loading']"))
            )
        except Exception:
            pass

    def _extract_products_from_dom(self, category: str = "") -> list[SwiggyProduct]:
        """Extract product data from the current page DOM."""
        products = []

        # Try multiple card selector strategies
        card_selectors = [
            "[data-testid='default_container_ux4']",
            "[data-testid='item-widget']",
            "[class*='ProductCard']",
            "[class*='product-card']",
            "._2MiLl",
        ]

        product_cards = []
        for sel in card_selectors:
            product_cards = self.driver.find_elements(By.CSS_SELECTOR, sel)
            if product_cards:
                break

        for card in product_cards:
            try:
                product = self._parse_product_card(card, category)
                if product and product.name:
                    products.append(product)
            except Exception as e:
                if self.debug:
                    print(f"    Error parsing card: {e}")
                continue

        return products

    def _parse_product_card(self, card, category: str = "") -> Optional[SwiggyProduct]:
        """Parse a single product card DOM element into a SwiggyProduct."""
        name = None
        price = None
        mrp = None
        discount = None
        quantity = None
        image_url = None
        available = True

        # Extract name
        name_selectors = [
            "[data-testid='item-name']",
            ".novMV",
            ".sc-aXZVg",
            "[class*='ProductName']",
            "[class*='product-name']",
            "[class*='itemName']",
            "div[class*='name']",
        ]
        for sel in name_selectors:
            try:
                elem = card.find_element(By.CSS_SELECTOR, sel)
                name = elem.text.strip()
                if name:
                    break
            except Exception:
                continue

        # Fallback: use first meaningful text line from card
        if not name:
            try:
                lines = card.text.strip().split("\n")
                for line in lines:
                    line = line.strip()
                    if (line and len(line) > 3
                            and not line.startswith("₹")
                            and not line.endswith("OFF")
                            and not line.endswith("mins")):
                        name = line
                        break
            except Exception:
                pass

        if not name:
            return None

        # Extract selling price
        price_selectors = [
            "[data-testid='item-offer-price']",
            "[class*='offer-price']",
            "[class*='selling-price']",
            "[class*='discountedPrice']",
        ]
        for sel in price_selectors:
            try:
                elem = card.find_element(By.CSS_SELECTOR, sel)
                price = self._parse_price_value(elem.text.strip())
                if price:
                    break
            except Exception:
                continue

        # Extract MRP (original price)
        mrp_selectors = [
            "[data-testid='item-mrp-price']",
            "[class*='mrp-price']",
            "[class*='original-price']",
            "[class*='strikePrice']",
            "s", "del",
        ]
        for sel in mrp_selectors:
            try:
                elem = card.find_element(By.CSS_SELECTOR, sel)
                mrp = self._parse_price_value(elem.text.strip())
                if mrp:
                    break
            except Exception:
                continue

        # Extract discount text
        discount_selectors = [
            "[data-testid='item-offer-label-discount-text']",
            "[class*='discount']",
            "[class*='Discount']",
            "[class*='offer-label']",
        ]
        for sel in discount_selectors:
            try:
                elem = card.find_element(By.CSS_SELECTOR, sel)
                text = elem.text.strip()
                if text and ("%" in text or "OFF" in text.upper()):
                    discount = text
                    break
            except Exception:
                continue

        # Check availability (look for sold-out indicators)
        try:
            card.find_element(By.CSS_SELECTOR,
                "[data-testid='sold-out'], [class*='sold-out'], [class*='OutOfStock']")
            available = False
        except Exception:
            available = True

        # Extract image URL
        try:
            img = card.find_element(By.CSS_SELECTOR, "img")
            image_url = img.get_attribute("src")
        except Exception:
            pass

        # Extract quantity / weight
        qty_selectors = [
            "[class*='quantity']",
            "[class*='weight']",
            "[class*='unit']",
            "[class*='variant']",
        ]
        for sel in qty_selectors:
            try:
                elem = card.find_element(By.CSS_SELECTOR, sel)
                text = elem.text.strip()
                if text and len(text) < 30:
                    quantity = text
                    break
            except Exception:
                continue

        # Try to extract quantity from name
        if not quantity and name:
            qty_match = re.search(
                r'(\d+(?:\.\d+)?\s*(?:g|kg|ml|l|L|pcs?|pack|units?|piece|no|nos))\b',
                name, re.IGNORECASE
            )
            if qty_match:
                quantity = qty_match.group(1)

        # Fallback: extract price from all card text
        if not price:
            try:
                card_text = card.text
                price_match = re.search(r'₹\s*(\d+(?:\.\d+)?)', card_text)
                if price_match:
                    price = float(price_match.group(1))
            except Exception:
                pass

        # Calculate discount if we have both price and MRP
        if not discount and price and mrp and mrp > price:
            pct = round((1 - price / mrp) * 100)
            discount = f"{pct}% OFF"

        return SwiggyProduct(
            name=name,
            price=price,
            mrp=mrp,
            discount=discount,
            quantity=quantity,
            category=category,
            available=available,
            image_url=image_url,
            delivery_time="10-15 mins",
        )

    def _extract_products_from_api(self, category: str = "") -> list[SwiggyProduct]:
        """Extract products from intercepted API responses in network logs."""
        products = []
        api_responses = self._extract_api_responses()
        for resp in api_responses:
            data = resp.get("data", {})
            products.extend(self._parse_json_products(data, category))
        return products

    def _extract_products_from_page_json(self, category: str = "") -> list[SwiggyProduct]:
        """Extract products from embedded JSON in page source (e.g., __NEXT_DATA__)."""
        products = []
        try:
            soup = BeautifulSoup(self.driver.page_source, "lxml")

            # Look for Next.js data
            next_data = soup.find("script", {"id": "__NEXT_DATA__"})
            if next_data and next_data.string:
                try:
                    data = json.loads(next_data.string)
                    products.extend(self._parse_json_products(data, category))
                except (json.JSONDecodeError, TypeError):
                    pass

            # Look for other JSON script tags
            for script in soup.find_all("script", {"type": "application/json"}):
                if script.string:
                    try:
                        data = json.loads(script.string)
                        products.extend(self._parse_json_products(data, category))
                    except (json.JSONDecodeError, TypeError):
                        continue

            # Look for window.__PRELOADED_STATE__ or similar global state
            for script in soup.find_all("script"):
                if script.string and "window.__" in (script.string or ""):
                    json_match = re.search(
                        r'window\.__\w+__\s*=\s*({.+?});?\s*(?:</script>|$)',
                        script.string, re.DOTALL
                    )
                    if json_match:
                        try:
                            data = json.loads(json_match.group(1))
                            products.extend(self._parse_json_products(data, category))
                        except (json.JSONDecodeError, TypeError):
                            continue

        except Exception as e:
            if self.debug:
                print(f"    Error extracting from page JSON: {e}")

        return products

    def _parse_json_products(self, data, category: str = "",
                             depth: int = 0) -> list[SwiggyProduct]:
        """Recursively parse JSON data to find product objects."""
        products = []

        if depth > 12:
            return products

        if isinstance(data, dict):
            # Check if this dict looks like a product
            name_keys = ["name", "display_name", "displayName", "productName", "title"]
            price_keys = ["price", "offer_price", "offerPrice", "selling_price",
                          "sellingPrice", "finalPrice"]

            has_name = any(k in data for k in name_keys)
            has_price = any(k in data for k in price_keys)

            if has_name and has_price:
                name = None
                for k in name_keys:
                    if data.get(k) and isinstance(data[k], str) and len(data[k]) > 2:
                        name = data[k]
                        break

                if name:
                    price = None
                    for k in price_keys:
                        try:
                            val = data.get(k)
                            if val is not None:
                                price = float(val)
                                if price > 0:
                                    break
                        except (ValueError, TypeError):
                            continue

                    mrp = None
                    for k in ["mrp", "marked_price", "markedPrice", "originalPrice", "maxPrice"]:
                        try:
                            val = data.get(k)
                            if val is not None:
                                mrp = float(val)
                                if mrp > 0:
                                    break
                        except (ValueError, TypeError):
                            continue

                    discount_text = data.get("discount") or data.get("offer_text") or data.get("offerText")
                    quantity_text = data.get("quantity") or data.get("weight") or data.get("unit")
                    brand_text = data.get("brand") or data.get("brandName") or data.get("brand_name")
                    avail = data.get("available", True) if "available" in data else True
                    if "in_stock" in data:
                        avail = data["in_stock"]
                    image = (data.get("image") or data.get("imageUrl")
                             or data.get("image_url") or data.get("product_image"))

                    # Calculate discount
                    if not discount_text and price and mrp and mrp > price:
                        pct = round((1 - price / mrp) * 100)
                        discount_text = f"{pct}% OFF"

                    product = SwiggyProduct(
                        name=str(name),
                        brand=str(brand_text) if brand_text else None,
                        price=price,
                        mrp=mrp,
                        discount=str(discount_text) if discount_text else None,
                        quantity=str(quantity_text) if quantity_text else None,
                        category=category,
                        available=bool(avail),
                        image_url=str(image) if image else None,
                        delivery_time="10-15 mins",
                    )
                    products.append(product)

            # Recurse into dict values
            for value in data.values():
                if isinstance(value, (dict, list)):
                    products.extend(self._parse_json_products(value, category, depth + 1))

        elif isinstance(data, list):
            for item in data:
                if isinstance(item, (dict, list)):
                    products.extend(self._parse_json_products(item, category, depth + 1))

        return products

    def _parse_price_value(self, price_text: str) -> Optional[float]:
        """Extract numeric price from a price string like '₹45' or 'Rs. 120.50'."""
        if not price_text:
            return None
        cleaned = re.sub(r'[^\d.]', '', price_text)
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None

    def scrape_all(self, search_terms: list = None,
                   max_products: int = 500) -> list[SwiggyProduct]:
        """
        Scrape products from Swiggy Instamart.

        If search_terms are provided, searches for each term.
        Otherwise, browses categories from the home page.
        Falls back to a default set of common grocery search terms
        if no categories can be discovered.

        Args:
            search_terms: List of search queries (e.g., ["milk", "bread"])
            max_products: Maximum number of products to collect

        Returns:
            Deduplicated list of SwiggyProduct objects
        """
        # Set location first
        self._set_location()

        all_products = []

        if search_terms:
            for term in search_terms:
                print(f"\n  Searching: {term}...")
                products = self.search_products(term)
                all_products.extend(products)
                print(f"    Found {len(products)} products")

                if len(all_products) >= max_products:
                    break

                time.sleep(random.uniform(2, 4))
        else:
            # Try browsing categories first
            categories = self.get_categories()
            if categories:
                print(f"\n  Found {len(categories)} categories")
                for cat in categories:
                    if len(all_products) >= max_products:
                        break

                    cat_name = cat.get("name", "Unknown")
                    cat_url = cat.get("url", "")

                    if cat_url:
                        print(f"\n  Browsing: {cat_name}...")
                        products = self.browse_category(cat_url, cat_name)
                        all_products.extend(products)
                        print(f"    Found {len(products)} products")
                        time.sleep(random.uniform(2, 4))
            else:
                # Fall back to common grocery search terms
                default_searches = [
                    "milk", "bread", "rice", "eggs", "fruits",
                    "vegetables", "snacks", "beverages", "dal",
                    "oil", "masala", "atta", "biscuits", "chips",
                    "sugar", "tea", "coffee", "paneer", "butter",
                    "cheese", "yogurt", "juice", "water", "soap",
                ]
                print("  No categories found, using default search terms...")
                for term in default_searches:
                    if len(all_products) >= max_products:
                        break
                    print(f"\n  Searching: {term}...")
                    products = self.search_products(term)
                    all_products.extend(products)
                    print(f"    Found {len(products)} products")
                    time.sleep(random.uniform(2, 4))

        # Deduplicate by (name, quantity, price)
        seen = set()
        unique_products = []
        for p in all_products:
            key = (p.name, p.quantity, p.price)
            if key not in seen:
                seen.add(key)
                unique_products.append(p)

        return unique_products

    def close(self):
        """Close the browser and clean up."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
