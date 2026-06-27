from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from breadcrumbs.models import ConnectorEvent, ScreenObservation, new_id
from breadcrumbs.privacy import (
    PrivacyBoundaryError,
    assert_no_raw_screen_fields,
    redact_text,
    sanitize_connector_event,
    sanitize_screen_observation,
)


class SanitizerTest(unittest.TestCase):
    def test_redacts_common_sensitive_values(self) -> None:
        text = "Email surya@example.com or 415-555-1212 with sk-abc123456789abcdef."
        redacted = redact_text(text)
        self.assertIn("[email]", redacted)
        self.assertIn("[phone]", redacted)
        self.assertIn("[secret]", redacted)
        self.assertNotIn("surya@example.com", redacted)

    def test_rejects_raw_screen_fields(self) -> None:
        with self.assertRaises(PrivacyBoundaryError):
            assert_no_raw_screen_fields({"summary": "ok", "frame_path": "/tmp/screen.png"})

    def test_screen_observation_sanitization_drops_raw_ocr_and_frame(self) -> None:
        observation = ScreenObservation(
            id=new_id("ocr"),
            session_id="ses_1",
            app_name="Gmail",
            window_title="Draft to surya@example.com",
            ocr_text="raw text should stay local",
            summary="Editing a draft to surya@example.com",
            frame_path="/private/screen.png",
        )
        payload = sanitize_screen_observation(observation)
        self.assertNotIn("ocr_text", payload)
        self.assertNotIn("frame_path", payload)
        self.assertEqual(payload["summary"], "Editing a draft to [email]")

    def test_connector_event_uploads_snippet_not_full_text_key(self) -> None:
        event = ConnectorEvent(
            id="evt_1",
            session_id="ses_1",
            app="gmail",
            event_type="text_change",
            source="chrome-extension",
            document_id="doc_1",
            title="Hello",
            text="Please email surya@example.com",
            metadata={"url": "https://mail.google.com", "text": "local only"},
        )
        payload = sanitize_connector_event(event)
        self.assertEqual(payload["snippet"], "Please email [email]")
        self.assertNotIn("text", payload)
        self.assertNotIn("text", payload["metadata"])


if __name__ == "__main__":
    unittest.main()
