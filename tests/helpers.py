from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Iterable

from app.core.config import load_config
from app.core.database import Database
from app.core.paths import ensure_runtime_dirs


def temp_config(base_dir: Path) -> dict[str, Any]:
    config = load_config()
    config["work_dir"] = str(base_dir / "data")
    config["database_file"] = str(base_dir / "data" / "danbooru_manager.db")
    config["thumbnail_dir"] = str(base_dir / "data" / "thumbnails" / "active")
    config["active_thumbnail_dir"] = str(base_dir / "data" / "thumbnails" / "active")
    config["saved_thumbnail_dir"] = str(base_dir / "data" / "thumbnails" / "saved")
    config["rejected_thumbnail_dir"] = str(base_dir / "data" / "thumbnails" / "rejected")
    config["original_cache_dir"] = str(base_dir / "data" / "originals" / "cache")
    config["default_output_dir"] = str(base_dir / "saved")
    config["history_file"] = str(base_dir / "downloaded_ids.txt")
    ensure_runtime_dirs(config)
    return config


def open_temp_database(base_dir: Path) -> tuple[dict[str, Any], Database]:
    config = temp_config(base_dir)
    db = Database(Path(config["database_file"]))
    db.connect()
    db.initialize_schema()
    return config, db


def explain_plan(db: Database, sql: str, parameters: Iterable[Any] = ()) -> list[str]:
    rows = db.execute("EXPLAIN QUERY PLAN " + sql, tuple(parameters)).fetchall()
    return [str(row["detail"]) for row in rows]


def assert_plan_uses_index(testcase: Any, plan: list[str], index_name: str) -> None:
    joined = "\n".join(plan)
    testcase.assertIn(
        index_name,
        joined,
        msg=f"Expected query plan to use {index_name}, got:\n{joined}",
    )


def timed(callable_: Callable[[], Any]) -> tuple[Any, float]:
    started_at = time.perf_counter()
    result = callable_()
    return result, time.perf_counter() - started_at


def seed_posts_with_tags(db: Database, count: int = 3000, tags_per_post: int = 5) -> None:
    statuses = ("new", "potential", "saved", "rejected", "already_known")
    post_rows = []
    tag_rows = []
    score_rows = []
    for post_id in range(1, count + 1):
        status = statuses[post_id % len(statuses)]
        parent_id = post_id - 1 if post_id % 25 == 0 else None
        final_file_path = f"C:/library/{post_id}.jpg" if status == "saved" else None
        post_rows.append(
            (
                post_id,
                "danbooru",
                "g",
                post_id % 1000,
                post_id % 250,
                "jpg",
                f"https://example.invalid/{post_id}.jpg",
                f"https://example.invalid/large/{post_id}.jpg",
                f"https://example.invalid/preview/{post_id}.jpg",
                1024 + (post_id % 500),
                768 + (post_id % 400),
                100000 + post_id,
                parent_id,
                1 if post_id % 25 == 1 else 0,
                status,
                final_file_path,
                "2026-01-01T00:00:00Z",
            )
        )
        for index in range(tags_per_post):
            tag = f"tag_{(post_id + index) % 500:03d}"
            tag_type = ("general", "character", "copyright", "artist", "meta")[index % 5]
            tag_rows.append((post_id, tag, tag_type))
            score_rows.append((tag,))
        shared_tag = "shared_hot_tag" if post_id % 2 == 0 else "shared_cold_tag"
        tag_rows.append((post_id, shared_tag, "general"))
        score_rows.append((shared_tag,))

    db.executemany(
        """
        INSERT INTO posts (
            id, source, rating, score, fav_count, file_ext, file_url,
            large_file_url, preview_url, image_width, image_height, file_size,
            parent_id, has_children, status, final_file_path, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        post_rows,
    )
    db.executemany(
        """
        INSERT OR IGNORE INTO post_tags (post_id, tag, tag_type)
        VALUES (?, ?, ?)
        """,
        tag_rows,
    )
    db.executemany(
        """
        INSERT INTO tag_scores (tag)
        VALUES (?)
        ON CONFLICT(tag) DO NOTHING
        """,
        score_rows,
    )
    db.commit()
