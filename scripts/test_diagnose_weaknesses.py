#!/usr/bin/env python3
"""Regression tests for scripts/diagnose_weaknesses.py.

The script is an exploratory diagnostic, so the tests here cover the three properties that were
wrong and that a reader of the output would otherwise have to discover by hand:

1. The losing games are written as a replayable PGN, not as a board diagram.
2. A game that hit the ply cap is unfinished, not a loss.
3. The losing-games file is replaced on every run, so a run without losses cannot leave the
   losing games of an earlier run next to a summary that reports none.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import chess

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "diagnose_weaknesses.py"

PASS = 0
FAIL = 0


def check(cond: bool, message: str) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"ok   {message}")
    else:
        FAIL += 1
        print(f"FAIL {message}")


def load_module():
    spec = importlib.util.spec_from_file_location("diagnose_weaknesses", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_losing_game_is_a_replayable_pgn() -> None:
    dw = load_module()
    moves = [chess.Move.from_uci(u) for u in ["e2e4", "e7e5", "g1f3", "b8c6", "f1b5"]]
    pgn = dw.build_pgn(moves, 0, True, "0-1")
    check("[White \"candidate\"]" in pgn, "the PGN names the candidate as White")
    check("[Black \"greedy-eval-opponent\"]" in pgn, "the PGN names the opponent")
    check("[Result \"0-1\"]" in pgn, "the PGN carries the result")
    check("1. e4 e5 2. Nf3 Nc6 3. Bb5" in pgn, "the PGN carries the move history")

    game = chess.pgn.read_game(io.StringIO(pgn))
    check(game is not None, "the record parses as PGN")
    board = chess.Board()
    replayed = 0
    for move in game.mainline_moves():
        check_legal = move in board.legal_moves
        if not check_legal:
            break
        board.push(move)
        replayed += 1
    check(replayed == len(moves), "every move of the record replays from the start position")
    check(board.fen() == "r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3",
          "the replayed position is the position after the recorded moves")


def test_a_truncated_game_is_unfinished_and_not_a_loss() -> None:
    binary = REPO_ROOT / "target" / "release" / "flawless"
    if not binary.is_file():
        print("skip the truncated-game test: no release binary")
        return
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "run"
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--games", "2",
                "--movetime-ms", "20",
                "--max-plies", "1",
                "--binary", str(binary),
                "--out", str(out),
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        check(proc.returncode == 0, f"the diagnostic runs (rc={proc.returncode})")
        summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        check(summary["losing_games"] == 0, "a truncated game is not counted as a loss")
        check(summary["flagged_material_losses"] == 0, "a truncated game flags no material loss")
        for result in summary["results"]:
            check(result["result"] == "*", "the truncated game is recorded with the result '*'")
            check(result["unfinished"] is True, "the truncated game is marked unfinished")
            check(result["engine_lost"] is False, "the truncated game is not marked as a loss")
        check((out / "losing-games.pgn").is_file(), "the losing-games file is written")
        check((out / "losing-games.pgn").read_text(encoding="utf-8") == "",
              "the losing-games file is empty when there is no loss")


def test_the_losing_games_file_is_replaced_on_every_run() -> None:
    binary = REPO_ROOT / "target" / "release" / "flawless"
    if not binary.is_file():
        print("skip the replace-on-every-run test: no release binary")
        return
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "run"
        out.mkdir()
        # A stale file from an earlier run, with content that must not survive.
        stale = out / "losing-games.pgn"
        stale.write_text("[stale record from an earlier run]\n", encoding="utf-8")
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--games", "1",
                "--movetime-ms", "20",
                "--max-plies", "1",
                "--binary", str(binary),
                "--out", str(out),
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        check(proc.returncode == 0, f"the diagnostic runs over the stale file (rc={proc.returncode})")
        check(stale.read_text(encoding="utf-8") == "",
              "the stale losing games are replaced, not left in place")


def test_two_losing_games_stay_two_separate_pgn_records() -> None:
    """Two losses must produce two readable records, not one corrupted one."""
    module = load_module()
    chess = module.chess
    first = [chess.Move.from_uci("e2e4"), chess.Move.from_uci("e7e5")]
    second = [chess.Move.from_uci("d2d4"), chess.Move.from_uci("d7d5")]
    a = module.build_pgn(first, 0, True, "0-1")
    b = module.build_pgn(second, 1, False, "0-1")

    with tempfile.TemporaryDirectory() as td:
        out = Path(td)
        (out / "losing-games.pgn").write_text("\n\n".join([a, b]) + "\n", encoding="utf-8")
        text = (out / "losing-games.pgn").read_text(encoding="utf-8")

        import chess.pgn
        import io

        # `read_game` returns one game at a time, so the file has to be read until it is empty.
        games = []
        handle = io.StringIO(text)
        while True:
            parsed = chess.pgn.read_game(handle)
            if parsed is None:
                break
            games.append(parsed)
        check(len(games) == 2, f"both records are parsed (parsed {len(games)})")
        if len(games) == 2:
            check(games[0].headers.get("Round") == "1",
                  "the first record keeps its own round header")
            check(games[1].headers.get("Round") == "2",
                  "the second record keeps its own round header")
            check(games[0].headers.get("White") == "candidate",
                  "the first record keeps its own player headers")
            check(games[1].headers.get("White") == "greedy-eval-opponent",
                  "the second record keeps its own player headers")
            check([m.uci() for m in games[0].mainline_moves()] == ["e2e4", "e7e5"],
                  "the first record keeps its own move history")
            check([m.uci() for m in games[1].mainline_moves()] == ["d2d4", "d7d5"],
                  "the second record keeps its own move history")

    # The separator the script itself writes has to be the one the reader needs: a single newline
    # would let the second record's headers be swallowed by the first.
    joined = "\n\n".join([a, b])
    check("\n\n[Event " in joined, "the records are separated by a blank line")
    corrupted = "\n".join([a, b])
    handle = io.StringIO(corrupted)
    single = []
    while True:
        parsed = chess.pgn.read_game(handle)
        if parsed is None:
            break
        single.append(parsed)
    check(len(single) == 2, "a single newline still yields two records")
    if len(single) == 2:
        # python-chess reports a missing header as the PGN unknown marker "?".
        check(single[1].headers.get("Round") == "?",
              "a single newline strips the headers of the later record (the regression this guards)")
        check(single[1].headers.get("White") == "?",
              "a single newline strips the player headers of the later record")



# ---------------------------------------------------------------------------
# Engine failures must abort with a distinct exit code (3) and reap the child;
# a legitimate ply-cap truncation keeps exit code 0 (pinned above).
# ---------------------------------------------------------------------------

ENGINE_FAILURE_RC = 3

STUB_HEADER = (
    "#!/usr/bin/env python3\n"
    "import os, sys, time\n"
    "def uci():\n"
    "    print('id name stub')\n"
    "    print('uciok', flush=True)\n"
    "if os.environ.get('STUB_PID_FILE'):\n"
    "    open(os.environ['STUB_PID_FILE'], 'w').write(str(os.getpid()))\n"
)

# bestmove 0000: the engine saw no legal move where one exists.
STUB_0000 = STUB_HEADER + (
    "for line in sys.stdin:\n"
    "    line = line.strip()\n"
    "    if line == 'uci':\n"
    "        uci()\n"
    "    elif line.startswith('go'):\n"
    "        print('bestmove 0000', flush=True)\n"
)

# unparsable move token.
STUB_MALFORMED = STUB_HEADER + (
    "for line in sys.stdin:\n"
    "    line = line.strip()\n"
    "    if line == 'uci':\n"
    "        uci()\n"
    "    elif line.startswith('go'):\n"
    "        print('bestmove z9z9z9', flush=True)\n"
)

# legal-looking token that is illegal in the current position.
STUB_ILLEGAL = STUB_HEADER + (
    "for line in sys.stdin:\n"
    "    line = line.strip()\n"
    "    if line == 'uci':\n"
    "        uci()\n"
    "    elif line.startswith('go'):\n"
    "        print('bestmove a1a2', flush=True)\n"
)

# no bestmove at all: the stream simply ends.
STUB_MISSING = STUB_HEADER + (
    "for line in sys.stdin:\n"
    "    line = line.strip()\n"
    "    if line == 'uci':\n"
    "        uci()\n"
    "    elif line.startswith('go'):\n"
    "        print('info string thinking', flush=True)\n"
    "        sys.exit(0)\n"
)

# refuses to answer uci at all.
STUB_NO_UCIOK = STUB_HEADER + "sys.exit(0)\n"


def _write_stub(td: Path, name: str, body: str) -> Path:
    path = td / name
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return path


def _run_diagnostic(binary: Path, out: Path, games: str = "1", max_plies: str = "150",
                    pid_file: Path | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    if pid_file is not None:
        env["STUB_PID_FILE"] = str(pid_file)
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--games", games,
            "--movetime-ms", "10",
            "--max-plies", max_plies,
            "--binary", str(binary),
            "--out", str(out),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )


def test_engine_failure_aborts_with_distinct_exit_code() -> None:
    cases = {
        "0000": STUB_0000,
        "malformed": STUB_MALFORMED,
        "illegal": STUB_ILLEGAL,
        "missing bestmove": STUB_MISSING,
        "no uciok": STUB_NO_UCIOK,
    }
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        for label, body in cases.items():
            stub = _write_stub(td_path, f"stub_{label.replace(' ', '_')}.py", body)
            out = td_path / f"out_{label.replace(' ', '_')}"
            proc = _run_diagnostic(stub, out)
            check(proc.returncode == ENGINE_FAILURE_RC,
                  f"engine failure ({label}) aborts with rc={ENGINE_FAILURE_RC} (got {proc.returncode})")
            check("ENGINE FAILURE" in proc.stderr,
                  f"engine failure ({label}) names the failure on stderr")
            check("not a ply-cap truncation" in proc.stderr,
                  f"engine failure ({label}) distinguishes itself from truncation")
            check(not (out / "summary.json").exists(),
                  f"engine failure ({label}) writes no summary claiming results")


def test_engine_failure_exit_codes_are_distinct() -> None:
    # rc 2 (binary missing) and rc 3 (engine failure) must not collide, and a
    # legitimate truncation must remain rc 0 (pinned in the earlier test).
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        proc = _run_diagnostic(td_path / "no_such_binary", td_path / "out_missing_binary")
        check(proc.returncode == 2, f"a missing binary exits 2 (got {proc.returncode})")
        stub = _write_stub(td_path, "stub_0000b.py", STUB_0000)
        proc = _run_diagnostic(stub, td_path / "out_0000")
        check(proc.returncode == 3, f"an engine failure exits 3 (got {proc.returncode})")
        check(proc.returncode != 2, "engine failure and binary-missing exit codes differ")


def test_engine_failure_reaps_the_child_process() -> None:
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        pid_file = td_path / "stub.pid"
        stub = _write_stub(td_path, "stub_hang_fail.py", STUB_0000 + "time.sleep(60)\n")
        proc = _run_diagnostic(stub, td_path / "out", pid_file=pid_file)
        check(proc.returncode == ENGINE_FAILURE_RC,
              f"the hanging-stub failure aborts (rc={proc.returncode})")
        check(pid_file.is_file(), "the stub recorded its pid")
        if pid_file.is_file():
            pid = int(pid_file.read_text().strip())
            alive = True
            try:
                os.kill(pid, 0)
            except (ProcessLookupError, PermissionError):
                alive = False
            import time as _time
            for _ in range(20):
                if not alive:
                    break
                _time.sleep(0.5)
                try:
                    os.kill(pid, 0)
                except (ProcessLookupError, PermissionError):
                    alive = False
            check(not alive, "the engine child process is reaped before the abort returns")


def main() -> int:
    test_the_losing_game_is_a_replayable_pgn()
    test_a_truncated_game_is_unfinished_and_not_a_loss()
    test_the_losing_games_file_is_replaced_on_every_run()
    test_two_losing_games_stay_two_separate_pgn_records()
    test_engine_failure_aborts_with_distinct_exit_code()
    test_engine_failure_exit_codes_are_distinct()
    test_engine_failure_reaps_the_child_process()
    print(f"\n{PASS} checks passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
