from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_compose_keeps_manager_data_inside_archive_library() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "DANBOORU_DATA_DIR: /archive/.danbooru_manager" in compose
    assert "DANBOORU_ARCHIVE_ROOT: /archive" in compose
    assert "DANBOORU_CACHE_ROOT: /cache" in compose
    assert "DANBOORU_IMPORT_ROOT: /import" in compose
    assert "DANBOORU_ARCHIVE_YEAR" not in compose
    assert '${DANBOORU_ARCHIVE_DIR:?' in compose
    assert '${DANBOORU_CACHE_DIR:?' in compose
    assert '${DANBOORU_IMPORT_DIR:?' in compose
    assert ":/import:ro" in compose
    assert ":/archive" in compose
    assert "./danbooru_manager_data:/data" not in compose


def test_example_environment_requires_only_library_root() -> None:
    example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "DANBOORU_ARCHIVE_DIR=/path/to/images" in example
    assert "DANBOORU_CACHE_DIR=/srv/danbooru-manager-cache" in example
    assert "DANBOORU_IMPORT_DIR=/path/to/existing/images" in example
    assert "DANBOORU_ARCHIVE_YEAR" not in example


def test_dockerfile_has_no_separate_data_volume() -> None:
    dockerfile = (ROOT / "Dockerfile.web").read_text(encoding="utf-8")

    assert "DANBOORU_DATA_DIR=/archive/.danbooru_manager" in dockerfile
    assert "DANBOORU_CACHE_ROOT=/cache" in dockerfile
    assert "DANBOORU_IMPORT_ROOT=/import" in dockerfile
    assert 'VOLUME ["/archive", "/cache", "/import"]' in dockerfile
    assert 'VOLUME ["/data", "/archive"]' not in dockerfile


def test_web_importer_uses_headless_image_reader_dependency() -> None:
    requirements = (ROOT / "requirements-web.txt").read_text(encoding="utf-8")

    assert "Pillow" in requirements
