from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any, Mapping

DEFAULT_LANGUAGE = "en"
FALLBACK_LANGUAGE = "en"
SUPPORTED_LANGUAGES: dict[str, str] = {
    "en": "English",
    "de": "Deutsch",
}


@lru_cache(maxsize=None)
def _load_language(language: str) -> dict[str, Any]:
    code = normalize_language(language)
    try:
        text = resources.files("app.i18n.locales").joinpath(f"{code}.json").read_text(encoding="utf-8")
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    if code != FALLBACK_LANGUAGE:
        return _load_language(FALLBACK_LANGUAGE)
    return {}


def normalize_language(language: Any) -> str:
    code = str(language or DEFAULT_LANGUAGE).strip().lower().replace("_", "-")
    if not code:
        return DEFAULT_LANGUAGE
    code = code.split("-", 1)[0]
    if code not in SUPPORTED_LANGUAGES:
        return DEFAULT_LANGUAGE
    return code


def language_from_config(config: Mapping[str, Any] | None) -> str:
    if not isinstance(config, Mapping):
        return DEFAULT_LANGUAGE
    ui_config = config.get("ui")
    if isinstance(ui_config, Mapping):
        return normalize_language(ui_config.get("language"))
    return normalize_language(config.get("language"))


def available_languages() -> list[tuple[str, str]]:
    return list(SUPPORTED_LANGUAGES.items())


def tr(key: str, default: str | None = None, *, language: str | None = None, config: Mapping[str, Any] | None = None, **kwargs: Any) -> str:
    """Translate a UI string by key.

    Missing keys intentionally fall back to the provided default or the key. That
    makes incremental migration possible instead of forcing one giant brittle
    string transplant, because apparently UIs enjoy becoming archeological digs.
    """
    lang = normalize_language(language if language is not None else language_from_config(config))
    catalog = _load_language(lang)
    fallback = _load_language(FALLBACK_LANGUAGE) if lang != FALLBACK_LANGUAGE else catalog

    value = catalog.get(key, fallback.get(key, default if default is not None else key))
    if not isinstance(value, str):
        value = default if default is not None else key

    if kwargs:
        try:
            return value.format(**kwargs)
        except Exception:
            return value
    return value
