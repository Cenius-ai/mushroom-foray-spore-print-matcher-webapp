"""Lookalike warning score: a deterministic, explainable heuristic.

score = round(100 * (0.55 * cap_norm + 0.45 * gill_norm))
  cap_norm  = clamp((cap_mm - 20) / 160)      broad caps score higher
  gill_norm = clamp((8 - gill_mm) / 7)        crowded (small-spaced) gills score higher

Bands: low < 34, moderate 34-66, high >= 67.

This is a *heuristic* and is labelled as such everywhere it is rendered: it never
states that a mushroom is edible or toxic.
"""

from __future__ import annotations

from dataclasses import dataclass

import config
from color import clamp

CAP_WEIGHT = 0.55
GILL_WEIGHT = 0.45
CAP_FLOOR_MM = 20.0
CAP_SPAN_MM = 160.0
GILL_CEILING_MM = 8.0
GILL_SPAN_MM = 7.0
LOW_BAND_MAX = 34.0
MODERATE_BAND_MAX = 66.0


@dataclass(frozen=True)
class ScoreResult:
    score: float
    risk_band: str
    cap_contribution: float
    gill_contribution: float
    factors: list[dict]


def cap_norm(cap_mm: float) -> float:
    return clamp((cap_mm - CAP_FLOOR_MM) / CAP_SPAN_MM)


def gill_norm(gill_mm: float) -> float:
    return clamp((GILL_CEILING_MM - gill_mm) / GILL_SPAN_MM)


def risk_band(score: float) -> str:
    if score < LOW_BAND_MAX:
        return "low"
    if score <= MODERATE_BAND_MAX:
        return "moderate"
    return "high"


def _cap_factor_text(cap_mm: float, norm: float, points: float) -> str:
    if norm <= 0.0:
        return (
            f"Cap {cap_mm:.0f} mm is narrow, so the cap contribution is 0 of 55 points "
            f"— small caps rarely overlap with the broad-capped lookalikes."
        )
    return (
        f"Cap {cap_mm:.0f} mm is broad: cap factor {norm:.2f} x weight {CAP_WEIGHT:.2f} "
        f"contributes {points:.0f} of 55 points."
    )


def _gill_factor_text(gill_mm: float, norm: float, points: float) -> str:
    if norm <= 0.0:
        return (
            f"Gill spacing {gill_mm:.1f} mm is open, so the gill-crowding contribution is "
            f"0 of 45 points — widely spaced gills rarely match the crowded-gill lookalikes."
        )
    return (
        f"Gill spacing {gill_mm:.1f} mm is crowded: gill-crowding factor {norm:.2f} x weight "
        f"{GILL_WEIGHT:.2f} contributes {points:.0f} of 45 points."
    )


def score_find(cap_mm: float, gill_mm: float) -> ScoreResult:
    """Deterministic score + band + two explained factor entries."""
    if not (config.CAP_MIN_MM <= cap_mm <= config.CAP_MAX_MM):
        raise ValueError("cap_diameter_mm out of range")
    if not (config.GILL_MIN_MM <= gill_mm <= config.GILL_MAX_MM):
        raise ValueError("gill_spacing out of range")

    cap_component = CAP_WEIGHT * cap_norm(cap_mm)
    gill_component = GILL_WEIGHT * gill_norm(gill_mm)
    total = round(100.0 * (cap_component + gill_component), 0)

    factors = [
        {
            "component": "cap",
            "contribution": round(cap_component * 100.0, 0),
            "text": _cap_factor_text(cap_mm, cap_norm(cap_mm), cap_component * 100.0),
        },
        {
            "component": "gill",
            "contribution": round(gill_component * 100.0, 0),
            "text": _gill_factor_text(gill_mm, gill_norm(gill_mm), gill_component * 100.0),
        },
    ]
    return ScoreResult(
        score=total,
        risk_band=risk_band(total),
        cap_contribution=round(cap_component * 100.0, 0),
        gill_contribution=round(gill_component * 100.0, 0),
        factors=factors,
    )


def score_payload(cap_mm: float, gill_mm: float) -> dict:
    """The exact JSON body returned by ``POST /api/score``."""
    result = score_find(cap_mm, gill_mm)
    return {
        "score": result.score,
        "risk_band": result.risk_band,
        "factors": result.factors,
    }
