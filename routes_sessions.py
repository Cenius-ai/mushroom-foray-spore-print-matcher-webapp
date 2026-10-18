"""``/api/sessions`` - create and list the signed-in user's foray sessions."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import require_user
from db import get_db
from foray_service import create_session, list_sessions

router = APIRouter(prefix="/api/sessions", tags=["foray"])


class SessionCreate(BaseModel):
    name: str = ""


@router.post("", status_code=201)
def post_session(body: SessionCreate, request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    return create_session(db, user.id, body.name)


@router.get("")
def get_sessions(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    return {"sessions": list_sessions(db, user.id)}
