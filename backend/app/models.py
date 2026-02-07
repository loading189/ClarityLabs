from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
    String,
    Text,
    text,
    Integer,
    Float,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db import Base

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.app.sim.models import SimulatorConfig, SimulatorRun



# -------------------------
# Helpers
# -------------------------

from datetime import timezone
# If you want real tz conversion later:
# from zoneinfo import ZoneInfo

def default_story() -> dict:
    return {
        "scenario_id": "restaurant_v1",
        "timezone": "America/Chicago",
        "hours": {"open_hour": 11, "close_hour": 22, "business_hours_only": True},
        "mix": {
            "bank": True,
            "payroll": True,
            "card_processor": True,
            "ecommerce": False,
            "invoicing": False,
        },
        "rhythm": {
            "lunch_peak": True,
            "dinner_peak": True,
            "weekend_boost": 1.2,
        },
        "payout_behavior": {"deposit_delay_days": [0, 1, 2]},
        "truth": {"shocks": [], "notes": ""},
    }

def default_simulation_params() -> dict:
    return {
        "volume_level": "medium",
        "volatility": "normal",
        "seasonality": False,
        "story": default_story(),
    }




def utcnow() -> datetime:
    return datetime.now(timezone.utc)



def uuid_str() -> str:
    return str(uuid.uuid4())


# -------------------------
# Core models
# -------------------------

class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    businesses = relationship(
        "Business",
        back_populates="org",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    org_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    industry: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    org = relationship("Organization", back_populates="businesses")

    accounts = relationship(
        "Account",
        back_populates="business",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    categories = relationship(
        "Category",
        back_populates="business",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # NOTE: RawEvent isn't ORM-related here (and doesn't need to be),
    # but its DB FK is now ondelete=CASCADE so deletes work.

    # Simulator tables (newer approach)
    sim_config = relationship(
        "SimulatorConfig",
        back_populates="business",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    sim_runs = relationship(
        "SimulatorRun",
        back_populates="business",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # Legacy simulator flags
    sim_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
        default=False,
    )
    sim_profile: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        server_default=text("'normal'"),
        default="normal",
    )

    integration_profile = relationship(
        "BusinessIntegrationProfile",
        back_populates="business",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    integration_connections = relationship(
        "IntegrationConnection",
        back_populates="business",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Account(Base):
    """
    Chart of Accounts item.
    type: asset | liability | equity | revenue | expense
    subtype: optional (cash, ar, ap, cogs, payroll, etc)
    """
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    business_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )

    code: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    subtype: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)

    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    business = relationship("Business", back_populates="accounts")

    # Optional quality-of-life: see which categories point at this account
    categories = relationship("Category", back_populates="account")


class RawEvent(Base):
    """
    Immutable vendor event log. This is your replayable truth.
    """
    __tablename__ = "raw_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)

    business_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )

    source: Mapped[str] = mapped_column(String(40), nullable=False)  # plaid/shopify/stripe/etc
    source_event_id: Mapped[str] = mapped_column(String(120), nullable=False)  # dedupe key

    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)

    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class HealthSignalState(Base):
    __tablename__ = "health_signal_states"

    business_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        primary_key=True,
    )
    signal_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    signal_type: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    fingerprint: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    severity: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    detected_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolution_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        Index("ix_health_signal_states_business_id", "business_id"),
    )


class MonitorRuntime(Base):
    __tablename__ = "monitor_runtime"

    business_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        primary_key=True,
    )
    last_pulse_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    newest_event_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    newest_event_source_event_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    __table_args__ = (
        Index("ix_monitor_runtime_business_id", "business_id"),
    )


# -------------------------
# Integration profile
# -------------------------

class BusinessIntegrationProfile(Base):
    __tablename__ = "business_integration_profiles"

    business_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        primary_key=True,
    )

    bank: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    payroll: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    card_processor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ecommerce: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    invoicing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    scenario_id: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default="restaurant_v1",
        server_default=text("'restaurant_v1'"),
        index=True,
    )

    story_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )


    simulation_params: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=default_simulation_params,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)

    business = relationship("Business", back_populates="integration_profile")


class IntegrationConnection(Base):
    __tablename__ = "integration_connections"
    __table_args__ = (
        UniqueConstraint("business_id", "provider", name="uq_integration_connection_business_provider"),
        Index("ix_integration_connections_business_id", "business_id"),
        Index("ix_integration_connections_provider", "provider"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    business_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="connected")
    connected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_cursor: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    last_cursor_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_webhook_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_ingest_counts: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    config_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    plaid_access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    plaid_item_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    plaid_environment: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )

    business = relationship("Business", back_populates="integration_connections")


class ProcessingEventState(Base):
    __tablename__ = "processing_event_states"
    __table_args__ = (
        Index("ix_processing_event_states_business_status", "business_id", "status"),
        Index("ix_processing_event_states_business_updated", "business_id", "updated_at"),
    )

    business_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        primary_key=True,
    )
    source_event_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ingested")
    normalized_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    error_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

class Category(Base):
    """
    Business-facing category list used in Categorize UI dropdown.
    MUST be anchored to COA via account_id.
    """
    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)

    business_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)

    # Legacy/optional. Do NOT rely on this for phase-2 mapping.
    system_key: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)

    account_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    business = relationship("Business", back_populates="categories")
    account = relationship("Account", back_populates="categories")

    mappings = relationship(
        "BusinessCategoryMap",
        back_populates="category",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class CategoryRule(Base):
    __tablename__ = "category_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)

    business_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    category_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    contains_text: Mapped[str] = mapped_column(String(120), nullable=False)
    direction: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # inflow/outflow
    account: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)

    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_run_updated_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    category = relationship("Category")


class TxnCategorization(Base):
    __tablename__ = "txn_categorizations"
    __table_args__ = (
        UniqueConstraint("business_id", "source_event_id", name="uq_txncat_business_sourceevent"),
        Index("ix_txncat_business_id", "business_id"),
        Index("ix_txncat_source_event_id", "source_event_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)

    business_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    source_event_id: Mapped[str] = mapped_column(String(120), nullable=False)

    category_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    source: Mapped[str] = mapped_column(String(30), default="manual", nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    category = relationship("Category")


class AuditLog(Base):
    """
    Append-only audit log for categorization workflow changes.
    """
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_business_id", "business_id"),
        Index("ix_audit_logs_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)

    business_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )

    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    actor: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    source_event_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    rule_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)

    before_state: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    after_state: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class AssistantMessage(Base):
    __tablename__ = "assistant_messages"
    __table_args__ = (
        Index("ix_assistant_messages_business_created", "business_id", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    business_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    author: Mapped[str] = mapped_column(String(20), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    signal_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    audit_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)


class SystemCategory(Base):
    """
    Optional curated set of system keys. Keep for UI/reference.
    Do NOT FK constrain BusinessCategoryMap.system_key during iteration.
    """
    __tablename__ = "system_categories"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    group: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)


class BusinessCategoryMap(Base):
    """
    Per business mapping: system_key -> category_id
    """
    __tablename__ = "business_category_map"
    __table_args__ = (
        UniqueConstraint("business_id", "system_key", name="uq_business_system_key"),
        UniqueConstraint("business_id", "category_id", name="uq_business_category_id"),
        Index("ix_bcm_business_id", "business_id"),
        Index("ix_bcm_system_key", "system_key"),
        Index("ix_bcm_category_id", "category_id"),
    )


    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)

    business_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ✅ No FK: prevents system_key FK violations during iteration/seeding
    system_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    category_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    is_default: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
        default=True,
    )

    category = relationship("Category", back_populates="mappings")


class VendorCategoryMap(Base):
    __tablename__ = "vendor_category_map"
    __table_args__ = (
        UniqueConstraint("business_id", "vendor_key", name="uq_vendor_category_map_business_vendor"),
        Index("ix_vendor_category_map_business_id", "business_id"),
        Index("ix_vendor_category_map_vendor_key", "vendor_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    business_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
    )
    vendor_key: Mapped[str] = mapped_column(String(160), nullable=False)
    category_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("categories.id", ondelete="CASCADE"),
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    category = relationship("Category")
