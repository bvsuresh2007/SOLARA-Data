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

Inventory SOH flow (same page, runs after sales):
  1. Click Request Report
  2. Select Vendor Inventory_F (no date fields)
  3. Submit → refresh → find INVENTORY row → click Download
  4. Save as zepto_soh_YYYY-MM-DD.xlsx
"""

import logging
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

# Allow running as a script: python scrapers/zepto_scraper.py
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "scrapers"

from .base_scraper import BaseScraper, logger
from .gmail_otp import fetch_latest_otp
from .google_drive_upload import upload_to_drive

ZEPTO_OTP_SENDER  = "mailer@zeptonow.com"
OTP_WAIT_SECONDS  = 10
OTP_MAX_ATTEMPTS  = 3
REPORTS_URL       = "https://brands.zepto.co.in/vendor/reports"


class ZeptoScraper(BaseScraper):
    portal_name = "zepto"
    # Disable Python-level retries — Playwright's sync API leaves dirty asyncio
    # state after __exit__, causing "Sync API inside asyncio loop" on retry.
    # Long-polling inside download_report() handles the "report not ready" case.
    # Workflow-level retry (scraper-retry.yml) handles login/network failures.
    max_retries = 1

    def __init__(self, headless: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.login_url = os.environ["ZEPTO_LINK"]
        self.email     = os.environ["ZEPTO_EMAIL"].split("#")[0].strip()
        self.password  = os.environ["ZEPTO_PASSWORD"]
        self._headless = headless

    SESSION_FILE = Path(__file__).resolve().parent / "sessions" / "zepto_session.json"

    def _init_browser(self):
        # Reset asyncio event loop so retries don't hit "Sync API inside asyncio loop"
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if not loop.is_running():
                loop.close()
        except Exception:
            pass
        asyncio.set_event_loop(asyncio.new_event_loop())

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
            raise RuntimeError("Could not fetch Zepto OTP from Gmail.")

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

        # --- Refresh until the new row appears (Zepto can take 30–60s to generate) ---
        date_display = report_date.strftime("%d %b %Y")  # e.g. "02 Mar 2026" (Zepto uses zero-padded day)
        logger.info("[Zepto] Waiting for SALES report row for %s", date_display)

        # Poll until the report row appears — Zepto can take up to 10-15 minutes
        # to generate a report. Poll every 60s for up to 15 minutes (15 attempts).
        download_row = None
        max_poll = 15
        for refresh_attempt in range(1, max_poll + 1):
            logger.info("[Zepto] Polling for report row (attempt %d/%d)", refresh_attempt, max_poll)
            self.page.reload(wait_until="networkidle")
            self.page.wait_for_timeout(3000)

            row = self.page.locator(
                f'tr:has-text("SALES"):has-text("{date_display} - {date_display}")'
            ).first
            if row.is_visible():
                # Also confirm the Download button is present and enabled before breaking —
                # the row appears while the report is still "Processing" (no button yet).
                dl_btn = row.locator('button:has-text("Download")')
                if dl_btn.count() > 0 and dl_btn.first.is_enabled():
                    download_row = row
                    logger.info("[Zepto] Report row + Download button ready on attempt %d", refresh_attempt)
                    break
                logger.info("[Zepto] Row visible but Download button not ready yet, continuing poll...")
                continue

            if refresh_attempt < max_poll:
                logger.info("[Zepto] Row not ready yet, waiting 60s before next poll...")
                self.page.wait_for_timeout(60_000)

        if download_row is None:
            self._screenshot("download_row_not_found")
            raise RuntimeError(f"No SALES report row found for {date_display} after {max_poll} poll attempts (~15 min).")

        output_path = self.portal_data_path / f"zepto_sales_{date_iso}.xlsx"
        with self.page.expect_download() as dl_info:
            download_row.locator('button:has-text("Download")').click()

        dl_info.value.save_as(str(output_path))
        logger.info("[Zepto] Saved to %s", output_path)

        # Upload to Google Drive: SolaraDashboard Reports / YYYY-MM / Zepto /
        upload_to_drive(portal="Zepto", report_date=report_date, file_path=output_path)

        return output_path

    # ------------------------------------------------------------------
    # Inventory SOH download (Vendor Inventory_F)
    # ------------------------------------------------------------------

    def download_inventory_report(self, report_date: date = None) -> "Path | None":
        """
        Request and download the Vendor Inventory_F report.
        No date range is needed — Zepto generates a current snapshot.
        Polls for the INVENTORY row (up to 10 min) then downloads.
        Returns the local file path, or None on failure (non-fatal).
        """
        if report_date is None:
            report_date = date.today() - timedelta(days=1)

        date_iso = report_date.strftime("%Y-%m-%d")
        logger.info("[Zepto] Requesting Vendor Inventory_F report")

        # Navigate to reports page
        self.page.goto(REPORTS_URL, wait_until="domcontentloaded")
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_timeout(1500)

        # --- Click Request Report ---
        logger.info("[Zepto] Clicking Request Report (inventory)")
        self.page.locator('button:has-text("Request Report")').first.click()
        self.page.wait_for_timeout(1500)

        # --- Select Vendor Inventory_F from MUI drawer dropdown ---
        logger.info("[Zepto] Selecting Vendor Inventory_F report type")
        drawer = self.page.locator('[role="presentation"]').last
        report_select_wrapper = drawer.locator('div:has(> input[name="reportType"])').first
        report_select_wrapper.click()
        self.page.wait_for_timeout(800)

        listbox = self.page.locator('ul[role="listbox"], [role="listbox"]').first
        listbox.locator(
            'li:has-text("Vendor Inventory_F"), [role="option"]:has-text("Vendor Inventory_F")'
        ).first.click()
        self.page.wait_for_timeout(500)

        # --- NO date fields for inventory — submit directly ---
        logger.info("[Zepto] Submitting Vendor Inventory_F request")
        self.page.locator('button:has-text("Submit")').last.click()
        self.page.wait_for_timeout(2000)

        # --- Poll for INVENTORY row ---
        logger.info("[Zepto] Waiting for INVENTORY report row")
        download_row = None
        max_poll = 10  # 10 × 60s = up to 10 minutes
        for refresh_attempt in range(1, max_poll + 1):
            logger.info("[Zepto] Polling inventory row (attempt %d/%d)", refresh_attempt, max_poll)
            self.page.reload(wait_until="networkidle")
            self.page.wait_for_timeout(3000)

            row = self.page.locator('tr:has-text("INVENTORY")').first
            if row.is_visible():
                dl_btn = row.locator('button:has-text("Download")')
                if dl_btn.count() > 0 and dl_btn.first.is_enabled():
                    download_row = row
                    logger.info("[Zepto] Inventory row + Download button ready on attempt %d", refresh_attempt)
                    break
                logger.info("[Zepto] Inventory row visible but Download not ready yet, continuing poll...")
                if refresh_attempt < max_poll:
                    self.page.wait_for_timeout(60_000)
                continue

            if refresh_attempt < max_poll:
                logger.info("[Zepto] Inventory row not ready yet, waiting 60s...")
                self.page.wait_for_timeout(60_000)

        if download_row is None:
            self._screenshot("zepto_inventory_row_not_found")
            logger.error("[Zepto] No INVENTORY report row found after %d poll attempts — skipping SOH", max_poll)
            return None

        output_path = self.portal_data_path / f"zepto_soh_{date_iso}.xlsx"
        try:
            with self.page.expect_download(timeout=60_000) as dl_info:
                download_row.locator('button:has-text("Download")').click()
            dl_info.value.save_as(str(output_path))
            logger.info("[Zepto] Inventory SOH saved to %s", output_path)
            upload_to_drive(portal="Zepto", report_date=report_date, file_path=output_path)
            return output_path
        except Exception as exc:
            logger.error("[Zepto] Inventory download failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # run() — overrides BaseScraper to add Drive session sync + inventory
    # ------------------------------------------------------------------

    def run(self, report_date: date = None) -> dict:
        """
        Full Zepto scrape cycle with Drive session sync:
          1. Download zepto_session.json from Drive (so CI has a saved session)
          2. Init browser, login (checks session validity, falls back to OTP)
          3. download_report() — Sales_F for report_date
          4. download_inventory_report() — Vendor Inventory_F (current snapshot)
          5. Upload the refreshed session JSON back to Drive
        No-op if PROFILE_STORAGE_DRIVE_FOLDER_ID is not set (local dev).
        """
        try:
            from scrapers.profile_sync import download_session_file, upload_session_file
        except ImportError:
            from profile_sync import download_session_file, upload_session_file

        if report_date is None:
            report_date = date.today() - timedelta(days=1)

        download_session_file("zepto")

        result = {
            "portal": self.portal_name,
            "date": report_date,
            "file": None,
            "soh_file": None,
            "status": "failed",
            "error": None,
        }

        try:
            self._init_browser()
            self.login()
            # Sales report
            result["file"] = self.download_report(report_date)
            result["status"] = "success"
            # Inventory SOH (non-fatal — failure doesn't abort the run)
            try:
                result["soh_file"] = self.download_inventory_report(report_date)
            except Exception as inv_exc:
                logger.warning("[Zepto] Inventory SOH download failed (non-fatal): %s", inv_exc)
            self.logout()
        except Exception as exc:
            self._log.error("Zepto run failed: %s", exc)
            self._screenshot("zepto_run_failed")
            result["error"] = str(exc)
        finally:
            self._close_browser()

        # Only upload session if login succeeded
        if self.SESSION_FILE.exists():
            upload_session_file("zepto")

        return result

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------

    def logout(self) -> None:
        try:
            self.page.locator('button:has-text("Logout"), a:has-text("Logout")').first.click(timeout=5_000)
        except Exception:
            pass


# ------------------------------------------------------------------
# CLI entry point for manual testing / session refresh
# ------------------------------------------------------------------
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    scraper = ZeptoScraper(headless=False)
    result  = scraper.run()
    print("\nResult:", result)
