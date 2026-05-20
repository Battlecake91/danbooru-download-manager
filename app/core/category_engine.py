from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.database import Database


@dataclass(frozen=True)
class CategoryMatch:
    id: int | None
    name: str
    folder_name: str
    output_path: str | None
    matched: bool
    reason: str


class CategoryEngine:
    def __init__(self, config: dict[str, Any], db: Database) -> None:
        self.config = config
        self.db = db

    def list_categories(self) -> list[CategoryMatch]:
        rows = self.db.list_categories_full()
        results: list[CategoryMatch] = []

        for row in rows:
            results.append(
                CategoryMatch(
                    id=int(row["id"]),
                    name=str(row["name"]),
                    folder_name=str(row["folder_name"]),
                    output_path=row["output_path"],
                    matched=False,
                    reason="Manuelle Auswahl",
                )
            )

        if not any(category.name == "_unmatched" for category in results):
            results.append(
                CategoryMatch(
                    id=None,
                    name="_unmatched",
                    folder_name="_unmatched",
                    output_path=None,
                    matched=False,
                    reason="Fallback",
                )
            )

        return results

    def category_by_name(self, name: str) -> CategoryMatch | None:
        row = self.db.get_category_by_name(name)
        if row is None:
            return None

        return CategoryMatch(
            id=int(row["id"]),
            name=str(row["name"]),
            folder_name=str(row["folder_name"]),
            output_path=row["output_path"],
            matched=False,
            reason="Manuelle Auswahl",
        )

    def suggest_category_for_post(self, post_id: int) -> CategoryMatch:
        tags = self.get_post_tags(post_id)

        categories = self.db.list_categories_full()
        all_rules = self.db.list_category_rules()
        rules_by_category: dict[int, list[Any]] = {}

        for rule in all_rules:
            rules_by_category.setdefault(int(rule["category_id"]), []).append(rule)

        for category in categories:
            category_id = int(category["id"])
            rules = rules_by_category.get(category_id, [])

            include = {str(rule["tag"]) for rule in rules if str(rule["rule_type"]) == "include"}
            exclude = {str(rule["tag"]) for rule in rules if str(rule["rule_type"]) == "exclude"}

            if exclude.intersection(tags):
                continue

            include_groups: dict[str, set[str]] = {}
            for rule in rules:
                rule_type = str(rule["rule_type"])
                if rule_type.startswith("include_group_"):
                    include_groups.setdefault(rule_type, set()).add(str(rule["tag"]))

            if include and not include.intersection(tags):
                continue

            if include_groups:
                group_match = False
                for group_tags in include_groups.values():
                    if group_tags and group_tags.issubset(tags):
                        group_match = True
                        break
                if not group_match:
                    continue

            if include or include_groups:
                return CategoryMatch(
                    id=category_id,
                    name=str(category["name"]),
                    folder_name=str(category["folder_name"]),
                    output_path=category["output_path"],
                    matched=True,
                    reason="SQL-Regel passt",
                )

        unmatched = self.category_by_name("_unmatched")
        if unmatched is not None:
            return CategoryMatch(
                id=unmatched.id,
                name=unmatched.name,
                folder_name=unmatched.folder_name,
                output_path=unmatched.output_path,
                matched=False,
                reason="Keine SQL-Regel passt, Fallback",
            )

        return CategoryMatch(
            id=None,
            name="_unmatched",
            folder_name="_unmatched",
            output_path=None,
            matched=False,
            reason="Keine SQL-Regel passt, interner Fallback",
        )

    def get_post_tags(self, post_id: int) -> set[str]:
        rows = self.db.execute(
            """
            SELECT tag
            FROM post_tags
            WHERE post_id = ?
            """,
            (post_id,),
        ).fetchall()
        return {str(row["tag"]) for row in rows}

    def output_directory_for_category(self, category: CategoryMatch) -> Path:
        if category.output_path:
            return Path(str(category.output_path))

        default_output_dir = Path(str(self.config.get("default_output_dir", "./danbooru_saved")))
        return default_output_dir / category.folder_name
