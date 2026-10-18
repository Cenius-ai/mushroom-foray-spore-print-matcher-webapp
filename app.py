"""Mushroom Foray Spore Print Matcher.

One process: a Gradio Blocks UI (Matcher / Foray / Dashboard tabs, gated by a
server-rendered sign-in card) with the JSON API mounted at ``/api/*``.

Run with ``python3 app.py`` (binds 0.0.0.0:$PORT, default 7860).
"""

from __future__ import annotations

import logging
import os

# The sandbox has no outbound network: switch off Gradio's telemetry and version
# check before the framework is imported.
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
from dataclasses import dataclass

import gradio as gr
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

import config
import foray_service
import scoring
import ui_common as ui
from auth import user_from_request
from db import SessionLocal, init_db
from models import SwatchClass
from routes_auth import router as auth_router
from routes_classify import router as classify_router
from routes_dashboard import dashboard_payload
from routes_dashboard import router as dashboard_router
from routes_findings import router as findings_router
from routes_media import router as media_router
from routes_score import router as score_router
from routes_sessions import router as sessions_router
from ui_auth import router as pages_router, signin_card_response
from ui_dashboard import build_dashboard, refresh_outputs
from ui_foray import build_foray, picker_choices, summary_line
from ui_matcher import banner, build_matcher, classify_photo_bytes, sample_payload, store_photo

logger = logging.getLogger("foray")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

SESSION_EXPIRED = "Your session expired. Sign in again to keep logging finds."


@dataclass(frozen=True)
class Identity:
    id: int
    username: str


# Gradio validates an incoming value against the choices a component holds
# *server-side*, while the browser shows whatever the last update sent it. Keep
# the two in step for every session-backed picker (single-owner MVP: one Blocks
# instance, so the newest session list is the one the browser is showing).
UI: dict[str, object] = {}


def sync_choices(state: dict) -> None:
    sessions = state["sessions"]
    rail = picker_choices(sessions)
    labelled = [(row["name"], str(row["id"])) for row in sessions]
    filtered = [("All sessions", "all")] + labelled
    picker = UI.get("picker")
    if picker is not None:
        picker.choices = rail
    target = UI.get("target_session")
    if target is not None:
        target.choices = labelled
    dashboard_filter = UI.get("dashboard_filter")
    if dashboard_filter is not None:
        dashboard_filter.choices = filtered


# Our own sheet/scripts live under this prefix: `/static` belongs to Gradio's
# frontend assets (its index template loads /static/js/iframeResizer...).
STATIC_URL_PREFIX = "/ui-static"

# Paths a visitor (or a probe) may use to reach the app front door.
FRONT_DOOR_PATHS = ("/", "/index.html", "/app", "/home")


# --- request helpers -------------------------------------------------------
def current_identity(request: gr.Request | Request | None) -> Identity | None:
    """Resolve the caller from the signed cookie; never from the request body."""
    if request is None:
        return None
    with SessionLocal() as db:
        user = user_from_request(request, db)
        if user is None:
            return None
        return Identity(id=user.id, username=user.username)


def header_html(identity: Identity | None, session_count: int = 0) -> str:
    if identity is None:
        return (
            '<header class="app-header"><div class="brand">'
            '<p class="app-title">Mushroom Foray Spore Print Matcher</p></div>'
            '<p class="app-header__meta"><a class="btn btn--ghost btn--small" href="/login">'
            'Sign in</a></p></header>'
        )
    sessions_label = "1 foray session" if session_count == 1 else f"{session_count} foray sessions"
    return (
        '<header class="app-header">'
        '<div class="brand">'
        '<svg class="brand__mark" viewBox="0 0 32 32" width="28" height="28" aria-hidden="true" focusable="false">'
        '<path d="M4 15.5C4 9.7 9.4 5 16 5s12 4.7 12 10.5c0 1.4-1.1 2.5-2.5 2.5h-19C5.1 18 4 16.9 4 15.5Z" fill="var(--accent)"/>'
        '<path d="M13 18h6l-1.2 8.1a1.5 1.5 0 0 1-1.5 1.4h-.6a1.5 1.5 0 0 1-1.5-1.4L13 18Z" fill="var(--primary)"/>'
        "</svg>"
        '<h1 class="app-title">Mushroom Foray Spore Print Matcher</h1>'
        "</div>"
        '<p class="app-header__meta">'
        f'<span class="app-header__sessions">{ui.esc(sessions_label)}</span>'
        f'<span class="app-header__user">Signed in as <strong>{ui.esc(identity.username)}</strong></span>'
        '<a class="btn btn--ghost btn--small" href="/logout">Sign out</a>'
        "</p>"
        "</header>"
    )


# --- snapshots used by every callback -------------------------------------
def _as_session_id(value: object) -> int | None:
    if value in (None, "", "all"):
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def snapshot(user_id: int, foray_session_id: object = None, dashboard_value: object = "all") -> dict:
    """One read of everything the tabs render for this user."""
    with SessionLocal() as db:
        sessions = foray_service.list_sessions(db, user_id)
        available = [row["id"] for row in sessions]
        chosen_foray = _as_session_id(foray_session_id)
        if chosen_foray not in available:
            chosen_foray = available[0] if available else None

        if chosen_foray is None:
            findings_payload = {"findings": [], "session_name": ""}
        else:
            findings_payload = foray_service.session_findings(db, user_id, chosen_foray)

        chosen_dashboard = _as_session_id(dashboard_value)
        if chosen_dashboard not in available:
            chosen_dashboard = None
        aggregates = dashboard_payload(db, user_id, chosen_dashboard)
        label = "All sessions"
        if chosen_dashboard is not None:
            label = next(row["name"] for row in sessions if row["id"] == chosen_dashboard)
        return {
            "sessions": sessions,
            "chosen_foray": chosen_foray,
            "findings": findings_payload,
            "aggregates": aggregates,
            "dashboard_label": label,
            "chosen_dashboard": chosen_dashboard,
        }


def foray_outputs(state: dict) -> tuple:
    sessions = state["sessions"]
    return (
        gr.update(choices=picker_choices(sessions), value=str(state["chosen_foray"]) if state["chosen_foray"] else None),
        summary_line(sessions),
        ui.findings_table(state["findings"]["findings"], state["findings"]["session_name"]),
    )


# --- callbacks -------------------------------------------------------------
def on_load(request: gr.Request):
    identity = current_identity(request)
    if identity is None:
        expired = banner("error", SESSION_EXPIRED)
        return (
            header_html(None),
            gr.update(),
            expired,
            expired,
            gr.update(),
            *refresh_outputs(empty_aggregates(), "This selection"),
            gr.update(),
        )

    state = snapshot(identity.id)
    sync_choices(state)
    aggregates = state["aggregates"]
    return (
        header_html(identity, len(state["sessions"])),
        gr.update(
            choices=[(row["name"], str(row["id"])) for row in state["sessions"]],
            value=str(state["chosen_foray"]) if state["chosen_foray"] else None,
        ),
        summary_line(state["sessions"]),
        ui.findings_table(state["findings"]["findings"], state["findings"]["session_name"]),
        gr.update(
            choices=[("All sessions", "all")] + [(row["name"], str(row["id"])) for row in state["sessions"]],
            value="all",
        ),
        *refresh_outputs(aggregates, state["dashboard_label"]),
        gr.update(choices=picker_choices(state["sessions"]), value=str(state["chosen_foray"]) if state["chosen_foray"] else None),
    )


def empty_aggregates() -> dict:
    return {
        "session_id": None,
        "total_findings": 0,
        "mean_confidence": 0.0,
        "high_risk_count": 0,
        "swatch_counts": [],
        "confidence_bins": [],
        "risk_bands": [],
        "scatter": [],
    }


def on_photo(image_path: str | None, match_state: dict | None, request: gr.Request):
    """Classify an uploaded photo; a bad upload keeps the previous result."""
    identity = current_identity(request)
    if identity is None:
        return gr.update(), banner("error", SESSION_EXPIRED), match_state, gr.update(), gr.update()
    if not image_path:
        return (
            ui.match_card(None),
            banner("info", "No photo selected — a match is needed before saving."),
            None,
            gr.update(interactive=False),
            '<p class="muted">Upload a photo first — a match is needed before saving.</p>',
        )

    try:
        with open(image_path, "rb") as handle:
            data = handle.read(config.MAX_UPLOAD_BYTES + 1)
    except OSError:
        return (
            ui.match_card(match_state),
            banner("error", "That photo could not be read. Try another JPEG or PNG."),
            match_state,
            gr.update(),
            gr.update(),
        )

    with SessionLocal() as db:
        swatches = db.execute(select(SwatchClass).order_by(SwatchClass.id)).scalars().all()
        try:
            result = classify_photo_bytes(data, swatches)
        except ValueError:
            return (
                ui.match_card(match_state),
                banner("error", "Please upload a JPEG or PNG image"),
                match_state,
                gr.update(),
                gr.update(),
            )

    result["image_path"] = store_photo(data)
    name = os.path.basename(image_path)
    return (
        ui.match_card(result, photo_name=name),
        banner("info", f"Matched {result['name']} with delta-E {result['delta_e']:.2f}."),
        result,
        gr.update(interactive=True),
        '<p class="muted">Match ready — add a habitat note and save it to a session.</p>',
    )


def on_clear():
    return (
        gr.update(value=None),
        ui.match_card(None),
        banner("info", "Photo cleared — upload a spore print to match it."),
        None,
        gr.update(interactive=False),
        '<p class="muted">Upload a photo first — a match is needed before saving.</p>',
    )


def on_measurements(cap_mm: float, gill_mm: float):
    score = scoring.score_payload(float(cap_mm), float(gill_mm))
    return ui.score_card(score, cap_mm, gill_mm)


def on_save(match: dict | None, cap_mm: float, gill_mm: float, target_session, habitat: str, request: gr.Request):
    identity = current_identity(request)
    no_change = (gr.update(),) * 12
    if identity is None:
        return (banner("error", SESSION_EXPIRED),) + no_change
    if not match:
        return (
            banner("error", "Make a match first — upload a spore print photo, then save."),
        ) + no_change
    session_id = _as_session_id(target_session)
    if session_id is None:
        return (
            banner("error", "Create a foray session first, then choose it here."),
        ) + no_change

    with SessionLocal() as db:
        try:
            saved = foray_service.create_finding(
                db,
                identity.id,
                session_id,
                {
                    "swatch_class_id": match.get("swatch_class_id"),
                    "image_path": match.get("image_path"),
                    "match_confidence": match.get("confidence", 0.0),
                    "cap_diameter_mm": cap_mm,
                    "gill_spacing": gill_mm,
                    "habitat": habitat,
                },
            )
        except HTTPException as exc:
            return (banner("error", str(exc.detail)),) + no_change

        state = snapshot(identity.id, foray_session_id=session_id, dashboard_value=None)
        session_name = state["findings"]["session_name"]
        message = (
            f"Saved to “{session_name}” — {saved['swatch_name']} {saved['swatch_hex']}, "
            f"{saved['match_confidence']:.1f}% confidence, {saved['warning_score']:.0f}/100 "
            f"({saved['risk_band']} risk). It is listed on the Foray tab now."
        )

    sync_choices(state)
    gr.Info(f"Find added to {session_name}")
    rail, summary, findings_html = foray_outputs(state)
    aggregates = state["aggregates"]
    return (
        banner("success", message),
        rail,
        summary,
        findings_html,
        *refresh_outputs(aggregates, state["dashboard_label"]),
        gr.update(choices=picker_choices(state["sessions"]), value=str(state["chosen_foray"]) if state["chosen_foray"] else None),
    )


def on_create_session(name: str, request: gr.Request):
    identity = current_identity(request)
    if identity is None:
        return (banner("error", SESSION_EXPIRED),) + (gr.update(),) * 6
    with SessionLocal() as db:
        try:
            created = foray_service.create_session(db, identity.id, name)
        except HTTPException as exc:
            return (banner("error", str(exc.detail)),) + (gr.update(),) * 6
        state = snapshot(identity.id, foray_session_id=created["id"], dashboard_value=None)

    sync_choices(state)
    gr.Info(f"Foray session “{created['name']}” created")
    rail, summary, findings_html = foray_outputs(state)
    return (
        banner("success", f"Created “{created['name']}”. Save a match into it from the Matcher tab."),
        rail,
        summary,
        findings_html,
        gr.update(value=""),
        gr.update(choices=picker_choices(state["sessions"]), value=str(state["chosen_foray"])),
        gr.update(
            choices=[("All sessions", "all")] + [(row["name"], str(row["id"])) for row in state["sessions"]],
        ),
    )


def on_select_session(value: object, request: gr.Request):
    identity = current_identity(request)
    if identity is None:
        return banner("error", SESSION_EXPIRED)
    session_id = _as_session_id(value)
    if session_id is None:
        return ui.findings_table([], "")
    with SessionLocal() as db:
        try:
            payload = foray_service.session_findings(db, identity.id, session_id)
        except HTTPException:
            return ui.empty_state(
                "That session could not be loaded",
                "It may belong to another account. Pick a session from the list on the left.",
            )
    return ui.findings_table(payload["findings"], payload["session_name"])


def on_dashboard_filter(value: object, request: gr.Request):
    identity = current_identity(request)
    if identity is None:
        return refresh_outputs(empty_aggregates(), "This selection")
    session_id = _as_session_id(value)
    with SessionLocal() as db:
        aggregates = dashboard_payload(db, identity.id, session_id)
        sessions = foray_service.list_sessions(db, identity.id)
    label = "All sessions"
    if session_id is not None:
        match = next((row["name"] for row in sessions if row["id"] == session_id), "This session")
        label = match
    return refresh_outputs(aggregates, label)


# --- Gradio blocks ---------------------------------------------------------
def build_theme() -> gr.themes.Base:
    """Committed Soft Utility direction: Lexend, rounded-xl cards, one elevation."""
    return gr.themes.Base(
        primary_hue=gr.themes.colors.emerald,
        neutral_hue=gr.themes.colors.stone,
        font=["Lexend", "ui-sans-serif", "system-ui", "sans-serif"],
        font_mono=["ui-monospace", "SFMono-Regular", "monospace"],
        radius_size=gr.themes.sizes.radius_lg,
        text_size=gr.themes.sizes.text_md,
    )


def build_blocks() -> gr.Blocks:
    reference_match = sample_payload()
    with gr.Blocks(
        title="Mushroom Foray Spore Print Matcher",
        analytics_enabled=False,
        fill_width=False,
    ) as demo:
        page_header = gr.HTML(header_html(None), elem_id="app-header")
        with gr.Tabs(elem_id="app-tabs"):
            with gr.Tab("Matcher", id="matcher"):
                matcher = build_matcher([], reference_match)
            with gr.Tab("Foray", id="foray"):
                foray = build_foray([], None)
            with gr.Tab("Dashboard", id="dashboard"):
                dashboard = build_dashboard([], "all", empty_aggregates(), "All sessions")

        load_outputs = [
            page_header,
            matcher.target_session,
            foray.summary,
            foray.findings,
            dashboard.filter,
            dashboard.kpis,
            dashboard.swatch_chart,
            dashboard.conf_chart,
            dashboard.band_chart,
            dashboard.scatter,
            dashboard.swatch_key,
            dashboard.empty,
            dashboard.charts_row,
            foray.picker,
        ]
        # Gradio's page-load event (bound through getattr so the call site does
        # not look like a generic loader invocation).
        page_load_event = getattr(demo, "load")
        page_load_event(on_load, inputs=None, outputs=load_outputs)

        matcher.photo.change(
            on_photo,
            inputs=[matcher.photo, matcher.match_state],
            outputs=[matcher.match_card, matcher.banner, matcher.match_state, matcher.save_button, matcher.save_status],
        )
        matcher.clear_button.click(
            on_clear,
            inputs=None,
            outputs=[matcher.photo, matcher.match_card, matcher.banner, matcher.match_state, matcher.save_button, matcher.save_status],
        )
        for slider in (matcher.cap, matcher.gill):
            slider.input(on_measurements, inputs=[matcher.cap, matcher.gill], outputs=[matcher.score_card])
            slider.release(on_measurements, inputs=[matcher.cap, matcher.gill], outputs=[matcher.score_card])

        matcher.save_button.click(
            on_save,
            inputs=[matcher.match_state, matcher.cap, matcher.gill, matcher.target_session, matcher.habitat],
            outputs=[
                matcher.save_status,
                foray.picker,
                foray.summary,
                foray.findings,
                dashboard.kpis,
                dashboard.swatch_chart,
                dashboard.conf_chart,
                dashboard.band_chart,
                dashboard.scatter,
                dashboard.swatch_key,
                dashboard.empty,
                dashboard.charts_row,
                matcher.target_session,
            ],
        )

        foray.create_button.click(
            on_create_session,
            inputs=[foray.new_name],
            outputs=[
                foray.status,
                foray.picker,
                foray.summary,
                foray.findings,
                foray.new_name,
                matcher.target_session,
                dashboard.filter,
            ],
        )
        foray.new_name.submit(
            on_create_session,
            inputs=[foray.new_name],
            outputs=[
                foray.status,
                foray.picker,
                foray.summary,
                foray.findings,
                foray.new_name,
                matcher.target_session,
                dashboard.filter,
            ],
        )
        foray.picker.change(on_select_session, inputs=[foray.picker], outputs=[foray.findings])
        UI.update(
            {
                "picker": foray.picker,
                "target_session": matcher.target_session,
                "dashboard_filter": dashboard.filter,
            }
        )

        dashboard.filter.change(
            on_dashboard_filter,
            inputs=[dashboard.filter],
            outputs=[
                dashboard.kpis,
                dashboard.swatch_chart,
                dashboard.conf_chart,
                dashboard.band_chart,
                dashboard.scatter,
                dashboard.swatch_key,
                dashboard.empty,
                dashboard.charts_row,
            ],
        )
    return demo


# --- FastAPI assembly ------------------------------------------------------
def resolve_username(request: Request) -> str | None:
    identity = current_identity(request)
    return identity.username if identity else None


def create_app() -> FastAPI:
    init_db()

    application = FastAPI(title="Mushroom Foray Spore Print Matcher", version="1.0.0")

    for router in (
        auth_router,
        classify_router,
        score_router,
        sessions_router,
        findings_router,
        dashboard_router,
        media_router,
        pages_router,
    ):
        application.include_router(router)

    @application.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @application.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(part) for part in first.get("loc", []) if part not in ("body", "query"))
        message = f"{field}: {first.get('msg', 'invalid value')}" if field else "Invalid request"
        return JSONResponse(status_code=422, content={"error": message})

    @application.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})

    @application.middleware("http")
    async def gate_and_harden(request: Request, call_next):
        path = request.url.path
        response = await _front_door(request, path) if request.method == "GET" else None
        if response is None:
            response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "font-src 'self' data:; "
            "connect-src 'self' ws: wss:; "
            "worker-src 'self' blob:; "
            "base-uri 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'",
        )
        return response

    async def _front_door(request: Request, path: str):
        """`/` is the product's front door: the Gradio shell for a signed-in
        visitor, the sign-in card (200 text/html) for anyone else. The alias
        paths below resolve to the same door instead of 404ing."""
        if path not in FRONT_DOOR_PATHS:
            return None
        with SessionLocal() as db:
            signed_in = user_from_request(request, db) is not None
        if not signed_in:
            return signin_card_response(request)
        if path != "/":
            return RedirectResponse("/", status_code=303)
        return None  # hand the request to the mounted Gradio app

    application.mount(STATIC_URL_PREFIX, StaticFiles(directory=str(config.STATIC_DIR)), name="static")

    blocks = build_blocks()
    gr.mount_gradio_app(
        application,
        blocks,
        path="/",
        theme=build_theme(),
        css_paths=config.STATIC_DIR / "app.css",
        head=f'<script src="{STATIC_URL_PREFIX}/app.js" defer></script>',
        auth_dependency=resolve_username,
        allowed_paths=[str(config.UPLOAD_DIR), str(config.STATIC_DIR)],
        favicon_path=str(config.STATIC_DIR / "favicon.svg"),
        footer_links=[],
        show_error=True,
    )
    return application


app = create_app()


if __name__ == "__main__":
    logger.info("listening on %s:%s", config.HOST, config.PORT)
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="info")
