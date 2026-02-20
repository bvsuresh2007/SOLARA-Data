"""
One-time Blinkit authentication setup.

Run this ONCE to log in and save the browser profile.
The scraper will then use the saved profile on every subsequent
run without triggering OTP again.

Usage:
    python auth_blinkit.py

What it does:
    1. Opens a Chrome window using a persistent profile (blinkit_profile/)
    2. Navigates to partnersbiz.com
    3. If already logged in → done, just closes.
    4. If not logged in:
         - Fills your email from .env (BLINKIT_EMAIL)
         - Clicks "Request OTP" ONCE
         - Waits up to 2 minutes for OTP email to arrive (via Gmail API)
         - Types the OTP automatically
         - Selects the first company on the "Access dashboard as" screen
         - Confirms login and saves the profile automatically

Requirements:
    - BLINKIT_EMAIL set in .env
    - token.json present (run auth_gmail.py first to set up Gmail access)
"""

import io
import os
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

PROFILE_DIR = Path("blinkit_profile").resolve()
LOGIN_URL   = "https://partnersbiz.com/"
EMAIL       = os.environ.get("BLINKIT_EMAIL", "").split("#")[0].strip()

# OTP email sender confirmed from previous inspector runs
BLINKIT_OTP_SENDER = "noreply@partnersbiz.com"


def _fetch_otp_from_gmail(after_epoch: int, max_wait: int = 120, poll_interval: int = 10) -> str | None:
    """Poll Gmail for the latest OTP from Blinkit, up to max_wait seconds."""
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from scrapers.gmail_otp import fetch_latest_otp
    except ImportError:
        print("  WARNING: scrapers.gmail_otp not importable — cannot auto-fetch OTP.")
        return None

    deadline = time.time() + max_wait
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        remaining = int(deadline - time.time())
        print(f"  Polling Gmail for OTP (attempt {attempt}, {remaining}s remaining)...")
        try:
            otp = fetch_latest_otp(sender=BLINKIT_OTP_SENDER, after_epoch=after_epoch)
            if otp:
                print(f"  OTP received: {otp}")
                return otp
        except Exception as e:
            print(f"  Gmail poll error: {e}")
        if time.time() < deadline:
            time.sleep(poll_interval)
    print("  OTP not received within the time limit.")
    return None


def is_logged_in(page) -> bool:
    """Return True if the current page looks like a post-login dashboard."""
    url = page.url
    return (
        "partnersbiz.com" in url
        and "/login" not in url
        and url.rstrip("/") != "https://partnersbiz.com"
    )


def _handle_company_selector(page) -> bool:
    """
    Handle the 'Access dashboard as' company selector that appears after OTP.
    Clicks the first company option in the list.
    Returns True if selector was found and clicked.
    """
    try:
        page.wait_for_timeout(2000)
        # Check if company selector is present
        selector_visible = page.evaluate("""
            () => {
                const heading = document.body.innerText || '';
                return heading.includes('Access dashboard as');
            }
        """)
        if not selector_visible:
            return False

        print("Company selector visible. Clicking first company...")

        # Find and click the first company option
        clicked = page.evaluate("""
            () => {
                // The company list items are clickable elements
                const items = Array.from(document.querySelectorAll(
                    '[class*="company"], [class*="account"], [class*="partner"], ' +
                    '[class*="merchant"], li, .list-item'
                )).filter(el => {
                    const r = el.getBoundingClientRect();
                    return r.width > 50 && r.height > 10 && r.height < 200;
                });

                // Find items that contain company-like text
                const nonHeading = items.filter(el => {
                    const txt = el.innerText.trim();
                    return txt.length > 0 && txt.length < 200
                        && !txt.includes('Access dashboard')
                        && el.tagName !== 'BODY'
                        && el.tagName !== 'SECTION'
                        && el.tagName !== 'DIV' || el.querySelector('h3, h4, p, span');
                });

                if (nonHeading.length > 0) {
                    nonHeading[0].click();
                    return {clicked: nonHeading[0].innerText.trim().substring(0, 80)};
                }
                return {clicked: null};
            }
        """)
        if clicked and clicked.get('clicked'):
            print(f"  Clicked company: {clicked['clicked']}")
            page.wait_for_timeout(3000)
            return True

        # Fallback: try clicking any visible >link element on the page
        page.screenshot(path="blinkit_company_selector.png")
        print("  Could not auto-click company. Screenshot saved: blinkit_company_selector.png")
        print("  Please click your company in the browser window and press Enter when done...")
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            print("  (non-interactive — waiting 30s)")
            time.sleep(30)
        return True
    except Exception as e:
        print(f"  Company selector error: {e}")
        return False


def main():
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Profile dir: {PROFILE_DIR}")
    print(f"Email: {EMAIL or '(BLINKIT_EMAIL not set in .env)'}")

    if not EMAIL:
        print("\nERROR: Set BLINKIT_EMAIL in your .env file first.")
        sys.exit(1)

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            slow_mo=200,
            args=["--start-maximized"],
            viewport={"width": 1400, "height": 900},
        )
        page = ctx.new_page()
        page.set_default_timeout(30_000)

        print("\nNavigating to partnersbiz.com...")
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        # Check if already logged in
        if is_logged_in(page):
            print(f"\n✓ Already logged in! URL: {page.url}")
            print("Profile is valid — no OTP needed.")
            print("Closing in 5s...")
            time.sleep(5)
            ctx.close()
            return

        print(f"\nNot logged in (URL: {page.url}). Starting login flow...")

        # Fill email
        try:
            email_input = page.locator('input[placeholder="Enter Email ID"]')
            email_input.wait_for(state="visible", timeout=10_000)
            email_input.fill(EMAIL)
            page.wait_for_timeout(500)
            print(f"Filled email: {EMAIL}")
        except Exception as e:
            print(f"ERROR: Could not find email input: {e}")
            page.screenshot(path="blinkit_auth_error.png")
            ctx.close()
            return

        # Click Request OTP — ONLY ONCE
        print("Clicking 'Request OTP'...")
        otp_requested_at = int(time.time())
        page.locator('button:has-text("Request OTP")').click()
        page.wait_for_timeout(2000)

        # Wait for OTP boxes to appear
        try:
            page.locator('input[maxlength="1"]').first.wait_for(state="visible", timeout=15_000)
            print("OTP boxes visible.")
        except Exception:
            print("OTP boxes not found — check the browser window.")
            page.screenshot(path="blinkit_auth_no_otp_boxes.png")

        # Auto-fetch OTP via Gmail
        print(f"\nWaiting for OTP email from {BLINKIT_OTP_SENDER}...")
        otp = _fetch_otp_from_gmail(after_epoch=otp_requested_at, max_wait=120, poll_interval=10)

        if otp:
            print(f"Typing OTP: {otp}")
            otp_first = page.locator('input[maxlength="1"]').first
            otp_first.click()
            page.keyboard.type(otp)
            page.wait_for_timeout(1000)

            print("Clicking 'Submit OTP'...")
            page.locator('button:has-text("Submit OTP")').click()
            page.wait_for_timeout(3000)

            # Handle company selector
            _handle_company_selector(page)
            page.wait_for_timeout(2000)
        else:
            # Fallback: wait for user to enter OTP manually
            print("\n" + "="*60)
            print(">>> Could not auto-fetch OTP from Gmail.")
            print(">>> Please enter the OTP manually in the browser window.")
            print(">>> Press Enter here when done, or just wait 3 minutes...")
            print("="*60)
            try:
                input()
            except (EOFError, KeyboardInterrupt):
                # Non-interactive mode — poll for login completion
                try:
                    page.wait_for_url(
                        lambda u: "partnersbiz.com" in u
                                  and "/login" not in u
                                  and u.rstrip("/") != "https://partnersbiz.com",
                        timeout=180_000,
                    )
                except Exception:
                    print("\nTimeout waiting for manual login.")

        page.wait_for_timeout(2000)

        # Final check
        print(f"\n--- Post-login page ---")
        print(f"URL: {page.url}")
        try:
            print(f"Title: {page.title()}")
        except Exception:
            pass

        if is_logged_in(page):
            print("✓ Successfully logged in to partnersbiz.com")
        else:
            print(f"WARNING: URL after login: {page.url}")
            print("May not be fully logged in — check the browser window.")
            page.screenshot(path="blinkit_auth_final.png")

        # Profile is saved automatically on ctx.close()
        print(f"\nSaving profile to {PROFILE_DIR}...")
        ctx.close()
        print("Done! Run the Blinkit scraper now — it will use this saved session.")


if __name__ == "__main__":
    main()
