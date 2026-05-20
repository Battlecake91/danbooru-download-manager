from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.connection: sqlite3.Connection | None = None

    def connect(self) -> None:
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.execute("PRAGMA foreign_keys = ON")
        self.execute("PRAGMA journal_mode = WAL")

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def execute(self, sql: str, parameters: Iterable[Any] = ()) -> sqlite3.Cursor:
        if self.connection is None:
            raise RuntimeError("Datenbank ist nicht verbunden")
        return self.connection.execute(sql, tuple(parameters))

    def executemany(self, sql: str, rows: Iterable[Iterable[Any]]) -> sqlite3.Cursor:
        if self.connection is None:
            raise RuntimeError("Datenbank ist nicht verbunden")
        return self.connection.executemany(sql, rows)

    def commit(self) -> None:
        if self.connection is None:
            raise RuntimeError("Datenbank ist nicht verbunden")
        self.connection.commit()

    def initialize_schema(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY,
            source TEXT DEFAULT 'danbooru',

            rating TEXT,
            score INTEGER,
            fav_count INTEGER,

            file_ext TEXT,
            file_url TEXT,
            large_file_url TEXT,
            preview_url TEXT,

            thumbnail_path TEXT,
            original_path TEXT,

            parent_id INTEGER,
            has_children INTEGER DEFAULT 0,

            status TEXT DEFAULT 'new',

            local_score REAL DEFAULT 0,
            llm_score REAL DEFAULT NULL,
            final_score REAL DEFAULT NULL,

            created_at TEXT,
            last_seen_at TEXT,
            downloaded_at TEXT,
            reviewed_at TEXT,
            saved_at TEXT
        );

        CREATE TABLE IF NOT EXISTS post_tags (
            post_id INTEGER NOT NULL,
            tag TEXT NOT NULL,
            tag_type TEXT NOT NULL,

            PRIMARY KEY (post_id, tag),
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_post_tags_tag ON post_tags(tag);
        CREATE INDEX IF NOT EXISTS idx_post_tags_post_id ON post_tags(post_id);
        CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status);
        CREATE INDEX IF NOT EXISTS idx_posts_parent_id ON posts(parent_id);

        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            folder_name TEXT NOT NULL,
            output_path TEXT,
            hotkey TEXT,
            sort_order INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS category_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            rule_type TEXT NOT NULL,
            tag TEXT NOT NULL,

            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_category_rules_tag ON category_rules(tag);

        CREATE TABLE IF NOT EXISTS post_categories (
            post_id INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            source TEXT NOT NULL DEFAULT 'auto',

            PRIMARY KEY (post_id, category_id),
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS filename_excluded_tags (
            tag TEXT PRIMARY KEY,
            reason TEXT
        );

        CREATE TABLE IF NOT EXISTS tag_aliases (
            original_tag TEXT PRIMARY KEY,
            alias_tag TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tag_scores (
            tag TEXT PRIMARY KEY,
            manual_score REAL DEFAULT NULL,
            computed_score REAL DEFAULT 0,
            accepted_count INTEGER DEFAULT 0,
            rejected_count INTEGER DEFAULT 0,
            average_rating REAL DEFAULT NULL
        );

        CREATE TABLE IF NOT EXISTS post_reviews (
            post_id INTEGER PRIMARY KEY,
            stars INTEGER,
            decision TEXT,
            category_id INTEGER,
            notes TEXT,
            reviewed_at TEXT,

            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE,
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS downloaded_history_import (
            post_id INTEGER PRIMARY KEY,
            filename TEXT,
            imported_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """

        if self.connection is None:
            raise RuntimeError("Datenbank ist nicht verbunden")

        self.connection.executescript(schema)
        self.commit()

    def upsert_category(
        self,
        name: str,
        folder_name: str,
        output_path: str | None,
        hotkey: str | None,
        sort_order: int,
    ) -> int:
        self.execute(
            """
            INSERT INTO categories (name, folder_name, output_path, hotkey, sort_order)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                folder_name = excluded.folder_name,
                output_path = excluded.output_path,
                hotkey = excluded.hotkey,
                sort_order = excluded.sort_order
            """,
            (name, folder_name, output_path, hotkey, sort_order),
        )
        self.commit()

        row = self.execute(
            "SELECT id FROM categories WHERE name = ?",
            (name,),
        ).fetchone()

        if row is None:
            raise RuntimeError(f"Kategorie konnte nicht gespeichert werden: {name}")

        return int(row["id"])

    def sync_static_config(self, config: dict[str, Any]) -> None:
        categories = normalize_categories(config.get("categories", []) or [])

        for index, category in enumerate(categories):
            category_id = self.upsert_category(
                name=category["name"],
                folder_name=category.get("folder_name", category["name"]),
                output_path=category.get("output_path"),
                hotkey=category.get("hotkey"),
                sort_order=index,
            )

            self.execute(
                "DELETE FROM category_rules WHERE category_id = ?",
                (category_id,),
            )

            for tag in category.get("include", []) or []:
                self.execute(
                    """
                    INSERT INTO category_rules (category_id, rule_type, tag)
                    VALUES (?, ?, ?)
                    """,
                    (category_id, "include", tag),
                )

            for tag in category.get("exclude", []) or []:
                self.execute(
                    """
                    INSERT INTO category_rules (category_id, rule_type, tag)
                    VALUES (?, ?, ?)
                    """,
                    (category_id, "exclude", tag),
                )

            include_groups = category.get("include_groups", []) or []
            for group_index, group in enumerate(include_groups):
                for tag in group:
                    self.execute(
                        """
                        INSERT INTO category_rules (category_id, rule_type, tag)
                        VALUES (?, ?, ?)
                        """,
                        (category_id, f"include_group_{group_index}", tag),
                    )

        filename = config.get("filename", {}) or {}
        for tag in filename.get("excluded_tags", []) or []:
            self.execute(
                """
                INSERT INTO filename_excluded_tags (tag, reason)
                VALUES (?, ?)
                ON CONFLICT(tag) DO NOTHING
                """,
                (tag, "config"),
            )

        llm = config.get("llm", {}) or {}
        aliases = llm.get("tag_aliases", {}) or {}
        for original, alias in aliases.items():
            self.execute(
                """
                INSERT INTO tag_aliases (original_tag, alias_tag)
                VALUES (?, ?)
                ON CONFLICT(original_tag) DO UPDATE SET
                    alias_tag = excluded.alias_tag
                """,
                (original, alias),
            )

        self.commit()

    def fetch_preview_posts(
        self,
        status_filter: str | None = None,
        text_filter: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[sqlite3.Row]:
        where_parts: list[str] = []
        parameters: list[Any] = []

        if status_filter and status_filter != "all":
            where_parts.append("p.status = ?")
            parameters.append(status_filter)

        if text_filter:
            pattern = f"%{text_filter.strip()}%"
            where_parts.append(
                """
                (
                    CAST(p.id AS TEXT) LIKE ?
                    OR EXISTS (
                        SELECT 1
                        FROM post_tags pt
                        WHERE pt.post_id = p.id
                        AND pt.tag LIKE ?
                    )
                )
                """
            )
            parameters.extend([pattern, pattern])

        where_sql = ""
        if where_parts:
            where_sql = "WHERE " + " AND ".join(where_parts)

        parameters.extend([limit, offset])

        cursor = self.execute(
            f"""
            SELECT
                p.id,
                p.rating,
                p.score,
                p.fav_count,
                p.thumbnail_path,
                p.parent_id,
                p.has_children,
                p.status,
                p.local_score,
                p.llm_score,
                p.final_score,
                (
                    SELECT GROUP_CONCAT(pt.tag, ' ')
                    FROM post_tags pt
                    WHERE pt.post_id = p.id
                    ORDER BY
                        CASE pt.tag_type
                            WHEN 'copyright' THEN 1
                            WHEN 'character' THEN 2
                            WHEN 'artist' THEN 3
                            WHEN 'general' THEN 4
                            WHEN 'meta' THEN 5
                            ELSE 9
                        END,
                        pt.tag
                ) AS tags
            FROM posts p
            {where_sql}
            ORDER BY p.id DESC
            LIMIT ?
            OFFSET ?
            """,
            parameters,
        )
        return list(cursor.fetchall())

    def count_preview_posts(
        self,
        status_filter: str | None = None,
        text_filter: str | None = None,
    ) -> int:
        where_parts: list[str] = []
        parameters: list[Any] = []

        if status_filter and status_filter != "all":
            where_parts.append("p.status = ?")
            parameters.append(status_filter)

        if text_filter:
            pattern = f"%{text_filter.strip()}%"
            where_parts.append(
                """
                (
                    CAST(p.id AS TEXT) LIKE ?
                    OR EXISTS (
                        SELECT 1
                        FROM post_tags pt
                        WHERE pt.post_id = p.id
                        AND pt.tag LIKE ?
                    )
                )
                """
            )
            parameters.extend([pattern, pattern])

        where_sql = ""
        if where_parts:
            where_sql = "WHERE " + " AND ".join(where_parts)

        row = self.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM posts p
            {where_sql}
            """,
            parameters,
        ).fetchone()

        return int(row["count"]) if row else 0

    def set_post_status(self, post_id: int, status: str) -> None:
        allowed = {
            "new",
            "potential",
            "review",
            "auto_rejected",
            "rejected",
            "accepted",
            "downloaded",
            "saved",
        }
        if status not in allowed:
            raise ValueError(f"Ungültiger Status: {status}")

        self.execute(
            """
            UPDATE posts
            SET status = ?
            WHERE id = ?
            """,
            (status, post_id),
        )
        self.commit()


def normalize_categories(raw_categories: Any) -> list[dict[str, Any]]:
    if raw_categories is None:
        return []

    normalized: list[dict[str, Any]] = []

    if isinstance(raw_categories, list):
        for item in raw_categories:
            if isinstance(item, dict):
                if "name" not in item:
                    raise ValueError(f"Kategorie ohne name: {item!r}")

                name = str(item["name"])

                normalized.append(
                    {
                        "name": name,
                        "folder_name": str(item.get("folder_name", name)),
                        "output_path": item.get("output_path"),
                        "hotkey": item.get("hotkey"),
                        "include": list(item.get("include", []) or []),
                        "exclude": list(item.get("exclude", []) or []),
                        "include_groups": list(item.get("include_groups", []) or []),
                    }
                )

            elif isinstance(item, str):
                normalized.append(
                    {
                        "name": item,
                        "folder_name": item,
                        "output_path": None,
                        "hotkey": None,
                        "include": [item],
                        "exclude": [],
                        "include_groups": [],
                    }
                )

            else:
                raise ValueError(f"Ungültiger Kategorieeintrag: {item!r}")

        return normalized

    if isinstance(raw_categories, dict):
        for name, value in raw_categories.items():
            if isinstance(value, list):
                normalized.append(
                    {
                        "name": str(name),
                        "folder_name": str(name),
                        "output_path": None,
                        "hotkey": None,
                        "include": list(value),
                        "exclude": [],
                        "include_groups": [],
                    }
                )

            elif isinstance(value, dict):
                normalized.append(
                    {
                        "name": str(name),
                        "folder_name": str(value.get("folder_name", name)),
                        "output_path": value.get("output_path"),
                        "hotkey": value.get("hotkey"),
                        "include": list(value.get("include", []) or []),
                        "exclude": list(value.get("exclude", []) or []),
                        "include_groups": list(value.get("include_groups", []) or []),
                    }
                )

            else:
                raise ValueError(f"Ungültige Kategorie '{name}': {value!r}")

        return normalized

    raise ValueError(f"Ungültiges categories-Format: {type(raw_categories).__name__}")
