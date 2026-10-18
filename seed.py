"""Idempotent demo seed: six swatch classes, the demo account, foray sessions.

Run standalone with ``python3 seed.py`` (it seeds and exits; it never binds the
HTTP port). The same function runs on the normal boot path via ``db.init_db``.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone

from PIL import Image, ImageDraw
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import config
import color as colour
import scoring
from auth import hash_password
from db import session_scope
from models import Finding, ForaySession, SwatchClass, User

PAPER_RGB = (247, 245, 239)

# name, hex, short field description
SWATCH_SEED: list[tuple[str, str, str]] = [
    ("White", "#F6F3EA", "Chalk-white print, often on a pale gill edge; common in Amanita and Tricholoma."),
    ("Cream", "#EDE0B8", "Warm ivory print typical of Boletus and Leccinum; reads as paper until it dries."),
    ("Pale Pink", "#E9C6C8", "Blush-pink print seen in Entoloma and Pluteus; the pink deepens with age."),
    ("Salmon", "#DD8A6E", "Coral-salmon print from Cortinarius and some Agaricus; the warmest of the six."),
    ("Ochre", "#B77B2E", "Golden-ochre print of Cortinarius and Inocybe; a rusty tone that darkens as it oxidises."),
    ("Dark Brown", "#4A2E1C", "Deep chocolate print of Agaricus and Psilocybe; almost black in a thick deposit."),
]

# session name, note shown in the session rail
SESSION_SEED: list[tuple[str, str]] = [
    ("Autumn ridge foray — 12 October", "Morning transect across the sandstone ridge with the Tuesday group."),
    ("Late-summer beech transect", "Short evening loop through the beech hanger with two club members."),
]

# session index, swatch name, habitat, cap_mm, gill_mm, days_ago, tint jitter (0-1)
FINDING_SEED: list[tuple[int, str, str, float, float, int, float]] = [
    (0, "Cream", "Mossy oak ridge under Quercus robur", 210, 1.2, 12, 0.06),
    (0, "Dark Brown", "Pine duff under Scots pine", 250, 2.0, 12, 0.30),
    (0, "Ochre", "Bracken slope below the crag", 180, 3.0, 11, 0.10),
    (0, "Salmon", "Mixed hazel coppice edge", 120, 4.0, 10, 0.22),
    (0, "Pale Pink", "Beech leaf litter by the ride", 90, 5.0, 10, 0.26),
    (0, "White", "Limestone grassland verge", 140, 6.0, 9, 0.18),
    (0, "White", "Willow carr by the stream", 45, 9.0, 9, 0.06),
    (0, "Cream", "Damp birch hollow", 70, 12.0, 8, 0.32),
    (1, "Salmon", "Warm beech hanger, north-facing", 110, 4.5, 34, 0.14),
    (1, "Pale Pink", "Beech litter under a mossy log", 60, 7.0, 33, 0.28),
    (1, "Dark Brown", "Rotting stump on the ride", 165, 2.6, 31, 0.10),
]

SAMPLE_IMAGE_NAME = "sample_spore_print.png"
SAMPLE_HEX = "#EDE0B8"


def _tint_rgb(hex_colour: str, jitter: float, rng: random.Random) -> tuple[int, int, int]:
    """Shift a swatch colour slightly so seeded prints have realistic variety.

    The shift is dominated by one luminance offset plus a little per-channel
    noise, which keeps the print inside its own swatch class while varying
    delta-E (and therefore confidence) between finds.
    """
    base = colour.hex_to_rgb(hex_colour)
    offset = rng.uniform(-jitter, jitter) * 170.0
    shifted = []
    for channel in base:
        noise = rng.uniform(-0.4, 0.4) * jitter * 90.0
        shifted.append(max(0, min(255, round(channel + offset + noise))))
    return tuple(shifted)  # type: ignore[return-value]


def render_spore_print(path, print_rgb: tuple[int, int, int], seed_value: int) -> None:
    """Draw a deterministic spore-print photo: a dense deposit on pale paper.

    The deposit is a solid, slightly irregular disc (like a real print taken on a
    card) with speckle texture, a fuzzy rim and a faint gill impression - enough
    for the dominant-colour extractor to recover the pigment unambiguously.
    """
    rng = random.Random(seed_value)
    size = 320
    image = Image.new("RGB", (size, size), PAPER_RGB)
    draw = ImageDraw.Draw(image, "RGBA")
    centre = (size / 2, size / 2)
    radius = size * 0.33

    outline = []
    for step in range(60):
        angle = step * (2 * math.pi / 60)
        wobble = radius * (0.9 + 0.14 * rng.random())
        outline.append(
            (centre[0] + wobble * math.cos(angle), centre[1] + wobble * math.sin(angle))
        )
    draw.polygon(outline, fill=(print_rgb[0], print_rgb[1], print_rgb[2], 252))

    for _ in range(2400):  # spore speckle inside the deposit
        angle = rng.uniform(0, 2 * math.pi)
        distance = radius * (rng.random() ** 0.5) * 0.97
        x = centre[0] + distance * math.cos(angle)
        y = centre[1] + distance * math.sin(angle)
        shade = rng.randint(-12, 12)
        dot = rng.uniform(0.6, 1.9)
        draw.ellipse(
            [x - dot, y - dot, x + dot, y + dot],
            fill=(
                max(0, min(255, print_rgb[0] + shade)),
                max(0, min(255, print_rgb[1] + shade)),
                max(0, min(255, print_rgb[2] + shade)),
                80,
            ),
        )

    for _ in range(1400):  # fuzzy rim just outside the disc
        angle = rng.uniform(0, 2 * math.pi)
        distance = radius * rng.uniform(0.97, 1.2)
        x = centre[0] + distance * math.cos(angle)
        y = centre[1] + distance * math.sin(angle)
        dot = rng.uniform(0.8, 2.4)
        alpha = int(rng.uniform(60, 190))
        draw.ellipse(
            [x - dot, y - dot, x + dot, y + dot],
            fill=(print_rgb[0], print_rgb[1], print_rgb[2], alpha),
        )

    for step in range(-8, 9):  # faint radial gill impression across the deposit
        offset = step * (radius * 0.12)
        draw.line(
            [(centre[0] + offset, centre[1] - radius), (centre[0] + offset, centre[1] + radius)],
            fill=(max(0, print_rgb[0] - 18), max(0, print_rgb[1] - 18), max(0, print_rgb[2] - 18), 45),
            width=1,
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")


def seed_swatches(db: Session) -> dict[str, SwatchClass]:
    """Insert or refresh the six classes, always via `colour.srgb_to_lab`."""
    rows: dict[str, SwatchClass] = {}
    for name, hex_colour, description in SWATCH_SEED:
        lab_l, lab_a, lab_b = colour.hex_to_lab(hex_colour)
        row = db.execute(select(SwatchClass).where(SwatchClass.name == name)).scalar_one_or_none()
        if row is None:
            row = SwatchClass(
                name=name,
                hex=hex_colour,
                lab_l=lab_l,
                lab_a=lab_a,
                lab_b=lab_b,
                description=description,
            )
            db.add(row)
        else:
            row.hex = hex_colour
            row.lab_l, row.lab_a, row.lab_b = lab_l, lab_a, lab_b
            row.description = description
        rows[name] = row
    db.flush()
    return rows


def seed_user(db: Session, username: str, email: str, password: str) -> User:
    """Create one demo login through the app's own bcrypt path (idempotent)."""
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    if user is None:
        user = User(username=username, email=email, password_hash=hash_password(password))
        db.add(user)
        db.flush()
    elif not user.email:
        user.email = email
    return user


def seed_demo_user(db: Session) -> User:
    return seed_user(db, config.DEMO_USERNAME, config.DEMO_EMAIL, config.DEMO_PASSWORD)


def _seed_session(db: Session, user: User, name: str) -> ForaySession:
    row = db.execute(
        select(ForaySession).where(ForaySession.user_id == user.id, ForaySession.name == name)
    ).scalar_one_or_none()
    if row is None:
        row = ForaySession(user_id=user.id, name=name)
        db.add(row)
        db.flush()
    return row


def _seed_findings_for(db: Session, user: User, swatches: dict[str, SwatchClass]) -> None:
    """Give one demo account its own copy of the foray sessions and finds."""
    sessions = [_seed_session(db, user, name) for name, _note in SESSION_SEED]
    db.flush()

    existing = db.execute(
        select(func.count(Finding.id))
        .join(ForaySession, ForaySession.id == Finding.session_id)
        .where(ForaySession.user_id == user.id)
    ).scalar_one()
    if existing:
        return

    now = datetime.now(timezone.utc).replace(microsecond=0)
    for index, (session_index, swatch_name, habitat, cap_mm, gill_mm, days_ago, jitter) in enumerate(
        FINDING_SEED
    ):
        rng = random.Random(1000 + index)
        print_rgb = _tint_rgb(swatches[swatch_name].hex, jitter, rng)
        filename = f"seed_find_{index + 1:02d}.png"
        image_path = config.UPLOAD_DIR / filename
        if not image_path.exists():
            render_spore_print(image_path, print_rgb, seed_value=7000 + index)

        # Classify the generated print through the runtime path so the stored
        # confidence agrees with what the Matcher would report for the photo.
        image = colour.decode_image_bytes(image_path.read_bytes())
        lab_query = colour.srgb_to_lab(*colour.dominant_colour(image))
        swatch_row, delta_e = colour.nearest_swatch(lab_query, swatches.values())
        confidence = colour.confidence_from_delta_e(delta_e)
        score = scoring.score_find(cap_mm, gill_mm)

        created = now - timedelta(days=days_ago, hours=(index * 3) % 9)
        db.add(
            Finding(
                session_id=sessions[session_index].id,
                swatch_class_id=swatch_row.id,
                image_path=f"uploads/{filename}",
                match_confidence=confidence,
                cap_diameter_mm=cap_mm,
                gill_spacing=gill_mm,
                warning_score=score.score,
                risk_band=score.risk_band,
                habitat=habitat,
                created_at=created.isoformat(),
            )
        )
    db.flush()


def seed_demo_data(db: Session) -> None:
    """Six swatch classes plus every demo account with its own foray history."""
    swatches = seed_swatches(db)
    for username, email, password in config.DEMO_ACCOUNTS:
        user = seed_user(db, username, email, password)
        _seed_findings_for(db, user, swatches)


def seed_sample_image() -> str:
    """The Matcher's pre-loaded reference print (rendered once, deterministic)."""
    path = config.STATIC_DIR / SAMPLE_IMAGE_NAME
    if not path.exists():
        render_spore_print(path, colour.hex_to_rgb(SAMPLE_HEX), seed_value=4242)
    return str(path)


def seed_all() -> None:
    with session_scope() as db:
        seed_demo_data(db)
    seed_sample_image()


if __name__ == "__main__":
    from db import init_db

    init_db(seed=True)
    print(
        "Seed complete: 6 swatch classes, demo accounts "
        + ", ".join(f"{name}/{password}" for name, _email, password in config.DEMO_ACCOUNTS)
        + ", foray sessions and findings are in place."
    )
