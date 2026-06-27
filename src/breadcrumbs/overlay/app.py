from __future__ import annotations

from urllib import parse, request
import json
import sys


def _get_json(url: str) -> dict:
    with request.urlopen(url, timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(url: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with request.urlopen(req, timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


def run_overlay(api_base: str = "http://127.0.0.1:8765") -> int:
    try:
        from PySide6.QtCore import Qt, QTimer
        from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
    except ImportError:
        print("PySide6 is not installed. Install dependencies with `pip install -e .`.", file=sys.stderr)
        return 1

    class BreadcrumbsBubble(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.session_id: str | None = None
            self.suggestion_id: str | None = None
            self.setWindowTitle("Breadcrumbs")
            self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setFixedWidth(360)

            self.label = QLabel("Breadcrumbs idle")
            self.label.setWordWrap(True)
            self.suggestion_label = QLabel("No pending suggestions")
            self.suggestion_label.setWordWrap(True)
            self.start_button = QPushButton("Start")
            self.stop_button = QPushButton("Stop")
            self.approve_button = QPushButton("Approve")
            self.reject_button = QPushButton("Reject")
            self.stop_button.setEnabled(False)
            self.approve_button.setEnabled(False)
            self.reject_button.setEnabled(False)
            self.start_button.clicked.connect(self.start_session)
            self.stop_button.clicked.connect(self.stop_session)
            self.approve_button.clicked.connect(self.approve_suggestion)
            self.reject_button.clicked.connect(self.reject_suggestion)

            buttons = QHBoxLayout()
            buttons.addWidget(self.start_button)
            buttons.addWidget(self.stop_button)
            review_buttons = QHBoxLayout()
            review_buttons.addWidget(self.approve_button)
            review_buttons.addWidget(self.reject_button)

            layout = QVBoxLayout()
            layout.addWidget(self.label)
            layout.addWidget(self.suggestion_label)
            layout.addLayout(buttons)
            layout.addLayout(review_buttons)
            self.setLayout(layout)
            self.setStyleSheet(
                """
                QWidget {
                    background: #111827;
                    color: white;
                    border-radius: 8px;
                    font-size: 13px;
                }
                QPushButton {
                    background: #2563eb;
                    border: 0;
                    border-radius: 6px;
                    padding: 7px 10px;
                }
                QPushButton:disabled {
                    background: #374151;
                }
                """
            )
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.refresh_suggestions)
            self.timer.start(2500)

        def start_session(self) -> None:
            try:
                response = _post_json(
                    f"{api_base}/sessions/start",
                    {
                        "goal": "Learn preferences from this active work session",
                        "enabledApps": ["gmail", "slack", "vscode"],
                        "uploadMode": "sanitized_context",
                    },
                )
                self.session_id = response["id"]
                self.label.setText(f"Recording locally. Session: {self.session_id}")
                self.start_button.setEnabled(False)
                self.stop_button.setEnabled(True)
            except Exception as exc:
                self.label.setText(f"Could not start: {exc}")

        def stop_session(self) -> None:
            if not self.session_id:
                return
            try:
                _post_json(f"{api_base}/sessions/{self.session_id}/stop", {})
                self.label.setText("Session stopped")
                self.session_id = None
                self.suggestion_id = None
                self.suggestion_label.setText("No pending suggestions")
                self.start_button.setEnabled(True)
                self.stop_button.setEnabled(False)
                self.approve_button.setEnabled(False)
                self.reject_button.setEnabled(False)
            except Exception as exc:
                self.label.setText(f"Could not stop: {exc}")

        def refresh_suggestions(self) -> None:
            if not self.session_id:
                return
            try:
                query = parse.urlencode({"sessionId": self.session_id, "status": "pending"})
                data = _get_json(f"{api_base}/suggestions?{query}")
                suggestions = data.get("suggestions") or []
                if not suggestions:
                    self.suggestion_id = None
                    self.suggestion_label.setText("No pending suggestions")
                    self.approve_button.setEnabled(False)
                    self.reject_button.setEnabled(False)
                    return
                suggestion = suggestions[0]
                self.suggestion_id = suggestion["id"]
                self.suggestion_label.setText(
                    f"{suggestion['app']}: {suggestion['reason']}\nTarget: {suggestion['target_id']}"
                )
                self.approve_button.setEnabled(True)
                self.reject_button.setEnabled(True)
            except Exception:
                return

        def approve_suggestion(self) -> None:
            if not self.suggestion_id:
                return
            try:
                _post_json(f"{api_base}/suggestions/{self.suggestion_id}/approve", {})
                self.suggestion_label.setText("Approved. Connector will apply it.")
                self.suggestion_id = None
                self.refresh_suggestions()
            except Exception as exc:
                self.suggestion_label.setText(f"Could not approve: {exc}")

        def reject_suggestion(self) -> None:
            if not self.suggestion_id:
                return
            try:
                _post_json(f"{api_base}/suggestions/{self.suggestion_id}/reject", {})
                self.suggestion_label.setText("Rejected.")
                self.suggestion_id = None
                self.refresh_suggestions()
            except Exception as exc:
                self.suggestion_label.setText(f"Could not reject: {exc}")

    app = QApplication(sys.argv)
    bubble = BreadcrumbsBubble()
    bubble.move(40, 80)
    bubble.show()
    return app.exec()
