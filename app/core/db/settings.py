from __future__ import annotations

import json
import secrets
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

from app.core.db.common import (
    ACTIVE_STATUSES,
    ALL_ALLOWED_STATUSES,
    calculate_computed_tag_score,
    clamp_number,
    is_path_like_preview_search_term,
    parse_preview_search_terms,
)
from app.core.tag_privacy import build_tag_identity, canonicalize_tag, normalize_tag_token, salted_tag_hash


class DatabaseSettingsMixin:
    """Application settings and fetch preset persistence."""

    def get_app_setting(self, key: str, default: str | None = None) -> str | None:
        row = self.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        value = row["value"]
        return str(value) if value is not None else default

    def set_app_setting(self, key: str, value: str | None) -> None:
        self.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, value),
        )
        self.commit()

    def app_settings_as_values(self) -> dict[str, Any]:
        """Return app_settings decoded as JSON where possible.

        ConfigTab stores values as JSON. Older helper code may have written raw
        strings, so decoding has to be forgiving instead of theatrical.
        """
        rows = self.execute(
            """
            SELECT key, value
            FROM app_settings
            """
        ).fetchall()

        values: dict[str, Any] = {}
        for row in rows:
            key = str(row["key"])
            raw_value = row["value"]
            try:
                values[key] = json.loads(raw_value)
            except Exception:
                values[key] = raw_value
        return values

    def apply_app_settings_to_config(self, config: dict[str, Any]) -> None:
        """Overlay SQLite app_settings onto a runtime config dictionary.

        The database is the leading configuration source once it exists. This is
        especially important for credentials: GUI saves username/api_key in
        app_settings and fetch/import workers only receive the runtime dict.
        """
        for dotted_key, value in self.app_settings_as_values().items():
            parts = str(dotted_key).split(".")
            if not parts:
                continue

            target: Any = config
            for part in parts[:-1]:
                child = target.get(part) if isinstance(target, dict) else None
                if not isinstance(child, dict):
                    child = {}
                    target[part] = child
                target = child

            if isinstance(target, dict):
                target[parts[-1]] = value

        # Older builds used Danbooru's file_url as the viewer cache source.
        # Viewing a post should only cache a preview-sized asset; final saving
        # still downloads file_url through ensure_full_original_cached().
        if str(config.get("viewer_download_source", "preview")).strip().lower() == "file":
            config["viewer_download_source"] = "preview"

    def save_fetch_preset(self, name: str, payload: dict[str, Any]) -> None:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Preset name must not be empty")
        self.execute(
            """
            INSERT INTO fetch_presets (name, payload, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(name) DO UPDATE SET
                payload = excluded.payload,
                updated_at = CURRENT_TIMESTAMP
            """,
            (clean_name, json.dumps(payload, ensure_ascii=False, sort_keys=True)),
        )
        self.commit()

    def list_fetch_presets(self) -> list[sqlite3.Row]:
        return list(
            self.execute(
                """
                SELECT name, payload, updated_at
                FROM fetch_presets
                ORDER BY name COLLATE NOCASE ASC
                """
            ).fetchall()
        )

    def get_fetch_preset(self, name: str) -> dict[str, Any] | None:
        row = self.execute("SELECT payload FROM fetch_presets WHERE name = ?", (name.strip(),)).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(str(row["payload"] or "{}"))
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def delete_fetch_preset(self, name: str) -> None:
        self.execute("DELETE FROM fetch_presets WHERE name = ?", (name.strip(),))
        self.commit()
