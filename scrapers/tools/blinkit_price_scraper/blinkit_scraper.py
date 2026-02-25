"""
Blinkit Product Price Scraper — Playwright

Scrapes live price, MRP, discount and stock status from Blinkit product pages.

Strategies (in order):
  1. Response interception — captures Blinkit's XHR/fetch product API responses
  2. __NEXT_DATA__         — extracts from the embedded Next.js page data
  3. DOM                   — reads rendered price/title elements
"""

import json
import re
import time
from dataclasses import dataclass
from typing import Optional

from playwright.sync_api import sync_playwright, BrowserContext, Response


# ── Stealth: injected before any page JS runs ─────────────────────────────────
_STEALTH = """
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
    Object.defineProperty(navigator, 'languages', {get: () => ['en-IN','en-US','en']});
    window.chrome = {runtime: {}};
    const origQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = p =>
        p.name === 'notifications'
            ? Promise.resolve({state: Notification.permission})
            : origQuery(p);
"""

# ── Known pincode → coordinates mapping ──────────────────────────────────────
_PINCODE_COORDS = {
    "122009": {"lat": "28.4595", "lon": "77.0266", "city": "Gurugram"},
    "110001": {"lat": "28.6139", "lon": "77.2090", "city": "New Delhi"},
    "400001": {"lat": "18.9387", "lon": "72.8353", "city": "Mumbai"},
    "560001": {"lat": "12.9716", "lon": "77.5946", "city": "Bengaluru"},
    "560103": {"lat": "12.9784", "lon": "77.6408", "city": "Whitefield"},
    "411001": {"lat": "18.5204", "lon": "73.8567", "city": "Pune"},
    "600001": {"lat": "13.0827", "lon": "80.2707", "city": "Chennai"},
    "700001": {"lat": "22.5726", "lon": "88.3639", "city": "Kolkata"},
}
_DEFAULT_COORDS = _PINCODE_COORDS["122009"]


@dataclass
class BlinkitProductData:
    product_id: str
    url: str
    title: Optional[str] = None
    price: Optional[str] = None
    price_value: Optional[float] = None
    mrp: Optional[str] = None
    mrp_value: Optional[float] = None
    discount: Optional[str] = None
    quantity: Optional[str] = None
    brand: Optional[str] = None
    in_stock: bool = False
    error: Optional[str] = None


class BlinkitScraper:
    """
    Playwright-based Blinkit product price scraper.

    One browser process is shared across scrape() calls; each call
    uses a fresh isolated browser context. Call close() when done.
    """

    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )

    # Known non-product "name" values that appear in Blinkit API metadata
    _BAD_NAMES = frozenset({
        "product_page", "home_page", "listing_page", "category_page",
        "pdp_layout_v2", "pdp_layout_v1", "cart", "checkout",
        "search_page", "store_page",
    })

    def __init__(self, pincode: str = "122009", debug: bool = False, headless: bool = True):
        self.pincode = pincode
        self.debug = debug
        self.headless = headless
        self._pw = None
        self._browser = None
        coords = _PINCODE_COORDS.get(pincode, _DEFAULT_COORDS)
        self._lat = coords["lat"]
        self._lon = coords["lon"]

    # ── Browser lifecycle ─────────────────────────────────────────────────────

    def _launch(self):
        self._pw = sync_playwright().__enter__()
        self._browser = self._pw.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )

    def close(self):
        try:
            self._browser.close()
        except Exception:
            pass
        try:
            self._pw.__exit__(None, None, None)
        except Exception:
            pass
        self._pw = self._browser = None

    # ── Utility helpers ───────────────────────────────────────────────────────

    @staticmethod
    def extract_product_id(entry: str) -> str:
        """Extract numeric product ID from a Blinkit URL or return entry as-is."""
        m = re.search(r'/prid/(\d+)', entry)
        return m.group(1) if m else entry.strip()

    @staticmethod
    def _parse_price(val) -> Optional[float]:
        if val is None:
            return None
        try:
            return float(str(val).replace(",", "").replace("₹", "").strip())
        except ValueError:
            return None

    @staticmethod
    def _fmt(val: float) -> str:
        return f"₹{val:,.0f}"

    # ── Extraction helpers ────────────────────────────────────────────────────

    def _populate_from_dict(self, obj: dict, result: BlinkitProductData) -> bool:
        """Try to fill result fields from a single dict. Returns True if name found."""
        name = (
            obj.get("name") or obj.get("product_name") or obj.get("item_name")
            or obj.get("display_name")
        )
        if not name:
            return False
        # Skip known page-type identifiers — not real product names
        if str(name).lower() in self._BAD_NAMES:
            return False

        result.title = str(name)
        result.brand = obj.get("brand") or obj.get("brand_name")
        result.quantity = (
            obj.get("unit") or obj.get("quantity") or obj.get("pack_size")
            or obj.get("product_unit") or obj.get("unit_quantity")
        )

        price = (
            obj.get("price") or obj.get("offer_price") or obj.get("selling_price")
            or obj.get("discounted_price") or obj.get("final_price")
        )
        mrp = (
            obj.get("mrp") or obj.get("max_retail_price") or obj.get("original_price")
            or obj.get("base_price")
        )

        if price:
            result.price_value = self._parse_price(price)
            if result.price_value:
                result.price = self._fmt(result.price_value)

        if mrp:
            result.mrp_value = self._parse_price(mrp)
            if result.mrp_value:
                result.mrp = self._fmt(result.mrp_value)

        if result.price_value and result.mrp_value and result.mrp_value > result.price_value:
            pct = (result.mrp_value - result.price_value) / result.mrp_value * 100
            result.discount = f"{pct:.0f}% off"
        elif d := (obj.get("discount") or obj.get("discount_percentage")):
            result.discount = f"{d}%"

        avail = obj.get("is_available") or obj.get("in_stock") or obj.get("available")
        if avail is not None:
            result.in_stock = bool(avail)
        elif result.price_value:
            # If we have a price but no explicit availability field, assume in stock
            result.in_stock = True

        return True

    def _search_json(self, data, result: BlinkitProductData, depth: int = 0) -> bool:
        """Recursively search any JSON structure for product data."""
        if depth > 8 or not data:
            return False
        if isinstance(data, dict):
            if self._populate_from_dict(data, result):
                return True
            for key in ("product", "products", "item", "items", "data", "result", "payload"):
                sub = data.get(key)
                if sub:
                    if isinstance(sub, list) and sub:
                        sub = sub[0]
                    if isinstance(sub, dict) and self._search_json(sub, result, depth + 1):
                        return True
            for val in data.values():
                if isinstance(val, dict) and self._search_json(val, result, depth + 1):
                    return True
        elif isinstance(data, list):
            for item in data[:5]:
                if isinstance(item, dict) and self._search_json(item, result, depth + 1):
                    return True
        return False

    def _extract_next_data(self, page, result: BlinkitProductData) -> bool:
        try:
            data = page.evaluate("""() => {
                const el = document.getElementById('__NEXT_DATA__');
                if (!el) return null;
                try { return JSON.parse(el.textContent); } catch(e) { return null; }
            }""")
            if data:
                props = (data.get("props") or {}).get("pageProps") or {}
                return self._search_json(props, result)
        except Exception:
            pass
        return False

    def _extract_dom(self, page, result: BlinkitProductData) -> bool:
        try:
            data = page.evaluate(r"""() => {
                const get = s => document.querySelector(s)?.textContent?.trim() || '';
                const name = get('h1') || get('[class*="ProductName"]') || get('[class*="product-name"]')
                           || get('[class*="productName"]');
                const body = document.body?.innerText || '';
                const prices = [...body.matchAll(/₹\s?([\d,]+(?:\.\d{1,2})?)/g)]
                    .map(m => parseFloat(m[1].replace(/,/g, '')))
                    .filter(v => v > 0 && v < 100000);
                const outOfStock = /out.of.stock|notify.me/i.test(body);
                return { name, prices, in_stock: !outOfStock };
            }""")
            if data.get("name") and len(data["name"]) > 2:
                result.title = data["name"]
            prices = data.get("prices") or []
            if prices:
                result.price_value = prices[0]
                result.price = self._fmt(prices[0])
                if len(prices) > 1 and prices[1] > prices[0]:
                    result.mrp_value = prices[1]
                    result.mrp = self._fmt(prices[1])
                    pct = (prices[1] - prices[0]) / prices[1] * 100
                    result.discount = f"{pct:.0f}% off"
            result.in_stock = data.get("in_stock", False)
            return bool(result.title)
        except Exception:
            pass
        return False

    # ── Public scrape ─────────────────────────────────────────────────────────

    def scrape(self, entry: str) -> BlinkitProductData:
        """
        Scrape a Blinkit product by ID or URL.

        Args:
            entry: Product ID (e.g. "627046") or full Blinkit URL

        Returns:
            BlinkitProductData with all available fields populated
        """
        pid = self.extract_product_id(entry)
        url = f"https://blinkit.com/prn/-/prid/{pid}"
        result = BlinkitProductData(product_id=pid, url=url)

        if not self._browser:
            self._launch()

        captured: list[dict] = []

        ctx: BrowserContext = self._browser.new_context(
            user_agent=self._UA,
            viewport={"width": 1920, "height": 1080},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            extra_http_headers={
                "lat": self._lat,
                "lon": self._lon,
                "app_client": "CONSUMER_WEB",
            },
        )

        try:
            page = ctx.new_page()
            page.set_default_timeout(30_000)
            page.add_init_script(_STEALTH)

            # Response listener: capture product API responses
            def on_response(response: Response):
                if "json" not in response.headers.get("content-type", ""):
                    return
                u = response.url
                if not any(k in u for k in [
                    "v2/product", "v1/product", "/product/", "/prid/",
                    "item_detail", "product_detail", "listing", "catalog",
                ]):
                    return
                try:
                    captured.append(response.json())
                except Exception:
                    pass

            page.on("response", on_response)

            # Set location cookies before navigation
            ctx.add_cookies([{
                "name": "userLocation",
                "value": json.dumps({
                    "lat": float(self._lat),
                    "lng": float(self._lon),
                    "address": {"postcode": self.pincode},
                }),
                "domain": ".blinkit.com",
                "path": "/",
            }])

            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(3_000)

            if self.debug:
                fname = f"debug_blinkit_{pid}.html"
                with open(fname, "w", encoding="utf-8") as f:
                    f.write(page.content())
                print(f"  Debug HTML → {fname}")

            # Strategy 1: API response interception
            for body in captured:
                if self._search_json(body, result):
                    print("  [Source: API response]")
                    break

            # Strategy 2: __NEXT_DATA__
            if not result.title:
                if self._extract_next_data(page, result):
                    print("  [Source: __NEXT_DATA__]")

            # Strategy 3: DOM
            if not result.title:
                if self._extract_dom(page, result):
                    print("  [Source: DOM]")

            if not result.title and not result.price:
                result.error = "Could not extract product data"

        except Exception as e:
            result.error = str(e)
        finally:
            ctx.close()

        return result

    def scrape_multiple(self, entries: list[str], delay: float = 3.0) -> list[BlinkitProductData]:
        results = []
        for i, entry in enumerate(entries, 1):
            print(f"\n[{i}/{len(entries)}] Scraping: {entry[:80]}...")
            results.append(self.scrape(entry))
            if i < len(entries):
                time.sleep(delay)
        return results
