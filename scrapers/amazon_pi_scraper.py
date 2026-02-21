"""
Amazon PI (pi.amazon.in) scraper.

Login flow:
  1. Navigate to pi.amazon.in/brand-summary
  2. Redirected to Amazon standard login page
  3. Enter email → Continue → Enter password → Sign In
  4. Handle OTP/2FA if prompted
"""
import os
from datetime import date
from pathlib import Path

from .base_scraper import BaseScraper, logger


# NOT in orchestrator.SCRAPERS — download_report() is not implemented yet.
class AmazonPIScraper(BaseScraper):
    portal_name = "amazon_pi"

    def __init__(self, headless: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.login_url = os.environ["AMAZON_PI_LINK"]
        self.email     = os.environ["AMAZON_PI_EMAIL"]
        self.password  = os.environ["AMAZON_PI_PASSWORD"]
        self._headless = headless

    def _init_browser(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().__enter__()
        self.browser = self._pw.chromium.launch(
            headless=self._headless,
            slow_mo=100,
        )
        self.page = self.browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        )
        self.page.set_default_timeout(30_000)

    def login(self) -> None:
        logger.info("[AmazonPI] Navigating to %s", self.login_url)
        self.page.goto(self.login_url, wait_until="domcontentloaded")

        # Amazon redirects to its standard login page
        logger.info("[AmazonPI] Waiting for Amazon login page")
        email_input = self.page.locator('#ap_email')
        email_input.wait_for(state="visible")

        # --- Step 1: Enter email and click Continue ---
        logger.info("[AmazonPI] Entering email: %s", self.email)
        email_input.fill(self.email)
        # Use input[type="submit"] — avoids strict-mode violation where #continue
        # matches both a <span id="continue"> and <input id="continue" type="submit">
        self.page.locator('input[type="submit"]').click()

        # --- Step 2: Enter password ---
        # After clicking Continue, Amazon loads the password step with #ap_password
        logger.info("[AmazonPI] Entering password")
        password_input = self.page.locator('#ap_password')
        password_input.wait_for(state="visible")
        password_input.fill(self.password)
        self.page.locator('#signInSubmit').click()

        # --- Step 3: Handle OTP / 2FA if it appears ---
        try:
            otp_input = self.page.locator('#auth-mfa-otpcode, input[name="otpCode"]')
            otp_input.wait_for(state="visible", timeout=5_000)
            logger.warning("[AmazonPI] OTP/2FA screen detected — manual intervention may be needed")
            self.page.wait_for_url("**/pi.amazon.in**", timeout=60_000)
        except Exception:
            pass

        # Wait for redirect back to pi.amazon.in
        logger.info("[AmazonPI] Waiting for dashboard to load")
        self.page.wait_for_url("**/pi.amazon.in**", timeout=30_000)
        logger.info("[AmazonPI] Login complete — URL: %s", self.page.url)

    def download_report(self, report_date: date) -> Path:
        raise NotImplementedError(
            "Amazon PI report download not yet implemented. "
            "Login works — next step is to navigate to the reports section."
        )

    def logout(self) -> None:
        try:
            self.page.goto("https://www.amazon.in/gp/sign-in.html", wait_until="domcontentloaded")
        except Exception:
            pass
