#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path


PRESERVED_NAMES = {
    "danbooru_manager_data",
    "logs",
    "updates",
    "release",
    "build",
    "dist",
    "__pycache__",
}

PRESERVED_SUFFIXES = {
    ".db",
    ".db-wal",
    ".db-shm",
    ".log",
}


class UpdateError(RuntimeError):
    pass


def log(message: str) -> None:
    print(f"[Updater] {message}", flush=True)


def wait_for_process(pid: int | None, timeout_seconds: int = 60) -> None:
    if not pid or pid <= 0:
        return

    log(f"Waiting for application process {pid} to exit...")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not process_exists(pid):
            return
        time.sleep(0.5)

    raise UpdateError(f"Application process {pid} did not exit in time.")


def process_exists(pid: int) -> bool:
    if os.name == "nt":
        completed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            text=True,
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return str(pid) in completed.stdout

    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def safe_extract(zip_path: Path, extract_dir: Path) -> None:
    log(f"Extracting {zip_path}...")
    extract_root = extract_dir.resolve()
    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            member_path = extract_root / member.filename
            resolved = member_path.resolve()
            try:
                resolved.relative_to(extract_root)
            except ValueError:
                raise UpdateError(f"Unsafe ZIP path blocked: {member.filename}")
        archive.extractall(extract_root)


def find_payload_root(extract_dir: Path) -> Path:
    entries = [entry for entry in extract_dir.iterdir() if entry.name != "__MACOSX"]
    dirs = [entry for entry in entries if entry.is_dir()]
    files = [entry for entry in entries if entry.is_file()]

    if len(dirs) == 1 and not files:
        candidate = dirs[0]
        if (candidate / "DanbooruManager.exe").exists() or (candidate / "main.py").exists():
            return candidate

    if (extract_dir / "DanbooruManager.exe").exists() or (extract_dir / "main.py").exists():
        return extract_dir

    if len(dirs) == 1:
        return dirs[0]

    raise UpdateError("Could not determine application folder inside update ZIP.")


def should_preserve(relative_path: Path) -> bool:
    parts = {part.lower() for part in relative_path.parts}
    if parts & PRESERVED_NAMES:
        return True
    if relative_path.suffix.lower() in PRESERVED_SUFFIXES:
        return True
    return False


def remove_replaceable_target_files(target_dir: Path) -> None:
    log("Removing old program files...")
    for path in sorted(target_dir.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if path == target_dir:
            continue
        relative = path.relative_to(target_dir)
        if should_preserve(relative):
            continue
        if not path.exists():
            continue
        if path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass
        else:
            path.unlink()


def copy_payload(payload_root: Path, target_dir: Path) -> None:
    log("Copying new program files...")
    for source in payload_root.rglob("*"):
        relative = source.relative_to(payload_root)
        if should_preserve(relative):
            continue
        target = target_dir / relative
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def restart_application(restart_path: Path | None) -> None:
    if restart_path is None:
        return
    if not restart_path.exists():
        log(f"Restart executable does not exist anymore: {restart_path}")
        return

    log(f"Restarting {restart_path}...")
    subprocess.Popen(
        [str(restart_path)],
        cwd=str(restart_path.parent),
        close_fds=True,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Portable updater for Danbooru Manager.")
    parser.add_argument("--zip", required=True, help="Downloaded release ZIP.")
    parser.add_argument("--target", required=True, help="Installation/application folder to update.")
    parser.add_argument("--restart", default="", help="Executable to restart after update.")
    parser.add_argument("--pid", type=int, default=0, help="Application PID to wait for before replacing files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    zip_path = Path(args.zip).resolve()
    target_dir = Path(args.target).resolve()
    restart_path = Path(args.restart).resolve() if args.restart else None

    try:
        if not zip_path.exists():
            raise UpdateError(f"Update ZIP not found: {zip_path}")
        if not target_dir.exists():
            raise UpdateError(f"Target directory not found: {target_dir}")

        wait_for_process(args.pid)

        with tempfile.TemporaryDirectory(prefix="danbooru_manager_update_") as tmp:
            extract_dir = Path(tmp) / "extract"
            extract_dir.mkdir(parents=True, exist_ok=True)
            safe_extract(zip_path, extract_dir)
            payload_root = find_payload_root(extract_dir)
            log(f"Payload root: {payload_root}")
            remove_replaceable_target_files(target_dir)
            copy_payload(payload_root, target_dir)

        log("Update finished.")
        restart_application(restart_path)
        return 0
    except Exception as exc:
        log(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
