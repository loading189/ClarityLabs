from __future__ import annotations

from datetime import datetime

from backend.app.db import SessionLocal  # or however you create sessions
from backend.app.models import Organization, Business, Account


DEFAULT_COA = [
    {"code": "1000", "name": "Cash", "type": "asset", "subtype": "cash"},
    {"code": "1100", "name": "Accounts Receivable", "type": "asset", "subtype": "ar"},
    {"code": "2000", "name": "Accounts Payable", "type": "liability", "subtype": "ap"},
    {"code": "3000", "name": "Owner Equity", "type": "equity", "subtype": None},
    {"code": "4000", "name": "Revenue", "type": "revenue", "subtype": None},
    {"code": "5000", "name": "Cost of Goods Sold", "type": "expense", "subtype": "cogs"},
    {"code": "5100", "name": "Payroll Expense", "type": "expense", "subtype": "payroll"},
]


def bootstrap_demo(org_name: str = "Demo Org", biz_name: str = "Demo Business") -> None:
    db = SessionLocal()
    try:
        # 1) Create org
        org = Organization(name=org_name, created_at=datetime.utcnow())
        db.add(org)
        db.flush()  # gets org.id without committing

        # 2) Create business
        biz = Business(org_id=org.id, name=biz_name, industry="demo", created_at=datetime.utcnow())
        db.add(biz)
        db.flush()

        # 3) Create default COA
        accounts = []
        for row in DEFAULT_COA:
            accounts.append(
                Account(
                    business_id=biz.id,
                    code=row["code"],
                    name=row["name"],
                    type=row["type"],
                    subtype=row["subtype"],
                    active=True,
                    created_at=datetime.utcnow(),
                )
            )
        db.add_all(accounts)

        db.commit()

        print("\n✅ Bootstrapped successfully")
        print(f"Organization: {org.id}  |  {org.name}")
        print(f"Business:     {biz.id}  |  {biz.name}")
        print(f"Accounts:     {len(accounts)} rows inserted\n")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    bootstrap_demo()
