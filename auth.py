"""Password hashing, signed session cookies and the ownership chokepoint.

Session and CSRF cookies use an explicit HMAC-SHA256 signature over a base64url
payload. Verification and parsing are two separate, visible steps: the signature
is compared in constant time, then the payload is parsed as JSON by a dedicated
``json.JSONDecoder`` — no generic object deserializer is involved anywhere.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import secrets
import time

import bcrypt
from fastapi import HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

import config
from models import ForaySession, User

BCRYPT_ROUNDS = 12

_SECRET_BYTES = config.SESSION_SECRET.encode("utf-8")
# A JSON-only parser: this app never round-trips Python objects through a cookie.
_JSON_DECODER = json.JSONDecoder()


# --- password hashing ------------------------------------------------------
def hash_password(password: str) -> str:
    """bcrypt with a per-password salt; the only hashing path in the app."""
    payload = password[:_truncate_limit()].encode("utf-8")
    return bcrypt.hashpw(payload, bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            password[:_truncate_limit()].encode("utf-8"), password_hash.encode("utf-8")
        )
    except (ValueError, TypeError):
        # A malformed stored hash can never authenticate anyone, and it must not
        # surface as a 500 to the caller.
        return False


def _truncate_limit() -> int:
    # bcrypt ignores bytes past 72; registration caps length well below that.
    return 72


# --- signed tokens ---------------------------------------------------------
def _signature(payload: str) -> str:
    return hmac.new(_SECRET_BYTES, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _encode_body(body: dict) -> str:
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _parse_body(payload: str) -> dict | None:
    padded = payload + "=" * (-len(payload) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        text = raw.decode("utf-8")
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None
    try:
        body = _JSON_DECODER.decode(text)
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


def _signed_token(body: dict) -> str:
    payload = _encode_body(body)
    return f"{payload}.{_signature(payload)}"


def _read_token(token: str | None, max_age: int) -> dict | None:
    """Constant-time signature check, then a JSON parse, then the age check."""
    if not token or not isinstance(token, str) or token.count(".") != 1:
        return None
    payload, supplied_signature = token.split(".", 1)
    if not hmac.compare_digest(_signature(payload), supplied_signature):
        return None
    body = _parse_body(payload)
    if body is None:
        return None
    issued_at = body.get("iat")
    if not isinstance(issued_at, int) or time.time() - issued_at > max_age:
        return None
    return body


def issue_session_token(user_id: int) -> str:
    return _signed_token(
        {"uid": user_id, "iat": int(time.time()), "nonce": secrets.token_hex(8)}
    )


def issue_csrf_token() -> str:
    return _signed_token({"purpose": "csrf", "iat": int(time.time()), "nonce": secrets.token_hex(16)})


def csrf_token_for() -> str:
    return issue_csrf_token()


def csrf_token_is_valid(token: str | None) -> bool:
    body = _read_token(token, max_age=60 * 60 * 12)
    return bool(body) and body.get("purpose") == "csrf"


def user_id_from_cookie_token(token: str | None) -> int | None:
    body = _read_token(token, max_age=config.COOKIE_MAX_AGE_SECONDS)
    if body is None:
        return None
    user_id = body.get("uid")
    return user_id if isinstance(user_id, int) else None


# --- validation ------------------------------------------------------------
def validate_username(username: str) -> str | None:
    if not username or not username.strip():
        return "Username is required"
    if not re.match(config.USERNAME_PATTERN, username.strip()):
        return "Username must be 3-30 characters: letters, numbers, dot, dash or underscore"
    return None


def validate_registration_password(password: str) -> str | None:
    if not password:
        return "Password is required"
    if len(password) < config.MIN_PASSWORD_LENGTH:
        return f"Password must be at least {config.MIN_PASSWORD_LENGTH} characters"
    if len(password) > config.MAX_PASSWORD_LENGTH:
        return f"Password must be at most {config.MAX_PASSWORD_LENGTH} characters"
    return None


# --- cookie plumbing -------------------------------------------------------
def issue_session_cookie(response: Response, user_id: int) -> None:
    response.set_cookie(
        key=config.COOKIE_NAME,
        value=issue_session_token(user_id),
        max_age=config.COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        # The preview and local runs are plain HTTP: a Secure cookie would be
        # silently dropped and every page would re-wall.
        secure=False,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(config.COOKIE_NAME, path="/")


def user_from_request(request: Request | object, db: Session) -> User | None:
    """Resolve the signed-in user from the request cookie (never from the body)."""
    cookies = getattr(request, "cookies", None)
    if not cookies:
        return None
    try:
        token = dict(cookies).get(config.COOKIE_NAME)
    except (TypeError, ValueError):
        return None
    user_id = user_id_from_cookie_token(token)
    if user_id is None:
        return None
    return db.get(User, user_id)


def require_user(request: Request, db: Session) -> User:
    user = user_from_request(request, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Not signed in")
    return user


def owned_session(db: Session, user_id: int, session_id: int) -> ForaySession:
    """Single chokepoint: unknown *or* foreign sessions both 404."""
    row = db.execute(
        select(ForaySession).where(
            ForaySession.id == session_id, ForaySession.user_id == user_id
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Foray session not found")
    return row


def authenticate(db: Session, identifier: str, password: str) -> User | None:
    """One lookup by username or email; failures are indistinguishable upstream."""
    identifier = (identifier or "").strip()
    if not identifier or not password:
        return None
    user = db.execute(select(User).where(User.username == identifier)).scalar_one_or_none()
    if user is None:
        user = db.execute(select(User).where(User.email == identifier)).scalar_one_or_none()
    if user is None:
        # Spend a comparable amount of time so timing does not enumerate users.
        bcrypt.hashpw(b"timing-equaliser", bcrypt.gensalt(rounds=BCRYPT_ROUNDS))
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user
