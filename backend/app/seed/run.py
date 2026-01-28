from sqlalchemy.orm import Session
from backend.app.models import SystemCategory
from backend.app.seed.system_categories import SYSTEM_CATEGORIES

def seed_system_categories(db: Session) -> None:
    existing = {r[0] for r in db.query(SystemCategory.key).all()}
    for key, display_name, group in SYSTEM_CATEGORIES:
        if key in existing:
            continue
        db.add(SystemCategory(key=key, display_name=display_name, group=group))
    db.commit()
