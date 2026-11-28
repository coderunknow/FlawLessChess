#!/usr/bin/env python3
"""Tactical diagnostics for the Flawless engine.

**Diagnostic output, not strength evidence.** The script checks objective, referee-verified
properties of a handful of positions (mate in one, winning capture, stalemate) and records, per
position, the first search depth at which the engine played the expected move.

The expectations are derived with python-chess at run time (the pinned test oracle), not
hard-coded, so a wrong fixture cannot make the diagnostic pass. Every position is checked
for legality first: both kings present, the side not to move is not in check.

Usage:
    python3 scripts/tactic_test.py [--binary PATH] [--max-depth 10] [--out DIR]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

import chess

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BIN = REPO_ROOT / "target" / "release" / "flawless"
DEFAULT_OUT = REPO_ROOT / "benches" / "tactic-test-20261124"

# Rough material values, used only to decide whether a capture wins material.
VALUE = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}

# (name, fen, expectation)
#   "mate"      : the engine has to play a move that is checkmate in the position
#   "capture"   : the engine has to play a move that wins the hanging piece
#   "legal"     : the engine has to return a legal move (no objective claim)
#   "none"      : the side to move has no legal move; the engine must answer "bestmove 0000"
# Every FEN below was verified with the python-chess referee: valid position, the side not to
# move is not in check, and the expected set of moves is not empty.
CASES: list[tuple[str, str, str]] = [
    ("mate1_queen", "7k/5Q2/6K1/8/8/8/8/8 w - - 0 1", "mate"),
    ("mate1_rook", "7k/8/6K1/8/8/8/8/R7 w - - 0 1", "mate"),
    ("win_queen", "4k3/8/8/8/3q4/8/8/3RK3 w - - 0 1", "capture"),
    ("win_rook", "4k3/8/8/8/8/8/3r4/3RK3 w - - 0 1", "capture"),
    ("stalemate", "7k/5Q2/5K2/8/8/8/8/8 b - - 0 1", "none"),
    ("quiet_legal", "4k3/8/8/8/8/8/4P3/4K3 w - - 0 1", "legal"),
]


def mating_moves(board: chess.Board) -> set[str]:
    out = set()
    for move in board.legal_moves:
        board.push(move)
        if board.is_checkmate():
            out.add(move.uci())
        board.pop()
    return out


def winning_captures(board: chess.Board) -> set[str]:
    """Captures that win material.

    A capture wins when the captured piece is worth more than the capturer, and also when the
    captured piece is worth at least as much but is not defended afterwards, so that the
    capturing side comes out of the exchange ahead.
    """
    out = set()
    for move in board.legal_moves:
        if not board.is_capture(move):
            continue
        victim = board.piece_at(move.to_square)
        capturer = board.piece_at(move.from_square)
        if victim is None or capturer is None:
            continue
        gain = VALUE[victim.piece_type] - VALUE[capturer.piece_type]
        if gain > 0:
            out.add(move.uci())
            continue
        if gain == 0:
            # Equal material: the capture only wins when the captured piece cannot be taken back.
            board.push(move)
            recapturable = any(
                reply.to_square == move.to_square and board.is_capture(reply)
                for reply in board.legal_moves
            )
            board.pop()
            if not recapturable:
                out.add(move.uci())
    return out


def expected_moves(board: chess.Board, expectation: str) -> set[str]:
    if expectation == "mate":
        return mating_moves(board)
    if expectation == "capture":
        return winning_captures(board)
    if expectation == "none":
        return {"0000"}
    return {move.uci() for move in board.legal_moves}


class EngineError(RuntimeError):
    """The engine process failed in a way that makes the diagnostic meaningless."""


def engine_bestmove(binary: Path, fen: str, depth: int) -> str | None:
    proc = subprocess.Popen(
        [str(binary), "uci"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=0,
    )
    try:
        proc.stdin.write("uci\n")
        proc.stdin.flush()
        # An engine that closes stdout without answering must not spin this loop forever.
        while True:
            line = proc.stdout.readline()
            if not line:
                raise EngineError("the engine closed stdout before answering 'uciok'")
            if line.strip() == "uciok":
                break
        proc.stdin.write(f"position fen {fen}\n")
        proc.stdin.flush()
        proc.stdin.write(f"go depth {depth}\n")
        proc.stdin.flush()
        bestmove = None
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            if line.startswith("bestmove"):
                parts = line.split()
                bestmove = parts[1] if len(parts) > 1 else None
                break
        return bestmove
    finally:
        # The engine may already have gone away; a broken pipe here must not mask the result.
        try:
            proc.stdin.write("quit\n")
            proc.stdin.flush()
        except (BrokenPipeError, ValueError, OSError):
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", default=str(DEFAULT_BIN))
    parser.add_argument("--max-depth", type=int, default=10)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    binary = Path(args.binary)
    if not binary.is_file() or not os.access(binary, os.X_OK):
        print(f"engine binary missing or not executable: {binary}")
        return 2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    results = []
    for name, fen, expectation in CASES:
        board = chess.Board(fen)
        if not board.is_valid():
            print(f"SKIP {name}: invalid position ({board.status()})")
            results.append(
                {"name": name, "fen": fen, "expectation": expectation, "valid": False,
                 "expected_moves": [], "found_at_depth": None, "passed": False,
                 "note": "position rejected by the referee"}
            )
            continue
        expected = expected_moves(board, expectation)
        if not expected:
            print(f"SKIP {name}: the referee found no move satisfying '{expectation}'")
            results.append(
                {"name": name, "fen": fen, "expectation": expectation, "valid": True,
                 "expected_moves": [], "found_at_depth": None, "passed": False,
                 "note": "no objective expectation for this position"}
            )
            continue

        found_at = None
        chosen = None
        for depth in range(1, args.max_depth + 1):
            best = engine_bestmove(binary, fen, depth)
            if best is None:
                break
            chosen = best
            if best in expected:
                found_at = depth
                break
        if expectation == "none" and chosen == "0000" and found_at is None:
            found_at = 1
        passed = found_at is not None
        print(f"{'PASS' if passed else 'FAIL'} {name}: {expectation} "
              f"(expected {len(expected)} move(s), engine {chosen}, depth {found_at})")
        results.append(
            {
                "name": name,
                "fen": fen,
                "expectation": expectation,
                "valid": True,
                "expected_moves": sorted(expected)[:8],
                "engine_move": chosen,
                "found_at_depth": found_at,
                "passed": passed,
            }
        )

    passed = sum(1 for r in results if r["passed"])
    print(f"\n=== SUMMARY: {passed}/{len(results)} tactical diagnostics passed ===")
    payload = {
        "schema": 1,
        "kind": "tactical_diagnostic",
        "binary": str(binary),
        "binary_sha256": None,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "max_depth": args.max_depth,
        "note": "Diagnostic only. This is not a strength measurement and not a rating.",
        "passed": passed,
        "total": len(results),
        "results": results,
    }
    payload["binary_sha256"] = hashlib.sha256(binary.read_bytes()).hexdigest()
    (out / "results.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with (out / "results.jsonl").open("w", encoding="utf-8") as handle:
        for record in results:
            handle.write(json.dumps(record) + "\n")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
