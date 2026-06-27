from __future__ import annotations

from dataclasses import asdict
from typing import Any

from breadcrumbs.ai import PreferenceEngine
from breadcrumbs.capture import LocalOcrEngine, LocalScreenRecorder, ScreenCaptureService
from breadcrumbs.config import Settings
from breadcrumbs.memory import build_memory_client
from breadcrumbs.models import SuggestionStatus, UploadMode
from breadcrumbs.privacy import (
    sanitize_connector_event,
    sanitize_preference,
    sanitize_screen_observation,
    sanitize_suggestion,
)
from breadcrumbs.storage import SQLiteStore


def create_app(
    settings: Settings | None = None,
    store: SQLiteStore | None = None,
    memory_client: Any | None = None,
):
    try:
        from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
        from fastapi.middleware.cors import CORSMiddleware
        from pydantic import BaseModel, Field
    except ImportError as exc:
        raise RuntimeError("Install API dependencies with `pip install -e .` before running the server") from exc

    settings = settings or Settings.from_env()
    settings.ensure_dirs()
    store = store or SQLiteStore(settings.db_path)
    store.init_db()
    memory = memory_client or build_memory_client(settings)
    engine = PreferenceEngine()
    capture = ScreenCaptureService(settings.screenshots_dir)
    ocr = LocalOcrEngine()
    recorders: dict[str, LocalScreenRecorder] = {}

    class StartSessionRequest(BaseModel):
        goal: str = ""
        enabledApps: list[str] = Field(default_factory=lambda: ["gmail", "slack", "vscode"])
        uploadMode: str = UploadMode.SANITIZED_CONTEXT.value

    class ConnectorEventRequest(BaseModel):
        sessionId: str
        app: str
        eventType: str
        source: str = "connector"
        documentId: str | None = None
        title: str | None = None
        text: str | None = None
        metadata: dict[str, Any] = Field(default_factory=dict)

    class ScreenSummaryRequest(BaseModel):
        sessionId: str
        appName: str | None = None
        windowTitle: str | None = None
        ocrText: str | None = None
        summary: str
        framePath: str | None = None

    class TargetDocumentRequest(BaseModel):
        app: str
        targetId: str
        text: str

    class InferPreferenceRequest(BaseModel):
        sessionId: str
        beforeText: str
        afterText: str
        app: str | None = None
        evidenceEventIds: list[str] = Field(default_factory=list)
        targetDocuments: list[TargetDocumentRequest] = Field(default_factory=list)

    class ActionCompleteRequest(BaseModel):
        status: str = "completed"

    app = FastAPI(title="Breadcrumbs Local API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1", "http://localhost", "chrome-extension://*"],
        allow_origin_regex=r"chrome-extension://.*",
        allow_methods=["*"],
        allow_headers=["*"],
    )

    sockets: set[WebSocket] = set()

    def should_upload(session_id: str) -> bool:
        session = store.get_session(session_id)
        return bool(
            settings.cloud_upload_enabled
            and session
            and session.upload_mode == UploadMode.SANITIZED_CONTEXT.value
        )

    async def broadcast(message: dict[str, Any]) -> None:
        stale: list[WebSocket] = []
        for socket in sockets:
            try:
                await socket.send_json(message)
            except Exception:
                stale.append(socket)
        for socket in stale:
            sockets.discard(socket)

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "cloudUpload": settings.cloud_upload_enabled}

    @app.post("/sessions/start")
    async def start_session(payload: StartSessionRequest) -> dict[str, Any]:
        session = store.create_session(payload.goal, payload.enabledApps, payload.uploadMode)
        recorder = LocalScreenRecorder(
            session_id=session.id,
            capture=capture,
            ocr=ocr,
            store=store,
            memory_client=memory,
            upload_sanitized=should_upload(session.id),
            interval_sec=settings.screen_capture_interval_sec,
        )
        recorders[session.id] = recorder
        recorder.start()
        await broadcast({"type": "session_started", "session": asdict(session)})
        return asdict(session)

    @app.post("/sessions/{session_id}/stop")
    async def stop_session(session_id: str) -> dict[str, Any]:
        recorder = recorders.pop(session_id, None)
        if recorder:
            recorder.stop()
        session = store.stop_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="session not found")
        await broadcast({"type": "session_stopped", "session": asdict(session)})
        return asdict(session)

    @app.post("/events/connector")
    async def connector_event(payload: ConnectorEventRequest) -> dict[str, Any]:
        event = store.add_connector_event(
            session_id=payload.sessionId,
            app=payload.app,
            event_type=payload.eventType,
            source=payload.source,
            document_id=payload.documentId,
            title=payload.title,
            text=payload.text,
            metadata=payload.metadata,
        )
        sanitized = sanitize_connector_event(event)
        if should_upload(payload.sessionId):
            memory.upload_context_event(sanitized)
        await broadcast({"type": "connector_event", "event": sanitized})
        return {"event": asdict(event), "uploaded": should_upload(payload.sessionId)}

    @app.post("/events/screen-summary")
    async def screen_summary(payload: ScreenSummaryRequest) -> dict[str, Any]:
        observation = store.add_screen_observation(
            session_id=payload.sessionId,
            app_name=payload.appName,
            window_title=payload.windowTitle,
            ocr_text=payload.ocrText,
            summary=payload.summary,
            frame_path=payload.framePath,
        )
        sanitized = sanitize_screen_observation(observation)
        if should_upload(payload.sessionId):
            memory.upload_context_event(sanitized)
        await broadcast({"type": "screen_summary", "observation": sanitized})
        return {"observation": asdict(observation), "uploaded": should_upload(payload.sessionId)}

    @app.post("/preferences/infer")
    async def infer_preference(payload: InferPreferenceRequest) -> dict[str, Any]:
        preference = engine.infer(
            session_id=payload.sessionId,
            before_text=payload.beforeText,
            after_text=payload.afterText,
            evidence_event_ids=payload.evidenceEventIds,
            app=payload.app,
        )
        store.add_preference(preference)
        if should_upload(payload.sessionId):
            memory.upload_preference(sanitize_preference(preference))

        target_docs = [
            {"app": item.app, "target_id": item.targetId, "text": item.text}
            for item in payload.targetDocuments
        ]
        suggestions = engine.suggest_for_documents(payload.sessionId, preference, target_docs)
        store.add_suggestions(suggestions)
        if should_upload(payload.sessionId):
            for suggestion in suggestions:
                memory.upload_suggestion(sanitize_suggestion(suggestion))

        response = {
            "preference": asdict(preference),
            "suggestions": [asdict(suggestion) for suggestion in suggestions],
        }
        await broadcast({"type": "preference_inferred", **response})
        return response

    @app.get("/suggestions")
    def list_suggestions(
        sessionId: str | None = None,
        status: str | None = Query(default=SuggestionStatus.PENDING.value),
    ) -> dict[str, Any]:
        return {
            "suggestions": [
                asdict(suggestion)
                for suggestion in store.list_suggestions(session_id=sessionId, status=status)
            ]
        }

    @app.post("/suggestions/{suggestion_id}/approve")
    async def approve_suggestion(suggestion_id: str) -> dict[str, Any]:
        suggestion = store.update_suggestion_status(suggestion_id, SuggestionStatus.APPROVED.value)
        if not suggestion:
            raise HTTPException(status_code=404, detail="suggestion not found")
        action = store.enqueue_action_for_suggestion(suggestion)
        if should_upload(suggestion.session_id):
            memory.upload_suggestion(sanitize_suggestion(suggestion))
        await broadcast({"type": "suggestion_approved", "suggestion": asdict(suggestion), "action": asdict(action)})
        return {"suggestion": asdict(suggestion), "action": asdict(action)}

    @app.post("/suggestions/{suggestion_id}/reject")
    async def reject_suggestion(suggestion_id: str) -> dict[str, Any]:
        suggestion = store.update_suggestion_status(suggestion_id, SuggestionStatus.REJECTED.value)
        if not suggestion:
            raise HTTPException(status_code=404, detail="suggestion not found")
        if should_upload(suggestion.session_id):
            memory.upload_suggestion(sanitize_suggestion(suggestion))
        await broadcast({"type": "suggestion_rejected", "suggestion": asdict(suggestion)})
        return asdict(suggestion)

    @app.get("/actions/pending")
    def pending_actions(app: str | None = None) -> dict[str, Any]:
        return {"actions": [asdict(action) for action in store.list_pending_actions(app=app)]}

    @app.post("/actions/{action_id}/complete")
    async def complete_action(action_id: str, payload: ActionCompleteRequest) -> dict[str, Any]:
        action = store.complete_action(action_id, payload.status)
        if not action:
            raise HTTPException(status_code=404, detail="action not found")
        await broadcast({"type": "action_completed", "action": asdict(action)})
        return asdict(action)

    @app.websocket("/stream")
    async def stream(socket: WebSocket) -> None:
        await socket.accept()
        sockets.add(socket)
        try:
            await socket.send_json({"type": "connected"})
            while True:
                await socket.receive_text()
        except WebSocketDisconnect:
            sockets.discard(socket)

    return app
