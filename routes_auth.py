"""``/api/auth`` - register, login, logout and identity restore."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import (
    authenticate,
    clear_session_cookie,
    hash_password,
    issue_session_cookie,
    require_user,
    validate_registration_password,
    validate_username,
)
from db import get_db
from models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])

CONFLICT_MESSAGE = "That username is already taken"


class Credentials(BaseModel):
    username: str = ""
    password: str = ""


@router.post("/register", status_code=201)
def register(body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    username = body.username.strip()
    problem = validate_username(username)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    problem = validate_registration_password(body.password)
    if problem:
        raise HTTPException(status_code=400, detail=problem)

    taken = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if taken is not None:
        raise HTTPException(status_code=409, detail=CONFLICT_MESSAGE)

    user = User(username=username, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    issue_session_cookie(response, user.id)
    return {"user_id": user.id, "username": user.username}


@router.post("/login")
def login(body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    user = authenticate(db, body.username, body.password)
    if user is None:
        # Identical response for an unknown username and a wrong password.
        raise HTTPException(status_code=401, detail="Username or password is incorrect")
    issue_session_cookie(response, user.id)
    return {"user_id": user.id, "username": user.username}


@router.post("/logout", status_code=204)
def logout(request: Request, db: Session = Depends(get_db)):
    require_user(request, db)
    response = Response(status_code=204)
    clear_session_cookie(response)
    return response


@router.get("/me")
def me(request: Request, db: Session = Depends(get_db)):
    user = require_user(request, db)
    return {"user_id": user.id, "username": user.username, "email": user.email}

