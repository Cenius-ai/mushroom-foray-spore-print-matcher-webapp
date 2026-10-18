"""Sign-in screen and the small authenticated routes that live outside Gradio.

The sign-in card is rendered server-side so it works before any JavaScript runs
and so automation can drive plain inputs. Sessions are signed HttpOnly cookies;
passwords are verified through :mod:`auth`, the same path the JSON API uses.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

import config
from auth import (
    authenticate,
    clear_session_cookie,
    csrf_token_for,
    csrf_token_is_valid,
    hash_password,
    issue_session_cookie,
    user_from_request,
    validate_registration_password,
    validate_username,
)
from db import SessionLocal
from models import User

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory=str(config.TEMPLATES_DIR))

INVALID_CREDENTIALS = "Username or password is incorrect"
CSRF_FAILED = "Your sign-in form expired. Please try again."


def render_signin(request: Request, *, mode: str, error: str = "", username: str = "", status_code: int = 200):
    token = csrf_token_for()
    response = templates.TemplateResponse(
        request,
        "login.html",
        {
            "request": request,
            "mode": mode,
            "error": error,
            "username": username,
            "csrf_token": token,
        },
        status_code=status_code,
    )
    response.set_cookie(
        key=config.CSRF_COOKIE_NAME,
        value=token,
        max_age=60 * 60 * 12,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )
    return response


def signin_card_response(request: Request, mode: str = "signin", status_code: int = 200):
    """The sign-in card itself. The front door renders this for anonymous visitors,
    so `GET /` is a real HTML page (200) rather than a redirect."""
    chosen = "register" if mode == "register" else "signin"
    return render_signin(request, mode=chosen, status_code=status_code)


@router.get("/login", response_class=HTMLResponse)
def signin_page(request: Request, mode: str = "signin"):
    with SessionLocal() as db:
        if user_from_request(request, db) is not None:
            return RedirectResponse("/", status_code=303)
    chosen = "register" if mode == "register" else "signin"
    return render_signin(request, mode=chosen)


@router.post("/login", response_class=HTMLResponse)
async def signin_submit(request: Request):
    form = await request.form()
    mode = "register" if form.get("mode") == "register" else "signin"
    username = str(form.get("username") or "").strip()
    password = str(form.get("password") or "")

    # Double-submit CSRF: strict when we have issued a token, permissive for a
    # brand-new client that never loaded the form (nothing to double-submit).
    cookie_token = request.cookies.get(config.CSRF_COOKIE_NAME)
    if cookie_token and not csrf_token_is_valid(str(form.get("csrf_token") or "")):
        return render_signin(request, mode=mode, error=CSRF_FAILED, username=username, status_code=400)

    with SessionLocal() as db:
        if mode == "register":
            problem = validate_username(username) or validate_registration_password(password)
            if problem:
                return render_signin(request, mode=mode, error=problem, username=username, status_code=400)
            taken = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
            if taken is not None:
                return render_signin(
                    request,
                    mode=mode,
                    error="That username is already taken",
                    username=username,
                    status_code=409,
                )
            user = User(username=username, password_hash=hash_password(password))
            db.add(user)
            db.commit()
            db.refresh(user)
        else:
            user = authenticate(db, username, password)
            if user is None:
                return render_signin(
                    request,
                    mode=mode,
                    error=INVALID_CREDENTIALS,
                    username=username,
                    status_code=401,
                )

        response = RedirectResponse("/", status_code=303)
        issue_session_cookie(response, user.id)
        response.delete_cookie(config.CSRF_COOKIE_NAME, path="/")
        return response


@router.get("/logout")
def logout(request: Request):
    response = RedirectResponse("/login", status_code=303)
    clear_session_cookie(response)
    return response
