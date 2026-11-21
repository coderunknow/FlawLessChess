#!/usr/bin/env python3
"""TT stress probe: one engine process, a small hash, and many searches in sequence, so the table is
shared across positions and collisions occur. Every `bestmove` must be a legal move in python-chess,
and the first move of the deepest `info ... pv` line must equal `bestmove`. Random legal positions
from random games. Needs python-chess (pip install chess==1.11.2).

Usage: tt_bestmove_probe.py <engine> <positions> <depth> <seed> [hash_mb]
Exit status 0 when there are no failures.
"""
import os
import random
import sys

import chess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_io import Engine  # noqa: E402

exe = sys.argv[1]
n = int(sys.argv[2])
depth = int(sys.argv[3])
seed = int(sys.argv[4])
hash_mb = int(sys.argv[5]) if len(sys.argv) > 5 else 1
random.seed(seed)


def random_positions(count):
    out = []
    while len(out) < count:
        b = chess.Board()
        for _ in range(random.randint(4, 120)):
            moves = list(b.legal_moves)
            if not moves or b.is_game_over():
                break
            b.push(random.choice(moves))
        if not b.is_game_over():
            out.append(b.fen())
    return out


SEARCH_S = 60.0  # a depth-limited search of these positions takes well under a second
HANDSHAKE_S = 10.0

eng = Engine(exe)
failures = 0
checked = 0
rc = None
try:
    eng.send("uci")
    eng.read_until("uciok", HANDSHAKE_S)
    eng.send(f"setoption name Hash value {hash_mb}")
    eng.send("isready")
    eng.read_until("readyok", HANDSHAKE_S)
    for fen in random_positions(n):
        board = chess.Board(fen)
        legal = {m.uci() for m in board.legal_moves}
        eng.send(f"position fen {fen}")
        eng.send(f"go depth {depth}")
        try:
            lines = eng.read_until("bestmove", SEARCH_S)
        except (TimeoutError, RuntimeError) as e:
            failures += 1
            print("NO RESPONSE", e, "in", fen)
            break
        best = lines[-1].split()[1]
        deepest_pv = None
        for l in lines:
            if l.startswith("info") and " pv " in l:
                deepest_pv = l.split(" pv ", 1)[1].split()
        checked += 1
        if best not in legal:
            failures += 1
            print("ILLEGAL bestmove", best, "in", fen)
        elif deepest_pv and deepest_pv[0] != best:
            failures += 1
            print("PV/bestmove mismatch", best, deepest_pv[:3], "in", fen)
finally:
    rc = eng.close()
print("positions", checked, "hash_mb", hash_mb, "depth", depth, "failures", failures, "exit", rc)
sys.exit(1 if failures or rc != 0 else 0)
