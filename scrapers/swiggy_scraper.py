"""
Swiggy Instamart Vendor Dashboard scraper.

Login strategy:
  - Uses a persistent Chrome profile (scrapers/sessions/swiggy_profile/) so the OTP-based
    session survives across scraper runs.
  - On first run (or when session expires), requests ONE OTP to the vendor email,
    auto-fetches it from Gmail, and logs in.  Profile is then saved to Drive.
  - On subsequent runs, the saved profile lets the scraper skip OTP entirely.

Report flow:
  1. Navigate to partner.swiggy.com/instamart/sales — already logged in via profile
  2. Set custom date range: start = report_date - 1 day, end = report_date
  3. Click "Generate Report"
  4. Poll "Available Reports" section until status = "Ready" (up to 5 minutes)
  5. Download the completed report
  6. Upload to Google Drive
  7. Upload updated profile to Drive

Dashboard URL: https://partner.swiggy.com/instamart/sales  (SWIGGY_LINK in .env)
"""

import io
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path


try:
    from .google_drive_upload import upload_to_drive as _upload_to_drive
except ImportError:
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location(
        "google_drive_upload", Path(__file__).parent / "google_drive_upload.py"
    )
    try:
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _upload_to_drive = _mod.upload_to_drive
    except Exception:
        _upload_to_drive = None

try:
    from .gmail_otp import fetch_latest_otp as _fetch_otp
except ImportError:
    try:
        import importlib.util as _ilu2
        _spec2 = _ilu2.spec_from_file_location(
            "gmail_otp", Path(__file__).parent / "gmail_otp.py"
        )
        _mod2 = _ilu2.module_from_spec(_spec2)
        _spec2.loader.exec_module(_mod2)
        _fetch_otp = _mod2.fetch_latest_otp
    except Exception:
        _fetch_otp = None

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# --- Paths ---
_HERE       = Path(__file__).resolve().parent
PROFILE_DIR = (_HERE / "sessions" / "swiggy_profile").resolve()


def _profile_dir() -> Path:
    """Return the resolved path of the Swiggy Chrome profile directory."""
    return (_HERE / "sessions" / "swiggy_profile").resolve()

# --- URLs ---
# Swiggy migrated from partner.swiggy.com → partner.instamart.in
LOGIN_URL = "https://partner.instamart.in/"
SALES_URL = os.environ.get("SWIGGY_LINK", "https://partner.instamart.in/instamart/sales")

# Both old and new domains are accepted (migration may be in-progress)
_SWIGGY_DOMAINS = ("partner.instamart.in", "partner.swiggy.com")

# OTP sender — Swiggy sends OTPs from this address
SWIGGY_OTP_SENDER = "no-reply@swiggy.in"

# --- Timing ---
REPORT_POLL_INTERVAL_S = 30     # seconds between polls for report readiness (reload every 30s)
REPORT_MAX_POLLS       = 20     # 20 × 30s = 10 minutes max wait
OTP_WAIT_S             = 120    # max seconds to wait for OTP email


class SwiggyScraper:
    """Downloads the daily sales report from the Swiggy Instamart vendor portal."""

    portal_name = "swiggy"

    def __init__(self, headless: bool = True, raw_data_path: str = None):
        self.headless      = headless
        self.raw_data_path = Path(raw_data_path or os.getenv("RAW_DATA_PATH", "./data/raw"))
        self.out_dir       = self.raw_data_path / self.portal_name
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._log = __import__("logging").getLogger("scrapers.swiggy")
        self._email = os.environ.get("SWIGGY_EMAIL", "").split("#")[0].strip()

    # ------------------------------------------------------------------
    # Browser lifecycle
    # ------------------------------------------------------------------

    def _init_browser(self):
        from playwright.sync_api import sync_playwright
        profile = _profile_dir()
        profile.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().__enter__()
        self._ctx = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            headless=self.headless,
            slow_mo=200 if not self.headless else 0,
            args=["--start-maximized"] if not self.headless else [],
            viewport={"width": 1400, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        pages = self._ctx.pages
        self._page = pages[0] if pages else self._ctx.new_page()
        self._page.set_default_timeout(30_000)

    def _close_browser(self):
        try:
            self._ctx.close()
        except Exception:
            pass
        try:
            self._pw.__exit__(None, None, None)
        except Exception:
            pass

    def _shot(self, label: str):
        try:
            path = self.out_dir / f"debug_swiggy_{label}_{int(time.time())}.png"
            self._page.screenshot(path=str(path))
            self._log.debug("[Swiggy] Screenshot: %s", path)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Session check
    # ------------------------------------------------------------------

    def _is_logged_in(self) -> bool:
        """Return True if the current URL is inside the dashboard (not login page)."""
        url = self._page.url
        on_portal = any(d in url for d in _SWIGGY_DOMAINS)
        return (
            on_portal
            and "/login" not in url.lower()
            and "/auth" not in url.lower()
            and url.rstrip("/") not in ("https://partner.swiggy.com", "https://partner.instamart.in")
        )

    # ------------------------------------------------------------------
    # OTP auto-fetch
    # ------------------------------------------------------------------

    def _get_otp_from_gmail(self, after_epoch: int) -> str | None:
        """Poll Gmail for a fresh Swiggy OTP for up to OTP_WAIT_S seconds."""
        if not _fetch_otp:
            self._log.warning("[Swiggy] gmail_otp not available — cannot auto-fetch OTP")
            return None
        deadline = time.time() + OTP_WAIT_S
        attempt  = 0
        while time.time() < deadline:
            attempt += 1
            self._log.info(
                "[Swiggy] Polling Gmail for OTP (attempt %d, %ds left)...",
                attempt, int(deadline - time.time()),
            )
            try:
                otp = _fetch_otp(sender=SWIGGY_OTP_SENDER, after_epoch=after_epoch)
                if otp:
                    self._log.info("[Swiggy] OTP received: %s", otp)
                    return otp
            except Exception as e:
                self._log.warning("[Swiggy] Gmail poll error: %s", e)
            if time.time() < deadline:
                time.sleep(10)
        self._log.warning("[Swiggy] OTP not received within %ds", OTP_WAIT_S)
        return None

    # ------------------------------------------------------------------
    # Re-authentication (session expired)
    # ------------------------------------------------------------------

    def _re_auth(self) -> None:
        """
        Full OTP login flow. Called when the persistent profile session has expired.
        Requests ONE OTP, auto-fetches from Gmail, fills the boxes, submits.
        """
        self._log.info("[Swiggy] Session expired — performing re-auth")

        # Navigate to the portal — it will redirect to the login page if not authenticated
        self._page.goto(SALES_URL, wait_until="domcontentloaded")
        self._page.wait_for_timeout(3000)
        self._shot("reauth_login_page")

        if self._is_logged_in():
            self._log.info("[Swiggy] Already logged in after navigation")
            return

        # Fill email / phone field
        try:
            # Swiggy login: input for email or mobile number
            email_input = self._page.locator(
                'input[type="email"], input[type="text"][placeholder*="email" i], '
                'input[placeholder*="mobile" i], input[placeholder*="phone" i], '
                'input[name*="email" i], input[name*="phone" i], input[name*="mobile" i]'
            ).first
            email_input.wait_for(state="visible", timeout=15_000)
            email_input.fill(self._email)
            self._page.wait_for_timeout(500)
            self._log.info("[Swiggy] Filled email/phone: %s", self._email)
        except Exception as e:
            self._shot("reauth_email_error")
            raise RuntimeError(f"[Swiggy] Cannot find email/phone input: {e}")

        # Click "Get OTP" / "Request OTP" / "Continue" button.
        # The button is disabled until the email field passes validation — wait for enabled.
        otp_requested_at = int(time.time())
        try:
            # First try the specific Swiggy submit button by data-testid
            btn = self._page.locator('[data-testid="submit-phone-number"]')
            if btn.count() == 0:
                # Fall back to text-based selectors
                btn = self._page.locator(
                    'button:has-text("Get OTP"), button:has-text("Request OTP"), '
                    'button:has-text("Send OTP"), button:has-text("Continue"), '
                    'button[type="submit"]'
                ).first
            # Wait for the button to be visible AND enabled (React enables it after validation)
            btn.wait_for(state="visible", timeout=10_000)
            # Poll until enabled (up to 10s)
            for _ in range(20):
                if btn.is_enabled():
                    break
                self._page.wait_for_timeout(500)
            btn.click()
            self._page.wait_for_timeout(2000)
            self._log.info("[Swiggy] OTP requested")
        except Exception as e:
            self._shot("reauth_otp_request_error")
            raise RuntimeError(f"[Swiggy] Cannot click OTP request button: {e}")

        # Wait for OTP input boxes
        try:
            self._page.locator('input[maxlength="1"]').first.wait_for(
                state="visible", timeout=15_000
            )
            self._log.info("[Swiggy] OTP input boxes appeared")
        except Exception:
            # Swiggy may use a single 4/6-digit input instead of individual boxes
            try:
                self._page.locator(
                    'input[maxlength="4"], input[maxlength="6"], '
                    'input[placeholder*="OTP" i], input[name*="otp" i]'
                ).first.wait_for(state="visible", timeout=10_000)
                self._log.info("[Swiggy] Single OTP input appeared")
            except Exception:
                self._shot("reauth_otp_boxes_missing")
                raise RuntimeError("[Swiggy] OTP input did not appear after requesting OTP")

        self._shot("reauth_otp_visible")

        # Fetch OTP from Gmail
        otp = self._get_otp_from_gmail(after_epoch=otp_requested_at)
        if not otp:
            self._shot("reauth_otp_timeout")
            raise RuntimeError(
                "[Swiggy] Could not fetch OTP from Gmail. "
                "Check token.json and that email is delivered to the inbox."
            )

        # Enter OTP
        self._log.info("[Swiggy] Entering OTP: %s", otp)
        otp_boxes = self._page.locator('input[maxlength="1"]').all()

        if len(otp_boxes) >= len(otp):
            # Individual digit boxes
            for i, digit in enumerate(otp):
                box = otp_boxes[i]
                box.click()
                box.press_sequentially(digit, delay=80)
                self._page.wait_for_timeout(80)
        else:
            # Single input or fewer boxes than expected — type full OTP into first input
            single = self._page.locator(
                'input[maxlength="1"], input[maxlength="4"], input[maxlength="6"], '
                'input[placeholder*="OTP" i], input[name*="otp" i]'
            ).first
            single.click()
            single.press_sequentially(otp, delay=100)

        self._page.wait_for_timeout(800)
        self._shot("reauth_otp_filled")

        # Submit OTP — Swiggy may auto-submit on last digit; also try explicit button
        try:
            submit_btn = self._page.locator(
                'button:has-text("Submit OTP"), button:has-text("Verify OTP"), '
                'button:has-text("Verify"), button:has-text("Login"), '
                'button[type="submit"]'
            ).first
            if submit_btn.is_visible(timeout=3_000):
                submit_btn.click()
                self._page.wait_for_timeout(2000)
        except Exception:
            pass  # auto-submitted after last digit

        self._shot("reauth_post_submit")

        # Wait for any post-OTP page (dashboard or account-select), on either domain
        try:
            self._page.wait_for_url(
                lambda u: any(d in u for d in _SWIGGY_DOMAINS)
                          and "/login" not in u.lower()
                          and "/auth" not in u.lower()
                          and u.rstrip("/") not in ("https://partner.swiggy.com", "https://partner.instamart.in"),
                timeout=30_000,
            )
        except Exception:
            self._shot("reauth_dashboard_wait_failed")
            raise RuntimeError(
                f"[Swiggy] Did not reach dashboard after OTP. URL: {self._page.url}"
            )

        self._log.info("[Swiggy] Re-auth successful. URL: %s", self._page.url)

        # Handle account-select page (Swiggy may show a store/account picker after OTP)
        self._handle_account_select()

    # ------------------------------------------------------------------
    # Account-select handler (post-OTP store picker)
    # ------------------------------------------------------------------

    def _handle_account_select(self) -> None:
        """
        Swiggy may redirect to an account-select / store-picker page after OTP.
        Also handles the portal migration page ("This website is moving!") which
        auto-redirects to partner.instamart.in after 3 seconds.
        Silently skips if on neither page.
        """
        url = self._page.url
        if "account-select" not in url and "store-select" not in url:
            return

        self._log.info("[Swiggy] On account-select page — picking first account")
        self._shot("account_select")

        # Check for the migration notice ("This website is moving!")
        page_text = self._page.inner_text("body") if self._page else ""
        if "partner.instamart.in" in page_text or "website is moving" in page_text.lower():
            self._log.info("[Swiggy] Migration page detected — waiting for auto-redirect to partner.instamart.in")
            try:
                self._page.wait_for_url(
                    lambda u: "partner.instamart.in" in u,
                    timeout=10_000,
                )
                self._log.info("[Swiggy] Redirected to %s", self._page.url)
            except Exception:
                # Redirect didn't happen — navigate there directly
                self._log.info("[Swiggy] Navigating directly to partner.instamart.in")
                self._page.goto(LOGIN_URL, wait_until="domcontentloaded")
                self._page.wait_for_timeout(3000)
            self._shot("after_account_select")
            return

        try:
            # Look for a clickable store/account card or list item
            item = self._page.locator(
                '[class*="store" i], [class*="account" i], [class*="restaurant" i], '
                '[class*="outlet" i], [class*="card" i]'
            ).first
            item.wait_for(state="visible", timeout=10_000)
            item.click()
            self._page.wait_for_timeout(3000)
            self._log.info("[Swiggy] Account selected. URL: %s", self._page.url)
        except Exception as e:
            self._log.warning("[Swiggy] Could not auto-select account: %s", e)
            self._shot("account_select_error")
        self._shot("after_account_select")

    # ------------------------------------------------------------------
    # Login (check session, re-auth if needed)
    # ------------------------------------------------------------------

    def login(self) -> None:
        """
        Navigate directly to SALES_URL. If not logged in, the portal redirects
        to the login page automatically. Uses saved persistent profile — no OTP
        needed if the session is still valid. Falls back to full re-auth
        (OTP via Gmail) if the session has expired.
        """
        self._log.info("[Swiggy] Navigating to %s", SALES_URL)
        self._page.goto(SALES_URL, wait_until="domcontentloaded")
        self._page.wait_for_timeout(3000)

        if self._is_logged_in():
            self._log.info("[Swiggy] Session valid. URL: %s", self._page.url)
            return

        # Full re-auth
        self._re_auth()

    # ------------------------------------------------------------------
    # Navigate to Sales page
    # ------------------------------------------------------------------

    def _go_to_sales(self) -> None:
        """Navigate to the Swiggy Instamart sales page."""
        self._log.info("[Swiggy] Navigating to sales page: %s", SALES_URL)
        self._page.goto(SALES_URL, wait_until="domcontentloaded")
        self._page.wait_for_timeout(4000)
        self._shot("sales_page")

        if not self._is_logged_in():
            raise RuntimeError(
                f"[Swiggy] Redirected to login when navigating to sales. URL: {self._page.url}"
            )
        self._log.info("[Swiggy] Sales page loaded. URL: %s", self._page.url)

    # ------------------------------------------------------------------
    # Set date range
    # ------------------------------------------------------------------

    def _set_date_range(self, start_date: date, end_date: date) -> None:
        """
        Set the custom date range on the Swiggy Instamart sales page.

        The Swiggy portal shows a date-range dropdown (e.g. "This Week", "Yesterday",
        "Custom Range"). We:
          1. Click the dropdown trigger
          2. Select "Custom Range" (or "Custom Date Range") from the list
          3. Fill the start and end date inputs that appear
          4. Confirm / Apply

        Formats tried:
          - YYYY-MM-DD (ISO)
          - DD/MM/YYYY (Indian)
          - DD MMM YYYY (e.g. "22 Feb 2026")
        """
        start_str   = start_date.strftime("%Y-%m-%d")
        end_str     = end_date.strftime("%Y-%m-%d")
        start_ddmm  = start_date.strftime("%d/%m/%Y")
        end_ddmm    = end_date.strftime("%d/%m/%Y")
        start_label = start_date.strftime("%-d %b %Y") if not sys.platform.startswith("win") \
                      else start_date.strftime("%d %b %Y").lstrip("0")
        end_label   = end_date.strftime("%-d %b %Y") if not sys.platform.startswith("win") \
                      else end_date.strftime("%d %b %Y").lstrip("0")

        self._log.info("[Swiggy] Setting date range: %s to %s", start_str, end_str)
        self._shot("before_date_set")

        # --- Step 1: Dump visible date-related elements for diagnostics ---
        info = self._page.evaluate("""
            () => {
                const els = Array.from(document.querySelectorAll('*')).filter(el => {
                    const rect = el.getBoundingClientRect();
                    if (rect.width < 10) return false;
                    const txt = (el.innerText || '').toLowerCase();
                    const cls = (el.className || '').toString().toLowerCase();
                    const dt  = (el.getAttribute('data-testid') || '').toLowerCase();
                    return (
                        txt.includes('date range') || txt.includes('this week') ||
                        txt.includes('yesterday') || txt.includes('custom') ||
                        cls.includes('date') || cls.includes('filter') ||
                        dt.includes('date') || dt.includes('filter')
                    ) && el.children.length < 6;
                }).slice(0, 8);
                return els.map(el => ({
                    tag: el.tagName,
                    cls: el.className.toString().substring(0, 80),
                    dt:  el.getAttribute('data-testid') || '',
                    txt: el.innerText.trim().substring(0, 60),
                }));
            }
        """)
        self._log.info("[Swiggy] Date-area elements: %s", info)

        # --- Step 2: Click the date range trigger ---
        # Try data-testid first, then class/text heuristics
        trigger_clicked = False
        for selector in [
            '[data-testid*="date" i]',
            '[data-testid*="filter" i]',
            '[class*="DateFilter" i]',
            '[class*="dateFilter" i]',
            '[class*="date-filter" i]',
            '[class*="dateRange" i]',
            '[class*="date-range" i]',
        ]:
            try:
                loc = self._page.locator(selector).first
                if loc.is_visible(timeout=1500):
                    loc.click()
                    self._page.wait_for_timeout(1000)
                    trigger_clicked = True
                    self._log.info("[Swiggy] Clicked date trigger via: %s", selector)
                    break
            except Exception:
                pass

        if not trigger_clicked:
            # Text-based fallback using JS
            self._page.evaluate("""
                () => {
                    const all = Array.from(document.querySelectorAll('*'));
                    for (const el of all) {
                        const rect = el.getBoundingClientRect();
                        if (rect.width < 10) continue;
                        const txt = (el.innerText || '').toLowerCase().trim();
                        if (
                            (txt === 'date range' || txt.startsWith('date range') ||
                             txt.includes('this week') || txt.includes('yesterday') ||
                             txt.includes('custom range'))
                            && el.children.length < 5
                        ) {
                            el.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                            return el.innerText.trim().substring(0, 60);
                        }
                    }
                    return null;
                }
            """)
            self._page.wait_for_timeout(1000)

        self._shot("after_date_trigger_click")

        # --- Step 3: Select "Custom Range" from the dropdown ---
        custom_clicked = False
        for label in ["Custom Range", "Custom Date Range", "Custom", "Date Range"]:
            try:
                loc = self._page.get_by_text(label, exact=True).first
                if loc.is_visible(timeout=1500):
                    loc.click()
                    self._page.wait_for_timeout(1000)
                    custom_clicked = True
                    self._log.info("[Swiggy] Clicked '%s' in date dropdown", label)
                    break
            except Exception:
                pass

        if not custom_clicked:
            # Fallback: evaluate
            self._page.evaluate("""
                () => {
                    const candidates = Array.from(document.querySelectorAll('li, [role="option"], [class*="option" i]'));
                    for (const el of candidates) {
                        const txt = (el.innerText || '').toLowerCase().trim();
                        if (txt.includes('custom') || txt === 'date range') {
                            el.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                            return txt;
                        }
                    }
                    return null;
                }
            """)
            self._page.wait_for_timeout(1000)

        self._shot("after_custom_range_click")

        # --- Step 4: Fill date inputs ---
        filled = self._page.evaluate("""
            ([iso_start, iso_end, ddmm_start, ddmm_end]) => {
                const inputs = Array.from(document.querySelectorAll('input[type="date"], input[type="text"]'))
                    .filter(el => {
                        const rect = el.getBoundingClientRect();
                        if (rect.width < 10) return false;
                        const ph = (el.placeholder || '').toLowerCase();
                        const nm = (el.name   || '').toLowerCase();
                        const id = (el.id     || '').toLowerCase();
                        return ph.includes('date') || ph.includes('from') || ph.includes('start') || ph.includes('to') ||
                               nm.includes('date') || nm.includes('start') || nm.includes('end') ||
                               id.includes('date') || id.includes('from') || id.includes('to') ||
                               el.type === 'date';
                    });

                function fill(el, val) {
                    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    setter.call(el, val);
                    el.dispatchEvent(new Event('input',  {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                }

                if (inputs.length >= 2) {
                    fill(inputs[0], iso_start);
                    fill(inputs[1], iso_end);
                    return 'filled 2: ' + (inputs[0].id || inputs[0].name || inputs[0].placeholder);
                } else if (inputs.length === 1) {
                    fill(inputs[0], iso_start + ' - ' + iso_end);
                    return 'filled combined: ' + (inputs[0].id || inputs[0].placeholder);
                }
                return null;
            }
        """, [start_str, end_str, start_ddmm, end_ddmm])

        if filled:
            self._log.info("[Swiggy] Filled date inputs: %s", filled)
        else:
            # Try DD/MM/YYYY format inputs (some Swiggy date pickers use this)
            filled2 = self._page.evaluate("""
                ([ddmm_start, ddmm_end]) => {
                    const inputs = Array.from(document.querySelectorAll('input'))
                        .filter(el => el.getBoundingClientRect().width > 10 && !el.disabled);
                    if (inputs.length >= 2) {
                        function fill(el, val) {
                            const setter = Object.getOwnPropertyDescriptor(
                                window.HTMLInputElement.prototype, 'value').set;
                            setter.call(el, val);
                            el.dispatchEvent(new Event('input',  {bubbles: true}));
                            el.dispatchEvent(new Event('change', {bubbles: true}));
                        }
                        fill(inputs[0], ddmm_start);
                        fill(inputs[1], ddmm_end);
                        return 'filled visible inputs with DD/MM/YYYY';
                    }
                    return null;
                }
            """, [start_ddmm, end_ddmm])
            if filled2:
                self._log.info("[Swiggy] %s", filled2)
            else:
                self._log.warning(
                    "[Swiggy] Could not fill date inputs. "
                    "Run with headless=False to inspect the date picker UI."
                )

        self._page.wait_for_timeout(800)
        self._shot("after_date_fill")

        # --- Step 5: Click calendar day cells (Swiggy shows a calendar picker, not plain inputs) ---
        # The "Custom Date Range" option opens a floating calendar where you click days.
        # Try clicking: start day, then end day in the calendar cells visible on screen.
        start_day = str(int(start_date.strftime("%d")))  # no leading zero: "22"
        end_day   = str(int(end_date.strftime("%d")))
        start_month_year = start_date.strftime("%B %Y")  # "February 2026"
        end_month_year   = end_date.strftime("%B %Y")

        cells_clicked = self._page.evaluate("""
            ([startDay, endDay, startMY, endMY]) => {
                // Swiggy uses a floating calendar portal. Find all calendar cell elements
                // that contain just a day number (1–31).
                const portals = Array.from(document.querySelectorAll('[id^=":r"]'));
                // Search in the whole document if no portals found
                const searchRoot = portals.length > 0 ? portals[portals.length - 1] : document;

                // Find all visible elements whose innerText is exactly a day number
                function findDayCells(root) {
                    return Array.from(root.querySelectorAll('*')).filter(el => {
                        const rect = el.getBoundingClientRect();
                        if (rect.width < 5 || rect.width > 60) return false;
                        const txt = (el.innerText || '').trim();
                        return /^\\d{1,2}$/.test(txt) && parseInt(txt) >= 1 && parseInt(txt) <= 31;
                    });
                }

                const cells = findDayCells(document);
                // Filter to cells that look like calendar day buttons (not year/header)
                const dayBtns = cells.filter(el => {
                    const cls = (el.className || '').toString();
                    const tag = el.tagName;
                    // Must be interactive or in a date-related container
                    return (tag === 'BUTTON' || tag === 'TD' || tag === 'DIV' || tag === 'SPAN') &&
                           el.getBoundingClientRect().height < 50;
                });

                let startClicked = false;
                let endClicked = false;

                // Click start day
                for (const el of dayBtns) {
                    if ((el.innerText || '').trim() === startDay) {
                        el.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                        startClicked = true;
                        break;
                    }
                }

                // Click end day (after start — search again in case calendar updated)
                for (const el of dayBtns) {
                    if ((el.innerText || '').trim() === endDay && el !== dayBtns[0]) {
                        el.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                        endClicked = true;
                        break;
                    }
                }

                return {startClicked, endClicked, totalCells: dayBtns.length};
            }
        """, [start_day, end_day, start_month_year, end_month_year])
        self._log.info("[Swiggy] Calendar cell click result: %s", cells_clicked)
        self._page.wait_for_timeout(800)

        # --- Step 6: Click "Select Range" / "Apply" to confirm and close the calendar ---
        for label in ["Select Range", "Apply", "Done", "Confirm", "OK"]:
            try:
                btn = self._page.get_by_text(label, exact=True).first
                if btn.is_visible(timeout=1000):
                    btn.click()
                    self._page.wait_for_timeout(1500)
                    self._log.info("[Swiggy] Clicked '%s' to apply date range", label)
                    break
            except Exception:
                pass

        # Dismiss any remaining overlay with Escape
        self._page.keyboard.press("Escape")
        self._page.wait_for_timeout(500)

        self._page.wait_for_timeout(1000)
        self._shot("after_date_set")
        self._log.info("[Swiggy] Date range set (%s -> %s)", start_str, end_str)

    # ------------------------------------------------------------------
    # Generate report
    # ------------------------------------------------------------------

    def _click_generate_report(self) -> None:
        """
        Click the "Generate Report" button on the sales page.
        Uses dispatchEvent to bypass any floating overlay that might intercept the click.
        """
        self._log.info("[Swiggy] Looking for 'Generate Report' button")
        # First log all visible buttons for diagnostics
        all_btns = self._page.evaluate("""
            () => Array.from(document.querySelectorAll('button'))
                .filter(el => el.getBoundingClientRect().width > 0)
                .map(el => ({text: el.innerText.trim().substring(0, 50), cls: el.className.toString().substring(0, 60)}))
        """)
        self._log.info("[Swiggy] Visible buttons: %s", all_btns)

        # Use JS dispatchEvent to avoid overlay interception
        clicked = self._page.evaluate("""
            () => {
                const btns = Array.from(document.querySelectorAll('button'));
                const targets = ['generate report', 'generate', 'download report', 'export', 'request report'];
                for (const btn of btns) {
                    const txt = (btn.innerText || '').toLowerCase().trim();
                    if (targets.some(t => txt === t || txt.startsWith(t))) {
                        btn.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                        return btn.innerText.trim();
                    }
                }
                return null;
            }
        """)
        if clicked:
            self._log.info("[Swiggy] 'Generate Report' clicked via JS: %s", clicked)
            self._page.wait_for_timeout(2000)
            self._shot("after_generate_report")
        else:
            self._shot("generate_report_btn_missing")
            raise RuntimeError("[Swiggy] 'Generate Report' button not found in page")

    # ------------------------------------------------------------------
    # Poll "Available Reports" section
    # ------------------------------------------------------------------

    # ---- JS helpers (shared between steps) ----
    _JS_FIND_REPORTS_SECTION = """
        () => {
            for (const el of Array.from(document.querySelectorAll('*'))) {
                const rect = el.getBoundingClientRect();
                if (rect.width < 50) continue;
                const txt = (el.innerText || '').trim();
                if (txt.toLowerCase().startsWith('available reports') && el.children.length > 0) {
                    return el.innerText.substring(0, 600);
                }
            }
            return null;
        }
    """

    _JS_GET_NEWEST_REPORT = """
        () => {
            // IMSales entries are in a list; the first one in DOM order is the newest
            const all = Array.from(document.querySelectorAll('*'));
            const sectionEl = all.find(el =>
                el.getBoundingClientRect().width > 50 &&
                (el.innerText || '').trim().toLowerCase().startsWith('available reports') &&
                el.children.length > 0
            );
            if (!sectionEl) return null;
            // Leaf nodes with "IMSales_" pattern
            const leaves = Array.from(sectionEl.querySelectorAll('*')).filter(el =>
                el.children.length === 0 && /^IMSales_/.test((el.innerText || '').trim())
            );
            return leaves.length > 0 ? {name: leaves[0].innerText.trim(), total: leaves.length} : null;
        }
    """

    def _poll_and_download_report(self, report_date: date) -> "Path | None":
        """
        Phase 1 — Confirm queued: Wait up to 60s for the new report to show
                  "Generation in progress" in the Available Reports section.
        Phase 2 — Wait for ready: Reload every 30s until that report's status
                  changes to "Generated on…".
        Phase 3 — Download: Click the download-icon via Playwright locator
                  wrapped in expect_download. Falls back to expect_popup if the
                  file opens in a new tab.

        Returns the saved file path, or None if timed out.
        """
        date_str    = report_date.strftime("%Y-%m-%d")
        output_path = self.out_dir / f"swiggy_sales_{date_str}.xlsx"

        self._log.info("[Swiggy] Polling for report readiness (max %ds)...",
                       REPORT_POLL_INTERVAL_S * REPORT_MAX_POLLS)

        # ---- Phase 1: Wait for "Generation in progress" to appear (confirm queued) ----
        newest_name = None
        self._log.info("[Swiggy] Phase 1 — waiting up to 60s for report to appear in queue...")
        for attempt in range(12):  # 5s × 12 = 60s
            info = self._page.evaluate(self._JS_GET_NEWEST_REPORT)
            if info:
                newest_name = info["name"]
                section_text = self._page.evaluate(self._JS_FIND_REPORTS_SECTION) or ""
                self._log.info("[Swiggy] Newest report: %s  (total: %d)", newest_name, info["total"])
                # Check if it's showing "Generation in progress"
                if "generation in progress" in section_text.lower():
                    self._log.info("[Swiggy] Confirmed generating: %s", newest_name)
                    break
            self._page.wait_for_timeout(5_000)
            try:
                self._page.reload(wait_until="domcontentloaded")
                self._page.wait_for_timeout(3_000)
            except Exception:
                pass
        else:
            self._log.warning(
                "[Swiggy] Could not confirm 'Generation in progress' within 60s. "
                "Proceeding anyway with newest=%s", newest_name
            )

        if not newest_name:
            self._log.warning("[Swiggy] No report found in Available Reports section")
            return None

        # ---- Phase 2: Poll every 30s until our report shows "Generated on…" ----
        self._log.info(
            "[Swiggy] Phase 2 — polling every 30s until '%s' is ready (max %d polls)...",
            newest_name, REPORT_MAX_POLLS,
        )
        for poll in range(REPORT_MAX_POLLS):
            self._shot(f"report_poll_{poll + 1}")
            section_text = self._page.evaluate(self._JS_FIND_REPORTS_SECTION) or ""
            self._log.info("[Swiggy] Poll %d/%d section:\n%s",
                           poll + 1, REPORT_MAX_POLLS, section_text[:300])

            # Check if our report is ready: look for "Generated on" immediately after its name
            # Section text format:
            #   IMSales_022426_1113\nGenerated on February 24, 2026 at 11:13 AM\n...
            #   IMSales_022426_1005\nGenerated on February 24, 2026 at 10:05:14 AM\n...
            lines = [l.strip() for l in section_text.splitlines() if l.strip()]
            our_report_ready = False
            for i, line in enumerate(lines):
                if line == newest_name or line.startswith(newest_name):
                    # Next line should be the status
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].lower()
                        if next_line.startswith("generated on"):
                            our_report_ready = True
                            self._log.info(
                                "[Swiggy] Report '%s' is READY: %s",
                                newest_name, lines[i + 1],
                            )
                        elif "generation in progress" in next_line:
                            self._log.info("[Swiggy] Report '%s' still generating...", newest_name)
                        else:
                            self._log.info("[Swiggy] Report '%s' status: %s", newest_name, lines[i + 1])
                    break

            if our_report_ready:
                # ---- Phase 3: Download ----
                # Use Playwright locator wrapped in expect_download (correct pattern)
                file_path = self._download_ready_report(report_date, date_str, output_path)
                if file_path:
                    return file_path

            # Still processing — wait 30s and reload
            if poll < REPORT_MAX_POLLS - 1:
                self._log.info("[Swiggy] Waiting 30s before next poll...")
                self._page.wait_for_timeout(30_000)
                try:
                    self._page.reload(wait_until="domcontentloaded")
                    self._page.wait_for_timeout(3_000)
                except Exception:
                    pass

        self._shot("report_poll_timeout")
        self._log.warning(
            "[Swiggy] Report '%s' not ready after %d polls", newest_name, REPORT_MAX_POLLS
        )
        return None

    def _download_ready_report(
        self, report_date: date, date_str: str, output_path: "Path"
    ) -> "Path | None":
        """
        Click the download-icon on the first ready report entry and capture the file.

        Tries three strategies:
          1. expect_download wrapping Playwright locator click
          2. expect_popup (download opens in new tab)
          3. Network request interception to extract file URL
        """
        self._log.info("[Swiggy] Attempting download...")
        self._shot("before_download_click")

        # Strategy 1: expect_download wrapping locator.click()
        # The download-icon div (imads__Ri7gC) is the clickable area.
        for selector in [
            '[data-testid="download-icon"]',
            '[class*="Ri7gC"]',
        ]:
            try:
                loc = self._page.locator(selector).first
                if not loc.is_visible(timeout=2_000):
                    continue
                self._log.info("[Swiggy] Clicking download via locator: %s", selector)
                try:
                    with self._page.expect_download(timeout=30_000) as dl_info:
                        loc.click(force=True)
                    dl = dl_info.value
                    suggested = dl.suggested_filename or ""
                    if suggested.lower().endswith(".csv"):
                        output_path = output_path.with_suffix(".csv")
                    dl.save_as(str(output_path))
                    self._log.info("[Swiggy] Downloaded (expect_download): %s", output_path)
                    return output_path
                except Exception as e:
                    self._log.warning("[Swiggy] expect_download failed (%s): %s", selector, e)
            except Exception:
                pass

        # Strategy 2: expect_popup (file opens in a new tab)
        for selector in [
            '[data-testid="download-icon"]',
            '[class*="Ri7gC"]',
        ]:
            try:
                loc = self._page.locator(selector).first
                if not loc.is_visible(timeout=1_000):
                    continue
                self._log.info("[Swiggy] Trying popup capture for: %s", selector)
                try:
                    with self._ctx.expect_page(timeout=20_000) as popup_info:
                        loc.click(force=True)
                    popup = popup_info.value
                    popup.wait_for_load_state("domcontentloaded", timeout=20_000)
                    popup_url = popup.url
                    self._log.info("[Swiggy] Popup URL: %s", popup_url)
                    # Try to capture download from popup
                    try:
                        with popup.expect_download(timeout=15_000) as dl_info:
                            pass
                        dl = dl_info.value
                        suggested = dl.suggested_filename or ""
                        if suggested.lower().endswith(".csv"):
                            output_path = output_path.with_suffix(".csv")
                        dl.save_as(str(output_path))
                        self._log.info("[Swiggy] Downloaded from popup: %s", output_path)
                        return output_path
                    except Exception:
                        # Navigate current page to the popup URL
                        if popup_url and popup_url.startswith("http"):
                            self._log.info("[Swiggy] Navigating to popup URL: %s", popup_url)
                            try:
                                with self._page.expect_download(timeout=15_000) as dl_info:
                                    self._page.goto(popup_url, wait_until="domcontentloaded")
                                dl = dl_info.value
                                dl.save_as(str(output_path))
                                self._log.info("[Swiggy] Downloaded via URL nav: %s", output_path)
                                return output_path
                            except Exception as nav_e:
                                self._log.warning("[Swiggy] URL nav download failed: %s", nav_e)
                except Exception as popup_e:
                    self._log.warning("[Swiggy] expect_page failed (%s): %s", selector, popup_e)
            except Exception:
                pass

        # Strategy 3: Intercept network request to get download URL
        self._log.info("[Swiggy] Trying network intercept approach...")
        captured_url = []

        def handle_request(req):
            url = req.url
            if any(x in url.lower() for x in ["download", "report", "export", ".xlsx", ".csv", ".zip"]):
                captured_url.append(url)

        self._page.on("request", handle_request)
        try:
            loc = self._page.locator('[data-testid="download-icon"]').first
            if loc.is_visible(timeout=2_000):
                loc.click(force=True)
                self._page.wait_for_timeout(5_000)
        except Exception:
            pass
        self._page.remove_listener("request", handle_request)

        if captured_url:
            self._log.info("[Swiggy] Captured download URL: %s", captured_url[-1])
            import urllib.request
            try:
                urllib.request.urlretrieve(captured_url[-1], str(output_path))
                self._log.info("[Swiggy] Downloaded via URL: %s", output_path)
                return output_path
            except Exception as ue:
                self._log.warning("[Swiggy] URL download failed: %s", ue)

        self._shot("download_failed")
        self._log.warning("[Swiggy] All download strategies exhausted")
        return None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self, report_date: date = None) -> dict:
        """
        Full scraping cycle.

        Date range sent to the portal:
          start = report_date - 1 day
          end   = report_date

        Returns a status dict with keys:
          portal, date, file, status, error, drive_link (optional)
        """
        if report_date is None:
            report_date = date.today() - timedelta(days=1)

        start_date = report_date - timedelta(days=1)
        end_date   = report_date

        result = {
            "portal": self.portal_name,
            "date":   report_date,
            "file":   None,
            "status": "failed",
            "error":  None,
        }

        try:
            from scrapers.profile_sync import download_profile, upload_profile
        except ImportError:
            from profile_sync import download_profile, upload_profile

        login_ok = False
        try:
            # Pull latest profile from Drive before launching browser (no-op if not configured)
            download_profile("swiggy")

            self._init_browser()
            self.login()
            login_ok = True

            # Snapshot session after login so it's preserved even if download fails
            session_path = _HERE / "sessions" / "swiggy_session.json"
            session_path.parent.mkdir(parents=True, exist_ok=True)
            self._ctx.storage_state(path=str(session_path))
            self._log.info("[Swiggy] Session snapshot saved to %s", session_path)

            self._go_to_sales()
            self._set_date_range(start_date, end_date)
            self._click_generate_report()

            file_path = self._poll_and_download_report(report_date)
            if file_path:
                result.update({"file": file_path, "status": "success"})
            else:
                result.update({"status": "failed", "error": "Report download timed out"})

            # Upload to Google Drive: SolaraDashboard Reports / YYYY-MM / Swiggy /
            if _upload_to_drive and file_path:
                drive_link = _upload_to_drive(
                    portal="Swiggy",
                    report_date=report_date,
                    file_path=file_path,
                )
                if drive_link:
                    result["drive_link"] = drive_link
                    self._log.info("[Swiggy] Uploaded to Drive: %s", drive_link)

        except Exception as exc:
            self._log.error("[Swiggy] Run failed: %s", exc)
            result["error"] = str(exc)
        finally:
            self._close_browser()
            # Only upload profile if login succeeded — avoids overwriting Drive with a failed session
            if login_ok:
                upload_profile("swiggy")

        return result


# ------------------------------------------------------------------
# CLI entry point for manual testing / first auth
# ------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    import logging
    from dotenv import load_dotenv
    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(description="Swiggy Instamart scraper")
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Report date YYYY-MM-DD (default: yesterday). "
             "Date range sent to portal will be (date-1) to date.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help="Run headless (default: headed for easier debugging / first auth)",
    )
    args = parser.parse_args()

    if args.date:
        from datetime import datetime
        report_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        report_date = date.today() - timedelta(days=1)

    scraper = SwiggyScraper(headless=args.headless)
    result  = scraper.run(report_date=report_date)
    print("\nResult:", result)
