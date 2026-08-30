from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import math

from app.core.archive_paths import resolve_archive_path
from app.core.database import Database
from app.core.tag_privacy import canonicalize_tag, normalize_tag_token


@dataclass(frozen=True)
class CategoryMatch:
    id: int | None
    name: str
    folder_name: str
    output_path: str | None
    matched: bool
    reason: str




@dataclass(frozen=True)
class CategoryInfluence:
    category_id: int
    name: str
    score: float
    matched_tags: int
    examples: int
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
        self._category_influence_rows_by_tag: dict[str, list[dict[str, Any]]] = {}
        self._category_influence_aliases: dict[str, str] | None = None

    def clear_category_influence_cache(self) -> None:
        """Drop cached influence statistics.

        This is intentionally small and safe to call after category/tag-score
        maintenance. The viewer benefits from caching, but nobody wants stale
        hints after a bulk edit. Well, nobody sane.
        """
        self._category_influence_rows_by_tag.clear()
        self._category_influence_aliases = None

    def _tag_aliases_for_influence(self) -> dict[str, str]:
        if self._category_influence_aliases is None:
            self._category_influence_aliases = self.db.list_tag_alias_map()
        return self._category_influence_aliases

    def _category_tag_hits_cached(self, tags: set[str]) -> list[dict[str, Any]]:
        clean_tags = {normalize_tag_token(str(tag)) for tag in tags if normalize_tag_token(str(tag))}
        if not clean_tags:
            return []

        missing_tags = sorted(tag for tag in clean_tags if tag not in self._category_influence_rows_by_tag)
        if missing_tags:
            for tag in missing_tags:
                self._category_influence_rows_by_tag[tag] = []
            for row in self.db.fetch_category_tag_hits(missing_tags):
                tag = normalize_tag_token(str(row["tag"] or ""))
                if not tag:
                    continue
                self._category_influence_rows_by_tag.setdefault(tag, []).append({key: row[key] for key in row.keys()})

        rows: list[dict[str, Any]] = []
        for tag in clean_tags:
            rows.extend(self._category_influence_rows_by_tag.get(tag, []))
        return rows

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
                    reason="Manual selection",
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
            reason="Manual selection",
        )

    def tag_hint_category_mode(self) -> str:
        viewer_config = self.config.get("viewer", {}) or {}
        mode = str(viewer_config.get("tag_hint_category_mode", "never")).lower()
        if mode not in {"never", "only_when_unmatched", "always"}:
            return "never"
        return mode

    def category_match_from_influence(self, influence: CategoryInfluence) -> CategoryMatch | None:
        category = self.category_by_name(influence.name)
        if category is None:
            return None

        return CategoryMatch(
            id=category.id,
            name=category.name,
            folder_name=category.folder_name,
            output_path=category.output_path,
            matched=True,
            reason=f"Tag hint selected ({influence.score:g})",
        )

    def best_tag_hint_category_for_tags(self, tags: set[str]) -> CategoryMatch | None:
        for influence in self.category_influence_for_tags(tags):
            if influence.name == "_unmatched":
                continue
            category = self.category_match_from_influence(influence)
            if category is not None:
                return category
        return None

    def suggest_category_for_post(self, post_id: int) -> CategoryMatch:
        tags = self.get_post_tags(post_id)
        tag_hint_mode = self.tag_hint_category_mode()
        tag_hint_category = self.best_tag_hint_category_for_tags(tags) if tag_hint_mode != "never" else None

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

                if tag_hint_mode == "always" and tag_hint_category is not None:
                    return tag_hint_category

                return CategoryMatch(
                    id=category_id,
                    name=str(category["name"]),
                    folder_name=str(category["folder_name"]),
                    output_path=category["output_path"],
                    matched=True,
                    reason="Category rule matches",
                )

        if tag_hint_mode in {"only_when_unmatched", "always"} and tag_hint_category is not None:
            return tag_hint_category

        unmatched = self.category_by_name("_unmatched")
        if unmatched is not None:
            return CategoryMatch(
                id=unmatched.id,
                name=unmatched.name,
                folder_name=unmatched.folder_name,
                output_path=unmatched.output_path,
                matched=False,
                reason="No category rule matches, fallback",
            )

        return CategoryMatch(
            id=None,
            name="_unmatched",
            folder_name="_unmatched",
            output_path=None,
            matched=False,
            reason="No category rule matches, internal fallback",
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

    def category_influence_for_post(self, post_id: int) -> list[CategoryInfluence]:
        """Return soft category hints based on already sorted examples.

        This does not replace hard category rules. It is a preparation layer for
        later LLM/category weighting: aliases are resolved, personal tag scores
        dampen or boost tag contributions, and previous category assignments form
        the example base.
        """
        return self.category_influence_for_tags(self.get_post_tags(post_id))

    def category_influence_for_tags(self, tags: set[str]) -> list[CategoryInfluence]:
        clean_tags = {normalize_tag_token(tag) for tag in tags if normalize_tag_token(tag)}
        if not clean_tags:
            return []

        tag_metadata_for_current = self.db.fetch_tag_display_metadata(clean_tags)
        ignored_current_tags = {
            tag
            for tag, metadata in tag_metadata_for_current.items()
            if bool(metadata.get("ignore_category_influence"))
        }
        effective_clean_tags = clean_tags.difference(ignored_current_tags)
        if not effective_clean_tags:
            return []

        aliases = self._tag_aliases_for_influence()
        canonical_tags = {canonicalize_tag(tag, aliases) for tag in effective_clean_tags}
        canonical_tags.discard("")
        if not canonical_tags:
            return []

        # Expand current canonical tags back to known original aliases so
        # red_hairband -> hairband can match older blue_hairband examples.
        candidate_original_tags = set(effective_clean_tags)
        for original, alias in aliases.items():
            if canonicalize_tag(original, aliases) in canonical_tags or canonicalize_tag(alias, aliases) in canonical_tags:
                candidate_original_tags.add(original)
                candidate_original_tags.add(alias)

        rows = self._category_tag_hits_cached(candidate_original_tags)
        if not rows:
            return []

        tag_metadata = self.db.fetch_tag_display_metadata(candidate_original_tags)
        category_scores: dict[int, dict[str, Any]] = {}
        canonical_seen_by_category: dict[int, set[str]] = {}

        for row in rows:
            category_id = int(row["category_id"])
            original_tag = normalize_tag_token(str(row["tag"] or ""))
            canonical_tag = canonicalize_tag(original_tag, aliases)
            if canonical_tag not in canonical_tags:
                continue

            hit_count = int(row["hit_count"] or 0)
            saved_hits = int(row["saved_hits"] or 0)
            avg_stars = row["avg_stars"]
            category_post_count = max(1, int(row["category_post_count"] or 0))
            tag_total_hits = max(1, int(row["tag_total_hits"] or 0))
            categorized_post_count = max(1, int(row["categorized_post_count"] or 0))

            metadata = tag_metadata.get(original_tag, {})
            if bool(metadata.get("ignore_category_influence")):
                continue
            try:
                tag_score = float(metadata.get("score", 0.0) or 0.0)
            except (TypeError, ValueError):
                tag_score = 0.0

            try:
                star_bonus = (float(avg_stars) - 5.0) / 12.0 if avg_stars is not None else 0.0
            except (TypeError, ValueError):
                star_bonus = 0.0

            # Use lift instead of raw frequency. Raw frequency made broad tags
            # such as "1girl" always point to the largest category. Lift asks:
            # is this tag more typical for this category than for all saved
            # category examples? That is the actual hint we need. Imagine that.
            category_ratio = hit_count / category_post_count
            global_ratio = tag_total_hits / categorized_post_count
            lift = category_ratio / max(global_ratio, 0.0001)

            # Tags that appear almost everywhere are bad evidence. They still get
            # a tiny vote, but not enough to drown distinctive tags.
            ubiquity = tag_total_hits / categorized_post_count
            distinctiveness = max(0.05, 1.0 - ubiquity)

            # Saturate repeated hits. Seeing the same tag 500 times in one large
            # category should not be 500 times more convincing.
            support = math.log1p(hit_count)
            lift_weight = max(0.0, math.log2(max(lift, 0.01)))
            saved_weight = min(saved_hits / category_post_count, 1.0) * 0.25
            score_weight = max(-0.5, min(0.5, tag_score / 10.0))
            contribution = support * lift_weight * distinctiveness * (1.0 + score_weight + star_bonus + saved_weight)
            if contribution <= 0:
                continue

            bucket = category_scores.setdefault(
                category_id,
                {
                    "category_id": category_id,
                    "name": str(row["category_name"]),
                    "score": 0.0,
                    "examples": 0,
                    "tags": {},
                },
            )
            bucket["score"] += contribution
            bucket["examples"] += hit_count
            tag_bucket = bucket["tags"].setdefault(
                canonical_tag,
                {"display": canonical_tag, "hits": 0, "score": 0.0},
            )
            tag_bucket["hits"] += hit_count
            tag_bucket["score"] += contribution
            canonical_seen_by_category.setdefault(category_id, set()).add(canonical_tag)

        influences: list[CategoryInfluence] = []
        for category_id, bucket in category_scores.items():
            tags_sorted = sorted(
                bucket["tags"].values(),
                key=lambda item: (-float(item["score"]), str(item["display"]).casefold()),
            )
            reason_parts = [f"{item['display']} ({item['hits']}x)" for item in tags_sorted[:8]]
            if len(tags_sorted) > 8:
                reason_parts.append(f"+{len(tags_sorted) - 8} more")
            score = round(float(bucket["score"]), 2)
            if score <= 0:
                continue
            influences.append(
                CategoryInfluence(
                    category_id=category_id,
                    name=str(bucket["name"]),
                    score=score,
                    matched_tags=len(canonical_seen_by_category.get(category_id, set())),
                    examples=int(bucket["examples"]),
                    reason=", ".join(reason_parts) if reason_parts else "no usable matches",
                )
            )

        influences.sort(key=lambda item: (-item.score, item.name.casefold()))
        return influences

    def build_category_decision_report_for_post(
        self,
        post_id: int,
        selected_category_name: str | None = None,
    ) -> str:
        tags = self.get_post_tags(post_id)
        if not tags:
            return f"Post {post_id} was not found or has no stored tags."

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

        tag_metadata = self.db.fetch_tag_metadata(tags)
        ignored_influence_tags = sorted(
            [tag for tag, metadata in tag_metadata.items() if bool(metadata.get("ignore_category_influence"))],
            key=str.casefold,
        )
        influences = self.category_influence_for_tags(tags)
        influence_by_name = {entry.name: entry for entry in influences}
        top_influence = influences[0] if influences else None
        tag_hint_category = self.best_tag_hint_category_for_tags(tags)
        tag_hint_mode = self.tag_hint_category_mode()

        automatic_name = winner_name or "_unmatched"
        if tag_hint_category is not None and (tag_hint_mode == "always" or (tag_hint_mode == "only_when_unmatched" and winner_name is None)):
            automatic_name = tag_hint_category.name
        lines: list[str] = [title]
        lines.append(f"Automatic: {automatic_name}")
        if top_influence is not None:
            lines.append(f"Tag influence: {top_influence.name} (+{top_influence.score:g})")
            if tag_hint_category is not None and automatic_name == tag_hint_category.name:
                lines.append(f"Note: tag hint mode '{tag_hint_mode}' selected the category from tag influence.")
            elif automatic_name != "_unmatched" and top_influence.name != automatic_name:
                lines.append("Note: Hard category rules take precedence over tag influence.")
            elif automatic_name == "_unmatched":
                lines.append("Note: tag influence is currently only a hint and does not replace a rule yet.")
        if selected_category_name:
            lines.append(f"Currently selected: {selected_category_name}")
            if selected_category_name != automatic_name:
                lines.append("Deviation: manual selection overrides the automatic suggestion.")
        lines.append(f"Tags in post: {len(tags)}")
        if ignored_influence_tags:
            lines.append(f"Ignored for category hint: {', '.join(ignored_influence_tags[:20])}" + (f" … +{len(ignored_influence_tags) - 20}" if len(ignored_influence_tags) > 20 else ""))
        lines.append("Order: The first matching category wins.")
        lines.append("")

        lines.append("Quick overview")
        if matched_names:
            lines.append(f"Matches: {', '.join(matched_names)}")
            if len(matched_names) > 1:
                lines.append(f"Additional matching categories after the winner: {', '.join(matched_names[1:])}")
        else:
            lines.append("Match: no category, therefore fallback _unmatched")
        if influences:
            preview = "; ".join(
                f"{entry.name} +{entry.score:g}" for entry in influences[:5]
            )
            lines.append(f"Top tag influence: {preview}")
        else:
            lines.append("Tag influence: no usable earlier category examples")
        lines.append("")

        if influences:
            lines.append("Tag influence details")
            for entry in influences[:5]:
                lines.append(
                    f"[{entry.name}] +{entry.score:g} | Tags: {entry.matched_tags} | Examples: {entry.examples}"
                )
                lines.append(f"  Matches: {entry.reason}")
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
            lines.append("Relevant details")
            for entry in important_blocks:
                lines.append(str(entry["block"]))
                lines.append("")

        blocked_entries = [entry for entry in evaluations if not entry["matched"] and entry["name"] not in important_names]
        if blocked_entries:
            lines.append("Non-matching categories, short summary")
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
            summary = "no positive group or global required condition"
            block.append(f"  Result: no match, {summary}")
            return False, "\n".join(block), summary

        global_missing = sorted(global_required.difference(tags), key=str.casefold)
        global_blocked = sorted(global_forbidden.intersection(tags), key=str.casefold)

        if global_missing or global_blocked:
            reasons: list[str] = []
            if global_missing:
                reasons.append("globally missing: " + ", ".join(global_missing))
            if global_blocked:
                reasons.append("globally blocked: " + ", ".join(f"-{tag}" for tag in global_blocked))
            summary = "; ".join(reasons)
            block.append(f"  Result: no match, {summary}")
            return False, "\n".join(block), summary

        if global_required or global_forbidden:
            block.append("  Global conditions: met")
            if global_required:
                block.append("    Required: " + ", ".join(sorted(global_required, key=str.casefold)))
            if global_forbidden:
                block.append("    Exclusion absent: " + ", ".join(f"-{tag}" for tag in sorted(global_forbidden, key=str.casefold)))

        if not groups and global_required:
            summary = "global required conditions met"
            block.append(f"  Result: matches, {summary}")
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
                block.append(f"  OR group {group_index}: matches")
                if required_tags:
                    block.append("    Required: " + ", ".join(sorted(required_tags, key=str.casefold)))
                if forbidden_tags:
                    block.append("    Exclusion absent: " + ", ".join(f"-{tag}" for tag in sorted(forbidden_tags, key=str.casefold)))
            summary = f"{len(matching_groups)} group(s) met"
            block.append(f"  Result: matches, {summary}")
            return True, "\n".join(block), summary

        failed_reason = "no OR group met"
        block.append(f"  Result: no match, {failed_reason}")
        if best_failed is not None:
            group_index, missing, blocked = best_failed
            details: list[str] = []
            if missing:
                details.append("missing: " + ", ".join(missing[:12]))
            if blocked:
                details.append("blocked: " + ", ".join(f"-{tag}" for tag in blocked[:12]))
            if details:
                block.append(f"  Closest group {group_index}: " + "; ".join(details))
                failed_reason += f"; group {group_index}: " + "; ".join(details)
            else:
                block.append(f"  Closest group {group_index}: pure exclusion group or empty group")
                failed_reason += f"; group {group_index}: no positive match condition"
        return False, "\n".join(block), failed_reason

    def output_directory_for_category(self, category: CategoryMatch) -> Path:
        if category.output_path:
            return resolve_archive_path(self.config, category.output_path) or Path(str(category.output_path))

        default_output_dir = Path(str(self.config.get("default_output_dir", "./danbooru_saved")))
        return default_output_dir / category.folder_name
