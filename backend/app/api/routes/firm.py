from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user
from backend.app.db import get_db
from backend.app.models import User
from backend.app.services.firm_overview_service import get_firm_overview_for_user


router = APIRouter(prefix="/api/firm", tags=["firm"])


@router.get("/overview")
def firm_overview(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return get_firm_overview_for_user(user.id, db)
