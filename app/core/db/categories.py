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


class DatabaseCategoryMixin:
    """Category, category-rule, and category-priority database operations."""

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
            raise RuntimeError(f"Category could not be saved: {name}")
        return int(row["id"])

    def create_category(self, name: str, folder_name: str | None = None) -> int:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Category name must not be empty")

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
            raise RuntimeError(f"Category not found: {category_name}")
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
