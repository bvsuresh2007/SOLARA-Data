"""
Zepto Product Price Scraper — Playwright

Scrapes live price, MRP, discount and availability from Zepto product pages.

Strategies (in order):
  1. API response interception — Zepto BFF product endpoints (when available)
  2. Meta tags + og:title      — SSR metadata (reliable for name, price, rating)
  3. DOM                       — rendered H1, price elements, body text
"""

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
_PINCODE_COORDS = {
    "400001": {"lat": "18.9387", "lng": "72.8353"},
    "400093": {"lat": "19.1136", "lng": "72.8697"},
    "560001": {"lat": "12.9716", "lng": "77.5946"},
    "560103": {"lat": "12.9784", "lng": "77.6408"},
    "110001": {"lat": "28.6139", "lng": "77.2090"},
    "122009": {"lat": "28.4595", "lng": "77.0266"},
    "411001": {"lat": "18.5204", "lng": "73.8567"},
    "600001": {"lat": "13.0827", "lng": "80.2707"},
    "700001": {"lat": "22.5726", "lng": "88.3639"},
}
_DEFAULT_COORDS = _PINCODE_COORDS["400093"]  # Mumbai


@dataclass
class ZeptoProductData:
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
    """
    Playwright-based Zepto product price scraper.

    One browser process is shared across scrape() calls; each call
    uses a fresh isolated browser context. Call close() when done.
    """

    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )

    # File-like names that are obviously not product names
    _BAD_NAME_PATTERNS = re.compile(
        r'\.(svg|png|jpg|jpeg|webp|gif|ico|woff|ttf)$'
        r'|^https?://'
        r'|^[a-z0-9-]+\.(js|css|json)$',
        re.IGNORECASE,
    )

    def __init__(self, pincode: Optional[str] = None, debug: bool = False, headless: bool = True):
        self.pincode = pincode
        self.debug = debug
        self.headless = headless
        self._pw = None
        self._browser = None
        coords = _PINCODE_COORDS.get(pincode or "", _DEFAULT_COORDS)
        self._lat = coords["lat"]
        self._lng = coords["lng"]

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
        m = re.search(r'/pvid/([a-f0-9-]+)', url)
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

    def _calc_discount(self, result: ZeptoProductData):
        if (not result.discount and result.price_value
                and result.mrp_value and result.mrp_value > result.price_value):
            pct = (result.mrp_value - result.price_value) / result.mrp_value * 100
            result.discount = f"{pct:.0f}% off"

    # ── Extraction helpers ────────────────────────────────────────────────────

    def _is_bad_name(self, name: str) -> bool:
        """Return True if the name looks like a file/asset path, not a product name."""
        return bool(self._BAD_NAME_PATTERNS.search(name)) or len(name.strip()) < 3

    def _populate_from_dict(self, obj: dict, result: ZeptoProductData) -> bool:
        """Try to fill result from a single dict. Returns True if valid data found."""
        name = (
            obj.get("name") or obj.get("product_name") or obj.get("itemName")
            or obj.get("productName") or obj.get("displayName")
        )
        price = (
            obj.get("sellingPrice") or obj.get("price") or obj.get("salePrice")
            or obj.get("selling_price") or obj.get("offerPrice") or obj.get("offer_price")
        )
        if not name and not price:
            return False

        # Reject file/asset names
        if name and self._is_bad_name(str(name)):
            return False

        # Must have at least a price to be considered a valid product dict
        if not price:
            return False

        if name:
            result.name = str(name)
        result.brand = obj.get("brand") or obj.get("brandName") or obj.get("brand_name")
        result.description = obj.get("description")
        result.category = obj.get("category") or obj.get("categoryName") or obj.get("category_name")
        result.quantity = (
            obj.get("quantity") or obj.get("packSize") or obj.get("unit")
            or obj.get("pack_size") or obj.get("weight")
        )

        result.price_value = self._parse_price(price)
        if result.price_value:
            result.price = self._fmt(result.price_value)

        mrp = (
            obj.get("mrp") or obj.get("maxRetailPrice") or obj.get("originalPrice")
            or obj.get("max_retail_price") or obj.get("original_price")
        )
        if mrp:
            result.mrp_value = self._parse_price(mrp)
            if result.mrp_value:
                result.mrp = self._fmt(result.mrp_value)

        discount = obj.get("discount") or obj.get("discountPercent") or obj.get("discount_percentage")
        if discount:
            result.discount = f"{discount}%"
        self._calc_discount(result)

        images = obj.get("images") or obj.get("imageUrls") or []
        if images and isinstance(images, list):
            first = images[0]
            result.image_url = first if isinstance(first, str) else (first or {}).get("url")
        result.image_url = result.image_url or obj.get("image") or obj.get("imageUrl")

        avail = obj.get("availability") or obj.get("isAvailable") or obj.get("is_available")
        if avail is not None:
            result.availability = "In Stock" if avail else "Out of Stock"
        elif result.price_value:
            result.availability = "In Stock"

        if r := (obj.get("rating") or obj.get("averageRating") or obj.get("average_rating")):
            result.rating = str(r)
        if rc := (obj.get("ratingCount") or obj.get("reviewCount") or obj.get("rating_count")):
            result.rating_count = str(rc)

        return bool(result.name or result.price)

    def _search_json(self, data, result: ZeptoProductData, depth: int = 0) -> bool:
        """Recursively search any JSON structure for product data."""
        if depth > 8 or not data:
            return False
        if isinstance(data, dict):
            if self._populate_from_dict(data, result):
                return True
            for key in ("product", "productData", "data", "item", "detail", "result", "payload"):
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

    def _extract_meta(self, page, result: ZeptoProductData) -> bool:
        """Extract from meta tags and og:title — reliable for Zepto's SSR content."""
        try:
            data = page.evaluate("""() => {
                const meta = (name) =>
                    document.querySelector(`meta[name="${name}"]`)?.content ||
                    document.querySelector(`meta[property="${name}"]`)?.content ||
                    document.querySelector(`meta[itemprop="${name}"]`)?.content || '';

                const h1 = document.querySelector('h1')?.textContent?.trim() || '';
                const ogTitle = meta('og:title');
                const description = meta('description');
                const image = meta('og:image');
                const ratingValue = meta('ratingValue');
                const reviewCount = meta('reviewCount');
                const pageTitle = document.title || '';

                // Brand: Zepto has 2x meta[itemprop="name"] — first is product, second is brand.
                // The shorter value is the brand.
                const nameMetas = [...document.querySelectorAll("meta[itemprop='name']")]
                    .map(m => m.content).filter(Boolean).sort((a, b) => a.length - b.length);
                const brand = nameMetas.length > 1 ? nameMetas[0] : '';

                return { h1, ogTitle, description, image, ratingValue, reviewCount, brand, pageTitle };
            }""")

            # Product name: prefer H1, fall back to cleaned og:title
            name = data.get("h1") or ""
            if not name:
                og = data.get("ogTitle", "")
                name = re.sub(r"^Buy\s+", "", og, flags=re.IGNORECASE)
                name = re.sub(r"\s+Online\s*[-–].*$", "", name, flags=re.IGNORECASE)
                name = re.sub(r"\s*\|.*$", "", name).strip()

            if name and len(name) > 3:
                result.name = name

            # Price: parse from og:title  ("... Price @ ₹3499 ...")
            # or from page title
            for src in [data.get("ogTitle", ""), data.get("pageTitle", "")]:
                m = re.search(r"₹\s*([\d,]+)", src)
                if m:
                    val = float(m.group(1).replace(",", ""))
                    if val > 10:  # sanity check
                        result.price_value = val
                        result.price = self._fmt(val)
                        break

            # Brand from itemprop:name meta (e.g. "Solara Appliances")
            brand = data.get("brand", "")
            if brand and brand.lower() not in ("zepto", ""):
                result.brand = brand

            # Image
            if data.get("image") and not result.image_url:
                result.image_url = data["image"]

            # Rating + review count
            if data.get("ratingValue"):
                result.rating = str(data["ratingValue"])
            if data.get("reviewCount"):
                result.rating_count = str(data["reviewCount"])

            if result.name:
                if result.price_value:
                    result.availability = "In Stock"
                return True

        except Exception:
            pass
        return False

    def _extract_dom(self, page, result: ZeptoProductData) -> bool:
        """DOM fallback: reads rendered price elements."""
        try:
            data = page.evaluate(r"""() => {
                const get = s => document.querySelector(s)?.textContent?.trim() || '';
                const name = get('h1')
                    || get("[data-testid='product-title']")
                    || get("[data-testid='pdp-product-name']")
                    || get("[class*='product-title']")
                    || get("[class*='productTitle']");

                // Collect prices from elements that look like product prices
                // (avoid tiny values like ratings/specs)
                const priceEls = [];
                for (const el of document.querySelectorAll('span, div, p')) {
                    const t = el.textContent?.trim() || '';
                    const m = t.match(/^₹\s*([\d,]{3,}(?:\.\d{1,2})?)$/);
                    if (m) priceEls.push(parseFloat(m[1].replace(/,/g, '')));
                }
                const prices = [...new Set(priceEls)].sort((a, b) => a - b);

                const avail = /out.of.stock|coming.soon|notify.me/i.test(document.body?.innerText || '')
                    ? 'Out of Stock' : 'In Stock';
                return { name, prices, availability: avail };
            }""")

            if data.get("name") and len(data["name"]) > 2 and not result.name:
                result.name = data["name"]
            prices = data.get("prices") or []
            if prices and not result.price:
                result.price_value = prices[0]
                result.price = self._fmt(prices[0])
                if len(prices) > 1 and prices[1] > prices[0]:
                    result.mrp_value = prices[1]
                    result.mrp = self._fmt(prices[1])
                    self._calc_discount(result)
            if not result.availability:
                result.availability = data.get("availability")
            return bool(result.name)
        except Exception:
            pass
        return False

    # ── Public scrape ─────────────────────────────────────────────────────────

    def scrape(self, url: str) -> ZeptoProductData:
        """
        Scrape a Zepto product page.

        Args:
            url: Full Zepto product URL (must include /pvid/UUID)

        Returns:
            ZeptoProductData with all available fields populated
        """
        result = ZeptoProductData(url=url)
        result.product_id = self._extract_product_id(url)

        if not self._browser:
            self._launch()

        captured: list[dict] = []

        ctx: BrowserContext = self._browser.new_context(
            user_agent=self._UA,
            viewport={"width": 1440, "height": 900},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
        )

        try:
            page = ctx.new_page()
            page.set_default_timeout(30_000)
            page.add_init_script(_STEALTH)

            # Inject location into localStorage before page JS runs
            if self.pincode:
                page.add_init_script(f"""
                    try {{
                        localStorage.setItem('userLatLng',
                            JSON.stringify({{lat: {self._lat}, lng: {self._lng}}}));
                        localStorage.setItem('pincode', '{self.pincode}');
                        localStorage.setItem('userPincode', '{self.pincode}');
                        localStorage.setItem('deliveryPincode', '{self.pincode}');
                    }} catch(e) {{}}
                """)

            # Response interception — only capture specific product endpoints
            def on_response(resp: Response):
                if "json" not in resp.headers.get("content-type", ""):
                    return
                u = resp.url
                # Only capture product-specific API calls (pvid or known product patterns)
                if not any(k in u for k in ["pvid", "product_variant", "/product/detail", "/pdp/"]):
                    return
                try:
                    body = resp.json()
                    captured.append(body)
                except Exception:
                    pass

            page.on("response", on_response)

            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(3_000)

            if self.debug:
                fname = f"debug_zepto_{result.product_id or 'page'}.html"
                with open(fname, "w", encoding="utf-8") as f:
                    f.write(page.content())
                print(f"  Debug HTML → {fname}")

            # Strategy 1: API response interception
            for body in captured:
                if self._search_json(body, result):
                    print("  [Source: API response]")
                    break

            # Strategy 2: Meta tags + og:title (most reliable for Zepto SSR)
            if not result.name:
                if self._extract_meta(page, result):
                    print("  [Source: meta tags]")

            # Strategy 3: DOM
            if not result.name:
                if self._extract_dom(page, result):
                    print("  [Source: DOM]")

            # Supplement missing image
            if not result.image_url:
                try:
                    result.image_url = page.evaluate(
                        '() => document.querySelector(\'meta[property="og:image"]\')?.content || null'
                    )
                except Exception:
                    pass

            if not result.name:
                result.error = "Could not extract product data"

        except Exception as e:
            result.error = str(e)
        finally:
            ctx.close()

        return result

    def scrape_multiple(self, urls: list[str], delay: float = 3.0) -> list[ZeptoProductData]:
        results = []
        for i, url in enumerate(urls, 1):
            print(f"\n[{i}/{len(urls)}] Scraping: {url[:80]}...")
            results.append(self.scrape(url))
            if i < len(urls):
                time.sleep(delay)
        return results
