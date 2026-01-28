from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str], *, cwd: Path) -> None:
    command_str = " ".join(cmd)
    print(f"$ {command_str}")
    result = subprocess.run(cmd, cwd=str(cwd))
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> None:
    repo_root = Path(__file__).resolve().parents[3]

    print("Running backend checks...")
    _run([sys.executable, "-m", "pytest"], cwd=repo_root)

    frontend_dir = repo_root / "frontend"
    if frontend_dir.exists():
        print("Running frontend build...")
        _run(["npm", "run", "build"], cwd=frontend_dir)
    else:
        print("Frontend folder not found; skipping frontend build.")

    print("All checks passed.")


if __name__ == "__main__":
    main()
