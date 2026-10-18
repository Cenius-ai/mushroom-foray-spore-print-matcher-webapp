"""End-to-end smoke: sign in on the card, match a print, save a find, chart it."""

from __future__ import annotations

import io
import uuid

from PIL import Image

from conftest import DEMO_IDENTIFIER, DEMO_PASSWORD, form_login


def solid_png(rgb: tuple[int, int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (80, 80), rgb).save(buffer, format="PNG")
    return buffer.getvalue()


def test_reviewer_walkthrough_over_the_seeded_app(anon_client):
    # 1. the sign-in card is the front door and the demo credential works
    page = anon_client.get("/login")
    assert "Demo: cenius@cenius.ai / cenius" in page.text
    signed_in = form_login(anon_client, DEMO_IDENTIFIER, DEMO_PASSWORD)
    assert signed_in.status_code == 303

    # 2. the app shell loads for the signed-in visitor
    shell = anon_client.get("/")
    assert shell.status_code == 200

    # 3. upload a spore print and get the closest swatch
    match = anon_client.post(
        "/api/classify",
        files={"file": ("print.png", solid_png((183, 123, 46)), "image/png")},
    )
    assert match.status_code == 200
    result = match.json()
    assert result["name"] == "Ochre"
    assert result["confidence"] > 50

    # 4. move both sliders and read the explained score
    score = anon_client.post("/api/score", json={"cap_diameter_mm": 210, "gill_spacing": 2})
    assert score.status_code == 200
    assert score.json()["risk_band"] == "high"
    assert len(score.json()["factors"]) == 2

    # 5. save the find into a brand-new foray session
    session = anon_client.post(
        "/api/sessions", json={"name": f"Smoke foray {uuid.uuid4().hex[:6]}"}
    ).json()
    saved = anon_client.post(
        f"/api/sessions/{session['id']}/findings",
        json={
            "swatch_class_id": result["swatch_class_id"],
            "image_path": result["image_path"],
            "match_confidence": result["confidence"],
            "cap_diameter_mm": 210,
            "gill_spacing": 2,
            "habitat": "Pine duff",
        },
    )
    assert saved.status_code == 201
    finding = saved.json()
    assert finding["habitat"] == "Pine duff"
    assert finding["risk_band"] == "high"

    # 6. it is listed in the session and charted for that session only
    listed = anon_client.get(f"/api/sessions/{session['id']}/findings").json()["findings"]
    assert [row["id"] for row in listed] == [finding["id"]]

    charted = anon_client.get(f"/api/dashboard?session_id={session['id']}").json()
    assert charted["total_findings"] == 1
    assert charted["high_risk_count"] == 1
    assert charted["swatch_counts"][finding["swatch_class_id"] - 1]["count"] == 1

    # 7. the image is retrievable by its owner
    filename = finding["image_path"].split("/")[-1]
    assert anon_client.get(f"/media/{filename}").status_code == 200

    # 8. every screen the reviewer can click still renders
    sessions = anon_client.get("/api/sessions").json()["sessions"]
    assert sessions, "the foray rail should list at least one session"
    demo_session = next(row for row in sessions if row["name"].startswith("Autumn ridge foray"))
    assert demo_session["finding_count"] >= 8


def test_empty_accounts_see_invitations_not_errors(app_module):
    from fastapi.testclient import TestClient

    with TestClient(app_module.app) as fresh:
        name = f"empty{uuid.uuid4().hex[:6]}"
        assert fresh.post(
            "/api/auth/register", json={"username": name, "password": "emptyaccount"}
        ).status_code == 201

        assert fresh.get("/api/sessions").json() == {"sessions": []}
        dashboard = fresh.get("/api/dashboard").json()
        assert dashboard["total_findings"] == 0
        assert dashboard["scatter"] == []

        # the Gradio callbacks render the empty-state invitations, not blank panels
        class FakeRequest:
            def __init__(self, cookie):
                self.cookies = {"foray_session": cookie} if cookie else {}

        cookie = fresh.cookies.get("foray_session")
        header, _picker, summary, findings_html = app_module.on_load(FakeRequest(cookie))[:4]
        assert "Signed in as" in header
        assert "Create your first foray session to start logging finds" in summary
        assert "No finds logged yet" in findings_html
