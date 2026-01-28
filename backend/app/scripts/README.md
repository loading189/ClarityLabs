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
