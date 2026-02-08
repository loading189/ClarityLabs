from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.config import allow_business_delete, pilot_mode_enabled
from backend.app.api.deps import ROLE_ORDER, get_current_user, require_membership_dep
from backend.app.coa_templates import DEFAULT_COA
from backend.app.db import get_db
from backend.app.models import Account, Business, BusinessIntegrationProfile, BusinessMembership, Organization, User
from backend.app.services import business_service

router = APIRouter(prefix="/api/businesses", tags=["businesses"])


class BusinessCreateIn(BaseModel):
    name: str
    is_demo: bool = False
    external_id: Optional[str] = None
    slug: Optional[str] = None


class BusinessOut(BaseModel):
    id: str
    name: str
    org_id: str
    created_at: datetime
    is_demo: bool = False


class BusinessMembershipSummaryOut(BaseModel):
    business_id: str
    business_name: str
    role: str


class BusinessCreateOut(BaseModel):
    business: BusinessOut
    membership: BusinessMembershipSummaryOut


@router.post("", response_model=BusinessCreateOut)
def create_business(
    payload: BusinessCreateIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    org = db.execute(select(Organization).order_by(Organization.created_at.asc())).scalars().first()
    if not org:
        org = Organization(name="Default Organization")
        db.add(org)
        db.flush()

    biz = Business(
        org_id=org.id,
        name=payload.name.strip() or "New Business",
        created_at=datetime.now(timezone.utc),
    )
    db.add(biz)
    db.flush()

    for a in DEFAULT_COA:
        db.add(Account(business_id=biz.id, **a))
    db.add(BusinessIntegrationProfile(business_id=biz.id))
    db.add(
        BusinessMembership(
            business_id=biz.id,
            user_id=user.id,
            role="owner",
        )
    )
    db.commit()
    db.refresh(biz)

    business_out = BusinessOut(
        id=biz.id,
        name=biz.name,
        org_id=biz.org_id,
        created_at=biz.created_at,
        is_demo=payload.is_demo,
    )
    membership_out = BusinessMembershipSummaryOut(
        business_id=biz.id,
        business_name=biz.name,
        role="owner",
    )
    return BusinessCreateOut(business=business_out, membership=membership_out)


class BusinessJoinIn(BaseModel):
    role: Optional[str] = None


class BusinessJoinOut(BaseModel):
    business_id: str
    user_id: str
    role: str


@router.post("/{business_id}/join", response_model=BusinessJoinOut)
def join_business(
    business_id: str,
    payload: BusinessJoinIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not pilot_mode_enabled():
        raise HTTPException(status_code=404, detail="not found")

    role = "advisor"
    if payload.role:
        requested = payload.role.strip().lower()
        if requested not in ROLE_ORDER:
            raise HTTPException(status_code=400, detail="invalid role")
        role = requested

    existing = (
        db.execute(
            select(BusinessMembership).where(
                BusinessMembership.business_id == business_id,
                BusinessMembership.user_id == user.id,
            )
        )
        .scalars()
        .first()
    )
    if existing:
        return BusinessJoinOut(business_id=existing.business_id, user_id=existing.user_id, role=existing.role)

    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="business not found")

    membership = BusinessMembership(
        business_id=business_id,
        user_id=user.id,
        role=role,
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return BusinessJoinOut(business_id=membership.business_id, user_id=membership.user_id, role=membership.role)


@router.delete("/{business_id}")
def delete_business(
    business_id: str,
    confirm: bool = Query(default=False),
    db: Session = Depends(get_db),
    membership: BusinessMembership = Depends(require_membership_dep(min_role="owner")),
):
    if not allow_business_delete():
        raise HTTPException(status_code=403, detail="business delete not enabled")
    if not confirm:
        raise HTTPException(status_code=400, detail="confirm=true is required")
    if membership.business_id != business_id:
        raise HTTPException(status_code=403, detail="membership required")
    deleted = business_service.hard_delete_business(db, business_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="business not found")
    return {"deleted": True, "business_id": business_id}


@router.get("/mine", response_model=list[BusinessMembershipSummaryOut])
def list_my_businesses(
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
    return [
        BusinessMembershipSummaryOut(
            business_id=membership.business_id,
            business_name=business.name,
            role=membership.role,
        )
        for membership, business in rows
    ]


class BusinessMemberOut(BaseModel):
    id: str
    email: str
    name: Optional[str]
    role: str


@router.get("/{business_id}/members", response_model=list[BusinessMemberOut])
def list_business_members(
    business_id: str,
    db: Session = Depends(get_db),
    membership: BusinessMembership = Depends(require_membership_dep()),
):
    rows = (
        db.execute(
            select(BusinessMembership, User)
            .join(User, BusinessMembership.user_id == User.id)
            .where(BusinessMembership.business_id == business_id)
            .order_by(User.email.asc())
        )
        .all()
    )
    return [
        BusinessMemberOut(
            id=member.user_id,
            email=member_user.email,
            name=member_user.name,
            role=member.role,
        )
        for member, member_user in rows
    ]
