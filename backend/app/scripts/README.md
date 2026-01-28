# Scripts

## Golden run (deterministic pipeline harness)

Runs a deterministic end-to-end pipeline from simulated RawEvents through normalization, categorization, ledger, and signals.
It writes a JSON artifact with stage hashes and samples to `backend/.artifacts/golden/golden_run.json`.

```bash
python -m backend.app.scripts.golden_run
```

## Golden run regression check

Runs the golden run twice and asserts that stage hashes match (determinism check).

```bash
python -m backend.app.scripts.golden_run_check
```

## Business brief endpoint

Fetch a concise brief built from facts + signals:

```bash
curl "http://localhost:8000/brief/business/<business_id>?window_days=30"
```

Example response (shape):

```json
{
  "business_id": "uuid",
  "as_of": "2024-01-31T00:00:00+00:00",
  "window_days": 30,
  "status": "ATTENTION",
  "headline": "Cash outflow spiked in the last 30 days.",
  "bullets": [
    "Outflow grew faster than inflow in the recent window.",
    "Payroll is one of the top spend drivers this month.",
    "Two revenue categories slipped below prior-month levels."
  ],
  "next_best_action": "Review the largest expense drivers and trim discretionary spend.",
  "confidence": 0.65,
  "confidence_reason": "Based on 145 transactions across 6 months.",
  "top_signals": [],
  "facts_meta": {
    "as_of": "2024-01-31",
    "txn_count": 145,
    "months_covered": 6
  }
}
```
