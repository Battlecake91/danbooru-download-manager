from __future__ import annotations

import json
from pathlib import Path
from typing import Any


LOCAL_MODE = "local"
REMOTE_MODE = "remote_docker"


def connection_profile_path(config: dict[str, Any]) -> Path:
    return Path(str(config.get("work_dir") or "./danbooru_manager_data")) / "desktop_connection.json"


def connection_profile_exists(config: dict[str, Any]) -> bool:
    return connection_profile_path(config).is_file()


def load_connection_profile(config: dict[str, Any]) -> dict[str, Any]:
    profile = {
        "mode": LOCAL_MODE,
        "remote_url": "http://127.0.0.1:8765",
        "remote_token": "",
    }
    path = connection_profile_path(config)
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = {}
        if isinstance(loaded, dict):
            profile.update({key: loaded[key] for key in profile if key in loaded})
    if profile["mode"] not in {LOCAL_MODE, REMOTE_MODE}:
        profile["mode"] = LOCAL_MODE
    profile["remote_url"] = str(profile["remote_url"] or "http://127.0.0.1:8765").rstrip("/")
    profile["remote_token"] = str(profile["remote_token"] or "")
    return profile


def save_connection_profile(config: dict[str, Any], profile: dict[str, Any]) -> Path:
    payload = validate_connection_profile(profile)
    path = connection_profile_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    return path


def validate_connection_profile(profile: dict[str, Any]) -> dict[str, str]:
    mode = str(profile.get("mode") or LOCAL_MODE)
    if mode not in {LOCAL_MODE, REMOTE_MODE}:
        raise ValueError("Connection mode must be local or remote_docker")
    remote_url = str(profile.get("remote_url") or "").strip().rstrip("/")
    remote_token = str(profile.get("remote_token") or "").strip()
    if mode == REMOTE_MODE:
        if not remote_url.startswith(("http://", "https://")):
            raise ValueError("Remote Docker URL must start with http:// or https://")
        if not remote_token:
            raise ValueError("Remote Docker API token is required")
    return {"mode": mode, "remote_url": remote_url, "remote_token": remote_token}


def apply_connection_profile(config: dict[str, Any], profile: dict[str, Any]) -> None:
    config["connection"] = {
        "mode": str(profile.get("mode") or LOCAL_MODE),
        "remote_url": str(profile.get("remote_url") or "").rstrip("/"),
        "remote_token": str(profile.get("remote_token") or ""),
    }


def database_from_config(config: dict[str, Any]):
    connection = config.get("connection", {}) or {}
    if str(connection.get("mode") or LOCAL_MODE) == REMOTE_MODE:
        from app.core.remote_database import RemoteDatabase

        return RemoteDatabase(
            str(connection.get("remote_url") or ""),
            str(connection.get("remote_token") or ""),
        )

    from app.core.database import Database

    return Database(Path(str(config["database_file"])))
