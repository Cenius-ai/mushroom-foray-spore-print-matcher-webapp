"""Runtime configuration for the Mushroom Foray Spore Print Matcher.

Every value has a working development default so a fresh clone boots with no
`.env` file present. `install.sh` writes a random `SESSION_SECRET` into `.env`
when one is missing, so real deployments never share the dev fallback.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# A `.env` written by install.sh (or copied from `.env.example`) is optional:
# every value below has a working default, so a bare clone boots with no env.
load_dotenv(Path(__file__).resolve().parent / ".env")

# --- service ---------------------------------------------------------------
HOST = "0.0.0.0"
DEFAULT_PORT = 7860  # the Gradio runner probes this port
PORT = int(os.getenv("PORT") or DEFAULT_PORT)

# --- secrets ---------------------------------------------------------------
# Dev fallback (sanctioned for a boot-with-no-env clone); install.sh replaces it.
DEV_SESSION_SECRET = "cenius-dev-8c41f0a7d35b62e9"
SESSION_SECRET = os.getenv("SESSION_SECRET") or DEV_SESSION_SECRET
COOKIE_NAME = "foray_session"
COOKIE_MAX_AGE_SECONDS = 14 * 24 * 60 * 60
CSRF_COOKIE_NAME = "foray_csrf"

# --- datastore -------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL") or "sqlite:///./foray.db"
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR") or (BASE_DIR / "uploads"))
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

# --- upload rules ----------------------------------------------------------
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_MIME = {"image/jpeg", "image/png"}
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG"}

# --- demo accounts (rendered verbatim on the sign-in card) -----------------
# The plan's demo credential, seeded alongside the platform's standard account.
DEMO_USERNAME = "cenius"
DEMO_EMAIL = "cenius@cenius.ai"
DEMO_PASSWORD = "cenius"

PLAN_DEMO_USERNAME = "demo"
PLAN_DEMO_EMAIL = "demo@cenius.ai"
PLAN_DEMO_PASSWORD = "demo1234"

# (username, email, password) for every seeded demo login.
DEMO_ACCOUNTS = (
    (DEMO_USERNAME, DEMO_EMAIL, DEMO_PASSWORD),
    (PLAN_DEMO_USERNAME, PLAN_DEMO_EMAIL, PLAN_DEMO_PASSWORD),
)

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 64
USERNAME_PATTERN = r"^[A-Za-z0-9_.-]{3,30}$"

# --- matcher / scoring limits ---------------------------------------------
CAP_MIN_MM, CAP_MAX_MM = 5.0, 300.0
GILL_MIN_MM, GILL_MAX_MM = 0.5, 30.0
HABITAT_MAX_CHARS = 120
SESSION_NAME_MAX_CHARS = 64
