"""
Refresh EasyEcom Google OAuth session — run this when the scraper fails with
'Google OAuth session in the profile may have expired'.

Opens a visible browser so you can complete Google sign-in manually if prompted.
Saves the refreshed session to the profile and uploads it to Drive.

Usage:
    cd C:/Users/accou/Documents/Projects/SOLARA-Data
    source venv/Scripts/activate
    python auth_easyecom.py
"""
import json
import sys
import logging
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("auth_easyecom")

_HERE = Path(__file__).resolve().parent
PROFILE_DIR = (_HERE / "scrapers" / "sessions" / "easyecom_profile").resolve()
SESSION_FILE = PROFILE_DIR.parent / "easyecom_session.json"

LOGIN_URL = "https://app.easyecom.io/V2/account/auth/login"
DASHBOARD_URL = "https://app.easyecom.io/V2/sales_dashboard.php"

try:
    from scrapers.profile_sync import download_profile, upload_profile, upload_session_file
except ImportError:
    log.warning("profile_sync not available — will not sync with Drive")
    download_profile = upload_profile = upload_session_file = lambda *a, **k: None


def main():
    log.info("=== EasyEcom Auth Refresh ===")
    log.info("Profile: %s", PROFILE_DIR)

    # Download latest profile from Drive
    try:
        download_profile("easyecom")
        log.info("Profile downloaded from Drive")
    except Exception as e:
        log.warning("Could not download profile from Drive: %s", e)

    if not PROFILE_DIR.exists():
        log.warning("Profile directory missing — starting with fresh profile")
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    # Inject existing session cookies if available
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        log.info("Opening VISIBLE browser — please complete Google sign-in if prompted")
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            slow_mo=300,
            args=["--start-maximized"],
            viewport={"width": 1400, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        )

        # Inject existing session cookies
        if SESSION_FILE.exists():
            try:
                state = json.loads(SESSION_FILE.read_text())
                cookies = state.get("cookies", [])
                if cookies:
                    ctx.add_cookies(cookies)
                    log.info("Injected %d cookies from existing session", len(cookies))
            except Exception as e:
                log.warning("Could not inject session cookies: %s", e)

        page = ctx.new_page()
        page.set_default_timeout(300_000)  # 5 min for manual interaction

        log.info("Navigating to EasyEcom login page...")
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # Click "Continue with Google"
        try:
            page.wait_for_selector('button:has-text("Continue with Google")', timeout=15_000)
            page.click('button:has-text("Continue with Google")')
            log.info("Clicked 'Continue with Google' — waiting for dashboard (up to 5 min)...")
        except Exception as e:
            log.warning("Could not find 'Continue with Google': %s — waiting for manual interaction", e)

        # Wait for successful login (up to 5 minutes for manual interaction)
        try:
            page.wait_for_url(
                lambda u: u.startswith("https://app.easyecom.io") and "/account/auth/" not in u,
                timeout=300_000,
            )
            log.info("Login successful! URL: %s", page.url)
        except Exception:
            log.error("Login did not complete within 5 minutes. URL: %s", page.url)
            ctx.close()
            return

        page.wait_for_timeout(3000)
        if "/account/auth/" in page.url:
            log.error("Bounced back to login. URL: %s", page.url)
            log.info("Please try manually: navigate to %s and log in", LOGIN_URL)
            input("Press Enter after completing login in the browser...")
            if "/account/auth/" in page.url:
                ctx.close()
                return

        log.info("Login verified. Saving session state...")

        # Save updated session state
        try:
            state = ctx.storage_state()
            SESSION_FILE.write_text(json.dumps(state))
            log.info("Session saved: %d cookies -> %s", len(state.get("cookies", [])), SESSION_FILE)
        except Exception as e:
            log.error("Could not save session: %s", e)

        input("Press Enter to close browser and upload profile to Drive...")
        ctx.close()

    # Upload updated profile and session to Drive
    try:
        upload_profile("easyecom")
        log.info("Profile uploaded to Drive")
    except Exception as e:
        log.warning("Could not upload profile: %s", e)

    try:
        upload_session_file("easyecom")
        log.info("Session file uploaded to Drive")
    except Exception as e:
        log.warning("Could not upload session file: %s", e)

    log.info("=== Auth refresh complete! Run the daily scraper again. ===")


if __name__ == "__main__":
    main()
