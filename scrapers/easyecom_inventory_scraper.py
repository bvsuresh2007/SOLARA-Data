"""
EasyEcom Manage Inventory scraper.

Downloads the current inventory snapshot from EasyEcom → Inventory → Manage Inventory.
Unlike the sales scraper, there is no report queue — the download starts immediately
when the Download Inventory button is clicked.

Flow:
  1. Fresh Google OAuth → dashboard (same login as sales scraper)
  2. Navigate to Manage Inventory page
  3. Dismiss "New Features" popup
  4. Click the Download Inventory button
  5. Capture and save the downloaded file

NOTE: INVENTORY_URL is a best-guess based on EasyEcom URL patterns.
      Verify on first run — if the page does not load, update INVENTORY_URL
      to match the URL shown in your browser at Inventory → Manage Inventory.
"""

import io
import os
import sys
import time
from datetime import date
from pathlib import Path


try:
    from .easyecom_scraper import EasyecomBaseScraper
    from .google_drive_upload import upload_to_drive as _upload_to_drive
except ImportError:
    from easyecom_scraper import EasyecomBaseScraper
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

# Force UTF-8 output on Windows
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# --- URLs ---
INVENTORY_URL = "https://app.easyecom.io/V2/current_inventory_update.php"

# --- Exports page (same URL as sales scraper) ---
EXPORTS_URL = "https://app.easyecom.io/V2/reports/import-export-report?jobType=1"

# --- Timing ---
DOWNLOAD_TIMEOUT_S = 300   # max seconds to wait for export to be ready
POLL_INTERVAL_S    = 10    # seconds between polls


class EasyecomInventoryScraper(EasyecomBaseScraper):
    """Downloads the daily inventory snapshot from EasyEcom Manage Inventory."""

    portal_name = "easyecom_inventory"

    # ------------------------------------------------------------------
    # Navigate to Manage Inventory page
    # ------------------------------------------------------------------

    def _go_to_inventory_page(self) -> None:
        self._log.info("[EasyEcom-Inv] Navigating to Manage Inventory: %s", INVENTORY_URL)
        try:
            self._page.goto(INVENTORY_URL, wait_until="domcontentloaded")
        except Exception as e:
            # Angular SPA pages can trigger spurious navigation errors; log and continue.
            self._log.warning("[EasyEcom-Inv] Navigation warning (continuing): %s", e)
        self._page.wait_for_timeout(4000)
        self._dismiss_popups()
        self._page.wait_for_timeout(1000)
        self._shot("inventory_page_ready")
        self._log.info("[EasyEcom-Inv] Inventory page loaded. Current URL: %s", self._page.url)

    # ------------------------------------------------------------------
    # Phase 1: click the queue button on the inventory page
    # ------------------------------------------------------------------

    def _queue_inventory_export(self) -> float:
        """
        Click the 'Download Full Report' button on the inventory page.
        This queues an export job — it does NOT immediately stream a file.
        Returns the timestamp at which the button was clicked.
        """
        self._log.info("[EasyEcom-Inv] Looking for Download / Full Report button")
        self._shot("before_queue")

        btn_info = self._page.evaluate("""
            () => {
                const candidates = Array.from(
                    document.querySelectorAll('button, a, [role="button"], [onclick]')
                );
                // Priority 1: 'download' + 'inventor' in text
                for (const el of candidates) {
                    const text = (el.innerText || el.textContent || '').trim().toLowerCase();
                    if (text.includes('download') && text.includes('inventor')) {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0)
                            return {found: true, x: rect.left + rect.width/2,
                                    y: rect.top + rect.height/2, text: (el.innerText||'').trim()};
                    }
                }
                // Priority 2: 'download full report'
                for (const el of candidates) {
                    const text = (el.innerText || el.textContent || '').trim().toLowerCase();
                    if (text.includes('download full') || text.includes('full report')) {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0)
                            return {found: true, x: rect.left + rect.width/2,
                                    y: rect.top + rect.height/2, text: (el.innerText||'').trim()};
                    }
                }
                // Priority 3: any visible 'download' button
                for (const el of candidates) {
                    const text = (el.innerText || el.textContent || '').trim().toLowerCase();
                    if (text.includes('download')) {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0)
                            return {found: true, fallback: true, x: rect.left + rect.width/2,
                                    y: rect.top + rect.height/2, text: (el.innerText||'').trim()};
                    }
                }
                return {found: false};
            }
        """)

        if not btn_info.get('found'):
            self._shot("queue_btn_not_found")
            raise RuntimeError(
                "Could not find Download button on Manage Inventory page. "
                f"URL: {self._page.url}"
            )

        self._log.info("[EasyEcom-Inv] Clicking %r to queue export (fallback=%s)",
                       btn_info.get('text', ''), btn_info.get('fallback', False))
        self._page.mouse.click(btn_info['x'], btn_info['y'])
        queued_at = time.time()
        self._page.wait_for_timeout(3000)
        self._shot("after_queue_click")
        return queued_at

    # ------------------------------------------------------------------
    # Phase 2: poll exports page until inventory row is complete
    # ------------------------------------------------------------------

    def _poll_exports_for_inventory(self, output_path: Path, queued_at: float) -> Path:
        """
        Poll /V2/reports/import-export-report?jobType=1 until an inventory
        export row is complete, then download it via JS dispatchEvent.
        Mirrors the sales scraper's _find_and_download_report exactly.
        """
        deadline = time.time() + DOWNLOAD_TIMEOUT_S
        self._log.info("[EasyEcom-Inv] Polling export jobs page for inventory row...")

        while time.time() < deadline:
            try:
                if EXPORTS_URL in self._page.url:
                    self._page.reload(wait_until="domcontentloaded", timeout=30_000)
                else:
                    self._page.goto(EXPORTS_URL, wait_until="domcontentloaded", timeout=30_000)
            except Exception as nav_err:
                self._log.warning("[EasyEcom-Inv] Nav error: %s", nav_err)
                time.sleep(5)
                continue

            self._page.wait_for_timeout(2000)
            self._dismiss_popups()
            self._shot("exports_panel")

            # Log first few rows for diagnostics
            table_rows = self._page.evaluate("""
                () => Array.from(document.querySelectorAll('table tr'))
                    .slice(0, 8)
                    .map(r => (r.innerText || '').trim().replace(/\\t+/g, ' | ').substring(0, 150))
            """)
            self._log.info("[EasyEcom-Inv] Export table: %s", table_rows[:4])

            # Find the inventory row using the same logic as the sales scraper
            dl_info = self._page.evaluate("""
                () => {
                    const rows = Array.from(document.querySelectorAll('table tr'));
                    for (const row of rows) {
                        const cells = Array.from(row.querySelectorAll('td'));
                        if (cells.length < 5) continue;

                        // Match any cell containing 'inventor' (catches all inventory job names)
                        const hasInventory = cells.some(td =>
                            (td.innerText || '').includes('DownloadInventoryJob')
                        );
                        if (!hasInventory) continue;

                        const cellTexts = cells.map(c => (c.innerText || '').trim());
                        const fullText  = cellTexts.join(' ').toLowerCase();

                        // In-progress check
                        const inProgress = fullText.includes('in-progress')
                            || fullText.includes('in progress')
                            || fullText.includes('pending')
                            || fullText.includes('processing')
                            || fullText.includes('queued');
                        if (inProgress)
                            return {not_ready: true, status: 'in_progress', cellTexts};

                        // Completion check: "Download Ended At" (index 4) non-empty OR keywords
                        const endedAt = cellTexts[4] || '';
                        const hasEndedAt = endedAt.length > 2
                            && endedAt !== '-' && endedAt.toLowerCase() !== 'n/a';
                        const hasCompletionKw = fullText.includes('complet')
                            || fullText.includes('success')
                            || fullText.includes('processed')
                            || fullText.includes('ready')
                            || fullText.includes('done')
                            || fullText.includes('finish');

                        if (!hasEndedAt && !hasCompletionKw)
                            return {not_ready: true, status: 'unknown', cellTexts};

                        // Row is complete — find download link in Action column
                        const actionCell = cells[cells.length - 1];
                        const allLinks = Array.from(
                            actionCell.querySelectorAll('a, button, [onclick]')
                        );
                        row.scrollIntoView({block: 'center', inline: 'nearest'});

                        for (const link of allLinks) {
                            const rect = link.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {
                                return {
                                    ready: true,
                                    cellTexts,
                                    linkText: link.textContent.trim()
                                              || link.title
                                              || link.getAttribute('data-original-title')
                                              || '(icon)',
                                    href:    link.getAttribute('href') || '',
                                    onclick: link.getAttribute('onclick') || '',
                                    x: rect.left + rect.width  / 2,
                                    y: rect.top  + rect.height / 2,
                                };
                            }
                        }

                        return {
                            ready_no_link: true,
                            cellTexts,
                            allLinkDebug: allLinks.map(l => ({
                                text:    l.textContent.trim().substring(0, 40),
                                href:    l.getAttribute('href') || '',
                                onclick: l.getAttribute('onclick') || '',
                                cls:     l.className || '',
                            })),
                        };
                    }
                    return null;
                }
            """)

            if dl_info is None:
                self._log.info("[EasyEcom-Inv] No inventory row found yet")
            elif dl_info.get('not_ready'):
                self._log.info("[EasyEcom-Inv] Export not ready [%s]: %s",
                               dl_info.get('status'), dl_info.get('cellTexts', []))
            elif dl_info.get('ready_no_link'):
                self._log.warning("[EasyEcom-Inv] Complete but no visible download link. "
                                  "Cells=%s Links=%s",
                                  dl_info.get('cellTexts'), dl_info.get('allLinkDebug'))
            elif dl_info.get('ready'):
                self._log.info("[EasyEcom-Inv] Export ready — link=%r href=%s",
                               dl_info.get('linkText'), dl_info.get('href'))
                result = self._try_download_inventory(dl_info, output_path)
                if result:
                    return result

            self._log.info("[EasyEcom-Inv] Waiting %ds...", POLL_INTERVAL_S)
            time.sleep(POLL_INTERVAL_S)

        self._shot("download_timeout")
        raise RuntimeError(
            f"Inventory export not ready after {DOWNLOAD_TIMEOUT_S}s. "
            f"Check {EXPORTS_URL} manually."
        )

    def _try_download_inventory(self, dl_info: dict, output_path: Path) -> "Path | None":
        """
        Download the inventory export using JS dispatchEvent (Strategy 1)
        or mouse.click (Strategy 2). Mirrors the sales scraper's _try_download.
        """
        new_pages = []

        def on_new_page(page):
            new_pages.append(page)
            self._log.debug("[EasyEcom-Inv] New popup: %s", page.url)

        self._ctx.on('page', on_new_page)

        try:
            # Strategy 1: JS dispatchEvent on the inventory row's action link
            try:
                with self._page.expect_download(timeout=15_000) as dl_handle:
                    self._page.evaluate("""
                        () => {
                            for (const row of document.querySelectorAll('table tr')) {
                                const cells = Array.from(row.querySelectorAll('td'));
                                if (cells.some(td =>
                                        (td.innerText||'').toLowerCase().includes('inventor'))) {
                                    const actionCell = cells[cells.length - 1];
                                    const link = actionCell.querySelector(
                                        'a.download_result, a, button'
                                    );
                                    if (link) {
                                        link.dispatchEvent(new MouseEvent('click',
                                            {bubbles: true, cancelable: true, view: window}));
                                    }
                                    return;
                                }
                            }
                        }
                    """)
                dl = dl_handle.value
                dl.save_as(str(output_path))
                self._log.info("[EasyEcom-Inv] Download complete: %s", output_path)
                return self._extract_from_zip(output_path)
            except Exception as e1:
                self._log.info("[EasyEcom-Inv] Strategy 1 failed: %s", e1)

            self._page.wait_for_timeout(2000)

            # Strategy 2: standard mouse.click
            try:
                with self._page.expect_download(timeout=15_000) as dl_handle:
                    self._page.mouse.click(dl_info['x'], dl_info['y'])
                dl = dl_handle.value
                dl.save_as(str(output_path))
                self._log.info("[EasyEcom-Inv] Download complete (strategy 2): %s", output_path)
                return self._extract_from_zip(output_path)
            except Exception as e2:
                self._log.warning("[EasyEcom-Inv] Both strategies failed. New pages: %s",
                                  [p.url for p in new_pages])
                return None

        finally:
            try:
                self._ctx.remove_listener('page', on_new_page)
            except Exception:
                pass

    def _extract_from_zip(self, zip_path: Path) -> Path:
        """Extract a single CSV/XLSX from a ZIP, or return the file as-is."""
        import zipfile as _zf
        if not _zf.is_zipfile(str(zip_path)):
            self._log.info("[EasyEcom-Inv] Downloaded file is not a ZIP — using as-is")
            return zip_path
        with _zf.ZipFile(str(zip_path)) as zf:
            members = [n for n in zf.namelist()
                       if n.lower().endswith(('.csv', '.xlsx'))]
            if not members:
                self._log.warning("[EasyEcom-Inv] ZIP has no CSV/XLSX: %s", zf.namelist())
                return zip_path
            name = members[0]
            suffix = Path(name).suffix
            out = zip_path.with_suffix(suffix)
            with zf.open(name) as src, open(str(out), 'wb') as dst:
                dst.write(src.read())
            self._log.info("[EasyEcom-Inv] Extracted %s -> %s", name, out)
        zip_path.unlink()
        return out

    def _download_inventory(self, report_date: date) -> Path:
        """Queue the inventory export then poll the exports page until ready."""
        date_str    = report_date.strftime("%Y-%m-%d")
        output_path = self.out_dir / f"easyecom_inventory_{date_str}.zip"
        queued_at   = self._queue_inventory_export()
        return self._poll_exports_for_inventory(output_path, queued_at)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self, report_date: date = None) -> dict:
        """Full scraping cycle. Returns status dict."""
        if report_date is None:
            report_date = date.today()

        result = {
            "portal": self.portal_name,
            "date": report_date,
            "file": None,
            "status": "failed",
            "error": None,
        }

        try:
            from scrapers.profile_sync import download_profile, upload_profile
        except ImportError:
            from profile_sync import download_profile, upload_profile

        login_ok = False
        try:
            # Pull latest profile from Drive before launching browser
            download_profile("easyecom")

            self._init_browser()
            self.login()
            login_ok = True

            self._go_to_inventory_page()
            file_path = self._download_inventory(report_date)
            result.update({"file": file_path, "status": "success"})

            # Upload to Google Drive: SolaraDashboard Reports / YYYY-MM / EasyEcom /
            if _upload_to_drive and file_path:
                drive_link = _upload_to_drive(
                    portal="EasyEcom",
                    report_date=report_date,
                    file_path=file_path,
                )
                if drive_link:
                    result["drive_link"] = drive_link
                    self._log.info("[EasyEcom-Inv] Uploaded to Drive: %s", drive_link)

        except Exception as exc:
            self._log.error("[EasyEcom-Inv] Run failed: %s", exc)
            result["error"] = str(exc)
        finally:
            self._close_browser()
            if login_ok:
                upload_profile("easyecom")
            else:
                self._log.info(
                    "[EasyEcom-Inv] Skipping profile upload — login did not succeed, Drive profile preserved"
                )

        return result


# ------------------------------------------------------------------
# CLI entry point for manual testing
# ------------------------------------------------------------------
if __name__ == "__main__":
    import logging
    from dotenv import load_dotenv
    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    scraper = EasyecomInventoryScraper(headless=False)
    result = scraper.run()
    print("\nResult:", result)
