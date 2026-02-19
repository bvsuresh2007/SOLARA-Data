"""
Amazon Vendor Central / Seller Central scraper.
Downloads daily sales & inventory reports.

Note: For real-time BSR/price data on individual ASINs, use the standalone tool:
  scrapers/tools/amazon_asin_scraper/main.py
"""
import os
from datetime import date
from pathlib import Path

from .base_scraper import BaseScraper, logger


class AmazonScraper(BaseScraper):
    portal_name = "amazon"

    LOGIN_URL  = "https://sellercentral.amazon.in/gp/homepage.html"
    REPORT_URL = "https://sellercentral.amazon.in/reportcentral/SALES_AND_TRAFFIC/1"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.email    = os.environ["AMAZON_EMAIL"]
        self.password = os.environ["AMAZON_PASSWORD"]

    def login(self) -> None:
        logger.info("[Amazon] Logging in to Seller Central")
        self.page.goto(self.LOGIN_URL, wait_until="networkidle")
        self.page.fill('#ap_email', self.email)
        self.page.click('#continue')
        self.page.wait_for_selector('#ap_password', timeout=10_000)
        self.page.fill('#ap_password', self.password)
        self.page.click('#signInSubmit')
        # Handle OTP / 2FA if required — wait for dashboard
        self.page.wait_for_url("**/homepage**", timeout=60_000)
        logger.info("[Amazon] Login successful")

    def download_report(self, report_date: date) -> Path:
        date_str = report_date.strftime("%Y-%m-%d")
        logger.info("[Amazon] Downloading sales report for %s", date_str)
        self.page.goto(self.REPORT_URL, wait_until="networkidle")

        # Set date range to single day
        self.page.fill('[name="reportStartDate"]', date_str)
        self.page.fill('[name="reportEndDate"]', date_str)
        self.page.click('[data-action="request-report"]')
        self.page.wait_for_selector('.report-download-link', timeout=120_000)

        output_path = self.portal_data_path / f"amazon_sales_{date_str}.xlsx"
        with self.page.expect_download() as dl_info:
            self.page.click('.report-download-link')
        dl_info.value.save_as(str(output_path))
        logger.info("[Amazon] Saved to %s", output_path)
        return output_path

    def logout(self) -> None:
        try:
            self.page.goto("https://sellercentral.amazon.in/gp/customer-preferences/select-language.html")
        except Exception:
            pass
