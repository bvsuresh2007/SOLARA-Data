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

REPORT_TYPE = "ASIN wise revenue and unit sales"


class AmazonPIScraper:
    """Scraper for Amazon PI (pi.amazon.in)."""

    portal_name = "amazon_pi"

    def __init__(self, headless: bool = True, raw_data_path: str = None):
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
            self._pw.__exit__(None, None, None)
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
        self._page.goto(self.login_url, wait_until="domcontentloaded")

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
        brand_sel = self._page.locator('select#brand-dropdown')
        brand_sel.wait_for(state="visible", timeout=15_000)
        brand_sel.select_option(label="SOLARA")
        self._log.info("[AmazonPI]   Brand = SOLARA")

        # Wait for the page to settle after brand selection.
        try:
            self._page.wait_for_load_state("networkidle", timeout=20_000)
        except Exception:
            pass
        self._page.locator('#aue-time-period-option').wait_for(state="visible", timeout=25_000)
        self._page.wait_for_timeout(1000)

        # ── Set Time Period ONCE (before any category switch) ──────────
        self._set_time_period(report_date)

        # ── Iterate categories via dropdown — no page.goto() between them ──
        for category in CATEGORIES:
            try:
                self._generate_for_category(category, report_date)
            except Exception as exc:
                self._log.error("[AmazonPI] Category %s failed: %s", category, exc)
                self._shot(f"error_{category[:6].replace(' ', '_')}")

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

        # ── Set category (AJAX reload, same page — Time Period persists) ──
        cat_sel = self._page.locator('select#category-dropdown')
        cat_sel.wait_for(state="visible", timeout=15_000)
        cat_sel.select_option(label=category)
        self._log.info("[AmazonPI]   Category = %s", category)

        # Wait for AJAX to settle (chart data loads for this category).
        # The chart may not load if the category has no data for our date; that's OK —
        # the Downloads section is always available.
        try:
            self._page.wait_for_load_state("networkidle", timeout=20_000)
        except Exception:
            pass
        self._page.wait_for_timeout(1500)

        # ── Scroll to Downloads section ────────────────────────────────
        self._page.evaluate("""
            const el = document.querySelector('select#download-dropdown')
                    || document.querySelector('select[name="download-report"]');
            if (el) el.scrollIntoView({behavior: 'smooth', block: 'center'});
        """)
        self._page.wait_for_timeout(800)

        # ── Report type: ASIN wise revenue and unit sales ──────────────
        dl_sel = self._page.locator('select#download-dropdown')
        dl_sel.wait_for(state="visible", timeout=10_000)
        dl_sel.select_option(label=REPORT_TYPE)
        self._log.info("[AmazonPI]   Report type = %s", REPORT_TYPE)
        self._page.wait_for_timeout(400)

        # ── Generate Excel ─────────────────────────────────────────────
        gen_btn = self._page.locator('a.a-button-text', has_text="Generate Excel")
        gen_btn.wait_for(state="visible", timeout=10_000)
        self._shot(f"before_gen_{category[:6].replace(' ', '_')}")
        gen_btn.click()
        self._log.info("[AmazonPI]   Generate Excel clicked for %s", category)
        self._page.wait_for_timeout(3000)
        self._shot(f"after_gen_{category[:6].replace(' ', '_')}")

    def _set_time_period(self, report_date: date) -> None:
        """
        Open the Time Period modal and set From = To = report_date (single day, Daily tab).

        Confirmed selectors (live page inspection 2026-02-23):
          Trigger:    section#aue-time-period-option
          Daily tab:  input[name="daily-range-tab"]  (type="submit")
          From input: input.a-cal-input nth(0)       (type="text", MM/DD/YYYY)
          To input:   input.a-cal-input nth(1)       (type="text", MM/DD/YYYY)
          Calendar:   [role="dialog"][id^="a-popover"] — opened by clicking the input
                      Day cells:  a[data-action="a-cal-select-date"]
                      Month nav:  a[data-action="a-cal-prev"] / a[data-action="a-cal-next"]
                      Month name: .a-cal-current
          Apply btn:  input#modal-save-button-time-period
        """
        date_str = report_date.strftime("%m/%d/%Y")
        self._log.info("[AmazonPI]   Setting time period to %s", date_str)

        # Open the Time Period modal by clicking the banner trigger.
        # This is called once (brand only, no category yet) so the chart is in a
        # stable state and the modal opens reliably.
        tp_trigger = self._page.locator('#aue-time-period-option')
        tp_trigger.scroll_into_view_if_needed()
        tp_trigger.click()
        apply_btn = self._page.locator('#modal-save-button-time-period')
        apply_btn.wait_for(state="visible", timeout=15_000)
        self._log.info("[AmazonPI]   Time Period modal opened")
        self._shot("tp_opened")

        # Confirm Daily tab — AUI radio button (always hidden by CSS).
        # Use dispatch_event to bypass CSS hidden state.
        daily_tab = self._page.locator('input[name="daily-range-tab"]')
        daily_tab.wait_for(state="attached", timeout=10_000)
        aria_checked = daily_tab.get_attribute('aria-checked')
        self._log.info("[AmazonPI]   Daily tab aria-checked=%s — dispatching click", aria_checked)
        daily_tab.dispatch_event('click')
        self._page.wait_for_timeout(500)

        # Set From date — a-cal-input is always hidden by AUI CSS; use "attached"
        from_inp = self._page.locator('input.a-cal-input').nth(0)
        from_inp.wait_for(state="attached", timeout=8_000)
        self._pick_date_in_cal_input(from_inp, report_date, "From")

        # Set To date (same flow; From calendar is now closed)
        to_inp = self._page.locator('input.a-cal-input').nth(1)
        to_inp.wait_for(state="attached", timeout=8_000)
        self._pick_date_in_cal_input(to_inp, report_date, "To")

        self._shot("tp_dates_filled")

        # Click Apply
        self._page.locator('#modal-save-button-time-period').click()
        self._log.info("[AmazonPI]   Time Period applied: %s", date_str)
        self._page.wait_for_timeout(2000)
        self._shot("tp_done")

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
        self._page.goto("https://pi.amazon.in/download-center", wait_until="domcontentloaded")
        self._page.wait_for_timeout(4000)

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

            # Keep only the first (most recent) ready row per category
            seen_cats: set = set()
            completed = []
            for r in our_rows:
                if _is_ready(r) and r.get("category") not in seen_cats:
                    completed.append(r)
                    seen_cats.add(r.get("category"))

            if len(completed) >= len(CATEGORIES):
                self._log.info("[AmazonPI] All %d reports ready — downloading", len(completed))
                break

            if poll < max_polls - 1:
                self._log.info("[AmazonPI] Waiting 30s for reports to complete... (poll %d/%d)", poll + 1, max_polls)
                self._shot(f"dc_poll_{poll}")
                time.sleep(30)
        else:
            self._log.warning("[AmazonPI] Timed out waiting for all reports. Downloading what's ready.")
            seen_cats2: set = set()
            completed = []
            for r in our_rows:
                if _is_ready(r) and r.get("category") not in seen_cats2:
                    completed.append(r)
                    seen_cats2.add(r.get("category"))

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

            # Method 2: click the download button by row index via JS (handles <button> elements)
            if not downloaded:
                try:
                    with self._page.expect_download(timeout=60_000) as dl_info:
                        self._page.evaluate("""(idx) => {
                            const trs = Array.from(document.querySelectorAll('table tr'));
                            const dataRows = trs.slice(1);
                            const tr = dataRows[idx];
                            if (!tr) return;
                            const tds = Array.from(tr.querySelectorAll('td'));
                            const btn = tds[9]?.querySelector('a, button');
                            if (btn) btn.click();
                        }""", row_idx)
                    dl = dl_info.value
                    dl.save_as(str(dest))
                    downloaded_files.append(dest)
                    downloaded = True
                    self._log.info("[AmazonPI] Downloaded (row-idx click): %s", dest)
                except Exception as e2:
                    self._log.warning("[AmazonPI] row-idx click failed for %s: %s", category_slug, e2)

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
                upload_profile("amazon_pi")

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
