from __future__ import annotations

import logging
from pathlib import Path

from app.core.database import Database

LOGGER = logging.getLogger(__name__)


def import_downloaded_ids_history(db: Database, history_file: Path) -> int:
    if not history_file.exists():
        LOGGER.warning("History-Datei nicht gefunden: %s", history_file)
        return 0

    imported = 0

    with history_file.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                continue

            parts = raw.split("\t", 1)
            try:
                post_id = int(parts[0])
            except ValueError:
                LOGGER.warning("Ungültige History-Zeile %s: %r", line_number, raw)
                continue

            filename = parts[1] if len(parts) > 1 else None

            db.execute(
                """
                INSERT INTO downloaded_history_import (post_id, filename)
                VALUES (?, ?)
                ON CONFLICT(post_id) DO UPDATE SET filename = excluded.filename
                """,
                (post_id, filename),
            )

            db.execute(
                """
                INSERT INTO posts (id, status, original_path, already_known_at)
                VALUES (?, 'already_known', ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    status = CASE
                        WHEN posts.status IN ('new', 'potential', 'downloaded') THEN 'already_known'
                        ELSE posts.status
                    END,
                    original_path = COALESCE(posts.original_path, excluded.original_path),
                    already_known_at = COALESCE(posts.already_known_at, CURRENT_TIMESTAMP)
                """,
                (post_id, filename),
            )

            imported += 1

    db.commit()
    return imported
