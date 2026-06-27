from __future__ import annotations

from threading import Event, Thread
from typing import Any
import time

from breadcrumbs.capture.ocr import LocalOcrEngine, summarize_ocr_text
from breadcrumbs.capture.screen import ScreenCaptureService
from breadcrumbs.privacy import sanitize_screen_observation
from breadcrumbs.storage import SQLiteStore


class LocalScreenRecorder:
    """Session-scoped local screenshot and OCR loop."""

    def __init__(
        self,
        session_id: str,
        capture: ScreenCaptureService,
        ocr: LocalOcrEngine,
        store: SQLiteStore,
        memory_client: Any,
        upload_sanitized: bool,
        interval_sec: float = 2.0,
    ) -> None:
        self.session_id = session_id
        self.capture = capture
        self.ocr = ocr
        self.store = store
        self.memory_client = memory_client
        self.upload_sanitized = upload_sanitized
        self.interval_sec = interval_sec
        self._stop = Event()
        self._thread = Thread(target=self._run, name=f"breadcrumbs-recorder-{session_id}", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                frame_path = self.capture.capture_frame(self.session_id)
                ocr_text = self.ocr.recognize_file(frame_path)
                summary = summarize_ocr_text(ocr_text)
                observation = self.store.add_screen_observation(
                    session_id=self.session_id,
                    app_name=None,
                    window_title=None,
                    ocr_text=ocr_text,
                    summary=summary,
                    frame_path=str(frame_path),
                )
                if self.upload_sanitized:
                    self.memory_client.upload_context_event(sanitize_screen_observation(observation))
            except Exception as exc:
                self.store.record_audit(
                    self.session_id,
                    "screen_capture_error",
                    {"error": str(exc), "local_only": True},
                )
                return
            self._stop.wait(self.interval_sec)
