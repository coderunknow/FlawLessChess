#!/usr/bin/env python3
"""Regression tests for exact-index RATING-100 recovery planning (stdlib only)."""
import hashlib
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from make_batch_dispatch import TIME_CONTROL, read_committed_runs, validate_power


IDENTITY = {
    "batch": "A",
    "anchor": "akimbo-0.1.1",
    "engine_sha256": "a" * 64,
    "anchor_sha256": "b" * 64,
    "opening_suite_sha256": "c" * 64,
    "time_control": TIME_CONTROL,
}
OPENINGS = [f"opening-{i:02d}" for i in range(50)]


def write_run(root, name, games, *, identity=None):
    run = os.path.join(root, name)
    os.makedirs(run)
    games_bytes = "".join(json.dumps(game, sort_keys=True) + "\n" for game in games).encode()
    with open(os.path.join(run, "games.jsonl"), "wb") as handle:
        handle.write(games_bytes)
    manifest = dict(identity or IDENTITY)
    manifest.update({
        "merged_sha256": hashlib.sha256(games_bytes).hexdigest(),
        "n_counted": sum(game.get("counted") is True for game in games),
        "n_attempts": len(games),
    })
    with open(os.path.join(run, "manifest.json"), "w", encoding="utf-8") as handle:
        json.dump(manifest, handle)


def game(index, *, counted=True, pair=None):
    return {
        "schedule_index": index,
        "white": "flawless",
        "black": "akimbo-0.1.1",
        "opening": OPENINGS[index // 2],
        "color_pair": pair or ("AB" if index % 2 == 0 else "BA"),
        "counted": counted,
        "engine_error": not counted,
        "adjudicated": True,
        "result": "1-0" if counted else "*",
        "replay_depth": 0 if counted else 1,
        "replay_of_schedule_index": None if counted else index,
        "moves": ["e2e4"],
    }


def expect_system_exit(call, label):
    try:
        call()
    except SystemExit:
        print("PASS", label)
    else:
        raise AssertionError(label + " must fail closed")


def read(root):
    # Fixture layout: 50 opening pairs, one repetition -> 50 shards x 2 color slots.
    return read_committed_runs(
        root, batch="A", anchor="akimbo-0.1.1",
        engine_sha=IDENTITY["engine_sha256"],
        anchor_sha=IDENTITY["anchor_sha256"],
        suite_sha=IDENTITY["opening_suite_sha256"],
        opening_names=OPENINGS,
        clusters=len(OPENINGS), repetitions=1,
    )


def main():
    with tempfile.TemporaryDirectory() as td:
        assert read(os.path.join(td, "not-created")) == {}
        write_run(td, "run-1", [game(0)])
        missing = read(td)
        assert missing[0] == [1]
        assert len(missing) == 50
        print("PASS exact reverse-color slot recovered without replaying counted AB")

    with tempfile.TemporaryDirectory() as td:
        write_run(td, "run-1", [game(0), game(1)])
        missing = read(td)
        assert 0 not in missing
        assert len(missing) == 49
        print("PASS complete AB/BA pair is never scheduled again")

    with tempfile.TemporaryDirectory() as td:
        write_run(td, "run-1", [game(0)])
        write_run(td, "run-2", [game(0)])
        expect_system_exit(lambda: read(td), "duplicate counted slot across runs")

    with tempfile.TemporaryDirectory() as td:
        wrong = dict(IDENTITY)
        wrong["time_control"] = {"mode": "clock", "period_moves": 40, "period_seconds": 900.001}
        write_run(td, "run-1", [game(0)], identity=wrong)
        expect_system_exit(lambda: read(td), "time-control identity mismatch")

    with tempfile.TemporaryDirectory() as td:
        bad = game(0)
        bad["opening"] = "different-opening"
        write_run(td, "run-1", [bad])
        expect_system_exit(lambda: read(td), "registered opening mismatch")

    with tempfile.TemporaryDirectory() as td:
        power_path = os.path.join(td, "power.json")
        power = {
            "design": "rating-100-v1",
            "sample_design": "rating-100-v1",
            "status": "PASS",
            "eligible_for_confirmatory_dispatch": True,
            "engine_sha256": IDENTITY["engine_sha256"],
            "opening_suites": {"batch_a_sha256": "a" * 64, "batch_b_sha256": "b" * 64},
            "approval": {
                "reviewer": "test",
                "reviewed_at": "2026-11-17",
                "evidence_ref": "synthetic-test",
                "decision_rule": "all three lower bounds strictly > 2000",
            },
        }
        with open(power_path, "w", encoding="utf-8") as handle:
            json.dump(power, handle)
        accepted = validate_power(
            power_path, "rating-100-v1", "a" * 64, "b" * 64, IDENTITY["engine_sha256"]
        )
        assert accepted["engine_sha256"] == IDENTITY["engine_sha256"]
        print("PASS matching engine SHA is accepted by the power guard")
        expect_system_exit(
            lambda: validate_power(power_path, "rating-100-v1", "a" * 64, "b" * 64, "d" * 64),
            "power assessment engine-SHA mismatch",
        )

    print("make_batch_dispatch recovery tests: 7/7 PASS")


if __name__ == "__main__":
    main()
