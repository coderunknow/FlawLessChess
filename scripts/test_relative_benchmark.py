#!/usr/bin/env python3
"""Regression tests for the PR-relative paired engine benchmark tooling."""
from __future__ import annotations

import json
import random
import sys
import tempfile
from argparse import Namespace
from pathlib import Path

import chess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import relative_benchmark as rb  # noqa: E402

PASS = 0
FAIL = 0


def check(cond: bool, message: str) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"FAIL: {message}")


def make_pair(name: str, candidate_white_result: str, candidate_black_result: str) -> list[dict]:
    """Return one correctly paired AB/BA opening, with results from White's perspective."""
    return [
        {
            "opening": name,
            "white": rb.CANDIDATE_NAME,
            "black": rb.BASELINE_NAME,
            "result": candidate_white_result,
            "counted": True,
            "engine_error": False,
            "adjudicated": True,
            "color_pair": "AB",
            "schedule_index": 0,
        },
        {
            "opening": name,
            "white": rb.BASELINE_NAME,
            "black": rb.CANDIDATE_NAME,
            "result": candidate_black_result,
            "counted": True,
            "engine_error": False,
            "adjudicated": True,
            "color_pair": "BA",
            "schedule_index": 1,
        },
    ]


def random_legal_opening_lines(count: int, seed: int) -> list[tuple[str, list[str]]]:
    rng = random.Random(seed)
    lines: list[tuple[str, list[str]]] = []
    seen: set[tuple[str, ...]] = set()
    while len(lines) < count:
        board = chess.Board()
        moves: list[str] = []
        for _ in range(6):
            legal = list(board.legal_moves)
            move = rng.choice(legal)
            moves.append(move.uci())
            board.push(move)
        key = tuple(moves)
        if key not in seen and not board.is_game_over(claim_draw=True):
            seen.add(key)
            lines.append((f"Test opening {len(lines):03d}", moves))
    return lines


def test_openings_are_verified_and_shuffle_reproducible() -> None:
    quick = rb.load_opening_suites([ROOT / "benches/openings-20.txt"])
    check(len(quick) == 20, "quick profile committed suite has 20 openings")
    suites = [
        rb.load_opening_suites([ROOT / "benches/rating-openings-100-batchA.txt"]),
        rb.load_opening_suites([ROOT / "benches/rating-openings-100-batchB.txt"]),
    ]
    check(len(suites[0]) == 50 and len(suites[1]) == 50, "extended suites each contain 50 openings")
    merged = suites[0] + suites[1]
    check(len({name for name, _ in merged}) == 100, "extended suite names are unique")
    check(
        [name for name, _ in rb.shuffled_openings(merged, 20261124)]
        == [name for name, _ in rb.shuffled_openings(merged, 20261124)],
        "same seed reproduces opening order",
    )
    check(
        [name for name, _ in rb.shuffled_openings(merged, 20261124)]
        != [name for name, _ in rb.shuffled_openings(merged, 20261125)],
        "different seed changes opening order",
    )


def test_color_pairing_and_wdl_summary() -> None:
    games = make_pair("open-1", "1-0", "1/2-1/2")
    games += make_pair("open-2", "0-1", "1/2-1/2")
    errors = rb.validate_run_records(games, ["open-1", "open-2"])
    check(not errors, "exact AB/BA color reversal validates")
    summary = rb.summarize_records(games, ["open-1", "open-2"], 7, bootstrap_replicates=1000)
    check(summary["valid"], "valid paired games pass validation")
    check(summary["wdl"] == {"W": 1, "D": 2, "L": 1}, "candidate W/D/L counted from both colors")
    check(summary["score"]["points"] == 2.0 and summary["score"]["percent"] == 50.0,
          "paired score percentage computed correctly")
    check(summary["relative_elo"]["estimate"] == 0.0, "50% maps to zero relative logistic Elo")


def test_invalid_or_uncounted_game_is_not_scored() -> None:
    games = make_pair("open-1", "1-0", "1-0")
    games[0]["counted"] = False
    games[0]["engine_error"] = True
    summary = rb.summarize_records(games, ["open-1"], 9, bootstrap_replicates=100)
    check(not summary["valid"], "engine-error/un-counted attempt invalidates the run")
    check(summary["games"] == 1 and summary["wdl"] == {"W": 0, "D": 0, "L": 1},
          "engine-error loss is excluded from scored W/D/L")


def test_zero_score_is_severe_without_finite_elo_claim() -> None:
    games: list[dict] = []
    names = []
    for i in range(20):
        name = f"open-{i}"
        names.append(name)
        games += make_pair(name, "0-1", "1-0")
    summary = rb.summarize_records(games, names, 11, bootstrap_replicates=1000)
    check(summary["valid"], "complete zero-score benchmark remains structurally valid")
    check(summary["severe_regression"], "zero-score boundary triggers severe-regression policy")
    check(summary["relative_elo"]["estimate"] is None, "perfect boundary is not clamped to finite Elo")
    check(summary["relative_elo"]["ci95"] == [None, None], "boundary CI values are null, not clamped")


def test_three_run_aggregate_is_clustered_and_provenance_checked() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "runs"
        suite_lines = random_legal_opening_lines(100, 55)
        for run_no in range(1, 4):
            run = root / f"replicate-{run_no}"
            match = run / "match"
            match.mkdir(parents=True)
            rb.write_openings(run / "openings.used.txt", suite_lines, 20261123 + run_no)
            games: list[dict] = []
            for index, (name, _moves) in enumerate(suite_lines):
                pair = make_pair(name, "1-0", "1/2-1/2")
                for row in pair:
                    row["schedule_index"] = index * 2 + (0 if row["color_pair"] == "AB" else 1)
                games.extend(pair)
            (match / "games.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in games), encoding="utf-8"
            )
            (run / "summary.json").write_text(json.dumps({"valid": True}), encoding="utf-8")
            manifest = {
                "kind": "relative_engine_match",
                "profile": "extended",
                "status": "completed",
                "seed": 20261123 + run_no,
                "candidate_commit": "candidate-sha",
                "baseline_commit": "baseline-sha",
                "candidate_binary": {"sha256": "c" * 64},
                "baseline_binary": {"sha256": "b" * 64},
                "opening_suites": [{"path": "suite.txt", "sha256": "a" * 64}],
                "opening_order_file": "openings.used.txt",
                "elapsed_seconds": 1.0,
            }
            (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        out = Path(td) / "aggregate"
        code = rb.aggregate_runs(Namespace(runs_root=str(root), out=str(out), bootstrap_seed=72))
        result = json.loads((out / "aggregate-summary.json").read_text(encoding="utf-8"))
        check(code == 0, "three valid extended replicates aggregate successfully")
        check(result["valid"] and result["games"] == 600, "aggregate retains all 600 paired games")
        check(result["opening_clusters"] == 100, "bootstrap unit stays 100 openings, not 600 games")
        check(len(result["replicates"]) == 3, "aggregate records all replicate seeds")


def test_a_perfect_score_is_a_positive_relative_signal() -> None:
    # At a perfect score the logistic Elo model has no finite value (the boundary is 1.0), so
    # the classification must be driven by the score interval and not by the Elo estimate.
    games: list[dict] = []
    names = []
    for i in range(20):
        name = f"open-{i}"
        names.append(name)
        # The results are from White's perspective: the candidate is White in the first game and
        # Black in the second, so a candidate win is "1-0" then "0-1".
        games += make_pair(name, "1-0", "0-1")
    summary = rb.summarize_records(games, names, 17, bootstrap_replicates=1000)
    check(summary["valid"], "a clean sweep is structurally valid")
    check(summary["games"] == 40, "every game of the sweep is scored")
    check(summary["score"]["fraction"] == 1.0, "the sweep scores a full point per game")
    check(
        summary["classification"] == "POSITIVE_RELATIVE_SIGNAL_SCREENING_ONLY",
        "a perfect score is a positive relative signal, not INCONCLUSIVE",
    )
    check(summary["relative_elo"]["estimate"] is None, "the Elo boundary stays null, not clamped")
    check(summary["relative_elo"]["ci95"] == [None, None], "the boundary CI values stay null")
    check(not summary["severe_regression"], "a perfect score is not a severe regression")


def test_game_without_the_candidate_is_excluded_from_the_scorable_set() -> None:
    # A row that does not name the candidate cannot be scored. It must be left out of the
    # confidence interval as well, otherwise the interval and the point estimate are computed
    # over different sets of games.
    games = make_pair("open-1", "1-0", "1/2-1/2")
    stray = dict(games[0])
    stray["white"] = "somebody-else"
    stray["black"] = "somebody-else"
    games.append(stray)
    summary = rb.summarize_records(games, ["open-1"], 13, bootstrap_replicates=200)
    check(not summary["valid"], "a game without the candidate is a validation error")
    check(summary["games"] == 2, "the game without the candidate is not scored")
    check(summary["opening_clusters"] == 1, "the game without the candidate is not clustered")


def test_opening_order_digest_is_verified_before_aggregation() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "runs"
        suite_lines = random_legal_opening_lines(100, 56)
        digests = []
        for run_no in range(1, 4):
            run = root / f"replicate-{run_no}"
            match = run / "match"
            match.mkdir(parents=True)
            used = run / "openings.used.txt"
            rb.write_openings(used, suite_lines, 20261123 + run_no)
            digests.append(rb.sha256_file(used))
            games: list[dict] = []
            for index, (name, _moves) in enumerate(suite_lines):
                pair = make_pair(name, "1-0", "1/2-1/2")
                for row in pair:
                    row["schedule_index"] = index * 2 + (0 if row["color_pair"] == "AB" else 1)
                games.extend(pair)
            (match / "games.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in games), encoding="utf-8"
            )
            (run / "summary.json").write_text(json.dumps({"valid": True}), encoding="utf-8")
            manifest = {
                "kind": "relative_engine_match",
                "profile": "extended",
                "status": "completed",
                "seed": 20261123 + run_no,
                "candidate_commit": "candidate-sha",
                "baseline_commit": "baseline-sha",
                "candidate_binary": {"sha256": "c" * 64},
                "baseline_binary": {"sha256": "b" * 64},
                "opening_suites": [{"path": "suite.txt", "sha256": "a" * 64}],
                "opening_order_file": "openings.used.txt",
                "opening_order_sha256": digests[-1],
                "flawless_ablate": "",
                "elapsed_seconds": 1.0,
            }
            (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        out = Path(td) / "aggregate-ok"
        code = rb.aggregate_runs(Namespace(runs_root=str(root), out=str(out), bootstrap_seed=73))
        result = json.loads((out / "aggregate-summary.json").read_text(encoding="utf-8"))
        check(code == 0 and result["valid"], "replicates with a matching opening digest aggregate")

        # Corrupt one replicate's saved opening order: the digest no longer matches the manifest.
        # The file stays well-formed, so only the digest check can catch it.
        tampered = root / "replicate-2" / "openings.used.txt"
        lines = tampered.read_text(encoding="utf-8").splitlines()
        index = next(i for i, line in enumerate(lines) if "|" in line)
        name, _sep, moves = lines[index].partition("|")
        parts = moves.split()
        parts[0] = "a2a3" if parts[0] != "a2a3" else "h2h3"
        lines[index] = f"{name}|{' '.join(parts)}"
        tampered.write_text("\n".join(lines) + "\n", encoding="utf-8")
        out2 = Path(td) / "aggregate-bad"
        code2 = rb.aggregate_runs(Namespace(runs_root=str(root), out=str(out2), bootstrap_seed=73))
        result2 = json.loads((out2 / "aggregate-summary.json").read_text(encoding="utf-8"))
        check(code2 != 0, "a mismatched opening-order digest fails the aggregation")
        check(not result2["valid"], "a mismatched opening-order digest invalidates the aggregate")
        check(any("digest mismatch" in e for e in result2["validation_errors"]),
              "the digest mismatch is reported as a validation error")


def test_replicates_with_different_ablation_masks_cannot_be_combined() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "runs"
        suite_lines = random_legal_opening_lines(100, 57)
        for run_no in range(1, 4):
            run = root / f"replicate-{run_no}"
            match = run / "match"
            match.mkdir(parents=True)
            rb.write_openings(run / "openings.used.txt", suite_lines, 20261123 + run_no)
            games: list[dict] = []
            for index, (name, _moves) in enumerate(suite_lines):
                pair = make_pair(name, "1-0", "1/2-1/2")
                for row in pair:
                    row["schedule_index"] = index * 2 + (0 if row["color_pair"] == "AB" else 1)
                games.extend(pair)
            (match / "games.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in games), encoding="utf-8"
            )
            (run / "summary.json").write_text(json.dumps({"valid": True}), encoding="utf-8")
            manifest = {
                "kind": "relative_engine_match",
                "profile": "extended",
                "status": "completed",
                "seed": 20261123 + run_no,
                "candidate_commit": "candidate-sha",
                "baseline_commit": "baseline-sha",
                "candidate_binary": {"sha256": "c" * 64},
                "baseline_binary": {"sha256": "b" * 64},
                "opening_suites": [{"path": "suite.txt", "sha256": "a" * 64}],
                "opening_order_file": "openings.used.txt",
                "flawless_ablate": "" if run_no != 2 else "space",
                "elapsed_seconds": 1.0,
            }
            (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        out = Path(td) / "aggregate-mixed"
        code = rb.aggregate_runs(Namespace(runs_root=str(root), out=str(out), bootstrap_seed=74))
        result = json.loads((out / "aggregate-summary.json").read_text(encoding="utf-8"))
        check(code != 0, "replicates under different ablation masks cannot be combined")
        check(not result["valid"], "mixed ablation masks invalidate the aggregate")
        check(any("ablation masks differ" in e for e in result["validation_errors"]),
              "the mixed ablation mask is reported as a validation error")


def main() -> int:
    test_openings_are_verified_and_shuffle_reproducible()
    test_color_pairing_and_wdl_summary()
    test_invalid_or_uncounted_game_is_not_scored()
    test_zero_score_is_severe_without_finite_elo_claim()
    test_three_run_aggregate_is_clustered_and_provenance_checked()
    test_a_perfect_score_is_a_positive_relative_signal()
    test_game_without_the_candidate_is_excluded_from_the_scorable_set()
    test_opening_order_digest_is_verified_before_aggregation()
    test_replicates_with_different_ablation_masks_cannot_be_combined()
    print(f"\n{PASS} checks passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
