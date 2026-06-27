from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from breadcrumbs.memory.embeddings import hash_embedding
from breadcrumbs.memory.mongo_memory import NoopMemoryClient
from breadcrumbs.privacy import PrivacyBoundaryError


class MemoryTest(unittest.TestCase):
    def test_hash_embedding_is_deterministic_and_normalized(self) -> None:
        first = hash_embedding("make outreach concise", dims=8)
        second = hash_embedding("make outreach concise", dims=8)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 8)

    def test_noop_memory_enforces_privacy_boundary(self) -> None:
        client = NoopMemoryClient()
        with self.assertRaises(PrivacyBoundaryError):
            client.upload_context_event({"summary": "bad", "screenshot_path": "/tmp/a.png"})


if __name__ == "__main__":
    unittest.main()
