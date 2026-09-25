from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from app.core.database import Database


SORT_SQL = {
    "id_desc": "p.id DESC",
    "id_asc": "p.id ASC",
    "score_desc": "COALESCE(p.score, 0) DESC, p.id DESC",
    "favorites_desc": "COALESCE(p.fav_count, 0) DESC, p.id DESC",
    "local_score_desc": "COALESCE(p.local_score, 0) DESC, p.id DESC",
}


def row_dict(row: Any) -> dict[str, Any]:
    return dict(row) if row is not None else {}


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
    order_sql = SORT_SQL.get(sort, SORT_SQL["id_desc"])
    count_row = db.execute(f"SELECT COUNT(*) AS total FROM posts p {where_sql}", params).fetchone()
    rows = db.execute(
        f"""
        SELECT
            p.id, p.rating, p.score, p.fav_count, p.image_width, p.image_height,
            p.status, p.local_score, p.thumbnail_path, p.rejected_thumbnail_path,
            p.preview_url, p.large_file_url, p.file_url, p.final_file_path,
            pr.stars,
            c.name AS category,
            (SELECT GROUP_CONCAT(pt.tag, ' ') FROM post_tags pt WHERE pt.post_id = p.id) AS tags
        FROM posts p
        LEFT JOIN post_reviews pr ON pr.post_id = p.id
        LEFT JOIN post_categories pc ON pc.post_id = p.id
        LEFT JOIN categories c ON c.id = pc.category_id
        {where_sql}
        ORDER BY {order_sql}
        LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    ).fetchall()
    posts = [row_dict(row) for row in rows]
    for post in posts:
        post["thumbnail_url"] = f"/api/media/{post['id']}/thumbnail"
    total = int(count_row["total"] if count_row else 0)
    return {
        "items": posts,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + len(posts) < total,
    }


def matching_post_ids(db: Database, *, status: str, search: str, sort: str) -> list[int]:
    where_sql, params = build_post_filter(status, search)
    order_sql = SORT_SQL.get(sort, SORT_SQL["id_desc"])
    rows = db.execute(f"SELECT p.id FROM posts p {where_sql} ORDER BY {order_sql}", params).fetchall()
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
    post["category"] = str(category["name"]) if category is not None else None
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
