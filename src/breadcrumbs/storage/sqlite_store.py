from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any
import json
import sqlite3

from breadcrumbs.models import (
    ConnectorAction,
    ConnectorEvent,
    LearnedPreference,
    ScreenObservation,
    Session,
    SessionStatus,
    Suggestion,
    SuggestionStatus,
    new_id,
    utc_now,
)


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


class SQLiteStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    enabled_apps TEXT NOT NULL,
                    upload_mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    stopped_at TEXT
                );

                CREATE TABLE IF NOT EXISTS screen_frames (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    frame_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );

                CREATE TABLE IF NOT EXISTS ocr_observations (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    app_name TEXT,
                    window_title TEXT,
                    ocr_text TEXT,
                    summary TEXT NOT NULL,
                    frame_path TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );

                CREATE TABLE IF NOT EXISTS connector_events (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    app TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    document_id TEXT,
                    title TEXT,
                    text TEXT,
                    metadata TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );

                CREATE TABLE IF NOT EXISTS local_documents (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    app TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    title TEXT,
                    text TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(session_id, app, target_id)
                );

                CREATE TABLE IF NOT EXISTS learned_preferences (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    applies_when TEXT NOT NULL,
                    suggested_rule TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    evidence_event_ids TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                );

                CREATE TABLE IF NOT EXISTS suggestions (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    preference_id TEXT NOT NULL,
                    app TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    before_text TEXT NOT NULL,
                    after_text TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES sessions(id),
                    FOREIGN KEY(preference_id) REFERENCES learned_preferences(id)
                );

                CREATE TABLE IF NOT EXISTS connector_actions (
                    id TEXT PRIMARY KEY,
                    suggestion_id TEXT NOT NULL,
                    app TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    FOREIGN KEY(suggestion_id) REFERENCES suggestions(id)
                );

                CREATE TABLE IF NOT EXISTS audit_log (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def create_session(self, goal: str, enabled_apps: list[str], upload_mode: str) -> Session:
        session = Session(
            id=new_id("ses"),
            goal=goal,
            enabled_apps=enabled_apps,
            upload_mode=upload_mode,
        )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (id, goal, enabled_apps, upload_mode, status, started_at, stopped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.id,
                    session.goal,
                    _json(session.enabled_apps),
                    session.upload_mode,
                    session.status,
                    session.started_at,
                    session.stopped_at,
                ),
            )
        self.record_audit(session.id, "session_started", asdict(session))
        return session

    def stop_session(self, session_id: str) -> Session | None:
        stopped_at = utc_now()
        with self.connect() as conn:
            conn.execute(
                "UPDATE sessions SET status = ?, stopped_at = ? WHERE id = ?",
                (SessionStatus.STOPPED.value, stopped_at, session_id),
            )
        self.record_audit(session_id, "session_stopped", {"stopped_at": stopped_at})
        return self.get_session(session_id)

    def get_session(self, session_id: str) -> Session | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return self._session_from_row(row) if row else None

    def add_connector_event(
        self,
        session_id: str,
        app: str,
        event_type: str,
        source: str,
        document_id: str | None = None,
        title: str | None = None,
        text: str | None = None,
        metadata: dict[str, Any] | None = None,
        created_at: str | None = None,
    ) -> ConnectorEvent:
        event = ConnectorEvent(
            id=new_id("evt"),
            session_id=session_id,
            app=app,
            event_type=event_type,
            source=source,
            document_id=document_id,
            title=title,
            text=text,
            metadata=metadata or {},
            created_at=created_at or utc_now(),
        )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO connector_events
                (id, session_id, app, event_type, source, document_id, title, text, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.session_id,
                    event.app,
                    event.event_type,
                    event.source,
                    event.document_id,
                    event.title,
                    event.text,
                    _json(event.metadata),
                    event.created_at,
                ),
            )
            if document_id and text is not None:
                conn.execute(
                    """
                    INSERT INTO local_documents (id, session_id, app, target_id, title, text, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(session_id, app, target_id)
                    DO UPDATE SET title = excluded.title, text = excluded.text, updated_at = excluded.updated_at
                    """,
                    (new_id("doc"), session_id, app, document_id, title, text, event.created_at),
                )
        return event

    def add_screen_observation(
        self,
        session_id: str,
        app_name: str | None,
        window_title: str | None,
        ocr_text: str | None,
        summary: str,
        frame_path: str | None,
    ) -> ScreenObservation:
        observation = ScreenObservation(
            id=new_id("ocr"),
            session_id=session_id,
            app_name=app_name,
            window_title=window_title,
            ocr_text=ocr_text,
            summary=summary,
            frame_path=frame_path,
        )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO ocr_observations
                (id, session_id, app_name, window_title, ocr_text, summary, frame_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    observation.id,
                    observation.session_id,
                    observation.app_name,
                    observation.window_title,
                    observation.ocr_text,
                    observation.summary,
                    observation.frame_path,
                    observation.created_at,
                ),
            )
            if frame_path:
                conn.execute(
                    "INSERT INTO screen_frames (id, session_id, frame_path, created_at) VALUES (?, ?, ?, ?)",
                    (new_id("frame"), session_id, frame_path, observation.created_at),
                )
        return observation

    def add_preference(self, preference: LearnedPreference) -> LearnedPreference:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO learned_preferences
                (id, session_id, summary, applies_when, suggested_rule, confidence, evidence_event_ids, tags, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    preference.id,
                    preference.session_id,
                    preference.summary,
                    preference.applies_when,
                    preference.suggested_rule,
                    preference.confidence,
                    _json(preference.evidence_event_ids),
                    _json(preference.tags),
                    preference.created_at,
                ),
            )
        self.record_audit(preference.session_id, "preference_learned", asdict(preference))
        return preference

    def add_suggestions(self, suggestions: list[Suggestion]) -> list[Suggestion]:
        with self.connect() as conn:
            conn.executemany(
                """
                INSERT INTO suggestions
                (id, session_id, preference_id, app, target_id, before_text, after_text, reason, confidence, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        suggestion.id,
                        suggestion.session_id,
                        suggestion.preference_id,
                        suggestion.app,
                        suggestion.target_id,
                        suggestion.before_text,
                        suggestion.after_text,
                        suggestion.reason,
                        suggestion.confidence,
                        suggestion.status,
                        suggestion.created_at,
                        suggestion.updated_at,
                    )
                    for suggestion in suggestions
                ],
            )
        for suggestion in suggestions:
            self.record_audit(suggestion.session_id, "suggestion_created", asdict(suggestion))
        return suggestions

    def list_suggestions(
        self,
        session_id: str | None = None,
        status: str | None = SuggestionStatus.PENDING.value,
    ) -> list[Suggestion]:
        clauses: list[str] = []
        values: list[Any] = []
        if session_id:
            clauses.append("session_id = ?")
            values.append(session_id)
        if status:
            clauses.append("status = ?")
            values.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as conn:
            rows = conn.execute(f"SELECT * FROM suggestions {where} ORDER BY created_at DESC", values).fetchall()
        return [self._suggestion_from_row(row) for row in rows]

    def get_suggestion(self, suggestion_id: str) -> Suggestion | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM suggestions WHERE id = ?", (suggestion_id,)).fetchone()
        return self._suggestion_from_row(row) if row else None

    def update_suggestion_status(self, suggestion_id: str, status: str) -> Suggestion | None:
        updated_at = utc_now()
        with self.connect() as conn:
            conn.execute(
                "UPDATE suggestions SET status = ?, updated_at = ? WHERE id = ?",
                (status, updated_at, suggestion_id),
            )
        suggestion = self.get_suggestion(suggestion_id)
        if suggestion:
            self.record_audit(suggestion.session_id, f"suggestion_{status}", {"suggestion_id": suggestion_id})
        return suggestion

    def enqueue_action_for_suggestion(self, suggestion: Suggestion) -> ConnectorAction:
        action = ConnectorAction(
            id=new_id("act"),
            suggestion_id=suggestion.id,
            app=suggestion.app,
            target_id=suggestion.target_id,
            action_type="replace_text",
            payload={"after_text": suggestion.after_text},
            status="pending",
        )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO connector_actions
                (id, suggestion_id, app, target_id, action_type, payload, status, created_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    action.id,
                    action.suggestion_id,
                    action.app,
                    action.target_id,
                    action.action_type,
                    _json(action.payload),
                    action.status,
                    action.created_at,
                    action.completed_at,
                ),
            )
        return action

    def list_pending_actions(self, app: str | None = None) -> list[ConnectorAction]:
        values: list[Any] = ["pending"]
        where = "WHERE status = ?"
        if app:
            where += " AND app = ?"
            values.append(app)
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM connector_actions {where} ORDER BY created_at ASC",
                values,
            ).fetchall()
        return [self._action_from_row(row) for row in rows]

    def complete_action(self, action_id: str, status: str = "completed") -> ConnectorAction | None:
        completed_at = utc_now()
        with self.connect() as conn:
            conn.execute(
                "UPDATE connector_actions SET status = ?, completed_at = ? WHERE id = ?",
                (status, completed_at, action_id),
            )
            row = conn.execute("SELECT * FROM connector_actions WHERE id = ?", (action_id,)).fetchone()
        return self._action_from_row(row) if row else None

    def get_recent_connector_events(self, session_id: str, limit: int = 20) -> list[ConnectorEvent]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM connector_events WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [self._connector_event_from_row(row) for row in rows]

    def record_audit(self, session_id: str | None, event_type: str, payload: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO audit_log (id, session_id, event_type, payload, created_at) VALUES (?, ?, ?, ?, ?)",
                (new_id("audit"), session_id, event_type, _json(payload), utc_now()),
            )

    def _session_from_row(self, row: sqlite3.Row) -> Session:
        return Session(
            id=row["id"],
            goal=row["goal"],
            enabled_apps=_loads(row["enabled_apps"], []),
            upload_mode=row["upload_mode"],
            status=row["status"],
            started_at=row["started_at"],
            stopped_at=row["stopped_at"],
        )

    def _connector_event_from_row(self, row: sqlite3.Row) -> ConnectorEvent:
        return ConnectorEvent(
            id=row["id"],
            session_id=row["session_id"],
            app=row["app"],
            event_type=row["event_type"],
            source=row["source"],
            document_id=row["document_id"],
            title=row["title"],
            text=row["text"],
            metadata=_loads(row["metadata"], {}),
            created_at=row["created_at"],
        )

    def _suggestion_from_row(self, row: sqlite3.Row) -> Suggestion:
        return Suggestion(
            id=row["id"],
            session_id=row["session_id"],
            preference_id=row["preference_id"],
            app=row["app"],
            target_id=row["target_id"],
            before_text=row["before_text"],
            after_text=row["after_text"],
            reason=row["reason"],
            confidence=row["confidence"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _action_from_row(self, row: sqlite3.Row) -> ConnectorAction:
        return ConnectorAction(
            id=row["id"],
            suggestion_id=row["suggestion_id"],
            app=row["app"],
            target_id=row["target_id"],
            action_type=row["action_type"],
            payload=_loads(row["payload"], {}),
            status=row["status"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
        )
