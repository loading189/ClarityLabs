# backend/app/api/deps.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Callable

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db import get_db
from backend.app.models import Business, BusinessMembership, User

ROLE_ORDER = {
    "viewer": 1,
    "staff": 2,
    "advisor": 3,
    "owner": 4,
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """
    Dev/pilot auth dependency.

    Reads identity from headers:
      - X-User-Email (preferred; will auto-provision user record if missing)
      - X-User-Id    (fallback; must already exist)

    NOTE:
    - This is intentionally simple for pilots; we can swap to real auth later.
    - db must be injected via Depends(get_db) so FastAPI doesn't treat Session
      as a Pydantic field (which would crash app startup).
    """
    email = request.headers.get("X-User-Email")
    user_id = request.headers.get("X-User-Id")
    if not email and not user_id:
        raise HTTPException(status_code=401, detail="Missing X-User-Email or X-User-Id header")

    if email:
        normalized = email.strip().lower()
        if not normalized:
            raise HTTPException(status_code=401, detail="Invalid X-User-Email header")

        user = db.execute(select(User).where(User.email == normalized)).scalars().first()
        if not user:
            user = User(
                email=normalized,
                name=normalized.split("@")[0],
                created_at=utcnow(),
                updated_at=utcnow(),
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        return user

    # If using X-User-Id, we expect the user to exist already.
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Unknown X-User-Id")
    return user


def require_business(db: Session, business_id: str) -> Business:
    biz = db.get(Business, business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="business not found")
    return biz


def require_membership(
    db: Session,
    business_id: str,
    user: User,
    *,
    min_role: str = "viewer",
) -> BusinessMembership:
    """
    Imperative membership check. Safe to call from inside endpoints/services.

    If you want a dependency version (so you don't have to manually call this),
    use require_membership_dep(...) below.
    """
    require_business(db, business_id)
    membership = (
        db.execute(
            select(BusinessMembership).where(
                BusinessMembership.business_id == business_id,
                BusinessMembership.user_id == user.id,
            )
        )
        .scalars()
        .first()
    )
    if not membership:
        raise HTTPException(status_code=403, detail="membership required")

    min_rank = ROLE_ORDER.get(min_role, 0)
    member_rank = ROLE_ORDER.get(membership.role or "", 0)
    if member_rank < min_rank:
        raise HTTPException(status_code=403, detail="insufficient role")
    return membership


def role_at_least(membership: BusinessMembership, min_role: str) -> bool:
    min_rank = ROLE_ORDER.get(min_role, 0)
    member_rank = ROLE_ORDER.get(membership.role or "", 0)
    return member_rank >= min_rank


def require_membership_dep(min_role: str = "viewer") -> Callable[..., BusinessMembership]:
    """
    FastAPI dependency factory that returns a BusinessMembership.

    Usage:
      @router.get("/business/{business_id}/something")
      def something(
          business_id: str,
          membership: BusinessMembership = Depends(require_membership_dep("advisor")),
          db: Session = Depends(get_db),
      ):
          ...

    This avoids repeating require_membership(db, business_id, user) in every endpoint.
    Keep using the imperative require_membership() if you prefer that style.
    """
    def _dep(
        business_id: str,
        db: Session = Depends(get_db),
        user: User = Depends(get_current_user),
    ) -> BusinessMembership:
        return require_membership(db, business_id, user, min_role=min_role)

    return _dep
