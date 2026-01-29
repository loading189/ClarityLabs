from datetime import date, datetime, timezone

from backend.app.clarity.health_v1 import build_health_v1_signals
from backend.app.norma.facts import compute_facts, facts_to_dict
from backend.app.norma.ledger import build_cash_ledger
from backend.app.norma.normalize import NormalizedTransaction


def _txn(
    source_event_id: str,
    occurred_at: datetime,
    amount: float,
    direction: str,
    description: str,
    category: str,
) -> NormalizedTransaction:
    return NormalizedTransaction(
        id=None,
        source_event_id=source_event_id,
        occurred_at=occurred_at,
        date=occurred_at.date(),
        description=description,
        amount=amount,
        direction=direction,
        account="checking",
        category=category,
    )


def _build_inputs():
    txns = [
        _txn(
            "evt_1",
            datetime(2024, 1, 5, 12, 0, tzinfo=timezone.utc),
            1200.0,
            "inflow",
            "Stripe payout",
            "revenue",
        ),
        _txn(
            "evt_2",
            datetime(2024, 1, 12, 9, 0, tzinfo=timezone.utc),
            400.0,
            "outflow",
            "Acme Rent",
            "rent",
        ),
        _txn(
            "evt_3",
            datetime(2024, 2, 3, 12, 0, tzinfo=timezone.utc),
            900.0,
            "inflow",
            "Square payout",
            "revenue",
        ),
        _txn(
            "evt_4",
            datetime(2024, 2, 10, 15, 0, tzinfo=timezone.utc),
            950.0,
            "outflow",
            "Payroll run",
            "payroll",
        ),
        _txn(
            "evt_5",
            datetime(2024, 2, 20, 11, 0, tzinfo=timezone.utc),
            300.0,
            "outflow",
            "Cloud hosting",
            "software",
        ),
    ]

    ledger = build_cash_ledger(txns, opening_balance=0.0)
    ledger_rows = [
        {
            "occurred_at": row.occurred_at.isoformat(),
            "date": row.date.isoformat(),
            "amount": float(row.amount),
            "balance": float(row.balance),
            "source_event_id": row.source_event_id,
        }
        for row in ledger
    ]

    facts = compute_facts(txns, ledger)
    facts_json = facts_to_dict(facts)

    categorization_metrics = {
        "total_events": 20,
        "uncategorized": 4,
        "posted": 16,
        "suggestion_coverage": 8,
        "brain_coverage": 3,
    }

    def is_known_vendor(key: str) -> bool:
        return key in {"acme rent", "stripe payout"}

    return txns, ledger_rows, facts_json, categorization_metrics, is_known_vendor


def test_health_v1_signals_deterministic():
    txns, ledger_rows, facts_json, metrics, is_known_vendor = _build_inputs()

    first = build_health_v1_signals(
        facts_json=facts_json,
        ledger_rows=ledger_rows,
        txns=txns,
        updated_at=date(2024, 2, 20).isoformat(),
        categorization_metrics=metrics,
        rule_count=1,
        is_known_vendor=is_known_vendor,
    )
    second = build_health_v1_signals(
        facts_json=facts_json,
        ledger_rows=ledger_rows,
        txns=txns,
        updated_at=date(2024, 2, 20).isoformat(),
        categorization_metrics=metrics,
        rule_count=1,
        is_known_vendor=is_known_vendor,
    )

    assert first == second


def test_health_v1_drilldowns_are_valid():
    txns, ledger_rows, facts_json, metrics, is_known_vendor = _build_inputs()

    signals = build_health_v1_signals(
        facts_json=facts_json,
        ledger_rows=ledger_rows,
        txns=txns,
        updated_at=date(2024, 2, 20).isoformat(),
        categorization_metrics=metrics,
        rule_count=0,
        is_known_vendor=is_known_vendor,
    )

    for signal in signals:
        for drilldown in signal.get("drilldowns", []):
            payload = drilldown.get("payload") or {}
            category_id = payload.get("category_id")
            assert category_id != "uncategorized"


def test_health_v1_signal_ordering_unchanged():
    txns, ledger_rows, facts_json, metrics, is_known_vendor = _build_inputs()

    signals = build_health_v1_signals(
        facts_json=facts_json,
        ledger_rows=ledger_rows,
        txns=txns,
        updated_at=date(2024, 2, 20).isoformat(),
        categorization_metrics=metrics,
        rule_count=1,
        is_known_vendor=is_known_vendor,
    )

    assert [signal["id"] for signal in signals] == [
        "vendor_concentration",
        "new_unknown_vendors",
        "expense_spike",
        "cash_runway_risk",
        "revenue_drop",
        "high_uncategorized_rate",
        "rule_coverage_low",
        "overdraft_pattern",
    ]
