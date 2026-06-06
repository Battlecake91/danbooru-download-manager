from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.version import APP_NAME, GITHUB_REPOSITORY, __version__


ProgressCallback = Callable[[int, int], None]


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    download_url: str
    size: int


@dataclass(frozen=True)
class UpdateInfo:
    current_version: str
    latest_version: str
    tag_name: str
    html_url: str
    release_name: str
    asset: ReleaseAsset

    @property
    def is_newer(self) -> bool:
        return compare_versions(self.latest_version, self.current_version) > 0


def is_frozen_app() -> bool:
    return bool(getattr(sys, "frozen", False))


def executable_dir() -> Path:
    return Path(sys.executable).resolve().parent


def startup_dir() -> Path:
    try:
        return Path(sys.argv[0]).resolve().parent
    except Exception:
        return Path.cwd().resolve()


def runtime_candidate_dirs() -> list[Path]:
    candidates = [
        executable_dir(),
        startup_dir(),
        Path.cwd().resolve(),
    ]

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def packaged_runtime_dir() -> Path | None:
    if is_frozen_app():
        return executable_dir()

    for directory in runtime_candidate_dirs():
        app_exe = directory / "DanbooruManager.exe"
        updater_exe = directory / "DanbooruManagerUpdater.exe"
        if app_exe.exists() and updater_exe.exists():
            return directory

    return None


def portable_update_available() -> bool:
    return packaged_runtime_dir() is not None


def normalize_version(value: str) -> str:
    value = str(value or "").strip()
    if value.lower().startswith("v"):
        value = value[1:]
    return value.strip()


def version_key(value: str) -> tuple[int, ...]:
    normalized = normalize_version(value)
    parts: list[int] = []
    for part in normalized.replace("-", ".").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        parts.append(int(digits or 0))
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def compare_versions(left: str, right: str) -> int:
    left_key = version_key(left)
    right_key = version_key(right)
    if left_key > right_key:
        return 1
    if left_key < right_key:
        return -1
    return 0


def _json_request(url: str, timeout: int = 20) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{APP_NAME}/{__version__}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"GitHub returned HTTP {exc.code} while checking for updates.") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach GitHub while checking for updates: {exc.reason}") from exc

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GitHub returned an invalid JSON response.") from exc


def find_release_asset(release: dict[str, Any]) -> ReleaseAsset:
    assets = release.get("assets") or []
    candidates: list[ReleaseAsset] = []

    for asset in assets:
        name = str(asset.get("name") or "")
        url = str(asset.get("browser_download_url") or "")
        size = int(asset.get("size") or 0)
        lower_name = name.lower()
        if not url:
            continue
        if not lower_name.endswith(".zip"):
            continue
        if "win64" not in lower_name and "windows" not in lower_name:
            continue
        if APP_NAME.lower() not in lower_name and "danbooru" not in lower_name:
            continue
        candidates.append(ReleaseAsset(name=name, download_url=url, size=size))

    if not candidates:
        raise RuntimeError("No suitable Windows ZIP asset was found in the latest GitHub release.")

    candidates.sort(key=lambda item: ("win64" not in item.name.lower(), item.name.lower()))
    return candidates[0]


def check_for_update(repo: str = GITHUB_REPOSITORY, current_version: str = __version__) -> UpdateInfo:
    release = _json_request(f"https://api.github.com/repos/{repo}/releases/latest")
    tag_name = str(release.get("tag_name") or "").strip()
    if not tag_name:
        raise RuntimeError("Latest GitHub release has no tag name.")

    asset = find_release_asset(release)
    latest_version = normalize_version(tag_name)

    return UpdateInfo(
        current_version=normalize_version(current_version),
        latest_version=latest_version,
        tag_name=tag_name,
        html_url=str(release.get("html_url") or ""),
        release_name=str(release.get("name") or tag_name),
        asset=asset,
    )


def updates_dir(config: dict[str, Any]) -> Path:
    work_dir = Path(str(config.get("work_dir") or "danbooru_manager_data"))
    path = work_dir / "updates"
    path.mkdir(parents=True, exist_ok=True)
    return path


def download_update_asset(info: UpdateInfo, target_dir: Path, progress_callback: ProgressCallback | None = None) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    zip_path = target_dir / info.asset.name
    part_path = zip_path.with_suffix(zip_path.suffix + ".part")

    request = urllib.request.Request(
        info.asset.download_url,
        headers={"User-Agent": f"{APP_NAME}/{__version__}"},
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            total = int(response.headers.get("Content-Length") or info.asset.size or 0)
            downloaded = 0
            with part_path.open("wb") as f:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback is not None:
                        progress_callback(downloaded, total)
    except Exception:
        if part_path.exists():
            part_path.unlink()
        raise

    if zip_path.exists():
        zip_path.unlink()
    part_path.replace(zip_path)
    return zip_path


def app_target_dir() -> Path:
    runtime_dir = packaged_runtime_dir()
    if runtime_dir is not None:
        return runtime_dir
    return Path.cwd().resolve()


def app_restart_executable() -> Path:
    runtime_dir = packaged_runtime_dir()
    if runtime_dir is not None:
        app_exe = runtime_dir / "DanbooruManager.exe"
        if app_exe.exists():
            return app_exe

    if is_frozen_app():
        return Path(sys.executable).resolve()

    return Path(sys.argv[0]).resolve()


def find_updater_executable(config: dict[str, Any]) -> Path:
    runtime_dir = packaged_runtime_dir()
    if runtime_dir is not None:
        candidates = [
            runtime_dir / "DanbooruManagerUpdater.exe",
            runtime_dir / "updater.exe",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate

    searched = ", ".join(str(path) for path in runtime_candidate_dirs())
    raise RuntimeError(
        "Portable updates require the packaged release folder with "
        "DanbooruManager.exe and DanbooruManagerUpdater.exe next to each other.\n\n"
        f"Searched in: {searched}\n\n"
        "Build the application with the Release task first and start the packaged EXE. "
        "Running from source will not overwrite your checkout."
    )


def make_updater_runner(updater_path: Path, config: dict[str, Any]) -> Path:
    # Run the updater from a temporary copy so the installed updater.exe can be
    # replaced by the new release too. Windows locks running executables because
    # apparently drama is a kernel feature.
    if not updater_path.suffix.lower() == ".exe":
        return updater_path

    runner_dir = updates_dir(config) / "runner"
    runner_dir.mkdir(parents=True, exist_ok=True)
    runner_path = runner_dir / updater_path.name
    shutil.copy2(updater_path, runner_path)
    return runner_path


def start_portable_update(zip_path: Path, config: dict[str, Any]) -> None:
    if not portable_update_available():
        find_updater_executable(config)

    updater_path = make_updater_runner(find_updater_executable(config), config)
    target_dir = app_target_dir()
    restart_executable = app_restart_executable()
    pid = os.getpid()

    if updater_path.suffix.lower() == ".py":
        command = [
            sys.executable,
            str(updater_path),
        ]
    else:
        command = [str(updater_path)]

    log_path = updates_dir(config) / "updater.log"
    command.extend(
        [
            "--zip",
            str(zip_path),
            "--target",
            str(target_dir),
            "--restart",
            str(restart_executable),
            "--pid",
            str(pid),
            "--log",
            str(log_path),
        ]
    )

    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    creationflags |= getattr(subprocess, "DETACHED_PROCESS", 0)
    process = subprocess.Popen(
        command,
        cwd=str(target_dir),
        close_fds=True,
        creationflags=creationflags,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if process.poll() is not None:
        raise RuntimeError(
            "The updater process exited immediately. "
            f"See {log_path} for details."
        )
