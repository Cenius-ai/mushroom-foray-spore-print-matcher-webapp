"""Matcher tab: photo upload, live score and the save-to-foray panel."""

from __future__ import annotations

from dataclasses import dataclass

import gradio as gr

import config
import color as colour
import scoring
import ui_common as ui


@dataclass
class MatcherTab:
    photo: gr.Image
    banner: gr.HTML
    match_card: gr.HTML
    cap: gr.Slider
    gill: gr.Slider
    score_card: gr.HTML
    match_state: gr.State
    target_session: gr.Dropdown
    habitat: gr.Textbox
    save_button: gr.Button
    save_status: gr.HTML
    clear_button: gr.Button


def banner(kind: str, message: str) -> str:
    role = "alert" if kind == "error" else "status"
    return f'<p class="banner banner--{kind}" role="{role}">{ui.esc(message)}</p>'


def classify_photo_bytes(data: bytes, swatches) -> dict:
    """Validate and match an uploaded photo; raises ValueError for a bad upload."""
    if not data or len(data) > config.MAX_UPLOAD_BYTES:
        raise ValueError("Please upload a JPEG or PNG image")
    image = colour.decode_image_bytes(data)
    dominant = colour.dominant_colour(image)
    lab_query = colour.srgb_to_lab(*dominant)
    swatch, delta_e = colour.nearest_swatch(lab_query, swatches)
    return {
        "swatch_class_id": swatch.id,
        "name": swatch.name,
        "hex": swatch.hex,
        "lab_l": round(swatch.lab_l, 2),
        "lab_a": round(swatch.lab_a, 2),
        "lab_b": round(swatch.lab_b, 2),
        "delta_e": delta_e,
        "confidence": colour.confidence_from_delta_e(delta_e),
        "print_hex": colour.rgb_to_hex(dominant),
        "image_path": None,
    }


def store_photo(data: bytes) -> str | None:
    from routes_classify import store_normalised_print

    try:
        image = colour.decode_image_bytes(data)
    except ValueError:
        return None
    return store_normalised_print(image)


def sample_payload() -> dict:
    """Classify the bundled reference print so the tab is populated on first paint."""
    from sqlalchemy import select

    from db import SessionLocal
    from models import SwatchClass
    from seed import seed_sample_image

    path = seed_sample_image()
    with open(path, "rb") as handle:
        data = handle.read()
    with SessionLocal() as db:
        swatches = db.execute(select(SwatchClass).order_by(SwatchClass.id)).scalars().all()
        try:
            return classify_photo_bytes(data, swatches)
        except ValueError:
            return {}


def default_score() -> dict:
    return scoring.score_payload(DEFAULT_CAP_MM, DEFAULT_GILL_MM)


DEFAULT_CAP_MM = 40.0
DEFAULT_GILL_MM = 6.0


def build_matcher(session_choices: list[tuple[str, str]], initial_match: dict) -> MatcherTab:
    score = default_score()
    with gr.Row(equal_height=False, elem_classes=["matcher-grid"]):
        with gr.Column(scale=5, min_width=240, elem_classes=["panel"]):
            gr.HTML(ui.section_header("Spore print photo", "JPEG or PNG, up to 5 MB", "1"))
            photo = gr.Image(
                value=config.STATIC_DIR / "sample_spore_print.png",
                type="filepath",
                # Upload only: the clipboard source makes Gradio call
                # navigator.clipboard.read() on mount, which the browser rejects
                # without a permission prompt and surfaces as an uncaught error.
                sources=["upload"],
                label="Drop a spore print photo",
                height=240,
                elem_id="photo-input",
            )
            banner_html = gr.HTML(
                banner("info", "Reference print loaded — upload your own to replace it."),
                elem_id="upload-banner",
            )
            clear_button = gr.Button("Clear photo", variant="secondary", size="sm", elem_id="clear-photo")

            gr.HTML(ui.section_header("Measurements", "drives the lookalike score live", "2"))
            cap = gr.Slider(
                minimum=config.CAP_MIN_MM,
                maximum=config.CAP_MAX_MM,
                value=DEFAULT_CAP_MM,
                step=1,
                label="Cap diameter (mm)",
                info="5–300 mm. Broad caps score higher.",
                elem_id="cap-slider",
            )
            gill = gr.Slider(
                minimum=config.GILL_MIN_MM,
                maximum=config.GILL_MAX_MM,
                value=DEFAULT_GILL_MM,
                step=0.1,
                label="Gill spacing (mm)",
                info="0.5–30 mm. Crowded (small) spacing scores higher.",
                elem_id="gill-slider",
            )

        with gr.Column(scale=7, min_width=260, elem_classes=["panel"]):
            match_card = gr.HTML(
                ui.match_card(initial_match or None),
                elem_id="match-card",
            )
            score_card = gr.HTML(ui.score_card(score, DEFAULT_CAP_MM, DEFAULT_GILL_MM), elem_id="score-card")

            gr.HTML(ui.section_header("Save to foray", "adds this find to a session", "3"))
            target_session = gr.Dropdown(
                choices=session_choices,
                value=session_choices[0][1] if session_choices else None,
                label="Foray session",
                info="Choose the session this find belongs to.",
                allow_custom_value=True,
                elem_id="target-session",
            )
            habitat = gr.Textbox(
                label="Habitat note",
                placeholder="Mossy oak ridge under Quercus robur",
                value="Mixed oak and beech woodland",
                max_lines=2,
                elem_id="habitat-note",
            )
            save_button = gr.Button(
                "Save find to foray",
                variant="primary",
                interactive=bool(initial_match),
                elem_id="save-find",
            )
            save_status = gr.HTML(
                '<p class="muted">A match is loaded, so this find can be saved straight away.</p>'
                if initial_match
                else '<p class="muted">Upload a photo first — a match is needed before saving.</p>',
                elem_id="save-status",
            )

    return MatcherTab(
        photo=photo,
        banner=banner_html,
        match_card=match_card,
        cap=cap,
        gill=gill,
        score_card=score_card,
        match_state=gr.State(initial_match or None),
        target_session=target_session,
        habitat=habitat,
        save_button=save_button,
        save_status=save_status,
        clear_button=clear_button,
    )
