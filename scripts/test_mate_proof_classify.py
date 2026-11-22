#!/usr/bin/env python3
"""Unit tests for the verdict logic in scripts/mate_proof_probe.py (no engine needed).

Each silent-pass path the release audit found must now produce a non-passing verdict.
Run: /home/user/.venv/bin/python3 scripts/test_mate_proof_classify.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mate_proof_probe as m  # noqa: E402


class ClassifyTests(unittest.TestCase):
    def test_exact_match_passes(self):
        self.assertEqual(m.classify(2, ("mate", 2), 3)[0], m.PASSING)

    def test_no_mate_and_no_claim_passes(self):
        self.assertEqual(m.classify(None, ("cp", 40), 3)[0], m.PASSING)

    def test_missed_mate_is_flagged(self):
        self.assertEqual(m.classify(2, ("cp", 900), 3)[0], "missed")

    def test_negative_mate_for_side_to_move_counts_as_missed(self):
        self.assertEqual(m.classify(2, ("mate", -2), 3)[0], "missed")

    def test_overstated_is_flagged(self):
        self.assertEqual(m.classify(2, ("mate", 4), 3)[0], "overstated")

    def test_understated_is_flagged(self):
        self.assertEqual(m.classify(3, ("mate", 1), 3)[0], "understated")

    def test_unverified_claim_beyond_limit_is_flagged(self):
        self.assertEqual(m.classify(None, ("mate", 5), 3)[0], "unverified")

    def test_no_score_line_is_flagged(self):
        self.assertEqual(m.classify(None, None, 3)[0], "no_score")
        self.assertEqual(m.classify(2, None, 3)[0], "no_score")

    def test_engine_score_parses_and_rejects_malformed(self):
        self.assertEqual(m.engine_score(["mate", "-2"]), ("mate", -2))
        self.assertEqual(m.engine_score(["cp", "15", "lowerbound"]), ("cp", 15))
        for bad in (["mate"], ["mate", "x"], ["bogus", "1"], []):
            with self.assertRaises(ValueError):
                m.engine_score(bad)

    def test_only_one_verdict_passes(self):
        verdicts = {m.classify(e, s, 3)[0] for e in (None, 1, 2) for s in (None, ("cp", 0), ("mate", 1), ("mate", 3), ("mate", 5))}
        self.assertIn(m.PASSING, verdicts)
        self.assertTrue(verdicts - {m.PASSING})


if __name__ == "__main__":
    unittest.main()
