#!/usr/bin/env python3
"""Clock-through-a-game probe: the engine plays both sides of a game with running clocks.

Each move is sent as `go wtime W btime B winc I binc I` (and `movestogo` when set). The probe measures
the wall time from the `go` line to `bestmove` and deducts it from the side that moved. A flag is a
remaining clock <= 0 AFTER that deduction and BEFORE the increment is added (audit finding F-37: the
increment used to be added first, so a move that overran the clock by less than the increment passed,
and whole-millisecond truncation hid fractions). Engine replies have a deadline; a stalled engine is a
failure. Only the GUI-visible contract is checked: the engine, the clocks, and the legality of each move
(python-chess). Requires python-chess.

Usage: selfplay_clock_probe.py <engine> <base_ms> <inc_ms> [plies] [movestogo]
Exit status 0 when no clock flags, no illegal moves, no missing replies, and a clean engine exit.
"""
import os
import sys
import time

import chess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_io import Engine  # noqa: E402

RESPONSE_S = 60.0  # longest acceptable wait for one move (the clock bounds real moves far below this)
HANDSHAKE_S = 10.0

exe = sys.argv[1]
base = int(sys.argv[2])
inc = int(sys.argv[3])
plies = int(sys.argv[4]) if len(sys.argv) > 4 else 150
mtg = int(sys.argv[5]) if len(sys.argv) > 5 else None

board = chess.Board()
clock = {chess.WHITE: float(base), chess.BLACK: float(base)}
min_left = {chess.WHITE: float(base), chess.BLACK: float(base)}  # remaining before the increment
total_think = 0.0
failures = []
rc = None
eng = Engine(exe)
try:
    eng.send("uci")
    eng.read_until("uciok", HANDSHAKE_S)
    eng.send("isready")
    eng.read_until("readyok", HANDSHAKE_S)
    eng.send("ucinewgame")
    ply = -1
    for ply in range(plies):
        if board.is_game_over():
            break
        side = board.turn
        cmd = (f"position fen {board.fen()}\n"
               f"go wtime {int(clock[chess.WHITE])} btime {int(clock[chess.BLACK])} winc {inc} binc {inc}")
        if mtg:
            cmd += f" movestogo {mtg}"
        t0 = time.monotonic()
        eng.send(cmd)
        try:
            lines = eng.read_until("bestmove", RESPONSE_S)
        except (TimeoutError, RuntimeError) as e:
            failures.append(f"ply {ply}: {e}")
            break
        spent = (time.monotonic() - t0) * 1000.0
        total_think += spent
        best = lines[-1].split()[1]
        if best == "0000" or chess.Move.from_uci(best) not in board.legal_moves:
            failures.append(f"ply {ply}: illegal bestmove {best} in {board.fen()}")
            break
        clock[side] -= spent                      # measured, not truncated
        min_left[side] = min(min_left[side], clock[side])
        if clock[side] <= 0:                      # flag check BEFORE the increment (F-37)
            failures.append(f"ply {ply}: {'white' if side else 'black'} flagged ({clock[side]:.1f} ms)")
            break
        clock[side] += inc
        board.push(chess.Move.from_uci(best))
    plies_played = ply + 1
finally:
    rc = eng.close()

if rc != 0:
    failures.append(f"engine exit status {rc}")
print(f"plies {plies_played} base {base} inc {inc} mtg {mtg} think {total_think / 1000:.2f}s "
      f"left W {clock[chess.WHITE]:.0f} B {clock[chess.BLACK]:.0f} "
      f"min W {min_left[chess.WHITE]:.0f} min B {min_left[chess.BLACK]:.0f} failures {len(failures)}")
for f in failures:
    print("FAIL", f)
sys.exit(1 if failures else 0)
