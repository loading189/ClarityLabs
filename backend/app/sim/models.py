from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    JSON,
    Index,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def uuid_str() -> str:
    return str(uuid.uuid4())


class SimulatorConfig(Base):
    """
    One row per business. This is the scheduler + tuning knobs for the live simulator.

    Key idea:
    - Your engine loop queries rows where enabled=1 and next_emit_at <= now.
    - It emits some events, then advances next_emit_at.
    """
    __tablename__ = "simulator_configs"
    __table_args__ = (
        Index("ix_simcfg_enabled_nextemit", "enabled", "next_emit_at"),
        Index("ix_simcfg_business_id", "business_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)

    business_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # master on/off
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # legacy-ish profile for “simple presets” (your PROFILES map)
    profile: Mapped[str] = mapped_column(String(40), nullable=False, default="normal")

    # baseline pacing knobs
    avg_events_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    typical_ticket_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=6500)
    payroll_every_n_days: Mapped[int] = mapped_column(Integer, nullable=False, default=14)

    # --- Live engine scheduling ---
    # When should the next emission happen?
    next_emit_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        index=True,
    )

    # When did we last emit? (helps debugging / UI)
    last_emit_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Safety cap: if engine is paused then resumed, avoid generating millions instantly
    max_backfill_events: Mapped[int] = mapped_column(Integer, nullable=False, default=250)

    # Deterministic-ish randomness per business
    seed: Mapped[int] = mapped_column(Integer, nullable=False, default=1337)

    # --- Concurrency lock (optional but best practice) ---
    # If you ever run multiple uvicorn workers / processes, this prevents double-emission.
    lock_owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lock_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    business = relationship("Business", back_populates="sim_config")


class SimulatorRun(Base):
    """
    Optional audit trail: when you run a big history seed or change story version,
    you can log it here.
    """
    __tablename__ = "simulator_runs"
    __table_args__ = (
        Index("ix_simrun_business_started", "business_id", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)

    business_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    kind: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default=text("'manual'"),
        default="manual",  # e.g., "history_seed", "story_change", "manual"
    )

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    # Anything you want to record for reproducibility (days, shocks, params snapshot, etc.)
    params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    business = relationship("Business", back_populates="sim_runs")
