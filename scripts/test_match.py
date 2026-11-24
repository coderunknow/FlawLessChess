#!/usr/bin/env python3
"""Regression tests for scripts/match.py (harness repair, RATING_PROTOCOL §3).

Run: python3 scripts/test_match.py   (needs python-chess; no pytest required)

Covers: clock-TC parsing and the repeating period schedule, deterministic
repetition scheduling (60x17x2=2040), engine-error record/replay/abort policy,
move-cap non-adjudication, manifest v2 finalization, and anchor-pool schema
hardening (template must be rejected; verified pools accepted).
"""
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import match  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

PASS = 0
FAIL = 0


def check(cond: bool, msg: str) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"FAIL: {msg}")


def raises_system_exit(fn, msg):
    try:
        fn()
    except SystemExit:
        return True
    check(False, msg + " (no SystemExit)")
    return False


# ---------------------------------------------------------------------------
# Stub UCI engines (python-chess based) for end-to-end harness tests.
# Modes: first/last (pick a move), mate (mate-in-1 else first), crash (exit at
# go), crash-once (exit at first go, then behave like mate), illegal, slow.
# ---------------------------------------------------------------------------

STUB = r'''
import sys, os, time
import chess
mode = sys.argv[1] if len(sys.argv) > 1 else "first"
marker = sys.argv[2] if len(sys.argv) > 2 else None
board = chess.Board()
print("id name stub-" + mode, flush=True)
while True:
    line = sys.stdin.readline()
    if not line:
        break
    parts = line.split()
    if not parts:
        continue
    cmd = parts[0]
    if cmd == "uci":
        print("uciok", flush=True)
    elif cmd == "isready":
        print("readyok", flush=True)
    elif cmd == "setoption":
        pass
    elif cmd == "position":
        board = chess.Board()
        if "moves" in parts:
            for u in parts[parts.index("moves") + 1:]:
                board.push_uci(u)
    elif cmd == "go":
        if mode == "crash":
            sys.stdout.flush()
            sys.exit(1)
        if mode == "crash-once":
            if marker and not os.path.exists(marker):
                open(marker, "w").write("x")
                sys.stdout.flush()
                sys.exit(1)
        if mode == "illegal":
            print("bestmove 0000", flush=True)
            continue
        if mode == "slow":
            time.sleep(0.2)
        moves = list(board.legal_moves)
        if not moves:
            print("bestmove 0000", flush=True)
            continue
        pick = None
        if mode in ("mate", "crash-once"):
            for m in moves:
                board.push(m)
                mate = board.is_checkmate()
                board.pop()
                if mate:
                    pick = m
                    break
        if pick is None:
            pick = moves[0] if mode != "last" else moves[-1]
        print("bestmove " + pick.uci(), flush=True)
    elif cmd == "quit":
        break
'''

# Deterministic one-move endings: each opening leaves a mate-in-1 for the side
# to move (opA: black mates with ...Qh4#; opB: white mates with Qxf7#), so the
# stub's 'mate' mode ends the game after exactly one engine move — exercising
# the go/clock path with counted, adjudicated results.
OPENINGS_MATE = ["opA|f2f3 e7e5 g2g4", "opB|e2e4 e7e5 f1c4 b8c6 d1h5 g8f6"]
OPENING_BLACK_MATES = "opA|f2f3 e7e5 g2g4"  # black to move, mate-in-1


def write_stub(tmpdir, name="stub_engine.py"):
    path = os.path.join(tmpdir, name)
    with open(path, "w") as f:
        f.write(STUB)
    return path


def run_match(tmpdir, extra_args, openings_lines, out_name,
              white_mode="mate", black_mode="mate", extra_stub_args=""):
    stub = write_stub(tmpdir)
    op = os.path.join(tmpdir, "openings.txt")
    with open(op, "w") as f:
        f.write("\n".join(openings_lines) + "\n")
    out = os.path.join(tmpdir, out_name)
    cmd = [sys.executable, os.path.join(HERE, "match.py"),
           "--white-cmd", f"{sys.executable} {stub} {white_mode} {extra_stub_args}".strip(),
           "--black-cmd", f"{sys.executable} {stub} {black_mode} {extra_stub_args}".strip(),
           "--openings", op, "--out", out] + extra_args
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    meta_path = os.path.join(out, "meta.json")
    meta = json.load(open(meta_path)) if os.path.exists(meta_path) else None
    games = []
    jsonl = os.path.join(out, "games.jsonl")
    if os.path.exists(jsonl):
        for line in open(jsonl):
            games.append(json.loads(line))
    return proc, meta, games


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


def test_parse_tc():
    tc = match.parse_tc("40/15", 0.0, "add")
    check(tc.period_moves == 40 and abs(tc.period_seconds - 900.0) < 1e-9, "parse 40/15 minutes")
    tc2 = match.parse_tc("40/900s", 5.0, "reset")
    check(tc2.period_seconds == 900.0 and tc2.increment_seconds == 5.0 and tc2.policy == "reset",
          "parse seconds + inc + reset")
    check(raises_system_exit(lambda: match.parse_tc("garbage", 0, "add"), "reject garbage tc"),
          "garbage tc rejected")
    check(raises_system_exit(lambda: match.parse_tc("40/15", 0, "weird"), "reject bad policy"),
          "bad tc-policy rejected")


def test_game_clock():
    tc = match.parse_tc("40/15", 0.0, "add")
    gc = match.GameClock(tc)
    import chess as _chess
    w = _chess.WHITE
    check(gc.go_args(w)[4] == 40, "movestogo=40 at start")
    check(gc.go_args(w)[0] == 900_000 and gc.go_args(w)[1] == 900_000, "both clocks start at period")
    # 40 white moves -> boundary: add policy grants a fresh period on top of remaining
    for _ in range(39):
        check(gc.charge(w, 1000), "no flag with plenty of time")
        gc.on_move_made(w)
    check(gc.moves_left["w"] == 1, "one move left before boundary")
    gc.charge(w, 1000)
    gc.on_move_made(w)
    check(gc.moves_left["w"] == 40, "period refilled to 40 moves")
    # started 900000, charged 40s total, added 900s at boundary -> 1760s
    check(gc.left_ms["w"] == 900_000 - 40_000 + 900_000, "add policy: carry + fresh period")
    # reset policy: clock SET to the period at the boundary
    gc2 = match.GameClock(match.parse_tc("40/15", 0.0, "reset"))
    for _ in range(40):
        gc2.charge(w, 1000)
        gc2.on_move_made(w)
    check(gc2.left_ms["w"] == 900_000, "reset policy: clock set to period")
    # flag fall detection
    gc3 = match.GameClock(match.parse_tc("40/2s", 0.0, "add"))
    check(gc3.charge(w, 2500) is False, "charge beyond clock -> flag")
    # increment applied per move
    gc4 = match.GameClock(match.parse_tc("40/15", 1.0, "add"))
    gc4.charge(w, 0)
    gc4.on_move_made(w)
    check(gc4.left_ms["w"] == 900_000 + 1000, "increment added after move")
    check(gc4.go_args(w)[2] == 1000 and gc4.go_args(w)[3] == 1000, "winc/binc passed through")


def test_schedule():
    openings = [(f"op{i}", []) for i in range(60)]
    sched = match.build_schedule(openings, 17)
    check(len(sched) == 60 * 17 * 2 == 2040, "60 x 17 x 2 = 2040 games")
    first = [s["color_pair"] for s in sched[:2]]
    check(first == ["AB", "BA"], "AB/BA reversal adjacent per repetition")
    check(all(sched[i]["opening_index"] == i // 34 for i in range(2040)), "opening-major order")
    s2 = match.build_schedule(openings, 17)
    check(match.schedule_sha256(sched) == match.schedule_sha256(s2), "schedule deterministic")
    check(match.schedule_sha256(sched) != match.schedule_sha256(match.build_schedule(openings, 1)),
          "different repetitions -> different schedule hash")
    # Deterministic sharding: contiguous slices partition the schedule exactly.
    n = len(sched)
    parts = []
    for i in range(4):
        lo, hi = i * n // 4, (i + 1) * n // 4
        parts.append(sched[lo:hi])
    check(sum(len(p) for p in parts) == n, "shards partition the schedule")
    check(parts[0] == sched[: n // 4] and parts[3] == sched[3 * n // 4 :], "contiguous ranges")


def valid_pool():
    return {
        "rating_source": "CCRL 40/15 list",
        "list_publication_date": "2026-11-13",
        "retrieval_date": "2026-11-14",
        "time_control": "40 moves in 15 minutes",
        "engines": [{
            "name": "ExampleEngine", "version": "1.2.3",
            "sha256": "a" * 64,
            "published_elo": 2100, "published_error": 25,
            "error_convention": "ci95",
            "license": "GPL-3.0", "license_verified": True,
            "binary_source_url": "https://example.org/engine-1.2.3",
            "binary_downloaded": True, "binary_sha256_verified": True,
        }],
    }


def test_anchor_schema():
    pool = valid_pool()
    match._require_anchor_schema(pool)  # must not raise
    # The committed template must NEVER validate (TBD/null placeholders).
    tpl_path = os.path.join(ROOT, "benches", "anchor-pool.template.json")
    tpl = json.load(open(tpl_path))
    check(raises_system_exit(lambda: match._require_anchor_schema(tpl), "template rejected"),
          "anchor-pool.template.json rejected by validator")
    bad = copy.deepcopy(pool); bad["engines"][0]["sha256"] = "deadbeef"
    check(raises_system_exit(lambda: match._require_anchor_schema(bad), "short sha rejected"),
          "malformed sha256 rejected")
    bad = copy.deepcopy(pool); bad["engines"][0]["published_elo"] = None
    check(raises_system_exit(lambda: match._require_anchor_schema(bad), "null elo rejected"),
          "null rating rejected")
    bad = copy.deepcopy(pool); bad["engines"][0]["error_convention"] = "plusminus 75"
    check(raises_system_exit(lambda: match._require_anchor_schema(bad), "ambiguous convention rejected"),
          "ambiguous uncertainty convention rejected")
    bad = copy.deepcopy(pool); bad["engines"][0]["license_verified"] = False
    check(raises_system_exit(lambda: match._require_anchor_schema(bad), "unverified license rejected"),
          "unverified license rejected")
    bad = copy.deepcopy(pool); bad["engines"][0]["binary_downloaded"] = False
    check(raises_system_exit(lambda: match._require_anchor_schema(bad), "missing binary rejected"),
          "unverified binary rejected")
    bad = copy.deepcopy(pool); bad["list_publication_date"] = "2026-13-99"
    check(raises_system_exit(lambda: match._require_anchor_schema(bad), "bad date rejected"),
          "invalid date rejected")
    bad = copy.deepcopy(pool); bad["engines"][0]["binary_source_url"] = "http://insecure.example/x"
    check(raises_system_exit(lambda: match._require_anchor_schema(bad), "non-https source rejected"),
          "non-https binary source rejected")
    bad = copy.deepcopy(pool); bad["engines"][0]["published_error"] = 0
    check(raises_system_exit(lambda: match._require_anchor_schema(bad), "zero error rejected"),
          "zero uncertainty rejected")


# ---------------------------------------------------------------------------
# End-to-end tests (real subprocesses, deterministic stubs)
# ---------------------------------------------------------------------------


def test_e2e_clock_batch():
    with tempfile.TemporaryDirectory() as td:
        proc, meta, games = run_match(td, ["--tc", "40/5s", "--repetitions", "2",
                                           "--threads", "1"],
                                      OPENINGS_MATE, "batch1")
        check(proc.returncode == 0, f"clock batch exit 0 (got {proc.returncode})")
        check(meta["completion_status"] == "completed", "manifest finalized: completed")
        check(meta["time_control"]["mode"] == "clock" and meta["time_control"]["period_moves"] == 40,
              "manifest records clock TC")
        check(meta["time_control"]["ponder"] is False, "pondering disabled")
        check(meta["threads"] == 1, "explicit single-thread engine option recorded")
        check(meta["n_games_planned"] == 8 and meta["n_games_counted"] == 8, "8 planned = 8 counted")
        check(meta["schedule"]["n_scheduled"] == 8, "schedule count recorded")
        check(meta["openings_file_sha256"] == hashlib.sha256(
            open(os.path.join(td, "openings.txt"), "rb").read()).hexdigest(), "opening-suite hash recorded")
        check("match_utc_start" in meta and "match_utc_end" in meta, "start+end timestamps")
        check(all(g["counted"] and g["adjudicated"] for g in games), "all games counted + adjudicated")
        check(all(g["result"] in ("1-0", "0-1") for g in games), "mate endings decisive")
        check([g["color_pair"] for g in games] == ["AB", "BA"] * 4, "AB/BA order preserved")
        check(all(g["clock_ms_at_end"] is not None for g in games), "clock state recorded")
        check([g["repetition"] for g in games] == [0, 0, 1, 1, 0, 0, 1, 1], "repetition ids recorded")


def test_e2e_error_abort():
    with tempfile.TemporaryDirectory() as td:
        proc, meta, games = run_match(td, ["--movetime", "50", "--games", "1",
                                           "--max-errors-per-side", "2",
                                           "--max-replays-per-game", "1"],
                                      [OPENING_BLACK_MATES], "batch2",
                                      white_mode="mate", black_mode="crash")
        check(proc.returncode == 2, "aborted batch returns 2")
        check(meta["completion_status"] == "aborted_engine_errors", "manifest records abort")
        check(meta["n_games_counted"] == 0, "engine-error games never counted")
        check(meta["engine_errors_by_side"].get("black") == 2, "two black errors -> abort")
        check(len(games) == 2 and all(not g["counted"] and g["engine_error"] for g in games),
              "both attempts recorded uncounted as engine_error")
        check(games[1]["replay_depth"] == 1 and games[1]["replay_of_schedule_index"] == 0,
              "second attempt is the recorded replay")


def test_e2e_replay_recovery():
    with tempfile.TemporaryDirectory() as td:
        stub = write_stub(td)
        marker = os.path.join(td, "marker")
        op = os.path.join(td, "openings.txt")
        open(op, "w").write(OPENING_BLACK_MATES + "\n")
        out = os.path.join(td, "batch3")
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, "match.py"),
             "--white-cmd", f"{sys.executable} {stub} mate",
             "--black-cmd", f"{sys.executable} {stub} crash-once {marker}",
             "--openings", op, "--out", out,
             "--movetime", "50", "--games", "1",
             "--max-errors-per-side", "2", "--max-replays-per-game", "1"],
            capture_output=True, text=True, timeout=120)
        meta = json.load(open(os.path.join(out, "meta.json")))
        games = [json.loads(l) for l in open(os.path.join(out, "games.jsonl"))]
        check(proc.returncode == 0, "recovery batch completes")
        check(meta["completion_status"] == "completed", "completed after replay")
        check(meta["n_engine_errors"] == 1 and meta["n_replays"] == 1, "1 error, 1 replay")
        check(meta["n_games_counted"] == 1 and meta["n_attempts"] == 2, "replay counted, original not")
        check(games[0]["counted"] is False and games[1]["counted"] is True, "counted flags correct")
        check(games[1]["replay_of_schedule_index"] == games[0]["schedule_index"], "replay identity")
        check(games[1]["result"] == "0-1" and games[1]["reason"] == "checkmate",
              "replayed game adjudicated normally")


def test_e2e_move_cap():
    with tempfile.TemporaryDirectory() as td:
        proc, meta, games = run_match(td, ["--movetime", "20", "--max-moves", "1", "--games", "1"],
                                      ["opA|"], "batch4", white_mode="first", black_mode="last")
        check(proc.returncode == 0, "move-cap batch exit 0")
        g = games[0]
        check(g["result"] == "*" and g["reason"] == "move_cap_unadjudicated", "move cap unadjudicated '*'")
        check(g["counted"] is False and meta["n_unadjudicated"] == 1, "move cap not scored")
        proc, meta, games = run_match(td, ["--movetime", "20", "--max-moves", "1", "--games", "1",
                                           "--move-cap-policy", "draw"], ["opA|"],
                                      "batch5", white_mode="first", black_mode="last")
        g = games[0]
        check(g["result"] == "1/2-1/2" and g["reason"] == "move_cap_draw_policy",
              "explicit draw policy honored (exploratory)")
        check(g["counted"] is True, "draw-policy games counted when explicitly requested")


def test_e2e_shard_manifest():
    with tempfile.TemporaryDirectory() as td:
        proc, meta, games = run_match(td, ["--tc", "40/5s", "--repetitions", "2",
                                           "--shard-index", "1", "--shard-count", "2",
                                           "--shard-id", "A-A1-01", "--batch-id", "A"],
                                      OPENINGS_MATE, "batch6")
        check(proc.returncode == 0, "shard batch exit 0")
        check(meta["shard_id"] == "A-A1-01" and meta["batch_id"] == "A", "shard/batch identity recorded")
        check(meta["schedule"]["shard"]["shard_index"] == 1, "shard slice recorded")
        check(meta["n_games_planned"] == 4, "half of the 8-game schedule in shard 1/2")
        check([g["schedule_index"] for g in games] == [4, 5, 6, 7], "contiguous slice identity")



def test_e2e_exact_schedule_index_recovery():
    with tempfile.TemporaryDirectory() as td:
        proc, meta, games = run_match(
            td,
            ["--movetime", "20", "--shard-index", "0", "--shard-count", "2",
             "--schedule-indices", "1"],
            OPENINGS_MATE,
            "batch-recovery-slot",
            white_mode="first",
            black_mode="last",
        )
        check(proc.returncode == 0, "exact schedule-index recovery exit 0")
        check(meta["n_games_planned"] == 1, "recovery schedules only the one missing game")
        check(meta["schedule"]["shard"]["selected_schedule_indices"] == [1],
              "manifest records exact recovered schedule index")
        check(len(games) == 1 and games[0]["schedule_index"] == 1,
              "recovery writes only schedule index 1")
        check(games[0]["color_pair"] == "BA", "recovery preserves requested reverse-color leg")

    with tempfile.TemporaryDirectory() as td:
        proc, meta, _games = run_match(
            td,
            ["--movetime", "20", "--shard-index", "0", "--shard-count", "2",
             "--schedule-indices", "2"],
            OPENINGS_MATE,
            "batch-invalid-recovery-slot",
        )
        check(proc.returncode != 0 and meta is None,
              "recovery rejects schedule index outside the assigned shard")
    with tempfile.TemporaryDirectory() as td:
        proc, meta, _games = run_match(
            td,
            ["--movetime", "20", "--shard-index", "0", "--shard-count", "2",
             "--schedule-indices", "1", "--games", "1"],
            OPENINGS_MATE,
            "batch-conflicting-recovery-options",
        )
        check(proc.returncode != 0 and meta is None,
              "recovery rejects combination with --games cap")

def main():
    test_parse_tc()
    test_game_clock()
    test_schedule()
    test_anchor_schema()
    test_e2e_clock_batch()
    test_e2e_error_abort()
    test_e2e_replay_recovery()
    test_e2e_move_cap()
    test_e2e_shard_manifest()
    test_e2e_exact_schedule_index_recovery()
    print(f"\n{PASS} checks passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
