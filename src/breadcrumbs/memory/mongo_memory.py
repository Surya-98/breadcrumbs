from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from breadcrumbs.config import Settings
from breadcrumbs.memory.embeddings import hash_embedding
from breadcrumbs.privacy import assert_no_raw_screen_fields


class MemoryClient(Protocol):
    def upload_context_event(self, payload: dict[str, Any]) -> None:
        ...

    def upload_preference(self, payload: dict[str, Any]) -> None:
        ...

    def upload_suggestion(self, payload: dict[str, Any]) -> None:
        ...

    def search_preferences(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        ...


@dataclass
class NoopMemoryClient:
    reason: str = "cloud upload disabled"

    def upload_context_event(self, payload: dict[str, Any]) -> None:
        assert_no_raw_screen_fields(payload)

    def upload_preference(self, payload: dict[str, Any]) -> None:
        assert_no_raw_screen_fields(payload)

    def upload_suggestion(self, payload: dict[str, Any]) -> None:
        assert_no_raw_screen_fields(payload)

    def search_preferences(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        return []


class MongoMemoryClient:
    """MongoDB Atlas memory writer for sanitized context only."""

    def __init__(self, uri: str, database: str) -> None:
        try:
            from pymongo import MongoClient
        except ImportError as exc:
            raise RuntimeError("pymongo is required for MongoDB memory uploads") from exc

        self.client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        self.db = self.client[database]

    def upload_context_event(self, payload: dict[str, Any]) -> None:
        assert_no_raw_screen_fields(payload)
        result = self.db.context_events.insert_one(payload)
        self._insert_vector("context_event", str(result.inserted_id), payload)

    def upload_preference(self, payload: dict[str, Any]) -> None:
        assert_no_raw_screen_fields(payload)
        result = self.db.preferences.insert_one(payload)
        self._insert_vector("preference", str(result.inserted_id), payload)

    def upload_suggestion(self, payload: dict[str, Any]) -> None:
        assert_no_raw_screen_fields(payload)
        self.db.suggestions.insert_one(payload)

    def search_preferences(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        vector = hash_embedding(query)
        pipeline = [
            {
                "$vectorSearch": {
                    "index": "memory_vectors",
                    "path": "embedding",
                    "queryVector": vector,
                    "numCandidates": max(limit * 10, 20),
                    "limit": limit,
                }
            },
            {"$match": {"kind": "preference"}},
            {"$project": {"embedding": 0}},
        ]
        return list(self.db.memory_vectors.aggregate(pipeline))

    def _insert_vector(self, kind: str, source_id: str, payload: dict[str, Any]) -> None:
        summary = " ".join(
            str(payload.get(key, ""))
            for key in ("summary", "snippet", "suggested_rule", "applies_when", "app", "event_type")
        )
        self.db.memory_vectors.insert_one(
            {
                "kind": kind,
                "source_id": source_id,
                "session_id": payload.get("session_id"),
                "app": payload.get("app") or payload.get("app_name"),
                "summary": summary.strip(),
                "embedding": hash_embedding(summary),
                "created_at": payload.get("created_at"),
            }
        )


def build_memory_client(settings: Settings) -> MemoryClient:
    if not settings.cloud_upload_enabled:
        return NoopMemoryClient()
    if not settings.mongodb_uri:
        return NoopMemoryClient("MONGODB_URI is not configured")
    return MongoMemoryClient(settings.mongodb_uri, settings.mongodb_database)
