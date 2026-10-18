"""Gradio callback level tests: the exact code path a browser click triggers."""

from __future__ import annotations

import app as app_module
from auth import issue_session_token
from conftest import DEMO_IDENTIFIER, DEMO_PASSWORD, form_login
from db import session_scope
from models import User
from ui_common import DISCLAIMER


class FakeRequest:
    """Stands in for gr.Request: only `.cookies` is read by the callbacks."""

    def __init__(self, cookie: str | None):
        self.cookies = {"foray_session": cookie} if cookie else {}


def cookie_for(username: str) -> str:
    with session_scope() as db:
        user = db.query(User).filter(User.username == username).one()
        user_id = user.id
    return issue_session_token(user_id)


def signed_in_request(username: str = app_module.config.DEMO_USERNAME) -> FakeRequest:
    return FakeRequest(cookie_for(username))


def test_load_populates_every_panel_for_the_signed_in_user():
    outputs = app_module.on_load(signed_in_request())
    assert len(outputs) == 14
    header, target_session, summary, findings_html = outputs[:4]
    assert "Signed in as" in header and "cenius" in header
    assert target_session["choices"], "the matcher session picker should be offered a session"
    assert "logged finds" in summary
    assert "<table" in findings_html and "habitat" in findings_html.lower()


def test_load_hides_everything_for_a_request_without_a_cookie():
    outputs = app_module.on_load(FakeRequest(None))
    assert len(outputs) == 14
    assert "Sign in" in outputs[0]
    assert "session expired" in outputs[2].lower()


def test_photo_upload_returns_a_match_card_with_the_swatch_details():
    import config

    match_card, banner_html, match, save_button, save_status = app_module.on_photo(
        str(config.STATIC_DIR / "sample_spore_print.png"), None, signed_in_request()
    )
    assert "Closest swatch class" in match_card
    assert "confidence" in match_card
    assert "Matched" in banner_html
    assert match["swatch_class_id"] and match["hex"].startswith("#")
    assert 0 <= match["confidence"] <= 100
    assert save_button["interactive"] is True


def test_bad_upload_keeps_the_previous_match_visible(tmp_path):
    previous = {"name": "Cream", "hex": "#EDE0B8", "delta_e": 2.1, "confidence": 86.0}
    bogus = tmp_path / "spore_print.pdf"
    bogus.write_bytes(b"%PDF-1.4 not an image")

    match_card, banner_html, match, save_button, _status = app_module.on_photo(
        str(bogus), previous, signed_in_request()
    )
    assert "Please upload a JPEG or PNG image" in banner_html
    assert "banner--error" in banner_html
    assert "Cream" in match_card, "the previous result must survive a failed upload"
    assert match == previous
    # the save button is left untouched: the previous match is still saveable
    assert "interactive" not in save_button


def test_measurement_sliders_recompute_score_band_and_both_factors():
    low = app_module.on_measurements(40, 6)
    high = app_module.on_measurements(250, 1)
    assert low != high
    assert "Lookalike warning score" in low
    assert "pill--low" in low and "pill--high" in high
    assert low.count("<li class=\"factor\"") == 2
    assert DISCLAIMER in low and DISCLAIMER in high


def test_slider_band_changes_without_a_submit():
    bands = [app_module.on_measurements(cap, 5) for cap in (20, 120, 260)]
    assert ["pill--low" in bands[0], "pill--moderate" in bands[1], "pill--high" in bands[2]] == [
        True,
        True,
        True,
    ]


def test_save_creates_a_find_and_refreshes_the_foray_and_dashboard():
    request = signed_in_request()
    created = app_module.on_create_session("Callback ridge walk", request)
    status, picker = created[0], created[1]
    assert "Created" in status
    session_value = picker["value"]

    match = {
        "swatch_class_id": 2,
        "confidence": 91.5,
        "image_path": None,
        "hex": "#EDE0B8",
        "name": "Cream",
    }
    outputs = app_module.on_save(match, 130, 3.5, session_value, "Pine duff", request)
    assert len(outputs) == 13
    assert "Saved to" in outputs[0]
    assert "Pine duff" in outputs[3], "the new find must be listed on the Foray tab"
    assert "kpi-strip" in outputs[4]


def test_save_without_a_match_explains_what_is_missing():
    outputs = app_module.on_save(None, 100, 5, "1", "Pine duff", signed_in_request())
    assert "Make a match first" in outputs[0]


def test_save_into_a_missing_session_is_refused(tmp_path):
    outputs = app_module.on_save(
        {"swatch_class_id": 1, "confidence": 50.0}, 100, 5, "9999", "Pine duff", signed_in_request()
    )
    assert "not found" in outputs[0].lower() or "session" in outputs[0].lower()


def test_create_session_rejects_a_blank_name():
    outputs = app_module.on_create_session("   ", signed_in_request())
    assert "Session name is required" in outputs[0]


def test_select_session_renders_its_own_findings_table():
    client_sidebar = app_module.on_load(signed_in_request())
    rail = client_sidebar[-1]
    first_value = rail["value"]
    table = app_module.on_select_session(first_value, signed_in_request())
    assert "<table" in table or "empty" in table


def test_select_session_with_a_foreign_id_shows_a_safe_message():
    html = app_module.on_select_session("9999", signed_in_request())
    assert "could not be loaded" in html


def test_dashboard_filter_returns_all_eight_panels():
    outputs = app_module.on_dashboard_filter("all", signed_in_request())
    assert len(outputs) == 8
    assert "kpi-strip" in outputs[0]
    assert list(outputs[1].columns) == ["Swatch class", "Finds", "Series"]


def test_callbacks_reject_requests_without_a_cookie():
    blank = FakeRequest(None)
    assert "expired" in app_module.on_save(None, 100, 5, "1", "x", blank)[0].lower()
    assert "expired" in app_module.on_create_session("Nope", blank)[0].lower()
    assert "expired" in app_module.on_select_session("1", blank).lower()


def test_sign_in_cookie_reaches_the_gradio_identity(anon_client):
    """The cookie issued by the sign-in card is the one Gradio resolves."""
    form_login(anon_client, DEMO_IDENTIFIER, DEMO_PASSWORD)
    cookie = anon_client.cookies.get("foray_session")
    assert cookie
    assert app_module.current_identity(FakeRequest(cookie)).username == "cenius"
    assert app_module.current_identity(FakeRequest(None)) is None
