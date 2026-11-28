#!/usr/bin/env python3
"""Regression suite for benches/diagnostics/adjudicate_traps.py.

Pins two adjudication bugs found in source review (2026-11-28):

* en passant: the captured pawn sits on the double-pushed pawn's square, not on
  the capture's ``to_square`` — a pawn collected en passant must count as
  collected, and ordinary captures must keep working (both colors);
* duplicate-flag cross-join: flags are bound to the exact source record; two
  transposed records sharing (fen, ply, move) keys must be accounted once per
  occurrence, never N x M.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import chess

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "benches" / "diagnostics"))

from adjudicate_traps import adjudicate, captured_square  # noqa: E402

PASS = 0
FAIL = 0


def check(condition: bool, message: str) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"ok   {message}")
    else:
        FAIL += 1
        print(f"FAIL {message}")


def game(white: str, black: str, moves: list[str], game_index: int) -> dict:
    return {
        "game_index": game_index,
        "white": white,
        "black": black,
        "result": "0-1",
        "opening": "fixture",
        "moves": moves,
    }


def run_records(records: list[dict], focus: str = "flawless") -> dict:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "games.jsonl"
        with open(path, "w", encoding="utf-8") as handle:
            for rec in records:
                handle.write(json.dumps(rec) + "\n")
        return adjudicate(str(path), focus=focus)


# 1.a3 e5 2.Nf3 e4 3.d4 exd3 e.p.: the d4 pawn is collected en passant and
# black could instead win the f3 knight (300cp) at the same time, so the move
# carries a moved_piece flag whose collection the old code missed.
EP_WHITE = ["a2a3", "e7e5", "g1f3", "e5e4", "d2d4", "e4d3"]
# Mirror for black as focus: 1.e4 Nf6 2.e5 a6 3.h3 d5 4.exd6 e.p. The e5 pawn
# attacks the f6 knight from move 2 on, so both black moves (a6, d5) carry a
# moved_piece flag; only the d5 double push is answered by the e.p. capture.
EP_BLACK = ["e2e4", "g8f6", "e4e5", "a7a6", "h2h3", "d7d5", "e5d6"]
# Ordinary capture of the moved piece still counts: 1.a3 e5 2.Nf3 e4 3.d3 exd3.
PLAIN_WHITE = ["a2a3", "e7e5", "g1f3", "e5e4", "d2d3", "e4d3"]


def test_captured_square_helper() -> None:
    board = chess.Board()
    board.push_uci("e2e4")
    board.push_uci("a7a6")
    board.push_uci("e4e5")
    board.push_uci("d7d5")
    ep = chess.Move.from_uci("e5d6")
    check(board.is_en_passant(ep), "e5d6 is an en passant capture in the fixture")
    check(
        captured_square(board, ep) == chess.parse_square("d5"),
        "captured_square returns the double-pushed pawn's square (d5), white capturing",
    )
    board.push(ep)
    board.push_uci("b8c6")
    board.push_uci("d2d4")
    plain = chess.Move.from_uci("c6d4")
    check(
        captured_square(board, plain) == chess.parse_square("d4"),
        "captured_square returns to_square for an ordinary capture",
    )
    board.push(plain)
    quiet = chess.Move.from_uci("g1f3")
    check(captured_square(board, quiet) is None, "captured_square is None for a quiet move")


def test_pawn_collected_en_passant_counts() -> None:
    result = run_records([game("flawless", "other", EP_WHITE, 0)])
    mp = result["moved_piece"]
    check(mp["flags"] == 1, "white-focus en passant fixture raises exactly one moved_piece flag")
    check(mp["collected"] == 1, "a pawn collected en passant counts as collected (white focus)")


def test_pawn_collected_en_passant_counts_black_focus() -> None:
    result = run_records([game("other", "flawless", EP_BLACK, 0)])
    mp = result["moved_piece"]
    check(mp["flags"] == 2, "black-focus fixture raises exactly two moved_piece flags (a6 and d5)")
    check(mp["collected"] == 1, "the pawn collected en passant counts as collected (black focus)")


def test_ordinary_capture_still_counts() -> None:
    result = run_records([game("flawless", "other", PLAIN_WHITE, 0)])
    mp = result["moved_piece"]
    check(mp["flags"] == 1, "ordinary-capture fixture raises exactly one moved_piece flag")
    check(mp["collected"] == 1, "an ordinary capture of the moved piece still counts")


def test_unanswered_move_is_not_collected() -> None:
    # Same hanging-knight shape, but the reply plays elsewhere: nothing collected.
    moves = ["a2a3", "e7e5", "g1f3", "e5e4", "d2d4", "a7a6"]
    result = run_records([game("flawless", "other", moves, 0)])
    mp = result["moved_piece"]
    check(mp["flags"] == 1, "the flag still fires when the move loses material elsewhere")
    check(mp["collected"] == 0, "a non-capturing reply collects nothing")


def test_duplicate_keys_count_once_per_record() -> None:
    # Two transposed records share every (fen, ply, move) key; each flag must be
    # applied to exactly one source occurrence (2 counts), never cross-joined
    # (the old code produced 2 records x 2 flags = 4).
    result = run_records(
        [
            game("flawless", "other", EP_WHITE, 1),
            game("flawless", "other", EP_WHITE, 2),
        ]
    )
    mp = result["moved_piece"]
    check(mp["flags"] == 2, "two records with identical keys give exactly two flags")
    check(mp["collected"] == 2, "each flag is counted exactly once (no N x N cross-join)")
    check(result["details"] == [], "no phantom details from duplicated keys")
    check(result["games"] == 2, "both source records were adjudicated")


def main() -> int:
    test_captured_square_helper()
    test_pawn_collected_en_passant_counts()
    test_pawn_collected_en_passant_counts_black_focus()
    test_ordinary_capture_still_counts()
    test_unanswered_move_is_not_collected()
    test_duplicate_keys_count_once_per_record()
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
