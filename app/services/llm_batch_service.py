from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

import requests

from app.core.database import Database
from app.services.llm_payload_service import LLMPayloadService


@dataclass
class LLMBatchRunResult:
    input_posts: int = 0
    candidate_posts: int = 0
    skipped_posts: int = 0
    batches_total: int = 0
    payloads_prepared: int = 0
    requests_sent: int = 0
    decisions_received: int = 0
    decisions_saved: int = 0
    skipped_reason: str | None = None
    batch_summaries: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class LLMBatchPreselectionService:
    """Run LLM preselection for many posts in configurable batches."""

    def __init__(self, config: dict[str, Any], db: Database, log_callback: Any | None = None) -> None:
        self.config = config
        self.db = db
        self.log_callback = log_callback
        self.payload_service = LLMPayloadService(config, db)

    def log(self, message: str) -> None:
        if self.log_callback is not None:
            self.log_callback(message)

    def run_for_post_ids(self, post_ids: Iterable[int]) -> LLMBatchRunResult:
        llm_config = self.config.get("llm", {}) or {}
        result = LLMBatchRunResult()

        input_ids = self._clean_post_ids(post_ids)
        result.input_posts = len(input_ids)

        if not bool(llm_config.get("run_after_fetch", False)):
            result.skipped_reason = "LLM nach Fetch ist deaktiviert."
            self._store_last_fetch_summary(result, input_ids=input_ids, candidates=[], payloads=[])
            return result

        statuses = llm_config.get("after_fetch_statuses", ["new", "potential"])
        if not isinstance(statuses, list):
            statuses = ["new", "potential"]
        status_list = [str(status) for status in statuses if str(status).strip()]
        skip_scored = bool(llm_config.get("skip_already_scored", True))

        self.log(f"LLM-Batch: Eingangsposts: {len(input_ids)}")
        self.log(
            "LLM-Batch: Statusfilter: "
            + (", ".join(status_list) if status_list else "alle")
            + f" | bereits bewertete ueberspringen: {'ja' if skip_scored else 'nein'}"
        )

        candidates = self.db.filter_post_ids_for_llm(
            input_ids,
            statuses=status_list,
            skip_already_scored=skip_scored,
        )
        result.candidate_posts = len(candidates)
        result.skipped_posts = max(0, len(input_ids) - len(candidates))
        self.log(f"LLM-Batch: Kandidaten nach Filter: {len(candidates)} | uebersprungen: {result.skipped_posts}")

        if not candidates:
            result.skipped_reason = "Keine passenden neuen Posts fuer LLM-Batch vorhanden."
            self._store_last_fetch_summary(result, input_ids=input_ids, candidates=candidates, payloads=[])
            return result

        payloads = self.payload_service.build_payload_batches(candidates)
        result.batches_total = len(payloads)
        result.payloads_prepared = len(payloads)
        result.batch_summaries = self._summarize_payloads(payloads)

        self._store_last_fetch_summary(result, input_ids=input_ids, candidates=candidates, payloads=payloads)
        self.log(f"LLM-Batch: {len(candidates)} Posts in {len(payloads)} Payload(s) vorbereitet.")
        for batch in result.batch_summaries:
            ids = batch.get("post_ids", [])
            id_text = ", ".join(str(post_id) for post_id in ids[:20])
            if len(ids) > 20:
                id_text += ", ..."
            self.log(f"LLM-Batch {batch.get('index')}/{batch.get('total')}: Posts {batch.get('post_count')}: {id_text}")

        if not bool(llm_config.get("enabled", False)):
            result.skipped_reason = "LLM deaktiviert: Payloads wurden nur vorbereitet."
            self._store_last_fetch_summary(result, input_ids=input_ids, candidates=candidates, payloads=payloads)
            return result

        backend = str(llm_config.get("backend", "none") or "none").lower()
        if backend == "none":
            result.skipped_reason = "LLM-Backend ist 'none': Payloads wurden nur vorbereitet."
            self._store_last_fetch_summary(result, input_ids=input_ids, candidates=candidates, payloads=payloads)
            return result

        model = str(llm_config.get("model", "") or "").strip()
        for index, payload in enumerate(payloads, start=1):
            self.log(f"LLM-Batch {index}/{len(payloads)} wird gesendet...")
            try:
                decisions = self._send_payload(payload, backend=backend)
                decisions = self._resolve_decision_categories(decisions)
                result.requests_sent += 1
                result.decisions_received += len(decisions)
                saved = self.db.store_llm_decisions(decisions, model=model or backend)
                result.decisions_saved += saved
                self.log(f"LLM-Batch {index}/{len(payloads)}: {len(decisions)} Entscheidungen empfangen, {saved} gespeichert.")
            except Exception as exc:
                text = f"LLM-Batch {index}/{len(payloads)} fehlgeschlagen: {exc}"
                result.errors.append(text)
                self.log(text)
        return result

    @staticmethod
    def _clean_post_ids(post_ids: Iterable[int]) -> list[int]:
        clean: list[int] = []
        seen: set[int] = set()
        for raw_id in post_ids:
            try:
                post_id = int(raw_id)
            except Exception:
                continue
            if post_id and post_id not in seen:
                clean.append(post_id)
                seen.add(post_id)
        return clean

    @staticmethod
    def _payload_post_ids(payload: dict[str, Any]) -> list[int]:
        ids: list[int] = []
        posts = payload.get("posts", [])
        if not isinstance(posts, list):
            return ids
        for post in posts:
            if not isinstance(post, dict):
                continue
            try:
                ids.append(int(post.get("post_id")))
            except Exception:
                continue
        return ids

    def _summarize_payloads(self, payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        total = len(payloads)
        summaries: list[dict[str, Any]] = []
        for index, payload in enumerate(payloads, start=1):
            post_ids = self._payload_post_ids(payload)
            batch_info = payload.get("batch", {}) if isinstance(payload.get("batch"), dict) else {}
            summaries.append(
                {
                    "index": int(batch_info.get("index", index) or index),
                    "total": int(batch_info.get("total", total) or total),
                    "post_count": len(post_ids),
                    "post_ids": post_ids,
                }
            )
        return summaries

    def _store_last_fetch_summary(
        self,
        result: LLMBatchRunResult,
        *,
        input_ids: list[int],
        candidates: list[int],
        payloads: list[dict[str, Any]],
    ) -> None:
        summary = {
            "input_posts": len(input_ids),
            "candidate_posts": len(candidates),
            "skipped_posts": max(0, len(input_ids) - len(candidates)),
            "batches_total": len(payloads),
            "payloads_prepared": len(payloads),
            "skipped_reason": result.skipped_reason,
            "batch_summaries": self._summarize_payloads(payloads),
        }
        # Keep payloads and summary in sync. Otherwise the viewer can show stale payloads
        # or nothing useful, because apparently one more hidden state was exactly what this UI needed.
        self.db.set_app_setting("llm.last_fetch_payloads", json.dumps(payloads, ensure_ascii=False, indent=2))
        self.db.set_app_setting("llm.last_fetch_payload_summary", json.dumps(summary, ensure_ascii=False, indent=2))


    def _resolve_decision_categories(self, decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        resolved: list[dict[str, Any]] = []
        for item in decisions:
            clean = dict(item)
            category = clean.get("category")
            if category not in (None, ""):
                mapped = self.db.llm_category_name_for_export(str(category))
                clean["category"] = mapped
            resolved.append(clean)
        return resolved

    def _send_payload(self, payload: dict[str, Any], *, backend: str) -> list[dict[str, Any]]:
        llm_config = self.config.get("llm", {}) or {}
        endpoint = str(llm_config.get("endpoint_url", "") or "").strip()
        if not endpoint:
            raise RuntimeError("LLM endpoint_url fehlt.")

        timeout = int(llm_config.get("request_timeout_seconds", 60) or 60)
        model = str(llm_config.get("model", "") or "").strip()
        api_key = str(llm_config.get("api_key", "") or "").strip()
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        elif backend == "openai_compatible":
            raise RuntimeError(
                "OpenAI-kompatibles Backend braucht einen API-Key. "
                "Trage ihn in der Konfiguration bei LLM/API-Key ein. Environment-Fallback wurde entfernt."
            )

        if backend == "openai_compatible":
            url = endpoint.rstrip("/")
            if not url.endswith("/chat/completions"):
                url += "/chat/completions"
            body: dict[str, Any] = {
                "model": model,
                "messages": [
                    {"role": "system", "content": payload.get("instructions", "")},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
            }
            response = requests.post(url, headers=headers, json=body, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content")
            if content is None:
                raise RuntimeError("OpenAI-kompatible Antwort enthaelt keinen message.content.")
            parsed = self._parse_jsonish_content(str(content))
            return self._extract_decisions(parsed)

        if backend == "local":
            body = {"model": model, "payload": payload}
            response = requests.post(endpoint, headers=headers, json=body, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            if "posts" in data:
                return self._extract_decisions(data)
            if "content" in data:
                return self._extract_decisions(self._parse_jsonish_content(str(data["content"])))
            if "response" in data:
                return self._extract_decisions(self._parse_jsonish_content(str(data["response"])))
            return self._extract_decisions(data)

        raise RuntimeError(f"Unbekanntes LLM-Backend: {backend}")

    @staticmethod
    def _parse_jsonish_content(content: str) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start < 0 or end <= start:
                raise
            data = json.loads(text[start:end + 1])
        if not isinstance(data, dict):
            raise RuntimeError("LLM-Antwort ist kein JSON-Objekt.")
        return data

    @staticmethod
    def _extract_decisions(data: dict[str, Any]) -> list[dict[str, Any]]:
        posts = data.get("posts")
        if not isinstance(posts, list):
            raise RuntimeError("LLM-Antwort enthaelt keine posts-Liste.")
        result: list[dict[str, Any]] = []
        allowed_decisions = {"reject", "maybe", "keep", "save_candidate"}
        for item in posts:
            if not isinstance(item, dict):
                continue
            try:
                post_id = int(item.get("post_id"))
            except Exception:
                continue
            decision = str(item.get("decision") or "maybe").strip()
            if decision not in allowed_decisions:
                decision = "maybe"
            result.append(
                {
                    "post_id": post_id,
                    "score": item.get("score"),
                    "decision": decision,
                    "category": item.get("category"),
                    "reason": item.get("reason"),
                }
            )
        return result
