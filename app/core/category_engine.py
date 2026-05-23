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


@dataclass(frozen=True)
class CategoryRuleSet:
    groups: list[tuple[set[str], set[str]]]
    global_required: set[str]
    global_forbidden: set[str]


def build_category_rule_set(rules: list[Any]) -> CategoryRuleSet:
    """Return category rules as OR branches plus global AND constraints.

    New rule types:
      - group_N_include/group_N_exclude are OR branches.
      - global_N_include/global_N_exclude are applied to every branch.

    Legacy rules stay compatible:
      - include tags are OR branches.
      - include_group_N rows are AND branches.
      - exclude tags become global blockers.
    """
    import re

    new_groups: dict[int, tuple[set[str], set[str]]] = {}
    legacy_groups: dict[str, set[str]] = {}
    legacy_includes: set[str] = set()
    legacy_excludes: set[str] = set()
    global_required: set[str] = set()
    global_forbidden: set[str] = set()

    include_re = re.compile(r"^group_(\d+)_include$")
    exclude_re = re.compile(r"^group_(\d+)_exclude$")
    global_include_re = re.compile(r"^global_(\d+)_include$")
    global_exclude_re = re.compile(r"^global_(\d+)_exclude$")

    for rule in rules:
        rule_type = str(rule["rule_type"])
        tag = str(rule["tag"])

        include_match = include_re.match(rule_type)
        exclude_match = exclude_re.match(rule_type)
        global_include_match = global_include_re.match(rule_type)
        global_exclude_match = global_exclude_re.match(rule_type)

        if include_match:
            index = int(include_match.group(1))
            includes, excludes = new_groups.setdefault(index, (set(), set()))
            includes.add(tag)
        elif exclude_match:
            index = int(exclude_match.group(1))
            includes, excludes = new_groups.setdefault(index, (set(), set()))
            excludes.add(tag)
        elif global_include_match:
            global_required.add(tag)
        elif global_exclude_match:
            global_forbidden.add(tag)
        elif rule_type == "include":
            legacy_includes.add(tag)
        elif rule_type == "exclude":
            legacy_excludes.add(tag)
        elif rule_type.startswith("include_group_"):
            legacy_groups.setdefault(rule_type, set()).add(tag)

    if new_groups:
        groups = [new_groups[index] for index in sorted(new_groups)]
    else:
        groups: list[tuple[set[str], set[str]]] = []
        for group_tags in legacy_groups.values():
            groups.append((set(group_tags), set()))
        for tag in sorted(legacy_includes):
            groups.append(({tag}, set()))

    global_forbidden.update(legacy_excludes)
    return CategoryRuleSet(
        groups=groups,
        global_required=global_required,
        global_forbidden=global_forbidden,
    )


def build_category_match_groups(rules: list[Any]) -> list[tuple[set[str], set[str]]]:
    """Compatibility helper: return final branches with globals applied."""
    rule_set = build_category_rule_set(rules)
    result: list[tuple[set[str], set[str]]] = []

    if not rule_set.groups and rule_set.global_required:
        result.append((set(rule_set.global_required), set(rule_set.global_forbidden)))
        return result

    for required_tags, forbidden_tags in rule_set.groups:
        result.append(
            (
                set(required_tags).union(rule_set.global_required),
                set(forbidden_tags).union(rule_set.global_forbidden),
            )
        )
    return result


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

            groups = build_category_match_groups(rules)
            if groups:
                group_match = False
                for required_tags, forbidden_tags in groups:
                    if forbidden_tags.intersection(tags):
                        continue
                    if required_tags and required_tags.issubset(tags):
                        group_match = True
                        break
                    if not required_tags and forbidden_tags:
                        # Pure exclude branches are intentionally not positive matches.
                        continue
                if not group_match:
                    continue

                return CategoryMatch(
                    id=category_id,
                    name=str(category["name"]),
                    folder_name=str(category["folder_name"]),
                    output_path=category["output_path"],
                    matched=True,
                    reason="Kategorie-Regel passt",
                )

        unmatched = self.category_by_name("_unmatched")
        if unmatched is not None:
            return CategoryMatch(
                id=unmatched.id,
                name=unmatched.name,
                folder_name=unmatched.folder_name,
                output_path=unmatched.output_path,
                matched=False,
                reason="Keine Kategorie-Regel passt, Fallback",
            )

        return CategoryMatch(
            id=None,
            name="_unmatched",
            folder_name="_unmatched",
            output_path=None,
            matched=False,
            reason="Keine Kategorie-Regel passt, interner Fallback",
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

    def build_category_decision_report_for_post(
        self,
        post_id: int,
        selected_category_name: str | None = None,
    ) -> str:
        tags = self.get_post_tags(post_id)
        if not tags:
            return f"Post {post_id} wurde nicht gefunden oder hat keine gespeicherten Tags."

        return self.build_category_decision_report(
            tags,
            title=f"Post {post_id}",
            selected_category_name=selected_category_name,
        )

    def build_category_decision_report(
        self,
        tags: set[str],
        *,
        title: str = "Tags",
        selected_category_name: str | None = None,
    ) -> str:
        categories = self.db.list_categories_full()
        all_rules = self.db.list_category_rules()
        rules_by_category: dict[int, list[Any]] = {}
        for rule in all_rules:
            rules_by_category.setdefault(int(rule["category_id"]), []).append(rule)

        lines: list[str] = []
        lines.append(title)
        if selected_category_name:
            lines.append(f"Aktuell im Viewer gewählt: {selected_category_name}")
        lines.append(f"Tags: {len(tags)}")
        if tags:
            preview = " ".join(sorted(tags, key=str.casefold)[:60])
            if len(tags) > 60:
                preview += f" … +{len(tags) - 60}"
            lines.append(preview)
        lines.append("")

        winner_name: str | None = None
        matched_names: list[str] = []
        category_blocks: list[str] = []

        for category_index, category in enumerate(categories, start=1):
            category_id = int(category["id"])
            name = str(category["name"])
            rules = rules_by_category.get(category_id, [])
            rule_set = build_category_rule_set(rules)

            matched, block = self.describe_category_decision(
                name=name,
                position=category_index,
                groups=rule_set.groups,
                global_required=rule_set.global_required,
                global_forbidden=rule_set.global_forbidden,
                tags=tags,
            )
            if matched:
                matched_names.append(name)
                if winner_name is None:
                    winner_name = name
            category_blocks.append(block)

        if winner_name is None:
            lines.append("Automatische Gewinner-Kategorie: _unmatched")
            lines.append("Keine Kategorie-Regel passt.")
        else:
            lines.append(f"Automatische Gewinner-Kategorie: {winner_name}")
            if selected_category_name and selected_category_name != winner_name:
                lines.append("Hinweis: Die aktuell gewählte Kategorie weicht vom automatischen Vorschlag ab.")
            if len(matched_names) > 1:
                also = ", ".join(matched_names[1:])
                lines.append(f"Weitere passende Kategorien weiter unten: {also}")
            lines.append("Hinweis: In der Kategorienliste gewinnt immer die erste passende Kategorie.")

        lines.append("")
        lines.append("Details:")
        lines.extend(category_blocks)
        return "\n".join(lines)

    def describe_category_decision(
        self,
        *,
        name: str,
        position: int,
        groups: list[tuple[set[str], set[str]]],
        global_required: set[str],
        global_forbidden: set[str],
        tags: set[str],
    ) -> tuple[bool, str]:
        block: list[str] = []
        block.append(f"[{position}] {name}")

        if not groups and not global_required:
            block.append("  – keine positive ODER-Gruppe oder globale Muss-Bedingung")
            block.append("  Ergebnis: passt nicht")
            return False, "\n".join(block)

        global_missing = sorted(global_required.difference(tags), key=str.casefold)
        global_blocked = sorted(global_forbidden.intersection(tags), key=str.casefold)

        if global_required or global_forbidden:
            block.append("  Globale Bedingungen:")
            for tag in sorted(global_required, key=str.casefold):
                block.append(f"    {'✓' if tag in tags else '✗'} {tag}")
            for tag in sorted(global_forbidden, key=str.casefold):
                block.append(f"    {'✗ blockiert' if tag in tags else '✓'} -{tag}")

        if global_missing or global_blocked:
            block.append("  Ergebnis: passt nicht, globale Bedingungen verhindern den Treffer")
            return False, "\n".join(block)

        if not groups and global_required:
            block.append("  Ergebnis: passt, globale Muss-Bedingungen sind erfüllt")
            return True, "\n".join(block)

        any_match = False
        for group_index, (required_tags, forbidden_tags) in enumerate(groups, start=1):
            missing = sorted(required_tags.difference(tags), key=str.casefold)
            blocked = sorted(forbidden_tags.intersection(tags), key=str.casefold)
            group_has_positive = bool(required_tags or global_required)
            group_matches = group_has_positive and not missing and not blocked
            any_match = any_match or group_matches

            state = "PASST" if group_matches else "passt nicht"
            block.append(f"  ODER-Gruppe {group_index}: {state}")
            if not required_tags and not forbidden_tags:
                block.append("    – leer")
            for tag in sorted(required_tags, key=str.casefold):
                block.append(f"    {'✓' if tag in tags else '✗'} {tag}")
            for tag in sorted(forbidden_tags, key=str.casefold):
                block.append(f"    {'✗ blockiert' if tag in tags else '✓'} -{tag}")
            if forbidden_tags and not required_tags and not global_required:
                block.append("    Hinweis: reine Ausschlussgruppen sind keine positive Trefferbedingung")

        block.append(f"  Ergebnis: {'passt' if any_match else 'passt nicht'}")
        return any_match, "\n".join(block)

    def output_directory_for_category(self, category: CategoryMatch) -> Path:
        if category.output_path:
            return Path(str(category.output_path))

        default_output_dir = Path(str(self.config.get("default_output_dir", "./danbooru_saved")))
        return default_output_dir / category.folder_name
