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

        evaluations: list[dict[str, Any]] = []
        matched_names: list[str] = []
        winner_name: str | None = None

        for category_index, category in enumerate(categories, start=1):
            category_id = int(category["id"])
            name = str(category["name"])
            rules = rules_by_category.get(category_id, [])
            rule_set = build_category_rule_set(rules)

            matched, block, summary = self.describe_category_decision(
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
            evaluations.append(
                {
                    "name": name,
                    "position": category_index,
                    "matched": matched,
                    "block": block,
                    "summary": summary,
                }
            )

        automatic_name = winner_name or "_unmatched"
        lines: list[str] = [title]
        lines.append(f"Automatik: {automatic_name}")
        if selected_category_name:
            lines.append(f"Aktuell gewählt: {selected_category_name}")
            if selected_category_name != automatic_name:
                lines.append("Abweichung: manuelle Auswahl überschreibt den automatischen Vorschlag.")
        lines.append(f"Tags im Post: {len(tags)}")
        lines.append("Reihenfolge: Die erste passende Kategorie gewinnt.")
        lines.append("")

        lines.append("Kurzübersicht")
        if matched_names:
            lines.append(f"Passt: {', '.join(matched_names)}")
            if len(matched_names) > 1:
                lines.append(f"Weitere passende Kategorien nach dem Gewinner: {', '.join(matched_names[1:])}")
        else:
            lines.append("Passt: keine Kategorie, daher Fallback _unmatched")
        lines.append("")

        important_names: list[str] = []
        if winner_name:
            important_names.append(winner_name)
        if selected_category_name and selected_category_name not in important_names:
            important_names.append(selected_category_name)
        for name in matched_names[1:]:
            if name not in important_names:
                important_names.append(name)

        important_blocks = [entry for entry in evaluations if entry["name"] in important_names]
        if important_blocks:
            lines.append("Relevante Details")
            for entry in important_blocks:
                lines.append(str(entry["block"]))
                lines.append("")

        blocked_entries = [entry for entry in evaluations if not entry["matched"] and entry["name"] not in important_names]
        if blocked_entries:
            lines.append("Nicht passende Kategorien, Kurzfassung")
            for entry in blocked_entries:
                lines.append(f"[{entry['position']}] {entry['name']}: {entry['summary']}")

        return "\n".join(line for line in lines).rstrip()

    def describe_category_decision(
        self,
        *,
        name: str,
        position: int,
        groups: list[tuple[set[str], set[str]]],
        global_required: set[str],
        global_forbidden: set[str],
        tags: set[str],
    ) -> tuple[bool, str, str]:
        block: list[str] = []
        block.append(f"[{position}] {name}")

        if not groups and not global_required:
            summary = "keine positive Gruppe oder globale Muss-Bedingung"
            block.append(f"  Ergebnis: passt nicht, {summary}")
            return False, "\n".join(block), summary

        global_missing = sorted(global_required.difference(tags), key=str.casefold)
        global_blocked = sorted(global_forbidden.intersection(tags), key=str.casefold)

        if global_missing or global_blocked:
            reasons: list[str] = []
            if global_missing:
                reasons.append("fehlt global: " + ", ".join(global_missing))
            if global_blocked:
                reasons.append("blockiert global: " + ", ".join(f"-{tag}" for tag in global_blocked))
            summary = "; ".join(reasons)
            block.append(f"  Ergebnis: passt nicht, {summary}")
            return False, "\n".join(block), summary

        if global_required or global_forbidden:
            block.append("  Globale Bedingungen: erfüllt")
            if global_required:
                block.append("    Muss: " + ", ".join(sorted(global_required, key=str.casefold)))
            if global_forbidden:
                block.append("    Ausschluss nicht vorhanden: " + ", ".join(f"-{tag}" for tag in sorted(global_forbidden, key=str.casefold)))

        if not groups and global_required:
            summary = "globale Muss-Bedingungen erfüllt"
            block.append(f"  Ergebnis: passt, {summary}")
            return True, "\n".join(block), summary

        matching_groups: list[tuple[int, set[str], set[str]]] = []
        best_failed: tuple[int, list[str], list[str]] | None = None
        best_failed_score: int | None = None

        for group_index, (required_tags, forbidden_tags) in enumerate(groups, start=1):
            missing = sorted(required_tags.difference(tags), key=str.casefold)
            blocked = sorted(forbidden_tags.intersection(tags), key=str.casefold)
            group_has_positive = bool(required_tags or global_required)
            group_matches = group_has_positive and not missing and not blocked

            if group_matches:
                matching_groups.append((group_index, required_tags, forbidden_tags))
                continue

            score = len(missing) + len(blocked)
            if best_failed_score is None or score < best_failed_score:
                best_failed_score = score
                best_failed = (group_index, missing, blocked)

        if matching_groups:
            for group_index, required_tags, forbidden_tags in matching_groups:
                block.append(f"  ODER-Gruppe {group_index}: passt")
                if required_tags:
                    block.append("    Muss: " + ", ".join(sorted(required_tags, key=str.casefold)))
                if forbidden_tags:
                    block.append("    Ausschluss nicht vorhanden: " + ", ".join(f"-{tag}" for tag in sorted(forbidden_tags, key=str.casefold)))
            summary = f"{len(matching_groups)} Gruppe(n) erfüllt"
            block.append(f"  Ergebnis: passt, {summary}")
            return True, "\n".join(block), summary

        failed_reason = "keine ODER-Gruppe erfüllt"
        block.append(f"  Ergebnis: passt nicht, {failed_reason}")
        if best_failed is not None:
            group_index, missing, blocked = best_failed
            details: list[str] = []
            if missing:
                details.append("fehlt: " + ", ".join(missing[:12]))
            if blocked:
                details.append("blockiert: " + ", ".join(f"-{tag}" for tag in blocked[:12]))
            if details:
                block.append(f"  Nächste Gruppe {group_index}: " + "; ".join(details))
                failed_reason += f"; Gruppe {group_index}: " + "; ".join(details)
            else:
                block.append(f"  Nächste Gruppe {group_index}: reine Ausschlussgruppe oder leere Gruppe")
                failed_reason += f"; Gruppe {group_index}: keine positive Trefferbedingung"
        return False, "\n".join(block), failed_reason

    def output_directory_for_category(self, category: CategoryMatch) -> Path:
        if category.output_path:
            return Path(str(category.output_path))

        default_output_dir = Path(str(self.config.get("default_output_dir", "./danbooru_saved")))
        return default_output_dir / category.folder_name
