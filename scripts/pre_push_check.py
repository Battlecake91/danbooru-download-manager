#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


def project_root() -> Path:
    current = Path(__file__).resolve()
    for parent in [current.parent, *current.parents]:
        if (parent / ".git").exists():
            return parent
    return Path.cwd().resolve()


def run_step(label: str, command: list[str], cwd: Path) -> None:
    print(f"\n=== {label} ===")
    print("[INFO] Running: " + " ".join(command))
    completed = subprocess.run(command, cwd=str(cwd), text=True)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> int:
    root = project_root()
    python = sys.executable

    run_step("Whitespace check", ["git", "diff", "--check"], root)
    run_step("Compile Python sources", [python, "-m", "compileall", "-q", "app", "main.py", "scripts", "tests"], root)

    if importlib.util.find_spec("pytest") is not None:
        run_step("Run pytest", [python, "-m", "pytest"], root)
    else:
        run_step("Run unittest fallback", [python, "-m", "unittest", "discover", "-v"], root)

    print("\n[INFO] Pre-push checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
