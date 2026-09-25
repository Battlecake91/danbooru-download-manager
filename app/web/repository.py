from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from app.core.category_engine import build_category_match_groups
from app.core.database import Database
from app.core.recommendation_engine import RecommendationEngine, RecommendationScore


SORT_SQL = {
    "id_desc": "p.id DESC",
    "id_asc": "p.id ASC",
    "score_desc": "COALESCE(p.score, -999999) DESC, p.id DESC",
    "score_asc": "COALESCE(p.score, 999999) ASC, p.id DESC",
    "favorites_desc": "COALESCE(p.fav_count, 0) DESC, p.id DESC",
    "llm_score_desc": "COALESCE(p.llm_score, -999999) DESC, p.id DESC",
    "llm_score_asc": "COALESCE(p.llm_score, 999999) ASC, p.id DESC",
    "personal_desc": "COALESCE(pr.stars, -1) DESC, p.id DESC",
    "personal_asc": "COALESCE(pr.stars, 999) ASC, p.id DESC",
    "rating": "CASE p.rating WHEN 'g' THEN 0 WHEN 's' THEN 1 WHEN 'q' THEN 2 WHEN 'e' THEN 3 ELSE 9 END ASC, p.id DESC",
    "status": "CASE p.status WHEN 'new' THEN 0 WHEN 'potential' THEN 1 WHEN 'saved' THEN 2 WHEN 'already_known' THEN 3 WHEN 'rejected' THEN 4 ELSE 9 END ASC, p.id DESC",
    "category": "COALESCE(c.name, '_unmatched') COLLATE NOCASE ASC, p.id DESC",
    "saved_desc": "COALESCE(p.saved_at, '') DESC, p.id DESC",
    "seen_desc": "COALESCE(p.last_seen_at, '') DESC, p.id DESC",
    "resolution_desc": "COALESCE(p.image_width, 0) * COALESCE(p.image_height, 0) DESC, p.id DESC",
    "filesize_desc": "COALESCE(p.file_size, 0) DESC, p.id DESC",
}

RECOMMENDATION_SORTS = {"recommendation_desc", "recommendation_asc", "local_score_desc"}
POST_JOINS = """
LEFT JOIN post_reviews pr ON pr.post_id = p.id
LEFT JOIN post_categories pc ON pc.post_id = p.id
LEFT JOIN categories c ON c.id = pc.category_id
"""


def row_dict(row: Any) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def apply_category_suggestions(db: Database, posts: list[dict[str, Any]]) -> None:
    """Apply the same rule-based category fallback shown by the desktop preview."""
    category_rows = [row_dict(row) for row in db.list_categories_full()]
    rules_by_category: dict[int, list[Any]] = {}
    for rule in db.list_category_rules():
        rules_by_category.setdefault(int(rule["category_id"]), []).append(rule)

    prepared: list[tuple[int, str, list[tuple[set[str], set[str]]]]] = []
    fallback = next((row for row in category_rows if str(row["name"]) == "_unmatched"), None)
    for category in category_rows:
        category_id = int(category["id"])
        groups = build_category_match_groups(rules_by_category.get(category_id, []))
        if groups:
            prepared.append((category_id, str(category["name"]), groups))

    for post in posts:
        if post.get("category_id") is not None:
            post["category_id"] = int(post["category_id"])
            post["category_source"] = str(post.get("category_source") or "manual")
            continue

        tags = {tag for tag in str(post.get("tags") or "").split() if tag}
        suggestion: tuple[int, str] | None = None
        for category_id, name, groups in prepared:
            if any(
                required.issubset(tags) and not forbidden.intersection(tags)
                for required, forbidden in groups
                if required
            ):
                suggestion = (category_id, name)
                break

        if suggestion is not None:
            post["category_id"], post["category"] = suggestion
            post["category_source"] = "automatic"
        elif fallback is not None:
            post["category_id"] = int(fallback["id"])
            post["category"] = str(fallback["name"])
            post["category_source"] = "automatic"
        else:
            post["category_id"] = None
            post["category"] = None
            post["category_source"] = "unassigned"


def build_post_filter(status: str, search: str) -> tuple[str, list[Any]]:
    parts: list[str] = []
    params: list[Any] = []
    status = status.strip().lower()
    if status and status != "all":
        if status == "worklist":
            parts.append("p.status IN ('new', 'potential')")
        else:
            parts.append("p.status = ?")
            params.append(status)

    for raw_term in search.split():
        negative = raw_term.startswith("-") and len(raw_term) > 1
        term = raw_term[1:] if negative else raw_term
        if not term:
            continue
        if negative:
            parts.append(
                "NOT EXISTS (SELECT 1 FROM post_tags nx WHERE nx.post_id = p.id AND nx.tag = ? COLLATE NOCASE)"
            )
            params.append(term)
        else:
            parts.append(
                "(CAST(p.id AS TEXT) LIKE ? OR EXISTS "
                "(SELECT 1 FROM post_tags sx WHERE sx.post_id = p.id AND sx.tag = ? COLLATE NOCASE))"
            )
            params.extend([f"%{term}%", term])
    return ("WHERE " + " AND ".join(parts), params) if parts else ("", params)


def recommendation_results(
    db: Database,
    where_sql: str,
    params: list[Any],
) -> dict[int, RecommendationScore]:
    rows = db.execute(
        f"""
        SELECT p.id,
               (SELECT GROUP_CONCAT(pt.tag, ' ') FROM post_tags pt WHERE pt.post_id = p.id) AS tags
        FROM posts p
        {where_sql}
        ORDER BY p.id DESC
        """,
        params,
    ).fetchall()
    tag_sets = [str(row["tags"] or "").split() for row in rows]
    scores = RecommendationEngine(db).score_tag_sets(tag_sets)
    return {int(row["id"]): score for row, score in zip(rows, scores)}


def recommendation_summary(results: dict[int, RecommendationScore]) -> dict[str, float] | None:
    if not results:
        return None
    scores = [float(result.score) for result in results.values()]
    return {
        "best": max(scores),
        "worst": min(scores),
        "average": round(sum(scores) / len(scores), 2),
    }


def recommendation_order(results: dict[int, RecommendationScore], sort: str) -> list[int]:
    ascending = sort == "recommendation_asc"
    if ascending:
        return sorted(results, key=lambda post_id: (results[post_id].score, -post_id))
    return sorted(results, key=lambda post_id: (-results[post_id].score, -post_id))


def apply_recommendations(posts: list[dict[str, Any]], results: dict[int, RecommendationScore]) -> None:
    for post in posts:
        result = results.get(int(post["id"]))
        if result is None:
            continue
        post["local_score"] = result.score
        post["recommendation_score"] = result.score
        post["recommendation_positive"] = ", ".join(result.positive)
        post["recommendation_negative"] = ", ".join(result.negative)
        post["recommendation_ignored_count"] = len(result.ignored)
        post["recommendation_used_count"] = result.used_count


def select_post_rows(
    db: Database,
    where_sql: str,
    params: list[Any],
    *,
    order_sql: str,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict[str, Any]]:
    pagination = "" if limit is None else "LIMIT ? OFFSET ?"
    query_params = params if limit is None else [*params, limit, offset]
    rows = db.execute(
        f"""
        SELECT
            p.id, p.rating, p.score, p.fav_count, p.image_width, p.image_height,
            p.file_size, p.status, p.local_score, p.llm_score, p.final_score,
            p.saved_at, p.last_seen_at, p.thumbnail_path, p.rejected_thumbnail_path,
            p.preview_url, p.large_file_url, p.file_url, p.final_file_path,
            pr.stars,
            c.id AS category_id,
            c.name AS category,
            pc.source AS category_source,
            (SELECT GROUP_CONCAT(pt.tag, ' ') FROM post_tags pt WHERE pt.post_id = p.id) AS tags
        FROM posts p
        {POST_JOINS}
        {where_sql}
        ORDER BY {order_sql}
        {pagination}
        """,
        query_params,
    ).fetchall()
    return [row_dict(row) for row in rows]


def list_posts(
    db: Database,
    *,
    status: str,
    search: str,
    sort: str,
    offset: int,
    limit: int,
) -> dict[str, Any]:
    where_sql, params = build_post_filter(status, search)
    count_row = db.execute(f"SELECT COUNT(*) AS total FROM posts p {where_sql}", params).fetchone()
    all_recommendations: dict[int, RecommendationScore] | None = None
    if sort in RECOMMENDATION_SORTS:
        all_recommendations = recommendation_results(db, where_sql, params)
        ordered_ids = recommendation_order(all_recommendations, "recommendation_asc" if sort == "recommendation_asc" else "recommendation_desc")
        page_ids = ordered_ids[offset : offset + limit]
        if page_ids:
            placeholders = ", ".join("?" for _ in page_ids)
            posts = select_post_rows(
                db,
                f"WHERE p.id IN ({placeholders})",
                page_ids,
                order_sql="p.id DESC",
            )
            positions = {post_id: index for index, post_id in enumerate(page_ids)}
            posts.sort(key=lambda post: positions[int(post["id"])])
        else:
            posts = []
    else:
        order_sql = SORT_SQL.get(sort, SORT_SQL["id_desc"])
        posts = select_post_rows(db, where_sql, params, order_sql=order_sql, limit=limit, offset=offset)

    if all_recommendations is None and offset == 0:
        all_recommendations = recommendation_results(db, where_sql, params)
    page_recommendations = all_recommendations
    if page_recommendations is None:
        page_ids = [int(post["id"]) for post in posts]
        if page_ids:
            placeholders = ", ".join("?" for _ in page_ids)
            page_recommendations = recommendation_results(db, f"WHERE p.id IN ({placeholders})", page_ids)
        else:
            page_recommendations = {}
    apply_recommendations(posts, page_recommendations)
    apply_category_suggestions(db, posts)
    for post in posts:
        post["thumbnail_url"] = f"/api/media/{post['id']}/thumbnail"
    total = int(count_row["total"] if count_row else 0)
    return {
        "items": posts,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + len(posts) < total,
        "preselection_summary": recommendation_summary(all_recommendations or {}) if offset == 0 else None,
    }


def matching_post_ids(db: Database, *, status: str, search: str, sort: str) -> list[int]:
    where_sql, params = build_post_filter(status, search)
    if sort in RECOMMENDATION_SORTS:
        results = recommendation_results(db, where_sql, params)
        return recommendation_order(results, "recommendation_asc" if sort == "recommendation_asc" else "recommendation_desc")
    order_sql = SORT_SQL.get(sort, SORT_SQL["id_desc"])
    rows = db.execute(
        f"SELECT p.id FROM posts p {POST_JOINS} {where_sql} ORDER BY {order_sql}",
        params,
    ).fetchall()
    return [int(row["id"]) for row in rows]


def post_detail(
    db: Database,
    post_id: int,
    *,
    status: str,
    search: str,
    sort: str,
) -> dict[str, Any] | None:
    row = db.get_post_detail(post_id)
    if row is None:
        return None
    post = row_dict(row)
    category = db.get_assigned_category_for_post(post_id)
    post["category_id"] = int(category["id"]) if category is not None else None
    post["category"] = str(category["name"]) if category is not None else None
    post["category_source"] = str(category["assignment_source"] or "manual") if category is not None else None
    post["categories"] = [row_dict(item) for item in db.list_categories_full()]
    post["image_url"] = f"/api/media/{post_id}/viewer"

    tag_rows = db.execute(
        """
        SELECT tag, COALESCE(NULLIF(tag_type, ''), 'general') AS tag_type
        FROM post_tags
        WHERE post_id = ?
        ORDER BY
            CASE tag_type
                WHEN 'artist' THEN 1
                WHEN 'copyright' THEN 2
                WHEN 'character' THEN 3
                WHEN 'general' THEN 4
                WHEN 'meta' THEN 5
                ELSE 9
            END,
            tag COLLATE NOCASE
        """,
        (post_id,),
    ).fetchall()
    typed_tags: dict[str, list[dict[str, Any]]] = {
        "artist": [],
        "copyright": [],
        "character": [],
        "general": [],
        "meta": [],
    }
    tag_names = [str(item["tag"]) for item in tag_rows]
    post["tags"] = " ".join(tag_names)
    apply_category_suggestions(db, [post])
    recommendation = RecommendationEngine(db).score_tags(tag_names)
    post["local_score"] = recommendation.score
    post["recommendation_score"] = recommendation.score
    post["recommendation_positive"] = ", ".join(recommendation.positive)
    post["recommendation_negative"] = ", ".join(recommendation.negative)
    post["recommendation_ignored_count"] = len(recommendation.ignored)
    post["recommendation_used_count"] = recommendation.used_count
    tag_metadata = db.fetch_tag_display_metadata(tag_names)
    for item in tag_rows:
        tag = str(item["tag"])
        tag_type = str(item["tag_type"] or "general")
        if tag_type not in typed_tags:
            tag_type = "general"
        typed_tags[tag_type].append({"tag": tag, **tag_metadata.get(tag, {})})
    post["typed_tags"] = typed_tags

    ids = matching_post_ids(db, status=status, search=search, sort=sort)
    try:
        index = ids.index(post_id)
    except ValueError:
        index = -1
    post["navigation"] = {
        "index": index,
        "total": len(ids),
        "previous_id": ids[index - 1] if index > 0 else None,
        "next_id": ids[index + 1] if 0 <= index < len(ids) - 1 else None,
    }
    strip_ids = ids[max(0, index - 3) : index + 4] if index >= 0 else [post_id]
    strip_rows: dict[int, dict[str, Any]] = {}
    if strip_ids:
        placeholders = ", ".join("?" for _ in strip_ids)
        rows = db.execute(
            f"""
            SELECT id, status, score, thumbnail_path, rejected_thumbnail_path, preview_url
            FROM posts
            WHERE id IN ({placeholders})
            """,
            strip_ids,
        ).fetchall()
        strip_rows = {int(item["id"]): row_dict(item) for item in rows}
    post["preview_strip"] = [
        {
            **strip_rows[item_id],
            "active": item_id == post_id,
            "thumbnail_url": f"/api/media/{item_id}/thumbnail",
        }
        for item_id in strip_ids
        if item_id in strip_rows
    ]
    return post


def resolve_media_path(config: dict[str, Any], post: dict[str, Any], variant: str) -> Path | None:
    if variant == "thumbnail":
        fields = ("thumbnail_path", "rejected_thumbnail_path")
        roots = (
            config.get("active_thumbnail_dir"),
            config.get("saved_thumbnail_dir"),
            config.get("rejected_thumbnail_dir"),
        )
    else:
        fields = ("original_cache_path", "original_path", "final_file_path")
        roots = (
            config.get("original_cache_dir"),
            config.get("default_output_dir"),
        )

    allowed_roots = [Path(str(root)).resolve() for root in roots if root]
    candidates: list[Path] = []
    for field in fields:
        raw = str(post.get(field) or "").strip()
        if raw:
            source = Path(raw)
            candidates.append(source)
            portable_names = {
                source.name,
                PureWindowsPath(raw).name,
                PurePosixPath(raw).name,
            }
            candidates.extend(root / name for root in allowed_roots for name in portable_names if name)
    post_id = str(post.get("id") or "")
    for root in allowed_roots:
        candidates.extend(root.glob(f"{post_id}.*"))

    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            if not resolved.is_file():
                continue
            if any(resolved == root or root in resolved.parents for root in allowed_roots):
                return resolved
        except OSError:
            continue
    return None
