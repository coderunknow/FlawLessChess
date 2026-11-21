"""MultiPV probe: with MultiPV k, the engine prints min(k, legal) lines numbered 1..n, scores
non-increasing, distinct first moves, legal PVs, and `multipv 1` first move equal to `bestmove`.

Usage: multipv_probe.py <engine> <positions> <seed> <k>
"""
import subprocess, sys, random, chess, re
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from probe_io import search_lines  # noqa: E402
exe = sys.argv[1]; n = int(sys.argv[2]); seed = int(sys.argv[3]); k = int(sys.argv[4])
random.seed(seed)
fails = 0; total = 0
for t in range(n):
    b = chess.Board()
    for _ in range(random.randint(0, 80)):
        mv = list(b.legal_moves)
        if not mv or b.is_game_over(claim_draw=False): break
        b.push(random.choice(mv))
    if b.is_game_over(claim_draw=False): continue
    lines = [l.rstrip() for l in search_lines(exe, ["uci", "isready", "setoption name MultiPV value %d" % k,
                                                     "position fen %s" % b.fen(), "go depth 4"])]
    total += 1
    bm = lines[-1].split()[1]
    last_depth = max(int(l.split()[2]) for l in lines if l.startswith("info depth"))
    final = {}
    for l in lines:
        if l.startswith("info depth %d " % last_depth) and " multipv " in l:
            mpv = int(l.split(" multipv ")[1].split()[0])
            sc = re.search(r" score (cp|mate) (-?\d+)", l)
            pv = l.split(" pv ")[1].split()
            if sc.group(1) == "cp":
                value = int(sc.group(2))
            else:
                n = int(sc.group(2))  # mate N: N>0 mates in N, N<0 is mated in |N|
                value = (100000 - n) if n > 0 else -(100000 + n)
            final[mpv] = (value, pv)
    legal_moves = set(m.uci() for m in b.legal_moves)
    problems = []
    expected = min(k, len(legal_moves))
    if len(final) != expected: problems.append("lines %d != %d" % (len(final), expected))
    if sorted(final) != list(range(1, len(final) + 1)): problems.append("multipv numbering %s" % sorted(final))
    if final:
        scores = [final[i][0] for i in sorted(final)]
        if any(scores[i] < scores[i+1] for i in range(len(scores)-1)): problems.append("scores not descending %s" % scores)
        firsts = [final[i][1][0] for i in sorted(final)]
        if len(set(firsts)) != len(firsts): problems.append("duplicate PV first moves")
        if final[1][1][0] != bm: problems.append("multipv 1 first %s != bestmove %s" % (final[1][1][0], bm))
        for i, (sc, pv) in final.items():
            c = b.copy()
            for u in pv:
                m = chess.Move.from_uci(u)
                if m not in c.legal_moves: problems.append("illegal pv %s line %d" % (u, i)); break
                c.push(m)
    if problems:
        fails += 1
        if fails <= 5: print("FAIL", b.fen(), problems[:2], flush=True)
print("positions", total, "multipv", k, "failures", fails)
sys.exit(1 if fails else 0)
