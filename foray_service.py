"""Foray session and finding operations shared by the JSON API and the Gradio UI.

Ownership is resolved here through :func:`auth.owned_session`, so every caller -
HTTP route or Gradio callback - applies the identical check and the identical
validation before anything is written.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import config
import scoring
from auth import owned_session
from models import Finding, ForaySession, SwatchClass
from serializers import clean_image_path, finding_payload, session_payload


def list_sessions(db: Session, user_id: int) -> list[dict]:
    rows = (
        db.execute(
            select(ForaySession)
            .where(ForaySession.user_id == user_id)
            .order_by(ForaySession.created_at.desc(), ForaySession.id.desc())
        )
        .scalars()
        .all()
    )
    counts = db.execute(
        select(Finding.session_id, func.count(Finding.id))
        .join(ForaySession, ForaySession.id == Finding.session_id)
        .where(ForaySession.user_id == user_id)
        .group_by(Finding.session_id)
    ).all()
    counts_by_session = {session_id: count for session_id, count in counts}
    return [session_payload(row, counts_by_session.get(row.id, 0)) for row in rows]


def create_session(db: Session, user_id: int, name: str) -> dict:
    clean_name = (name or "").strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Session name is required")
    if len(clean_name) > config.SESSION_NAME_MAX_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Session name must be at most {config.SESSION_NAME_MAX_CHARS} characters",
        )
    duplicate = db.execute(
        select(ForaySession).where(
            ForaySession.user_id == user_id, ForaySession.name == clean_name
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="You already have a foray session with that name")

    session_row = ForaySession(user_id=user_id, name=clean_name)
    db.add(session_row)
    db.commit()
    db.refresh(session_row)
    return session_payload(session_row, 0)


def session_findings(db: Session, user_id: int, session_id: int) -> dict:
    session_row = owned_session(db, user_id, session_id)
    rows = db.execute(
        select(Finding, SwatchClass)
        .join(SwatchClass, SwatchClass.id == Finding.swatch_class_id)
        .where(Finding.session_id == session_row.id)
        .order_by(Finding.created_at.desc(), Finding.id.desc())
    ).all()
    return {
        "session_id": session_row.id,
        "session_name": session_row.name,
        "findings": [finding_payload(finding, swatch) for finding, swatch in rows],
    }


def create_finding(db: Session, user_id: int, session_id: int, body: dict) -> dict:
    """Validate then insert one finding. The score is always re-derived here."""
    session_row = owned_session(db, user_id, session_id)  # 404 before anything is written

    swatch_class_id = body.get("swatch_class_id")
    swatch = db.get(SwatchClass, swatch_class_id) if swatch_class_id is not None else None
    if swatch is None:
        raise HTTPException(status_code=422, detail="Unknown swatch_class_id")

    cap_mm = _as_float(body.get("cap_diameter_mm"), "cap_diameter_mm")
    gill_mm = _as_float(body.get("gill_spacing"), "gill_spacing")
    confidence = _as_float(body.get("match_confidence", 0.0), "match_confidence")

    if not (config.CAP_MIN_MM <= cap_mm <= config.CAP_MAX_MM):
        raise HTTPException(status_code=422, detail="cap_diameter_mm is out of range")
    if not (config.GILL_MIN_MM <= gill_mm <= config.GILL_MAX_MM):
        raise HTTPException(status_code=422, detail="gill_spacing is out of range")
    if not (0.0 <= confidence <= 100.0):
        raise HTTPException(status_code=422, detail="match_confidence must be between 0 and 100")

    habitat = str(body.get("habitat") or "").strip()
    if not habitat:
        raise HTTPException(status_code=422, detail="Habitat note is required")
    if len(habitat) > config.HABITAT_MAX_CHARS:
        raise HTTPException(
            status_code=422,
            detail=f"Habitat note must be at most {config.HABITAT_MAX_CHARS} characters",
        )

    score = scoring.score_find(cap_mm, gill_mm)

    # Re-entrancy guard: a double-clicked Save returns the find it just wrote
    # instead of creating a second identical row.
    duplicate = db.execute(
        select(Finding)
        .where(
            Finding.session_id == session_row.id,
            Finding.swatch_class_id == swatch.id,
            Finding.habitat == habitat,
            Finding.cap_diameter_mm == cap_mm,
            Finding.gill_spacing == gill_mm,
            Finding.match_confidence == round(confidence, 1),
        )
        .order_by(Finding.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if duplicate is not None and _seconds_since(duplicate.created_at) < 10:
        return finding_payload(duplicate, swatch)

    finding = Finding(
        session_id=session_row.id,
        swatch_class_id=swatch.id,
        image_path=clean_image_path(body.get("image_path"), config.UPLOAD_DIR),
        match_confidence=round(confidence, 1),
        cap_diameter_mm=cap_mm,
        gill_spacing=gill_mm,
        warning_score=score.score,
        risk_band=score.risk_band,
        habitat=habitat,
    )
    db.add(finding)
    db.commit()
    db.refresh(finding)
    return finding_payload(finding, swatch)


def _seconds_since(iso_timestamp: str) -> float:
    try:
        created = datetime.fromisoformat(iso_timestamp)
    except (TypeError, ValueError):
        return float("inf")
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - created).total_seconds()


def _as_float(value: object, field: str) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"{field} must be a number") from exc
