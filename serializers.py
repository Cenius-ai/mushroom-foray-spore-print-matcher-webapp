"""JSON shapes shared by the API routers and the Gradio callbacks."""

from __future__ import annotations

import re

from models import Finding, ForaySession, SwatchClass

# Client-supplied image references must look exactly like our own uploads:
# a server-generated name inside `uploads/`, PNG only (never SVG: active content).
IMAGE_NAME_PATTERN = re.compile(r"^[a-z0-9_]{8,60}\.png$")
IMAGE_PATH_PATTERN = re.compile(r"^uploads/[a-z0-9_]{8,60}\.png$")


def finding_payload(finding: Finding, swatch: SwatchClass) -> dict:
    return {
        "id": finding.id,
        "session_id": finding.session_id,
        "swatch_class_id": finding.swatch_class_id,
        "swatch_name": swatch.name,
        "swatch_hex": swatch.hex,
        "match_confidence": round(finding.match_confidence, 1),
        "habitat": finding.habitat,
        "cap_diameter_mm": finding.cap_diameter_mm,
        "gill_spacing": finding.gill_spacing,
        "warning_score": finding.warning_score,
        "risk_band": finding.risk_band,
        "created_at": finding.created_at,
        "image_path": finding.image_path,
    }


def session_payload(session: ForaySession, finding_count: int) -> dict:
    return {
        "id": session.id,
        "name": session.name,
        "created_at": session.created_at,
        "finding_count": finding_count,
    }


def clean_image_path(value: str | None, upload_root) -> str | None:
    """Accept only server-shaped upload references whose file really exists."""
    if not value or not IMAGE_PATH_PATTERN.match(value):
        return None
    candidate = (upload_root.parent / value).resolve()
    try:
        candidate.relative_to(upload_root.resolve())
    except ValueError:
        return None
    return value if candidate.is_file() else None
