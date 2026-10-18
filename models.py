"""SQLAlchemy models: users, swatch classes, foray sessions and findings."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow_iso() -> str:
    """Timestamps are stored as UTC ISO-8601 text (SQLite friendly)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=utcnow_iso)

    sessions: Mapped[list["ForaySession"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )


class SwatchClass(Base):
    """One of six seeded spore-print colour classes with a persisted Lab centroid."""

    __tablename__ = "swatch_class"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    hex: Mapped[str] = mapped_column(String(7), nullable=False)
    lab_l: Mapped[float] = mapped_column(Float, nullable=False)
    lab_a: Mapped[float] = mapped_column(Float, nullable=False)
    lab_b: Mapped[float] = mapped_column(Float, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    findings: Mapped[list["Finding"]] = relationship(back_populates="swatch")


class ForaySession(Base):
    __tablename__ = "foray_session"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_foray_session_user_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=utcnow_iso)

    owner: Mapped[User] = relationship(back_populates="sessions")
    findings: Mapped[list["Finding"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class Finding(Base):
    __tablename__ = "finding"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("foray_session.id", ondelete="CASCADE"), nullable=False, index=True
    )
    swatch_class_id: Mapped[int] = mapped_column(
        ForeignKey("swatch_class.id"), nullable=False, index=True
    )
    image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    match_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    cap_diameter_mm: Mapped[float] = mapped_column(Float, nullable=False)
    gill_spacing: Mapped[float] = mapped_column(Float, nullable=False)
    warning_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_band: Mapped[str] = mapped_column(String(10), nullable=False)
    habitat: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default=utcnow_iso)

    session: Mapped[ForaySession] = relationship(back_populates="findings")
    swatch: Mapped[SwatchClass] = relationship(back_populates="findings")
