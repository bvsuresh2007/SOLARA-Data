"""
Amazon PI (pi.amazon.in) scraper.

Flow:
  Phase 1 – For each of 6 categories:
    1. Navigate to https://pi.amazon.in/reports/sbg
    2. Brand = SOLARA  |  Category = <target>
    3. Downloads section → select "ASIN wise revenue and unit sales"
    4. Daily tab → set From = To = yesterday
    5. Click "Generate Excel" (queues report)

  Phase 2 – Download Center:
    1. Navigate to https://pi.amazon.in/download-center
    2. Refresh until all 6 reports show "Completed"
    3. Filter/identify rows by: brand=SOLARA, category, report name, date, status
    4. Click Download Link for each → save to data/raw/amazon_pi/<date>/

Session persistence:
  Uses a persistent Chrome profile (scrapers/sessions/amazon_pi_profile/) so the
  session survives between runs. On re-run, if already logged in, login is skipped.

Standalone (visible, keeps browser open after login):
  python scrapers/amazon_pi_scraper.py
"""

import logging
import os
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

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

_HERE = Path(__file__).resolve().parent
PROFILE_DIR = (_HERE / "sessions" / "amazon_pi_profile").resolve()

CATEGORIES = [
    "Kitchen Appliances",
    "Storage And Containers",
    "Cookware",
    "Kitchen Tools",
    "Toys-School Supplies",
    "Tableware",
]

REPORT_TYPE = "ASIN-wise Sales & Indexed GVs at a City Level"


class AmazonPIScraper:
    """Scraper for Amazon PI (pi.amazon.in)."""

    portal_name = "amazon_pi"

    def __init__(self, headless: bool = False, raw_data_path: str = None):  # headless=False: new React UI hangs in headless mode
        self.headless = headless
        self.raw_data_path = Path(raw_data_path or os.getenv("RAW_DATA_PATH", "./data/raw"))
        self.out_dir = self.raw_data_path / self.portal_name
        self.out_dir.mkdir(parents=True, exist_ok=True)

        self.login_url = os.environ["AMAZON_PI_LINK"]
        self.email     = os.environ["AMAZON_PI_EMAIL"]
        self.password  = os.environ["AMAZON_PI_PASSWORD"]
        self._log = logging.getLogger("scrapers.amazon_pi")

    # ------------------------------------------------------------------
    # Browser lifecycle
    # ------------------------------------------------------------------

    def _init_browser(self):
        from playwright.sync_api import sync_playwright
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().__enter__()
        self._ctx = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
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
            self._pw.stop()
        except Exception:
            pass

    def _shot(self, label: str):
        try:
            path = self.out_dir / f"debug_{label}_{int(time.time())}.png"
            self._page.screenshot(path=str(path))
            self._log.info("Screenshot: %s", path)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def login(self) -> None:
        self._log.info("[AmazonPI] Navigating to %s", self.login_url)
        try:
            self._page.goto(self.login_url, wait_until="domcontentloaded", timeout=30_000)
        except Exception:
            # login_url (e.g. brand-summary) may time out if that page no longer exists.
            # Fall back to reports/sbg which is always reachable when logged in.
            self._log.info("[AmazonPI] login_url timed out — retrying with reports/sbg")
            self._page.goto("https://pi.amazon.in/reports/sbg", wait_until="domcontentloaded",
                            timeout=45_000)

        if self._page.url.startswith("https://pi.amazon.in"):
            self._log.info("[AmazonPI] Session active — skipping login. URL: %s", self._page.url)
            return

        self._log.info("[AmazonPI] Waiting for login page")
        # Amazon uses #ap_email on the classic form, or a generic input on the
        # new "Sign in or create account" combined flow.
        try:
            email_input = self._page.locator(
                '#ap_email, input[name="loginID"], input[type="email"]'
            ).first
            email_input.wait_for(state="visible", timeout=15_000)
        except Exception:
            if self._page.url.startswith("https://pi.amazon.in"):
                return
            self._shot("email_field_missing")
            raise RuntimeError(f"[AmazonPI] Login page not found. URL: {self._page.url}")

        self._log.info("[AmazonPI] Entering email")
        email_input.fill(self.email)
        # Click Continue/Submit — Amazon may show "Continue" or "Sign-In" button
        self._page.locator(
            'input[type="submit"], input#continue, span#continue'
        ).first.click()

        self._log.info("[AmazonPI] Entering password")
        pwd = self._page.locator('#ap_password, input[name="password"]').first
        pwd.wait_for(state="visible", timeout=15_000)
        pwd.fill(self.password)
        self._page.locator(
            '#signInSubmit, input[type="submit"]'
        ).first.click()

        # TOTP
        try:
            otp_input = self._page.locator('#auth-mfa-otpcode, input[name="otpCode"]')
            otp_input.wait_for(state="visible", timeout=8_000)
            self._log.info("[AmazonPI] TOTP screen — generating code")
            code = self._get_totp_code()
            self._log.info("[AmazonPI] Filling TOTP: %s", code)
            otp_input.fill(code)
            self._page.locator('#auth-signin-button, input[type="submit"]').first.click()
        except Exception as exc:
            if "timeout" not in str(exc).lower():
                self._log.warning("[AmazonPI] OTP step error: %s", exc)

        self._log.info("[AmazonPI] Waiting for PI dashboard")
        try:
            self._page.wait_for_url("https://pi.amazon.in/**", timeout=30_000)
        except Exception:
            self._shot("post_login_redirect")
            raise RuntimeError(f"[AmazonPI] Login failed. URL: {self._page.url}")

        self._log.info("[AmazonPI] Login complete — %s", self._page.url)

    def _get_totp_code(self) -> str:
        try:
            from scrapers.totp_helper import get_totp_code
        except ImportError:
            import importlib.util as _ilu
            _spec = _ilu.spec_from_file_location("totp_helper", Path(__file__).parent / "totp_helper.py")
            _mod = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)
            get_totp_code = _mod.get_totp_code
        return get_totp_code("AMAZON_PI_TOTP_SECRET")

    # ------------------------------------------------------------------
    # Phase 1 — Generate reports for all categories
    # ------------------------------------------------------------------

    def download_report(self, report_date: date = None) -> list:
        """
        Full flow: generate Excel for all 6 categories, then download from Download Center.
        Returns list of downloaded file paths.

        Key design: navigate to SBG ONCE, set Brand ONCE, set Time Period ONCE, then
        iterate categories using only the category dropdown (AJAX, same page).  This
        preserves the Time Period state across categories, avoiding the issue where the
        modal fails to open for categories whose chart data doesn't load quickly.
        """
        if report_date is None:
            report_date = date.today() - timedelta(days=1)

        self._log.info("[AmazonPI] Starting report generation for %s", report_date)

        # ── Navigate once ──────────────────────────────────────────────
        self._page.goto("https://pi.amazon.in/reports/sbg", wait_until="domcontentloaded")

        # ── Brand = SOLARA ─────────────────────────────────────────────
        # Amazon PI changed from native <select> to a custom button listbox.
        # We must click the button and re-select SOLARA to trigger the data load.
        brand_btn = self._page.locator('[data-testid="undefined-brand-dropdown"] button')
        brand_btn.wait_for(state="visible", timeout=30_000)
        brand_text = brand_btn.inner_text().strip()
        self._log.info("[AmazonPI]   Brand button visible: %s — clicking to trigger data load", brand_text)
        brand_btn.click()
        self._page.wait_for_timeout(1500)
        # Select exact "SOLARA" from the listbox (not "Essentials by SOLARA" which has no data).
        listbox = self._page.locator('[role="listbox"]')
        listbox.wait_for(state="visible", timeout=10_000)
        options = listbox.locator('[role="option"]')
        solara_option = None
        for i in range(options.count()):
            if options.nth(i).inner_text().strip() == "SOLARA":
                solara_option = options.nth(i)
                break
        if solara_option is None:
            solara_option = options.filter(has_text=re.compile(r"^SOLARA$", re.I)).first
        # Use JS click for option (rendered in <div id="portal"> overlay)
        solara_option.evaluate("el => el.click()")
        self._log.info("[AmazonPI]   Brand = SOLARA selected")

        # Page re-renders after brand selection — wait for content to load.
        # #aue-time-period-option appears once chart data is ready (~15s).
        self._page.wait_for_timeout(5000)
        try:
            self._page.wait_for_load_state("networkidle", timeout=30_000)
        except Exception:
            pass
        self._page.locator('#aue-time-period-option').wait_for(state="visible", timeout=120_000)
        self._page.wait_for_timeout(1000)

        # ── Set Time Period ONCE (before any category switch) ──────────
        self._set_time_period(report_date)

        # ── Iterate categories via dropdown — no page.goto() between them ──
        # Storage And Containers needs a wider date range (the Generate Excel button
        # doesn't render for single-day period). Process it last with a 15-day range.
        storage_cat = "Storage And Containers"
        for category in CATEGORIES:
            if category == storage_cat:
                continue  # handle separately below
            try:
                self._generate_for_category(category, report_date)
            except Exception as exc:
                self._log.error("[AmazonPI] Category %s failed: %s", category, exc)
                self._shot(f"error_{category[:6].replace(' ', '_')}")

        # ── Storage And Containers: full page reload + fresh setup ──
        # The Generate Excel button doesn't render when switching categories via dropdown.
        # Fix: reload the SBG page fresh, select category FIRST, then set time period.
        try:
            self._log.info("[AmazonPI] Full page reload for %s", storage_cat)

            # Reload the SBG page completely — fresh DOM state
            self._page.goto("https://pi.amazon.in/reports/sbg",
                            wait_until="domcontentloaded", timeout=30_000)
            try:
                self._page.wait_for_load_state("networkidle", timeout=20_000)
            except Exception:
                pass
            self._page.wait_for_timeout(3000)

            # Re-select Brand = SOLARA (page reload resets brand to default)
            brand_btn = self._page.locator('[data-testid="undefined-brand-dropdown"] button')
            brand_btn.wait_for(state="visible", timeout=30_000)
            brand_btn.click()
            self._page.wait_for_timeout(1500)
            listbox = self._page.locator('[role="listbox"]')
            listbox.wait_for(state="visible", timeout=10_000)
            opts = listbox.locator('[role="option"]')
            for i in range(opts.count()):
                if opts.nth(i).inner_text().strip() == "SOLARA":
                    opts.nth(i).evaluate("el => el.click()")
                    break
            self._log.info("[AmazonPI]   Brand = SOLARA re-selected after reload")
            self._page.wait_for_timeout(5000)

            # Wait for time period section to appear (page fully loaded after brand selection)
            self._page.locator('#aue-time-period-option').wait_for(
                state="visible", timeout=120_000)
            self._page.wait_for_timeout(1000)

            # Select Storage And Containers
            # force=True click to bypass overlay, then JS for option
            cat_btn = self._page.locator('[data-testid="sbg-category-dropdown"] button')
            cat_btn.wait_for(state="visible", timeout=30_000)
            cat_btn.click(force=True)
            # Wait for listbox options to render
            self._page.wait_for_function(
                "() => document.querySelectorAll('[role=\"option\"]').length > 0",
                timeout=15_000,
            )
            self._page.wait_for_timeout(500)
            opt_result = self._page.evaluate("""(cat) => {
                const options = document.querySelectorAll('[role="option"]');
                for (const opt of options) {
                    if (opt.innerText && opt.innerText.trim().toLowerCase().includes(cat.toLowerCase())) {
                        opt.click();
                        return {selected: true, text: opt.innerText.trim()};
                    }
                }
                return {selected: false, texts: Array.from(options).map(o => o.innerText?.trim())};
            }""", storage_cat)
            if not opt_result.get("selected"):
                raise RuntimeError(f"Category '{storage_cat}' not found: {opt_result.get('texts')}")
            self._log.info("[AmazonPI]   Category = %s", storage_cat)

            # Select ALL sub-categories
            self._select_all_subcategories()

            # Wait for page to settle after category + subcategory selection
            try:
                self._page.wait_for_load_state("networkidle", timeout=20_000)
            except Exception:
                pass
            self._page.wait_for_timeout(3000)

            # Set time period (single day)
            self._set_time_period(report_date)

            # Wait again after time period for download section to render
            try:
                self._page.wait_for_load_state("networkidle", timeout=20_000)
            except Exception:
                pass
            self._page.wait_for_timeout(5000)

            # Now scroll to download section, select report type, and try Generate Excel
            self._page.evaluate("""
                const el = document.querySelector('#aue-report-download');
                if (el) el.scrollIntoView({behavior: 'instant', block: 'center'});
                else window.scrollTo(0, document.body.scrollHeight);
            """)
            self._page.wait_for_timeout(2000)

            # Select the correct report type
            storage_dl_section = self._page.locator('#aue-report-download')
            self._select_report_type(storage_dl_section)
            self._page.wait_for_timeout(1000)

            # Dump what we see
            result = self._page.evaluate("""() => {
                const section = document.querySelector('#aue-report-download');
                if (!section) return {found: false, html: 'NO SECTION'};
                const btns = section.querySelectorAll('button');
                const btnTexts = [];
                for (const btn of btns) {
                    btnTexts.push(btn.innerText?.trim() || '(empty)');
                    if (btn.innerText && btn.innerText.trim().includes('Generate Excel')) {
                        btn.scrollIntoView({block: 'center'});
                        btn.click();
                        return {found: true, btnTexts: btnTexts};
                    }
                }
                return {found: false, btnTexts: btnTexts, html: section.innerHTML.substring(0, 800)};
            }""")

            if result.get("found"):
                self._log.info("[AmazonPI]   Generate Excel clicked via JS for %s", storage_cat)
                self._shot(f"after_gen_{storage_cat[:6].replace(' ', '_')}")
            else:
                self._log.info("[AmazonPI]   Buttons found: %s", result.get("btnTexts"))
                self._log.info("[AmazonPI]   Section HTML: %s", result.get("html", "")[:800])
                self._shot(f"no_gen_{storage_cat[:6].replace(' ', '_')}")
                raise RuntimeError("Generate Excel not found for " + storage_cat)

        except Exception as exc:
            self._log.error("[AmazonPI] Category %s failed: %s", storage_cat, exc)
            self._shot(f"error_{storage_cat[:6].replace(' ', '_')}")

        self._log.info("[AmazonPI] All generation requests queued. Moving to Download Center.")
        files = self._download_from_center(report_date)
        return files

    def _generate_for_category(self, category: str, report_date: date) -> None:
        """Switch category dropdown and click Generate Excel.  Time Period is already set.

        Confirmed selectors (from live page inspection 2026-02-23):
          Category:      select#category-dropdown
          Download type: select#download-dropdown
          Generate Excel: a.a-button-text containing "Generate Excel"
        """
        self._log.info("[AmazonPI] Generating: %s — %s", category, report_date)

        # Dismiss any open dropdown overlay from previous category
        self._page.keyboard.press("Escape")
        self._page.wait_for_timeout(300)
        # Also click body to close any React portal overlay
        self._page.evaluate("() => { document.body.click(); }")
        self._page.wait_for_timeout(300)

        # ── Set category — custom button listbox (data-testid="sbg-category-dropdown") ──
        # Uses JS click because React portal (<div id="portal">) renders the listbox
        # options in an overlay that intercepts Playwright's standard click.
        self._page.wait_for_function(
            "() => { const b = document.querySelector('[data-testid=\"sbg-category-dropdown\"] button'); "
            "return b && !b.disabled; }",
            timeout=60_000,
        )
        # force=True click to open dropdown (bypasses overlay actionability checks)
        cat_btn = self._page.locator('[data-testid="sbg-category-dropdown"] button')
        cat_btn.click(force=True)
        # Wait for listbox options to render
        self._page.wait_for_function(
            "() => document.querySelectorAll('[role=\"option\"]').length > 0",
            timeout=15_000,
        )
        self._page.wait_for_timeout(500)
        # JS click to select option (bypasses <div id="portal"> overlay)
        opt_result = self._page.evaluate("""(cat) => {
            const options = document.querySelectorAll('[role="option"]');
            for (const opt of options) {
                if (opt.innerText && opt.innerText.trim().toLowerCase().includes(cat.toLowerCase())) {
                    opt.click();
                    return {selected: true, text: opt.innerText.trim()};
                }
            }
            return {selected: false, texts: Array.from(options).map(o => o.innerText?.trim())};
        }""", category)
        if not opt_result.get("selected"):
            raise RuntimeError(f"Category '{category}' not found in dropdown: {opt_result.get('texts')}")
        self._log.info("[AmazonPI]   Category = %s", category)

        # Select ALL sub-categories (default only selects top N, missing some ASINs)
        self._select_all_subcategories()

        # Wait for AJAX to settle (chart data loads for this category).
        # Some categories (e.g. Storage And Containers) take 5+ seconds for the
        # download section to render after category switch.
        try:
            self._page.wait_for_load_state("networkidle", timeout=20_000)
        except Exception:
            pass
        self._page.wait_for_timeout(3000)

        # Wait for the download section to exist in the DOM before scrolling
        try:
            self._page.locator('#aue-report-download').wait_for(state="attached", timeout=15_000)
        except Exception:
            self._log.info("[AmazonPI]   #aue-report-download not in DOM yet — waiting longer")
            self._page.wait_for_timeout(5000)

        # ── Scroll to Downloads section (#aue-report-download) ────────
        # The download section is deep below the fold (y~1900). Scroll aggressively.
        self._page.evaluate("""
            const el = document.querySelector('#aue-report-download')
                    || document.querySelector('button#multi-select-simple-button')
                    || document.querySelector('[id*="download"]');
            if (el) el.scrollIntoView({behavior: 'instant', block: 'center'});
            else window.scrollTo(0, document.body.scrollHeight);
        """)
        self._page.wait_for_timeout(2000)

        # ── Select the correct report type from the dropdown ──────────
        # The default may be "ASIN-wise Sales & Indexed GVs at a City Level" (41 ASINs).
        # We need "ASIN wise revenue and unit sales" (118 ASINs — full data).
        download_section = self._page.locator('#aue-report-download')
        self._select_report_type(download_section)
        self._page.wait_for_timeout(400)

        # ── Generate Excel ─────────────────────────────────────────────
        # The button exists in #aue-report-download but Playwright's scroll_into_view
        # can timeout (30s) if an overlay/modal blocks it. Use JS click as primary method.
        gen_found = False

        # Dismiss any success toast/banner from previous category's Generate Excel
        try:
            dismiss = self._page.locator('button:has-text("Dismiss"), button[aria-label="Close"], button:has-text("OK"), button:has-text("×")')
            if dismiss.count() > 0:
                dismiss.first.click(timeout=2_000)
                self._page.wait_for_timeout(500)
        except Exception:
            pass

        # Method 1 (most reliable): JS DOM click — bypasses Playwright overlay checks
        try:
            result = self._page.evaluate("""() => {
                const section = document.querySelector('#aue-report-download');
                if (!section) return {found: false, html: 'NO SECTION'};
                const btns = section.querySelectorAll('button');
                const btnTexts = [];
                for (const btn of btns) {
                    btnTexts.push(btn.innerText?.trim() || '(empty)');
                    if (btn.innerText && btn.innerText.trim().includes('Generate Excel')) {
                        btn.scrollIntoView({block: 'center'});
                        btn.click();
                        return {found: true, btnTexts: btnTexts};
                    }
                }
                return {found: false, btnTexts: btnTexts, html: section.innerHTML.substring(0, 500)};
            }""")
            if result.get("found"):
                gen_found = True
                self._log.info("[AmazonPI]   Generate Excel clicked via JS for %s", category)
            else:
                self._log.info("[AmazonPI]   JS: buttons in section = %s", result.get("btnTexts"))
                self._log.info("[AmazonPI]   JS: section HTML = %s", result.get("html", "")[:500])
                # Maybe Generate Excel is a sibling, not inside #aue-report-download
                try:
                    sib = self._page.evaluate("""() => {
                        const section = document.querySelector('#aue-report-download');
                        if (!section) return {found: false};
                        // Check next sibling
                        let el = section.nextElementSibling;
                        while (el) {
                            const btns = el.querySelectorAll('button');
                            for (const btn of btns) {
                                if (btn.innerText && btn.innerText.trim().includes('Generate')) {
                                    btn.scrollIntoView({block: 'center'});
                                    btn.click();
                                    return {found: true, text: btn.innerText.trim()};
                                }
                            }
                            el = el.nextElementSibling;
                        }
                        // Check parent's children
                        const parent = section.parentElement;
                        if (parent) {
                            const allBtns = parent.querySelectorAll('button');
                            for (const btn of allBtns) {
                                if (btn.innerText && btn.innerText.trim().includes('Generate')) {
                                    btn.scrollIntoView({block: 'center'});
                                    btn.click();
                                    return {found: true, text: btn.innerText.trim(), loc: 'parent'};
                                }
                            }
                        }
                        return {found: false, parentHTML: parent ? parent.innerHTML.substring(0, 800) : 'no parent'};
                    }""")
                    if sib.get("found"):
                        gen_found = True
                        self._log.info("[AmazonPI]   Generate Excel clicked via sibling JS for %s (btn=%s)", category, sib.get("text"))
                    else:
                        self._log.info("[AmazonPI]   Sibling search: %s", str(sib.get("parentHTML", ""))[:400])
                except Exception as e:
                    self._log.info("[AmazonPI]   Sibling search failed: %s", str(e)[:80])
        except Exception as e:
            self._log.info("[AmazonPI]   JS click failed: %s", str(e)[:80])

        # Method 2: Playwright locator with force click (skips actionability checks)
        if not gen_found:
            try:
                dl_sec = self._page.locator('#aue-report-download')
                gen_btn = dl_sec.locator('button:has-text("Generate Excel")')
                gen_btn.first.click(force=True, timeout=10_000)
                gen_found = True
                self._log.info("[AmazonPI]   Generate Excel clicked (force) for %s", category)
            except Exception as e:
                self._log.info("[AmazonPI]   Force click failed: %s", str(e)[:80])

        # Method 3: page-wide role search
        if not gen_found:
            try:
                gen_btn2 = self._page.get_by_role("button", name="Generate Excel", exact=False)
                gen_btn2.click(force=True, timeout=10_000)
                gen_found = True
                self._log.info("[AmazonPI]   Generate Excel clicked (role+force) for %s", category)
            except Exception:
                pass

        if not gen_found:
            self._log.error("[AmazonPI]   Generate Excel NOT found for %s", category)
            self._shot(f"no_gen_{category[:6].replace(' ', '_')}")
            raise RuntimeError(f"Generate Excel not found for {category}")

        self._log.info("[AmazonPI]   Generate Excel clicked for %s", category)
        self._page.wait_for_timeout(3000)
        self._shot(f"after_gen_{category[:6].replace(' ', '_')}")

    def _set_time_period(self, report_date: date) -> None:
        """
        Open the Time Period popper and set From = To = report_date (single day, Daily tab).

        Updated for Amazon PI UI redesign (2026-03-26):
          Trigger:     button nth(1) inside #aue-time-period-option
                       (nth(0) is the info tooltip — clicking it opens a tooltip, not the picker)
          Popper:      id='time-period-popper' (role="dialog")
          Daily tab:   [role="button"] text="Daily" in sidebar nav
          Start/End:   calendar icon buttons (aria-label="Start date" / "End date")
                       → opens id='start-date-popper' / id='end-date-popper'
                       → day buttons: aria-label like "Wednesday March 25 2026"
          Apply btn:   button text="Apply" inside time-period-popper
        """
        date_str = report_date.strftime("%d/%m/%Y")
        self._log.info("[AmazonPI]   Setting time period to %s", date_str)

        # Open the Time Period popper — click the date-range button (index 1),
        # NOT index 0 which is the info tooltip button.
        tp_section = self._page.locator('#aue-time-period-option')
        tp_section.scroll_into_view_if_needed()
        date_range_btn = tp_section.locator('button').nth(1)
        date_range_btn.wait_for(state="visible", timeout=15_000)
        date_range_btn.click()

        popper = self._page.locator('#time-period-popper')
        popper.wait_for(state="visible", timeout=15_000)
        self._log.info("[AmazonPI]   Time Period popper opened")
        self._shot("tp_opened")

        # Ensure Daily granularity is selected (sidebar nav item).
        daily_li = popper.locator('[role="button"]', has_text="Daily")
        daily_li.wait_for(state="visible", timeout=5_000)
        daily_li.click()
        self._page.wait_for_timeout(300)

        # Set Start and End dates via calendar icon buttons.
        # The date inputs are readonly — must click the calendar icon to open
        # a date-popper and click the day cell.
        self._pick_date_calendar("Start", report_date)
        self._page.wait_for_timeout(500)
        self._pick_date_calendar("End", report_date)
        self._page.wait_for_timeout(500)

        self._shot("tp_dates_filled")

        # Click Apply button inside the popper.
        apply_btn = popper.get_by_role("button", name="Apply")
        apply_btn.wait_for(state="visible", timeout=5_000)
        apply_btn.click()
        self._log.info("[AmazonPI]   Time Period applied: %s", report_date.strftime("%d/%m/%Y"))
        self._page.wait_for_timeout(2000)
        self._shot("tp_done")

    def _select_all_subcategories(self) -> None:
        """
        Open the sub-category dropdown (#aue-subcategory-option) and select ALL options.

        Amazon PI defaults to showing only the top N sub-categories (e.g. 3 of 6 for
        Storage And Containers). This causes missing ASINs in the downloaded report.

        The dropdown has checkboxes for each sub-category, a "Clear all" button,
        and "Apply"/"Cancel" buttons. We click each unchecked checkbox, then Apply.
        """
        subcat_section = self._page.locator('#aue-subcategory-option')
        try:
            subcat_section.wait_for(state="visible", timeout=10_000)
        except Exception:
            self._log.info("[AmazonPI]   No sub-category section found — skipping")
            return

        # Check current selection text
        current_text = subcat_section.inner_text().strip()
        self._log.info("[AmazonPI]   Sub-category: %s", current_text[:100])

        # Open the dropdown (button inside the section)
        subcat_btn = subcat_section.locator('button[aria-haspopup]').first
        try:
            subcat_btn.wait_for(state="visible", timeout=5_000)
        except Exception:
            self._log.info("[AmazonPI]   No sub-category dropdown button — skipping")
            return

        subcat_btn.click(force=True)
        self._page.wait_for_timeout(1000)

        # Click all unchecked checkboxes via JS
        result = self._page.evaluate("""() => {
            // Find the portal/listbox that just opened
            const portal = document.querySelector('#portal');
            if (!portal) return {clicked: 0, error: 'no portal'};

            const checkboxes = portal.querySelectorAll('input[type="checkbox"]');
            let clicked = 0;
            let total = checkboxes.length;

            for (const cb of checkboxes) {
                if (!cb.checked) {
                    cb.click();
                    clicked++;
                }
            }

            // If no <input> checkboxes, try role="checkbox" buttons
            if (total === 0) {
                const roleCheckboxes = portal.querySelectorAll('[role="checkbox"]');
                total = roleCheckboxes.length;
                for (const cb of roleCheckboxes) {
                    if (cb.getAttribute('aria-checked') !== 'true') {
                        cb.click();
                        clicked++;
                    }
                }
            }

            // If still no checkboxes found, look for list items that can be clicked
            if (total === 0) {
                const items = portal.querySelectorAll('[role="option"]');
                total = items.length;
                for (const item of items) {
                    if (item.getAttribute('aria-selected') !== 'true') {
                        item.click();
                        clicked++;
                    }
                }
            }

            return {clicked, total};
        }""")
        self._log.info("[AmazonPI]   Sub-categories: checked %d more (total %d)",
                       result.get("clicked", 0), result.get("total", 0))

        self._page.wait_for_timeout(500)

        # Click Apply button
        apply_result = self._page.evaluate("""() => {
            const portal = document.querySelector('#portal');
            if (!portal) return {found: false};
            const buttons = portal.querySelectorAll('button');
            for (const btn of buttons) {
                if (btn.innerText && btn.innerText.trim() === 'Apply') {
                    btn.click();
                    return {found: true};
                }
            }
            return {found: false};
        }""")

        if apply_result.get("found"):
            self._log.info("[AmazonPI]   Sub-category Apply clicked — all sub-categories selected")
        else:
            self._log.warning("[AmazonPI]   Apply button not found in sub-category dropdown")
            # Try to dismiss
            self._page.keyboard.press("Escape")

        self._page.wait_for_timeout(2000)

    def _select_report_type(self, download_section) -> None:
        """
        Verify the correct report type is selected in the download section.
        The default is "ASIN-wise Sales & Indexed GVs at a City Level" which is what we want.
        Only changes it if a different type is selected.
        """
        try:
            current_text = download_section.evaluate("""(section) => {
                const btn = section.querySelector('button[aria-haspopup="listbox"]');
                return btn ? btn.innerText.trim() : '';
            }""")
            self._log.info("[AmazonPI]   Report type: %s", current_text)

            if REPORT_TYPE.lower() in current_text.lower():
                self._log.info("[AmazonPI]   Report type correct — no change needed")
                return

            # Need to switch — use JS click to avoid portal overlay
            self._page.evaluate("""() => {
                const section = document.querySelector('#aue-report-download');
                if (section) {
                    const btn = section.querySelector('button[aria-haspopup="listbox"]');
                    if (btn) btn.click();
                }
            }""")
            self._page.wait_for_timeout(1000)
            opt_result = self._page.evaluate("""(targetType) => {
                const options = document.querySelectorAll('[role="option"]');
                for (const opt of options) {
                    if (opt.innerText && opt.innerText.toLowerCase().includes(targetType.toLowerCase())) {
                        opt.click();
                        return {selected: true, text: opt.innerText.trim()};
                    }
                }
                return {selected: false, available: Array.from(options).map(o => o.innerText?.trim())};
            }""", REPORT_TYPE)
            self._log.info("[AmazonPI]   Report type selection result: %s", opt_result)
            self._page.wait_for_timeout(1000)
        except Exception as exc:
            self._log.warning("[AmazonPI]   Report type verification failed (non-critical): %s", exc)

    def _set_time_period_range(self, start_date: date, end_date: date) -> None:
        """
        Re-open the Time Period popper and set a date range (start_date to end_date).
        Used for categories like Storage And Containers that don't render Generate Excel
        for single-day periods.
        """
        self._log.info("[AmazonPI]   Setting time period range: %s to %s",
                       start_date.strftime("%d/%m/%Y"), end_date.strftime("%d/%m/%Y"))

        tp_section = self._page.locator('#aue-time-period-option')
        tp_section.scroll_into_view_if_needed()
        date_range_btn = tp_section.locator('button').nth(1)
        date_range_btn.wait_for(state="visible", timeout=15_000)
        date_range_btn.click()

        popper = self._page.locator('#time-period-popper')
        popper.wait_for(state="visible", timeout=15_000)

        # Keep Daily granularity
        daily_li = popper.locator('[role="button"]', has_text="Daily")
        daily_li.wait_for(state="visible", timeout=5_000)
        daily_li.click()
        self._page.wait_for_timeout(300)

        # Set Start date to start_date, End date to end_date
        self._pick_date_calendar("Start", start_date)
        self._page.wait_for_timeout(500)
        self._pick_date_calendar("End", end_date)
        self._page.wait_for_timeout(500)

        apply_btn = popper.get_by_role("button", name="Apply")
        apply_btn.wait_for(state="visible", timeout=5_000)
        apply_btn.click()
        self._log.info("[AmazonPI]   Time Period range applied: %s to %s",
                       start_date.strftime("%d/%m/%Y"), end_date.strftime("%d/%m/%Y"))
        self._page.wait_for_timeout(2000)

    def _pick_date_calendar(self, which: str, target: date) -> None:
        """
        Open the start/end date calendar popper and click the target date.

        which: "Start" or "End"
        Calendar button: button[aria-label="Start date"] or button[aria-label="End date"]
        Calendar popper: id='start-date-popper' or id='end-date-popper'
        Month nav: aria-label="go to previous month" / "go to next month"
        Month btn: button text matching "Month YYYY" (e.g. "February 2026")
        Day cells: button[aria-label*="Month Day Year"] (e.g. "March 25 2026")
        """
        MONTHS = ["January", "February", "March", "April", "May", "June",
                  "July", "August", "September", "October", "November", "December"]
        target_month_name = MONTHS[target.month - 1]

        # Click the calendar icon button to open the date popper.
        cal_btn = self._page.locator(f'button[aria-label="{which} date"]')
        cal_btn.wait_for(state="visible", timeout=10_000)
        cal_btn.click()
        self._page.wait_for_timeout(500)

        # Wait for the calendar popper.
        cal_id = f"#{which.lower()}-date-popper"
        cal_popper = self._page.locator(cal_id)
        cal_popper.wait_for(state="visible", timeout=10_000)
        self._log.info("[AmazonPI]   %s-date-popper opened", which.lower())

        # Navigate to target month/year (max 24 steps).
        for _ in range(24):
            month_btn = cal_popper.locator('button').filter(
                has_text=re.compile(r'^\w+ \d{4}$')
            ).first
            try:
                month_text = month_btn.inner_text().strip()
            except Exception:
                break
            parts = month_text.split()
            if len(parts) == 2 and parts[0] in MONTHS:
                cur_month = MONTHS.index(parts[0]) + 1
                cur_year = int(parts[1])
                if cur_month == target.month and cur_year == target.year:
                    break
                if (cur_year, cur_month) < (target.year, target.month):
                    cal_popper.locator('button[aria-label="go to next month"]').click()
                else:
                    cal_popper.locator('button[aria-label="go to previous month"]').click()
                self._page.wait_for_timeout(300)
            else:
                break

        # Click the day button (aria-label contains "Month Day Year").
        day_aria = f"{target_month_name} {target.day} {target.year}"
        day_btn = cal_popper.locator(f'button[aria-label*="{day_aria}"]')
        day_btn.wait_for(state="visible", timeout=5_000)
        day_btn.click()
        self._log.info("[AmazonPI]   %s date: clicked %s", which, day_aria)
        self._page.wait_for_timeout(300)

    def _pick_date_in_cal_input(self, inp, target: date, label: str = "") -> None:
        """
        Fill an Amazon AUI a-cal-input.

        The a-cal-input itself is always hidden by AUI CSS. The calendar opens when the
        VISIBLE wrapper ancestor is clicked (real mouse event). We find that ancestor via
        JS, click it via page.mouse.click(), then confirm the date by clicking the day cell.
        If the calendar popover does not appear, we fall back to nativeSetter-only and
        hope AUI reads the DOM value on Apply.
        """
        value = target.strftime("%m/%d/%Y")
        try:
            # 1. Trigger the AUI calendar via the DOM click() method.
            #    a-cal-input is hidden by CSS (zero dimensions), so Playwright's own
            #    click() fails even with force=True. el.click() from JS bypasses that.
            inp.evaluate("el => el.click()")
            self._page.wait_for_timeout(500)

            # 2. Force value + fire events (may also navigate the calendar view)
            inp.evaluate("""(el, val) => {
                const setter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value').set;
                setter.call(el, val);
                el.dispatchEvent(new Event('input',  {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
            }""", value)
            self._page.wait_for_timeout(500)

            # 3. Try to interact with the calendar popover if it opened.
            #    Use a short timeout so we don't block if it didn't open.
            try:
                cal = self._page.locator('[role="dialog"][id^="a-popover"]').last
                cal.wait_for(state="visible", timeout=3_000)
                self._navigate_cal_to_month(cal, target.month, target.year)
                day_val = target.day
                clicked = cal.evaluate("""(el, day) => {
                    const cells = el.querySelectorAll('a[data-action="a-cal-select-date"]');
                    for (const c of cells) {
                        if (c.innerText.trim() === String(day) &&
                                !c.className.includes('unavailable') &&
                                !c.className.includes('disabled')) {
                            c.click();
                            return true;
                        }
                    }
                    return false;
                }""", day_val)
                if clicked:
                    self._log.info("[AmazonPI]   %s: clicked day %d in calendar", label, target.day)
                else:
                    self._page.keyboard.press("Escape")
                    self._log.warning("[AmazonPI]   %s: day cell not found, dismissed", label)
            except Exception:
                # Calendar didn't open — nativeSetter value should still work for Apply
                self._log.info("[AmazonPI]   %s: no calendar popover — relying on nativeSetter", label)

            self._page.wait_for_timeout(300)
            self._log.info("[AmazonPI]   %s value: %s", label, inp.input_value())

        except Exception as e:
            self._log.warning("[AmazonPI]   _pick_date_in_cal_input(%s) error: %s", label, e)

    def _navigate_cal_to_month(self, cal, target_month: int, target_year: int) -> None:
        """Navigate an AUI calendar popover to the correct month/year."""
        MONTHS = ["January", "February", "March", "April", "May", "June",
                  "July", "August", "September", "October", "November", "December"]
        for _ in range(24):
            try:
                text = cal.locator('.a-cal-current').first.inner_text().strip()
            except Exception:
                return
            parts = text.split()
            if len(parts) < 2 or parts[0] not in MONTHS:
                return
            curr_m = MONTHS.index(parts[0]) + 1
            try:
                curr_y = int(parts[1])
            except ValueError:
                return
            if curr_m == target_month and curr_y == target_year:
                return
            if target_year * 12 + target_month > curr_y * 12 + curr_m:
                cal.locator('a[data-action="a-cal-next"]').click()
            else:
                cal.locator('a[data-action="a-cal-prev"]').click()
            self._page.wait_for_timeout(300)

    # ------------------------------------------------------------------
    # Phase 2 — Download Center
    # ------------------------------------------------------------------

    def _download_from_center(self, report_date: date) -> list:
        """
        Navigate to Download Center, poll for all 6 reports to complete,
        then download each. Returns list of saved file paths.

        Identifies rows by: brand=SOLARA, report type contains "ASIN",
        category in CATEGORIES, date matches report_date, status=Completed.
        """
        self._log.info("[AmazonPI] Navigating to Download Center")
        # Try direct URL first; if it times out, fall back to clicking the Download Center button
        # on the SBG page (the new React UI is an SPA and may not accept direct navigation).
        try:
            self._page.goto("https://pi.amazon.in/download-center", wait_until="domcontentloaded",
                            timeout=20_000)
            self._page.wait_for_timeout(4000)
        except Exception:
            self._log.info("[AmazonPI] Direct URL timed out — clicking Download Center button on SBG page")
            try:
                self._page.goto("https://pi.amazon.in/reports/sbg", wait_until="domcontentloaded",
                                timeout=30_000)
                self._page.wait_for_timeout(3000)
                dc_btn = self._page.get_by_role("button", name="Download Center", exact=False)
                dc_btn.wait_for(state="visible", timeout=15_000)
                dc_btn.click()
                self._page.wait_for_timeout(4000)
            except Exception as e2:
                self._log.error("[AmazonPI] Could not navigate to Download Center: %s", e2)

        # Platform-safe date strings for matching Download Center table values
        # Download Center shows dates in D/M/YYYY (no leading zeros on some portals)
        date_dd_mm_yyyy = report_date.strftime("%d/%m/%Y")           # "22/02/2026"
        date_d_m_yyyy   = f"{report_date.day}/{report_date.month}/{report_date.year}"  # "22/2/2026"

        out_dir = self.out_dir / report_date.strftime("%Y-%m-%d")
        out_dir.mkdir(parents=True, exist_ok=True)

        # Poll until all 6 show Completed (max ~15 min)
        downloaded_files = []
        our_rows: list = []
        max_polls = 30
        for poll in range(max_polls):
            # Refresh the table
            try:
                refresh_btn = self._page.get_by_text("Refresh", exact=True).first
                refresh_btn.click()
                self._page.wait_for_timeout(3000)
            except Exception:
                pass

            rows = self._get_download_center_rows()
            self._log.info("[AmazonPI] Download Center: %d rows found", len(rows))

            # Identify our rows:
            #   brand=SOLARA, report=ASIN wise*, category in our list,
            #   date matches report_date (check both start and end — we set From=To=report_date)
            def _date_matches(row: dict) -> bool:
                for field in ("start", "end"):
                    val = row.get(field, "")
                    if date_dd_mm_yyyy in val or date_d_m_yyyy in val:
                        return True
                return False

            # Table columns (from live inspection):
            #   tds[4] = Report Name   → "Sales by Geography"
            #   tds[5] = CSV Name      → "ASIN wise revenue and unit sales"
            # Filter on csv_name (col 5), NOT report (col 4).
            # Status column shows "Ready" (not "Completed") when the file is downloadable.
            def _is_ready(r: dict) -> bool:
                s = r.get("status", "").lower()
                return s in ("ready", "completed")

            our_rows = [
                r for r in rows
                if "SOLARA" in r.get("brand", "")
                and "ASIN" in r.get("csv_name", "")
                and any(cat.lower() in r.get("category", "").lower() for cat in CATEGORIES)
                and _date_matches(r)
            ]
            ready_count = sum(1 for r in our_rows if _is_ready(r))
            self._log.info("[AmazonPI]   Our rows: %d, ready: %d / %d",
                           len(our_rows), ready_count, len(CATEGORIES))
            # Log each matched row for debugging
            for r in our_rows:
                self._log.info("    row: brand=%r cat=%r csv=%r start=%r end=%r status=%r link=%s",
                               r.get("brand"), r.get("category"), r.get("csv_name"),
                               r.get("start"), r.get("end"), r.get("status"),
                               "yes" if r.get("link") else "no")

            # Keep only the FIRST (newest/top-of-table) row per category.
            # We want the newest report (from the current run with all sub-categories selected),
            # not an old one that's already ready.
            first_per_cat: dict = {}  # category -> first row (ready or not)
            for r in our_rows:
                cat = r.get("category", "")
                if cat not in first_per_cat:
                    first_per_cat[cat] = r

            # Build completed list: first row per category that is ready
            completed = [r for r in first_per_cat.values() if _is_ready(r)]
            self._log.info("[AmazonPI]   First-per-category: %d found, %d ready / %d target",
                           len(first_per_cat), len(completed), len(CATEGORIES))

            # Break when the first (newest) row for each category is ready
            if len(completed) >= len(CATEGORIES):
                self._log.info("[AmazonPI] All %d newest reports ready — downloading",
                               len(completed))
                break
            if len(completed) >= len(first_per_cat) and len(first_per_cat) > 0:
                self._log.info("[AmazonPI] All %d found categories ready — downloading",
                               len(completed))
                break

            if poll < max_polls - 1:
                self._log.info("[AmazonPI] Waiting 30s for reports to complete... (poll %d/%d)", poll + 1, max_polls)
                self._shot(f"dc_poll_{poll}")
                time.sleep(30)
        else:
            self._log.warning("[AmazonPI] Timed out waiting for all reports. Downloading what's ready.")
            # On timeout, download the first ready row per category (prefer newest)
            first_per_cat_timeout: dict = {}
            for r in our_rows:
                cat = r.get("category", "")
                if cat not in first_per_cat_timeout:
                    first_per_cat_timeout[cat] = r
            # If newest isn't ready, fall back to any ready row for that category
            completed = []
            for cat, first_row in first_per_cat_timeout.items():
                if _is_ready(first_row):
                    completed.append(first_row)
                else:
                    # Find any ready row for this category
                    for r in our_rows:
                        if r.get("category") == cat and _is_ready(r):
                            completed.append(r)
                            break

        # Download each completed report (.xlsx — "Generate Excel" output)
        for row in completed:
            category_slug = row.get("category", "unknown").replace(" ", "_").replace("/", "-")
            filename = f"{category_slug}_{report_date.strftime('%Y-%m-%d')}_ASIN_revenue.xlsx"
            dest = out_dir / filename
            link_href = row.get("link") or ""
            row_idx   = row.get("row_idx", -1)
            self._log.info("[AmazonPI] Downloading %s  href=%s  row=%s",
                           category_slug, link_href or "(none)", row_idx)

            downloaded = False

            # Method 1: click the <a> element by href (when href is known)
            if link_href and not link_href.startswith("javascript"):
                try:
                    link_el = self._page.locator(f'a[href="{link_href}"]').first
                    with self._page.expect_download(timeout=60_000) as dl_info:
                        link_el.click()
                    dl = dl_info.value
                    dl.save_as(str(dest))
                    downloaded_files.append(dest)
                    downloaded = True
                    self._log.info("[AmazonPI] Downloaded (href click): %s", dest)
                except Exception as e:
                    self._log.warning("[AmazonPI] href-click failed for %s: %s", category_slug, e)

            # Method 2: click the download button by row index via Playwright .nth() locator
            # NOTE: row_idx is from JS querySelectorAll('table tr').slice(1), so it's 0-based
            # relative to data rows. Using Playwright .nth(row_idx + 1) to account for header row.
            if not downloaded:
                try:
                    target_row = self._page.locator("table tr").nth(row_idx + 1)
                    btn_locator = target_row.locator("td:nth-child(10) a, td:nth-child(10) button").first
                    with self._page.expect_download(timeout=60_000) as dl_info:
                        btn_locator.click()
                    dl = dl_info.value
                    dl.save_as(str(dest))
                    downloaded_files.append(dest)
                    downloaded = True
                    self._log.info("[AmazonPI] Downloaded (row-idx locator click): %s", dest)
                except Exception as e2:
                    self._log.warning("[AmazonPI] row-idx locator click failed for %s: %s", category_slug, e2)

            # Method 3: navigate to href URL directly (last resort)
            if not downloaded and link_href and not link_href.startswith("javascript"):
                try:
                    with self._page.expect_download(timeout=60_000) as dl_info:
                        self._page.goto(link_href, wait_until="commit")
                    dl = dl_info.value
                    dl.save_as(str(dest))
                    downloaded_files.append(dest)
                    downloaded = True
                    self._log.info("[AmazonPI] Downloaded (navigate): %s", dest)
                except Exception as e3:
                    self._log.error("[AmazonPI] All download methods failed for %s: %s", category_slug, e3)

        self._log.info("[AmazonPI] Downloaded %d/%d files", len(downloaded_files), len(CATEGORIES))
        return downloaded_files

    def _get_download_center_rows(self) -> list:
        """Parse the Download Center table and return list of row dicts.

        Table columns (from live page, 2026-02-23):
          0=S.No, 1=Download Time, 2=Selected Brand, 3=Selected Category,
          4=Report Name, 5=Downloaded CSV Name, 6=TP Start, 7=TP End,
          8=Download Status, 9=Download Link
        """
        rows = self._page.evaluate("""() => {
            const trs = Array.from(document.querySelectorAll('table tr'));
            return trs.slice(1).map((tr, rowIdx) => {
                const tds = Array.from(tr.querySelectorAll('td'));
                if (tds.length < 9) return null;
                // Download button may be <a> or <button>
                const linkEl = tds[9]?.querySelector('a') || tds[9]?.querySelector('button');
                return {
                    sno:      tds[0]?.innerText?.trim(),
                    row_idx:  rowIdx,
                    time:     tds[1]?.innerText?.trim(),
                    brand:    tds[2]?.innerText?.trim(),
                    category: tds[3]?.innerText?.trim(),
                    report:   tds[4]?.innerText?.trim(),
                    csv_name: tds[5]?.innerText?.trim(),
                    start:    tds[6]?.innerText?.trim(),
                    end:      tds[7]?.innerText?.trim(),
                    status:   tds[8]?.innerText?.trim(),
                    link:     linkEl?.href || null,
                };
            }).filter(r => r !== null);
        }""")
        return rows or []

    # ------------------------------------------------------------------
    # Public orchestrator interface
    # ------------------------------------------------------------------

    def run(self, report_date: date = None) -> dict:
        """Full scraping cycle — for the orchestrator.

        Downloads the Chrome profile from Drive, runs login + report generation +
        download, uploads the updated profile back to Drive, and returns a status dict.

        Profile sync is a no-op when PROFILE_STORAGE_DRIVE_FOLDER_ID is not set.
        """
        if report_date is None:
            report_date = date.today() - timedelta(days=1)

        result = {
            "portal": self.portal_name,
            "date": report_date,
            "files": None,
            "status": "failed",
            "error": None,
        }

        try:
            from scrapers.profile_sync import download_profile, upload_profile
        except ImportError:
            from profile_sync import download_profile, upload_profile

        login_ok = False
        try:
            # Pull latest profile from Drive before launching browser (no-op if not configured)
            download_profile("amazon_pi")

            self._init_browser()
            self.login()
            login_ok = True
            files = self.download_report(report_date)
            result["files"] = [str(f) for f in files]
            result["status"] = "success" if files else "partial"

            # Upload each downloaded Excel to Google Drive: Reports / YYYY-MM / Amazon PI /
            if _upload_to_drive and files:
                drive_links = []
                for file_path in files:
                    drive_link = _upload_to_drive(
                        portal="Amazon PI",
                        report_date=report_date,
                        file_path=Path(file_path),
                    )
                    if drive_link:
                        drive_links.append(drive_link)
                        self._log.info("[AmazonPI] Uploaded to Drive: %s", drive_link)
                if drive_links:
                    result["drive_links"] = drive_links

        except Exception as exc:
            self._log.error("[AmazonPI] Run failed: %s", exc)
            result["error"] = str(exc)

        finally:
            self._close_browser()
            # Only upload profile if login succeeded — avoids overwriting Drive with a failed session
            if login_ok:
                try:
                    upload_profile("amazon_pi")
                except Exception as exc:
                    self._log.warning("[AmazonPI] Profile upload failed (non-critical): %s", exc)

        return result

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------

    def logout(self) -> None:
        try:
            self._page.goto("https://www.amazon.in/gp/sign-in.html", wait_until="domcontentloaded")
        except Exception:
            pass


# ------------------------------------------------------------------
# Standalone entry point — login only, browser stays open
# ------------------------------------------------------------------

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    try:
        from scrapers.profile_sync import download_profile, upload_profile
    except ImportError:
        from profile_sync import download_profile, upload_profile

    scraper = AmazonPIScraper(headless=False)

    # Pull latest profile from Drive before launching browser (no-op if not configured)
    download_profile("amazon_pi")
    scraper._init_browser()

    login_ok = False
    try:
        scraper.login()
        login_ok = True
        print("\n" + "=" * 60)
        print("LOGIN COMPLETE")
        print(f"URL: {scraper._page.url}")
        print("=" * 60)
        print("\nBrowser open. Press Enter to run full report download...")
        try:
            input()
        except EOFError:
            pass

        yesterday = date.today() - timedelta(days=1)
        files = scraper.download_report(yesterday)
        print(f"\nDownloaded {len(files)} files:")
        for f in files:
            print(f"  {f}")

        print("\nPress Enter to close browser.")
        try:
            input()
        except EOFError:
            pass

    except Exception as e:
        logger.error("Failed: %s", e)
        scraper._shot("main_error")
        print(f"\nError: {e}")
        try:
            input("Press Enter to close.")
        except EOFError:
            pass
    finally:
        scraper._close_browser()
        # Only upload profile if login succeeded — avoids overwriting Drive with a failed session
        if login_ok:
            upload_profile("amazon_pi")
