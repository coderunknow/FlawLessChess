#!/usr/bin/env python3
"""PV legality probe: every `info ... pv` line must be a legal line from the root, and the last
PV's first move must equal `bestmove`. Random positions from random games; needs python-chess.

Usage: pv_legality_probe.py <engine> <positions> <depth> <seed>
Exit status 0 when there are no failures.
"""
import subprocess, sys, random, chess
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from probe_io import search_lines  # noqa: E402
exe = sys.argv[1]; n = int(sys.argv[2]); depth = int(sys.argv[3]); seed = int(sys.argv[4])
random.seed(seed)
def positions():
    while True:
        b = chess.Board()
        for _ in range(random.randint(0, 120)):
            mv = list(b.legal_moves)
            if not mv or b.is_game_over(claim_draw=False): break
            b.push(random.choice(mv))
        if not b.is_game_over(claim_draw=False):
            yield b
gen = positions()
bad = 0; checked = 0; pvs = 0
for i in range(n):
    b = next(gen)
    lines = [l.rstrip() for l in search_lines(exe, ["uci", "isready", "position fen %s" % b.fen(),
                                                     "go depth %d" % depth])]
    best = lines[-1].split()[1]
    problems = []
    if best == "0000":
        problems.append("0000 on a position with legal moves")
    elif chess.Move.from_uci(best) not in b.legal_moves:
        problems.append("illegal bestmove %s" % best)
    for l in lines:
        if l.startswith("info") and " pv " in l:
            pv = l.split(" pv ", 1)[1].split()
            pvs += 1
            c = b.copy()
            for k, u in enumerate(pv):
                try:
                    m = chess.Move.from_uci(u)
                except ValueError:
                    problems.append("bad pv token %s" % u); break
                if m not in c.legal_moves:
                    problems.append("illegal pv move %s at ply %d (%s)" % (u, k, l[:60])); break
                c.push(m)
    final_pv = [l for l in lines if l.startswith("info") and " pv " in l]
    if final_pv:
        first = final_pv[-1].split(" pv ", 1)[1].split()[0]
        if first != best:
            problems.append("last PV first move %s != bestmove %s" % (first, best))
    checked += 1
    if problems:
        bad += 1
        print("FAIL", b.fen(), problems[:2], flush=True)
print("positions", checked, "pv lines", pvs, "failures", bad)
sys.exit(1 if bad else 0)
