"""HTTP contract: auth, classify, score, sessions, findings and the dashboard."""

from __future__ import annotations

import io
import uuid

import pytest
from PIL import Image

import config
from conftest import DEMO_IDENTIFIER, DEMO_PASSWORD, form_login


def png_bytes(rgb: tuple[int, int, int], size: int = 64) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (size, size), rgb).save(buffer, format="PNG")
    return buffer.getvalue()


def unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# --- auth ------------------------------------------------------------------
def test_register_then_me_round_trip(anon_client):
    name = unique("forager")
    response = anon_client.post(
        "/api/auth/register", json={"username": name, "password": "supersecret"}
    )
    assert response.status_code == 201
    assert response.json()["username"] == name
    me = anon_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == name


def test_register_rejects_a_short_password(anon_client):
    response = anon_client.post(
        "/api/auth/register", json={"username": unique("short"), "password": "abc"}
    )
    assert response.status_code == 400
    assert response.json()["error"] == "Password must be at least 8 characters"


def test_register_rejects_a_blank_username(anon_client):
    response = anon_client.post(
        "/api/auth/register", json={"username": "   ", "password": "supersecret"}
    )
    assert response.status_code == 400
    assert response.json()["error"] == "Username is required"


def test_register_rejects_a_duplicate_username(anon_client, demo_client):
    response = anon_client.post(
        "/api/auth/register", json={"username": config.DEMO_USERNAME, "password": "supersecret"}
    )
    assert response.status_code == 409


def test_unknown_user_and_wrong_password_are_indistinguishable(anon_client):
    unknown = anon_client.post(
        "/api/auth/login", json={"username": "nobody-here", "password": "whatever1"}
    )
    wrong = anon_client.post(
        "/api/auth/login", json={"username": DEMO_IDENTIFIER, "password": "wrong-password"}
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json() == {"error": "Username or password is incorrect"}


@pytest.mark.parametrize(
    ("identifier", "password", "expected_username"),
    [
        (DEMO_IDENTIFIER, DEMO_PASSWORD, config.DEMO_USERNAME),
        (config.DEMO_USERNAME, DEMO_PASSWORD, config.DEMO_USERNAME),
        ("demo", "demo1234", "demo"),
        ("demo@cenius.ai", "demo1234", "demo"),
    ],
)
def test_login_accepts_either_email_or_username(anon_client, identifier, password, expected_username):
    response = anon_client.post(
        "/api/auth/login", json={"username": identifier, "password": password}
    )
    assert response.status_code == 200
    assert response.json()["username"] == expected_username


def test_me_requires_a_session(anon_client):
    response = anon_client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]


def test_logout_clears_the_session(demo_client):
    from fastapi.testclient import TestClient

    import app as app_module

    with TestClient(app_module.app) as client:
        client.post(
            "/api/auth/login", json={"username": DEMO_IDENTIFIER, "password": DEMO_PASSWORD}
        )
        assert client.post("/api/auth/logout").status_code == 204
        assert client.get("/api/auth/me").status_code == 401


def test_session_cookie_is_httponly_and_not_secure_so_plain_http_works(anon_client):
    response = anon_client.post(
        "/api/auth/login", json={"username": DEMO_IDENTIFIER, "password": DEMO_PASSWORD}
    )
    raw = response.headers.get("set-cookie", "").lower()
    assert "httponly" in raw
    assert "samesite=lax" in raw
    assert "secure" not in raw


# --- sign-in page ----------------------------------------------------------
def test_front_door_serves_the_sign_in_card_as_html(anon_client):
    response = anon_client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'name="username"' in response.text and 'name="password"' in response.text
    assert "Demo: cenius@cenius.ai / cenius" in response.text


@pytest.mark.parametrize("path", ["/", "/index.html", "/app", "/home"])
def test_every_front_door_alias_answers_with_html(anon_client, path):
    response = anon_client.get(path, follow_redirects=False)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_sign_in_page_shows_the_demo_credential(anon_client):
    page = anon_client.get("/login")
    assert page.status_code == 200
    assert "Demo: cenius@cenius.ai / cenius" in page.text
    assert "demo / demo1234" in page.text
    assert 'name="username"' in page.text and 'name="password"' in page.text


def test_sign_in_form_rejects_a_wrong_password_with_one_message(anon_client):
    response = form_login(anon_client, DEMO_IDENTIFIER, "definitely-wrong")
    assert response.status_code == 401
    assert "Username or password is incorrect" in response.text


def test_sign_in_form_logs_in_and_redirects_into_the_app(anon_client):
    response = form_login(anon_client, DEMO_IDENTIFIER, DEMO_PASSWORD)
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert anon_client.get("/api/auth/me").status_code == 200


def test_sign_in_form_registers_with_validation(anon_client):
    short = form_login(anon_client, unique("tiny"), "abc", mode="register")
    assert short.status_code == 400
    assert "Password must be at least 8 characters" in short.text

    created = form_login(anon_client, unique("newbie"), "longenough", mode="register")
    assert created.status_code == 303
    assert anon_client.get("/api/auth/me").status_code == 200


def test_signed_in_visitors_skip_the_sign_in_page(anon_client):
    form_login(anon_client, DEMO_IDENTIFIER, DEMO_PASSWORD)
    response = anon_client.get("/login", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_authenticated_root_serves_the_gradio_shell(anon_client):
    form_login(anon_client, DEMO_IDENTIFIER, DEMO_PASSWORD)
    response = anon_client.get("/")
    assert response.status_code == 200
    assert "gradio" in response.text.lower()
    assert response.headers["x-content-type-options"] == "nosniff"


# --- classify --------------------------------------------------------------
def test_classify_matches_a_solid_cream_print(demo_client):
    response = demo_client.post(
        "/api/classify",
        files={"file": ("print.png", png_bytes((237, 224, 184)), "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Cream"
    assert body["hex"] == "#EDE0B8"
    assert 0 <= body["confidence"] <= 100
    assert body["delta_e"] >= 0
    assert body["image_path"].startswith("uploads/")


def test_classify_rejects_a_non_image(demo_client):
    response = demo_client.post(
        "/api/classify",
        files={"file": ("print.pdf", b"%PDF-1.4 not an image", "application/pdf")},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "Please upload a JPEG or PNG image"


def test_classify_rejects_a_png_typed_pdf_payload(demo_client):
    response = demo_client.post(
        "/api/classify",
        files={"file": ("print.png", b"%PDF-1.4 not an image", "image/png")},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "Please upload a JPEG or PNG image"


def test_classify_rejects_an_oversized_upload(demo_client):
    oversized = b"\x89PNG\r\n\x1a\n" + b"0" * (config.MAX_UPLOAD_BYTES + 10)
    response = demo_client.post(
        "/api/classify", files={"file": ("big.png", oversized, "image/png")}
    )
    assert response.status_code == 400


def test_classify_requires_a_session(anon_client):
    response = anon_client.post(
        "/api/classify", files={"file": ("print.png", png_bytes((237, 224, 184)), "image/png")}
    )
    assert response.status_code == 401


# --- score -----------------------------------------------------------------
def test_score_low_band_with_two_factors(demo_client):
    response = demo_client.post("/api/score", json={"cap_diameter_mm": 30, "gill_spacing": 7})
    assert response.status_code == 200
    body = response.json()
    assert body["risk_band"] == "low"
    assert [factor["component"] for factor in body["factors"]] == ["cap", "gill"]


def test_score_high_band_for_a_broad_cap_and_crowded_gills(demo_client):
    response = demo_client.post("/api/score", json={"cap_diameter_mm": 250, "gill_spacing": 1})
    assert response.status_code == 200
    body = response.json()
    assert body["risk_band"] == "high"
    assert body["score"] >= 67


def test_score_rejects_an_out_of_range_cap(demo_client):
    response = demo_client.post("/api/score", json={"cap_diameter_mm": 900, "gill_spacing": 5})
    assert response.status_code == 422
    assert "cap_diameter_mm" in response.json()["error"]


# --- sessions + findings ---------------------------------------------------
def test_create_and_list_sessions(demo_client):
    name = unique("Autumn foray")
    created = demo_client.post("/api/sessions", json={"name": name})
    assert created.status_code == 201
    body = created.json()
    assert body["finding_count"] == 0
    listed = demo_client.get("/api/sessions").json()["sessions"]
    assert name in [row["name"] for row in listed]


def test_blank_session_name_is_rejected(demo_client):
    response = demo_client.post("/api/sessions", json={"name": "  "})
    assert response.status_code == 400
    assert response.json()["error"] == "Session name is required"


def test_finding_round_trip_joins_the_swatch_class(demo_client):
    session_id = demo_client.post("/api/sessions", json={"name": unique("Ridge")}).json()["id"]
    swatch = demo_client.get("/api/dashboard").json()["swatch_counts"][1]

    created = demo_client.post(
        f"/api/sessions/{session_id}/findings",
        json={
            "swatch_class_id": 2,
            "image_path": None,
            "match_confidence": 88.5,
            "cap_diameter_mm": 120,
            "gill_spacing": 4,
            "warning_score": 1,
            "risk_band": "low",
            "habitat": "Mossy oak ridge",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["swatch_name"] == swatch["name"]
    assert body["swatch_hex"] == swatch["hex"]
    # the score is re-derived server-side, never taken from the body
    assert body["warning_score"] == 60
    assert body["risk_band"] == "moderate"

    listed = demo_client.get(f"/api/sessions/{session_id}/findings").json()
    assert listed["session_name"]
    assert [row["habitat"] for row in listed["findings"]] == ["Mossy oak ridge"]


def test_empty_session_lists_an_empty_findings_array(demo_client):
    session_id = demo_client.post("/api/sessions", json={"name": unique("Empty")}).json()["id"]
    response = demo_client.get(f"/api/sessions/{session_id}/findings")
    assert response.status_code == 200
    assert response.json()["findings"] == []


def test_findings_and_sessions_are_scoped_to_their_owner(demo_client, second_user):
    victim_session = demo_client.post("/api/sessions", json={"name": unique("Private")}).json()["id"]

    assert second_user.get(f"/api/sessions/{victim_session}/findings").status_code == 404
    assert second_user.post(
        f"/api/sessions/{victim_session}/findings",
        json={
            "swatch_class_id": 1,
            "match_confidence": 50,
            "cap_diameter_mm": 60,
            "gill_spacing": 5,
            "habitat": "not mine",
        },
    ).status_code == 404
    assert second_user.get(f"/api/dashboard?session_id={victim_session}").status_code == 404
    assert victim_session not in [
        row["id"] for row in second_user.get("/api/sessions").json()["sessions"]
    ]


def test_findings_require_a_session_cookie(anon_client):
    assert anon_client.get("/api/sessions").status_code == 401
    assert anon_client.post("/api/sessions", json={"name": "nope"}).status_code == 401
    assert anon_client.get("/api/dashboard").status_code == 401


def test_unknown_swatch_class_is_rejected(demo_client):
    session_id = demo_client.post("/api/sessions", json={"name": unique("Bad swatch")}).json()["id"]
    response = demo_client.post(
        f"/api/sessions/{session_id}/findings",
        json={
            "swatch_class_id": 999,
            "match_confidence": 50,
            "cap_diameter_mm": 60,
            "gill_spacing": 5,
            "habitat": "nowhere",
        },
    )
    assert response.status_code == 422


def test_habitat_is_required(demo_client):
    session_id = demo_client.post("/api/sessions", json={"name": unique("No habitat")}).json()["id"]
    response = demo_client.post(
        f"/api/sessions/{session_id}/findings",
        json={
            "swatch_class_id": 1,
            "match_confidence": 50,
            "cap_diameter_mm": 60,
            "gill_spacing": 5,
            "habitat": "   ",
        },
    )
    assert response.status_code == 422
    assert "Habitat" in response.json()["error"]


# --- dashboard -------------------------------------------------------------
def test_dashboard_aggregates_cover_only_the_signed_in_user(demo_client):
    body = demo_client.get("/api/dashboard").json()
    assert body["session_id"] is None
    assert body["total_findings"] >= 8
    assert len(body["swatch_counts"]) == 6
    assert len(body["confidence_bins"]) == 5
    assert {row["band"] for row in body["risk_bands"]} == {"low", "moderate", "high"}
    assert len(body["scatter"]) == body["total_findings"]
    assert 0 <= body["mean_confidence"] <= 100
    assert body["high_risk_count"] == next(
        row["count"] for row in body["risk_bands"] if row["band"] == "high"
    )


def test_dashboard_scoped_to_an_empty_session_is_all_zeroes(demo_client):
    session_id = demo_client.post("/api/sessions", json={"name": unique("Nothing yet")}).json()["id"]
    body = demo_client.get(f"/api/dashboard?session_id={session_id}").json()
    assert body["total_findings"] == 0
    assert body["mean_confidence"] == 0
    assert body["high_risk_count"] == 0
    assert body["swatch_counts"] == []
    assert body["confidence_bins"] == []
    assert body["scatter"] == []


def test_dashboard_scoped_to_the_demo_session(demo_client):
    sessions = demo_client.get("/api/sessions").json()["sessions"]
    demo_session = next(row for row in sessions if row["name"].startswith("Autumn ridge foray"))
    body = demo_client.get(f"/api/dashboard?session_id={demo_session['id']}").json()
    assert body["total_findings"] == 8
    assert body["session_id"] == demo_session["id"]


# --- media -----------------------------------------------------------------
def test_media_is_served_to_its_owner_only(demo_client, second_user):
    listed = demo_client.get("/api/sessions").json()["sessions"]
    demo_session = next(row for row in listed if row["name"].startswith("Autumn ridge foray"))
    findings = demo_client.get(f"/api/sessions/{demo_session['id']}/findings").json()["findings"]
    filename = findings[0]["image_path"].split("/")[-1]

    mine = demo_client.get(f"/media/{filename}")
    assert mine.status_code == 200
    assert mine.headers["content-type"] == "image/png"

    assert second_user.get(f"/media/{filename}").status_code == 404
    assert demo_client.get("/media/../../foray.db").status_code == 404
    assert demo_client.get("/media/nope.png").status_code == 404


# --- health ----------------------------------------------------------------
def test_health_endpoint(anon_client):
    response = anon_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# --- re-entrancy -----------------------------------------------------------
def test_double_clicked_save_creates_exactly_one_finding(demo_client):
    session_id = demo_client.post("/api/sessions", json={"name": unique("Double click")}).json()["id"]
    body = {
        "swatch_class_id": 3,
        "match_confidence": 77.0,
        "cap_diameter_mm": 95,
        "gill_spacing": 4.5,
        "habitat": "Double-click guard copse",
    }
    first = demo_client.post(f"/api/sessions/{session_id}/findings", json=body)
    second = demo_client.post(f"/api/sessions/{session_id}/findings", json=body)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    listed = demo_client.get(f"/api/sessions/{session_id}/findings").json()["findings"]
    assert len(listed) == 1


def test_plan_demo_account_signs_in_and_has_its_own_foray_history(anon_client):
    response = anon_client.post(
        "/api/auth/login", json={"username": "demo", "password": "demo1234"}
    )
    assert response.status_code == 200
    assert response.json()["username"] == "demo"

    sessions = anon_client.get("/api/sessions").json()["sessions"]
    assert any(row["name"].startswith("Autumn ridge foray") for row in sessions)
    assert sum(row["finding_count"] for row in sessions) == 11
    dashboard = anon_client.get("/api/dashboard").json()
    assert dashboard["total_findings"] == 11
    assert len(dashboard["swatch_counts"]) == 6
