from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from app.core.config import load_config
from app.core.database import Database
from app.core.paths import ensure_runtime_dirs
from app.services.history_import import import_downloaded_ids_history
from app.services.post_import_service import PostImportService


def setup_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Danbooru Manager - SQLite configuration, API import, thumbnail cache and preview GUI"
    )
    parser.add_argument(
        "--init-db",
        action="store_true",
        help="Datenbank initialisieren",
    )
    parser.add_argument(
        "--import-history",
        action="store_true",
        help="downloaded_ids.txt in die SQLite-Datenbank übernehmen",
    )
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="Danbooru-Posts laden, speichern und Thumbnails cachen",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Preview-GUI starten",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Debug-Logging aktivieren",
    )
    parser.add_argument(
        "--debug-startup",
        action="store_true",
        help="Startzeit-Markierungen ausgeben und Lazy-Tab-Erzeugung protokollieren",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    setup_logging(args.debug)

    config = load_config()
    config["debug_startup"] = bool(args.debug_startup)
    ensure_runtime_dirs(config)

    db = Database(Path(config["database_file"]))
    db.connect()
    db.initialize_schema()

    # SQLite/app_settings is the leading GUI configuration once the database
    # exists. External config files and .env files are intentionally not read.
    db.apply_app_settings_to_config(config)
    ensure_runtime_dirs(config)

    if args.init_db:
        logging.info("Database initialized: %s", config["database_file"])

    if args.import_history:
        history_file = Path(config.get("history_file", "downloaded_ids.txt"))
        imported = import_downloaded_ids_history(db, history_file)
        logging.info("History import finished: %s entries", imported)

    if args.fetch:
        service = PostImportService(config, db)
        result = service.fetch_and_store()
        logging.info(
            "Fetch finished: queries=%s, seen=%s, inserted=%s, updated=%s, thumbnails=%s",
            result.queries,
            result.seen_posts,
            result.inserted_posts,
            result.updated_posts,
            result.cached_thumbnails,
        )

    if args.gui:
        # Import erst hier, damit CLI-Operationen nicht von Qt abhängen müssen.
        from app.gui.main_window import run_gui

        exit_code = run_gui(config, db)
        db.close()
        return exit_code

    if not args.init_db and not args.import_history and not args.fetch and not args.gui:
        logging.info("Nothing to do. Use --init-db, --import-history, --fetch or --gui.")

    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
