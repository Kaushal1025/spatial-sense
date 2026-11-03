"""Tests for target normalization and per-frame phrase merging. No API calls.

Run from the repo root: python3 -m unittest discover -s server -p "test_*.py"
"""

import asyncio
import os
import unittest
from unittest import mock

from server import sam


class NormalizeTargetsTest(unittest.TestCase):
    def test_lowercase_and_trim(self):
        self.assertEqual(sam.normalize_targets(["  Frying   Pan "]), ["frying pan"])

    def test_max_three_words(self):
        self.assertEqual(sam.normalize_targets(["big red coffee mug"]), ["big red coffee"])

    def test_dedupe_drop_empty_and_cap(self):
        raw = ["Bottle", "bottle", "  ", "!!", "can", "keys", "phone"]
        self.assertEqual(sam.normalize_targets(raw), ["bottle", "can", "keys"])

    def test_strips_punctuation(self):
        self.assertEqual(sam.normalize_targets(["frying pan?"]), ["frying pan"])


class MergePhrasesTest(unittest.TestCase):
    def test_no_targets_no_hand(self):
        phrases = sam.merge_phrases([])
        self.assertNotIn("hand", phrases)
        self.assertEqual(phrases, sam.PHRASES[: sam.MAX_PHRASES])

    def test_targets_first_then_hand(self):
        phrases = sam.merge_phrases(["frying pan"])
        self.assertEqual(phrases[:2], ["frying pan", "hand"])
        self.assertEqual(len(phrases), sam.MAX_PHRASES)

    def test_dedupes_target_already_in_phrases(self):
        phrases = sam.merge_phrases(["chair", "bottle"])
        self.assertEqual(phrases[:3], ["chair", "bottle", "hand"])
        self.assertEqual(phrases.count("chair"), 1)
        self.assertEqual(len(phrases), sam.MAX_PHRASES)

    def test_cap_with_max_targets(self):
        phrases = sam.merge_phrases(["keys", "phone", "wallet"])
        self.assertEqual(phrases[:4], ["keys", "phone", "wallet", "hand"])
        self.assertEqual(len(phrases), 8)


class MockSegmentTest(unittest.TestCase):
    def test_mock_segment_uses_merged_phrases(self):
        with mock.patch.dict(os.environ, {"SAM_MOCK": "1"}):
            regions = asyncio.run(sam.segment(b"", phrases=sam.merge_phrases(["bottle"])))
        labels = {r["label"] for r in regions}
        self.assertIn("bottle", labels)
        self.assertIn("hand", labels)
        self.assertIn("person", labels)

    def test_mock_segment_default_skips_hand(self):
        with mock.patch.dict(os.environ, {"SAM_MOCK": "1"}):
            regions = asyncio.run(sam.segment(b""))
        self.assertNotIn("hand", {r["label"] for r in regions})


if __name__ == "__main__":
    unittest.main()
