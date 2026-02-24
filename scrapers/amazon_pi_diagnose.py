"""
Amazon PI diagnostic script — targeted at Time Period dropdown.

Focuses on: click Time Period, capture the open dropdown HTML/screenshot,
inspect the date inputs and Daily tab structure.

Usage:
    python scrapers/amazon_pi_diagnose.py

Outputs to: data/raw/amazon_pi/diagnose2/
"""
import json
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("diagnose")

_HERE   = Path(__file__).resolve().parent
PROFILE = (_HERE / "sessions" / "amazon_pi_profile").resolve()
OUT     = Path("data/raw/amazon_pi/diagnose2")
OUT.mkdir(parents=True, exist_ok=True)

REPORT_DATE = date.today() - timedelta(days=1)

def shot(page, label):
    p = OUT / f"{label}.png"
    page.screenshot(path=str(p), full_page=True)
    log.info("Screenshot: %s", p.name)

def dump(page, label):
    p = OUT / f"{label}.html"
    p.write_text(page.content(), encoding="utf-8")
    log.info("HTML dump: %s", p.name)

def dump_visible_inputs(page, label):
    data = page.evaluate("""() =>
        Array.from(document.querySelectorAll('input, select, textarea'))
             .filter(i => i.offsetParent !== null || i.getBoundingClientRect().width > 0)
             .map(i => ({
                 tag: i.tagName, id: i.id, name: i.name, type: i.type || '',
                 placeholder: i.placeholder || '', value: i.value || '',
                 readOnly: i.readOnly, class: i.className.slice(0,100),
                 ariaLabel: i.getAttribute('aria-label') || '',
                 rect: (r => ({w: Math.round(r.width), h: Math.round(r.height)}))(i.getBoundingClientRect())
             }))
    """)
    p = OUT / f"{label}.json"
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Inputs dump (%d): %s", len(data), p.name)
    for i in data:
        log.info("  [%s] id=%r name=%r type=%r placeholder=%r value=%r readOnly=%r ariaLabel=%r size=%sx%s",
                 i["tag"], i["id"], i["name"], i["type"],
                 i["placeholder"], i["value"], i["readOnly"], i["ariaLabel"],
                 i["rect"]["w"], i["rect"]["h"])

def main():
    from playwright.sync_api import sync_playwright
    PROFILE.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE),
            headless=False,
            slow_mo=400,
            args=["--start-maximized"],
            viewport={"width": 1400, "height": 900},
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.set_default_timeout(30_000)

        # --- Login ---
        page.goto(os.environ["AMAZON_PI_LINK"], wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        if not page.url.startswith("https://pi.amazon.in"):
            log.info("Logging in...")
            page.locator('#ap_email').fill(os.environ["AMAZON_PI_EMAIL"])
            page.locator('input[type="submit"]').click()
            page.locator('#ap_password').wait_for(state="visible", timeout=15_000)
            page.locator('#ap_password').fill(os.environ["AMAZON_PI_PASSWORD"])
            page.locator('#signInSubmit').click()
            try:
                otp = page.locator('#auth-mfa-otpcode, input[name="otpCode"]')
                otp.wait_for(state="visible", timeout=8_000)
                from scrapers.totp_helper import get_totp_code
                otp.fill(get_totp_code("AMAZON_PI_TOTP_SECRET"))
                page.locator('#auth-signin-button, input[type="submit"]').first.click()
            except Exception:
                pass
            page.wait_for_url("https://pi.amazon.in/**", timeout=30_000)

        log.info("Logged in: %s", page.url)

        # --- Navigate to SBG ---
        page.goto("https://pi.amazon.in/reports/sbg", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # --- Set Brand = SOLARA ---
        log.info("Setting brand = SOLARA")
        page.locator('select#brand-dropdown').wait_for(state="visible", timeout=15_000)
        page.locator('select#brand-dropdown').select_option(label="SOLARA")
        page.wait_for_timeout(1000)

        # --- Set Category = Kitchen Appliances ---
        log.info("Setting category = Kitchen Appliances")
        page.locator('select#category-dropdown').wait_for(state="visible", timeout=15_000)
        page.locator('select#category-dropdown').select_option(label="Kitchen Appliances")

        # --- WAIT for page to finish loading after category change ---
        log.info("Waiting for Time Period element to be ready...")
        try:
            page.locator('#aue-time-period-option').wait_for(state="visible", timeout=20_000)
            log.info("Time Period element is visible")
        except Exception as e:
            log.warning("Wait failed: %s — trying anyway", e)
        page.wait_for_timeout(1500)
        shot(page, "A_before_tp_click")

        # --- Click Time Period ---
        log.info("Clicking Time Period dropdown...")
        tp = page.locator('#aue-time-period-option')
        log.info("is_visible=%s", tp.is_visible())
        tp.click()
        page.wait_for_timeout(2000)
        shot(page, "B_after_tp_click")
        dump(page, "B_after_tp_click")

        log.info("=== Visible elements after clicking Time Period ===")
        elements = page.evaluate("""() => {
            const tags = 'input, select, button, a, [role="tab"], li, div[class*="tab"], span[class*="tab"]';
            return Array.from(document.querySelectorAll(tags))
                .filter(el => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                })
                .map(el => ({
                    tag: el.tagName,
                    id: el.id,
                    class: el.className.slice(0, 80),
                    text: (el.innerText || el.value || '').slice(0, 60).trim(),
                    type: el.type || '',
                    value: el.value || '',
                    placeholder: el.placeholder || '',
                    readOnly: el.readOnly || false,
                    ariaLabel: el.getAttribute('aria-label') || '',
                }));
        }""")
        p = OUT / "B_elements.json"
        p.write_text(json.dumps(elements, indent=2, ensure_ascii=False), encoding="utf-8")
        for el in elements:
            log.info("  [%s] id=%r class=%r text=%r type=%r value=%r readOnly=%r",
                     el["tag"], el["id"], el["class"][:50], el["text"][:50],
                     el["type"], el["value"], el["readOnly"])

        # --- Look specifically for the Daily tab ---
        log.info("=== Searching for Daily tab ===")
        daily_candidates = page.evaluate("""() =>
            Array.from(document.querySelectorAll('*'))
                .filter(el => {
                    const t = (el.innerText || '').trim();
                    const r = el.getBoundingClientRect();
                    return (t === 'Daily' || t === 'DAILY') && r.width > 0;
                })
                .map(el => ({
                    tag: el.tagName, id: el.id,
                    class: el.className.slice(0,100),
                    text: el.innerText.trim(),
                    outerHTML: el.outerHTML.slice(0, 300)
                }))
        """)
        log.info("Daily tab candidates: %d", len(daily_candidates))
        for c in daily_candidates:
            log.info("  %s", c)

        # --- Click Daily if found ---
        if daily_candidates:
            # Try clicking the first visible one
            for c in daily_candidates:
                try:
                    sel = f"#{c['id']}" if c['id'] else None
                    if not sel:
                        # Use text
                        el = page.get_by_text("Daily", exact=True).first
                    else:
                        el = page.locator(sel).first
                    el.click()
                    log.info("Clicked Daily tab")
                    break
                except Exception as e:
                    log.warning("Could not click: %s", e)
        page.wait_for_timeout(1000)
        shot(page, "C_after_daily_click")
        dump(page, "C_after_daily_click")

        # --- Dump all inputs after Daily click ---
        log.info("=== Inputs after clicking Daily ===")
        dump_visible_inputs(page, "C_inputs_after_daily")

        # --- Look for date inputs specifically ---
        log.info("=== Looking for date input areas ===")
        date_context = page.evaluate("""() => {
            // Find elements containing 'From', 'To', date-picker related classes
            const candidates = Array.from(document.querySelectorAll('*')).filter(el => {
                const r = el.getBoundingClientRect();
                if (r.width === 0) return false;
                const cls = el.className || '';
                const id = el.id || '';
                const text = (el.innerText || '').toLowerCase();
                return cls.includes('date') || cls.includes('from') || cls.includes('range') ||
                       id.includes('date') || id.includes('from') || id.includes('range') ||
                       text === 'from' || text === 'to';
            });
            return candidates.slice(0, 20).map(el => ({
                tag: el.tagName, id: el.id,
                class: el.className.slice(0,100),
                text: (el.innerText || '').slice(0,60).trim(),
                outerHTML: el.outerHTML.slice(0, 400)
            }));
        }""")
        log.info("Date-related elements: %d", len(date_context))
        for d in date_context:
            log.info("  [%s] id=%r class=%r text=%r", d["tag"], d["id"], d["class"][:60], d["text"][:60])
            log.info("    HTML: %s", d["outerHTML"][:200])

        # --- Try to fill date input ---
        date_str = REPORT_DATE.strftime("%m/%d/%Y")
        log.info("=== Attempting to fill date: %s ===", date_str)
        all_inputs = [i for i in page.locator('input').all()
                      if page.evaluate("el => el.getBoundingClientRect().width > 0", i.element_handle())]
        log.info("Inputs with non-zero width: %d", len(all_inputs))
        for idx, inp in enumerate(all_inputs):
            info = page.evaluate("""el => ({
                id: el.id, name: el.name, type: el.type,
                placeholder: el.placeholder, value: el.value,
                readOnly: el.readOnly, class: el.className.slice(0,80),
                w: Math.round(el.getBoundingClientRect().width),
                h: Math.round(el.getBoundingClientRect().height)
            })""", inp.element_handle())
            log.info("  input[%d]: %s", idx, info)
            if idx < 2 and not info.get("readOnly") and info.get("type") not in ("radio", "checkbox", "hidden"):
                log.info("  -> Attempting to fill input[%d]", idx)
                inp.click()
                page.wait_for_timeout(200)
                inp.press("Control+a")
                inp.type(date_str, delay=50)
                page.wait_for_timeout(300)
                log.info("  -> After type, value=%r", inp.input_value())
                shot(page, f"D_after_fill_input{idx}")

        # --- Look for Apply button ---
        log.info("=== Looking for Apply button ===")
        apply_candidates = page.evaluate("""() =>
            Array.from(document.querySelectorAll('*'))
                .filter(el => {
                    const t = (el.innerText || '').trim();
                    const r = el.getBoundingClientRect();
                    return (t === 'Apply' || t === 'APPLY') && r.width > 0 && r.height > 0;
                })
                .map(el => ({
                    tag: el.tagName, id: el.id,
                    class: el.className.slice(0,100),
                    outerHTML: el.outerHTML.slice(0, 200)
                }))
        """)
        log.info("Apply candidates: %d", len(apply_candidates))
        for c in apply_candidates:
            log.info("  %s", c)

        shot(page, "E_final_state")
        dump(page, "E_final_state")

        log.info("=== DONE — files in %s ===", OUT)
        input("\nPress Enter to close...")
        ctx.close()

if __name__ == "__main__":
    main()
