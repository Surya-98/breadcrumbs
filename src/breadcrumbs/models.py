from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class UploadMode(StrEnum):
    LOCAL_ONLY = "local_only"
    SANITIZED_CONTEXT = "sanitized_context"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    STOPPED = "stopped"


class SuggestionStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"


@dataclass(frozen=True)
class Session:
    id: str
    goal: str
    enabled_apps: list[str]
    upload_mode: str
    status: str = SessionStatus.ACTIVE.value
    started_at: str = field(default_factory=utc_now)
    stopped_at: str | None = None


@dataclass(frozen=True)
class ConnectorEvent:
    id: str
    session_id: str
    app: str
    event_type: str
    source: str
    document_id: str | None
    title: str | None
    text: str | None
    metadata: dict
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class ScreenObservation:
    id: str
    session_id: str
    app_name: str | None
    window_title: str | None
    ocr_text: str | None
    summary: str
    frame_path: str | None
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class LearnedPreference:
    id: str
    session_id: str
    summary: str
    applies_when: str
    suggested_rule: str
    confidence: float
    evidence_event_ids: list[str]
    tags: list[str]
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class Suggestion:
    id: str
    session_id: str
    preference_id: str
    app: str
    target_id: str
    before_text: str
    after_text: str
    reason: str
    confidence: float
    status: str = SuggestionStatus.PENDING.value
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class ConnectorAction:
    id: str
    suggestion_id: str
    app: str
    target_id: str
    action_type: str
    payload: dict
    status: str
    created_at: str = field(default_factory=utc_now)
    completed_at: str | None = None
