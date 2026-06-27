from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from breadcrumbs.ai import PreferenceEngine


class PreferenceEngineTest(unittest.TestCase):
    def test_infers_concise_direct_warm_preference(self) -> None:
        engine = PreferenceEngine()
        before = "Hi Sam, I just wanted to reach out to see if maybe you had time to talk. Let me know if possible."
        after = "Hi Sam, could we talk this week? Thanks,"
        preference = engine.infer("ses_1", before, after, ["evt_1"], app="gmail")
        self.assertIn("concise", preference.tags)
        self.assertIn("direct", preference.tags)
        self.assertIn("warm", preference.tags)
        self.assertGreaterEqual(preference.confidence, 0.75)

    def test_suggests_rewrites_for_cross_app_documents(self) -> None:
        engine = PreferenceEngine()
        preference = engine.infer(
            "ses_1",
            "I just wanted to reach out to see if maybe you could review this.",
            "Could you review this? Thanks.",
            ["evt_1"],
            app="slack",
        )
        suggestions = engine.suggest_for_documents(
            "ses_1",
            preference,
            [
                {
                    "app": "slack",
                    "target_id": "msg_1",
                    "text": "I just wanted to reach out to see if maybe this is ready.",
                },
                {
                    "app": "vscode",
                    "target_id": "file_1",
                    "text": "I think this function maybe handles user preferences.",
                },
            ],
        )
        self.assertEqual(len(suggestions), 2)
        self.assertTrue(all(suggestion.status == "pending" for suggestion in suggestions))
        self.assertIn("Thanks", suggestions[0].after_text)


if __name__ == "__main__":
    unittest.main()
