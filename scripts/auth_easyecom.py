"""
EasyEcom Google login helper.

Opens a visible Chrome window using the persistent profile at
scrapers/sessions/easyecom_profile/. Clicks "Continue with Google",
waits for the dashboard redirect (up to 5 minutes for manual Google auth),
then closes the browser and uploads the profile to Drive.

Usage:
  python scripts/auth_easyecom.py
"""

import logging
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("auth_easyecom")

PROFILE_DIR = ROOT / "scrapers" / "sessions" / "easyecom_profile"
LOGIN_URL    = "https://app.easyecom.io/V2/account/auth/login"


def main():
    # Ensure profile directory exists (creates an empty one on first run)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Profile dir: %s", PROFILE_DIR)

    from playwright.sync_api import sync_playwright

    pw  = sync_playwright().__enter__()
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=False,
        slow_mo=0,
        args=["--start-maximized"],
        viewport={"width": 1400, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
    )
    page = ctx.new_page()
    page.set_default_timeout(30_000)

    print("\n" + "=" * 60)
    print("EasyEcom login — browser opening...")
    print("Complete Google login in the browser window.")
    print("This script will close automatically once you are logged in.")
    print("=" * 60 + "\n")

    logger.info("Navigating to EasyEcom login page...")
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)

    # Click "Continue with Google" — if the profile already has a Google session
    # it will auto-complete; otherwise the user completes it manually in the browser.
    try:
        logger.info("Waiting for 'Continue with Google' button...")
        page.wait_for_selector('button:has-text("Continue with Google")', timeout=15_000)
        page.click('button:has-text("Continue with Google")')
        logger.info("Clicked 'Continue with Google' — waiting for redirect...")
    except Exception as e:
        logger.warning("Could not auto-click button (%s) — waiting for manual login...", e)

    # Wait up to 5 minutes for a successful redirect to the EasyEcom dashboard.
    # This gives plenty of time for Google OAuth if a fresh login is required.
    try:
        page.wait_for_url(
            lambda u: u.startswith("https://app.easyecom.io") and "/account/auth/" not in u,
            timeout=300_000,
        )
    except Exception:
        # Handle multi-account selection page
        if "multiple-signin" in page.url or "accounts.google.com" in page.url:
            logger.warning("Account selection detected — waiting another 60s for manual selection...")
            try:
                page.wait_for_url(
                    lambda u: u.startswith("https://app.easyecom.io") and "/account/auth/" not in u,
                    timeout=60_000,
                )
            except Exception as e2:
                logger.error("Login failed: %s — URL: %s", e2, page.url)
                ctx.close()
                pw.__exit__(None, None, None)
                sys.exit(1)
        else:
            logger.error("Login timeout — URL: %s", page.url)
            ctx.close()
            pw.__exit__(None, None, None)
            sys.exit(1)

    logger.info("Login successful! Dashboard URL: %s", page.url)
    print("\n" + "=" * 60)
    print("LOGIN SUCCESSFUL")
    print(f"URL: {page.url}")
    print("Closing browser in 3 seconds and saving profile...")
    print("=" * 60)
    time.sleep(3)

    logger.info("Closing browser...")
    ctx.close()
    pw.stop()
    logger.info("Browser closed. Profile saved locally at: %s", PROFILE_DIR)

    # Upload profile to Drive so CI picks it up on next run
    folder_id = os.environ.get("PROFILE_STORAGE_DRIVE_FOLDER_ID")
    if folder_id:
        logger.info("Uploading profile to Google Drive (folder: %s)...", folder_id)
        try:
            from scrapers.profile_sync import upload_profile
            ok = upload_profile("easyecom")
            if ok:
                logger.info("Profile uploaded to Drive successfully.")
            else:
                logger.warning("Drive upload returned False — profile saved locally only.")
        except Exception as e:
            logger.error("Drive upload failed: %s", e)
            logger.info("Profile is still saved locally at: %s", PROFILE_DIR)
    else:
        logger.info("PROFILE_STORAGE_DRIVE_FOLDER_ID not set — profile saved locally only.")
        logger.info("To sync to CI, set this env var and re-run.")

    print("\nDone — profile saved and ready for use.")


if __name__ == "__main__":
    main()
