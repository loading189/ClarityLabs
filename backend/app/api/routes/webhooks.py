from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.integrations import get_adapter
from backend.app.integrations.shopify_stub import parse_body as parse_shopify_body
from backend.app.integrations.stripe_stub import parse_body as parse_stripe_body
from backend.app.services.ingest_orchestrator import process_ingested_events


router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def _extract_business_id(payload: dict) -> str:
    for key in ("business_id", "businessId"):
        value = payload.get(key)
        if value:
            return str(value)
    data = payload.get("data") or {}
    if isinstance(data, dict):
        meta = data.get("metadata") or {}
        for key in ("business_id", "businessId"):
            value = meta.get(key)
            if value:
                return str(value)
    raise HTTPException(status_code=400, detail="business_id required in webhook payload")


@router.post("/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    adapter = get_adapter("stripe")
    verification = adapter.verify_webhook(dict(request.headers), body)
    if not verification.ok:
        raise HTTPException(status_code=400, detail=f"webhook verification failed: {verification.reason}")
    payload = parse_stripe_body(body)
    business_id = _extract_business_id(payload)
    result = adapter.ingest_webhook_event(business_id=business_id, payload=payload, db=db)
    db.flush()
    ingest_processed = process_ingested_events(
        db,
        business_id=business_id,
        source_event_ids=list(result.source_event_ids),
    )
    return {
        "ok": True,
        "provider": "stripe",
        "inserted": result.inserted_count,
        "skipped": result.skipped_count,
        "ingest_processed": ingest_processed,
    }


@router.post("/shopify")
async def shopify_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    adapter = get_adapter("shopify")
    verification = adapter.verify_webhook(dict(request.headers), body)
    if not verification.ok:
        raise HTTPException(status_code=400, detail=f"webhook verification failed: {verification.reason}")
    payload = parse_shopify_body(body)
    business_id = _extract_business_id(payload)
    result = adapter.ingest_webhook_event(business_id=business_id, payload=payload, db=db)
    db.flush()
    ingest_processed = process_ingested_events(
        db,
        business_id=business_id,
        source_event_ids=list(result.source_event_ids),
    )
    return {
        "ok": True,
        "provider": "shopify",
        "inserted": result.inserted_count,
        "skipped": result.skipped_count,
        "ingest_processed": ingest_processed,
    }
