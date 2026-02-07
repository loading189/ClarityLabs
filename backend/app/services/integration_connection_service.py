from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import Business, IntegrationConnection


DEFAULT_PROVIDERS = ("plaid",)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _derive_status(conn: IntegrationConnection) -> str:
    if conn.disconnected_at:
        return "disconnected"
    if not conn.is_enabled:
        return "disabled"
    if conn.last_error_at and (conn.last_success_at is None or conn.last_error_at >= conn.last_success_at):
        return "error"
    return "connected"


def require_business(db: Session, business_id: str) -> Business:
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="business not found")
    return biz


def get_or_create_connection(db: Session, business_id: str, provider: str) -> IntegrationConnection:
    conn = db.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.business_id == business_id,
            IntegrationConnection.provider == provider,
        )
    ).scalar_one_or_none()
    if conn:
        return conn

    conn = IntegrationConnection(
        business_id=business_id,
        provider=provider,
        is_enabled=True,
        status="connected",
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    return conn


def list_connections(db: Session, business_id: str) -> List[IntegrationConnection]:
    require_business(db, business_id)
    existing = db.execute(
        select(IntegrationConnection).where(IntegrationConnection.business_id == business_id)
    ).scalars().all()
    existing_map = {c.provider: c for c in existing}

    for provider in DEFAULT_PROVIDERS:
        if provider not in existing_map:
            existing_map[provider] = get_or_create_connection(db, business_id, provider)

    return sorted(existing_map.values(), key=lambda c: c.provider)


def update_status(conn: IntegrationConnection) -> None:
    conn.status = _derive_status(conn)
    conn.updated_at = _now()


def mark_sync_success(conn: IntegrationConnection) -> None:
    now = _now()
    conn.last_sync_at = now
    conn.last_success_at = now
    conn.last_error_at = None
    conn.last_error = None
    update_status(conn)


def mark_sync_error(conn: IntegrationConnection, error: dict) -> None:
    now = _now()
    conn.last_sync_at = now
    conn.last_error_at = now
    conn.last_error = error
    update_status(conn)


def set_enabled(conn: IntegrationConnection, enabled: bool) -> None:
    conn.is_enabled = enabled
    if enabled and conn.disconnected_at:
        conn.disconnected_at = None
    update_status(conn)


def disconnect(conn: IntegrationConnection) -> None:
    conn.disconnected_at = _now()
    conn.is_enabled = False
    update_status(conn)
