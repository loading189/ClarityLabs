from __future__ import annotations

from typing import Dict, List, Optional


def _anchor_query(
    *,
    source_event_ids: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    accounts: Optional[List[str]] = None,
    vendors: Optional[List[str]] = None,
    categories: Optional[List[str]] = None,
    search: Optional[str] = None,
    direction: Optional[str] = None,
) -> Dict[str, object]:
    query: Dict[str, object] = {}
    if source_event_ids:
        query["source_event_ids"] = [str(txn_id) for txn_id in source_event_ids]
    if start_date:
        query["start_date"] = start_date
    if end_date:
        query["end_date"] = end_date
    if accounts:
        query["accounts"] = [str(value) for value in accounts if value]
    if vendors:
        query["vendors"] = [str(value) for value in vendors if value]
    if categories:
        query["categories"] = [str(value) for value in categories if value]
    if search:
        query["search"] = search
    if direction:
        query["direction"] = direction
    return query


def _add_ledger_anchor(
    payload: Dict[str, object],
    label: str,
    query: Dict[str, object],
    evidence_keys: Optional[List[str]] = None,
) -> None:
    anchors = payload.setdefault("ledger_anchors", [])
    if not isinstance(anchors, list):
        anchors = []
        payload["ledger_anchors"] = anchors
    entry: Dict[str, object] = {"label": label, "query": query}
    if evidence_keys:
        entry["evidence_keys"] = sorted({str(key) for key in evidence_keys if key})
    anchors.append(entry)
