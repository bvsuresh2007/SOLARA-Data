"""
Swiggy Instamart Product Scraper — Playwright

Scrapes live price, MRP, discount and availability from Swiggy Instamart product pages.

Strategies (in order):
  1. Response interception — captures Swiggy's product API JSON responses
  2. JavaScript extraction — __NEXT_DATA__, JSON-LD, global state, proximity pricing
  3. DOM fallback          — meta tags and rendered price elements
"""

import json
import re
import time
from dataclasses import dataclass, field
from typing import Optional

from playwright.sync_api import sync_playwright, BrowserContext, Response


# ── Stealth ───────────────────────────────────────────────────────────────────
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

# ── Pincode → coordinates ─────────────────────────────────────────────────────
PINCODE_COORDS = {
    "560001": {"lat": 12.9716, "lng": 77.5946, "area": "Bangalore City"},
    "560103": {"lat": 12.9784, "lng": 77.6408, "area": "Whitefield, Bangalore"},
    "400001": {"lat": 18.9387, "lng": 72.8353, "area": "Fort, Mumbai"},
    "400093": {"lat": 19.1136, "lng": 72.8697, "area": "Powai, Mumbai"},
    "110001": {"lat": 28.6139, "lng": 77.2090, "area": "Connaught Place, Delhi"},
    "122009": {"lat": 28.4595, "lng": 77.0266, "area": "DLF Phase 3, Gurugram"},
    "411001": {"lat": 18.5204, "lng": 73.8567, "area": "Shivajinagar, Pune"},
    "600001": {"lat": 13.0827, "lng": 80.2707, "area": "Park Town, Chennai"},
    "700001": {"lat": 22.5726, "lng": 88.3639, "area": "BBD Bagh, Kolkata"},
}
_DEFAULT_PINCODE = "560103"

# Generic page/site names that are not product names
_BAD_NAMES = frozenset([
    "swiggy", "instamart", "order groceries online", "grocery delivery",
    "fast delivery", "quick commerce", "instamart - fast delivery",
    "shop groceries", "10 minute grocery", "home",
])


@dataclass
class SwiggyProductData:
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
    """
    Playwright-based Swiggy Instamart product price scraper.

    Each scrape() call uses a fresh isolated browser context.
    The browser process is shared — call close() when all scraping is done.
    """

    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )

    def __init__(
        self,
        pincode: str = _DEFAULT_PINCODE,
        debug: bool = False,
        headless: bool = True,
        proxy: Optional[str] = None,
    ):
        self.pincode = pincode
        self.debug = debug
        self.headless = headless
        self.proxy = proxy
        self._pw = None
        self._browser = None
        coords = PINCODE_COORDS.get(pincode, PINCODE_COORDS[_DEFAULT_PINCODE])
        self._lat = coords["lat"]
        self._lng = coords["lng"]
        self._area = coords["area"]

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
    def _extract_product_id(url: str) -> Optional[str]:
        m = re.search(r'/item/[^/]+/(\d+)', url)
        if m:
            return m.group(1)
        m = re.search(r'/(\d+)(?:\?|$)', url)
        return m.group(1) if m else None

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

    def _is_bad_name(self, name: str) -> bool:
        return not name or name.lower().strip() in _BAD_NAMES or len(name.strip()) < 3

    # ── Extraction helpers ────────────────────────────────────────────────────

    def _populate_from_dict(self, obj: dict, result: SwiggyProductData) -> bool:
        """Try to fill result from a dict. Returns True if a valid product name is found."""
        name = (
            obj.get("name") or obj.get("display_name") or obj.get("item_name")
            or obj.get("productName") or obj.get("product_name")
        )
        if not name or self._is_bad_name(str(name)):
            return False

        result.name = str(name)
        result.brand = obj.get("brand") or obj.get("brand_name") or obj.get("brandName")
        result.description = obj.get("description") or obj.get("long_description")
        result.category = (
            obj.get("category") or obj.get("category_name")
            or obj.get("super_category") or obj.get("categoryName")
        )
        result.quantity = (
            obj.get("quantity") or obj.get("unit") or obj.get("pack_size")
            or obj.get("product_unit") or obj.get("weight")
        )

        price = (
            obj.get("price") or obj.get("offer_price") or obj.get("selling_price")
            or obj.get("discounted_price") or obj.get("final_price")
        )
        mrp = (
            obj.get("mrp") or obj.get("max_retail_price") or obj.get("original_price")
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

        avail = obj.get("available") or obj.get("in_stock") or obj.get("is_available")
        if avail is not None:
            result.availability = "In Stock" if avail else "Out of Stock"

        if img := (obj.get("image_url") or obj.get("image") or obj.get("imageUrl")):
            result.image_url = str(img)

        if r := (obj.get("rating") or obj.get("average_rating")):
            result.rating = str(r)
        if rc := (obj.get("rating_count") or obj.get("ratingCount")):
            result.rating_count = str(rc)

        return True

    def _find_product_in_json(self, data, depth: int = 0) -> Optional[dict]:
        """Recursively find the first dict that looks like a product."""
        if depth > 8 or not data:
            return None
        if isinstance(data, dict):
            name = (
                data.get("name") or data.get("display_name")
                or data.get("item_name") or data.get("productName")
            )
            price = (
                data.get("price") or data.get("offer_price")
                or data.get("selling_price") or data.get("mrp")
            )
            if name and price and not self._is_bad_name(str(name)):
                return data
            for key in ("product", "item", "data", "result", "items", "products", "payload"):
                sub = data.get(key)
                if sub:
                    if isinstance(sub, list) and sub:
                        sub = sub[0]
                    if isinstance(sub, dict):
                        r = self._find_product_in_json(sub, depth + 1)
                        if r:
                            return r
            for val in data.values():
                if isinstance(val, (dict, list)):
                    r = self._find_product_in_json(val, depth + 1)
                    if r:
                        return r
        elif isinstance(data, list):
            for item in data[:10]:
                if isinstance(item, dict):
                    r = self._find_product_in_json(item, depth + 1)
                    if r:
                        return r
        return None

    def _extract_via_js(self, page, result: SwiggyProductData) -> bool:
        """
        Multi-strategy JavaScript extraction.
        Reads __NEXT_DATA__, JSON-LD, window globals, and DOM proximity pricing.
        Returns True if a product name was found.
        """
        try:
            data = page.evaluate(r"""() => {
                const out = {};

                // 1. __NEXT_DATA__
                const nd = document.getElementById('__NEXT_DATA__');
                if (nd) {
                    try { out.__next_data = JSON.parse(nd.textContent); } catch(e) {}
                }

                // 2. JSON-LD Product schema
                for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
                    try {
                        const d = JSON.parse(s.textContent);
                        const items = Array.isArray(d) ? d : [d];
                        for (const item of items) {
                            if (item && item['@type'] === 'Product') {
                                out.json_ld = item;
                                break;
                            }
                        }
                    } catch(e) {}
                    if (out.json_ld) break;
                }

                // 3. Window global state objects
                for (const key of ['__INITIAL_STATE__', '__PRELOADED_STATE__', '__APP_DATA__']) {
                    if (window[key]) {
                        try { out['global_' + key] = window[key]; } catch(e) {}
                    }
                }

                // 4. h1 text — likely product name
                const h1 = document.querySelector('h1');
                out.h1 = h1 ? h1.textContent.trim() : '';

                // 5. All ₹ prices visible on the page
                const bodyText = document.body ? document.body.innerText : '';
                out.all_prices = [...bodyText.matchAll(/₹\s?([\d,]+(?:\.\d{1,2})?)/g)]
                    .map(m => parseFloat(m[1].replace(/,/g, '')))
                    .filter(v => v > 0 && v < 200000);

                // 6. Prices appearing near the h1 (product price is close after product name)
                out.nearby_prices = [];
                if (h1 && bodyText) {
                    const h1Text = h1.textContent.trim();
                    const h1Pos = bodyText.indexOf(h1Text.substring(0, 30));
                    if (h1Pos >= 0) {
                        const after = bodyText.substring(
                            h1Pos + h1Text.length,
                            h1Pos + h1Text.length + 500
                        );
                        const matches = [...after.matchAll(/₹\s?([\d,]+(?:\.\d{1,2})?)/g)]
                            .map(m => parseFloat(m[1].replace(/,/g, '')))
                            .filter(v => v > 0 && v < 200000);
                        // deduplicate
                        out.nearby_prices = matches.filter((v, i, a) => a.indexOf(v) === i).slice(0, 4);
                    }
                }

                // 7. Strikethrough/line-through prices → these are MRP
                out.strikethrough_prices = [];
                const stSelectors = [
                    'del', 's',
                    '[style*="line-through"]',
                    '[class*="strikethrough"]',
                    '[class*="strike"]',
                    '[class*="mrp"]',
                    '[class*="original"]',
                ];
                for (const sel of stSelectors) {
                    for (const el of document.querySelectorAll(sel)) {
                        const txt = el.textContent.trim();
                        const m = txt.match(/₹\s?([\d,]+(?:\.\d{1,2})?)/);
                        if (m) {
                            const v = parseFloat(m[1].replace(/,/g, ''));
                            if (v > 0) out.strikethrough_prices.push(v);
                        }
                    }
                }

                // 8. Discount text (e.g. "20% off")
                const discMatch = bodyText.match(/(\d+)\s*%\s*(?:off|OFF)/);
                out.discount_text = discMatch ? discMatch[1] + '% off' : '';

                // 9. Out of stock signal
                out.out_of_stock = /out.of.stock|notify.me|coming.soon/i.test(bodyText);

                // 10. og:image
                out.og_image = document.querySelector('meta[property="og:image"]')?.content || '';

                return out;
            }""")
        except Exception as e:
            print(f"  JS evaluation error: {e}")
            return False

        if not data:
            return False

        found_name = False

        # Try __NEXT_DATA__
        nd = data.get("__next_data")
        if nd:
            props = (nd.get("props") or {}).get("pageProps") or {}
            prod = self._find_product_in_json(props)
            if prod and self._populate_from_dict(prod, result):
                print("  [Source: __NEXT_DATA__]")
                found_name = True

        # Try JSON-LD
        if not result.name:
            ld = data.get("json_ld")
            if ld and ld.get("name"):
                result.name = ld["name"]
                result.description = ld.get("description")
                brand = ld.get("brand")
                result.brand = brand.get("name") if isinstance(brand, dict) else brand
                img = ld.get("image")
                if not result.image_url:
                    result.image_url = img[0] if isinstance(img, list) and img else img
                offers = ld.get("offers") or {}
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}
                if p := offers.get("price"):
                    result.price_value = self._parse_price(p)
                    if result.price_value:
                        result.price = self._fmt(result.price_value)
                if hp := offers.get("highPrice"):
                    result.mrp_value = self._parse_price(hp)
                    if result.mrp_value:
                        result.mrp = self._fmt(result.mrp_value)
                avail = offers.get("availability", "")
                if "InStock" in avail:
                    result.availability = "In Stock"
                elif "OutOfStock" in avail:
                    result.availability = "Out of Stock"
                print("  [Source: JSON-LD]")
                found_name = True

        # Try window globals
        if not result.name:
            for key in ("global___INITIAL_STATE__", "global___PRELOADED_STATE__", "global___APP_DATA__"):
                g = data.get(key)
                if g:
                    prod = self._find_product_in_json(g)
                    if prod and self._populate_from_dict(prod, result):
                        print(f"  [Source: window.{key.replace('global_', '')}]")
                        found_name = True
                        break

        # Use h1 as product name of last resort
        if not result.name:
            h1 = data.get("h1", "")
            if h1 and not self._is_bad_name(h1):
                result.name = h1
                print("  [Source: h1]")
                found_name = True

        # Set price/MRP from proximity/strikethrough data
        strikethrough = data.get("strikethrough_prices") or []
        if result.name and not result.price:
            prices = data.get("nearby_prices") or data.get("all_prices") or []
            if prices:
                result.price_value = prices[0]
                result.price = self._fmt(prices[0])
                # MRP: prefer strikethrough price, else second distinct price
                if strikethrough and strikethrough[0] > prices[0]:
                    result.mrp_value = strikethrough[0]
                    result.mrp = self._fmt(strikethrough[0])
                elif len(prices) > 1 and prices[1] > prices[0]:
                    result.mrp_value = prices[1]
                    result.mrp = self._fmt(prices[1])
        # If we have price but no MRP, try strikethrough prices
        if result.price_value and not result.mrp_value and strikethrough:
            candidate = max(strikethrough)
            if candidate > result.price_value:
                result.mrp_value = candidate
                result.mrp = self._fmt(candidate)

        # Compute discount if we have both prices
        if result.price_value and result.mrp_value and result.mrp_value > result.price_value:
            if not result.discount:
                pct = (result.mrp_value - result.price_value) / result.mrp_value * 100
                result.discount = f"{pct:.0f}% off"
        elif not result.discount and data.get("discount_text"):
            result.discount = data["discount_text"]

        if not result.availability:
            result.availability = "Out of Stock" if data.get("out_of_stock") else "In Stock"

        if not result.image_url and data.get("og_image"):
            result.image_url = data["og_image"]

        return found_name

    # ── Public scrape ─────────────────────────────────────────────────────────

    def scrape(self, url: str) -> SwiggyProductData:
        """
        Scrape a Swiggy Instamart product page.

        Args:
            url: Full Swiggy Instamart product URL

        Returns:
            SwiggyProductData with all available fields populated
        """
        result = SwiggyProductData(url=url)
        result.product_id = self._extract_product_id(url)

        if not self._browser:
            self._launch()

        captured: list[dict] = []
        proxy_cfg = {"server": self.proxy} if self.proxy else None

        ctx: BrowserContext = self._browser.new_context(
            user_agent=self._UA,
            viewport={"width": 1920, "height": 1080},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            **({"proxy": proxy_cfg} if proxy_cfg else {}),
        )

        try:
            page = ctx.new_page()
            page.set_default_timeout(30_000)
            page.add_init_script(_STEALTH)

            # Inject location before page JS runs (localStorage)
            loc_json = json.dumps({"lat": self._lat, "lng": self._lng, "address": self._area})
            page.add_init_script(f"""
                try {{
                    localStorage.setItem('userLocation', '{loc_json}');
                    localStorage.setItem('swiggyLat', '{self._lat}');
                    localStorage.setItem('swiggyLng', '{self._lng}');
                }} catch(e) {{}}
            """)

            # Set location cookies (Playwright context.add_cookies works before navigation)
            ctx.add_cookies([
                {"name": "userLocation", "value": loc_json,
                 "domain": ".swiggy.com", "path": "/"},
            ])

            # Response interception: capture product API responses
            def on_response(resp: Response):
                if "json" not in resp.headers.get("content-type", ""):
                    return
                u = resp.url
                if not any(k in u for k in [
                    "instamart", "item-detail", "item_detail",
                    "product", "catalog", "dapi.swiggy", "api.swiggy",
                ]):
                    return
                try:
                    body = resp.json()
                    prod = self._find_product_in_json(body)
                    if prod:
                        captured.append(prod)
                except Exception:
                    pass

            page.on("response", on_response)

            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(3_000)
            page.evaluate("window.scrollTo(0, 400)")
            page.wait_for_timeout(1_500)

            if self.debug:
                fname = f"debug_swiggy_{result.product_id or 'page'}.html"
                with open(fname, "w", encoding="utf-8") as f:
                    f.write(page.content())
                print(f"  Debug HTML → {fname}")

            # Strategy 1: captured API responses
            if captured:
                if self._populate_from_dict(captured[0], result):
                    print("  [Source: API response]")

            # Strategy 2: JS-based extraction (__NEXT_DATA__, JSON-LD, proximity pricing)
            if not result.name:
                self._extract_via_js(page, result)

            # Check for error page if still nothing
            if not result.name and not result.price:
                try:
                    body_text = page.locator("body").text_content(timeout=5_000) or ""
                    if any(p in body_text.lower() for p in [
                        "too many requests", "something went wrong", "access denied",
                    ]):
                        result.error = "Rate limited or access denied"
                    else:
                        result.error = "Could not extract product data"
                except Exception:
                    result.error = "Could not extract product data"

        except Exception as e:
            result.error = str(e)
        finally:
            ctx.close()

        return result

    def scrape_multiple(self, urls: list[str], delay: float = 25.0) -> list[SwiggyProductData]:
        results = []
        for i, url in enumerate(urls, 1):
            print(f"\n[{i}/{len(urls)}] Scraping: {url[:80]}...")
            results.append(self.scrape(url))
            if i < len(urls):
                time.sleep(delay)
        return results
