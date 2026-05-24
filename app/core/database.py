from __future__ import annotations

import json
import secrets
import shlex
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

from app.core.tag_privacy import build_tag_identity, canonicalize_tag, normalize_tag_token


ACTIVE_STATUSES = {"new", "potential"}

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


def parse_preview_search_terms(search_text: str) -> tuple[list[str], list[str]]:
    """Parse preview search into include and exclude terms.

    Example: ``brown_eyes -red_hair`` means: must match brown_eyes,
    must not have red_hair as tag. Quoted terms are supported because even
    search strings deserve a tiny bit of dignity.
    """
    try:
        tokens = shlex.split(search_text)
    except ValueError:
        tokens = search_text.split()

    positive: list[str] = []
    negative: list[str] = []

    for token in tokens:
        token = token.strip()
        if not token:
            continue
        if token.startswith("-") and len(token) > 1:
            negative.append(token[1:].strip())
        else:
            positive.append(token)

    return positive, negative


def is_path_like_preview_search_term(term: str) -> bool:
    return any(marker in term for marker in ("/", "\\", "."))


def clamp_number(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def calculate_computed_tag_score(
    *,
    average_rating: Any,
    saved_count: int,
    rejected_count: int,
    scoring_excluded: bool = False,
) -> float:
    """Compute a conservative automatic tag score.

    The score combines user stars and saved/rejected statistics, but heavily
    dampens extremely common tags. Otherwise `1girl` would become a fake
    villain just because it appears in almost everything. Computers love that
    kind of statistical stupidity, so we put a fence around it.
    """
    if scoring_excluded:
        return 0.0

    sample_count = int(saved_count or 0) + int(rejected_count or 0)
    star_signal = 0.0
    if average_rating not in {None, "", "None"}:
        try:
            # 0..10 stars -> about -2.5..+2.5. Good/bad, but not a dictator.
            star_signal = clamp_number((float(average_rating) - 5.0) / 2.0, -2.5, 2.5)
        except (TypeError, ValueError):
            star_signal = 0.0

    accept_signal = 0.0
    if sample_count >= 20:
        accept_rate = (float(saved_count or 0) + 1.0) / (float(sample_count) + 2.0)
        accept_signal = clamp_number((accept_rate - 0.5) * 10.0, -5.0, 5.0)

        # Confidence grows with samples, but caps early. 20 samples are a hint,
        # 100+ are usually enough.
        confidence = clamp_number(sample_count / 100.0, 0.2, 1.0)

        # Very common tags are usually weak predictors. If both sides have lots
        # of examples, we damp the signal hard instead of letting generic tags
        # like `1girl` bulldoze the result.
        generic_damping = 1.0
        if sample_count >= 1000 and saved_count >= 100 and rejected_count >= 100:
            generic_damping = 0.25
        elif sample_count >= 500 and saved_count >= 50 and rejected_count >= 50:
            generic_damping = 0.45

        accept_signal *= confidence * generic_damping

    return round(clamp_number(star_signal + accept_signal, -5.0, 5.0), 2)


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.connection: sqlite3.Connection | None = None

    def connect(self) -> None:
        # timeout/busy_timeout verhindern, dass zwei GUI-/Worker-Verbindungen
        # bei kurzer Last sofort gegeneinander verlieren. SQLite kann WAL, aber
        # Zauberei ist es nicht. Ein bisschen Geduld muss man ihm leider beibringen.
        self.connection = sqlite3.connect(self.path, timeout=30.0)
        self.connection.row_factory = sqlite3.Row
        self.execute("PRAGMA busy_timeout = 30000")
        self.execute("PRAGMA foreign_keys = ON")
        self.execute("PRAGMA journal_mode = WAL")

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def _is_database_locked_error(self, exc: sqlite3.OperationalError) -> bool:
        text = str(exc).lower()
        return "database is locked" in text or "database table is locked" in text

    def _lock_retry_delays(self) -> tuple[float, ...]:
        # Insgesamt knapp 12 Sekunden zusätzlich zu sqlite busy_timeout. Das ist
        # lang genug für Preview-Reloads, aber kurz genug, um echte Deadlocks nicht
        # als meditative Übung zu tarnen.
        return (0.05, 0.10, 0.20, 0.35, 0.50, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0)

    def execute(self, sql: str, parameters: Iterable[Any] = ()) -> sqlite3.Cursor:
        if self.connection is None:
            raise RuntimeError("Datenbank ist nicht verbunden")
        params = tuple(parameters)
        for delay in self._lock_retry_delays():
            try:
                return self.connection.execute(sql, params)
            except sqlite3.OperationalError as exc:
                if not self._is_database_locked_error(exc):
                    raise
                time.sleep(delay)
        return self.connection.execute(sql, params)

    def executemany(self, sql: str, rows: Iterable[Iterable[Any]]) -> sqlite3.Cursor:
        if self.connection is None:
            raise RuntimeError("Datenbank ist nicht verbunden")
        materialized_rows = [tuple(row) for row in rows]
        for delay in self._lock_retry_delays():
            try:
                return self.connection.executemany(sql, materialized_rows)
            except sqlite3.OperationalError as exc:
                if not self._is_database_locked_error(exc):
                    raise
                time.sleep(delay)
        return self.connection.executemany(sql, materialized_rows)

    def commit(self) -> None:
        if self.connection is None:
            raise RuntimeError("Datenbank ist nicht verbunden")
        for delay in self._lock_retry_delays():
            try:
                self.connection.commit()
                return
            except sqlite3.OperationalError as exc:
                if not self._is_database_locked_error(exc):
                    raise
                time.sleep(delay)
        self.connection.commit()

    def initialize_schema(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS fetch_presets (
            name TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
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
        CREATE INDEX IF NOT EXISTS idx_post_tags_type_tag ON post_tags(tag_type, tag);
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

        CREATE TABLE IF NOT EXISTS tag_identity_cache (
            original_tag TEXT PRIMARY KEY,
            canonical_tag TEXT NOT NULL,
            llm_token TEXT NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_tag_identity_canonical
        ON tag_identity_cache(canonical_tag);

        CREATE INDEX IF NOT EXISTS idx_tag_identity_llm_token
        ON tag_identity_cache(llm_token);

        CREATE TABLE IF NOT EXISTS tag_scores (
            tag TEXT PRIMARY KEY,
            manual_score REAL DEFAULT NULL,
            computed_score REAL DEFAULT 0,
            accepted_count INTEGER DEFAULT 0,
            rejected_count INTEGER DEFAULT 0,
            average_rating REAL DEFAULT NULL,
            scoring_excluded INTEGER DEFAULT 0,
            ignore_category_influence INTEGER DEFAULT 0,
            ignore_recommendation_score INTEGER DEFAULT 0,
            ignore_llm_input INTEGER DEFAULT 0
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

        stats_row = self.execute(
            "SELECT value FROM app_settings WHERE key = ?",
            ("maintenance.tag_stats_initialized_1_3_42",),
        ).fetchone()
        if stats_row is None or str(stats_row["value"] or "") != "1":
            self.refresh_all_tag_statistics()
            self.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                ("maintenance.tag_stats_initialized_1_3_42", "1"),
            )

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
        self.add_column_if_missing("tag_scores", "scoring_excluded", "INTEGER DEFAULT 0")
        self.add_column_if_missing("tag_scores", "ignore_category_influence", "INTEGER DEFAULT 0")
        self.add_column_if_missing("tag_scores", "ignore_recommendation_score", "INTEGER DEFAULT 0")
        self.add_column_if_missing("tag_scores", "ignore_llm_input", "INTEGER DEFAULT 0")
        self.ensure_llm_hash_salt()
        self.migrate_personal_rating_to_0_10()
        self.migrate_legacy_statuses()

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


    def migrate_legacy_statuses(self) -> None:
        """Collapse UI-deprecated statuses into the current workflow statuses."""
        self.execute("UPDATE posts SET status = 'new' WHERE status IN ('review', 'selected_save')")
        self.execute("UPDATE posts SET status = 'rejected', rejected_at = COALESCE(rejected_at, CURRENT_TIMESTAMP) WHERE status = 'auto_rejected'")
        self.execute("UPDATE posts SET status = 'potential' WHERE status = 'accepted'")
        self.execute("UPDATE posts SET status = 'already_known', already_known_at = COALESCE(already_known_at, downloaded_at, CURRENT_TIMESTAMP) WHERE status = 'downloaded'")
        self.execute(
            """
            UPDATE app_settings
            SET value = '["new", "potential"]', updated_at = CURRENT_TIMESTAMP
            WHERE key = 'workflow.worklist_statuses'
              AND value != '["new", "potential"]'
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
        self.execute("CREATE INDEX IF NOT EXISTS idx_posts_score ON posts(score)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_posts_saved_at ON posts(saved_at)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_posts_last_seen_at ON posts(last_seen_at)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_posts_rating ON posts(rating)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_posts_file_size ON posts(file_size)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_posts_resolution ON posts(image_width, image_height)")

        # Viewer hot path: category influence and tag display metadata need these
        # joins constantly. Without them SQLite gets to cosplay as a space heater
        # on every image switch.
        self.execute("CREATE INDEX IF NOT EXISTS idx_post_tags_tag_post ON post_tags(tag, post_id)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_post_tags_post_tag ON post_tags(post_id, tag)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_post_categories_post_category ON post_categories(post_id, category_id)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_post_categories_category_post ON post_categories(category_id, post_id)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_post_reviews_post ON post_reviews(post_id)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_tag_scores_tag ON tag_scores(tag)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_tag_aliases_original ON tag_aliases(original_tag)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_filename_excluded_tags_tag ON filename_excluded_tags(tag)")

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

    def delete_category_rules_for_category(self, category_id: int) -> None:
        self.execute("DELETE FROM category_rules WHERE category_id = ?", (category_id,))
        self.commit()

    @staticmethod
    def parse_category_group_expression(expression: str) -> tuple[list[str], list[str]]:
        import re

        includes: list[str] = []
        excludes: list[str] = []
        for token in [part.strip() for part in re.split(r"[\s,;]+", expression.strip()) if part.strip()]:
            if token == "-":
                continue
            if token.startswith("-") and len(token) > 1:
                tag = token[1:].strip()
                if tag and tag not in excludes:
                    excludes.append(tag)
            elif token not in includes:
                includes.append(token)
        return includes, excludes

    def replace_category_rule_groups(
        self,
        category_id: int,
        group_expressions: list[str],
        global_expressions: list[str] | None = None,
    ) -> None:
        """Replace category rules with intuitive groups.

        group_expressions are OR branches. global_expressions are AND conditions
        applied to every branch. Tokens without '-' are required tags, tokens
        with '-' are forbidden tags.
        """
        self.execute("DELETE FROM category_rules WHERE category_id = ?", (category_id,))

        def insert_expression(prefix: str, index: int, expression: str) -> None:
            includes, excludes = self.parse_category_group_expression(expression)
            if not includes and not excludes:
                return

            for tag in includes:
                self.execute(
                    """
                    INSERT OR IGNORE INTO category_rules (category_id, rule_type, tag)
                    VALUES (?, ?, ?)
                    """,
                    (category_id, f"{prefix}_{index}_include", tag),
                )
            for tag in excludes:
                self.execute(
                    """
                    INSERT OR IGNORE INTO category_rules (category_id, rule_type, tag)
                    VALUES (?, ?, ?)
                    """,
                    (category_id, f"{prefix}_{index}_exclude", tag),
                )

        for group_index, expression in enumerate(group_expressions):
            insert_expression("group", group_index, expression)

        for global_index, expression in enumerate(global_expressions or []):
            insert_expression("global", global_index, expression)

        self.commit()

    def normalize_category_sort_order(self) -> None:
        """Write dense 1-based priority values in the current effective order."""
        rows = self.list_categories_full()
        for index, row in enumerate(rows, start=1):
            if int(row["sort_order"] or 0) != index:
                self.execute(
                    "UPDATE categories SET sort_order = ? WHERE id = ?",
                    (index, int(row["id"])),
                )
        self.commit()

    def set_category_priority_order(self, ordered_category_ids: list[int]) -> None:
        """Persist the visible category order. The first row has highest priority."""
        if not ordered_category_ids:
            return

        known_ids = {int(row["id"]) for row in self.list_categories_full()}
        for index, category_id in enumerate(ordered_category_ids, start=1):
            if int(category_id) not in known_ids:
                continue
            self.execute(
                "UPDATE categories SET sort_order = ? WHERE id = ?",
                (index, int(category_id)),
            )
        self.commit()

    def move_category_sort_order(self, category_id: int, direction: int) -> None:
        """Move a category up/down in priority order. direction -1 = up, +1 = down."""
        rows = self.list_categories_full()
        ids = [int(row["id"]) for row in rows]
        if category_id not in ids:
            return

        index = ids.index(category_id)
        target = index + (-1 if direction < 0 else 1)
        if target < 0 or target >= len(ids):
            return

        ids[index], ids[target] = ids[target], ids[index]
        self.set_category_priority_order(ids)

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
                    ) AS tags,
                    (
                        SELECT GROUP_CONCAT(pt.tag, ' ')
                        FROM post_tags pt
                        WHERE pt.post_id = p.id AND pt.tag_type = 'general'
                        ORDER BY pt.tag
                    ) AS tags_general,
                    (
                        SELECT GROUP_CONCAT(pt.tag, ' ')
                        FROM post_tags pt
                        WHERE pt.post_id = p.id AND pt.tag_type = 'character'
                        ORDER BY pt.tag
                    ) AS tags_character,
                    (
                        SELECT GROUP_CONCAT(pt.tag, ' ')
                        FROM post_tags pt
                        WHERE pt.post_id = p.id AND pt.tag_type = 'copyright'
                        ORDER BY pt.tag
                    ) AS tags_copyright,
                    (
                        SELECT GROUP_CONCAT(pt.tag, ' ')
                        FROM post_tags pt
                        WHERE pt.post_id = p.id AND pt.tag_type = 'artist'
                        ORDER BY pt.tag
                    ) AS tags_artist,
                    (
                        SELECT GROUP_CONCAT(pt.tag, ' ')
                        FROM post_tags pt
                        WHERE pt.post_id = p.id AND pt.tag_type = 'meta'
                        ORDER BY pt.tag
                    ) AS tags_meta
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
                parameters.append("rejected")
            elif view_mode == "known" and not has_specific_status_filter:
                where_parts.append("p.status IN (?, ?)")
                parameters.append("already_known")
            elif view_mode == "all" or has_specific_status_filter:
                pass
            else:
                raise ValueError(f"Ungültiger view_mode: {view_mode}")

            if has_specific_status_filter:
                where_parts.append("p.status = ?")
                parameters.append(status_filter)

        if text_filter:
            positive_terms, negative_terms = parse_preview_search_terms(text_filter)

            for term in positive_terms:
                pattern = f"%{term}%"
                if is_path_like_preview_search_term(term):
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
                                  AND pt.tag = ? COLLATE NOCASE
                            )
                        )
                        """
                    )
                    parameters.extend([pattern, pattern, pattern, term])
                else:
                    where_parts.append(
                        """
                        (
                            CAST(p.id AS TEXT) LIKE ?
                            OR EXISTS (
                                SELECT 1
                                FROM post_tags pt
                                WHERE pt.post_id = p.id
                                  AND pt.tag = ? COLLATE NOCASE
                            )
                        )
                        """
                    )
                    parameters.extend([pattern, term])

            for term in negative_terms:
                where_parts.append(
                    """
                    NOT EXISTS (
                        SELECT 1
                        FROM post_tags pt_excl
                        WHERE pt_excl.post_id = p.id
                          AND pt_excl.tag = ? COLLATE NOCASE
                    )
                    """
                )
                parameters.append(term)

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
                    SELECT GROUP_CONCAT(pt.tag, ' ')
                    FROM post_tags pt
                    WHERE pt.post_id = p.id AND pt.tag_type = 'general'
                    ORDER BY pt.tag
                ) AS tags_general,
                (
                    SELECT GROUP_CONCAT(pt.tag, ' ')
                    FROM post_tags pt
                    WHERE pt.post_id = p.id AND pt.tag_type = 'character'
                    ORDER BY pt.tag
                ) AS tags_character,
                (
                    SELECT GROUP_CONCAT(pt.tag, ' ')
                    FROM post_tags pt
                    WHERE pt.post_id = p.id AND pt.tag_type = 'copyright'
                    ORDER BY pt.tag
                ) AS tags_copyright,
                (
                    SELECT GROUP_CONCAT(pt.tag, ' ')
                    FROM post_tags pt
                    WHERE pt.post_id = p.id AND pt.tag_type = 'artist'
                    ORDER BY pt.tag
                ) AS tags_artist,
                (
                    SELECT GROUP_CONCAT(pt.tag, ' ')
                    FROM post_tags pt
                    WHERE pt.post_id = p.id AND pt.tag_type = 'meta'
                    ORDER BY pt.tag
                ) AS tags_meta,
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
        self.refresh_tag_statistics_for_post(post_id)
        self.commit()

    def set_post_status(self, post_id: int, status: str, config: dict[str, Any] | None = None) -> None:
        self._set_post_status_no_commit(post_id, status, config)
        self.refresh_tag_statistics_for_post(post_id)
        self.commit()

    def set_post_statuses(self, post_ids: list[int], status: str, config: dict[str, Any] | None = None) -> None:
        clean_ids = []
        seen: set[int] = set()
        for post_id in post_ids:
            post_id_int = int(post_id)
            if post_id_int in seen:
                continue
            seen.add(post_id_int)
            clean_ids.append(post_id_int)

        if not clean_ids:
            return

        if status not in ALL_ALLOWED_STATUSES:
            raise ValueError(f"Ungültiger Status: {status}")

        scoring_statuses = {"saved", "rejected", "auto_rejected"}
        old_statuses = self._fetch_statuses_for_posts(clean_ids)
        needs_tag_statistics_refresh = status in scoring_statuses or any(
            old_status in scoring_statuses for old_status in old_statuses.values()
        )
        affected_tags = self._fetch_tags_for_posts(clean_ids) if needs_tag_statistics_refresh else []

        for post_id in clean_ids:
            self._set_post_status_no_commit(post_id, status, config)

        # Wichtig fuer den Previewer: Bei 100 markierten Thumbnails darf nicht fuer
        # jeden Post einzeln dieselbe Tag-Statistik neu aggregiert werden. Das war
        # technisch korrekt, aber performanceseitig etwa so elegant wie ein
        # Datenbank-Join mit Betonschuhen. Wir aktualisieren die vereinigte Tagmenge
        # genau einmal, und nur wenn saved/rejected fuer die Score-Berechnung
        # ueberhaupt betroffen ist.
        if affected_tags:
            self.refresh_tag_statistics_for_tags(affected_tags)

        self.commit()

    def _fetch_statuses_for_posts(self, post_ids: list[int]) -> dict[int, str]:
        clean_ids = [int(post_id) for post_id in post_ids]
        if not clean_ids:
            return {}

        placeholders = ", ".join("?" for _ in clean_ids)
        rows = self.execute(
            f"SELECT id, status FROM posts WHERE id IN ({placeholders})",
            clean_ids,
        ).fetchall()
        return {int(row["id"]): str(row["status"] or "") for row in rows}

    def _fetch_tags_for_posts(self, post_ids: list[int]) -> list[str]:
        clean_ids = [int(post_id) for post_id in post_ids]
        if not clean_ids:
            return []

        placeholders = ", ".join("?" for _ in clean_ids)
        rows = self.execute(
            f"SELECT DISTINCT tag FROM post_tags WHERE post_id IN ({placeholders})",
            clean_ids,
        ).fetchall()
        return [str(row["tag"]) for row in rows if str(row["tag"] or "").strip()]

    def _set_post_status_no_commit(self, post_id: int, status: str, config: dict[str, Any] | None = None) -> None:
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

    def reassign_posts_category(
        self,
        post_ids: list[int],
        old_category_id: int,
        new_category_id: int,
        source: str = "import-repair",
    ) -> None:
        clean_ids: list[int] = []
        seen: set[int] = set()
        for post_id in post_ids:
            post_id_int = int(post_id)
            if post_id_int in seen:
                continue
            seen.add(post_id_int)
            clean_ids.append(post_id_int)

        if not clean_ids:
            return

        affected_tags = self._fetch_tags_for_posts(clean_ids)
        placeholders = ", ".join("?" for _ in clean_ids)
        parameters: list[Any] = [int(old_category_id), *clean_ids]

        self.execute(
            f"""
            DELETE FROM post_categories
            WHERE category_id = ?
              AND post_id IN ({placeholders})
            """,
            parameters,
        )

        self.executemany(
            """
            INSERT INTO post_categories (post_id, category_id, source)
            VALUES (?, ?, ?)
            ON CONFLICT(post_id, category_id) DO UPDATE SET
                source = excluded.source
            """,
            [(post_id, int(new_category_id), source) for post_id in clean_ids],
        )

        self.execute(
            f"""
            UPDATE posts
            SET last_seen_at = CURRENT_TIMESTAMP
            WHERE id IN ({placeholders})
            """,
            clean_ids,
        )

        if affected_tags:
            self.refresh_tag_statistics_for_tags(affected_tags)

        self.commit()

    def import_existing_saved_file(self, post_id: int, category_id: int, file_path: str, source: str = "import") -> None:
        """Mark an already downloaded local file as saved and feed its tags into scoring.

        Used by the legacy-file importer. It deliberately does not move files,
        because the import source folder is supposed to remain under the user's
        control. Touching old download folders without being asked is how tools
        earn uninstall privileges.
        """
        path = Path(str(file_path)).expanduser()
        final_path = str(path)
        final_directory = str(path.parent)

        self.execute(
            """
            UPDATE posts
            SET status = 'saved',
                final_file_path = ?,
                final_directory = ?,
                original_path = COALESCE(original_path, ?),
                downloaded_at = COALESCE(downloaded_at, CURRENT_TIMESTAMP),
                saved_at = COALESCE(saved_at, CURRENT_TIMESTAMP),
                reviewed_at = COALESCE(reviewed_at, CURRENT_TIMESTAMP),
                last_seen_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (final_path, final_directory, final_path, int(post_id)),
        )

        self.execute("DELETE FROM post_categories WHERE post_id = ?", (int(post_id),))
        self.execute(
            """
            INSERT INTO post_categories (post_id, category_id, source)
            VALUES (?, ?, ?)
            """,
            (int(post_id), int(category_id), source),
        )

        affected_tags = self._fetch_tags_for_posts([int(post_id)])
        if affected_tags:
            self.refresh_tag_statistics_for_tags(affected_tags)

        self.commit()

    def update_post_final_file_path(self, post_id: int, file_path: str) -> None:
        path = Path(str(file_path)).expanduser()
        self.execute(
            """
            UPDATE posts
            SET final_file_path = ?,
                final_directory = ?,
                original_path = COALESCE(original_path, ?),
                status = 'saved',
                saved_at = COALESCE(saved_at, CURRENT_TIMESTAMP),
                last_seen_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (str(path), str(path.parent), str(path), int(post_id)),
        )
        self.commit()

    def fetch_saved_file_posts_for_category(self, category_id: int | None = None) -> list[sqlite3.Row]:
        parameters: list[Any] = []
        category_filter = ""
        if category_id is not None:
            category_filter = "AND pc.category_id = ?"
            parameters.append(int(category_id))

        return list(
            self.execute(
                f"""
                SELECT DISTINCT
                    p.id,
                    p.final_file_path,
                    p.file_ext,
                    pc.category_id
                FROM posts p
                JOIN post_categories pc ON pc.post_id = p.id
                WHERE p.final_file_path IS NOT NULL
                  AND p.final_file_path != ''
                  AND p.status = 'saved'
                  {category_filter}
                ORDER BY p.saved_at DESC, p.id DESC
                """,
                parameters,
            ).fetchall()
        )

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
                    SUM(CASE WHEN p.status = 'rejected' THEN 1 ELSE 0 END) AS rejected_count,
                    SUM(CASE WHEN p.status IN ('new', 'potential') THEN 1 ELSE 0 END) AS open_count,

                    COALESCE(ts.manual_score, '') AS manual_score,
                    COALESCE(ts.computed_score, 0) AS computed_score,
                    COALESCE(ts.average_rating, AVG(pr.stars)) AS average_rating,
                    COALESCE(ts.scoring_excluded, 0) AS scoring_excluded,
                    COALESCE(ts.ignore_category_influence, 0) AS ignore_category_influence,
                    COALESCE(ts.ignore_recommendation_score, 0) AS ignore_recommendation_score,
                    COALESCE(ts.ignore_llm_input, 0) AS ignore_llm_input,

                    ta.alias_tag AS alias_tag,

                    CASE WHEN fet.tag IS NULL THEN 0 ELSE 1 END AS filename_excluded

                FROM post_tags pt
                JOIN posts p ON p.id = pt.post_id
                LEFT JOIN tag_scores ts ON ts.tag = pt.tag
                LEFT JOIN tag_aliases ta ON ta.original_tag = pt.tag
                LEFT JOIN filename_excluded_tags fet ON fet.tag = pt.tag
                LEFT JOIN post_reviews pr ON pr.post_id = pt.post_id AND pr.stars IS NOT NULL
                {where_sql}
                GROUP BY pt.tag
                ORDER BY post_count DESC, pt.tag ASC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        )


    def search_tags_by_pattern(
        self,
        pattern: str,
        tag_type: str | None = None,
        limit: int = 1000,
    ) -> list[sqlite3.Row]:
        """Search tags with shell-style wildcards.

        Supported wildcards:
        - ``*`` matches any number of characters
        - ``?`` matches one character

        SQL LIKE treats ``_`` as a wildcard, which is adorable until your tag
        database is made almost entirely of underscores. Escape first, then add
        our own wildcards.
        """
        clean_pattern = str(pattern or "").strip()
        if not clean_pattern:
            return []

        like_pattern = (
            clean_pattern
            .replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
            .replace("*", "%")
            .replace("?", "_")
        )

        where_parts = ["pt.tag LIKE ? ESCAPE '\\'"]
        parameters: list[Any] = [like_pattern]

        if tag_type and tag_type != "all":
            where_parts.append("pt.tag_type = ?")
            parameters.append(tag_type)

        parameters.append(limit)

        return list(
            self.execute(
                f"""
                SELECT
                    pt.tag AS tag,
                    MIN(pt.tag_type) AS tag_type,
                    COUNT(DISTINCT pt.post_id) AS post_count,
                    ta.alias_tag AS alias_tag,
                    CASE WHEN fet.tag IS NULL THEN 0 ELSE 1 END AS filename_excluded,
                    COALESCE(ts.ignore_category_influence, 0) AS ignore_category_influence,
                    COALESCE(ts.ignore_recommendation_score, 0) AS ignore_recommendation_score,
                    COALESCE(ts.ignore_llm_input, 0) AS ignore_llm_input
                FROM post_tags pt
                LEFT JOIN tag_aliases ta ON ta.original_tag = pt.tag
                LEFT JOIN filename_excluded_tags fet ON fet.tag = pt.tag
                LEFT JOIN tag_scores ts ON ts.tag = pt.tag
                WHERE {" AND ".join(where_parts)}
                GROUP BY pt.tag
                ORDER BY post_count DESC, pt.tag ASC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        )


    def fetch_category_tag_hits(self, tags: Iterable[str]) -> list[sqlite3.Row]:
        """Return category/tag co-occurrences with normalization data.

        The category influence engine must not simply reward raw hit counts.
        Otherwise a broad tag such as ``1girl`` makes the largest category win
        forever, which is less "suggestion" and more "database astrology".
        The extra totals allow the caller to score distinctive tags by lift and
        per-category coverage instead of absolute popularity.
        """
        clean_tags = sorted({normalize_tag_token(str(tag)) for tag in tags if normalize_tag_token(str(tag))})
        if not clean_tags:
            return []

        placeholders = ", ".join("?" for _ in clean_tags)
        parameters = [*clean_tags, *clean_tags]
        return list(
            self.execute(
                f"""
                WITH
                category_totals AS (
                    SELECT
                        category_id,
                        COUNT(DISTINCT post_id) AS category_post_count
                    FROM post_categories
                    GROUP BY category_id
                ),
                global_total AS (
                    SELECT COUNT(DISTINCT post_id) AS categorized_post_count
                    FROM post_categories
                ),
                tag_totals AS (
                    SELECT
                        pt.tag AS tag,
                        COUNT(DISTINCT pc.post_id) AS tag_total_hits
                    FROM post_categories pc
                    JOIN post_tags pt ON pt.post_id = pc.post_id
                    WHERE pt.tag IN ({placeholders})
                    GROUP BY pt.tag
                )
                SELECT
                    c.id AS category_id,
                    c.name AS category_name,
                    pt.tag AS tag,
                    COUNT(DISTINCT pt.post_id) AS hit_count,
                    SUM(CASE WHEN p.status = 'saved' THEN 1 ELSE 0 END) AS saved_hits,
                    AVG(pr.stars) AS avg_stars,
                    COALESCE(ct.category_post_count, 0) AS category_post_count,
                    COALESCE(tt.tag_total_hits, 0) AS tag_total_hits,
                    COALESCE(gt.categorized_post_count, 0) AS categorized_post_count
                FROM post_categories pc
                JOIN categories c ON c.id = pc.category_id
                JOIN post_tags pt ON pt.post_id = pc.post_id
                JOIN posts p ON p.id = pc.post_id
                LEFT JOIN post_reviews pr ON pr.post_id = pc.post_id AND pr.stars IS NOT NULL
                LEFT JOIN category_totals ct ON ct.category_id = pc.category_id
                LEFT JOIN tag_totals tt ON tt.tag = pt.tag
                CROSS JOIN global_total gt
                WHERE pt.tag IN ({placeholders})
                GROUP BY c.id, pt.tag
                ORDER BY c.sort_order ASC, c.name ASC, hit_count DESC, pt.tag ASC
                """,
                parameters,
            ).fetchall()
        )


    def fetch_tag_display_metadata(self, tags: Iterable[str]) -> dict[str, dict[str, Any]]:
        """Return cheap per-tag metadata for viewer display and influence scoring.

        ``fetch_tag_metadata`` intentionally computes historical aggregates such
        as saved/rejected counts and average ratings. That is useful in the tag
        tab, but far too expensive for every image switch in the viewer. This
        fast path only reads direct tag settings plus alias/LLM identity data.
        Heavy historical fields are returned as neutral placeholders so the
        existing widgets can keep using one metadata shape.
        """
        clean_tags = sorted({normalize_tag_token(str(tag)) for tag in tags if normalize_tag_token(str(tag))})
        if not clean_tags:
            return {}

        placeholders = ", ".join("?" for _ in clean_tags)
        score_rows = self.execute(
            f"""
            SELECT
                tag,
                manual_score,
                COALESCE(computed_score, 0) AS stored_computed_score,
                COALESCE(scoring_excluded, 0) AS scoring_excluded,
                COALESCE(ignore_category_influence, 0) AS ignore_category_influence,
                COALESCE(ignore_recommendation_score, 0) AS ignore_recommendation_score,
                COALESCE(ignore_llm_input, 0) AS ignore_llm_input,
                average_rating
            FROM tag_scores
            WHERE tag IN ({placeholders})
            """,
            clean_tags,
        ).fetchall()
        score_by_tag = {str(row["tag"] or ""): row for row in score_rows}

        excluded_rows = self.execute(
            f"""
            SELECT tag
            FROM filename_excluded_tags
            WHERE tag IN ({placeholders})
            """,
            clean_tags,
        ).fetchall()
        filename_excluded = {str(row["tag"] or "") for row in excluded_rows}

        identities = self.build_tag_identities(clean_tags)
        result: dict[str, dict[str, Any]] = {}
        for tag in clean_tags:
            row = score_by_tag.get(tag)
            identity = identities.get(normalize_tag_token(tag), {})
            scoring_excluded = bool(row["scoring_excluded"]) if row is not None else False
            manual_score = row["manual_score"] if row is not None else None
            stored_computed_score = row["stored_computed_score"] if row is not None else 0.0
            computed_score = 0.0 if scoring_excluded else float(stored_computed_score or 0.0)
            effective_score = 0.0 if scoring_excluded else (manual_score if manual_score is not None else computed_score)
            result[tag] = {
                "canonical_tag": identity.get("canonical_tag", tag),
                "llm_token": identity.get("llm_token", ""),
                "score": effective_score,
                "manual_score": manual_score,
                "computed_score": computed_score,
                "stored_computed_score": stored_computed_score,
                "scoring_excluded": scoring_excluded,
                "ignore_category_influence": bool(row["ignore_category_influence"]) if row is not None else False,
                "ignore_recommendation_score": bool(row["ignore_recommendation_score"]) if row is not None else False,
                "ignore_llm_input": bool(row["ignore_llm_input"]) if row is not None else False,
                "filename_excluded": tag in filename_excluded,
                "average_rating": row["average_rating"] if row is not None else None,
                "rating_count": 0,
                "saved_count": 0,
                "rejected_count": 0,
                "post_count": 0,
            }
        return result




    def fetch_tag_metadata(self, tags: Iterable[str]) -> dict[str, dict[str, Any]]:
        clean_tags = sorted({str(tag).strip() for tag in tags if str(tag).strip()})
        if not clean_tags:
            return {}

        placeholders = ", ".join("?" for _ in clean_tags)
        rows = self.execute(
            f"""
            SELECT
                pt.tag AS tag,
                ts.manual_score AS manual_score,
                COALESCE(ts.computed_score, 0) AS stored_computed_score,
                COALESCE(ts.scoring_excluded, 0) AS scoring_excluded,
                COALESCE(ts.ignore_category_influence, 0) AS ignore_category_influence,
                COALESCE(ts.ignore_recommendation_score, 0) AS ignore_recommendation_score,
                COALESCE(ts.ignore_llm_input, 0) AS ignore_llm_input,
                CASE WHEN fet.tag IS NULL THEN 0 ELSE 1 END AS filename_excluded,
                COALESCE(ts.average_rating, AVG(pr.stars)) AS average_rating,
                COUNT(pr.stars) AS rating_count,
                SUM(CASE WHEN p.status = 'saved' THEN 1 ELSE 0 END) AS saved_count,
                SUM(CASE WHEN p.status = 'rejected' THEN 1 ELSE 0 END) AS rejected_count,
                COUNT(DISTINCT pt.post_id) AS post_count
            FROM post_tags pt
            JOIN posts p ON p.id = pt.post_id
            LEFT JOIN tag_scores ts ON ts.tag = pt.tag
            LEFT JOIN filename_excluded_tags fet ON fet.tag = pt.tag
            LEFT JOIN post_reviews pr ON pr.post_id = pt.post_id AND pr.stars IS NOT NULL
            WHERE pt.tag IN ({placeholders})
            GROUP BY pt.tag
            """,
            clean_tags,
        ).fetchall()

        identities = self.build_tag_identities(clean_tags)

        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            tag = str(row["tag"] or "")
            identity = identities.get(normalize_tag_token(tag), {})
            scoring_excluded = bool(row["scoring_excluded"])
            saved_count = int(row["saved_count"] or 0)
            rejected_count = int(row["rejected_count"] or 0)
            computed_score = calculate_computed_tag_score(
                average_rating=row["average_rating"],
                saved_count=saved_count,
                rejected_count=rejected_count,
                scoring_excluded=scoring_excluded,
            )
            manual_score = row["manual_score"]
            effective_score = 0.0 if scoring_excluded else (manual_score if manual_score is not None else computed_score)
            result[tag] = {
                "canonical_tag": identity.get("canonical_tag", tag),
                "llm_token": identity.get("llm_token", ""),
                "score": effective_score,
                "manual_score": manual_score,
                "computed_score": computed_score,
                "stored_computed_score": row["stored_computed_score"],
                "scoring_excluded": scoring_excluded,
                "ignore_category_influence": bool(row["ignore_category_influence"]),
                "ignore_recommendation_score": bool(row["ignore_recommendation_score"]),
                "ignore_llm_input": bool(row["ignore_llm_input"]),
                "filename_excluded": bool(row["filename_excluded"]),
                "average_rating": row["average_rating"],
                "rating_count": int(row["rating_count"] or 0),
                "saved_count": saved_count,
                "rejected_count": rejected_count,
                "post_count": int(row["post_count"] or 0),
            }
        return result


    # ------------------------------------------------------------------
    # Tag identity / alias privacy layer
    # ------------------------------------------------------------------

    def ensure_llm_hash_salt(self) -> str:
        """Return the local salted-hash secret, creating one if missing.

        This salt stays local in SQLite/app_settings. Without it, hashed tags
        would be a dictionary attack with extra steps, and humanity has already
        invented enough fake privacy.
        """
        row = self.execute(
            "SELECT value FROM app_settings WHERE key = ?",
            ("llm.hash_salt",),
        ).fetchone()
        if row is not None and row["value"]:
            try:
                loaded = json.loads(str(row["value"]))
                if isinstance(loaded, str) and loaded.strip():
                    return loaded.strip()
            except Exception:
                raw = str(row["value"]).strip()
                if raw:
                    return raw

        salt = secrets.token_hex(32)
        self.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            ("llm.hash_salt", json.dumps(salt)),
        )
        return salt

    def list_tag_alias_map(self) -> dict[str, str]:
        rows = self.execute(
            """
            SELECT original_tag, alias_tag
            FROM tag_aliases
            WHERE TRIM(COALESCE(alias_tag, '')) != ''
            """
        ).fetchall()
        result: dict[str, str] = {}
        for row in rows:
            original = normalize_tag_token(str(row["original_tag"] or ""))
            alias = normalize_tag_token(str(row["alias_tag"] or ""))
            if original and alias:
                result[original] = alias
        return result

    def get_llm_tag_export_settings(self) -> dict[str, Any]:
        def setting(key: str, default: Any) -> Any:
            row = self.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
            if row is None:
                return default
            try:
                return json.loads(str(row["value"]))
            except Exception:
                return row["value"]

        mode = str(setting("llm.tag_export_mode", "hashed_alias") or "hashed_alias").lower()
        if mode not in {"original", "alias", "hashed_alias"}:
            mode = "hashed_alias"
        prefix = str(setting("llm.hash_prefix", "tag_") or "tag_")
        try:
            length = int(setting("llm.hash_length", 12))
        except Exception:
            length = 12
        return {
            "mode": mode,
            "prefix": prefix,
            "hash_length": max(4, min(64, length)),
            "salt": self.ensure_llm_hash_salt(),
        }

    def build_tag_identities(self, tags: Iterable[str]) -> dict[str, dict[str, str]]:
        aliases = self.list_tag_alias_map()
        settings = self.get_llm_tag_export_settings()
        clean_tags = sorted({normalize_tag_token(str(tag)) for tag in tags if normalize_tag_token(str(tag))})
        result: dict[str, dict[str, str]] = {}
        cache_rows: list[tuple[str, str, str]] = []

        for tag in clean_tags:
            identity = build_tag_identity(
                tag,
                aliases=aliases,
                salt=str(settings["salt"]),
                prefix=str(settings["prefix"]),
                length=int(settings["hash_length"]),
            )
            result[tag] = {
                "original_tag": identity.original_tag,
                "canonical_tag": identity.canonical_tag,
                "llm_token": identity.llm_token,
            }
            cache_rows.append((identity.original_tag, identity.canonical_tag, identity.llm_token))

        if cache_rows:
            self.executemany(
                """
                INSERT INTO tag_identity_cache (original_tag, canonical_tag, llm_token, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(original_tag) DO UPDATE SET
                    canonical_tag = excluded.canonical_tag,
                    llm_token = excluded.llm_token,
                    updated_at = CURRENT_TIMESTAMP
                """,
                cache_rows,
            )
        return result

    def canonical_tag_for_tag(self, tag: str) -> str:
        clean_tag = normalize_tag_token(tag)
        if not clean_tag:
            return ""
        aliases = self.list_tag_alias_map()
        return canonicalize_tag(clean_tag, aliases)

    def llm_export_value_for_tag(self, tag: str, mode: str | None = None) -> str:
        clean_tag = normalize_tag_token(tag)
        if not clean_tag:
            return ""
        identity = self.build_tag_identities([clean_tag]).get(clean_tag)
        if not identity:
            return clean_tag
        export_mode = (mode or self.get_llm_tag_export_settings()["mode"]).lower()
        if export_mode == "original":
            return identity["original_tag"]
        if export_mode == "alias":
            return identity["canonical_tag"]
        return identity["llm_token"]

    def build_llm_tag_export(self, tags: Iterable[str], mode: str | None = None) -> list[str]:
        clean_tags = sorted({normalize_tag_token(str(tag)) for tag in tags if normalize_tag_token(str(tag))})
        identities = self.build_tag_identities(clean_tags)
        export_mode = (mode or self.get_llm_tag_export_settings()["mode"]).lower()
        exported: list[str] = []
        seen: set[str] = set()
        for tag in clean_tags:
            identity = identities.get(tag)
            if not identity:
                continue
            if export_mode == "original":
                value = identity["original_tag"]
            elif export_mode == "alias":
                value = identity["canonical_tag"]
            else:
                value = identity["llm_token"]
            if value and value not in seen:
                exported.append(value)
                seen.add(value)
        return exported

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

        clean_tag = normalize_tag_token(clean_tag)
        clean_alias = normalize_tag_token(clean_alias)

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
        # Alias changes can affect chained aliases and grouped LLM tokens, so the
        # cheap and safe move is to rebuild the cache lazily on next use.
        self.execute("DELETE FROM tag_identity_cache")
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


    def set_tag_scoring_flags(
        self,
        tag: str,
        *,
        ignore_category_influence: bool | None = None,
        ignore_recommendation_score: bool | None = None,
        ignore_llm_input: bool | None = None,
    ) -> None:
        clean_tag = normalize_tag_token(str(tag or ""))
        if not clean_tag:
            return

        assignments: list[str] = []
        parameters: list[Any] = [clean_tag]

        if ignore_category_influence is not None:
            assignments.append("ignore_category_influence = ?")
            parameters.append(1 if ignore_category_influence else 0)
        if ignore_recommendation_score is not None:
            assignments.append("ignore_recommendation_score = ?")
            parameters.append(1 if ignore_recommendation_score else 0)
        if ignore_llm_input is not None:
            assignments.append("ignore_llm_input = ?")
            parameters.append(1 if ignore_llm_input else 0)

        if not assignments:
            return

        insert_columns = ["tag"]
        insert_values: list[Any] = [clean_tag]
        update_parts: list[str] = []
        if ignore_category_influence is not None:
            insert_columns.append("ignore_category_influence")
            insert_values.append(1 if ignore_category_influence else 0)
            update_parts.append("ignore_category_influence = excluded.ignore_category_influence")
        if ignore_recommendation_score is not None:
            insert_columns.append("ignore_recommendation_score")
            insert_values.append(1 if ignore_recommendation_score else 0)
            update_parts.append("ignore_recommendation_score = excluded.ignore_recommendation_score")
        if ignore_llm_input is not None:
            insert_columns.append("ignore_llm_input")
            insert_values.append(1 if ignore_llm_input else 0)
            update_parts.append("ignore_llm_input = excluded.ignore_llm_input")

        placeholders = ", ".join("?" for _ in insert_columns)
        self.execute(
            f"""
            INSERT INTO tag_scores ({", ".join(insert_columns)})
            VALUES ({placeholders})
            ON CONFLICT(tag) DO UPDATE SET {", ".join(update_parts)}
            """,
            insert_values,
        )
        self.commit()

    def scoring_flag_tag_set(self, column: str) -> set[str]:
        allowed_columns = {
            "ignore_category_influence",
            "ignore_recommendation_score",
            "ignore_llm_input",
            "scoring_excluded",
        }
        if column not in allowed_columns:
            raise ValueError(f"Unbekannte Scoring-Flag-Spalte: {column}")
        rows = self.execute(
            f"SELECT tag FROM tag_scores WHERE COALESCE({column}, 0) != 0"
        ).fetchall()
        return {str(row["tag"]) for row in rows}

    def category_influence_ignored_tag_set(self) -> set[str]:
        return self.scoring_flag_tag_set("ignore_category_influence")

    def set_tag_scoring_excluded(self, tag: str, excluded: bool = True) -> None:
        clean_tag = tag.strip()
        if not clean_tag:
            return

        self.execute(
            """
            INSERT INTO tag_scores (tag, scoring_excluded)
            VALUES (?, ?)
            ON CONFLICT(tag) DO UPDATE SET scoring_excluded = excluded.scoring_excluded
            """,
            (clean_tag, 1 if excluded else 0),
        )
        self.refresh_tag_statistics_for_tags([clean_tag])
        self.commit()

    def scoring_excluded_tag_set(self) -> set[str]:
        rows = self.execute(
            "SELECT tag FROM tag_scores WHERE COALESCE(scoring_excluded, 0) != 0"
        ).fetchall()
        return {str(row["tag"]) for row in rows}

    def refresh_tag_statistics_for_tags(self, tags: Iterable[str]) -> None:
        clean_tags = sorted({str(tag).strip() for tag in tags if str(tag).strip()})
        if not clean_tags:
            return

        placeholders = ", ".join("?" for _ in clean_tags)
        rows = self.execute(
            f"""
            SELECT
                pt.tag AS tag,
                SUM(CASE WHEN p.status = 'saved' THEN 1 ELSE 0 END) AS saved_count,
                SUM(CASE WHEN p.status = 'rejected' THEN 1 ELSE 0 END) AS rejected_count,
                COALESCE(ts.average_rating, AVG(pr.stars)) AS average_rating,
                COALESCE(ts.scoring_excluded, 0) AS scoring_excluded
            FROM post_tags pt
            JOIN posts p ON p.id = pt.post_id
            LEFT JOIN tag_scores ts ON ts.tag = pt.tag
            LEFT JOIN post_reviews pr ON pr.post_id = pt.post_id AND pr.stars IS NOT NULL
            WHERE pt.tag IN ({placeholders})
            GROUP BY pt.tag
            """,
            clean_tags,
        ).fetchall()

        payload: list[tuple[str, float, int, int, float | None]] = []
        for row in rows:
            saved_count = int(row["saved_count"] or 0)
            rejected_count = int(row["rejected_count"] or 0)
            average_rating = row["average_rating"]
            scoring_excluded = bool(row["scoring_excluded"])
            computed_score = calculate_computed_tag_score(
                average_rating=average_rating,
                saved_count=saved_count,
                rejected_count=rejected_count,
                scoring_excluded=scoring_excluded,
            )
            payload.append((str(row["tag"]), computed_score, saved_count, rejected_count, average_rating))

        if payload:
            self.executemany(
                """
                INSERT INTO tag_scores (tag, computed_score, accepted_count, rejected_count, average_rating)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(tag) DO UPDATE SET
                    computed_score = excluded.computed_score,
                    accepted_count = excluded.accepted_count,
                    rejected_count = excluded.rejected_count,
                    average_rating = excluded.average_rating
                """,
                payload,
            )

    def refresh_tag_statistics_for_post(self, post_id: int) -> None:
        rows = self.execute("SELECT tag FROM post_tags WHERE post_id = ?", (post_id,)).fetchall()
        self.refresh_tag_statistics_for_tags([str(row["tag"]) for row in rows])


    def refresh_all_tag_statistics(self) -> None:
        """Refresh cached tag statistics from posts/reviews.

        The viewer computes fresh values on demand anyway. This cache refresh is
        useful for the Tag tab and exports, because stale counters are the sort
        of tiny lie that later turns into a debugging afternoon.
        """
        rows = self.execute(
            """
            SELECT
                pt.tag AS tag,
                SUM(CASE WHEN p.status = 'saved' THEN 1 ELSE 0 END) AS saved_count,
                SUM(CASE WHEN p.status = 'rejected' THEN 1 ELSE 0 END) AS rejected_count,
                COALESCE(ts.average_rating, AVG(pr.stars)) AS average_rating,
                COALESCE(ts.scoring_excluded, 0) AS scoring_excluded
            FROM post_tags pt
            JOIN posts p ON p.id = pt.post_id
            LEFT JOIN tag_scores ts ON ts.tag = pt.tag
            LEFT JOIN post_reviews pr ON pr.post_id = pt.post_id AND pr.stars IS NOT NULL
            GROUP BY pt.tag
            """
        ).fetchall()

        payload: list[tuple[str, float, int, int, float | None]] = []
        for row in rows:
            saved_count = int(row["saved_count"] or 0)
            rejected_count = int(row["rejected_count"] or 0)
            average_rating = row["average_rating"]
            scoring_excluded = bool(row["scoring_excluded"])
            computed_score = calculate_computed_tag_score(
                average_rating=average_rating,
                saved_count=saved_count,
                rejected_count=rejected_count,
                scoring_excluded=scoring_excluded,
            )
            payload.append((
                str(row["tag"]),
                computed_score,
                saved_count,
                rejected_count,
                average_rating,
            ))

        if payload:
            self.executemany(
                """
                INSERT INTO tag_scores (tag, computed_score, accepted_count, rejected_count, average_rating)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(tag) DO UPDATE SET
                    computed_score = excluded.computed_score,
                    accepted_count = excluded.accepted_count,
                    rejected_count = excluded.rejected_count,
                    average_rating = excluded.average_rating
                """,
                payload,
            )
            self.commit()


    # ------------------------------------------------------------------
    # App settings / Fetch presets / Tag suggestions
    # ------------------------------------------------------------------

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

    def save_fetch_preset(self, name: str, payload: dict[str, Any]) -> None:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Preset-Name darf nicht leer sein")
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

    def suggest_tags(self, prefix: str = "", limit: int = 300) -> list[str]:
        """Return tag suggestions quickly enough that the GUI does not feel cursed.

        This is used for interactive completion. The old version ranked every
        candidate by COUNT(DISTINCT post_id), which is fine for a report and
        absurd for a keypress. This version keeps the useful per-type mix, but
        avoids global grouping/counting while the user is typing.
        """
        clean = str(prefix or "").strip()
        max_limit = max(1, int(limit))

        if max_limit <= 20:
            type_limits = {
                "copyright": max(1, max_limit // 4),
                "character": max(1, max_limit // 4),
                "artist": max(1, max_limit // 5),
                "meta": max(1, max_limit // 10),
                "general": max(1, max_limit),
            }
        else:
            type_limits = {
                "copyright": max(20, max_limit // 5),
                "character": max(20, max_limit // 5),
                "artist": max(15, max_limit // 6),
                "meta": max(10, max_limit // 12),
                "general": max(30, max_limit // 3),
            }

        type_order = ["copyright", "character", "artist", "meta", "general"]
        suggestions: list[str] = []
        seen: set[str] = set()

        def add_rows(rows: list[sqlite3.Row]) -> None:
            for row in rows:
                tag = str(row["tag"] or "").strip()
                if tag and tag not in seen:
                    seen.add(tag)
                    suggestions.append(tag)

        def query_rows(tag_type: str | None, pattern: str, row_limit: int) -> list[sqlite3.Row]:
            if tag_type is None:
                return list(
                    self.execute(
                        """
                        SELECT DISTINCT tag
                        FROM post_tags
                        WHERE tag LIKE ?
                        ORDER BY tag COLLATE NOCASE ASC
                        LIMIT ?
                        """,
                        (pattern, row_limit),
                    ).fetchall()
                )
            return list(
                self.execute(
                    """
                    SELECT DISTINCT tag
                    FROM post_tags
                    WHERE tag_type = ? AND tag LIKE ?
                    ORDER BY tag COLLATE NOCASE ASC
                    LIMIT ?
                    """,
                    (tag_type, pattern, row_limit),
                ).fetchall()
            )

        if clean:
            prefix_pattern = f"{clean}%"
            contains_pattern = f"%{clean}%"
        else:
            prefix_pattern = "%"
            contains_pattern = "%"

        for tag_type in type_order:
            if len(suggestions) >= max_limit:
                break
            per_type_limit = min(type_limits[tag_type], max_limit - len(suggestions))
            if per_type_limit <= 0:
                continue
            add_rows(query_rows(tag_type, prefix_pattern, per_type_limit))

        # Prefix hits are cheap and usually what a completion field should do.
        # If the user types the middle of a tag, do a smaller contains fallback.
        # Humanity survives both cases, barely.
        if clean and len(suggestions) < max_limit:
            for tag_type in type_order:
                if len(suggestions) >= max_limit:
                    break
                per_type_limit = min(max(5, type_limits[tag_type] // 2), max_limit - len(suggestions))
                add_rows(query_rows(tag_type, contains_pattern, per_type_limit))

        remaining = max_limit - len(suggestions)
        if remaining > 0:
            add_rows(query_rows(None, prefix_pattern, remaining))

        return suggestions[:max_limit]

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
