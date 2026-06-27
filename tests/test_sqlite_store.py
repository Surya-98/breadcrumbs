from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from breadcrumbs.ai import PreferenceEngine
from breadcrumbs.storage import SQLiteStore


class SQLiteStoreTest(unittest.TestCase):
    def test_session_event_preference_suggestion_and_action_flow(self) -> None:
        with TemporaryDirectory() as tmp:
            store = SQLiteStore(Path(tmp) / "breadcrumbs.sqlite3")
            store.init_db()
            session = store.create_session("demo", ["gmail", "slack", "vscode"], "sanitized_context")
            event = store.add_connector_event(
                session_id=session.id,
                app="gmail",
                event_type="text_change",
                source="test",
                document_id="draft_1",
                title="Draft",
                text="I just wanted to reach out to see if maybe you can meet.",
            )

            engine = PreferenceEngine()
            preference = engine.infer(
                session.id,
                event.text or "",
                "Could we meet this week? Thanks.",
                [event.id],
                app="gmail",
            )
            store.add_preference(preference)
            suggestions = engine.suggest_for_documents(
                session.id,
                preference,
                [{"app": "gmail", "target_id": "draft_2", "text": event.text or ""}],
            )
            store.add_suggestions(suggestions)

            pending = store.list_suggestions(session_id=session.id)
            self.assertEqual(len(pending), 1)
            approved = store.update_suggestion_status(pending[0].id, "approved")
            self.assertIsNotNone(approved)
            action = store.enqueue_action_for_suggestion(approved)
            self.assertEqual(action.app, "gmail")
            self.assertEqual(store.list_pending_actions("gmail")[0].id, action.id)

            completed = store.complete_action(action.id)
            self.assertEqual(completed.status, "completed")


if __name__ == "__main__":
    unittest.main()
