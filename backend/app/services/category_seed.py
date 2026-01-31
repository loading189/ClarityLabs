from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Dict, Tuple, Optional, List

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from backend.app.models import Account, Category, BusinessCategoryMap
from backend.app.coa_templates import DEFAULT_COA


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def uuid_str() -> str:
    return str(uuid.uuid4())


# subtype -> (system_key, default_category_name)
SUBTYPE_TO_SYSTEM: Dict[str, Tuple[str, str]] = {
    "payroll": ("payroll", "Payroll"),
    "rent": ("rent", "Rent"),
    "utilities": ("utilities", "Utilities"),
    "software": ("software", "Software & Subscriptions"),
    "marketing": ("marketing", "Marketing & Advertising"),
    "hosting": ("hosting", "Hosting / Infrastructure"),
    "insurance": ("insurance", "Insurance"),
    "office_supplies": ("office_supplies", "Office Supplies"),
    "meals": ("meals", "Meals & Entertainment"),
    "travel": ("travel", "Travel"),
    "taxes": ("taxes", "Taxes & Licenses"),
    "cogs": ("cogs", "Cost of Goods Sold"),
    "sales": ("sales", "Sales Revenue"),
    "service": ("sales", "Service Revenue"),  # optional: treat service as sales/revenue bucket
    "contra": ("contra", "Refunds / Contra Revenue"),
    "draw": ("owner_draw", "Owner Draw"),
    "owner_draw": ("owner_draw", "Owner Draw"),
    # common reality / engine needs
    "bank_fees": ("bank_fees", "Bank Fees"),
}


def _slug(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "uncategorized"


def _fallback_system_key(acct: Account) -> str:
    # stable & rename-proof
    return f"acct_{acct.id}"


def _is_fallback_system_key(system_key: str) -> bool:
    return (system_key or "").strip().lower().startswith("acct_")


def ensure_category_mapping_for_category(
    db: Session,
    business_id: str,
    category_id: str,
) -> Optional[str]:
    """
    Ensure a category has at least one BusinessCategoryMap row.

    Returns the resolved system_key or None if it cannot be repaired safely.
    """
    rows = db.execute(
        select(BusinessCategoryMap.system_key).where(
            and_(
                BusinessCategoryMap.business_id == business_id,
                BusinessCategoryMap.category_id == category_id,
            )
        )
    ).scalars().all()

    if rows:
        curated = [r for r in rows if not (r or "").startswith("acct_")]
        pick = curated[0] if curated else rows[0]
        return (pick or "").strip().lower() or None

    category = db.execute(
        select(Category).where(
            and_(Category.business_id == business_id, Category.id == category_id)
        )
    ).scalar_one_or_none()
    if not category or not category.account_id:
        return None

    acct = db.execute(
        select(Account).where(
            and_(Account.business_id == business_id, Account.id == category.account_id)
        )
    ).scalar_one_or_none()
    if not acct:
        return None

    desired_key = (_choose_target_system_key_for_account(acct) or "").strip().lower()
    if not desired_key:
        return None

    existing = db.execute(
        select(BusinessCategoryMap).where(
            and_(
                BusinessCategoryMap.business_id == business_id,
                BusinessCategoryMap.system_key == desired_key,
            )
        )
    ).scalar_one_or_none()

    if existing and existing.category_id != category_id:
        desired_key = _fallback_system_key(acct)

    mapping = BusinessCategoryMap(
        id=uuid_str(),
        business_id=business_id,
        system_key=desired_key,
        category_id=category_id,
        is_default=True,
    )
    db.add(mapping)
    db.commit()

    return desired_key


def _ensure_uncategorized_account(db: Session, business_id: str) -> Account:
    """
    Categories require account_id NOT NULL.
    So we guarantee there is an 'Uncategorized' expense account to anchor the sink category.
    """
    acct = db.execute(
        select(Account).where(
            and_(
                Account.business_id == business_id,
                (
                    (Account.subtype == "uncategorized")
                    | (Account.name.ilike("uncategorized%"))
                ),
            )
        )
    ).scalars().first()

    if acct:
        return acct

    acct = Account(
        id=uuid_str(),
        business_id=business_id,
        code=None,
        name="Uncategorized",
        type="expense",
        subtype="uncategorized",
        active=True,
        created_at=utcnow(),
    )
    db.add(acct)
    db.flush()
    return acct


def _ensure_category_for_account(db: Session, business_id: str, acct: Account) -> Category:
    cat = db.execute(
        select(Category).where(
            and_(
                Category.business_id == business_id,
                Category.account_id == acct.id,
            )
        )
    ).scalars().first()

    if cat:
        return cat

    cat = Category(
        id=uuid_str(),
        business_id=business_id,
        name=acct.name,
        system_key=None,
        account_id=acct.id,
        created_at=utcnow(),
    )
    db.add(cat)
    db.flush()
    return cat


def _choose_target_system_key_for_account(acct: Account) -> str:
    """
    ONE mapping per category. So we pick the best single system_key:

    - If subtype known -> canonical key (utilities/software/etc)
    - Else if account name implies bank fees -> bank_fees
    - Else if uncategorized -> uncategorized
    - Else -> stable fallback acct_<id>
    """
    subtype = (acct.subtype or "").strip().lower()
    name = (acct.name or "").strip().lower()

    if subtype in SUBTYPE_TO_SYSTEM:
        return SUBTYPE_TO_SYSTEM[subtype][0]

    if "bank fee" in name or ("bank" in name and "fee" in name):
        return "bank_fees"

    if subtype == "uncategorized" or name == "uncategorized":
        return "uncategorized"

    return _fallback_system_key(acct)


def _ensure_single_mapping_for_category(
    db: Session,
    business_id: str,
    *,
    category_id: str,
    desired_system_key: str,
    map_by_system: Dict[str, BusinessCategoryMap],
    maps_by_category: Dict[str, List[BusinessCategoryMap]],
) -> bool:
    """
    Enforces: for a given (business_id, category_id) we end up with ONE mapping.

    Returns True if anything changed (create/update/delete).
    """
    desired_system_key = (desired_system_key or "").strip().lower()
    if not desired_system_key:
        return False

    changed = False
    existing_for_cat = list(maps_by_category.get(category_id, []))

    # If the desired system_key already exists but points to another category,
    # do NOT reassign it (that would break other mappings). Fall back to acct_<id>.
    existing_same_system = map_by_system.get(desired_system_key)
    if existing_same_system and existing_same_system.category_id != category_id:
        # caller should have provided a safe desired key, but guard anyway:
        # do nothing here; caller can choose fallback next pass if needed.
        return False

    if not existing_for_cat:
        # No mapping yet -> create
        m = BusinessCategoryMap(
            id=uuid_str(),
            business_id=business_id,
            system_key=desired_system_key,
            category_id=category_id,
            is_default=True,
        )
        db.add(m)
        map_by_system[desired_system_key] = m
        maps_by_category[category_id] = [m]
        return True

    # If there are multiple mappings already, we will keep ONE and delete the rest.
    # Prefer: desired key if present, else a curated (non-acct_) key, else the first.
    keep: Optional[BusinessCategoryMap] = None

    # Prefer mapping that already has desired system key
    for m in existing_for_cat:
        if (m.system_key or "").strip().lower() == desired_system_key:
            keep = m
            break

    if keep is None:
        curated = [m for m in existing_for_cat if not _is_fallback_system_key(m.system_key or "")]
        keep = curated[0] if curated else existing_for_cat[0]

    # Update the kept mapping's system_key to desired if we can
    keep_key = (keep.system_key or "").strip().lower()
    if keep_key != desired_system_key:
        # Only update if desired key isn't used elsewhere (guarded above)
        # and we won't lose the ability to resolve (we keep ONE row)
        # Remove old key from index dict
        if keep_key in map_by_system and map_by_system[keep_key].id == keep.id:
            map_by_system.pop(keep_key, None)

        keep.system_key = desired_system_key
        db.add(keep)
        map_by_system[desired_system_key] = keep
        changed = True

    # Delete extras
    for m in existing_for_cat:
        if m.id == keep.id:
            continue
        # Remove from map_by_system if it points at this row
        k = (m.system_key or "").strip().lower()
        if k in map_by_system and map_by_system[k].id == m.id:
            map_by_system.pop(k, None)

        db.delete(m)
        changed = True

    # Refresh category index
    maps_by_category[category_id] = [keep]

    return changed


def seed_coa_and_categories_and_mappings(db: Session, business_id: str) -> None:
    """
    Canonical seeder.

    Guarantees:
      - Accounts exist (DEFAULT_COA) if none exist
      - There is ALWAYS an 'Uncategorized' expense account + category + mapping
      - Categories exist for eligible accounts (expense/revenue/cogs)
      - BusinessCategoryMap ends up with EXACTLY ONE mapping per Category:
          * canonical system_key when subtype/name indicates (utilities/software/etc)
          * otherwise stable fallback acct_<account_id>
    """

    changed = False

    # 1) Ensure COA exists
    accounts = db.execute(select(Account).where(Account.business_id == business_id)).scalars().all()
    if not accounts:
        for a in DEFAULT_COA:
            db.add(
                Account(
                    id=uuid_str(),
                    business_id=business_id,
                    code=a.get("code"),
                    name=a["name"],
                    type=a["type"],
                    subtype=a.get("subtype"),
                    active=True,
                    created_at=utcnow(),
                )
            )
        db.flush()
        accounts = db.execute(select(Account).where(Account.business_id == business_id)).scalars().all()
        changed = True

    # 1b) Guarantee Uncategorized anchor account
    unc_acct = _ensure_uncategorized_account(db, business_id)
    if all(a.id != unc_acct.id for a in accounts):
        accounts.append(unc_acct)
        changed = True

    # 2) Load existing categories
    existing_cats = db.execute(select(Category).where(Category.business_id == business_id)).scalars().all()
    cat_by_account: Dict[str, Category] = {c.account_id: c for c in existing_cats if c.account_id}

    # 3) Load existing mappings (indexes for fast checks)
    existing_maps = db.execute(
        select(BusinessCategoryMap).where(BusinessCategoryMap.business_id == business_id)
    ).scalars().all()

    map_by_system: Dict[str, BusinessCategoryMap] = {
        (m.system_key or "").strip().lower(): m for m in existing_maps if m.system_key
    }
    maps_by_category: Dict[str, List[BusinessCategoryMap]] = {}
    for m in existing_maps:
        maps_by_category.setdefault(m.category_id, []).append(m)

    # Eligible accounts become assignable categories
    eligible: List[Account] = []
    for a in accounts:
        t = (a.type or "").strip().lower()
        st = (a.subtype or "").strip().lower()
        if t in ("expense", "revenue") or st == "cogs":
            eligible.append(a)

    # 4) Ensure Categories + enforce ONE mapping per category
    for acct in eligible:
        cat = cat_by_account.get(acct.id)
        if not cat:
            cat = _ensure_category_for_account(db, business_id, acct)
            cat_by_account[acct.id] = cat
            changed = True

        desired_key = _choose_target_system_key_for_account(acct)

        # If desired key is already taken by another category, fall back to acct_<id>
        desired_key_l = (desired_key or "").strip().lower()
        taken = map_by_system.get(desired_key_l)
        if taken and taken.category_id != cat.id:
            desired_key_l = _fallback_system_key(acct)

        if _ensure_single_mapping_for_category(
            db,
            business_id,
            category_id=cat.id,
            desired_system_key=desired_key_l,
            map_by_system=map_by_system,
            maps_by_category=maps_by_category,
        ):
            changed = True

    if changed:
        db.commit()
