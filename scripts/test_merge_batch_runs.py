#!/usr/bin/env python3
"""test_merge_batch_runs.py — synthetic self-test for merge_batch_runs.py.

Builds fake run dirs over the registered confirmatory designs (100 and 240
games), asserts the merge succeeds with full coverage, then asserts fail-closed
on: duplicate schedule index, identity mismatch, manifest bytes mismatch,
coverage gap, wrong opening, wrong BA seating, and unregistered expected-games
(the CodeRabbit 2026-11-27 findings #3/#5 for the merge path). Exits nonzero on
any failure.
"""
import json, os, shutil, subprocess, sys, tempfile, hashlib

ROOT = tempfile.mkdtemp(prefix="mergetest-")
SUITE50 = os.path.join(ROOT, "suite50.txt")
SUITE60 = os.path.join(ROOT, "suite60.txt")


def game(i, clusters, slots, counted=True, replay_of=None, white=None, black=None,
         opening=None, pair=None):
    slot = i % slots
    opening = opening or f"op{i // slots}"
    pair = pair or ("AB" if slot % 2 == 0 else "BA")
    if pair == "AB":
        white, black = white or "flawless", black or "topple-0.1.1"
    else:
        white, black = white or "topple-0.1.1", black or "flawless"
    return {"schedule_index": i, "counted": counted,
            "replay_of_schedule_index": replay_of, "result": "1/2-1/2",
            "white": white, "black": black, "opening": opening,
            "color_pair": pair,
            "reason": " adjud. " if counted else "replay"}


def manifest(engine_sha256=None):
    # Key shape mirrors the real per-run manifests written by aggregate_shards.py
    # (merge_batch_runs compares exactly these identity fields across runs).
    return {"batch": "A", "anchor": "topple-0.1.1",
            "engine_sha256": engine_sha256 or "e" * 64,
            "anchor_sha256": "a" * 64,
            "opening_suite_sha256": "suite",
            "time_control": {"mode": "clock", "period_moves": 40, "period_seconds": 900.0},
            "merged_sha256": None}


def write_run(name, games, man):
    d = os.path.join(ROOT, "runs", name)
    os.makedirs(d, exist_ok=True)
    gp = os.path.join(d, "games.jsonl")
    with open(gp, "w") as f:
        for g in games:
            f.write(json.dumps(g, sort_keys=True) + "\n")
    man = dict(man)
    man["n_attempts"] = len(games)
    man["n_counted"] = sum(1 for g in games if g.get("counted") is True)
    man["merged_sha256"] = hashlib.sha256(open(gp, "rb").read()).hexdigest()
    with open(os.path.join(d, "manifest.json"), "w") as f:
        json.dump(man, f)


def run_merge(expected_games, expect_fail=False, suite=None):
    out = os.path.join(ROOT, "canon")
    shutil.rmtree(out, ignore_errors=True)
    r = subprocess.run([sys.executable, "scripts/merge_batch_runs.py",
                        "--runs-root", os.path.join(ROOT, "runs"),
                        "--out", out, "--expected-games", str(expected_games),
                        "--suite", suite or (SUITE50 if expected_games == 100 else SUITE60)],
                       capture_output=True, text=True)
    if expect_fail:
        assert r.returncode != 0, f"expected FAIL, got success: {r.stdout}"
        return r.stderr.strip()
    assert r.returncode == 0, f"expected OK, got: {r.stderr}"
    canon = [json.loads(l) for l in open(os.path.join(out, "games.jsonl"))]
    man = json.load(open(os.path.join(out, "manifest.json")))
    assert [g["schedule_index"] for g in canon] == list(range(expected_games))
    assert man["n_counted"] == expected_games and man["n_runs"] == 2
    assert man["merged_sha256"] == hashlib.sha256(
        open(os.path.join(out, "games.jsonl"), "rb").read()).hexdigest()
    return r.stdout.strip()


def reset_runs():
    shutil.rmtree(os.path.join(ROOT, "runs"), ignore_errors=True)


# 50-opening suite for the 100-game design; 60-opening for the 240-game one.
with open(SUITE50, "w") as f:
    f.write("".join(f"op{i} | e4\n" for i in range(50)))
with open(SUITE60, "w") as f:
    f.write("".join(f"op{i} | e4\n" for i in range(60)))

# 1. happy path (100 = 50 openings x 2 slots): run-1 covers 0-49 + a replay of
# 49 (BA leg), run-2 covers 50-99. Exercises BA seating acceptance.
reset_runs()
write_run("run-1", [game(i, 50, 2) for i in range(50)]
          + [game(49, 50, 2, counted=False, replay_of=49)], manifest())
write_run("run-2", [game(i, 50, 2) for i in range(50, 100)], manifest())
print("case1 OK:", run_merge(100))

# 2. duplicate schedule index across runs -> fail closed
reset_runs()
write_run("run-1", [game(i, 50, 2) for i in range(50)], manifest())
write_run("run-2", [game(i, 50, 2) for i in range(45, 95)], manifest())
print("case2 (dup) OK:", run_merge(100, expect_fail=True))

# 3. identity mismatch (different engine binary hash across runs) -> fail closed
reset_runs()
write_run("run-1", [game(i, 50, 2) for i in range(50)], manifest())
write_run("run-2", [game(i, 50, 2) for i in range(50, 100)],
          manifest(engine_sha256="f" * 64))
print("case3 (identity) OK:", run_merge(100, expect_fail=True))

# 4. manifest bytes mismatch -> fail closed
reset_runs()
write_run("run-1", [game(i, 50, 2) for i in range(50)], manifest())
write_run("run-2", [game(i, 50, 2) for i in range(50, 100)], manifest())
d = os.path.join(ROOT, "runs", "run-2", "games.jsonl")
os.chmod(d, 0o644)
with open(d, "a") as f:
    f.write("\n")
print("case4 (bytes) OK:", run_merge(100, expect_fail=True))

# 5. gap in coverage -> fail closed
reset_runs()
write_run("run-1", [game(i, 50, 2) for i in range(50)], manifest())
write_run("run-2", [game(i, 50, 2) for i in range(51, 100)], manifest())
print("case5 (gap) OK:", run_merge(100, expect_fail=True))

# 6. one record seated under the wrong opening -> fail closed (the mapping is
# validated for EVERY registered design now)
reset_runs()
bad = [game(i, 50, 2) for i in range(50, 100)]
bad[0]["opening"] = "op49"  # index 50 must be op25
write_run("run-1", [game(i, 50, 2) for i in range(50)], manifest())
write_run("run-2", bad, manifest())
print("case6 (wrong opening) OK:", run_merge(100, expect_fail=True))

# 7. a BA leg seated like AB (Flawless white) -> fail closed
reset_runs()
bad = [game(i, 50, 2) for i in range(50, 100)]
bad[1] = game(51, 50, 2, white="flawless", black="topple-0.1.1")  # pair BA
bad[1]["color_pair"] = "BA"
bad[1]["opening"] = "op25"
write_run("run-1", [game(i, 50, 2) for i in range(50)], manifest())
write_run("run-2", bad, manifest())
print("case7 (BA seating) OK:", run_merge(100, expect_fail=True))

# 8. 240-game design (60 openings x 4 slots = 2 reps x AB/BA) merges with the
# generalized opening/pair mapping
reset_runs()
write_run("run-1", [game(i, 60, 4) for i in range(120)], manifest())
write_run("run-2", [game(i, 60, 4) for i in range(120, 240)], manifest())
print("case8 (240-shape) OK:", run_merge(240))

# 9. unregistered expected-games -> fail closed
reset_runs()
write_run("run-1", [game(i, 50, 2) for i in range(50)], manifest())
write_run("run-2", [game(i, 50, 2) for i in range(50, 100)], manifest())
print("case9 (unregistered shape) OK:", run_merge(2040, expect_fail=True))

shutil.rmtree(ROOT, ignore_errors=True)
print("merge_batch_runs self-test: ALL CASES PASS")
