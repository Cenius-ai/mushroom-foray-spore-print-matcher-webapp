"""``POST /api/score`` - the lookalike warning score for cap and gill measurements."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

import config
import scoring
from auth import require_user
from db import get_db

router = APIRouter(prefix="/api", tags=["matcher"])


class Measurements(BaseModel):
    cap_diameter_mm: float
    gill_spacing: float


@router.post("/score")
def score(body: Measurements, request: Request, db: Session = Depends(get_db)):
    require_user(request, db)
    if not (config.CAP_MIN_MM <= body.cap_diameter_mm <= config.CAP_MAX_MM):
        raise HTTPException(
            status_code=422,
            detail=f"cap_diameter_mm must be between {config.CAP_MIN_MM:g} and {config.CAP_MAX_MM:g}",
        )
    if not (config.GILL_MIN_MM <= body.gill_spacing <= config.GILL_MAX_MM):
        raise HTTPException(
            status_code=422,
            detail=f"gill_spacing must be between {config.GILL_MIN_MM:g} and {config.GILL_MAX_MM:g}",
        )
    return scoring.score_payload(body.cap_diameter_mm, body.gill_spacing)
