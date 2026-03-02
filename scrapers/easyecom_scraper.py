"""
EasyEcom Sales Details scraper.

Login strategy:
  - Uses a persistent Chrome profile (scrapers/sessions/easyecom_profile/) so Google OAuth
    auto-completes on every run without entering credentials.
  - Must do a fresh Google OAuth each run because the PHP session for
    sales_dashboard.php is short-lived (~24 min). Google auto-approves
    using the stored Google session in the profile.

Report flow:
  1. Fresh Google OAuth -> dashboard
  2. Navigate to sales_dashboard.php
  3. Dismiss "New Features" popup (appears on every navigation, JS click)
  4. Set date range to yesterday
  5. Click Queue Report -> select Sales_Report -> Submit
  6. Poll Exports panel until the new report is Complete
  7. Click View More -> download latest Sales_Report
"""

import io
import os
import sys
import time
import zipfile
from datetime import date, timedelta
from pathlib import Path


try:
    from .google_drive_upload import upload_to_drive as _upload_to_drive
except ImportError:
    # Running as __main__ (standalone) — relative imports don't work, use path directly
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

# Force UTF-8 output to avoid Windows cp1252 encoding errors (skip on Linux CI)
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# --- Paths ---
_HERE = Path(__file__).resolve().parent
# Module-level constant kept for backward-compat; run() always calls _profile_dir().
PROFILE_DIR = (_HERE / "sessions" / "easyecom_profile").resolve()


def _profile_dir() -> Path:
    """Return the resolved path of the EasyEcom Chrome profile directory."""
    return (_HERE / "sessions" / "easyecom_profile").resolve()

# --- URLs ---
LOGIN_URL = "https://app.easyecom.io/V2/account/auth/login"
SALES_URL = "https://app.easyecom.io/V2/sales_dashboard.php"

# --- Timing ---
DOWNLOAD_TIMEOUT_S = 900   # max seconds to wait for report to be ready (CI can take 5-10 min)
POLL_INTERVAL_S    = 10    # seconds between polls


class EasyecomBaseScraper:
    """Shared browser lifecycle and login logic for all EasyEcom scrapers."""

    portal_name: str  # defined by subclass

    def __init__(self, headless: bool = True, raw_data_path: str = None):
        self.headless = headless
        self.raw_data_path = Path(raw_data_path or os.getenv("RAW_DATA_PATH", "./data/raw"))
        self.out_dir = self.raw_data_path / self.portal_name
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._log = __import__("logging").getLogger(f"scrapers.{self.portal_name}")

    # ------------------------------------------------------------------
    # Browser lifecycle
    # ------------------------------------------------------------------

    def _init_browser(self):
        import json
        from playwright.sync_api import sync_playwright
        profile = _profile_dir()
        if not profile.exists():
            raise RuntimeError(
                f"EasyEcom Chrome profile not found at {profile}. "
                "Run auth_easyecom.py first to set up the profile."
            )

        # If a portable session JSON exists, clear the OS-encrypted Cookies DB
        # so that Chromium (especially on Linux CI with a Windows-created profile)
        # doesn't try to decrypt it and fail. The JSON cookies will be injected instead.
        session_file = profile.parent / "easyecom_session.json"
        if session_file.exists():
            cookies_db = profile / "Default" / "Cookies"
            if cookies_db.exists():
                cookies_db.unlink()
                self._log.info("[EasyEcom] Cleared encrypted cookie DB; will restore from session JSON")

        self._pw = sync_playwright().__enter__()
        self._ctx = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            headless=self.headless,
            slow_mo=300 if not self.headless else 0,
            args=["--start-maximized"] if not self.headless else [],
            viewport={"width": 1400, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        )

        # Inject platform-independent cookies (decrypted JSON — works on any OS)
        if session_file.exists():
            try:
                state = json.loads(session_file.read_text())
                cookies = state.get("cookies", [])
                if cookies:
                    self._ctx.add_cookies(cookies)
                    self._log.info("[EasyEcom] Injected %d cookies from session JSON", len(cookies))
            except Exception as exc:
                self._log.warning("[EasyEcom] Could not inject session cookies: %s", exc)

        self._page = self._ctx.new_page()
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
            path = self.out_dir / f"debug_{label}_{int(time.time())}.png"
            self._page.screenshot(path=str(path))
            self._log.debug("Screenshot: %s", path)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Popup dismissal (New Features modal, appears on every navigation)
    # ------------------------------------------------------------------

    def _dismiss_popups(self) -> None:
        """Dismiss the 'New Features' modal. Its Close button has class 'new-ui-outline-btn'."""
        try:
            dismissed = self._page.evaluate("""
                () => {
                    const btn = document.querySelector(
                        'button.new-ui-outline-btn, button[class*="new-ui-outline"]'
                    );
                    if (btn) {
                        btn.dispatchEvent(
                            new MouseEvent('click', {bubbles: true, cancelable: true, view: window})
                        );
                        return 'dismissed';
                    }
                    return 'not-found';
                }
            """)
            if dismissed == 'dismissed':
                self._log.info("[EasyEcom] Dismissed 'New Features' popup")
                self._page.wait_for_timeout(1500)
            else:
                self._log.debug("[EasyEcom] 'New Features' popup not present")
        except Exception as e:
            self._log.debug("[EasyEcom] Popup dismiss error: %s", e)

    # ------------------------------------------------------------------
    # Login: fresh Google OAuth via persistent profile
    # ------------------------------------------------------------------

    def login(self, _max_attempts: int = 3) -> None:
        """
        Always do a fresh Google OAuth. Google auto-approves using the
        Google session stored in the Chrome profile. This re-establishes
        the PHP session that EasyEcom requires.

        Retries up to _max_attempts times because the first attempt
        sometimes fails (Google OAuth redirects briefly to the dashboard,
        then EasyEcom bounces back to login before the PHP session is
        established). A retry with the refreshed Google cookies succeeds.
        """
        last_error = None
        for attempt in range(1, _max_attempts + 1):
            try:
                self._try_login(attempt)
                return  # success
            except RuntimeError as exc:
                last_error = exc
                if attempt < _max_attempts:
                    self._log.warning(
                        "[EasyEcom] Login attempt %d/%d failed: %s — retrying in 5s",
                        attempt, _max_attempts, exc,
                    )
                    self._page.wait_for_timeout(5000)
                else:
                    raise

    def _try_login(self, attempt: int = 1) -> None:
        """Single login attempt — navigate, click Google, wait for redirect."""
        self._log.info("[EasyEcom] Navigating to login page (attempt %d)", attempt)
        self._page.goto(LOGIN_URL, wait_until="domcontentloaded")
        self._page.wait_for_timeout(2000)

        self._log.info("[EasyEcom] Clicking Continue with Google (auto via profile)")
        try:
            self._page.wait_for_selector(
                'button:has-text("Continue with Google")', timeout=15_000
            )
        except Exception:
            self._shot("login_btn_not_found")
            raise RuntimeError("EasyEcom login page: 'Continue with Google' button not found.")

        self._page.click('button:has-text("Continue with Google")')

        self._log.info("[EasyEcom] Waiting for dashboard redirect...")
        # In visible mode give 5 min for manual Google login; in headless CI 60s is enough.
        wait_timeout = 60_000 if self.headless else 300_000
        try:
            # Use startswith to avoid matching accounts.google.com URLs that contain
            # easyecom.io in the redirect_uri parameter (false positive on expired sessions).
            self._page.wait_for_url(
                lambda u: u.startswith("https://app.easyecom.io") and "/account/auth/" not in u,
                timeout=wait_timeout,
            )
        except Exception:
            if "multiple-signin" in self._page.url:
                self._log.warning("[EasyEcom] Account selection page — waiting 60s for user action")
                self._page.wait_for_url(
                    lambda u: u.startswith("https://app.easyecom.io") and "/account/auth/" not in u,
                    timeout=60_000,
                )
            else:
                self._shot("login_timeout")
                raise RuntimeError(f"EasyEcom login timeout. URL: {self._page.url}")

        self._page.wait_for_timeout(3000)

        # Post-login verification: the page may briefly redirect to the dashboard
        # then bounce back to login if the PHP session wasn't established.
        current_url = self._page.url
        if "/account/auth/" in current_url:
            self._shot("login_bounce_back")
            raise RuntimeError(
                f"EasyEcom login appeared to succeed but page redirected back to login. "
                f"URL: {current_url}. Google OAuth session in the profile may have expired — "
                f"run auth_easyecom.py locally to refresh it."
            )
        self._log.info("[EasyEcom] Logged in. Dashboard URL: %s", current_url)


class EasyecomScraper(EasyecomBaseScraper):
    """Downloads the daily Sales_Report from EasyEcom Sales Details."""

    portal_name = "easyecom"

    # ------------------------------------------------------------------
    # Navigate to Sales Details
    # ------------------------------------------------------------------

    def _go_to_sales_page(self) -> None:
        self._log.info("[EasyEcom] Navigating to sales_dashboard.php")
        self._page.goto(SALES_URL, wait_until="networkidle")
        # Wait for Angular to finish rendering + any async modals to appear
        self._page.wait_for_timeout(4000)
        self._dismiss_popups()
        self._page.wait_for_timeout(1000)
        self._shot("sales_page_ready")
        # Verify the form loaded (not "Please login first")
        body_text = ""
        try:
            body_text = self._page.inner_text("body")
        except Exception:
            pass
        if "Please login first" in body_text:
            raise RuntimeError(
                "Sales Details page shows 'Please login first' — "
                "PHP session was not established. Try re-running auth_easyecom.py."
            )

    # ------------------------------------------------------------------
    # Set yesterday's date in the daterangepicker
    # ------------------------------------------------------------------

    def _set_date_to_yesterday(self, report_date: date) -> None:
        self._log.info("[EasyEcom] Setting date to yesterday: %s", report_date)

        # Dismiss any popup that may have re-opened
        self._dismiss_popups()

        # Use real mouse clicks via page.mouse.click() (isTrusted=true events).
        # dispatchEvent/jQuery API both fail to update the visible date display;
        # only real mouse interaction triggers the daterangepicker's callback chain.

        # Step 1: Click the visible date display trigger to open the picker.
        # Use jQuery to find the element that has the daterangepicker attached to it,
        # then click its center coordinates. This is more reliable than DOM walking.
        trigger_coords = self._page.evaluate("""
            () => {
                // Method 1: Use jQuery to find the element with daterangepicker data
                const $ = window.jQuery || window.$;
                if ($) {
                    let trigger = null;
                    $('*').each(function() {
                        if ($(this).data('daterangepicker')) { trigger = this; return false; }
                    });
                    if (trigger) {
                        const rect = trigger.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {
                            return {x: rect.left + rect.width / 2, y: rect.top + rect.height / 2,
                                    method: 'jquery', tag: trigger.tagName, w: Math.round(rect.width)};
                        }
                    }
                }
                // Method 2: Fallback — walk up DOM from daterangepicker hidden input
                const inp = document.querySelector('input[name="daterangepicker_start"]');
                if (inp) {
                    let el = inp.parentElement;
                    while (el && el !== document.body) {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 30 && rect.height > 10 && rect.height < 120) {
                            return {x: rect.left + rect.width / 2, y: rect.top + rect.height / 2,
                                    method: 'dom_walk', tag: el.tagName, w: Math.round(rect.width)};
                        }
                        el = el.parentElement;
                    }
                }
                return null;
            }
        """)
        if not trigger_coords:
            self._log.warning("[EasyEcom] Could not find daterangepicker trigger element")
            self._shot("after_date_set")
            return

        self._page.mouse.click(trigger_coords['x'], trigger_coords['y'])
        self._log.info("[EasyEcom] Clicked date picker trigger via %s at (%.0f, %.0f) w=%s",
                       trigger_coords.get('method', '?'), trigger_coords['x'], trigger_coords['y'],
                       trigger_coords.get('w', '?'))
        self._page.wait_for_timeout(1500)
        self._shot("daterangepicker_opened")

        # Step 2: Click the "Yesterday" preset in the now-open picker panel.
        yesterday_coords = self._page.evaluate("""
            () => {
                const picker = document.querySelector('.daterangepicker');
                if (!picker) return null;
                const pRect = picker.getBoundingClientRect();
                if (pRect.width === 0) return null;
                for (const li of picker.querySelectorAll('.ranges li')) {
                    if (li.textContent.trim() === 'Yesterday') {
                        const rect = li.getBoundingClientRect();
                        if (rect.width > 0) {
                            return {x: rect.left + rect.width / 2, y: rect.top + rect.height / 2};
                        }
                    }
                }
                return null;
            }
        """)
        if not yesterday_coords:
            self._log.warning("[EasyEcom] 'Yesterday' preset not visible in open picker")
            self._shot("after_date_set")
            return

        self._page.mouse.click(yesterday_coords['x'], yesterday_coords['y'])
        self._log.info("[EasyEcom] Clicked 'Yesterday' preset")
        self._page.wait_for_timeout(500)

        # Step 3: Click Apply button if still shown (some configs require explicit apply).
        # Inspector confirmed: for this site, clicking Yesterday auto-applies (Apply w=0).
        apply_coords = self._page.evaluate("""
            () => {
                const btn = document.querySelector('.daterangepicker .applyBtn');
                if (!btn) return null;
                const rect = btn.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                    return {x: rect.left + rect.width / 2, y: rect.top + rect.height / 2};
                }
                return null;
            }
        """)
        if apply_coords:
            self._page.mouse.click(apply_coords['x'], apply_coords['y'])
            self._log.info("[EasyEcom] Clicked Apply button")
            self._page.wait_for_timeout(500)

        self._page.wait_for_timeout(500)
        self._shot("after_date_set")

        # Step 4: VERIFY the date is actually set to yesterday before returning.
        # This prevents queueing a report for the wrong date.
        expected_str = report_date.strftime("%m/%d/%Y")
        actual_value = self._page.evaluate("""
            () => {
                const inp = document.querySelector('input[name="daterangepicker_start"]');
                return inp ? inp.value : '';
            }
        """)
        self._log.info("[EasyEcom] Date verification: expected=%s actual=%s",
                       expected_str, actual_value)
        if actual_value != expected_str:
            raise RuntimeError(
                f"Date was not set correctly! Expected {expected_str}, got {actual_value!r}. "
                "Will NOT queue report to avoid downloading today's data."
            )

    # ------------------------------------------------------------------
    # Queue the report
    # ------------------------------------------------------------------

    def _queue_report(self) -> None:
        self._log.info("[EasyEcom] Queuing Sales_Report")

        # Dismiss any popup before clicking Queue Report
        self._dismiss_popups()

        # Log the date variables that queueMiniReport() will use for start_date/end_date.
        # These outer-scope vars (a, b) are set by the daterangepicker apply callback.
        ab_info = self._page.evaluate("""
            () => {
                try {
                    return {a: typeof a !== 'undefined' ? String(a) : 'undef',
                            b: typeof b !== 'undefined' ? String(b) : 'undef'};
                } catch(e) { return {error: e.message}; }
            }
        """)
        self._log.info("[EasyEcom] Date vars before queue: a=%s b=%s", ab_info.get('a'), ab_info.get('b'))

        # Register a dialog handler to capture the AJAX response alert.
        # queueMiniReport() calls alert(data.trim()) on success — Playwright auto-dismisses
        # unhandled dialogs, so we register a handler to log the server's response text.
        alert_messages = []

        def on_dialog(dialog):
            msg = dialog.message
            alert_messages.append(msg)
            self._log.info("[EasyEcom] Queue AJAX response alert: %r", msg)
            dialog.accept()

        self._page.on('dialog', on_dialog)

        try:
            # Strategy 1 (most reliable): call window.queueMiniReport() directly.
            # Confirmed by inspector: the visible "Queue Report" button has
            # onclick="queueMiniReport()" and is NOT a dropdown toggle.
            # The actual dropdown toggle is hidden (display:none).
            direct_result = self._page.evaluate("""
                () => {
                    if (typeof window.queueMiniReport === 'function') {
                        try {
                            window.queueMiniReport();
                            return 'called';
                        } catch(e) {
                            return 'error: ' + String(e);
                        }
                    }
                    return 'not_found';
                }
            """)
            self._log.info("[EasyEcom] queueMiniReport() direct call: %s", direct_result)

            if direct_result == 'called':
                # Wait for the AJAX POST to complete and alert to fire
                self._page.wait_for_timeout(5000)
                self._shot("after_queue")
                if alert_messages:
                    self._log.info("[EasyEcom] Server confirmed: %r", alert_messages[0])
                return

            # Strategy 2: click the button directly (its onclick calls queueMiniReport()).
            # The button is id="primaryDropdownMenuButton" with onclick="queueMiniReport()".
            self._log.info("[EasyEcom] queueMiniReport not global — clicking #primaryDropdownMenuButton")
            btn_info = self._page.evaluate("""
                () => {
                    const btn = document.querySelector('#primaryDropdownMenuButton')
                        || Array.from(document.querySelectorAll('button')).find(b => {
                            const r = b.getBoundingClientRect();
                            return b.textContent.trim() === 'Queue Report' && r.top > 100 && r.width > 0;
                        });
                    if (!btn) return {found: false};
                    const r = btn.getBoundingClientRect();
                    return {found: true, x: r.left + r.width/2, y: r.top + r.height/2};
                }
            """)

            if not btn_info.get('found'):
                self._shot("queue_btn_not_found")
                raise RuntimeError("Could not find Queue Report button and queueMiniReport() is unavailable")

            self._page.mouse.click(btn_info['x'], btn_info['y'])
            self._page.wait_for_timeout(5000)
            self._shot("after_queue")
            if alert_messages:
                self._log.info("[EasyEcom] Server confirmed (click): %r", alert_messages[0])

        finally:
            try:
                self._page.remove_listener('dialog', on_dialog)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Wait for export completion and download
    # ------------------------------------------------------------------

    # Export Jobs page URL (confirmed by inspector10)
    EXPORTS_URL = "https://app.easyecom.io/V2/reports/import-export-report?jobType=1"

    def _find_and_download_report(self, report_date: date, queued_at: float) -> Path:
        """
        Poll the Export Jobs page until a miniSalesReportDownload is complete,
        then download it.

        Confirmed by inspector10:
          URL: /V2/reports/import-export-report?jobType=1
          Table: Report Name | Job Name | Marketplace | Started At | Ended At |
                 Processing Time | Status | Message | Action
          Report name contains: 'miniSalesReportDownload'
        """
        date_str    = report_date.strftime("%Y-%m-%d")
        deadline    = time.time() + DOWNLOAD_TIMEOUT_S
        # EasyEcom downloads a ZIP containing the CSV; we save it as .zip first,
        # then _extract_csv_from_zip() extracts it and renames to .csv
        output_path = self.out_dir / f"easyecom_sales_{date_str}.zip"

        self._log.info("[EasyEcom] Polling Export Jobs page for miniSalesReportDownload")

        while time.time() < deadline:
            try:
                if self.EXPORTS_URL in self._page.url:
                    self._page.reload(wait_until="domcontentloaded", timeout=30_000)
                else:
                    self._page.goto(self.EXPORTS_URL, wait_until="domcontentloaded",
                                    timeout=30_000)
            except Exception as nav_err:
                self._log.warning("[EasyEcom] Nav error: %s", nav_err)
                time.sleep(5)
                continue

            self._page.wait_for_timeout(2000)
            self._dismiss_popups()
            self._shot("exports_panel")

            # Log table content for diagnostics
            table_rows = self._page.evaluate("""
                () => Array.from(document.querySelectorAll('table tr'))
                    .slice(0, 8)
                    .map(r => (r.innerText || '').trim().replace(/\\t+/g, ' | ').substring(0, 150))
            """)
            self._log.info("[EasyEcom] Export table: %s", table_rows[:4])

            # Look for a completed miniSalesReportDownload row.
            # Table headers (confirmed by inspector):
            #   [0] Report Name  [1] Job Name  [2] Marketplace
            #   [3] Download Started At  [4] Download Ended At
            #   [5] Total Processing Time  [6] Status  [7] Message  [8] Action
            dl_info = self._page.evaluate("""
                () => {
                    const rows = Array.from(document.querySelectorAll('table tr'));
                    for (const row of rows) {
                        const cells = Array.from(row.querySelectorAll('td'));
                        if (cells.length < 5) continue;

                        // Check if any cell contains 'miniSalesReportDownload'
                        const hasMini = cells.some(td =>
                            (td.innerText || '').includes('miniSalesReportDownload')
                        );
                        if (!hasMini) continue;

                        const cellTexts = cells.map(c => (c.innerText || '').trim());
                        const fullText  = cellTexts.join(' ').toLowerCase();

                        // In-progress / pending check — use STATUS column (index 6) only,
                        // NOT fullText, to avoid false positives from "Total Processing Time"
                        // column which may contain "processing" even on completed rows.
                        const statusText = (cellTexts[6] || '').toLowerCase();
                        const inProgress = statusText.includes('in-progress')
                            || statusText.includes('in progress')
                            || statusText.includes('pending')
                            || statusText.includes('processing')
                            || statusText.includes('queued')
                            || statusText.includes('new')
                            || statusText.includes('running')
                            || statusText.includes('generating');
                        if (inProgress) {
                            return {not_ready: true, status: statusText, cellTexts};
                        }

                        // Completion check 1: "Download Ended At" column (index 4) is non-empty
                        const endedAt = cellTexts[4] || '';
                        const hasEndedAt = endedAt.length > 2
                            && endedAt !== '-' && endedAt.toLowerCase() !== 'n/a';

                        // Completion check 2: Status column (index 6) contains keywords
                        const hasCompletionKw = statusText.includes('complet')
                            || statusText.includes('success')
                            || statusText.includes('processed')
                            || statusText.includes('ready')
                            || statusText.includes('done')
                            || statusText.includes('finish')
                            || statusText.includes('exported')
                            || statusText.includes('generated');

                        if (!hasEndedAt && !hasCompletionKw) {
                            return {not_ready: true, status: 'unknown: ' + statusText, cellTexts};
                        }

                        // Row is complete — find download link in Action column (last td)
                        const actionCell = cells[cells.length - 1];
                        const allLinks = Array.from(
                            actionCell.querySelectorAll('a, button, [onclick]')
                        );

                        // Scroll row into view so getBoundingClientRect works
                        row.scrollIntoView({block: 'center', inline: 'nearest'});

                        for (const link of allLinks) {
                            const rect = link.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {
                                return {
                                    ready: true,
                                    cellTexts,
                                    linkText: link.textContent.trim()
                                              || link.title
                                              || link.getAttribute('data-original-title')
                                              || '(icon)',
                                    href:    link.getAttribute('href') || '',
                                    onclick: link.getAttribute('onclick') || '',
                                    x: rect.left + rect.width  / 2,
                                    y: rect.top  + rect.height / 2,
                                };
                            }
                        }

                        // No visible link — return debug info
                        return {
                            ready_no_link: true,
                            cellTexts,
                            allLinkDebug: allLinks.map(l => ({
                                text:    l.textContent.trim().substring(0, 40),
                                href:    l.getAttribute('href') || '',
                                onclick: l.getAttribute('onclick') || '',
                                cls:     l.className || '',
                            })),
                        };
                    }
                    return null;
                }
            """)

            if dl_info is None:
                self._log.info("[EasyEcom] No miniSalesReportDownload row found yet")
            elif dl_info.get('not_ready'):
                self._log.info("[EasyEcom] Report not ready [%s]: %s",
                               dl_info.get('status'), dl_info.get('cellTexts', []))
            elif dl_info.get('ready_no_link'):
                self._log.warning("[EasyEcom] Complete but no visible download link. Cells=%s Links=%s",
                                  dl_info.get('cellTexts'), dl_info.get('allLinkDebug'))
            elif dl_info.get('ready'):
                self._log.info("[EasyEcom] Report ready — link=%r href=%s onclick=%s",
                               dl_info.get('linkText'), dl_info.get('href'), dl_info.get('onclick'))

                # Log action cell HTML to understand the button structure
                action_html = self._page.evaluate("""
                    () => {
                        for (const row of document.querySelectorAll('table tr')) {
                            const cells = Array.from(row.querySelectorAll('td'));
                            if (cells.some(td => (td.innerText||'').includes('miniSalesReportDownload'))) {
                                return cells[cells.length - 1].innerHTML.substring(0, 300);
                            }
                        }
                        return '';
                    }
                """)
                self._log.info("[EasyEcom] Action cell HTML: %s", action_html)

                result = self._try_download(dl_info, output_path)
                if result:
                    return result

            self._log.info("[EasyEcom] Waiting %ds...", POLL_INTERVAL_S)
            time.sleep(POLL_INTERVAL_S)

        self._shot("download_timeout")
        raise RuntimeError(
            f"EasyEcom miniSalesReportDownload not ready after {DOWNLOAD_TIMEOUT_S}s. "
            f"Check {self.EXPORTS_URL} manually."
        )

    def _extract_csv_from_zip(self, zip_path: Path) -> Path:
        """
        EasyEcom downloads a ZIP containing a single CSV.
        Extract it in-place and return the CSV path.
        """
        if not zipfile.is_zipfile(str(zip_path)):
            self._log.info("[EasyEcom] Downloaded file is not a ZIP — using as-is")
            return zip_path

        with zipfile.ZipFile(str(zip_path)) as zf:
            csv_names = [n for n in zf.namelist() if n.lower().endswith('.csv')]
            if not csv_names:
                self._log.warning("[EasyEcom] ZIP has no CSV inside: %s", zf.namelist())
                return zip_path
            csv_name = csv_names[0]
            csv_path = zip_path.with_suffix('.csv')
            with zf.open(csv_name) as src, open(str(csv_path), 'wb') as dst:
                dst.write(src.read())
            self._log.info("[EasyEcom] Extracted %s -> %s", csv_name, csv_path)

        zip_path.unlink()   # Remove the zip once extracted
        return csv_path

    def _try_download(self, dl_info: dict, output_path: Path) -> "Path | None":
        """
        Download the report by dispatching a JS MouseEvent on the Angular download button.

        The download button (class='download_result') has no href — it's an Angular
        Material element whose click handler calls window.open() which opens a popup
        page that immediately starts the file download.

        page.mouse.click() does NOT trigger this (Playwright's CDP click doesn't go
        through Angular's zone.js change detection for window.open). dispatchEvent()
        with bubbles=true works because Angular's event listener on the element fires.

        Strategy 1: JS dispatchEvent click → new popup page download (confirmed working)
        Strategy 2: standard page.mouse.click with expect_download (fallback)
        """
        new_pages = []

        def on_new_page(page):
            new_pages.append(page)
            self._log.debug("[EasyEcom] New popup opened: %s", page.url)

        self._ctx.on('page', on_new_page)

        try:
            # --- Strategy 1 (primary): JS dispatchEvent click → popup download ---
            try:
                with self._page.expect_download(timeout=15_000) as dl_handle:
                    self._page.evaluate("""
                        () => {
                            for (const row of document.querySelectorAll('table tr')) {
                                const cells = Array.from(row.querySelectorAll('td'));
                                if (cells.some(td =>
                                        (td.innerText||'').includes('miniSalesReportDownload'))) {
                                    const actionCell = cells[cells.length - 1];
                                    const link = actionCell.querySelector('a.download_result, a, button');
                                    if (link) {
                                        link.dispatchEvent(new MouseEvent('click',
                                            {bubbles: true, cancelable: true, view: window}));
                                    }
                                    return;
                                }
                            }
                        }
                    """)
                dl = dl_handle.value
                dl.save_as(str(output_path))
                self._log.info("[EasyEcom] Download complete: %s", output_path)
                return self._extract_csv_from_zip(output_path)
            except Exception as e1:
                self._log.info("[EasyEcom] Strategy 1 failed: %s", e1)

            # Wait a moment for any popup page to appear
            self._page.wait_for_timeout(2000)

            # --- Strategy 2: standard mouse.click + expect_download ---
            try:
                self._log.info("[EasyEcom] Fallback: mouse.click + expect_download")
                with self._page.expect_download(timeout=15_000) as dl_handle:
                    self._page.mouse.click(dl_info['x'], dl_info['y'])
                dl = dl_handle.value
                dl.save_as(str(output_path))
                self._log.info("[EasyEcom] Download complete (strategy 2): %s", output_path)
                return self._extract_csv_from_zip(output_path)
            except Exception as e2:
                self._log.warning("[EasyEcom] All download strategies failed: S1=%s S2=%s. "
                                  "New pages: %s", e1, e2, [p.url for p in new_pages])
                return None

        finally:
            try:
                self._ctx.remove_listener('page', on_new_page)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self, report_date: date = None) -> dict:
        """Full scraping cycle. Returns status dict."""
        if report_date is None:
            report_date = date.today() - timedelta(days=1)

        result = {
            "portal": self.portal_name,
            "date": report_date,
            "file": None,
            "status": "failed",
            "error": None,
        }

        try:
            from scrapers.profile_sync import (
                download_profile, upload_profile,
                download_session_file, upload_session_file,
            )
        except ImportError:
            from profile_sync import (
                download_profile, upload_profile,
                download_session_file, upload_session_file,
            )

        login_ok = False
        try:
            # Pull latest profile + portable session cookies from Drive
            download_profile("easyecom")
            download_session_file("easyecom")  # platform-independent JSON cookies

            self._init_browser()
            self.login()
            login_ok = True

            # Persist platform-independent session state so the next CI run
            # (potentially on a different OS) can inject the cookies directly.
            import json
            session_file = _profile_dir().parent / "easyecom_session.json"
            try:
                state = self._ctx.storage_state()
                session_file.write_text(json.dumps(state))
                self._log.info("[EasyEcom] Saved session state (%d cookies)", len(state.get("cookies", [])))
            except Exception as exc:
                self._log.warning("[EasyEcom] Could not save session state: %s", exc)

            self._go_to_sales_page()
            self._set_date_to_yesterday(report_date)   # raises if date not set correctly
            queued_at = time.time()
            self._queue_report()
            file_path = self._find_and_download_report(report_date, queued_at)
            result.update({"file": file_path, "status": "success"})

            # Upload to Google Drive: SolaraDashboard Reports / YYYY-MM / EasyEcom /
            if _upload_to_drive and file_path:
                drive_link = _upload_to_drive(
                    portal="EasyEcom",
                    report_date=report_date,
                    file_path=file_path,
                )
                if drive_link:
                    result["drive_link"] = drive_link
                    self._log.info("[EasyEcom] Uploaded to Drive: %s", drive_link)
        except Exception as exc:
            self._log.error("[EasyEcom] Run failed: %s", exc)
            result["error"] = str(exc)
        finally:
            self._close_browser()
            # Only upload profile/session if login succeeded — avoids overwriting Drive with a failed session
            if login_ok:
                upload_profile("easyecom")
                upload_session_file("easyecom")  # platform-independent JSON cookies

        return result


# ------------------------------------------------------------------
# CLI entry point for manual testing
# ------------------------------------------------------------------
if __name__ == "__main__":
    import logging
    from dotenv import load_dotenv
    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    scraper = EasyecomScraper(headless=False)
    result  = scraper.run()
    print("\nResult:", result)
