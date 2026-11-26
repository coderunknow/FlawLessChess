#!/usr/bin/env python3
"""Manifest identity tests for the RATING-100 prospective power assessment."""
import hashlib
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from power_analysis import SCREENING_ENGINE_SHA256, SCREENING_SUITE_SHA256, read_screening_engine_sha

ENGINE_SHA = SCREENING_ENGINE_SHA256


def write_anchor(root: str, anchor: str, engine_sha: str) -> str:
    directory = os.path.join(root, anchor)
    os.makedirs(directory)
    games_path = os.path.join(directory, "games.jsonl")
    with open(games_path, "w", encoding="utf-8", newline="\n") as handle:
        for _ in range(120):
            handle.write(json.dumps({"counted": True}) + "\n")
    with open(games_path, "rb") as handle:
        games_sha = hashlib.sha256(handle.read()).hexdigest()
    manifest = {
        "batch": "A",
        "anchor": anchor,
        "engine_sha256": engine_sha,
        "opening_suite_sha256": SCREENING_SUITE_SHA256,
        "n_counted": 120,
        "n_attempts": 120,
        "merged_sha256": games_sha,
    }
    with open(os.path.join(directory, "manifest.json"), "w", encoding="utf-8") as handle:
        json.dump(manifest, handle)
    return games_path


class ScreeningIdentityTests(unittest.TestCase):
    def test_matching_manifests_return_frozen_engine_hash(self):
        with tempfile.TemporaryDirectory() as td:
            games_a = write_anchor(td, "topple-0.1.1", ENGINE_SHA)
            games_b = write_anchor(td, "topple-0.2.1", ENGINE_SHA)
            self.assertEqual(read_screening_engine_sha(games_a, games_b), ENGINE_SHA)

    def test_different_engine_hashes_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            games_a = write_anchor(td, "topple-0.1.1", ENGINE_SHA)
            games_b = write_anchor(td, "topple-0.2.1", "8" * 64)
            with self.assertRaisesRegex(ValueError, "preregistered only for SCREEN-2"):
                read_screening_engine_sha(games_a, games_b)

    def test_windows_crlf_checkout_preserves_manifest_integrity(self):
        with tempfile.TemporaryDirectory() as td:
            games_a = write_anchor(td, "topple-0.1.1", ENGINE_SHA)
            games_b = write_anchor(td, "topple-0.2.1", ENGINE_SHA)
            with open(games_a, "rb") as handle:
                lf_bytes = handle.read()
            with open(games_a, "wb") as handle:
                handle.write(lf_bytes.replace(b"\n", b"\r\n"))
            self.assertEqual(read_screening_engine_sha(games_a, games_b), ENGINE_SHA)

    def test_games_file_content_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            games_a = write_anchor(td, "topple-0.1.1", ENGINE_SHA)
            games_b = write_anchor(td, "topple-0.2.1", ENGINE_SHA)
            with open(games_a, "a", encoding="utf-8", newline="\n") as handle:
                handle.write("{}\n")
            with self.assertRaisesRegex(ValueError, "merged_sha256"):
                read_screening_engine_sha(games_a, games_b)

    def test_anchor_identity_must_match_registered_source(self):
        with tempfile.TemporaryDirectory() as td:
            games_a = write_anchor(td, "unexpected-anchor", ENGINE_SHA)
            games_b = write_anchor(td, "topple-0.2.1", ENGINE_SHA)
            with self.assertRaisesRegex(ValueError, "expected Batch A anchor"):
                read_screening_engine_sha(games_a, games_b)


class PowerAnalysisV2IdentityTests(unittest.TestCase):
    """The generalized power assessment: campaign label sets and frozen-engine identity."""

    def test_pool_key_strips_every_campaign_suffix(self):
        import power_analysis_v2 as v2
        self.assertEqual(v2.pool_key("topple-0.1.1-e3"), "topple-0.1.1")
        self.assertEqual(v2.pool_key("topple-0.1.1-e4"), "topple-0.1.1")
        self.assertEqual(v2.pool_key("akimbo-0.1.1-e4b"), "akimbo-0.1.1")

    def test_pool_key_rejects_missing_suffix_and_unknown_anchor(self):
        import power_analysis_v2 as v2
        with self.assertRaisesRegex(ValueError, "campaign suffix"):
            v2.pool_key("topple-0.1.1")
        with self.assertRaisesRegex(ValueError, "unknown anchor"):
            v2.pool_key("stockfish-8-e4")

    def test_label_sets_must_address_the_same_anchors(self):
        import power_analysis_v2 as v2
        v2.validate_label_sets(list(v2.DEFAULT_LABELS_A), list(v2.DEFAULT_LABELS_B))
        v2.validate_label_sets(list(v2.E4_LABELS_A), list(v2.E4_LABELS_B))
        # The E3 convention shares labels across suites; shared labels validate too.
        v2.validate_label_sets(list(v2.DEFAULT_LABELS_A), list(v2.E4_LABELS_B))
        with self.assertRaisesRegex(ValueError, "same anchors"):
            v2.validate_label_sets(list(v2.E4_LABELS_A), list(v2.E4_LABELS_B)[::-1])
        with self.assertRaisesRegex(ValueError, "same anchors"):
            v2.validate_label_sets(["topple-0.1.1-e4"], ["topple-0.1.1-e4b", "topple-0.2.1-e4b"])
        with self.assertRaisesRegex(ValueError, "unknown anchor"):
            v2.validate_label_sets(["mystery-e4"], ["mystery-e4b"])

    def _write_v2_anchor(self, root, label, batch, engine_sha):
        import power_analysis_v2 as v2
        directory = os.path.join(root, label)
        os.makedirs(directory)
        games_path = os.path.join(directory, "games.jsonl")
        with open(games_path, "w", encoding="utf-8", newline="\n") as handle:
            for _ in range(120):
                handle.write(json.dumps({"counted": True}) + "\n")
        with open(games_path, "rb") as handle:
            games_sha = hashlib.sha256(handle.read()).hexdigest()
        manifest = {
            "batch": batch,
            "anchor": label,
            "engine_sha256": engine_sha,
            "opening_suite_sha256": v2.SUITE_A_SHA256 if batch == "A" else v2.SUITE_B_SHA256,
            "n_counted": 120,
            "n_attempts": 120,
            "merged_sha256": games_sha,
        }
        with open(os.path.join(directory, "manifest.json"), "w", encoding="utf-8") as handle:
            json.dump(manifest, handle)
        return games_path

    def test_read_manifest_enforces_the_frozen_engine_sha(self):
        import power_analysis_v2 as v2
        with tempfile.TemporaryDirectory() as td:
            games = self._write_v2_anchor(td, "topple-0.1.1-e4b", "B", "a" * 64)
            manifest = v2.read_manifest(games, "topple-0.1.1-e4b", "B", v2.SUITE_B_SHA256, "a" * 64)
            self.assertEqual(manifest["engine_sha256"], "a" * 64)
            with self.assertRaisesRegex(ValueError, "frozen engine binary"):
                v2.read_manifest(games, "topple-0.1.1-e4b", "B", v2.SUITE_B_SHA256, "b" * 64)

    def test_read_manifest_enforces_label_batch_and_suite(self):
        import power_analysis_v2 as v2
        with tempfile.TemporaryDirectory() as td:
            games = self._write_v2_anchor(td, "akimbo-0.1.1-e4", "A", "a" * 64)
            with self.assertRaisesRegex(ValueError, "expected label"):
                v2.read_manifest(games, "akimbo-0.1.1-e4b", "A", v2.SUITE_A_SHA256, "a" * 64)
            with self.assertRaisesRegex(ValueError, "expected batch"):
                v2.read_manifest(games, "akimbo-0.1.1-e4", "B", v2.SUITE_A_SHA256, "a" * 64)
            with self.assertRaisesRegex(ValueError, "suite hash"):
                v2.read_manifest(games, "akimbo-0.1.1-e4", "A", v2.SUITE_B_SHA256, "a" * 64)


if __name__ == "__main__":
    unittest.main()
