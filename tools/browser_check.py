"""Live browser verification (dev-only tool; needs chromium + playwright).

Run:  APP_BASE_URL=https://foray.example.com python3 tools/browser_check.py
      python3 tools/browser_check.py [base_url]

The target origin comes from APP_BASE_URL (or the first argument), so the same
harness works against a local dev server, a remote host or a split deployment.
"""

from __future__ import annotations

import asyncio
import os
import sys

from playwright.async_api import async_playwright

LOCAL_HOST = os.environ.get("APP_HOST", "127.0.0.1")
LOCAL_PORT = os.environ.get("PORT", "7860")
BASE = (
    sys.argv[1]
    if len(sys.argv) > 1
    else os.environ.get("APP_BASE_URL") or f"http://{LOCAL_HOST}:{LOCAL_PORT}"
)
SHOTS = "/tmp/shots"
problems: list[str] = []
errors: list[str] = []


async def main() -> int:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--no-sandbox"])
        page = await browser.new_page(viewport={"width": 1280, "height": 950})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on(
            "console",
            lambda m: errors.append(f"console.error: {m.text}") if m.type == "error" else None,
        )
        page.on(
            "requestfailed",
            lambda r: errors.append(f"requestfailed: {r.url} ({r.failure})"),
        )
        responses: list[str] = []

        async def note_response(response):
            if response.status >= 400:
                responses.append(f"{response.status} {response.url}")

        page.on("response", note_response)

        # ---- gate + sign-in -------------------------------------------------
        await page.goto(BASE + "/", wait_until="domcontentloaded")
        await page.wait_for_selector("#signin-form", timeout=30000)
        print(f"gate -> {page.url}")
        if page.url.rstrip("/") != BASE.rstrip("/"):
            problems.append("the front door did not render the sign-in card at /")

        hint = await page.inner_text(".demo__creds")
        print(f"demo hint: {hint!r}")
        if "Demo: cenius@cenius.ai / cenius" not in hint:
            problems.append("demo credential hint missing")

        await page.screenshot(path=f"{SHOTS}/00-login.png", full_page=True)

        # password toggle
        await page.fill("input[name=password]", "cenius")
        await page.click("#toggle-password")
        ptype = await page.get_attribute("input[name=password]", "type")
        await page.click("#toggle-password")
        ptype_back = await page.get_attribute("input[name=password]", "type")
        print(f"password toggle: {ptype} -> {ptype_back}")
        if ptype != "text" or ptype_back != "password":
            problems.append("show/hide password toggle did not switch the input type")

        # wrong password keeps the visitor on the card with one message
        await page.fill("input[name=username]", "cenius@cenius.ai")
        await page.fill("input[name=password]", "wrong-password")
        await page.click("#signin-submit")
        await page.wait_for_selector(".form__error", timeout=20000)
        error_text = await page.inner_text(".form__error")
        print(f"bad sign-in message: {error_text!r}")
        if "Username or password is incorrect" not in error_text:
            problems.append("bad sign-in did not show the non-enumerating message")

        # ---- sign in with the demo account ----------------------------------
        await page.fill("input[name=password]", "cenius")
        await page.click("#signin-submit")
        await page.wait_for_selector("#app-tabs", timeout=60000)
        await page.wait_for_selector("#save-find", timeout=60000)
        await page.wait_for_timeout(2500)
        print(f"signed in -> {page.url}")
        if page.url.rstrip("/") != BASE.rstrip("/"):
            problems.append(f"sign-in did not land on the app root: {page.url}")

        body = (await page.inner_text("body")).lower()
        for needle in (
            "mushroom foray spore print matcher",
            "signed in as",
            "closest swatch class",
            "lookalike warning score",
            "heuristic only",
            "save find to foray",
        ):
            if needle not in body:
                problems.append(f"matcher tab missing {needle!r}")
        await page.screenshot(path=f"{SHOTS}/01-matcher.png", full_page=True)

        # the reference match card is populated on first paint
        match_text = await page.inner_text("#match-card")
        print(f"match card: {' '.join(match_text.split())[:110]}")
        if "confidence" not in match_text:
            problems.append("match card did not render the reference match")

        # ---- sliders recompute live ----------------------------------------
        before = " ".join((await page.inner_text("#score-card")).split())
        await page.locator("#cap-slider input[type=range]").fill("260")
        await page.wait_for_timeout(1200)
        await page.locator("#gill-slider input[type=range]").fill("1")
        await page.wait_for_timeout(2500)
        after_text = await page.inner_text("#score-card")
        print(f"score card after sliders: {' '.join(after_text.split())[:110]}")
        if "High risk" not in after_text:
            problems.append("moving both sliders did not update the score card to high risk")
        if before == " ".join(after_text.split()):
            problems.append("score card did not change when the sliders moved")

        # ---- save a find ----------------------------------------------------
        await page.fill("#habitat-note textarea", "Browser check pine duff")
        await page.click("#save-find")
        await page.wait_for_timeout(4000)
        status = await page.inner_text("#save-status")
        print(f"save status: {' '.join(status.split())[:140]}")
        if "Saved to" not in status:
            problems.append("save did not confirm")
        await page.screenshot(path=f"{SHOTS}/02-matcher-saved.png", full_page=True)

        # ---- foray tab ------------------------------------------------------
        await page.get_by_role("tab", name="Foray").click()
        await page.wait_for_timeout(2500)
        foray = await page.inner_text("body")
        if "Browser check pine duff" not in foray:
            problems.append("the saved find is not listed on the Foray tab")
        rail = await page.inner_text("#session-rail")
        print(f"session rail: {' '.join(rail.split())[:120]}")
        if "finds" not in rail:
            problems.append("session rail does not show finding counts")

        before_switch = await page.inner_text("#findings-table")
        radio = page.locator("#session-rail label").last
        await radio.click()
        await page.wait_for_timeout(2500)
        after_switch = await page.inner_text("#findings-table")
        print(f"rail switch changed the table: {before_switch.strip() != after_switch.strip()}")
        if before_switch.strip() == after_switch.strip():
            problems.append("clicking another session in the rail did not change the findings table")
        await page.screenshot(path=f"{SHOTS}/03b-foray-other-session.png", full_page=True)
        await page.screenshot(path=f"{SHOTS}/03-foray.png", full_page=True)

        # ---- dashboard ------------------------------------------------------
        await page.get_by_role("tab", name="Dashboard").click()
        await page.wait_for_timeout(3500)
        marks = {}
        for chart in ("swatch-chart", "confidence-chart", "band-chart", "scatter-chart"):
            marks[chart] = await page.eval_on_selector_all(
                f"#{chart} canvas, #{chart} svg, #{chart} [class*=mark]", "els => els.length"
            )
        print(f"chart marks: {marks}")
        empty = {
            name: count for name, count in marks.items() if count == 0
        }
        if empty:
            problems.append(f"charts rendered nothing: {empty}")
        kpis = (await page.inner_text("#kpi-strip")).lower()
        print(f"kpis: {' '.join(kpis.split())[:130]}")
        if "finds" not in kpis:
            problems.append("KPI strip missing")
        await page.screenshot(path=f"{SHOTS}/04-dashboard.png", full_page=True)

        # ---- widths ---------------------------------------------------------
        for width in (1280, 390, 320):
            await page.set_viewport_size({"width": width, "height": 900})
            await page.wait_for_timeout(1000)
            layout = await page.evaluate(
                """() => {
                  const doc = document.documentElement;
                  const small = [];
                  const visible = el => {
                    if (el.disabled) return false;
                    const r = el.getBoundingClientRect();
                    if (r.width < 1 || r.height < 1) return false;
                    const style = getComputedStyle(el);
                    if (style.visibility === 'hidden' || style.display === 'none') return false;
                    if (style.opacity === '0') return false;
                    if (el.closest('.visually-hidden, [aria-hidden="true"]')) return false;
                    return el.checkVisibility ? el.checkVisibility({ checkOpacity: false, checkVisibilityCSS: true }) : true;
                  };
                  document.querySelectorAll('button, a.btn, input[type=text], input[type=password], input[type=submit], [role=button]').forEach(el => {
                    if (!visible(el)) return;
                    const r = el.getBoundingClientRect();
                    if (r.height < 30 || r.width < 30) {
                      small.push((el.id || el.className || el.tagName) + ' ' + Math.round(r.width) + 'x' + Math.round(r.height));
                    }
                  });
                  const wide = [];
                  document.querySelectorAll('body *').forEach(el => {
                    const r = el.getBoundingClientRect();
                    if (r.right > window.innerWidth + 1 && r.width > 30) {
                      wide.push((el.id || el.tagName + '.' + (el.className || '').toString().slice(0, 24)) + ' right=' + Math.round(r.right) + ' w=' + Math.round(r.width));
                    }
                  });
                  return {
                    hscroll: doc.scrollWidth > window.innerWidth + 1,
                    scrollWidth: doc.scrollWidth,
                    width: window.innerWidth,
                    small: small.slice(0, 6),
                    wide: wide.slice(0, 6),
                  };
                }"""
            )
            print(f"width {width}: {layout}")
            if layout["hscroll"]:
                problems.append(f"horizontal scroll at {width}px ({layout['scrollWidth']})")
            if layout["small"]:
                problems.append(f"sub-24px targets at {width}px: {layout['small']}")
            await page.screenshot(path=f"{SHOTS}/05-width-{width}.png", full_page=True)

        await page.set_viewport_size({"width": 1280, "height": 950})
        await page.reload(wait_until="domcontentloaded")
        await page.wait_for_selector("#app-tabs", timeout=60000)
        await page.wait_for_timeout(2500)
        await page.get_by_role("tab", name="Foray").click()
        await page.wait_for_timeout(2500)
        reloaded = await page.inner_text("body")
        if "Browser check pine duff" not in reloaded:
            problems.append("the saved find did not survive a reload")

        font = await page.evaluate("() => getComputedStyle(document.body).fontFamily")
        print(f"body font: {font}")
        if "Lexend" not in font:
            problems.append(f"body font is not Lexend: {font}")
        rules = await page.evaluate(
            """() => [...document.styleSheets].reduce((n, s) => {
                 try { return n + s.cssRules.length } catch { return n } }, 0)"""
        )
        print(f"css rules loaded: {rules}")
        if rules < 50:
            problems.append(f"too few CSS rules applied ({rules})")

        await browser.close()

    expected = ("401 " + BASE + "/login",)
    unexpected_responses = [line for line in dict.fromkeys(responses) if not line.startswith(expected)]
    if unexpected_responses:
        print("UNEXPECTED HTTP >= 400:")
        for line in unexpected_responses:
            print("  ", line)
        problems.extend(unexpected_responses[:8])
    else:
        print("no unexpected 4xx/5xx responses (the deliberate bad sign-in is expected)")

    ignorable = (
        "status of 401 (Unauthorized)",
        "net::ERR_ABORTED",
    )
    real_errors = [err for err in dict.fromkeys(errors) if not any(token in err for token in ignorable)]
    if real_errors:
        print("BROWSER ERRORS:")
        for err in real_errors:
            print("  ", err[:180])
        problems.extend(real_errors[:8])
    else:
        print("no browser console/page errors")

    print("\nPROBLEMS:" if problems else "\nALL BROWSER CHECKS PASSED")
    for problem in problems:
        print(" -", problem)
    return 1 if problems else 0


raise SystemExit(asyncio.run(main()))
