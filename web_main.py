from __future__ import annotations

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "app.web.app:create_app",
        factory=True,
        host=os.environ.get("DANBOORU_WEB_HOST", "127.0.0.1"),
        port=int(os.environ.get("DANBOORU_WEB_PORT", "8765")),
        workers=1,
    )


if __name__ == "__main__":
    main()
