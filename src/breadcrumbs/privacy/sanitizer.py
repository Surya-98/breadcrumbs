from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Mapping
import re


class PrivacyBoundaryError(ValueError):
    """Raised when a cloud payload contains local-only screen data."""


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}(?!\d)")
CREDIT_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
TOKEN_RE = re.compile(r"\b(?:sk|pk|ghp|github_pat|AIza)[A-Za-z0-9_\-]{12,}\b")
WHITESPACE_RE = re.compile(r"\s+")

RAW_SCREEN_KEYS = {
    "frame",
    "frames",
    "frame_path",
    "screen_frame",
    "screen_frames",
    "screenshot",
    "screenshot_path",
    "image",
    "image_bytes",
    "raw_ocr",
    "raw_ocr_text",
    "ocr_text",
}

LOCAL_ONLY_KEYS = RAW_SCREEN_KEYS | {
    "before_text",
    "after_text",
    "text",
    "body",
    "full_text",
    "raw_text",
}


def _to_mapping(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError(f"Expected dataclass or mapping, got {type(value)!r}")


def compact_text(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text).strip()


def redact_text(text: str | None) -> str:
    if not text:
        return ""
    redacted = EMAIL_RE.sub("[email]", text)
    redacted = PHONE_RE.sub("[phone]", redacted)
    redacted = CREDIT_CARD_RE.sub("[card]", redacted)
    redacted = TOKEN_RE.sub("[secret]", redacted)
    return compact_text(redacted)


def redacted_snippet(text: str | None, max_chars: int = 500) -> str:
    value = redact_text(text)
    if len(value) <= max_chars:
        return value
    return f"{value[: max_chars - 1].rstrip()}..."


def assert_no_raw_screen_fields(payload: Any, path: str = "$") -> None:
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            key_text = str(key)
            if key_text in RAW_SCREEN_KEYS:
                raise PrivacyBoundaryError(f"Cloud payload includes local-only screen field at {path}.{key_text}")
            assert_no_raw_screen_fields(value, f"{path}.{key_text}")
    elif isinstance(payload, list | tuple):
        for index, value in enumerate(payload):
            assert_no_raw_screen_fields(value, f"{path}[{index}]")


def _safe_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        if key in LOCAL_ONLY_KEYS:
            continue
        if isinstance(value, str):
            safe[key] = redacted_snippet(value, 240)
        elif isinstance(value, int | float | bool) or value is None:
            safe[key] = value
        elif isinstance(value, list):
            safe[key] = [redacted_snippet(str(item), 80) for item in value[:10]]
        else:
            safe[key] = redacted_snippet(str(value), 240)
    return safe


def sanitize_connector_event(event: Any) -> dict[str, Any]:
    data = _to_mapping(event)
    payload = {
        "kind": "connector_event",
        "source_event_id": data.get("id"),
        "session_id": data.get("session_id"),
        "app": data.get("app"),
        "event_type": data.get("event_type"),
        "source": data.get("source"),
        "document_id": data.get("document_id"),
        "title": redacted_snippet(data.get("title"), 180),
        "snippet": redacted_snippet(data.get("text"), 500),
        "metadata": _safe_metadata(data.get("metadata")),
        "created_at": data.get("created_at"),
    }
    assert_no_raw_screen_fields(payload)
    return payload


def sanitize_screen_observation(observation: Any) -> dict[str, Any]:
    data = _to_mapping(observation)
    payload = {
        "kind": "screen_summary",
        "source_event_id": data.get("id"),
        "session_id": data.get("session_id"),
        "app_name": redacted_snippet(data.get("app_name"), 120),
        "window_title": redacted_snippet(data.get("window_title"), 180),
        "summary": redacted_snippet(data.get("summary"), 500),
        "created_at": data.get("created_at"),
    }
    assert_no_raw_screen_fields(payload)
    return payload


def sanitize_preference(preference: Any) -> dict[str, Any]:
    data = _to_mapping(preference)
    payload = {
        "kind": "learned_preference",
        "preference_id": data.get("id"),
        "session_id": data.get("session_id"),
        "summary": redacted_snippet(data.get("summary"), 500),
        "applies_when": redacted_snippet(data.get("applies_when"), 320),
        "suggested_rule": redacted_snippet(data.get("suggested_rule"), 500),
        "confidence": data.get("confidence"),
        "evidence_event_ids": list(data.get("evidence_event_ids") or []),
        "tags": list(data.get("tags") or []),
        "created_at": data.get("created_at"),
    }
    assert_no_raw_screen_fields(payload)
    return payload


def sanitize_suggestion(suggestion: Any) -> dict[str, Any]:
    data = _to_mapping(suggestion)
    payload = {
        "kind": "suggestion",
        "suggestion_id": data.get("id"),
        "session_id": data.get("session_id"),
        "preference_id": data.get("preference_id"),
        "app": data.get("app"),
        "target_id": data.get("target_id"),
        "reason": redacted_snippet(data.get("reason"), 320),
        "confidence": data.get("confidence"),
        "status": data.get("status"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
    }
    assert_no_raw_screen_fields(payload)
    return payload
