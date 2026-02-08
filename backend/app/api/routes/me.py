from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user
from backend.app.db import get_db
from backend.app.models import Business, BusinessMembership, User


router = APIRouter(prefix="/api", tags=["users"])


class MembershipOut(BaseModel):
    business_id: str
    business_name: str
    role: str


class MeOut(BaseModel):
    id: str
    email: str
    name: Optional[str]
    memberships: list[MembershipOut]


@router.get("/me", response_model=MeOut)
def get_me(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = (
        db.execute(
            select(BusinessMembership, Business)
            .join(Business, BusinessMembership.business_id == Business.id)
            .where(BusinessMembership.user_id == user.id)
            .order_by(Business.created_at.desc())
        )
        .all()
    )
    memberships = [
        MembershipOut(
            business_id=membership.business_id,
            business_name=business.name,
            role=membership.role,
        )
        for membership, business in rows
    ]
    return MeOut(id=user.id, email=user.email, name=user.name, memberships=memberships)
