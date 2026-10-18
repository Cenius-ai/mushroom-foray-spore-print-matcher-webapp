"""``/api/sessions/{id}/findings`` - save a find and read a session's finds."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import require_user
from db import get_db
from foray_service import create_finding, session_findings

router = APIRouter(prefix="/api/sessions", tags=["foray"])


class FindingCreate(BaseModel):
    swatch_class_id: int
    image_path: str | None = None
    match_confidence: float = 0.0
    cap_diameter_mm: Any = None
    gill_spacing: Any = None
    warning_score: float | None = None
    risk_band: str | None = None
    habitat: str = ""


@router.post("/{session_id}/findings", status_code=201)
def post_finding(
    session_id: int,
    body: FindingCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    user = require_user(request, db)
    return create_finding(db, user.id, session_id, body.model_dump())


@router.get("/{session_id}/findings")
def get_findings(session_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    return session_findings(db, user.id, session_id)
