"""
Zepto Brands Dashboard scraper.

Login flow:
  1. Navigate to brands.zepto.co.in/login
  2. Enter email + password → click Log In
  3. OTP screen appears → fetch OTP from automation@solara.in
  4. Enter OTP → click Confirm

Report download flow:
  1. Navigate to /vendor/reports
  2. Click Request Report
  3. Select report type Sales_F, enter yesterday's date → Submit
  4. Refresh page, find the new Sales_F row for yesterday → click Download
  5. Save Excel file
"""

import os
import time
from datetime import date, timedelta
from pathlib import Path

from .base_scraper import BaseScraper, logger
from .gmail_otp import fetch_latest_otp
from .google_drive_upload import upload_to_drive

ZEPTO_OTP_SENDER  = "mailer@zeptonow.com"
OTP_WAIT_SECONDS  = 10
OTP_MAX_ATTEMPTS  = 3
REPORTS_URL       = "https://brands.zepto.co.in/vendor/reports"


class ZeptoScraper(BaseScraper):
    portal_name = "zepto"

    def __init__(self, headless: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.login_url = os.environ["ZEPTO_LINK"]
        self.email     = os.environ["ZEPTO_EMAIL"].split("#")[0].strip()
        self.password  = os.environ["ZEPTO_PASSWORD"]
        self._headless = headless

    SESSION_FILE = Path(__file__).resolve().parent / "sessions" / "zepto_session.json"

    def _init_browser(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().__enter__()
        self.browser = self._pw.chromium.launch(
            headless=self._headless,
            slow_mo=100,
        )
        ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )
        if self.SESSION_FILE.exists():
            logger.info("[Zepto] Restoring saved browser session")
            self._context = self.browser.new_context(
                storage_state=str(self.SESSION_FILE), user_agent=ua
            )
        else:
            self._context = self.browser.new_context(user_agent=ua)

        self.page = self._context.new_page()
        self.page.set_default_timeout(30_000)

    def _save_session(self):
        self._context.storage_state(path=str(self.SESSION_FILE))
        logger.info("[Zepto] Session saved to %s", self.SESSION_FILE)

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    def login(self) -> None:
        # If a saved session exists, check if it's still valid first
        if self.SESSION_FILE.exists():
            logger.info("[Zepto] Checking saved session validity")
            self.page.goto(REPORTS_URL, wait_until="domcontentloaded")
            self.page.wait_for_timeout(2000)
            if "login" not in self.page.url:
                logger.info("[Zepto] Session still valid — skipping login")
                return
            logger.info("[Zepto] Session expired — performing fresh login")
            self.SESSION_FILE.unlink(missing_ok=True)

        logger.info("[Zepto] Navigating to %s", self.login_url)
        self.page.goto(self.login_url, wait_until="domcontentloaded")

        # --- Step 1: Fill email + password ---
        logger.info("[Zepto] Entering email: %s", self.email)
        self.page.locator('#email').wait_for(state="visible")
        self.page.locator('#email').fill(self.email)
        self.page.locator('#password').fill(self.password)

        # --- Step 2: Click Log In — record timestamp just before triggering OTP ---
        otp_triggered_at = int(time.time())
        logger.info("[Zepto] Clicking Log In")
        self.page.locator('button:has-text("Log In")').click()

        # --- Step 3: Wait for OTP input ---
        logger.info("[Zepto] Waiting for OTP screen")
        otp_input = self.page.locator('#otp')
        try:
            otp_input.wait_for(state="visible", timeout=15_000)
        except Exception:
            self._screenshot("otp_screen_not_found")
            raise RuntimeError("OTP screen did not appear after clicking Log In.")

        # --- Step 4: Fetch OTP — only emails received after login was triggered ---
        logger.info("[Zepto] OTP screen detected. Waiting %ds for email...", OTP_WAIT_SECONDS)
        otp = None
        for attempt in range(1, OTP_MAX_ATTEMPTS + 1):
            time.sleep(OTP_WAIT_SECONDS)
            logger.info("[Zepto] Fetching OTP from Gmail (attempt %d/%d)", attempt, OTP_MAX_ATTEMPTS)
            otp = fetch_latest_otp(sender=ZEPTO_OTP_SENDER, after_epoch=otp_triggered_at)
            if otp:
                break
            logger.warning("[Zepto] OTP not found yet, retrying...")

        if not otp:
            self._screenshot("otp_fetch_failed")
            raise RuntimeError("Could not fetch Zepto OTP from automation@solara.in.")

        # --- Step 5: Enter OTP + confirm ---
        logger.info("[Zepto] Entering OTP: %s", otp)
        otp_input.fill(otp)
        self.page.locator('button:has-text("Confirm")').click()

        # Wait for redirect away from login page
        try:
            self.page.wait_for_url(
                lambda url: "login" not in url,
                timeout=20_000,
            )
        except Exception:
            self._screenshot("post_otp_submit")
            raise RuntimeError(
                f"Still on login page after OTP submission — OTP may be invalid or expired. "
                f"URL: {self.page.url}"
            )

        logger.info("[Zepto] Login complete — URL: %s", self.page.url)
        self._save_session()

    # ------------------------------------------------------------------
    # Report download
    # ------------------------------------------------------------------

    def download_report(self, report_date: date = None) -> Path:
        if report_date is None:
            report_date = date.today() - timedelta(days=1)

        date_mm_dd_yyyy = report_date.strftime("%m/%d/%Y")
        date_iso        = report_date.strftime("%Y-%m-%d")
        logger.info("[Zepto] Requesting Sales_F report for %s", date_iso)

        # Navigate to reports page
        self.page.goto(REPORTS_URL, wait_until="domcontentloaded")
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(1500)

        # --- Click Request Report ---
        logger.info("[Zepto] Clicking Request Report")
        self.page.locator('button:has-text("Request Report")').first.click()
        self.page.wait_for_timeout(1500)

        # --- Select Sales_F from MUI drawer dropdown ---
        logger.info("[Zepto] Selecting Sales_F report type")
        drawer = self.page.locator('[role="presentation"]').last
        report_select_wrapper = drawer.locator('div:has(> input[name="reportType"])').first
        report_select_wrapper.click()
        self.page.wait_for_timeout(800)

        # Options render in a body-level MUI portal
        listbox = self.page.locator('ul[role="listbox"], [role="listbox"]').first
        listbox.locator('li:has-text("Sales_F"), [role="option"]:has-text("Sales_F")').first.click()
        self.page.wait_for_timeout(500)

        # --- Fill date fields (mm/dd/yyyy) ---
        logger.info("[Zepto] Setting date: %s", date_mm_dd_yyyy)
        date_inputs = self.page.locator('input[type="tel"][placeholder="mm/dd/yyyy"]').all()
        for inp in date_inputs:
            inp.click()
            inp.fill(date_mm_dd_yyyy)
            self.page.keyboard.press("Tab")
        self.page.wait_for_timeout(500)

        # --- Submit ---
        logger.info("[Zepto] Submitting report request")
        self.page.locator('button:has-text("Submit")').last.click()
        self.page.wait_for_timeout(2000)

        # --- Refresh to see the new row ---
        logger.info("[Zepto] Refreshing page")
        self.page.reload(wait_until="networkidle")
        self.page.wait_for_timeout(2000)

        # --- Find and click Download on the first SALES row for our date ---
        # Row format: "19 Feb 2026 | ... | SALES | 18 Feb 2026 - 18 Feb 2026 | Completed | Download"
        logger.info("[Zepto] Looking for download link for %s", date_iso)
        date_display = f"{report_date.day} {report_date.strftime('%b %Y')}"  # e.g. "18 Feb 2026"

        download_row = self.page.locator(
            f'tr:has-text("SALES"):has-text("{date_display} - {date_display}")'
        ).first

        try:
            download_row.wait_for(state="visible", timeout=15_000)
        except Exception:
            self._screenshot("download_row_not_found")
            raise RuntimeError(f"No SALES report row found for {date_display} after refresh.")

        output_path = self.portal_data_path / f"zepto_sales_{date_iso}.xlsx"
        with self.page.expect_download() as dl_info:
            download_row.locator('button:has-text("Download")').click()

        dl_info.value.save_as(str(output_path))
        logger.info("[Zepto] Saved to %s", output_path)

        # Upload to Google Drive: SolaraDashboard Reports / YYYY-MM / Zepto /
        upload_to_drive(portal="Zepto", report_date=report_date, file_path=output_path)

        return output_path

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------

    def logout(self) -> None:
        try:
            self.page.locator('button:has-text("Logout"), a:has-text("Logout")').first.click(timeout=5_000)
        except Exception:
            pass
