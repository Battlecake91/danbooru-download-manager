from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_compose_keeps_manager_data_inside_archive_library() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "DANBOORU_DATA_DIR: /archive/.danbooru_manager" in compose
    assert 'DANBOORU_OUTPUT_DIR: "/archive/${DANBOORU_ARCHIVE_YEAR:?' in compose
    assert '${DANBOORU_ARCHIVE_DIR:?' in compose
    assert ":/archive" in compose
    assert "./danbooru_manager_data:/data" not in compose


def test_example_environment_defines_library_and_year() -> None:
    example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "DANBOORU_ARCHIVE_DIR=/path/to/images" in example
    assert "DANBOORU_ARCHIVE_YEAR=2026" in example
