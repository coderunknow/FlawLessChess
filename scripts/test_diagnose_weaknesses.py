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


def main() -> int:
    test_the_losing_game_is_a_replayable_pgn()
    test_a_truncated_game_is_unfinished_and_not_a_loss()
    test_the_losing_games_file_is_replaced_on_every_run()
    test_two_losing_games_stay_two_separate_pgn_records()
    print(f"\n{PASS} checks passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
