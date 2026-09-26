from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Iterator

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.version import __version__
from app.danbooru.api import DanbooruApi
from app.danbooru.thumbnail_cache import ThumbnailCache
from app.services.final_save_service import AlreadySavedError, FinalSaveService
from app.web.repository import (
    RecommendationResultCache,
    list_posts,
    media_post_data,
    post_detail,
    resolve_media_path,
    row_dict,
)
from app.web.runtime import FetchController, FetchScheduler, build_web_config, fetch_overrides_from_payload, open_database


STATIC_DIR = Path(__file__).with_name("static")
ALLOWED_STATUSES = {
    "new",
    "potential",
    "selected_save",
    "saved",
    "rejected",
    "auto_rejected",
    "already_known",
    "imported",
}


class FetchRequest(BaseModel):
    preset_name: str | None = None
    payload: dict[str, Any] | None = None
    search_tags: str | None = None
    max_posts_per_query: int | None = Field(default=None, ge=1, le=100000)
    max_total_posts: int | None = Field(default=None, ge=1, le=100000)
    max_consecutive_known_posts: int | None = Field(default=None, ge=0, le=100000)


class FetchPresetRequest(BaseModel):
    payload: dict[str, Any]


class SchedulerRequest(BaseModel):
    enabled: bool = False
    interval_hours: float = Field(default=6, ge=0.25, le=8760)
    batch_size: int | None = Field(default=None, ge=50, le=200)


class PostActionRequest(BaseModel):
    status: str | None = None
    stars: float | None = Field(default=None, ge=0, le=10)
    category_id: int | None = None


class BulkPostStatusRequest(BaseModel):
    post_ids: list[int] = Field(min_length=1)
    status: str


class PostSaveRequest(BaseModel):
    category_id: int | None = None
    overwrite_existing: bool = False


class ViewerSettingsRequest(BaseModel):
    next_after_status_change: bool = True


class PreviewSettingsRequest(BaseModel):
    batch_size: int = Field(default=75, ge=50, le=200)
    thumbnail_size: int = Field(default=280, ge=120, le=600)


class TagUpdateRequest(BaseModel):
    alias: str | None = None
    manual_score: float | None = Field(default=None, ge=-10, le=10)
    scoring_excluded: bool | None = None
    filename_excluded: bool | None = None
    fetch_excluded: bool | None = None
    ignore_category_influence: bool | None = None
    ignore_recommendation_score: bool | None = None
    ignore_llm_input: bool | None = None


class CategoryRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    folder_name: str | None = Field(default=None, max_length=180)
    output_path: str | None = None
    hotkey: str | None = Field(default=None, max_length=30)
    sort_order: int | None = Field(default=None, ge=1)


class SettingsRequest(BaseModel):
    base_url: str | None = None
    username: str | None = None
    api_key: str | None = None
    request_timeout_seconds: int | None = Field(default=None, ge=5, le=300)
    request_min_interval_seconds: float | None = Field(default=None, ge=0, le=60)


def _post_statuses_by_id(db: Any, post_ids: list[int], *, chunk_size: int = 500) -> dict[int, str]:
    statuses: dict[int, str] = {}
    for start in range(0, len(post_ids), chunk_size):
        chunk = post_ids[start : start + chunk_size]
        placeholders = ", ".join("?" for _ in chunk)
        rows = db.execute(
            f"SELECT id, status FROM posts WHERE id IN ({placeholders})",
            chunk,
        ).fetchall()
        statuses.update({int(row["id"]): str(row["status"] or "new") for row in rows})
    return statuses


def create_app() -> FastAPI:
    config = build_web_config()
    fetch_controller = FetchController(config)
    scheduler = FetchScheduler(config, fetch_controller)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        scheduler.start()
        yield
        fetch_controller.cancel()
        scheduler.stop()

    app = FastAPI(title="Danbooru Download Manager Web", version=__version__, lifespan=lifespan)
    app.state.config = config
    app.state.fetch_controller = fetch_controller
    app.state.scheduler = scheduler
    app.state.recommendation_cache = RecommendationResultCache()

    def database(request: Request) -> Iterator[Any]:
        db = open_database(request.app.state.config)
        try:
            yield db
        finally:
            db.close()

    @app.get("/api/bootstrap")
    def bootstrap(request: Request, db=Depends(database)) -> dict[str, Any]:
        counts = {
            str(row["status"] or "new"): int(row["count"])
            for row in db.execute("SELECT status, COUNT(*) AS count FROM posts GROUP BY status").fetchall()
        }
        return {
            "version": __version__,
            "counts": counts,
            "scheduler": request.app.state.scheduler.settings(),
            "fetch": request.app.state.fetch_controller.snapshot(),
            "viewer": {
                "next_after_status_change": bool(
                    (request.app.state.config.get("web", {}) or {}).get("viewer_next_after_status_change", True)
                ),
            },
            "preview": {
                "batch_size": max(
                    50,
                    min(200, int((request.app.state.config.get("web", {}) or {}).get("preview_batch_size", 75) or 75)),
                ),
                "thumbnail_size": max(
                    120,
                    min(600, int((request.app.state.config.get("web", {}) or {}).get("preview_thumbnail_size", 280) or 280)),
                ),
            },
        }

    @app.get("/api/fetch")
    def fetch_status(request: Request) -> dict[str, Any]:
        return request.app.state.fetch_controller.snapshot()

    @app.post("/api/fetch", status_code=202)
    def start_fetch(payload: FetchRequest, request: Request, db=Depends(database)) -> dict[str, Any]:
        preset_payload: dict[str, Any] = {}
        if payload.preset_name:
            stored = db.get_fetch_preset(payload.preset_name)
            if stored is None:
                raise HTTPException(status_code=404, detail="Fetch preset not found")
            preset_payload.update(stored)
        if payload.payload:
            preset_payload.update(payload.payload)
        legacy_fields = payload.model_dump(exclude_unset=True, exclude={"preset_name", "payload"})
        preset_payload.update({key: value for key, value in legacy_fields.items() if value is not None})
        overrides = fetch_overrides_from_payload(preset_payload)
        request.app.state.recommendation_cache.clear()
        if not request.app.state.fetch_controller.start(overrides):
            raise HTTPException(status_code=409, detail="A fetch is already running")
        return request.app.state.fetch_controller.snapshot()

    @app.post("/api/fetch/cancel", status_code=202)
    def cancel_fetch(request: Request) -> dict[str, Any]:
        if not request.app.state.fetch_controller.cancel():
            raise HTTPException(status_code=409, detail="No fetch is running")
        return request.app.state.fetch_controller.snapshot()

    @app.get("/api/fetch-presets")
    def fetch_presets(db=Depends(database)) -> dict[str, Any]:
        items = []
        for row in db.list_fetch_presets():
            name = str(row["name"])
            items.append(
                {
                    "name": name,
                    "payload": db.get_fetch_preset(name) or {},
                    "updated_at": row["updated_at"],
                }
            )
        return {"items": items}

    @app.put("/api/fetch-presets/{name}")
    def save_fetch_preset(name: str, payload: FetchPresetRequest, db=Depends(database)) -> dict[str, Any]:
        db.save_fetch_preset(name, payload.payload)
        return {"ok": True}

    @app.delete("/api/fetch-presets/{name}", status_code=204)
    def delete_fetch_preset(name: str, db=Depends(database)) -> None:
        db.delete_fetch_preset(name)

    @app.get("/api/scheduler")
    def scheduler_status(request: Request) -> dict[str, Any]:
        return request.app.state.scheduler.settings()

    @app.put("/api/scheduler")
    def scheduler_update(payload: SchedulerRequest, request: Request) -> dict[str, Any]:
        return request.app.state.scheduler.update(**payload.model_dump())

    @app.get("/api/posts")
    def posts(
        request: Request,
        status: str = "worklist",
        search: str = "",
        sort: str = "id_desc",
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=32, ge=8, le=200),
        db=Depends(database),
    ) -> dict[str, Any]:
        cache = None if request.app.state.fetch_controller.snapshot().get("running") else request.app.state.recommendation_cache
        return list_posts(
            db,
            status=status,
            search=search.strip(),
            sort=sort,
            offset=offset,
            limit=limit,
            recommendation_cache=cache,
        )

    @app.patch("/api/posts/status")
    def update_post_statuses(
        payload: BulkPostStatusRequest,
        request: Request,
        db=Depends(database),
    ) -> dict[str, Any]:
        if payload.status not in ALLOWED_STATUSES:
            raise HTTPException(status_code=422, detail="Invalid status")
        post_ids = list(dict.fromkeys(int(post_id) for post_id in payload.post_ids))
        old_statuses = _post_statuses_by_id(db, post_ids)
        missing_ids = [post_id for post_id in post_ids if post_id not in old_statuses]
        if missing_ids:
            preview = ", ".join(map(str, missing_ids[:20]))
            suffix = f" (+{len(missing_ids) - 20} more)" if len(missing_ids) > 20 else ""
            raise HTTPException(status_code=404, detail=f"Posts not found: {preview}{suffix}")

        db.set_post_statuses(post_ids, payload.status, request.app.state.config)
        request.app.state.recommendation_cache.apply_status_changes(
            {post_id: (old_statuses[post_id], payload.status) for post_id in post_ids}
        )
        return {"ok": True, "updated": len(post_ids), "status": payload.status, "post_ids": post_ids}

    @app.get("/api/posts/{post_id}")
    def post(
        post_id: int,
        request: Request,
        status: str = "worklist",
        search: str = "",
        sort: str = "id_desc",
        db=Depends(database),
    ) -> dict[str, Any]:
        cache = None if request.app.state.fetch_controller.snapshot().get("running") else request.app.state.recommendation_cache
        value = post_detail(
            db,
            post_id,
            status=status,
            search=search.strip(),
            sort=sort,
            recommendation_cache=cache,
        )
        if value is None:
            raise HTTPException(status_code=404, detail="Post not found")
        base_url = str(request.app.state.config.get("base_url") or "https://danbooru.donmai.us").rstrip("/")
        value["original_post_url"] = f"{base_url}/posts/{post_id}"
        return value

    @app.patch("/api/posts/{post_id}")
    def update_post(post_id: int, payload: PostActionRequest, request: Request, db=Depends(database)) -> dict[str, Any]:
        post = db.get_post_detail(post_id)
        if post is None:
            raise HTTPException(status_code=404, detail="Post not found")
        if payload.status is not None:
            if payload.status not in ALLOWED_STATUSES:
                raise HTTPException(status_code=422, detail="Invalid status")
            old_status = str(post["status"] or "new")
            db.set_post_status(post_id, payload.status, request.app.state.config)
            request.app.state.recommendation_cache.apply_status_change(post_id, old_status, payload.status)
        if payload.stars is not None:
            db.set_post_review(post_id, stars=payload.stars)
        if payload.category_id is not None:
            category = next(
                (row for row in db.list_categories_full() if int(row["id"]) == payload.category_id),
                None,
            )
            if category is None:
                raise HTTPException(status_code=404, detail="Category not found")
            db.assign_post_category(post_id, payload.category_id, source="manual-web")
            return {
                "ok": True,
                "category_id": int(category["id"]),
                "category": str(category["name"]),
                "category_source": "manual-web",
            }
        return {"ok": True}

    @app.post("/api/posts/{post_id}/save")
    def save_post(post_id: int, payload: PostSaveRequest, request: Request, db=Depends(database)) -> dict[str, Any]:
        post = db.get_post_detail(post_id)
        if post is None:
            raise HTTPException(status_code=404, detail="Post not found")
        old_status = str(post["status"] or "new")

        service = FinalSaveService(request.app.state.config, db)
        category = None
        if payload.category_id is not None:
            category_row = next(
                (row for row in db.list_categories_full() if int(row["id"]) == payload.category_id),
                None,
            )
            if category_row is None:
                raise HTTPException(status_code=404, detail="Category not found")
            category = service.category_by_name(str(category_row["name"]))

        try:
            result = service.save_post(
                post_id,
                category=category,
                overwrite_existing=payload.overwrite_existing,
            )
        except AlreadySavedError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Save failed: {exc}") from exc

        request.app.state.recommendation_cache.apply_status_change(post_id, old_status, "saved")
        return {
            "ok": True,
            "post_id": result.post_id,
            "category": result.category.name,
            "category_source": result.category_source,
            "final_path": str(result.final_path),
        }

    @app.put("/api/viewer/settings")
    def update_viewer_settings(
        payload: ViewerSettingsRequest,
        request: Request,
        db=Depends(database),
    ) -> dict[str, Any]:
        value = bool(payload.next_after_status_change)
        db.set_app_setting("web.viewer_next_after_status_change", json.dumps(value))
        web_config = request.app.state.config.setdefault("web", {})
        web_config["viewer_next_after_status_change"] = value
        return {"next_after_status_change": value}

    @app.put("/api/preview/settings")
    def update_preview_settings(
        payload: PreviewSettingsRequest,
        request: Request,
        db=Depends(database),
    ) -> dict[str, Any]:
        batch_size = int(payload.batch_size)
        thumbnail_size = int(payload.thumbnail_size)
        db.set_app_setting("web.preview_batch_size", json.dumps(batch_size))
        db.set_app_setting("web.preview_thumbnail_size", json.dumps(thumbnail_size))
        web_config = request.app.state.config.setdefault("web", {})
        web_config["preview_batch_size"] = batch_size
        web_config["preview_thumbnail_size"] = thumbnail_size
        return {"batch_size": batch_size, "thumbnail_size": thumbnail_size}

    @app.get("/api/media/{post_id}/{variant}")
    def media(post_id: int, variant: str, request: Request, db=Depends(database)):
        if variant not in {"thumbnail", "viewer"}:
            raise HTTPException(status_code=404, detail="Unknown media variant")
        post_data = media_post_data(db, post_id)
        if post_data is None:
            raise HTTPException(status_code=404, detail="Post not found")
        path = resolve_media_path(request.app.state.config, post_data, variant)
        if path is not None:
            return FileResponse(path, headers={"Cache-Control": "private, max-age=3600"})
        if variant == "thumbnail" and post_data.get("preview_url"):
            media_config = dict(request.app.state.config)
            media_config["thumbnail_download_source"] = "preview"
            api = DanbooruApi(media_config)
            cache = ThumbnailCache(media_config, api.session)
            cache_post = dict(post_data)
            cache_post["preview_file_url"] = post_data.get("preview_url")
            cached = cache.cache_thumbnail(cache_post)
            api.session.close()
            if cached:
                db.execute("UPDATE posts SET thumbnail_path = ? WHERE id = ?", (cached, post_id))
                db.commit()
                return FileResponse(cached, headers={"Cache-Control": "private, max-age=3600"})
        remote = post_data.get("preview_url") if variant == "thumbnail" else (
            post_data.get("large_file_url") or post_data.get("file_url") or post_data.get("preview_url")
        )
        if remote:
            api = DanbooruApi(request.app.state.config)
            response = api.session.get(str(remote), stream=True, timeout=api.timeout)
            if response.ok:
                def chunks():
                    try:
                        yield from response.iter_content(chunk_size=1024 * 128)
                    finally:
                        response.close()
                        api.session.close()

                return StreamingResponse(
                    chunks(),
                    media_type=response.headers.get("Content-Type"),
                    headers={"Cache-Control": "private, max-age=3600"},
                )
            response.close()
            api.session.close()

        if variant == "viewer":
            thumbnail_path = resolve_media_path(request.app.state.config, post_data, "thumbnail")
            if thumbnail_path is not None:
                return FileResponse(thumbnail_path, headers={"Cache-Control": "private, max-age=3600"})
        if remote:
            raise HTTPException(status_code=502, detail="Remote media could not be loaded")
        raise HTTPException(status_code=404, detail="No media available")

    @app.get("/api/tags")
    def tags(
        search: str = "",
        tag_type: str = "all",
        limit: int = Query(default=100, ge=1, le=1000),
        db=Depends(database),
    ) -> dict[str, Any]:
        rows = db.fetch_tag_overview(search_text=search or None, tag_type=tag_type, limit=limit, source="local")
        return {"items": [row_dict(row) for row in rows]}

    @app.patch("/api/tags/{tag}")
    def update_tag(tag: str, payload: TagUpdateRequest, request: Request, db=Depends(database)) -> dict[str, Any]:
        fields = payload.model_fields_set
        if "alias" in fields:
            db.set_tag_alias(tag, payload.alias or "")
        if "manual_score" in fields:
            db.set_tag_manual_score(tag, payload.manual_score)
        if payload.scoring_excluded is not None:
            db.set_tag_scoring_excluded(tag, payload.scoring_excluded)
        if payload.filename_excluded is not None:
            if payload.filename_excluded:
                db.add_filename_excluded_tag(tag, "web")
            else:
                db.remove_filename_excluded_tag(tag)
        if payload.fetch_excluded is not None:
            if payload.fetch_excluded:
                db.add_fetch_excluded_tag(tag, "web")
            else:
                db.remove_fetch_excluded_tag(tag)
        scoring_flags = {
            "ignore_category_influence": payload.ignore_category_influence,
            "ignore_recommendation_score": payload.ignore_recommendation_score,
            "ignore_llm_input": payload.ignore_llm_input,
        }
        if any(value is not None for value in scoring_flags.values()):
            db.set_tag_scoring_flags(tag, **scoring_flags)
        request.app.state.recommendation_cache.clear()
        metadata_by_tag = db.fetch_tag_display_metadata([tag])
        metadata = next(iter(metadata_by_tag.values()), {})
        return {"ok": True, "tag": tag.strip(), **metadata}

    @app.get("/api/categories")
    def categories(db=Depends(database)) -> dict[str, Any]:
        return {"items": [row_dict(row) for row in db.list_categories_full()]}

    @app.post("/api/categories", status_code=201)
    def create_category(payload: CategoryRequest, db=Depends(database)) -> dict[str, Any]:
        category_id = db.create_category(payload.name, payload.folder_name)
        return {"id": category_id}

    @app.put("/api/categories/{category_id}")
    def update_category(category_id: int, payload: CategoryRequest, db=Depends(database)) -> dict[str, Any]:
        db.update_category(
            category_id,
            payload.name,
            payload.folder_name or payload.name,
            payload.output_path,
            payload.hotkey,
            payload.sort_order or 1,
        )
        return {"ok": True}

    @app.delete("/api/categories/{category_id}", status_code=204)
    def delete_category(category_id: int, db=Depends(database)) -> None:
        db.delete_category(category_id)

    @app.get("/api/settings")
    def settings(request: Request) -> dict[str, Any]:
        current = request.app.state.config
        return {
            "base_url": current.get("base_url"),
            "username": current.get("username"),
            "api_key_configured": bool(current.get("api_key")),
            "request_timeout_seconds": current.get("request_timeout_seconds"),
            "request_min_interval_seconds": current.get("request_min_interval_seconds"),
            "database_file": current.get("database_file"),
        }

    @app.patch("/api/settings")
    def update_settings(payload: SettingsRequest, request: Request, db=Depends(database)) -> dict[str, Any]:
        values = payload.model_dump(exclude_unset=True)
        for key, value in values.items():
            db.set_app_setting(key, json.dumps(value))
            request.app.state.config[key] = value
        return {"ok": True}

    @app.get("/api/maintenance")
    def maintenance(db=Depends(database)) -> dict[str, Any]:
        return db.analyze_database_size()

    @app.post("/api/maintenance/checkpoint")
    def checkpoint(db=Depends(database)) -> dict[str, Any]:
        return {"result": db.checkpoint_wal_truncate()}

    @app.get("/viewer/{post_id}", include_in_schema=False)
    def viewer_page(post_id: int) -> FileResponse:
        _ = post_id
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="web")
    return app
