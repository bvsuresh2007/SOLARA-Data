"""
Zepto Vendor Dashboard scraper.
Downloads daily sales & inventory Excel reports.
"""
import os
from datetime import date
from pathlib import Path

from .base_scraper import BaseScraper, logger


class ZeptoScraper(BaseScraper):
    portal_name = "zepto"

    LOGIN_URL  = "https://vendor.zepto.co/login"
    REPORT_URL = "https://vendor.zepto.co/reports"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.email    = os.environ["ZEPTO_EMAIL"]
        self.password = os.environ["ZEPTO_PASSWORD"]

    def login(self) -> None:
        logger.info("[Zepto] Logging in")
        self.page.goto(self.LOGIN_URL, wait_until="networkidle")
        self.page.fill('input[type="email"]', self.email)
        self.page.fill('input[type="password"]', self.password)
        self.page.click('button[type="submit"]')
        self.page.wait_for_url("**/dashboard**", timeout=30_000)
        logger.info("[Zepto] Login successful")

    def download_report(self, report_date: date) -> Path:
        date_str = report_date.strftime("%d-%m-%Y")  # Zepto uses DD-MM-YYYY
        logger.info("[Zepto] Downloading report for %s", date_str)

        self.page.goto(self.REPORT_URL, wait_until="networkidle")
        self.page.fill('[placeholder="From Date"]', date_str)
        self.page.fill('[placeholder="To Date"]', date_str)
        self.page.click('button:has-text("Download")')
        self.page.wait_for_load_state("networkidle")

        output_path = self.portal_data_path / f"zepto_sales_{report_date.strftime('%Y-%m-%d')}.xlsx"
        with self.page.expect_download() as dl_info:
            self.page.click('a:has-text("Export")')
        dl_info.value.save_as(str(output_path))
        logger.info("[Zepto] Saved to %s", output_path)
        return output_path

    def logout(self) -> None:
        try:
            self.page.click('button:has-text("Logout")', timeout=5_000)
        except Exception:
            pass
