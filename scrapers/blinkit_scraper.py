"""
Blinkit Seller Portal scraper.
Downloads daily sales & inventory Excel reports.
"""
import os
from datetime import date
from pathlib import Path

from .base_scraper import BaseScraper, logger


class BlinkitScraper(BaseScraper):
    portal_name = "blinkit"

    LOGIN_URL  = "https://seller.blinkit.com/login"
    REPORT_URL = "https://seller.blinkit.com/reports"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.email    = os.environ["BLINKIT_EMAIL"]
        self.password = os.environ["BLINKIT_PASSWORD"]

    def login(self) -> None:
        logger.info("[Blinkit] Logging in")
        self.page.goto(self.LOGIN_URL, wait_until="networkidle")
        self.page.fill('input[name="email"]', self.email)
        self.page.fill('input[name="password"]', self.password)
        self.page.click('button[type="submit"]')
        self.page.wait_for_url("**/dashboard**", timeout=30_000)
        logger.info("[Blinkit] Login successful")

    def download_report(self, report_date: date) -> Path:
        date_str = report_date.strftime("%Y-%m-%d")
        logger.info("[Blinkit] Downloading report for %s", date_str)

        self.page.goto(self.REPORT_URL, wait_until="networkidle")
        self.page.select_option('[data-id="report-type"]', "sales")
        self.page.fill('[data-id="date-from"]', date_str)
        self.page.fill('[data-id="date-to"]', date_str)
        self.page.click('[data-id="generate"]')
        self.page.wait_for_selector('[data-id="download-btn"]', timeout=60_000)

        output_path = self.portal_data_path / f"blinkit_sales_{date_str}.xlsx"
        with self.page.expect_download() as dl_info:
            self.page.click('[data-id="download-btn"]')
        dl_info.value.save_as(str(output_path))
        logger.info("[Blinkit] Saved to %s", output_path)
        return output_path

    def logout(self) -> None:
        try:
            self.page.click('[data-id="logout"]', timeout=5_000)
        except Exception:
            pass
