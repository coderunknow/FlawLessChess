#!/usr/bin/env python3
"""perft_random_differential.py — engine perft vs python-chess on random reachable positions.

Audit tool (test-only; python-chess is GPL-3.0+ and is never linked into the engine).
For each seed, plays random legal games with python-chess, samples positions along the way
(including positions with en passant, castling and promotion potential), and compares
`flawless perft D <fen>` with python-chess perft at depths 1..D. Any mismatch is printed with
the FEN and the depth, and the script exits 1.

Usage:
    FLAWLESS_ENGINE=./target/release/flawless python3 scripts/perft_random_differential.py <seed> <games> [depth]

Default depth is 3 (python-chess perft(3) is fast enough for thousands of positions).
"""
from __future__ import annotations

import os
import random
import subprocess
import sys

import chess

ENGINE = os.environ.get("FLAWLESS_ENGINE", "./target/release/flawless")


def oracle_perft(board: chess.Board, depth: int) -> int:
    if depth == 0:
        return 1
    if depth == 1:
        return board.legal_moves.count()
    total = 0
    for m in list(board.legal_moves):
        board.push(m)
        total += oracle_perft(board, depth - 1)
        board.pop()
    return total


def engine_perft(fen: str, depth: int) -> int:
    out = subprocess.run(
        [ENGINE, "perft", str(depth), fen],
        capture_output=True, text=True, timeout=120, check=False,
    )
    if out.returncode != 0:
        raise RuntimeError(f"engine rc={out.returncode} on {fen!r}: {out.stderr[:200]}")
    for line in out.stdout.splitlines():
        if line.startswith("perft("):
            return int(line.rsplit("=", 1)[1].split()[0])
    raise RuntimeError(f"no perft line for {fen!r}: {out.stdout[:200]!r}")


def main() -> int:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    games = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    depth = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    rnd = random.Random(seed)
    positions = 0
    checks = 0
    failures = 0
    for g in range(games):
        board = chess.Board()
        for ply in range(rnd.randint(4, 140)):
            if board.is_game_over(claim_draw=True):
                break
            moves = list(board.legal_moves)
            board.push(rnd.choice(moves))
            if rnd.random() < 0.25 or board.has_legal_en_passant():
                positions += 1
                fen = board.fen()
                for d in range(1, depth + 1):
                    expect = oracle_perft(board.copy(), d)
                    got = engine_perft(fen, d)
                    checks += 1
                    if got != expect:
                        failures += 1
                        print(f"MISMATCH seed={seed} game={g} ply={ply} depth={d} "
                              f"engine={got} oracle={expect} fen={fen}")
    print(f"seed={seed} games={games} positions={positions} checks={checks} failures={failures}")
    print("RESULT PASS" if failures == 0 else "RESULT FAIL")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
