from __future__ import annotations

from pathlib import Path

from backend.app.scripts.golden_run import ARTIFACT_DIR, run_golden_run


def run_check() -> None:
    path_a = ARTIFACT_DIR / "golden_run_check_a.json"
    path_b = ARTIFACT_DIR / "golden_run_check_b.json"

    artifact_a = run_golden_run(output_path=path_a)
    artifact_b = run_golden_run(output_path=path_b)

    stages_a = artifact_a.get("stages", {})
    stages_b = artifact_b.get("stages", {})

    for stage, summary_a in stages_a.items():
        summary_b = stages_b.get(stage, {})
        hash_a = summary_a.get("hash")
        hash_b = summary_b.get("hash")
        if hash_a != hash_b:
            raise AssertionError(f"Golden run mismatch for stage '{stage}': {hash_a} != {hash_b}")

    print("✅ Golden run determinism check passed")


if __name__ == "__main__":
    run_check()
