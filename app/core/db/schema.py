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


class DatabaseSchemaMixin:
    """Schema creation, migrations, and index maintenance."""

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
            llm_decision TEXT DEFAULT NULL,
            llm_category TEXT DEFAULT NULL,
            llm_reason TEXT DEFAULT NULL,
            llm_model TEXT DEFAULT NULL,
            llm_reviewed_at TEXT DEFAULT NULL,
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

        CREATE TABLE IF NOT EXISTS danbooru_tags (
            name TEXT PRIMARY KEY,
            category TEXT,
            category_id INTEGER,
            post_count INTEGER DEFAULT 0,
            is_deprecated INTEGER DEFAULT 0,
            last_synced_at TEXT DEFAULT CURRENT_TIMESTAMP,
            raw_json TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_danbooru_tags_category ON danbooru_tags(category);
        CREATE INDEX IF NOT EXISTS idx_danbooru_tags_post_count ON danbooru_tags(post_count DESC);
        CREATE INDEX IF NOT EXISTS idx_danbooru_tags_name ON danbooru_tags(name);

        CREATE TABLE IF NOT EXISTS danbooru_tag_aliases (
            antecedent_name TEXT PRIMARY KEY,
            consequent_name TEXT NOT NULL,
            status TEXT,
            last_synced_at TEXT DEFAULT CURRENT_TIMESTAMP,
            raw_json TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_danbooru_tag_aliases_consequent ON danbooru_tag_aliases(consequent_name);

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
            raise RuntimeError("Database is not connected")

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
        self.add_column_if_missing("posts", "llm_decision", "TEXT DEFAULT NULL")
        self.add_column_if_missing("posts", "llm_category", "TEXT DEFAULT NULL")
        self.add_column_if_missing("posts", "llm_reason", "TEXT DEFAULT NULL")
        self.add_column_if_missing("posts", "llm_model", "TEXT DEFAULT NULL")
        self.add_column_if_missing("posts", "llm_reviewed_at", "TEXT DEFAULT NULL")
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
        # Older development builds could create duplicate rules.
        # Clean them up before adding the unique index, otherwise SQLite crashes on startup.
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
        self.execute("CREATE INDEX IF NOT EXISTS idx_danbooru_tags_category_count ON danbooru_tags(category, post_count DESC)")
        self.execute("CREATE INDEX IF NOT EXISTS idx_danbooru_tags_name_count ON danbooru_tags(name, post_count DESC)")

    def add_column_if_missing(self, table_name: str, column_name: str, declaration: str) -> None:
        columns = self.execute(f"PRAGMA table_info({table_name})").fetchall()
        existing = {str(row["name"]) for row in columns}
        if column_name not in existing:
            self.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {declaration}")
