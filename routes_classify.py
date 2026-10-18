"""``POST /api/classify`` - upload a spore-print photo, get the nearest swatch."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

import config
import color as colour
from auth import require_user
from db import get_db
from models import SwatchClass

router = APIRouter(prefix="/api", tags=["matcher"])

BAD_UPLOAD_MESSAGE = "Please upload a JPEG or PNG image"


def _reject(detail: str = BAD_UPLOAD_MESSAGE) -> None:
    from fastapi import HTTPException

    raise HTTPException(status_code=400, detail=detail)


async def read_capped_upload(upload: UploadFile | None) -> bytes:
    """Read at most MAX_UPLOAD_BYTES + 1, so an oversized body is rejected early."""
    if upload is None or not upload.filename:
        _reject()
    content_type = (upload.content_type or "").split(";")[0].strip().lower()
    if content_type not in config.ALLOWED_IMAGE_MIME:
        _reject()
    data = await upload.read(config.MAX_UPLOAD_BYTES + 1)
    if not data or len(data) > config.MAX_UPLOAD_BYTES:
        _reject()
    return data


def store_normalised_print(image) -> str:
    """Persist the upload as a fresh PNG under a server-generated name.

    Re-encoding through Pillow drops EXIF and any polyglot payload, and a PNG of
    our own naming can never be an SVG (active content) served from our origin.
    """
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{secrets.token_hex(12)}.png"
    image.convert("RGB").save(config.UPLOAD_DIR / filename, format="PNG")
    return f"uploads/{filename}"


def classify_image(image, swatches) -> dict:
    """Pure classification: dominant colour -> CIE Lab -> nearest centroid."""
    dominant = colour.dominant_colour(image)
    lab_query = colour.srgb_to_lab(*dominant)
    swatch, delta_e = colour.nearest_swatch(lab_query, swatches)
    return {
        "swatch_class_id": swatch.id,
        "name": swatch.name,
        "hex": swatch.hex,
        "lab_l": round(swatch.lab_l, 2),
        "lab_a": round(swatch.lab_a, 2),
        "lab_b": round(swatch.lab_b, 2),
        "delta_e": delta_e,
        "confidence": colour.confidence_from_delta_e(delta_e),
        "print_hex": colour.rgb_to_hex(dominant),
    }


@router.post("/classify")
async def classify(request: Request, file: UploadFile | None = File(default=None), db: Session = Depends(get_db)):
    require_user(request, db)
    data = await read_capped_upload(file)
    try:
        image = colour.decode_image_bytes(data)
    except ValueError:
        _reject()

    swatches = db.execute(select(SwatchClass).order_by(SwatchClass.id)).scalars().all()
    if not swatches:
        _reject("No swatch classes are seeded yet")

    result = classify_image(image, swatches)
    result["image_path"] = store_normalised_print(image)
    return result
