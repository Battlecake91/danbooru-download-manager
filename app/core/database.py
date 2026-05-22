from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from typing import Any, Iterable


ACTIVE_STATUSES = {"new", "potential", "review", "selected_save"}

ALL_ALLOWED_STATUSES = {
    "new",
    "potential",
    "review",
    "selected_save",
    "auto_rejected",
    "rejected",
    "accepted",
    "already_known",
    "downloaded",
    "saved",
}


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
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS config_imports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name TEXT NOT NULL,
            imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
            note TEXT
        );

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
            image_width INTEGER,
            image_height INTEGER,
            file_size INTEGER,

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
        self.migrate_schema()
        self.create_safe_indexes()
        self.commit()

    def migrate_schema(self) -> None:
        self.add_column_if_missing("posts", "image_width", "INTEGER")
        self.add_column_if_missing("posts", "image_height", "INTEGER")
        self.add_column_if_missing("posts", "file_size", "INTEGER")
        self.add_column_if_missing("posts", "original_cache_path", "TEXT")
        self.add_column_if_missing("posts", "final_file_path", "TEXT")
        self.add_column_if_missing("posts", "final_directory", "TEXT")
        self.add_column_if_missing("posts", "rejected_thumbnail_path", "TEXT")
        self.add_column_if_missing("posts", "selected_at", "TEXT")
        self.add_column_if_missing("posts", "rejected_at", "TEXT")
        self.add_column_if_missing("posts", "already_known_at", "TEXT")
        self.migrate_personal_rating_to_0_10()

        self.execute(
            """
            UPDATE posts
            SET status = 'already_known',
                already_known_at = COALESCE(already_known_at, downloaded_at, CURRENT_TIMESTAMP)
            WHERE status = 'downloaded'
              AND final_file_path IS NULL
              AND id IN (SELECT post_id FROM downloaded_history_import)
            """
        )


    def migrate_personal_rating_to_0_10(self) -> None:
        marker = self.execute(
            "SELECT value FROM app_settings WHERE key = ?",
            ("migration.personal_rating_0_10",),
        ).fetchone()
        if marker is not None:
            return

        self.execute(
            """
            UPDATE post_reviews
            SET stars = ROUND(stars * 2)
            WHERE stars IS NOT NULL
              AND stars > 0
              AND stars <= 5
            """
        )
        self.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            ("migration.personal_rating_0_10", "true"),
        )

    def create_safe_indexes(self) -> None:
        # Alte Entwicklungsstände konnten duplicate rules erzeugen.
        # Vor dem Unique-Index wird aufgeräumt, sonst crasht SQLite beim Start.
        self.execute(
            """
            DELETE FROM category_rules
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM category_rules
                GROUP BY category_id, rule_type, tag
            )
            """
        )
        self.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_category_rules_unique
            ON category_rules(category_id, rule_type, tag)
            """
        )

    def add_column_if_missing(self, table_name: str, column_name: str, declaration: str) -> None:
        columns = self.execute(f"PRAGMA table_info({table_name})").fetchall()
        existing = {str(row["name"]) for row in columns}
        if column_name not in existing:
            self.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {declaration}")

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

            for tag in category.get("include", []) or []:
                self.add_category_rule(category_id, "include", str(tag))

            for tag in category.get("exclude", []) or []:
                self.add_category_rule(category_id, "exclude", str(tag))

            include_groups = category.get("include_groups", []) or []
            for group_index, group in enumerate(include_groups):
                for tag in group:
                    self.add_category_rule(category_id, f"include_group_{group_index}", str(tag))

        filename = config.get("filename", {}) or {}
        for tag in filename.get("excluded_tags", []) or []:
            self.add_filename_excluded_tag(str(tag), "config-import")

        llm = config.get("llm", {}) or {}
        aliases = llm.get("tag_aliases", {}) or {}
        for original, alias in aliases.items():
            self.set_tag_alias(str(original), str(alias))

        self.execute(
            """
            INSERT INTO config_imports (source_name, note)
            VALUES (?, ?)
            """,
            ("config.yaml", "non-destructive import"),
        )
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
                folder_name = COALESCE(NULLIF(excluded.folder_name, ''), categories.folder_name),
                output_path = COALESCE(excluded.output_path, categories.output_path),
                hotkey = COALESCE(excluded.hotkey, categories.hotkey),
                sort_order = excluded.sort_order
            """,
            (name, folder_name, output_path, hotkey, sort_order),
        )
        self.commit()

        row = self.execute("SELECT id FROM categories WHERE name = ?", (name,)).fetchone()
        if row is None:
            raise RuntimeError(f"Kategorie konnte nicht gespeichert werden: {name}")
        return int(row["id"])

    def create_category(self, name: str, folder_name: str | None = None) -> int:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Kategorie-Name darf nicht leer sein")

        return self.upsert_category(
            name=clean_name,
            folder_name=folder_name or clean_name,
            output_path=None,
            hotkey=None,
            sort_order=self.next_category_sort_order(),
        )

    def next_category_sort_order(self) -> int:
        row = self.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 AS next_order FROM categories").fetchone()
        return int(row["next_order"]) if row else 1

    def update_category(
        self,
        category_id: int,
        name: str,
        folder_name: str,
        output_path: str | None,
        hotkey: str | None,
        sort_order: int,
    ) -> None:
        self.execute(
            """
            UPDATE categories
            SET name = ?,
                folder_name = ?,
                output_path = ?,
                hotkey = ?,
                sort_order = ?
            WHERE id = ?
            """,
            (
                name.strip(),
                folder_name.strip() or name.strip(),
                output_path.strip() if output_path else None,
                hotkey.strip() if hotkey else None,
                sort_order,
                category_id,
            ),
        )
        self.commit()

    def delete_category(self, category_id: int) -> None:
        self.execute("DELETE FROM categories WHERE id = ?", (category_id,))
        self.commit()

    def list_categories_full(self) -> list[sqlite3.Row]:
        return list(
            self.execute(
                """
                SELECT id, name, folder_name, output_path, hotkey, sort_order
                FROM categories
                ORDER BY sort_order ASC, name ASC
                """
            ).fetchall()
        )

    def list_category_names(self) -> list[str]:
        return [str(row["name"]) for row in self.list_categories_full()]

    def get_category_by_name(self, name: str) -> sqlite3.Row | None:
        return self.execute(
            """
            SELECT id, name, folder_name, output_path, hotkey, sort_order
            FROM categories
            WHERE name = ?
            """,
            (name,),
        ).fetchone()

    def list_category_rules(self, category_id: int | None = None) -> list[sqlite3.Row]:
        if category_id is None:
            return list(
                self.execute(
                    """
                    SELECT cr.id, cr.category_id, c.name AS category_name, cr.rule_type, cr.tag
                    FROM category_rules cr
                    JOIN categories c ON c.id = cr.category_id
                    ORDER BY c.sort_order ASC, c.name ASC, cr.rule_type ASC, cr.tag ASC
                    """
                ).fetchall()
            )

        return list(
            self.execute(
                """
                SELECT cr.id, cr.category_id, c.name AS category_name, cr.rule_type, cr.tag
                FROM category_rules cr
                JOIN categories c ON c.id = cr.category_id
                WHERE cr.category_id = ?
                ORDER BY cr.rule_type ASC, cr.tag ASC
                """,
                (category_id,),
            ).fetchall()
        )

    def add_category_rule(self, category_id: int, rule_type: str, tag: str) -> None:
        clean_tag = tag.strip()
        if not clean_tag:
            return

        self.execute(
            """
            INSERT OR IGNORE INTO category_rules (category_id, rule_type, tag)
            VALUES (?, ?, ?)
            """,
            (category_id, rule_type, clean_tag),
        )
        self.commit()

    def add_tag_to_category_rule(self, category_name: str, tag: str, rule_type: str = "include") -> None:
        category = self.get_category_by_name(category_name)
        if category is None:
            raise RuntimeError(f"Kategorie nicht gefunden: {category_name}")
        self.add_category_rule(int(category["id"]), rule_type, tag)

    def delete_category_rule(self, rule_id: int) -> None:
        self.execute("DELETE FROM category_rules WHERE id = ?", (rule_id,))
        self.commit()

    def fetch_preview_posts(
        self,
        view_mode: str = "worklist",
        status_filter: str | None = None,
        text_filter: str | None = None,
        worklist_statuses: list[str] | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[sqlite3.Row]:
        where_sql, parameters = self._build_preview_where(
            view_mode=view_mode,
            status_filter=status_filter,
            text_filter=text_filter,
            worklist_statuses=worklist_statuses,
        )

        parameters.extend([limit, offset])

        return list(
            self.execute(
                f"""
                SELECT
                    p.id,
                    p.rating,
                    p.score,
                    p.fav_count,
                    p.thumbnail_path,
                    p.rejected_thumbnail_path,
                    p.parent_id,
                    p.has_children,
                    p.status,
                    p.local_score,
                    p.llm_score,
                    p.final_score,
                    p.final_file_path,
                    p.final_directory,
                    p.rejected_at,
                    p.saved_at,
                    p.already_known_at,

                    CASE
                        WHEN p.parent_id IS NOT NULL
                         AND EXISTS (
                             SELECT 1
                             FROM posts parent
                             WHERE parent.id = p.parent_id
                               AND parent.final_file_path IS NOT NULL
                               AND parent.final_file_path != ''
                         )
                        THEN 1
                        ELSE 0
                    END AS known_parent_loaded,

                    (
                        SELECT COUNT(*)
                        FROM posts child
                        WHERE child.parent_id = p.id
                          AND child.final_file_path IS NOT NULL
                          AND child.final_file_path != ''
                    ) AS known_child_count,

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
            ).fetchall()
        )

    def count_preview_posts(
        self,
        view_mode: str = "worklist",
        status_filter: str | None = None,
        text_filter: str | None = None,
        worklist_statuses: list[str] | None = None,
    ) -> int:
        where_sql, parameters = self._build_preview_where(
            view_mode=view_mode,
            status_filter=status_filter,
            text_filter=text_filter,
            worklist_statuses=worklist_statuses,
        )

        row = self.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM posts p
            {where_sql}
            """,
            parameters,
        ).fetchone()

        return int(row["count"]) if row else 0

    def _build_preview_where(
        self,
        view_mode: str,
        status_filter: str | None,
        text_filter: str | None,
        worklist_statuses: list[str] | None,
    ) -> tuple[str, list[Any]]:
        where_parts: list[str] = []
        parameters: list[Any] = []

        has_specific_status_filter = bool(status_filter and status_filter != "all")

        # Bei aktiver Text-/Tag-Suche wird bewusst über alle Status gesucht,
        # damit bereits lokal gespeicherte Bilder über Tags auffindbar bleiben.
        # Sonst versteckt die Arbeitsliste exakt die Dateien, die man sucht. Klassiker.
        if not text_filter:
            if view_mode == "worklist" and not has_specific_status_filter:
                statuses = worklist_statuses or sorted(ACTIVE_STATUSES)
                placeholders = ", ".join("?" for _ in statuses)
                where_parts.append(f"p.status IN ({placeholders})")
                parameters.extend(statuses)
            elif view_mode == "saved" and not has_specific_status_filter:
                where_parts.append("p.status = ?")
                parameters.append("saved")
            elif view_mode == "rejected" and not has_specific_status_filter:
                where_parts.append("p.status IN (?, ?)")
                parameters.extend(["rejected", "auto_rejected"])
            elif view_mode == "known" and not has_specific_status_filter:
                where_parts.append("p.status IN (?, ?)")
                parameters.extend(["already_known", "downloaded"])
            elif view_mode == "all" or has_specific_status_filter:
                pass
            else:
                raise ValueError(f"Ungültiger view_mode: {view_mode}")

            if has_specific_status_filter:
                where_parts.append("p.status = ?")
                parameters.append(status_filter)

        if text_filter:
            pattern = f"%{text_filter.strip()}%"
            where_parts.append(
                """
                (
                    CAST(p.id AS TEXT) LIKE ?
                    OR p.final_file_path LIKE ?
                    OR p.final_directory LIKE ?
                    OR EXISTS (
                        SELECT 1
                        FROM post_tags pt
                        WHERE pt.post_id = p.id
                        AND pt.tag LIKE ?
                    )
                )
                """
            )
            parameters.extend([pattern, pattern, pattern, pattern])

        where_sql = ""
        if where_parts:
            where_sql = "WHERE " + " AND ".join(where_parts)

        return where_sql, parameters

    def get_post_detail(self, post_id: int) -> sqlite3.Row | None:
        return self.execute(
            """
            SELECT
                p.*,
                CASE
                    WHEN p.parent_id IS NOT NULL
                     AND EXISTS (
                         SELECT 1
                         FROM posts parent
                         WHERE parent.id = p.parent_id
                           AND parent.final_file_path IS NOT NULL
                           AND parent.final_file_path != ''
                     )
                    THEN 1
                    ELSE 0
                END AS known_parent_loaded,
                (
                    SELECT COUNT(*)
                    FROM posts child
                    WHERE child.parent_id = p.id
                      AND child.final_file_path IS NOT NULL
                      AND child.final_file_path != ''
                ) AS known_child_count,
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
                ) AS tags,
                (
                    SELECT stars
                    FROM post_reviews pr
                    WHERE pr.post_id = p.id
                ) AS stars
            FROM posts p
            WHERE p.id = ?
            """,
            (post_id,),
        ).fetchone()

    def get_related_posts(self, post_id: int) -> list[sqlite3.Row]:
        current = self.execute("SELECT id, parent_id FROM posts WHERE id = ?", (post_id,)).fetchone()
        if current is None:
            return []

        rows: list[sqlite3.Row] = []

        parent_id = current["parent_id"]
        if parent_id is not None:
            parent = self.execute(
                """
                SELECT
                    'parent' AS relation,
                    id,
                    parent_id,
                    status,
                    rating,
                    score,
                    final_file_path,
                    thumbnail_path,
                    rejected_thumbnail_path
                FROM posts
                WHERE id = ?
                """,
                (parent_id,),
            ).fetchone()
            if parent is not None:
                rows.append(parent)

        rows.extend(
            self.execute(
                """
                SELECT
                    'child' AS relation,
                    id,
                    parent_id,
                    status,
                    rating,
                    score,
                    final_file_path,
                    thumbnail_path,
                    rejected_thumbnail_path
                FROM posts
                WHERE parent_id = ?
                ORDER BY id DESC
                """,
                (post_id,),
            ).fetchall()
        )

        return rows


    def update_post_remote_metadata(self, post_id: int, post: dict[str, Any]) -> None:
        self.execute(
            """
            UPDATE posts
            SET image_width = COALESCE(?, image_width),
                image_height = COALESCE(?, image_height),
                file_size = COALESCE(?, file_size),
                file_url = COALESCE(NULLIF(?, ''), file_url),
                large_file_url = COALESCE(NULLIF(?, ''), large_file_url),
                preview_url = COALESCE(NULLIF(?, ''), preview_url),
                file_ext = COALESCE(NULLIF(?, ''), file_ext),
                last_seen_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                post.get("image_width"),
                post.get("image_height"),
                post.get("file_size"),
                str(post.get("file_url") or ""),
                str(post.get("large_file_url") or ""),
                str(post.get("preview_file_url") or post.get("preview_url") or ""),
                str(post.get("file_ext") or ""),
                post_id,
            ),
        )
        self.commit()

    def fetch_saved_posts_for_quality_audit(self) -> list[sqlite3.Row]:
        return list(
            self.execute(
                """
                SELECT
                    id,
                    file_url,
                    file_ext,
                    image_width,
                    image_height,
                    file_size,
                    final_file_path,
                    final_directory,
                    original_cache_path
                FROM posts
                WHERE final_file_path IS NOT NULL
                  AND final_file_path != ''
                ORDER BY saved_at DESC, id DESC
                """
            ).fetchall()
        )

    def set_original_cache_path(self, post_id: int, path: str) -> None:
        self.execute(
            """
            UPDATE posts
            SET original_cache_path = ?,
                downloaded_at = COALESCE(downloaded_at, CURRENT_TIMESTAMP)
            WHERE id = ?
            """,
            (path, post_id),
        )
        self.commit()

    def set_post_review(self, post_id: int, stars: float | None = None, decision: str | None = None) -> None:
        self.execute(
            """
            INSERT INTO post_reviews (post_id, stars, decision, reviewed_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(post_id) DO UPDATE SET
                stars = COALESCE(excluded.stars, post_reviews.stars),
                decision = COALESCE(excluded.decision, post_reviews.decision),
                reviewed_at = CURRENT_TIMESTAMP
            """,
            (post_id, stars, decision),
        )
        self.execute("UPDATE posts SET reviewed_at = CURRENT_TIMESTAMP WHERE id = ?", (post_id,))
        self.commit()

    def set_post_status(self, post_id: int, status: str, config: dict[str, Any] | None = None) -> None:
        if status not in ALL_ALLOWED_STATUSES:
            raise ValueError(f"Ungültiger Status: {status}")

        extra_sets: list[str] = []
        parameters: list[Any] = [status]

        if status == "selected_save":
            extra_sets.append("selected_at = COALESCE(selected_at, CURRENT_TIMESTAMP)")
        elif status in {"rejected", "auto_rejected"}:
            extra_sets.append("rejected_at = COALESCE(rejected_at, CURRENT_TIMESTAMP)")
        elif status == "saved":
            extra_sets.append("saved_at = COALESCE(saved_at, CURRENT_TIMESTAMP)")
        elif status == "already_known":
            extra_sets.append("already_known_at = COALESCE(already_known_at, CURRENT_TIMESTAMP)")

        if config is not None:
            moved_thumbnail_path = None
            if status in {"rejected", "auto_rejected"}:
                moved_thumbnail_path = self.move_thumbnail_to_bucket(post_id, Path(config["rejected_thumbnail_dir"]))
                if moved_thumbnail_path:
                    extra_sets.append("rejected_thumbnail_path = ?")
                    parameters.append(moved_thumbnail_path)
            elif status == "saved":
                moved_thumbnail_path = self.move_thumbnail_to_bucket(post_id, Path(config["saved_thumbnail_dir"]))
                if moved_thumbnail_path:
                    extra_sets.append("thumbnail_path = ?")
                    parameters.append(moved_thumbnail_path)

        set_sql = "status = ?"
        if extra_sets:
            set_sql += ", " + ", ".join(extra_sets)

        parameters.append(post_id)

        self.execute(
            f"""
            UPDATE posts
            SET {set_sql}
            WHERE id = ?
            """,
            parameters,
        )
        self.commit()

    def move_thumbnail_to_bucket(self, post_id: int, target_dir: Path) -> str | None:
        row = self.execute(
            "SELECT thumbnail_path, rejected_thumbnail_path FROM posts WHERE id = ?",
            (post_id,),
        ).fetchone()

        if row is None:
            return None

        source_value = row["thumbnail_path"] or row["rejected_thumbnail_path"]
        if not source_value:
            return None

        source = Path(str(source_value))
        if not source.exists():
            return None

        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / source.name

        if source.resolve() == target.resolve():
            return str(target)

        shutil.move(str(source), str(target))
        return str(target)


    def assign_post_category(self, post_id: int, category_id: int, source: str = "manual") -> None:
        """Store exactly one effective category assignment for a post."""
        self.execute("DELETE FROM post_categories WHERE post_id = ?", (post_id,))
        self.execute(
            """
            INSERT INTO post_categories (post_id, category_id, source)
            VALUES (?, ?, ?)
            """,
            (post_id, category_id, source),
        )
        self.commit()

    def assign_post_category_by_name(self, post_id: int, category_name: str, source: str = "manual") -> None:
        category = self.get_category_by_name(category_name)
        if category is None:
            raise RuntimeError(f"Kategorie nicht gefunden: {category_name}")
        self.assign_post_category(post_id, int(category["id"]), source)

    def get_assigned_category_for_post(self, post_id: int) -> sqlite3.Row | None:
        return self.execute(
            """
            SELECT c.*, pc.source AS assignment_source
            FROM post_categories pc
            JOIN categories c ON c.id = pc.category_id
            WHERE pc.post_id = ?
            ORDER BY CASE pc.source WHEN 'manual' THEN 0 ELSE 1 END, c.sort_order, c.name
            LIMIT 1
            """,
            (post_id,),
        ).fetchone()


    def delete_post_record(self, post_id: int) -> None:
        """Remove one post and dependent DB rows, but do not delete image files."""
        self.execute("DELETE FROM post_reviews WHERE post_id = ?", (post_id,))
        self.execute("DELETE FROM post_categories WHERE post_id = ?", (post_id,))
        self.execute("DELETE FROM post_tags WHERE post_id = ?", (post_id,))
        self.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        self.commit()

    def fetch_tag_overview(
        self,
        search_text: str | None = None,
        tag_type: str | None = None,
        limit: int = 1000,
    ) -> list[sqlite3.Row]:
        where_parts: list[str] = []
        parameters: list[Any] = []

        if search_text:
            where_parts.append("pt.tag LIKE ?")
            parameters.append(f"%{search_text.strip()}%")

        if tag_type and tag_type != "all":
            where_parts.append("pt.tag_type = ?")
            parameters.append(tag_type)

        where_sql = ""
        if where_parts:
            where_sql = "WHERE " + " AND ".join(where_parts)

        parameters.append(limit)

        return list(
            self.execute(
                f"""
                SELECT
                    pt.tag AS tag,
                    MIN(pt.tag_type) AS tag_type,
                    COUNT(DISTINCT pt.post_id) AS post_count,

                    SUM(CASE WHEN p.status = 'saved' THEN 1 ELSE 0 END) AS saved_count,
                    SUM(CASE WHEN p.status IN ('rejected', 'auto_rejected') THEN 1 ELSE 0 END) AS rejected_count,
                    SUM(CASE WHEN p.status IN ('new', 'potential', 'review', 'selected_save') THEN 1 ELSE 0 END) AS open_count,

                    COALESCE(ts.manual_score, '') AS manual_score,
                    COALESCE(ts.computed_score, 0) AS computed_score,
                    COALESCE(ts.average_rating, '') AS average_rating,

                    ta.alias_tag AS alias_tag,

                    CASE WHEN fet.tag IS NULL THEN 0 ELSE 1 END AS filename_excluded

                FROM post_tags pt
                JOIN posts p ON p.id = pt.post_id
                LEFT JOIN tag_scores ts ON ts.tag = pt.tag
                LEFT JOIN tag_aliases ta ON ta.original_tag = pt.tag
                LEFT JOIN filename_excluded_tags fet ON fet.tag = pt.tag
                {where_sql}
                GROUP BY pt.tag
                ORDER BY post_count DESC, pt.tag ASC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        )

    def add_filename_excluded_tag(self, tag: str, reason: str = "manual") -> None:
        clean_tag = tag.strip()
        if not clean_tag:
            return

        self.execute(
            """
            INSERT INTO filename_excluded_tags (tag, reason)
            VALUES (?, ?)
            ON CONFLICT(tag) DO UPDATE SET reason = excluded.reason
            """,
            (clean_tag, reason),
        )
        self.commit()

    def remove_filename_excluded_tag(self, tag: str) -> None:
        self.execute("DELETE FROM filename_excluded_tags WHERE tag = ?", (tag,))
        self.commit()

    def list_filename_excluded_tags(self, search_text: str | None = None) -> list[sqlite3.Row]:
        if search_text:
            return list(
                self.execute(
                    """
                    SELECT tag, reason
                    FROM filename_excluded_tags
                    WHERE tag LIKE ?
                    ORDER BY tag ASC
                    """,
                    (f"%{search_text.strip()}%",),
                ).fetchall()
            )

        return list(
            self.execute(
                """
                SELECT tag, reason
                FROM filename_excluded_tags
                ORDER BY tag ASC
                """
            ).fetchall()
        )

    def filename_excluded_tag_set(self) -> set[str]:
        rows = self.execute("SELECT tag FROM filename_excluded_tags").fetchall()
        return {str(row["tag"]) for row in rows}

    def set_tag_alias(self, tag: str, alias: str) -> None:
        clean_tag = tag.strip()
        clean_alias = alias.strip()

        if not clean_tag:
            return

        if not clean_alias:
            self.execute("DELETE FROM tag_aliases WHERE original_tag = ?", (clean_tag,))
        else:
            self.execute(
                """
                INSERT INTO tag_aliases (original_tag, alias_tag)
                VALUES (?, ?)
                ON CONFLICT(original_tag) DO UPDATE SET alias_tag = excluded.alias_tag
                """,
                (clean_tag, clean_alias),
            )
        self.commit()

    def set_tag_manual_score(self, tag: str, score: float | None) -> None:
        clean_tag = tag.strip()
        if not clean_tag:
            return

        self.execute(
            """
            INSERT INTO tag_scores (tag, manual_score)
            VALUES (?, ?)
            ON CONFLICT(tag) DO UPDATE SET manual_score = excluded.manual_score
            """,
            (clean_tag, score),
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
