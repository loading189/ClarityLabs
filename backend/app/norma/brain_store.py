from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional
from uuid import uuid4


@dataclass
class Merchant:
    merchant_id: str
    canonical_name: str
    updated_at: str = ""


@dataclass
class Alias:
    alias_key: str               # normalized merchant_key
    merchant_id: str
    match_type: str = "exact"
    evidence_count: int = 0
    updated_at: str = ""


@dataclass
class BusinessLabel:
    business_id: str
    merchant_id: str
    system_key: str
    confidence: float = 0.92
    evidence_count: int = 1
    updated_at: str = ""


class BrainStore:
    """
    Org-wide store of merchants + aliases, with business-scoped labels:
      (business_id, merchant_id) -> system_key
      and lookup path: merchant_key -> alias -> merchant_id -> label per business
    MVP persistence: JSON file.
    """
    def __init__(self, path: Path):
        self.path = path
        self.merchants: Dict[str, Merchant] = {}
        self.aliases: Dict[str, Alias] = {}
        # labels[business_id][merchant_id] = BusinessLabel
        self.labels: Dict[str, Dict[str, BusinessLabel]] = {}
        self._load()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _load(self) -> None:
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))

        # Backwards compatible merchant load (ignore old keys like default_category)
        self.merchants = {}
        for m in data.get("merchants", []):
            mid = m.get("merchant_id")
            if not mid:
                continue
            self.merchants[mid] = Merchant(
                merchant_id=mid,
                canonical_name=m.get("canonical_name", ""),
                updated_at=m.get("updated_at", ""),
            )

        self.aliases = {}
        for a in data.get("aliases", []):
            ak = a.get("alias_key")
            mid = a.get("merchant_id")
            if not ak or not mid:
                continue
            self.aliases[ak] = Alias(
                alias_key=ak,
                merchant_id=mid,
                match_type=a.get("match_type", "exact"),
                evidence_count=int(a.get("evidence_count", 0) or 0),
                updated_at=a.get("updated_at", ""),
            )

        # New schema labels
        self.labels = {}
        raw_labels = data.get("labels", {})
        if isinstance(raw_labels, dict):
            for biz_id, per_biz in raw_labels.items():
                if not isinstance(per_biz, dict):
                    continue
                self.labels[biz_id] = {}
                for mid, lbl in per_biz.items():
                    if not isinstance(lbl, dict):
                        continue
                    self.labels[biz_id][mid] = BusinessLabel(
                        business_id=lbl.get("business_id", biz_id),
                        merchant_id=lbl.get("merchant_id", mid),
                        system_key=(lbl.get("system_key") or "uncategorized"),
                        confidence=float(lbl.get("confidence", 0.92) or 0.92),
                        evidence_count=int(lbl.get("evidence_count", 1) or 1),
                        updated_at=lbl.get("updated_at", ""),
                    )

        # One-time migration: old Merchant.default_category -> labels["__legacy__"]
        legacy_biz = "__legacy__"
        changed = False
        for m in data.get("merchants", []):
            mid = m.get("merchant_id")
            old_default = (m.get("default_category") or "").strip().lower()
            if not mid or not old_default:
                continue
            already = any(mid in d for d in self.labels.values())
            if already:
                continue
            self.labels.setdefault(legacy_biz, {})
            self.labels[legacy_biz][mid] = BusinessLabel(
                business_id=legacy_biz,
                merchant_id=mid,
                system_key=old_default,
                confidence=float(m.get("confidence", 0.92) or 0.92),
                evidence_count=int(m.get("evidence_count", 1) or 1),
                updated_at=m.get("updated_at", ""),
            )
            changed = True

        if changed:
            self.save()

    def delete_business(self, business_id: str) -> None:
        if business_id in self.labels:
            del self.labels[business_id]
            self.save()


    def save(self) -> None:
        payload = {
            "merchants": [asdict(m) for m in self.merchants.values()],
            "aliases": [asdict(a) for a in self.aliases.values()],
            "labels": {
                biz: {mid: asdict(lbl) for mid, lbl in per.items()}
                for biz, per in self.labels.items()
            },
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def resolve_merchant_id(self, alias_key: str) -> Optional[str]:
        a = self.aliases.get(alias_key)
        return a.merchant_id if a else None

    def get_merchant(self, merchant_id: str) -> Optional[Merchant]:
        return self.merchants.get(merchant_id)

    def _create_merchant(self, canonical_name: str) -> Merchant:
        now = self._now()
        m = Merchant(
            merchant_id=str(uuid4()),
            canonical_name=canonical_name,
            updated_at=now,
        )
        self.merchants[m.merchant_id] = m
        return m

    def _upsert_alias(self, alias_key: str, merchant_id: str) -> None:
        now = self._now()
        existing = self.aliases.get(alias_key)
        if existing:
            existing.evidence_count += 1
            existing.updated_at = now
            return
        self.aliases[alias_key] = Alias(
            alias_key=alias_key,
            merchant_id=merchant_id,
            evidence_count=1,
            updated_at=now,
        )

    def apply_label(
        self,
        *,
        business_id: str,
        alias_key: str,
        canonical_name: str,
        system_key: str,
        confidence: float = 0.92,
    ) -> BusinessLabel:
        """
        Label once => business-scoped memory:
          (business_id, merchant_key) => system_key
        """
        now = self._now()
        system_key = (system_key or "").strip().lower() or "uncategorized"

        mid = self.resolve_merchant_id(alias_key)
        if mid and mid in self.merchants:
            m = self.merchants[mid]
            if canonical_name and canonical_name.strip():
                m.canonical_name = canonical_name.strip()
            m.updated_at = now
            self._upsert_alias(alias_key, mid)
        else:
            m = self._create_merchant(canonical_name.strip() or "Unknown")
            self._upsert_alias(alias_key, m.merchant_id)
            mid = m.merchant_id

        per = self.labels.setdefault(business_id, {})
        existing = per.get(mid)
        if existing:
            existing.system_key = system_key
            existing.confidence = max(existing.confidence, float(confidence or 0.92))
            existing.evidence_count += 1
            existing.updated_at = now
            return existing

        lbl = BusinessLabel(
            business_id=business_id,
            merchant_id=mid,
            system_key=system_key,
            confidence=float(confidence or 0.92),
            evidence_count=1,
            updated_at=now,
        )
        per[mid] = lbl
        return lbl

    def lookup_label(self, *, business_id: str, alias_key: str) -> Optional[BusinessLabel]:
        mid = self.resolve_merchant_id(alias_key)
        if not mid:
            return None
        per = self.labels.get(business_id, {})
        return per.get(mid)

    def count_learned_merchants(self, business_id: str) -> int:
        return len(self.labels.get(business_id, {}))
