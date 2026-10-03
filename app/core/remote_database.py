from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable, Iterator

import requests


class RemoteHttpError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = int(status_code)


class RemoteRow(dict[str, Any]):
    def __init__(self, values: dict[str, Any], columns: list[str] | None = None) -> None:
        super().__init__(values)
        self._columns = columns or list(values)

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            key = self._columns[key]
        return super().__getitem__(key)


class RemoteCursor:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.columns = [str(value) for value in payload.get("columns", [])]
        self.rows = [RemoteRow(dict(row), self.columns) for row in payload.get("rows", [])]
        rowcount = payload.get("rowcount", -1)
        self.rowcount = int(-1 if rowcount is None else rowcount)
        self.lastrowid = payload.get("lastrowid")
        self.description = [(column, None, None, None, None, None, None) for column in self.columns] or None
        self._index = 0

    def fetchone(self) -> RemoteRow | None:
        if self._index >= len(self.rows):
            return None
        row = self.rows[self._index]
        self._index += 1
        return row

    def fetchall(self) -> list[RemoteRow]:
        rows = self.rows[self._index :]
        self._index = len(self.rows)
        return rows

    def __iter__(self) -> Iterator[RemoteRow]:
        return iter(self.fetchall())


def _encode(value: Any) -> Any:
    if isinstance(value, Path):
        return {"__remote_type__": "path", "value": str(value)}
    if isinstance(value, bytes):
        return {"__remote_type__": "bytes", "value": base64.b64encode(value).decode("ascii")}
    if isinstance(value, dict):
        return {str(key): _encode(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_encode(item) for item in value]
    return value


def _decode(value: Any) -> Any:
    if isinstance(value, dict):
        marker = value.get("__remote_type__")
        if marker == "path":
            return Path(str(value.get("value") or ""))
        if marker == "bytes":
            return base64.b64decode(str(value.get("value") or ""))
        return {key: _decode(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode(item) for item in value]
    return value


class RemoteDatabase:
    is_remote = True

    def __init__(self, base_url: str, token: str, timeout: float = 60.0) -> None:
        self.base_url = str(base_url or "").strip().rstrip("/")
        self.token = str(token or "").strip()
        self.timeout = float(timeout)
        self.path = Path("remote-docker")
        self.connection = None
        self.session = requests.Session()

    def _request(self, method: str, endpoint: str, **kwargs: Any) -> Any:
        if not self.base_url:
            raise RuntimeError("Remote Docker URL is missing")
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            response = self.session.request(
                method,
                f"{self.base_url}{endpoint}",
                headers=headers,
                timeout=self.timeout,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"Remote Docker connection failed: {exc}") from exc
        if not response.ok:
            try:
                detail = response.json().get("detail")
            except Exception:
                detail = response.text
            raise RemoteHttpError(
                response.status_code,
                str(detail or f"Remote Docker returned HTTP {response.status_code}"),
            )
        return response.json() if response.content else None

    def media_bytes(self, post_id: int, variant: str = "thumbnail") -> bytes:
        if variant not in {"thumbnail", "viewer"}:
            raise ValueError("Media variant must be thumbnail or viewer")
        with requests.get(
            f"{self.base_url}/api/media/{int(post_id)}/{variant}",
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=self.timeout,
        ) as response:
            if not response.ok:
                raise RemoteHttpError(response.status_code, response.text or "Remote media could not be loaded")
            return response.content

    def cache_media(self, post_id: int, target_dir: Path, variant: str = "viewer", force: bool = False) -> str:
        target_dir.mkdir(parents=True, exist_ok=True)
        base = target_dir / f"remote_{int(post_id)}_{variant}"
        existing = next((path for path in target_dir.glob(f"{base.name}.*") if path.is_file()), None)
        if existing is not None and existing.stat().st_size > 0 and not force:
            return str(existing)

        with requests.get(
            f"{self.base_url}/api/media/{int(post_id)}/{variant}",
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=self.timeout,
            stream=True,
        ) as response:
            if not response.ok:
                raise RemoteHttpError(response.status_code, response.text or "Remote media could not be loaded")
            content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0]
            extension = mimetypes.guess_extension(content_type) or ".img"
            target = base.with_suffix(extension)
            temporary = target.with_suffix(target.suffix + ".part")
            with temporary.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        handle.write(chunk)
        temporary.replace(target)
        return str(target)

    def connect(self, *, check_same_thread: bool = True) -> None:
        _ = check_same_thread
        self._request("GET", "/api/desktop/health")

    def close(self) -> None:
        self.session.close()

    def initialize_schema(self) -> None:
        return None

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def execute(self, sql: str, parameters: Iterable[Any] = ()) -> RemoteCursor:
        payload = self._request(
            "POST",
            "/api/desktop/sql",
            json={"operation": "execute", "sql": sql, "parameters": _encode(list(parameters))},
        )
        payload["rows"] = _decode(payload.get("rows", []))
        return RemoteCursor(payload)

    def executemany(self, sql: str, rows: Iterable[Iterable[Any]]) -> RemoteCursor:
        payload = self._request(
            "POST",
            "/api/desktop/sql",
            json={"operation": "executemany", "sql": sql, "rows": _encode([list(row) for row in rows])},
        )
        return RemoteCursor(payload)

    def executescript(self, sql_script: str) -> RemoteCursor:
        payload = self._request(
            "POST",
            "/api/desktop/sql",
            json={"operation": "executescript", "sql": sql_script},
        )
        return RemoteCursor(payload)

    def app_settings_as_values(self) -> dict[str, Any]:
        return dict(self._rpc("app_settings_as_values") or {})

    def set_post_status(
        self,
        post_id: int,
        status: str,
        config: dict[str, Any] | None = None,
    ) -> None:
        # The desktop config contains Windows cache paths. The web endpoint uses
        # the Docker runtime config instead and moves thumbnails inside /data.
        _ = config
        self._request(
            "PATCH",
            f"/api/posts/{int(post_id)}",
            json={"status": str(status)},
        )

    def set_post_statuses(
        self,
        post_ids: list[int],
        status: str,
        config: dict[str, Any] | None = None,
    ) -> None:
        _ = config
        clean_ids = list(dict.fromkeys(int(post_id) for post_id in post_ids))
        if not clean_ids:
            return
        self._request(
            "PATCH",
            "/api/posts/status",
            json={"post_ids": clean_ids, "status": str(status)},
        )

    def apply_app_settings_to_config(self, config: dict[str, Any]) -> None:
        local_only = {
            "connection",
            "work_dir",
            "database_file",
            "thumbnail_dir",
            "active_thumbnail_dir",
            "saved_thumbnail_dir",
            "rejected_thumbnail_dir",
            "original_cache_dir",
            "default_output_dir",
            "archive_paths",
        }
        for dotted_key, value in self.app_settings_as_values().items():
            if str(dotted_key).split(".", 1)[0] in local_only:
                continue
            target: dict[str, Any] = config
            parts = str(dotted_key).split(".")
            for part in parts[:-1]:
                child = target.get(part)
                if not isinstance(child, dict):
                    child = {}
                    target[part] = child
                target = child
            target[parts[-1]] = value
        if str(config.get("viewer_download_source", "preview")).lower() == "file":
            config["viewer_download_source"] = "preview"

    def save_post_remote(self, post_id: int, category_id: int | None, overwrite_existing: bool):
        try:
            payload = self._request(
                "POST",
                f"/api/posts/{int(post_id)}/save",
                json={"category_id": category_id, "overwrite_existing": bool(overwrite_existing)},
            )
        except RemoteHttpError as exc:
            if exc.status_code == 409:
                from app.services.final_save_service import AlreadySavedError

                raise AlreadySavedError(int(post_id), str(exc)) from exc
            raise
        return SimpleNamespace(
            post_id=int(payload["post_id"]),
            category=SimpleNamespace(id=category_id, name=str(payload["category"])),
            category_source=str(payload["category_source"]),
            source_path=Path(str(payload["final_path"])),
            final_path=Path(str(payload["final_path"])),
        )

    def _rpc(self, method: str, *args: Any, **kwargs: Any) -> Any:
        payload = self._request(
            "POST",
            "/api/desktop/rpc",
            json={"method": method, "args": _encode(list(args)), "kwargs": _encode(kwargs)},
        )
        return _decode(payload.get("result"))

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *args, **kwargs: self._rpc(name, *args, **kwargs)
