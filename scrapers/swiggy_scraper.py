"""
Swiggy Vendor Dashboard scraper.
Downloads daily sales & inventory Excel reports using Playwright.
"""
import os
import time
from datetime import date
from pathlib import Path

from .base_scraper import BaseScraper, logger


class SwiggyScraper(BaseScraper):
    portal_name = "swiggy"

    LOGIN_URL  = "https://vendor.swiggy.com/login"
    REPORT_URL = "https://vendor.swiggy.com/reports/sales"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.email    = os.environ["SWIGGY_EMAIL"]
        self.password = os.environ["SWIGGY_PASSWORD"]

    def login(self) -> None:
        logger.info("[Swiggy] Navigating to login page")
        self.page.goto(self.LOGIN_URL, wait_until="networkidle")
        self.page.fill('input[type="email"]', self.email)
        self.page.fill('input[type="password"]', self.password)
        self.page.click('button[type="submit"]')
        self.page.wait_for_url("**/dashboard**", timeout=30_000)
        logger.info("[Swiggy] Login successful")

    def download_report(self, report_date: date) -> Path:
        date_str = report_date.strftime("%Y-%m-%d")
        logger.info("[Swiggy] Downloading report for %s", date_str)

        self.page.goto(self.REPORT_URL, wait_until="networkidle")
        # Set date filter
        self.page.fill('[data-testid="start-date"]', date_str)
        self.page.fill('[data-testid="end-date"]', date_str)
        self.page.click('[data-testid="apply-filter"]')
        self.page.wait_for_load_state("networkidle")

        # Wait for download
        output_path = self.portal_data_path / f"swiggy_sales_{date_str}.xlsx"
        with self.page.expect_download() as dl_info:
            self.page.click('[data-testid="download-excel"]')
        download = dl_info.value
        download.save_as(str(output_path))
        logger.info("[Swiggy] Saved to %s", output_path)
        return output_path

    def logout(self) -> None:
        try:
            self.page.click('[data-testid="logout"]', timeout=5_000)
        except Exception:
            pass
