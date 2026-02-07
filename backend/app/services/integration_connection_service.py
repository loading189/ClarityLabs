from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from backend.app.models import IntegrationConnection


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def compute_connection_status(connection: IntegrationConnection) -> str:
    if connection.disconnected_at:
        return "disconnected"
    if not connection.is_enabled:
        return "disabled"
    if connection.last_error_at and (
        connection.last_success_at is None or connection.last_error_at > connection.last_success_at
    ):
        return "error"
    return "connected"


def refresh_connection_status(connection: IntegrationConnection) -> None:
    connection.status = compute_connection_status(connection)


def mark_sync_success(
    connection: IntegrationConnection,
    *,
    now: Optional[datetime] = None,
) -> None:
    now = now or utcnow()
    connection.last_sync_at = now
    connection.last_success_at = now
    connection.last_error = None
    connection.last_error_at = None
    refresh_connection_status(connection)


def mark_sync_error(
    connection: IntegrationConnection,
    *,
    error: str,
    now: Optional[datetime] = None,
) -> None:
    now = now or utcnow()
    connection.last_sync_at = now
    connection.last_error = error
    connection.last_error_at = now
    refresh_connection_status(connection)
