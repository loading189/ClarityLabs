from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.orm import Session

from backend.app.models import (
    AssistantMessage,
    AuditLog,
    Business,
    BusinessCategoryMap,
    BusinessIntegrationProfile,
    Category,
    CategoryRule,
    HealthSignalState,
    MonitorRuntime,
    RawEvent,
    TxnCategorization,
    Account,
)


def hard_delete_business(db: Session, business_id: str) -> bool:
    biz = db.get(Business, business_id)
    if not biz:
        return False

    db.execute(delete(AssistantMessage).where(AssistantMessage.business_id == business_id))
    db.execute(delete(HealthSignalState).where(HealthSignalState.business_id == business_id))
    db.execute(delete(AuditLog).where(AuditLog.business_id == business_id))
    db.execute(delete(MonitorRuntime).where(MonitorRuntime.business_id == business_id))
    db.execute(delete(TxnCategorization).where(TxnCategorization.business_id == business_id))
    db.execute(delete(CategoryRule).where(CategoryRule.business_id == business_id))
    db.execute(delete(BusinessCategoryMap).where(BusinessCategoryMap.business_id == business_id))
    db.execute(delete(Category).where(Category.business_id == business_id))
    db.execute(delete(Account).where(Account.business_id == business_id))
    db.execute(delete(RawEvent).where(RawEvent.business_id == business_id))
    db.execute(delete(BusinessIntegrationProfile).where(BusinessIntegrationProfile.business_id == business_id))

    db.delete(biz)
    db.commit()
    return True
