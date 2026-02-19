"""
Abstract base class for all portal scrapers.
Each portal scraper must implement: login(), download_report(), logout().
"""
import abc
import logging
import os
import time
from datetime import date, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


class BaseScraper(abc.ABC):
    """
    Base scraper using Playwright for browser automation.
    Subclasses implement portal-specific login and download logic.
    """

    portal_name: str = "base"
    max_retries: int = int(os.getenv("MAX_RETRY_ATTEMPTS", "3"))
    screenshot_on_error: bool = os.getenv("SCREENSHOT_ON_ERROR", "true").lower() == "true"

    def __init__(self, raw_data_path: str = None):
        self.raw_data_path = Path(raw_data_path or os.getenv("RAW_DATA_PATH", "./data/raw"))
        self.portal_data_path = self.raw_data_path / self.portal_name
        self.portal_data_path.mkdir(parents=True, exist_ok=True)
        self.browser = None
        self.page = None
        self._log = logging.getLogger(f"scrapers.{self.portal_name}")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _init_browser(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().__enter__()
        self.browser = self._pw.chromium.launch(headless=True)
        self.page = self.browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        )

    def _close_browser(self):
        try:
            if self.browser:
                self.browser.close()
            if hasattr(self, "_pw"):
                self._pw.__exit__(None, None, None)
        except Exception:
            pass

    def _screenshot(self, label: str):
        if self.screenshot_on_error and self.page:
            path = self.portal_data_path / f"error_{label}_{int(time.time())}.png"
            try:
                self.page.screenshot(path=str(path))
                self._log.info("Screenshot saved: %s", path)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def login(self) -> None:
        """Log in to the portal."""

    @abc.abstractmethod
    def download_report(self, report_date: date) -> Path:
        """Download the sales/inventory report for report_date. Returns the local file path."""

    @abc.abstractmethod
    def logout(self) -> None:
        """Log out / close the session."""

    # ------------------------------------------------------------------
    # Public run method with retry logic
    # ------------------------------------------------------------------

    def run(self, report_date: date = None) -> dict:
        """
        Full scraping cycle with retry. Returns:
        {"portal": str, "date": date, "file": Path | None, "status": str, "error": str | None}
        """
        if report_date is None:
            report_date = date.today() - timedelta(days=1)

        result = {
            "portal": self.portal_name,
            "date": report_date,
            "file": None,
            "status": "failed",
            "error": None,
        }

        for attempt in range(1, self.max_retries + 1):
            try:
                self._log.info("Attempt %d/%d for %s on %s", attempt, self.max_retries, self.portal_name, report_date)
                self._init_browser()
                self.login()
                file_path = self.download_report(report_date)
                self.logout()
                result.update({"file": file_path, "status": "success", "error": None})
                return result
            except Exception as exc:
                self._log.error("Attempt %d failed: %s", attempt, exc)
                self._screenshot(f"attempt_{attempt}")
                result["error"] = str(exc)
                if attempt < self.max_retries:
                    wait = 2 ** attempt
                    self._log.info("Waiting %ds before retry...", wait)
                    time.sleep(wait)
            finally:
                self._close_browser()

        return result
