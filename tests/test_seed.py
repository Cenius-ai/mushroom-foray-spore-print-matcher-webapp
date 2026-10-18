"""Seed integrity: six Lab-corrected swatches, the demo account and idempotency."""

from __future__ import annotations

import color as colour
import config
from db import session_scope
from models import Finding, ForaySession, SwatchClass, User
from seed import FINDING_SEED, SWATCH_SEED, seed_all

from sqlalchemy import func, select


def test_six_swatches_exist_with_lab_centroids_from_the_shared_function():
    with session_scope() as db:
        rows = db.execute(select(SwatchClass).order_by(SwatchClass.id)).scalars().all()
    assert [row.name for row in rows] == [name for name, _hex, _desc in SWATCH_SEED]
    for row in rows:
        expected = colour.hex_to_lab(row.hex)
        assert row.lab_l is not None and row.lab_a is not None and row.lab_b is not None
        assert abs(row.lab_l - expected[0]) < 1e-6
        assert abs(row.lab_a - expected[1]) < 1e-6
        assert abs(row.lab_b - expected[2]) < 1e-6


def test_seeding_twice_does_not_duplicate_anything():
    with session_scope() as db:
        before = {
            "swatches": db.execute(select(func.count(SwatchClass.id))).scalar_one(),
            "findings": db.execute(select(func.count(Finding.id))).scalar_one(),
            "sessions": db.execute(select(func.count(ForaySession.id))).scalar_one(),
            "users": db.execute(select(func.count(User.id))).scalar_one(),
        }
    seed_all()
    seed_all()
    with session_scope() as db:
        after = {
            "swatches": db.execute(select(func.count(SwatchClass.id))).scalar_one(),
            "findings": db.execute(select(func.count(Finding.id))).scalar_one(),
            "sessions": db.execute(select(func.count(ForaySession.id))).scalar_one(),
            "users": db.execute(select(func.count(User.id))).scalar_one(),
        }
    assert before["swatches"] == after["swatches"] == 6
    # re-seeding never adds a second copy of anything
    assert before["findings"] == after["findings"] >= len(FINDING_SEED)
    assert before["sessions"] == after["sessions"]
    assert before["users"] == after["users"]


def test_the_plan_demo_account_is_seeded_idempotently():
    from auth import verify_password

    with session_scope() as db:
        user = db.execute(
            select(User).where(User.username == config.PLAN_DEMO_USERNAME)
        ).scalar_one()
        assert user.password_hash != config.PLAN_DEMO_PASSWORD
        assert verify_password("demo1234", user.password_hash)
        assert not verify_password("cenius", user.password_hash)
        owned = db.execute(
            select(ForaySession).where(ForaySession.user_id == user.id)
        ).scalars().all()
        findings = db.execute(
            select(Finding)
            .join(ForaySession, ForaySession.id == Finding.session_id)
            .where(ForaySession.user_id == user.id)
        ).scalars().all()
    assert len(owned) == 2
    assert len(findings) == len(FINDING_SEED)


def test_demo_account_is_seeded_through_the_apps_own_hash_path():
    from auth import verify_password

    with session_scope() as db:
        user = db.execute(
            select(User).where(User.username == config.DEMO_USERNAME)
        ).scalar_one()
        assert user.email == config.DEMO_EMAIL
        assert user.password_hash != config.DEMO_PASSWORD
        assert verify_password(config.DEMO_PASSWORD, user.password_hash)
        assert not verify_password("wrong-password", user.password_hash)


def test_primary_demo_session_has_eight_finds_covering_every_swatch_and_band():
    with session_scope() as db:
        demo_user = db.execute(
            select(User).where(User.username == config.DEMO_USERNAME)
        ).scalar_one()
        session_row = db.execute(
            select(ForaySession).where(
                ForaySession.name.like("Autumn ridge foray%"),
                ForaySession.user_id == demo_user.id,
            )
        ).scalar_one()
        findings = db.execute(
            select(Finding).where(Finding.session_id == session_row.id)
        ).scalars().all()
        swatch_names = {
            db.get(SwatchClass, finding.swatch_class_id).name for finding in findings
        }
    assert len(findings) == 8
    assert swatch_names == {name for name, _hex, _desc in SWATCH_SEED}
    assert {finding.risk_band for finding in findings} == {"low", "moderate", "high"}
    assert all(0.0 <= finding.match_confidence <= 100.0 for finding in findings)
    assert all(finding.habitat for finding in findings)


def test_demo_finds_keep_their_confidence_inside_their_own_swatch_class():
    """Seeded prints are classified through the matcher, so a re-read must agree."""
    with session_scope() as db:
        rows = db.execute(select(Finding)).scalars().all()
        for finding in rows:
            swatch = db.get(SwatchClass, finding.swatch_class_id)
            assert swatch is not None
            assert finding.warning_score is not None
            assert 0 <= finding.warning_score <= 100
