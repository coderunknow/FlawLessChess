#!/usr/bin/env python3
"""Negative-mate probe: positions where the side to move is forced into mate by its opponent's next move
(mated in one full move, UCI `score mate -1`). For each, the engine must print `score mate -1` at its
deepest line and a legal bestmove. Convention checked against a constructed position (see ledger): the
UCI mate count is in full moves of the side to move, so a forced mate after the opponent's next move is
`mate -1`. Usage: negative_mate_probe.py <engine> <positions> <seed>. Exit 0 when there are no failures.
"""
import random
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from probe_io import Engine  # noqa: E402
import subprocess
import sys

import chess

exe, n, seed = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
random.seed(seed)


def mated_in_one_move(b):
    """True when the side to move has legal moves and every one of them allows a mate in one."""
    replies = list(b.legal_moves)
    if not replies:
        return False
    for m in replies:
        b.push(m)
        mate = any(_mates_now(b, x) for x in list(b.legal_moves))
        b.pop()
        if not mate:
            return False
    return True


def _mates_now(b, x):
    b.push(x)
    res = b.is_checkmate()
    b.pop()
    return res


def find_positions(count):
    found = []
    tries = 0
    while len(found) < count and tries < 400000:
        tries += 1
        b = chess.Board()
        for _ in range(random.randint(0, 80)):
            mv = list(b.legal_moves)
            if not mv or b.is_game_over(claim_draw=False):
                break
            b.push(random.choice(mv))
        if b.is_game_over(claim_draw=False):
            continue
        if mated_in_one_move(b.copy()):
            found.append(b.fen())
    return found, tries


positions, tries = find_positions(n)
print(f"constructed {len(positions)} positions, side to move mated in one move (tries {tries})")
if not positions:
    print("no positions constructed; this probe has no result")
    sys.exit(2)
eng = Engine(exe)
try:
    eng.send("uci"); eng.send("isready"); eng.read_until("readyok", 10)
    fails = 0
    for fen in positions:
        b = chess.Board(fen)
        eng.send(f"position fen {fen}"); eng.send("go depth 6")
        lines = [l.rstrip() for l in eng.read_until("bestmove", 60)]  # raises on a stalled engine (F-37)
        bm = lines[-1].split()[1]
        scores = [l for l in lines if l.startswith("info depth") and " score " in l]
        last = scores[-1] if scores else ""
        problems = []
        if " score mate -1" not in last:
            problems.append("expected 'score mate -1', got: " + (last.split(" score ")[1][:20] if last else "none"))
        try:
            mv = chess.Move.from_uci(bm)
            if mv not in b.legal_moves: problems.append(f"illegal bestmove {bm}")
        except ValueError:
            problems.append(f"bad bestmove {bm}")
        if problems:
            fails += 1
            print("FAIL", fen, problems)
finally:
    rc = eng.close()
print(f"positions {len(positions)} failures {fails}")
sys.exit(1 if fails or rc != 0 else 0)
