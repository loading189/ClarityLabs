from backend.app.analytics.monthly_trends import build_monthly_trends_payload


def test_monthly_trends_series_uses_ledger_rows():
    ledger_rows = [
        {
            "occurred_at": "2024-01-05T12:00:00+00:00",
            "date": "2024-01-05",
            "amount": 100.0,
            "balance": 100.0,
            "source_event_id": "evt_1",
        },
        {
            "occurred_at": "2024-01-20T12:00:00+00:00",
            "date": "2024-01-20",
            "amount": -40.0,
            "balance": 60.0,
            "source_event_id": "evt_2",
        },
        {
            "occurred_at": "2024-02-01T09:00:00+00:00",
            "date": "2024-02-01",
            "amount": 20.0,
            "balance": 80.0,
            "source_event_id": "evt_3",
        },
        {
            "occurred_at": "2024-02-11T09:00:00+00:00",
            "date": "2024-02-11",
            "amount": -10.0,
            "balance": 70.0,
            "source_event_id": "evt_4",
        },
    ]

    facts_json = {
        "current_cash": 70.0,
        "monthly_inflow_outflow": [],
    }

    payload = build_monthly_trends_payload(
        facts_json=facts_json,
        lookback_months=12,
        k=2.0,
        ledger_rows=ledger_rows,
    )

    series = payload["metrics"]["net"]["series"]
    jan = next(row for row in series if row["month"] == "2024-01")
    feb = next(row for row in series if row["month"] == "2024-02")

    assert jan["inflow"] == 100.0
    assert jan["outflow"] == 40.0
    assert jan["net"] == 60.0
    assert jan["cash_end"] == 60.0

    assert feb["inflow"] == 20.0
    assert feb["outflow"] == 10.0
    assert feb["net"] == 10.0
    assert feb["cash_end"] == 70.0
