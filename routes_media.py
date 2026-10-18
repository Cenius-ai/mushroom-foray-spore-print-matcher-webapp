"""``GET /media/{filename}`` - serve a stored spore-print image to its owner only.

Uploads live outside the served tree and are re-encoded to PNG on write, so this
route never hands out user-supplied bytes and never serves active content.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

import config
import serializers
from auth import require_user
from db import get_db

router = APIRouter(tags=["pages"])

# The stored key is the constant prefix below followed by a server-generated PNG
# name; the name is validated against the allowlist pattern before it is used.
UPLOAD_KEY_PREFIX = "uploads/"

# One fixed SQL statement: the only variable parts are named bind parameters
# (:image_path, :user_id), never string interpolation.
OWNED_IMAGE_SQL = text(
    "SELECT finding.id FROM finding "
    "JOIN foray_session ON foray_session.id = finding.session_id "
    "WHERE finding.image_path = :image_path AND foray_session.user_id = :user_id "
    "LIMIT 1"
)


@router.get("/media/{filename}")
def media(filename: str, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    if not serializers.IMAGE_NAME_PATTERN.match(filename):
        raise HTTPException(status_code=404, detail="Image not found")
    stored = UPLOAD_KEY_PREFIX + filename

    owned = db.execute(
        OWNED_IMAGE_SQL, {"image_path": stored, "user_id": user.id}
    ).first()
    if owned is None:
        # Unknown file and another user's file are indistinguishable.
        raise HTTPException(status_code=404, detail="Image not found")

    path = config.UPLOAD_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(
        path,
        media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="{filename}"', "Cache-Control": "private, max-age=600"},
    )
