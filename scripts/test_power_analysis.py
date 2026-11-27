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

    def _write_v2_anchor_with_openings(self, root, label, batch, engine_sha):
        """120 attempts: 59 complete pairs + one Petroff pair whose AB leg is unadjudicated."""
        import power_analysis_v2 as v2
        directory = os.path.join(root, label)
        os.makedirs(directory)
        games_path = os.path.join(directory, "games.jsonl")
        records = []
        for i in range(59):
            records.append({"counted": True, "opening": f"opening-{i:02d}", "white": "flawless",
                            "black": "anchor", "result": "1-0"})
            records.append({"counted": True, "opening": f"opening-{i:02d}", "white": "anchor",
                            "black": "flawless", "result": "0-1"})
        records.append({"counted": False, "adjudicated": False, "reason": "move_cap_unadjudicated",
                        "opening": "Petroff Defence", "white": "flawless", "black": "anchor",
                        "result": "*"})
        records.append({"counted": True, "opening": "Petroff Defence", "white": "anchor",
                        "black": "flawless", "result": "1/2-1/2"})
        with open(games_path, "w", encoding="utf-8", newline="\n") as handle:
            for record in records:
                handle.write(json.dumps(record) + "\n")
        with open(games_path, "rb") as handle:
            games_sha = hashlib.sha256(handle.read()).hexdigest()
        manifest = {
            "batch": batch, "anchor": label, "engine_sha256": engine_sha,
            "opening_suite_sha256": v2.SUITE_A_SHA256 if batch == "A" else v2.SUITE_B_SHA256,
            "n_counted": 119, "n_attempts": 120, "merged_sha256": games_sha,
        }
        with open(os.path.join(directory, "manifest.json"), "w", encoding="utf-8") as handle:
            json.dump(manifest, handle)
        return games_path

    def test_complete_case_cluster_exclusion_accepts_an_unadjudicated_pair(self):
        import power_analysis_v2 as v2
        exclude = frozenset(["Petroff Defence"])
        with tempfile.TemporaryDirectory() as td:
            games = self._write_v2_anchor_with_openings(td, "topple-0.2.1-e3", "A", "a" * 64)
            # Without the exclusion the file is rejected (119 counted / one single-leg cluster).
            with self.assertRaisesRegex(ValueError, "counted once|exactly two counted"):
                v2.read_manifest(games, "topple-0.2.1-e3", "A", v2.SUITE_A_SHA256, "a" * 64)
            v2.read_manifest(games, "topple-0.2.1-e3", "A", v2.SUITE_A_SHA256, "a" * 64, exclude)
            clusters = v2.load_cluster_games(games, exclude=exclude)
            self.assertEqual(len(clusters), 59)
            self.assertNotIn("Petroff Defence", clusters)
            with self.assertRaisesRegex(ValueError, "exactly two counted"):
                v2.load_cluster_games(games)  # no exclusion: single-leg cluster fails closed

    def test_exclusion_names_must_match_records(self):
        import power_analysis_v2 as v2
        exclude = frozenset(["Petroff Defence"])
        with tempfile.TemporaryDirectory() as td:
            games = self._write_v2_anchor_with_openings(td, "topple-0.2.1-e3", "A", "a" * 64)
            # A wrong name excludes nothing: the manifest check must still reject 119 counted.
            with self.assertRaisesRegex(ValueError, "counted once|manifest counted"):
                v2.read_manifest(games, "topple-0.2.1-e3", "A", v2.SUITE_A_SHA256, "a" * 64,
                                 frozenset(["Not An Opening"]))

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


class RestrictClustersTests(unittest.TestCase):
    """Regression tests for the design-loop cluster restriction.

    The first cut filtered ``games[batch].items()`` by cluster names even though
    its keys are LABELS, so ``restricted`` was always empty and every design
    died with a fabricated "missing clusters" error. These tests pin the
    label -> cluster -> scores structure and the fail-loud missing check.
    """

    def test_restricts_per_label_cluster_maps(self):
        import power_analysis_v2 as v2
        batch_games = {
            "lab-a": {"Ruy Lopez Morphy": [1.0, 0.0], "Petroff Defence": [0.5, 0.5]},
            "lab-b": {"Ruy Lopez Morphy": [0.0, 1.0], "Petroff Defence": [1.0, 1.0]},
        }
        restricted = v2.restrict_clusters(batch_games, {"Ruy Lopez Morphy"},
                                          ["lab-a", "lab-b"], "A")
        self.assertEqual(sorted(restricted), ["lab-a", "lab-b"])
        self.assertEqual(restricted["lab-a"], {"Ruy Lopez Morphy": [1.0, 0.0]})
        self.assertEqual(restricted["lab-b"], {"Ruy Lopez Morphy": [0.0, 1.0]})

    def test_missing_cluster_fails_loud_with_the_name(self):
        import power_analysis_v2 as v2
        batch_games = {"lab-a": {"Ruy Lopez Morphy": [1.0, 0.0]}}
        with self.assertRaisesRegex(ValueError, "lab-a.*Benoni Defence"):
            v2.restrict_clusters(batch_games, {"Ruy Lopez Morphy", "Benoni Defence"},
                                 ["lab-a"], "B")

    def test_wanted_minus_exclude_matches_registered_disposition(self):
        # The design rule is unchanged (60 clusters); the exclusion removes
        # clusters from the measurement only.
        names = {"Petroff Defence", "Ruy Lopez Morphy", "Italian Game"}
        exclude = frozenset({"Petroff Defence"})
        import power_analysis_v2 as v2
        batch_games = {
            "lab-a": {"Ruy Lopez Morphy": [1.0, 0.0], "Italian Game": [0.5, 0.5],
                      "Petroff Defence": [0.5, 0.5]},
        }
        restricted = v2.restrict_clusters(batch_games, names - exclude, ["lab-a"], "A")
        self.assertEqual(set(restricted["lab-a"]), {"Ruy Lopez Morphy", "Italian Game"})


if __name__ == "__main__":
    unittest.main()
