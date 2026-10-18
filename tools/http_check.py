"""HTTP-level verification of the running app (no browser available in this sandbox).

Checks: the gate, the sign-in card, session establishment, every static asset the
pages reference, absence of remote assets, and the WCAG contrast of the palette
pairs the design commits to.
"""

from __future__ import annotations

import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

LOCAL_HOST = os.environ.get("APP_HOST", "127.0.0.1")
LOCAL_PORT = os.environ.get("PORT", "7860")
BASE = (
    sys.argv[1]
    if len(sys.argv) > 1
    else os.environ.get("APP_BASE_URL") or f"http://{LOCAL_HOST}:{LOCAL_PORT}"
)
problems: list[str] = []


def opener():
    import http.cookiejar

    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar)), jar


def fetch(op, path, data=None, follow=True):
    url = BASE + path
    request = urllib.request.Request(url, data=data)
    if data is not None:
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        response = op.open(request)
        body = response.read()
        return response.status, response.headers, body, response.geturl()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read(), url


def main() -> int:
    op, jar = opener()

    status, headers, body, url = fetch(op, "/")
    ctype = headers.get("content-type", "") if headers else ""
    print(f"GET /            -> {status} {ctype} ({len(body)} bytes)")
    if status != 200 or not ctype.startswith("text/html"):
        problems.append(f"anonymous GET / is not an HTML page ({status} {ctype})")
    if b'name="password"' not in body:
        problems.append("anonymous GET / does not render the sign-in card")

    status, headers, body, _ = fetch(op, "/login")
    html = body.decode("utf-8", "replace")
    print(f"GET /login       -> {status} ({len(html)} chars)")
    if "Demo: cenius@cenius.ai / cenius" not in html:
        problems.append("demo hint missing from the sign-in card")
    for needle in ('name="username"', 'name="password"', 'type="submit"'):
        if needle not in html:
            problems.append(f"sign-in card missing {needle!r}")

    token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    payload = urllib.parse.urlencode(
        {"username": "cenius@cenius.ai", "password": "cenius", "mode": "signin", "csrf_token": token}
    ).encode()
    status, headers, body, url = fetch(op, "/login", data=payload)
    print(f"POST /login      -> {status} {url}")
    if "/login" in url:
        problems.append("sign-in did not leave the sign-in page")
    cookie_names = [cookie.name for cookie in jar]
    if "foray_session" not in cookie_names:
        problems.append(f"no session cookie issued: {cookie_names}")

    for alias in ("/index.html", "/app", "/home"):
        status, headers, body, _ = fetch(op, alias)
        print(f"GET {alias:13s}-> {status}")
        if status not in (200, 303):
            problems.append(f"alias {alias} answered {status}")

    status, headers, body, url = fetch(op, "/")
    shell = body.decode("utf-8", "replace")
    print(f"GET / (signed in)-> {status} ({len(shell)} chars)")
    if status != 200 or "gradio" not in shell.lower():
        problems.append("the Gradio shell did not render for a signed-in user")
    if "X-Frame-Options" not in headers:
        problems.append("missing security headers")

    # every same-origin asset the pages reference must resolve
    assets = set(re.findall(r'(?:src|href)="(\.?/[^"#?]+)"', shell))
    assets.update(re.findall(r'(?:src|href)="(\.?/[^"#?]+)"', html))
    for extra in (
        "/ui-static/app.css",
        "/ui-static/app.js",
        "/ui-static/login.js",
        "/ui-static/favicon.svg",
        "/ui-static/fonts/lexend.woff2",
    ):
        assets.add(extra)
    for asset in sorted(assets):
        path = asset.replace("./", "/", 1) if asset.startswith("./") else asset
        status, headers, body, _ = fetch(op, path)
        ctype = headers.get("content-type", "") if headers else ""
        print(f"  asset {path:46s} -> {status} {ctype}")
        if status >= 400:
            problems.append(f"asset {path} returned {status}")

    # no remote assets anywhere in the served HTML or the stylesheet
    status, _, css_body, _ = fetch(op, "/ui-static/app.css")
    css = css_body.decode("utf-8", "replace")
    if headers and not css.startswith("@font-face"):
        problems.append("the stylesheet does not start with the local @font-face rule")
    # only *fetched assets* matter: src/href/url() pointing at another origin
    fetched = re.findall(r'(?:src|href)="(https?://[^"]+)"', shell)
    fetched += re.findall(r"url\(\s*['\"]?(https?://[^)'\"]+)", css)
    for match in fetched:
        if any(host in match for host in ("127.0.0.1", "localhost")):
            continue
        problems.append(f"remote asset referenced: {match[:80]}")

    # palette contrast (WCAG AA)
    def lum(hex_colour: str) -> float:
        value = hex_colour.lstrip("#")
        channels = [int(value[i : i + 2], 16) / 255 for i in (0, 2, 4)]
        linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    def ratio(a: str, b: str) -> float:
        high, low = sorted((lum(a), lum(b)), reverse=True)
        return (high + 0.05) / (low + 0.05)

    pairs = [
        ("body text", "#0b1512", "#f5fcfa", 4.5),
        ("muted text", "#5a6663", "#fdffff", 4.5),
        ("on-accent", "#111111", "#3fbf86", 4.5),
        ("accent ink", "#0f5c3f", "#e6f6ee", 4.5),
        ("low pill", "#0f5c3f", "#e6f6ee", 4.5),
        ("moderate pill", "#7a4a00", "#fbeedc", 4.5),
        ("high pill", "#9b2320", "#fbe7e6", 4.5),
        ("chart-1 on card", "#1f7f5b", "#fdffff", 3.0),
        ("chart-2 on card", "#b26b00", "#fdffff", 3.0),
        ("chart-3 on card", "#c9302d", "#fdffff", 3.0),
        ("input border", "#869691", "#fdffff", 3.0),
        ("focus ring", "#2f9a6a", "#fdffff", 3.0),
    ]
    for label, fg, bg, target in pairs:
        value = ratio(fg, bg)
        flag = "ok  " if value >= target else "FAIL"
        print(f"  contrast {label:20s} {fg} on {bg} = {value:.2f} ({target}) {flag}")
        if value < target:
            problems.append(f"contrast {label} {value:.2f} < {target}")

    print("\nPROBLEMS:" if problems else "\nALL HTTP/ASSET/CONTRAST CHECKS PASSED")
    for problem in problems:
        print(" -", problem)
    return 1 if problems else 0


raise SystemExit(main())
