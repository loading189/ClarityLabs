from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.api.deps import require_membership_dep
from backend.app.db import get_db
from backend.app.models import ActionItem, HealthSignalState, IntegrationConnection
from backend.app.services import ledger_service, monitoring_service
from backend.app.services.actions_service import generate_actions_for_business
from backend.app.services.dev_tools import require_dev_tools
from backend.app.services.plaid_dev_service import ensure_dynamic_item, pump_sandbox_transactions, require_plaid_sandbox_config
from backend.app.services.plaid_sync_service import run_plaid_sync


router = APIRouter(prefix="/api/dev/plaid", tags=["dev"])


class EnsureDynamicItemIn(BaseModel):
    force_recreate: bool = False


class EnsureDynamicItemOut(BaseModel):
    business_id: str
    provider: str
    item_id: str
    status: str


class PumpTransactionsIn(BaseModel):
    start_date: date
    end_date: date
    daily_txn_count: int = Field(default=25, ge=1, le=200)
    profile: Literal["retail", "services", "ecom", "mixed"] = "mixed"
    run_sync: bool = True
    run_pipeline: bool = True
    refresh_actions: bool = True


@router.post("/{business_id}/ensure_dynamic_item", response_model=EnsureDynamicItemOut, dependencies=[Depends(require_membership_dep(min_role="staff"))])
def ensure_dynamic_item_endpoint(
    business_id: str,
    req: EnsureDynamicItemIn,
    db: Session = Depends(get_db),
):
    require_dev_tools()
    require_plaid_sandbox_config()
    row = ensure_dynamic_item(db, business_id, force_recreate=req.force_recreate)
    db.commit()
    return EnsureDynamicItemOut(
        business_id=business_id,
        provider="plaid",
        item_id=row.plaid_item_id or "",
        status="ready",
    )


@router.post("/{business_id}/pump_transactions", dependencies=[Depends(require_membership_dep(min_role="staff"))])
def pump_transactions_endpoint(
    business_id: str,
    req: PumpTransactionsIn,
    db: Session = Depends(get_db),
):
    require_dev_tools()
    require_plaid_sandbox_config()
    connection = db.execute(
        select(IntegrationConnection).where(
            IntegrationConnection.business_id == business_id,
            IntegrationConnection.provider == "plaid",
        )
    ).scalar_one_or_none()
    if not connection or not connection.plaid_access_token:
        raise HTTPException(
            400,
            "Plaid connection not found. Use /integrations/plaid/link_token + /integrations/plaid/exchange or /api/dev/plaid/{business_id}/ensure_dynamic_item.",
        )

    pump = pump_sandbox_transactions(
        connection=connection,
        business_id=business_id,
        start_date=req.start_date,
        end_date=req.end_date,
        daily_txn_count=req.daily_txn_count,
        profile=req.profile,
    )

    sync_payload = None
    if req.run_sync:
        sync_payload = run_plaid_sync(db, business_id)

    pipeline_payload = None
    if req.run_pipeline:
        pulse = monitoring_service.pulse(db, business_id, force_run=True)
        pipeline_payload = {
            "ledger_rows": len(ledger_service.ledger_lines(db, business_id, start_date=None, end_date=None, limit=5000)),
            "signals_open_count": int(
                db.execute(
                    select(func.count())
                    .select_from(HealthSignalState)
                    .where(HealthSignalState.business_id == business_id, HealthSignalState.status == "open")
                ).scalar_one()
            ),
            "pulse": pulse,
        }

    actions_payload = None
    if req.refresh_actions:
        result = generate_actions_for_business(db, business_id)
        actions_payload = {
            "created_count": result.created_count,
            "updated_count": result.updated_count,
            "suppressed_count": result.suppressed_count,
            "suppression_reasons": result.suppression_reasons,
            "open_count": int(
                db.execute(
                    select(func.count())
                    .select_from(ActionItem)
                    .where(ActionItem.business_id == business_id, ActionItem.status == "open")
                ).scalar_one()
            ),
        }

    db.commit()
    return {
        "business_id": business_id,
        "date_range": {
            "start_date": req.start_date.isoformat(),
            "end_date": req.end_date.isoformat(),
        },
        "seed_key": pump.seed_key,
        "txns_requested": pump.requested,
        "txns_created": pump.created,
        "sync": {
            "new": (sync_payload or {}).get("inserted", 0),
            "updated": 0,
            "removed": 0,
            "cursor": (sync_payload or {}).get("cursor"),
        }
        if req.run_sync
        else None,
        "pipeline": pipeline_payload,
        "actions": actions_payload,
    }
