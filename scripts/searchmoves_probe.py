#!/usr/bin/env python3
"""searchmoves restriction probe: with `go searchmoves <subset>`, `bestmove` and the first move of
every `info ... multipv N ... pv` line must be in the subset (when the subset names a legal move).
Each named move is checked with python-chess. Strict policy (owner decision, 2026-11-22): a list with
no legal move in the position must answer `bestmove 0000` and search nothing (no `info depth` line).
Usage: searchmoves_probe.py <engine> <positions> <seed> [multipv]
Exit status 0 when there are no failures.
"""
import random
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from probe_io import Engine  # noqa: E402
import subprocess
import sys

import chess

exe = sys.argv[1]
n = int(sys.argv[2])
seed = int(sys.argv[3])
mpv = int(sys.argv[4]) if len(sys.argv) > 4 else 3
random.seed(seed)


def random_board():
    b = chess.Board()
    for _ in range(random.randint(0, 80)):
        moves = list(b.legal_moves)
        if not moves or b.is_game_over():
            break
        b.push(random.choice(moves))
    return b


eng = Engine(exe)
try:
    eng.send("uci"); eng.send(f"setoption name MultiPV value {mpv}"); eng.send("isready")
    eng.read_until("readyok", 10)
    fails = []
    checked = 0
    for i in range(n):
        b = random_board()
        legal = list(b.legal_moves)
        if not legal or b.is_game_over():
            continue
        if random.random() < 0.2:
            # Illegal-only list: an empty legal intersection must give 0000 and no search.
            legal_set = {m.uci() for m in legal}
            bogus = [u for u in ("a1a8", "h8h1", "e4e4", "a2a5") if u not in legal_set] or ["e4e4"]
            names = " ".join(bogus[:2])
            eng.send(f"position fen {b.fen()}"); eng.send(f"go depth 3 searchmoves {names}")
            lines = eng.read_until("bestmove", 60)
            checked += 1
            if lines[-1] != "bestmove 0000":
                fails.append(f"illegal-only searchmoves {names} gave {lines[-1]} in {b.fen()}")
            if any(l.startswith("info depth") for l in lines):
                fails.append(f"illegal-only searchmoves {names} searched in {b.fen()}")
            continue
        k = random.randint(1, min(4, len(legal)))
        subset = random.sample(legal, k)
        names = " ".join(m.uci() for m in subset)
        eng.send(f"position fen {b.fen()}"); eng.send(f"go depth 3 searchmoves {names}")
        lines = eng.read_until("bestmove", 60)  # raises on a stalled engine (F-37)
        checked += 1
        best = lines[-1].split()[1]
        allowed = {m.uci() for m in subset}
        if best not in allowed:
            fails.append(f"bestmove {best} outside searchmoves {names} in {b.fen()}")
        for l in lines:
            if l.startswith("info depth") and " multipv " in l and " pv " in l:
                first = l.split(" pv ", 1)[1].split()[0]
                if first not in allowed and l.split(" multipv ")[1].split()[0] == "1":
                    fails.append(f"PV root {first} outside searchmoves {names}: {l[:80]}")
finally:
    rc = eng.close()
print(f"positions {checked} multipv {mpv} failures {len(fails)}")
for f in fails[:10]:
    print("FAIL", f)
sys.exit(1 if fails or rc != 0 else 0)
