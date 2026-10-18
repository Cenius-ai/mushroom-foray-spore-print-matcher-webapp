"""``GET /api/dashboard`` - aggregates over the signed-in user's findings."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import owned_session, require_user
from db import get_db
from models import Finding, ForaySession, SwatchClass

router = APIRouter(prefix="/api", tags=["dashboard"])

CONFIDENCE_BINS = [(0, 20), (20, 40), (40, 60), (60, 80), (80, 100)]
RISK_BANDS = ("low", "moderate", "high")


def _bin_label(low: int, high: int) -> str:
    return f"{low}–{high}%"


def dashboard_payload(db: Session, user_id: int, session_id: int | None) -> dict:
    query = (
        select(Finding, SwatchClass)
        .join(ForaySession, ForaySession.id == Finding.session_id)
        .join(SwatchClass, SwatchClass.id == Finding.swatch_class_id)
        .where(ForaySession.user_id == user_id)
    )
    if session_id is not None:
        query = query.where(Finding.session_id == session_id)
    rows = db.execute(query.order_by(Finding.id)).all()

    swatches = db.execute(select(SwatchClass).order_by(SwatchClass.id)).scalars().all()
    empty = {
        "session_id": session_id,
        "total_findings": 0,
        "mean_confidence": 0.0,
        "high_risk_count": 0,
        "swatch_counts": [],
        "confidence_bins": [],
        "risk_bands": [],
        "scatter": [],
    }
    if not rows:
        return empty

    counts_by_swatch: dict[int, int] = {}
    for finding, _swatch in rows:
        counts_by_swatch[finding.swatch_class_id] = counts_by_swatch.get(finding.swatch_class_id, 0) + 1

    bins = [(low, high, 0) for low, high in CONFIDENCE_BINS]
    band_counts = {band: 0 for band in RISK_BANDS}
    for finding, _swatch in rows:
        confidence = max(0.0, min(100.0, finding.match_confidence))
        for index, (low, high) in enumerate(CONFIDENCE_BINS):
            is_last = index == len(CONFIDENCE_BINS) - 1
            if low <= confidence < high or (is_last and confidence >= low):
                bins[index] = (low, high, bins[index][2] + 1)
                break
        band_counts[finding.risk_band] = band_counts.get(finding.risk_band, 0) + 1

    total = len(rows)
    return {
        "session_id": session_id,
        "total_findings": total,
        "mean_confidence": round(sum(f.match_confidence for f, _ in rows) / total, 1),
        "high_risk_count": band_counts["high"],
        "swatch_counts": [
            {"name": swatch.name, "hex": swatch.hex, "count": counts_by_swatch.get(swatch.id, 0)}
            for swatch in swatches
        ],
        "confidence_bins": [
            {"bin": _bin_label(low, high), "count": count} for low, high, count in bins
        ],
        "risk_bands": [{"band": band, "count": band_counts[band]} for band in RISK_BANDS],
        "scatter": [
            {
                "cap_diameter_mm": finding.cap_diameter_mm,
                "gill_spacing": finding.gill_spacing,
                "risk_band": finding.risk_band,
                "swatch_hex": swatch.hex,
            }
            for finding, swatch in rows
        ],
    }


@router.get("/dashboard")
def dashboard(request: Request, session_id: int | None = None, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if session_id is not None:
        owned_session(db, user.id, session_id)  # 404 when unknown or foreign
    return dashboard_payload(db, user.id, session_id)
