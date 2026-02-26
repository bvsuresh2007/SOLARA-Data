"""
Blinkit (PartnersBiz) sales report scraper.

Login strategy:
  - Uses a persistent Chrome profile (scrapers/sessions/blinkit_profile/) so the OTP-based
    session survives across scraper runs.
  - Run auth_blinkit.py ONCE to log in and save the profile. After that,
    the scraper reuses the saved session without triggering OTP.
  - If the session expires, the scraper will attempt a full re-auth using
    the Gmail OTP auto-fetch (same logic as auth_blinkit.py).

Report flow (TODO: verify selectors after first successful auth run):
  1. Navigate to partnersbiz.com — already logged in via persistent profile
  2. Go to SOH / Reports page
  3. Set date range to yesterday
  4. Request download / export
  5. Wait for file → save as blinkit_sales_YYYY-MM-DD.xlsx (or .csv)
  6. Upload to Google Drive

Dashboard URL: https://partnersbiz.com/app/soh  (BLINKIT_LINK in .env)
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
# Profile dir is read at call time (inside run()) so PROFILES_LOCAL_DIR can be
# set after module import. Module-level constant kept for backward-compat only.
PROFILE_DIR = (_HERE / "sessions" / "blinkit_profile").resolve()


def _profile_dir() -> Path:
    """Return the resolved path of the Blinkit Chrome profile directory."""
    return (_HERE / "sessions" / "blinkit_profile").resolve()

# --- URLs ---
LOGIN_URL   = "https://partnersbiz.com/"
SOH_URL     = os.environ.get("BLINKIT_LINK", "https://partnersbiz.com/app/soh")

# OTP sender confirmed from previous inspection runs
BLINKIT_OTP_SENDER = "noreply@partnersbiz.com"

# --- Timing ---
DOWNLOAD_TIMEOUT_S = 180
POLL_INTERVAL_S    = 10
OTP_WAIT_S         = 120   # max seconds to wait for OTP email


class BlinkitScraper:
    """Downloads the daily sales report from the Blinkit PartnersBiz portal."""

    portal_name = "blinkit"

    def __init__(self, headless: bool = True, raw_data_path: str = None):
        self.headless      = headless
        self.raw_data_path = Path(raw_data_path or os.getenv("RAW_DATA_PATH", "./data/raw"))
        self.out_dir       = self.raw_data_path / self.portal_name
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._log = __import__("logging").getLogger("scrapers.blinkit")
        self._email = os.environ.get("BLINKIT_EMAIL", "").split("#")[0].strip()

    # ------------------------------------------------------------------
    # Browser lifecycle
    # ------------------------------------------------------------------

    def _init_browser(self):
        from playwright.sync_api import sync_playwright
        profile = _profile_dir()
        profile.mkdir(parents=True, exist_ok=True)  # create fresh dir on first run
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
            path = self.out_dir / f"debug_blinkit_{label}_{int(time.time())}.png"
            self._page.screenshot(path=str(path))
            self._log.debug("[Blinkit] Screenshot: %s", path)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Modal dismissal
    # ------------------------------------------------------------------

    def _dismiss_modals(self) -> None:
        """
        Dismiss any open Ant Design modals or onboarding overlays.
        Called before any page interaction to clear blocking overlays.
        """
        try:
            # "Skip for now" onboarding modal (seen on /app/sales)
            skip_btn = self._page.locator('button:has-text("Skip for now"), button:has-text("Skip")')
            if skip_btn.first.is_visible(timeout=2_000):
                self._log.info("[Blinkit] Dismissing onboarding modal ('Skip for now')")
                skip_btn.first.click()
                self._page.wait_for_timeout(1000)
                return
        except Exception:
            pass

        try:
            # Generic Ant Design modal close button
            close_btn = self._page.locator('.ant-modal-close, .ant-modal-close-x, button.ant-modal-close')
            if close_btn.first.is_visible(timeout=1_000):
                self._log.info("[Blinkit] Dismissing modal via close button")
                close_btn.first.click()
                self._page.wait_for_timeout(1000)
                return
        except Exception:
            pass

        try:
            # Press Escape as last resort
            modal = self._page.locator('.ant-modal-wrap')
            if modal.first.is_visible(timeout=500):
                self._log.info("[Blinkit] Dismissing modal via Escape")
                self._page.keyboard.press("Escape")
                self._page.wait_for_timeout(1000)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------

    def _is_logged_in(self) -> bool:
        """Return True if the current URL is inside the dashboard (not login page)."""
        url = self._page.url
        return (
            "partnersbiz.com" in url
            and "/login" not in url
            and url.rstrip("/") != "https://partnersbiz.com"
        )

    def _is_on_company_selector(self) -> bool:
        """Return True if the 'Access dashboard as' company selector is shown."""
        try:
            return self._page.evaluate(
                "() => (document.body.innerText || '').includes('Access dashboard as')"
            )
        except Exception:
            return False

    # ------------------------------------------------------------------
    # OTP auto-fetch
    # ------------------------------------------------------------------

    def _get_otp_from_gmail(self, after_epoch: int) -> str | None:
        """Poll Gmail for a fresh Blinkit OTP for up to OTP_WAIT_S seconds."""
        if not _fetch_otp:
            self._log.warning("[Blinkit] gmail_otp not available — cannot auto-fetch OTP")
            return None
        deadline = time.time() + OTP_WAIT_S
        attempt  = 0
        while time.time() < deadline:
            attempt += 1
            self._log.info("[Blinkit] Polling Gmail for OTP (attempt %d, %ds left)...",
                           attempt, int(deadline - time.time()))
            try:
                otp = _fetch_otp(sender=BLINKIT_OTP_SENDER, after_epoch=after_epoch)
                if otp:
                    self._log.info("[Blinkit] OTP received: %s", otp)
                    return otp
            except Exception as e:
                self._log.warning("[Blinkit] Gmail poll error: %s", e)
            if time.time() < deadline:
                time.sleep(10)
        self._log.warning("[Blinkit] OTP not received within %ds", OTP_WAIT_S)
        return None

    # ------------------------------------------------------------------
    # Company selector (appears after OTP submission)
    # ------------------------------------------------------------------

    def _handle_company_selector(self) -> None:
        """
        Handle the 'Access dashboard as' company selector.

        After OTP is verified, PartnersBiz shows a 'Login as <Company Name>'
        button for each company linked to the account. Click the first one.
        """
        if not self._is_on_company_selector():
            return

        self._log.info("[Blinkit] Company selector visible — looking for 'Login as' button")
        self._shot("company_selector")

        # The selector is an Ant Design list — each company is a list row with
        # company name + "manufacturer" badge and a chevron ">".
        # Strategy 1: Ant Design list item
        clicked = self._page.evaluate("""
            () => {
                // Try Ant Design list items first
                const antItems = Array.from(document.querySelectorAll(
                    '.ant-list-item, [class*="list-item"], [class*="company-item"], [class*="companyItem"]'
                )).filter(el => el.getBoundingClientRect().width > 0);

                if (antItems.length > 0) {
                    antItems[0].dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
                    return antItems[0].innerText.trim().substring(0, 80);
                }

                // Strategy 2: find the "manufacturer" badge and click its ancestor row
                const mfr = Array.from(document.querySelectorAll('*')).find(el => {
                    const txt = (el.innerText || '').trim().toLowerCase();
                    return txt === 'manufacturer' && el.getBoundingClientRect().width > 0;
                });
                if (mfr) {
                    let el = mfr.parentElement;
                    for (let i = 0; i < 6; i++) {
                        if (!el) break;
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 100 && rect.height > 30 && rect.height < 200) {
                            el.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
                            return el.innerText.trim().substring(0, 80);
                        }
                        el = el.parentElement;
                    }
                }

                // Strategy 3: any clickable row below the "Access dashboard as" heading
                const heading = Array.from(document.querySelectorAll('*')).find(el =>
                    (el.innerText || '').trim() === 'Access dashboard as' &&
                    el.getBoundingClientRect().width > 0
                );
                if (heading) {
                    const headingBottom = heading.getBoundingClientRect().bottom;
                    const candidates = Array.from(document.querySelectorAll('div, li, a')).filter(el => {
                        const rect = el.getBoundingClientRect();
                        const txt  = (el.innerText || '').trim();
                        return rect.top > headingBottom && rect.width > 100
                            && rect.height > 20 && rect.height < 150
                            && txt.length > 2 && !el.querySelector('ul, ol, nav');
                    }).sort((a, b) =>
                        a.getBoundingClientRect().top - b.getBoundingClientRect().top
                    );
                    if (candidates.length > 0) {
                        candidates[0].dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
                        return candidates[0].innerText.trim().substring(0, 80);
                    }
                }

                return null;
            }
        """)
        if clicked:
            self._log.info("[Blinkit] Selected company: %s", clicked)
        else:
            self._log.warning("[Blinkit] Could not find company row — manual action needed")
        self._page.wait_for_timeout(3000)

    # ------------------------------------------------------------------
    # Re-authentication (session expired)
    # ------------------------------------------------------------------

    def _re_auth(self) -> None:
        """
        Full OTP login flow. Called when the persistent profile session has expired.

        Requests OTP once, auto-fetches from Gmail, fills the 6-digit boxes,
        clicks Submit, handles company selector, waits for dashboard.
        """
        self._log.info("[Blinkit] Session expired — performing re-auth")

        # Navigate to login page
        self._page.goto(LOGIN_URL, wait_until="domcontentloaded")
        self._page.wait_for_timeout(3000)

        if self._is_logged_in():
            self._log.info("[Blinkit] Already logged in after navigation")
            return

        # Fill email
        try:
            email_input = self._page.locator('input[placeholder="Enter Email ID"]')
            email_input.wait_for(state="visible", timeout=10_000)
            email_input.fill(self._email)
            self._page.wait_for_timeout(500)
            self._log.info("[Blinkit] Filled email: %s", self._email)
        except Exception as e:
            self._shot("reauth_email_error")
            raise RuntimeError(f"[Blinkit] Cannot find email input: {e}")

        # Request OTP — ONCE
        self._log.info("[Blinkit] Requesting OTP...")
        otp_requested_at = int(time.time())
        self._page.locator('button:has-text("Request OTP")').click()
        self._page.wait_for_timeout(2000)

        # Wait for OTP boxes to appear
        try:
            self._page.locator('input[maxlength="1"]').first.wait_for(
                state="visible", timeout=15_000
            )
        except Exception:
            self._shot("reauth_otp_boxes_missing")
            raise RuntimeError("[Blinkit] OTP input boxes did not appear after requesting OTP")

        self._shot("reauth_otp_boxes_visible")

        # Fetch OTP from Gmail (only ONE OTP was requested above)
        otp = self._get_otp_from_gmail(after_epoch=otp_requested_at)
        if not otp:
            self._shot("reauth_otp_timeout")
            raise RuntimeError(
                "[Blinkit] Could not fetch OTP from Gmail. "
                "Check token.json and that email is delivered to pavan.kumar@solara.in"
            )

        # Enter OTP — click each individual box and type one digit at a time.
        # This is necessary because individual-character OTP inputs use JS listeners
        # that don't fire reliably with keyboard.type() on the first box alone.
        self._log.info("[Blinkit] Entering OTP: %s", otp)
        otp_boxes = self._page.locator('input[maxlength="1"]').all()
        self._log.info("[Blinkit] OTP boxes found: %d", len(otp_boxes))

        if len(otp_boxes) >= len(otp):
            # Per-box entry: click → press digit → move to next
            for i, digit in enumerate(otp):
                box = otp_boxes[i]
                box.click()
                box.press_sequentially(digit, delay=80)
                self._page.wait_for_timeout(80)
        else:
            # Fallback: press_sequentially on the first box (relies on auto-advance)
            self._log.warning(
                "[Blinkit] Fewer boxes (%d) than OTP digits (%d) — using press_sequentially",
                len(otp_boxes), len(otp),
            )
            otp_boxes[0].click()
            otp_boxes[0].press_sequentially(otp, delay=150)

        self._page.wait_for_timeout(800)

        # Verify fill
        filled = self._page.evaluate(
            "() => Array.from(document.querySelectorAll('input[maxlength=\"1\"]'))"
            ".map(i => i.value).join('')"
        )
        self._log.info("[Blinkit] OTP boxes after fill: '%s' (expected: '%s')", filled, otp)
        self._shot("reauth_otp_filled")

        # Submit OTP
        try:
            submit_btn = self._page.locator('button:has-text("Submit OTP")')
            submit_btn.wait_for(state="visible", timeout=5_000)
            submit_btn.click()
        except Exception:
            # Fallback: any enabled submit-like button
            self._page.locator('button[type="submit"], button:has-text("Verify")').first.click()
        self._page.wait_for_timeout(3000)
        self._shot("reauth_post_submit")

        # Handle company selector
        self._handle_company_selector()

        # Wait for dashboard
        try:
            self._page.wait_for_url(
                lambda u: "partnersbiz.com" in u
                          and "/login" not in u
                          and u.rstrip("/") != "https://partnersbiz.com",
                timeout=30_000,
            )
        except Exception:
            self._shot("reauth_dashboard_wait_failed")
            raise RuntimeError(
                f"[Blinkit] Did not reach dashboard after OTP. URL: {self._page.url}"
            )

        self._log.info("[Blinkit] Re-auth successful. Dashboard URL: %s", self._page.url)

    # ------------------------------------------------------------------
    # Login (check session, re-auth if needed)
    # ------------------------------------------------------------------

    def login(self) -> None:
        """
        Navigate to partnersbiz.com. Uses saved persistent profile — no OTP
        needed if the session is still valid. Falls back to full re-auth
        (OTP via Gmail) if the session has expired.
        """
        self._log.info("[Blinkit] Navigating to %s", LOGIN_URL)
        self._page.goto(LOGIN_URL, wait_until="domcontentloaded")
        self._page.wait_for_timeout(3000)

        if self._is_logged_in():
            self._log.info("[Blinkit] Session valid. Dashboard URL: %s", self._page.url)
            return

        # Company selector may appear without OTP if profile has partial session
        if self._is_on_company_selector():
            self._log.info("[Blinkit] Company selector appeared — selecting company")
            self._handle_company_selector()
            self._page.wait_for_timeout(2000)
            if self._is_logged_in():
                self._log.info("[Blinkit] Logged in after company selection. URL: %s",
                               self._page.url)
                return

        # Full re-auth
        self._re_auth()

    # ------------------------------------------------------------------
    # Navigate to SOH / Reports page
    # ------------------------------------------------------------------

    def _go_to_soh(self) -> None:
        """Navigate to the SOH page and verify session is active."""
        self._log.info("[Blinkit] Navigating to SOH page: %s", SOH_URL)
        self._page.goto(SOH_URL, wait_until="domcontentloaded")
        self._page.wait_for_timeout(4000)
        self._shot("soh_page")

        if not self._is_logged_in():
            raise RuntimeError(
                f"[Blinkit] Redirected to login when navigating to SOH. URL: {self._page.url}"
            )
        self._log.info("[Blinkit] SOH page loaded. URL: %s", self._page.url)

    # ------------------------------------------------------------------
    # Report download flow (confirmed steps):
    #   1. /app/sales → "Download Sales Data" button
    #   2. Set start date = end date = yesterday
    #   3. Click "Request Data"
    #   4. Poll /app/report-requests until row is ready → download
    # ------------------------------------------------------------------

    def _request_sales_report(self, report_date: date) -> None:
        """
        Navigate to /app/sales, click Download Sales Data,
        set date = report_date for both start and end, click Request Data.
        Only ONE request is made — no retries that would generate extra data.
        """
        date_str = report_date.strftime("%Y-%m-%d")
        self._log.info("[Blinkit] Navigating to /app/sales")
        self._page.goto("https://partnersbiz.com/app/sales", wait_until="domcontentloaded")
        self._page.wait_for_timeout(3000)
        self._shot("sales_page")

        # Dismiss any onboarding/blocking modal before interacting
        self._dismiss_modals()

        # Click "Download Sales Data" button
        self._log.info("[Blinkit] Looking for 'Download Sales Data' button")
        try:
            dl_btn = self._page.get_by_text("Download Sales Data", exact=True)
            dl_btn.wait_for(state="visible", timeout=10_000)
            dl_btn.click()
            self._page.wait_for_timeout(2000)
            self._shot("after_download_sales_click")
        except Exception as e:
            self._shot("download_sales_btn_missing")
            raise RuntimeError(f"[Blinkit] 'Download Sales Data' button not found: {e}")

        # Set date range using the Ant Design RangePicker.
        # The picker shows a calendar — click the correct day cell twice
        # (once for start, once for end) which auto-closes the picker.
        day        = report_date.day
        month_name = report_date.strftime("%b %Y")   # e.g. "Feb 2026"
        self._log.info("[Blinkit] Setting date range to %s (day %d)", date_str, day)

        # Open the range picker (click the first date input in the modal)
        try:
            date_input = self._page.locator('.ant-picker-input input').first
            date_input.wait_for(state="visible", timeout=8_000)
            date_input.click()
            self._page.wait_for_timeout(1000)
        except Exception as e:
            self._log.warning("[Blinkit] Could not click date input: %s", e)

        # Click the day cell in the calendar matching report_date.
        # Ant Design cells have title="YYYY-MM-DD" on the td element.
        # Click twice: once selects start date, second click selects end date.
        cell_clicked = self._page.evaluate("""
            (dateStr) => {
                // Ant Design date cells: td[title="YYYY-MM-DD"] or td with data-date
                const cell = document.querySelector(
                    `td[title="${dateStr}"], td[data-date="${dateStr}"], ` +
                    `td.ant-picker-cell[title*="${dateStr}"]`
                );
                if (cell && cell.getBoundingClientRect().width > 0) {
                    cell.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                    return true;
                }
                return false;
            }
        """, date_str)

        self._page.wait_for_timeout(600)

        if cell_clicked:
            # Click the same cell again to set end date = start date
            self._page.evaluate("""
                (dateStr) => {
                    const cell = document.querySelector(
                        `td[title="${dateStr}"], td[data-date="${dateStr}"], ` +
                        `td.ant-picker-cell[title*="${dateStr}"]`
                    );
                    if (cell) cell.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                }
            """, date_str)
            self._page.wait_for_timeout(600)
            self._log.info("[Blinkit] Clicked date cell %s (start + end)", date_str)
        else:
            # Fallback: type into inputs directly and press Enter to close picker
            self._log.warning("[Blinkit] Date cell not found, falling back to text input")
            inputs = self._page.locator('.ant-picker-input input').all()
            if len(inputs) >= 1:
                inputs[0].click()
                inputs[0].fill(date_str)
                self._page.keyboard.press("Enter")
                self._page.wait_for_timeout(400)
            if len(inputs) >= 2:
                inputs[1].click()
                inputs[1].fill(date_str)
                self._page.keyboard.press("Enter")
                self._page.wait_for_timeout(400)

        # If picker is still open, press Escape to close it
        try:
            if self._page.locator('.ant-picker-dropdown:not(.ant-picker-dropdown-hidden)').is_visible(timeout=1_000):
                self._log.info("[Blinkit] Picker still open — pressing Escape")
                self._page.keyboard.press("Escape")
                self._page.wait_for_timeout(500)
        except Exception:
            pass

        self._shot("after_date_set")
        self._log.info("[Blinkit] Date range set. Clicking 'Request Data'")

        # Click "Request Data"
        try:
            req_btn = self._page.get_by_text("Request Data", exact=True)
            req_btn.wait_for(state="visible", timeout=8_000)
            req_btn.click()
            self._page.wait_for_timeout(2000)
            self._shot("after_request_data")
            self._log.info("[Blinkit] Report requested successfully")
        except Exception as e:
            self._shot("request_data_btn_missing")
            raise RuntimeError(f"[Blinkit] 'Request Data' button not found: {e}")

    def _download_from_report_requests(self, report_date: date) -> "Path | None":
        """
        Navigate to /app/report-requests, poll until the report for
        report_date is ready, then download it.
        Returns the saved file path or None on timeout.
        """
        date_str = report_date.strftime("%Y-%m-%d")
        output_path = self.out_dir / f"blinkit_sales_{date_str}.xlsx"

        # Date format used in the Filters column of Report Requests table: DD-MM-YYYY
        date_str_filter = f"{report_date.day:02d}-{report_date.month:02d}-{report_date.year}"

        self._log.info("[Blinkit] Navigating to /app/report-requests")
        self._page.goto("https://partnersbiz.com/app/report-requests", wait_until="domcontentloaded")
        self._page.wait_for_timeout(3000)
        self._shot("report_requests_page")

        # Poll up to 10 minutes (20 × 30s) for the report to reach "success"
        max_polls = 20
        for poll in range(max_polls):
            self._log.info("[Blinkit] Polling report-requests (attempt %d/%d)", poll + 1, max_polls)

            # Check the table for a "Sales Details Excel" row matching our date with status "success"
            row_info = self._page.evaluate("""
                (dateFilter) => {
                    const rows = Array.from(document.querySelectorAll('tr'));
                    for (const row of rows) {
                        const cells = Array.from(row.querySelectorAll('td'));
                        if (cells.length < 4) continue;
                        const reportType = (cells[1]?.innerText || '').trim();
                        const status     = (cells[2]?.innerText || '').trim().toLowerCase();
                        const filters    = (cells[5]?.innerText || cells[4]?.innerText || '').trim();

                        if (!reportType.toLowerCase().includes('sales')) continue;
                        if (!filters.includes(dateFilter)) continue;

                        if (status === 'success') {
                            // Click the download icon in the Actions column (last td)
                            const actionsTd = cells[cells.length - 1];
                            const icon = actionsTd.querySelector('a, button, svg, [class*="action"], [class*="download"]');
                            if (icon && icon.getBoundingClientRect().width > 0) {
                                icon.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                                return {status: 'clicked', text: actionsTd.innerHTML.substring(0, 100)};
                            }
                            // Fallback: click any visible element in actions column
                            const anyEl = Array.from(actionsTd.querySelectorAll('*')).find(
                                el => el.getBoundingClientRect().width > 0
                            );
                            if (anyEl) {
                                anyEl.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                                return {status: 'clicked_fallback', text: anyEl.outerHTML.substring(0, 100)};
                            }
                            return {status: 'success_no_button'};
                        }

                        return {status: status};  // still processing / failed
                    }
                    return {status: 'not_found'};
                }
            """, date_str_filter)

            self._log.info("[Blinkit] Row status: %s", row_info)
            self._shot(f"report_poll_{poll + 1}")

            if row_info and row_info.get("status") in ("clicked", "clicked_fallback"):
                try:
                    with self._page.expect_download(timeout=30_000) as dl_info:
                        pass  # download was already triggered by JS above
                    dl = dl_info.value
                    dl.save_as(str(output_path))
                    self._log.info("[Blinkit] Downloaded: %s", output_path)
                    return output_path
                except Exception:
                    # JS click may have triggered download already — retry with explicit click
                    self._log.info("[Blinkit] expect_download missed — retrying download click")
                    try:
                        with self._page.expect_download(timeout=15_000) as dl_info:
                            self._page.evaluate("""
                                (dateFilter) => {
                                    const rows = Array.from(document.querySelectorAll('tr'));
                                    for (const row of rows) {
                                        const cells = Array.from(row.querySelectorAll('td'));
                                        if (cells.length < 4) continue;
                                        if (!(cells[5]?.innerText || cells[4]?.innerText || '').includes(dateFilter)) continue;
                                        const actionsTd = cells[cells.length - 1];
                                        const icon = actionsTd.querySelector('a, button, svg, [class*="action"]');
                                        if (icon) { icon.dispatchEvent(new MouseEvent('click', {bubbles: true})); return true; }
                                    }
                                    return false;
                                }
                            """, date_str_filter)
                        dl = dl_info.value
                        dl.save_as(str(output_path))
                        self._log.info("[Blinkit] Downloaded (retry): %s", output_path)
                        return output_path
                    except Exception as e2:
                        self._log.warning("[Blinkit] Download click failed: %s", e2)

            if row_info and row_info.get("status") == "success_no_button":
                self._log.warning("[Blinkit] Row is success but no download button found")
                self._shot("success_no_button")
                break

            if poll < max_polls - 1:
                self._log.info("[Blinkit] Waiting 30s before next poll...")
                self._page.wait_for_timeout(30_000)
                self._page.reload(wait_until="domcontentloaded")
                self._page.wait_for_timeout(2000)

        self._shot("report_requests_timeout")
        self._log.warning("[Blinkit] Report not ready after %d polls", max_polls)
        return None

    # ------------------------------------------------------------------
    # Legacy stubs kept for backward-compat (not used in main flow)
    # ------------------------------------------------------------------

    def _set_date_to_yesterday(self, report_date: date) -> None:
        """
        Set the date range to yesterday in the SOH date picker.

        TODO: Selector depends on dashboard UI — needs verification after auth.

        Common patterns seen in similar portals:
          - A calendar icon / date display that opens a picker on click
          - Bootstrap daterangepicker (same as EasyEcom)
          - A custom React/Angular date picker
          - Direct input fields with text type

        Current implementation tries common approaches in order.
        Update selectors once you've inspected the dashboard.
        """
        date_str_display = report_date.strftime("%d %b %Y")   # e.g. "19 Feb 2026"
        date_str_input   = report_date.strftime("%Y-%m-%d")   # e.g. "2026-02-19"
        self._log.info("[Blinkit] Setting date to: %s", date_str_display)

        # --- Strategy 1: Bootstrap daterangepicker (same as EasyEcom) ---
        drp_trigger = self._page.evaluate("""
            () => {
                const $ = window.jQuery || window.$;
                if (!$) return null;
                let trigger = null;
                $('*').each(function() {
                    if ($(this).data('daterangepicker')) { trigger = this; return false; }
                });
                if (trigger) {
                    const rect = trigger.getBoundingClientRect();
                    if (rect.width > 0) {
                        return {x: rect.left + rect.width/2, y: rect.top + rect.height/2, method: 'drp'};
                    }
                }
                return null;
            }
        """)
        if drp_trigger:
            self._page.mouse.click(drp_trigger['x'], drp_trigger['y'])
            self._page.wait_for_timeout(1000)
            # Try clicking "Yesterday" preset
            yesterday_coords = self._page.evaluate("""
                () => {
                    const picker = document.querySelector('.daterangepicker');
                    if (!picker || picker.getBoundingClientRect().width === 0) return null;
                    for (const li of picker.querySelectorAll('.ranges li')) {
                        if (li.textContent.trim() === 'Yesterday') {
                            const rect = li.getBoundingClientRect();
                            return {x: rect.left + rect.width/2, y: rect.top + rect.height/2};
                        }
                    }
                    return null;
                }
            """)
            if yesterday_coords:
                self._page.mouse.click(yesterday_coords['x'], yesterday_coords['y'])
                self._page.wait_for_timeout(500)
                self._log.info("[Blinkit] Date set via Bootstrap daterangepicker (Yesterday preset)")
                self._shot("after_date_set")
                return

        # --- Strategy 2: Input fields with type="date" or ISO format ---
        date_inputs = self._page.evaluate("""
            () => Array.from(document.querySelectorAll(
                'input[type="date"], input[name*="date" i], input[id*="date" i], ' +
                'input[placeholder*="date" i], input[placeholder*="from" i], ' +
                'input[placeholder*="start" i]'
            )).filter(el => el.getBoundingClientRect().width > 0)
              .map(el => ({
                  id: el.id, name: el.name, type: el.type,
                  placeholder: el.placeholder,
                  x: el.getBoundingClientRect().left + el.getBoundingClientRect().width/2,
                  y: el.getBoundingClientRect().top + el.getBoundingClientRect().height/2,
              }))
        """)
        if date_inputs:
            self._log.info("[Blinkit] Found %d date input(s) — filling with %s",
                           len(date_inputs), date_str_input)
            for inp in date_inputs[:2]:  # fill start + end with same date
                self._page.mouse.click(inp['x'], inp['y'])
                self._page.keyboard.select_all()
                self._page.keyboard.type(date_str_input)
            self._page.wait_for_timeout(500)
            self._shot("after_date_set")
            return

        # --- Strategy 3: Click any visible element that looks like a date display ---
        self._log.warning(
            "[Blinkit] TODO: Could not find date picker automatically. "
            "Run with headless=False and inspect the date picker element. "
            "Expected date: %s", date_str_display
        )
        self._shot("date_picker_not_found")

    # ------------------------------------------------------------------
    # Request / trigger the report download
    # ------------------------------------------------------------------

    def _request_report(self) -> None:
        """
        Click the download/export button on the SOH page.

        TODO: Verify selector after auth inspection.
        The SOH page likely has one of:
          a) A direct "Download" / "Export" button that triggers file download
          b) A "Request Report" flow (like EasyEcom) that queues a job
          c) A CSV export link that directly downloads the filtered data

        Common selectors for Blinkit-type portals:
          - button containing "Download" text
          - button containing "Export" text
          - An anchor with href containing 'download' or 'export'
        """
        self._log.info("[Blinkit] Looking for download/export button on SOH page")

        # Try common download button patterns
        download_selectors = [
            'button:has-text("Download")',
            'button:has-text("Export")',
            'button:has-text("Download CSV")',
            'button:has-text("Download Excel")',
            'button:has-text("Download Report")',
            'a:has-text("Download")',
            'a:has-text("Export")',
            '[data-testid*="download" i]',
            '[class*="download" i]',
            '[class*="export" i]',
        ]

        for selector in download_selectors:
            try:
                el = self._page.locator(selector).first
                if el.is_visible(timeout=2000):
                    self._log.info("[Blinkit] Clicking: %s", selector)
                    el.click()
                    self._page.wait_for_timeout(2000)
                    self._shot("after_download_click")
                    return
            except Exception:
                continue

        # Fallback: inspect all buttons for download-like text
        btn_info = self._page.evaluate("""
            () => Array.from(document.querySelectorAll('button, a'))
                .filter(el => {
                    const rect = el.getBoundingClientRect();
                    const txt  = (el.innerText || el.textContent || '').trim().toLowerCase();
                    return rect.width > 0 && (
                        txt.includes('download') || txt.includes('export') ||
                        txt.includes('csv') || txt.includes('excel') || txt.includes('report')
                    );
                })
                .map(el => ({
                    tag: el.tagName, text: el.innerText.trim().substring(0, 60),
                    href: el.getAttribute('href') || '',
                    cls:  el.className.substring(0, 60),
                }))
        """)
        self._log.info("[Blinkit] Download-like elements found: %s", btn_info)

        if not btn_info:
            self._shot("no_download_button")
            raise RuntimeError(
                "[Blinkit] TODO: Could not find download/export button on SOH page. "
                "Inspect the dashboard at " + SOH_URL + " and update _request_report() selectors."
            )

        # Click the first one we found
        first = btn_info[0]
        self._log.info("[Blinkit] Clicking first download-like element: %s", first)
        clicked = self._page.evaluate("""
            (target) => {
                const els = Array.from(document.querySelectorAll('button, a'));
                for (const el of els) {
                    const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
                    if (txt.includes(target.toLowerCase())) {
                        el.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                        return true;
                    }
                }
                return false;
            }
        """, first['text'])
        self._page.wait_for_timeout(3000)
        self._shot("after_download_click_fallback")

    # ------------------------------------------------------------------
    # Wait for and capture the download
    # ------------------------------------------------------------------

    def _download_report(self, report_date: date) -> "Path | None":
        """
        Trigger the SOH export and capture the downloaded file.

        This handles the common pattern where clicking an export button
        immediately triggers a file download (as opposed to the EasyEcom
        "queue then poll" pattern).

        TODO: Update to match the actual download mechanism after inspection.
        """
        date_str    = report_date.strftime("%Y-%m-%d")
        output_xlsx = self.out_dir / f"blinkit_sales_{date_str}.xlsx"
        output_csv  = self.out_dir / f"blinkit_sales_{date_str}.csv"

        self._log.info("[Blinkit] Waiting for download trigger...")

        # Strategy 1: expect_download wrapping the button click
        try:
            with self._page.expect_download(timeout=DOWNLOAD_TIMEOUT_S * 1000) as dl_handle:
                self._request_report()
            dl = dl_handle.value
            suggested = dl.suggested_filename or ""
            # Choose output path based on file type
            if suggested.lower().endswith(".csv"):
                out_path = output_csv
            else:
                out_path = output_xlsx
            dl.save_as(str(out_path))
            self._log.info("[Blinkit] Download complete: %s", out_path)
            return out_path
        except Exception as e1:
            self._log.info("[Blinkit] expect_download strategy failed: %s", e1)

        # Strategy 2: navigate directly to a download URL
        # TODO: Some portals expose a direct CSV download endpoint.
        # Uncomment and fill in once you've found the endpoint:
        #
        # download_url = (
        #     f"https://partnersbiz.com/api/soh/download"
        #     f"?start_date={date_str}&end_date={date_str}&format=csv"
        # )
        # try:
        #     with self._page.expect_download(timeout=60_000) as dl_handle:
        #         self._page.goto(download_url)
        #     dl = dl_handle.value
        #     dl.save_as(str(output_csv))
        #     return output_csv
        # except Exception as e2:
        #     self._log.warning("[Blinkit] Direct URL download also failed: %s", e2)

        self._shot("download_failed")
        raise RuntimeError(
            "[Blinkit] Could not download report. "
            "The SOH page selectors need to be updated. "
            "Run with headless=False and inspect download flow."
        )

    # ------------------------------------------------------------------
    # Dashboard inspector (useful for initial setup)
    # ------------------------------------------------------------------

    def inspect_dashboard(self) -> dict:
        """
        Navigate to the SOH page and log all interactive elements.
        Call this after a successful auth to discover the correct selectors
        for the date picker and download button.

        Usage:
            scraper = BlinkitScraper(headless=False)
            scraper._init_browser()
            scraper.login()
            info = scraper.inspect_dashboard()
        """
        self._go_to_soh()
        self._shot("inspect_soh_loaded")

        info = self._page.evaluate("""
            () => {
                const buttons = Array.from(document.querySelectorAll('button')).map(el => ({
                    text: el.innerText.trim().substring(0, 80),
                    cls:  el.className.substring(0, 80),
                    id:   el.id,
                    visible: el.getBoundingClientRect().width > 0,
                })).filter(b => b.visible);

                const inputs = Array.from(document.querySelectorAll('input')).map(el => ({
                    type:        el.type,
                    name:        el.name,
                    id:          el.id,
                    placeholder: el.placeholder,
                    value:       el.value.substring(0, 40),
                    visible:     el.getBoundingClientRect().width > 0,
                })).filter(i => i.visible);

                const links = Array.from(document.querySelectorAll('a[href]')).map(el => ({
                    text: el.innerText.trim().substring(0, 60),
                    href: el.getAttribute('href'),
                    visible: el.getBoundingClientRect().width > 0,
                })).filter(l => l.visible).slice(0, 20);

                const selects = Array.from(document.querySelectorAll('select')).map(el => ({
                    name:    el.name,
                    id:      el.id,
                    options: Array.from(el.options).map(o => o.text).slice(0, 10),
                    visible: el.getBoundingClientRect().width > 0,
                })).filter(s => s.visible);

                return {buttons, inputs, links, selects, url: window.location.href, title: document.title};
            }
        """)

        self._log.info("[Blinkit] --- Dashboard inspection ---")
        self._log.info("[Blinkit] URL:     %s", info.get('url'))
        self._log.info("[Blinkit] Title:   %s", info.get('title'))
        self._log.info("[Blinkit] Buttons: %s", info.get('buttons'))
        self._log.info("[Blinkit] Inputs:  %s", info.get('inputs'))
        self._log.info("[Blinkit] Links:   %s", info.get('links'))
        self._log.info("[Blinkit] Selects: %s", info.get('selects'))
        return info

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self, report_date: date = None) -> dict:
        """Full scraping cycle. Returns status dict."""
        if report_date is None:
            report_date = date.today() - timedelta(days=1)

        result = {
            "portal":  self.portal_name,
            "date":    report_date,
            "file":    None,
            "status":  "failed",
            "error":   None,
        }

        try:
            from scrapers.profile_sync import download_profile, upload_profile
        except ImportError:
            from profile_sync import download_profile, upload_profile

        login_ok = False
        try:
            # Pull latest profile from Drive before launching browser (no-op if not configured)
            download_profile("blinkit")

            self._init_browser()
            self.login()
            login_ok = True
            self._go_to_soh()

            # Snapshot session cookies to disk immediately after reaching SOH.
            # This acts as a checkpoint — if the download flow crashes, the session
            # is preserved on disk so the next run can reuse it without OTP.
            session_path = _HERE / "sessions" / "blinkit_session.json"
            session_path.parent.mkdir(parents=True, exist_ok=True)
            self._ctx.storage_state(path=str(session_path))
            self._log.info("[Blinkit] Session snapshot saved to %s", session_path)

            self._request_sales_report(report_date)
            file_path = self._download_from_report_requests(report_date)
            result.update({"file": file_path, "status": "success"})

            # Upload to Google Drive: SolaraDashboard Reports / YYYY-MM / Blinkit /
            if _upload_to_drive and file_path:
                drive_link = _upload_to_drive(
                    portal="Blinkit",
                    report_date=report_date,
                    file_path=file_path,
                )
                if drive_link:
                    result["drive_link"] = drive_link
                    self._log.info("[Blinkit] Uploaded to Drive: %s", drive_link)

        except Exception as exc:
            self._log.error("[Blinkit] Run failed: %s", exc)
            result["error"] = str(exc)
        finally:
            self._close_browser()
            # Only upload profile if login succeeded — avoids overwriting Drive with a failed session
            if login_ok:
                upload_profile("blinkit")

        return result


# ------------------------------------------------------------------
# CLI entry point for manual testing and inspection
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

    parser = argparse.ArgumentParser(description="Blinkit scraper")
    parser.add_argument(
        "--inspect", action="store_true",
        help="Run dashboard inspection instead of full scrape (use after first auth)"
    )
    parser.add_argument(
        "--headless", action="store_true", default=False,
        help="Run headless (default: headed for debugging)"
    )
    args = parser.parse_args()

    scraper = BlinkitScraper(headless=args.headless)

    if args.inspect:
        scraper._init_browser()
        try:
            scraper.login()
            info = scraper.inspect_dashboard()
            print("\n=== DASHBOARD INSPECTION COMPLETE ===")
            print("Update selectors in _set_date_to_yesterday() and _request_report()")
            print("based on the logged buttons/inputs/links above.")
        finally:
            scraper._close_browser()
    else:
        result = scraper.run()
        print("\nResult:", result)
