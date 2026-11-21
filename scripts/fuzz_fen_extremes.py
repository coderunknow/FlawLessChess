#!/usr/bin/env python3
"""FEN extremes fuzz (F-29 class): mutated FENs sent to the engine as `position fen` + `go depth 1`.

Fields are pushed to their extremes (counters at the top of their range, castling and en passant
combinations that do not match the board, sparse and dense placements). For each FEN the engine must
(a) stay alive, (b) either answer `bestmove` or refuse the position with an `info string position error`
notice, and (c) print nothing to stderr containing "panicked". A debug build also checks overflow.
Each FEN that python-chess deems valid must get a legal bestmove (python-chess is the oracle).

Usage: FLAWLESS_ENGINE=./target/debug/flawless fuzz_fen_extremes.py <seed> <cases>
Exit status 0 when there are no failures.
"""
import os
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from probe_io import Engine  # noqa: E402
import random
import subprocess
import sys

import chess

EXE = os.environ.get("FLAWLESS_ENGINE", "./target/release/flawless")
seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
cases = int(sys.argv[2]) if len(sys.argv) > 2 else 200
random.seed(seed)

HALF = ["0", "1", "49", "50", "99", "100", "101", "149", "150", "32767", "65534", "65535", "65536", "-1", "x"]
FULL = ["1", "2", "99", "4294967294", "4294967295", "4294967296", "0", "-1", "abc"]
CASTLE = ["-", "K", "Q", "k", "q", "KQ", "kq", "KQkq", "KK", "Qq", "Kkq", "X"]
EP = ["-", "a3", "e3", "e6", "h6", "a6", "d6", "d3", "a1", "z9", "-"]


def random_board():
    b = chess.Board(None)
    squares = random.sample(range(64), random.randint(2, 32))
    b.set_piece_at(squares[0], chess.Piece(chess.KING, chess.WHITE))
    b.set_piece_at(squares[1], chess.Piece(chess.KING, chess.BLACK))
    kinds = [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN]
    for s in squares[2:]:
        r = random.randrange(0, 8)
        if r == 0:
            s2 = s
            # pawns never on the back ranks
            if s2 // 8 in (0, 7):
                continue
            b.set_piece_at(s2, chess.Piece(chess.PAWN, random.choice([chess.WHITE, chess.BLACK])))
        else:
            b.set_piece_at(s, chess.Piece(random.choice(kinds), random.choice([chess.WHITE, chess.BLACK])))
    return b


def mutate(fen):
    f = fen.split()
    if len(f) < 4:
        return fen
    if random.random() < 0.5:
        f[1] = random.choice(["w", "b", "W", "x"]) if random.random() < 0.2 else f[1]
    if random.random() < 0.5:
        f[2] = random.choice(CASTLE)
    if random.random() < 0.5:
        f[3] = random.choice(EP)
    if len(f) >= 5 and random.random() < 0.6:
        f[4] = random.choice(HALF)
    if len(f) >= 6 and random.random() < 0.6:
        f[5] = random.choice(FULL)
    return " ".join(f)


def make_fens(n):
    out = []
    while len(out) < n:
        b = random_board()
        if random.random() < 0.3:
            b.turn = random.choice([chess.WHITE, chess.BLACK])
        fen = b.fen()
        out.append(mutate(fen))
    return out


def in_engine_domain(fen):
    # The engine stores the clocks as u16 (halfmove) and u32 (fullmove); larger values are refused
    # with a notice by design, so they are outside the oracle comparison.
    f = fen.split()
    try:
        if len(f) >= 5 and not 0 <= int(f[4]) <= 65535:
            return False
        if len(f) >= 6 and not 0 <= int(f[5]) <= 4294967295:
            return False
    except ValueError:
        return False
    return True


def oracle_valid(fen):
    try:
        b = chess.Board(fen)
    except ValueError:
        return False
    # python-chess does not check promotion counts against missing pawns; the engine does (FIDE
    # reachability), so such positions are not "valid" for this comparison.
    return b.is_valid() and not b.is_game_over() and reachable_material(b)


def reachable_material(b):
    for color in (chess.WHITE, chess.BLACK):
        pawns = len(b.pieces(chess.PAWN, color))
        missing = 8 - pawns
        extra = 0
        starts = {chess.KNIGHT: 2, chess.BISHOP: 2, chess.ROOK: 2, chess.QUEEN: 1}
        for t, n in starts.items():
            extra += max(0, len(b.pieces(t, color)) - n)
        if extra > missing:
            return False
    return True


def start():
    eng = Engine(EXE)
    try:
        eng.send("uci")
        eng.read_until("uciok", 10)
    except BaseException:
        eng.close()
        raise
    return eng


fails = []
fens = make_fens(cases)
p = start()
trace = os.environ.get("FEN_FUZZ_TRACE")
for i, fen in enumerate(fens):
    if trace:
        with open(trace, "w") as tf:
            tf.write(f"{i} {fen}\n")
    p.send(f"position fen {fen}")
    p.send("go depth 1")
    try:
        lines = p.read_until("bestmove", 60)  # a stalled engine is a failure, not a hang (F-37)
    except TimeoutError as e:
        # A stalled engine ends the run as a failure (restarting it would wait 60 s per position).
        fails.append(("no bestmove: " + str(e)[:120], fen, None))
        break
    except RuntimeError as e:
        # The process ended (crash or closed stdout): record it and continue with a fresh engine.
        fails.append(("no bestmove (" + str(e)[:80] + ")", fen, p.p.poll()))
        p.close()
        p = start()
        continue
    best = lines[-1].split()[1]
    refused = any(l.startswith("info string position error") for l in lines)
    if not in_engine_domain(fen):
        continue
    valid = oracle_valid(fen)
    if refused:
        if valid:
            fails.append(("engine refused a position python-chess accepts", fen, lines[:2]))
        continue
    if best == "0000":
        # checkmated or stalemated roots are the only legal answer for 0000
        if valid and list(chess.Board(fen).legal_moves):
            fails.append(("bestmove 0000 with legal moves", fen, best))
        continue
    if valid:
        if chess.Move.from_uci(best) not in chess.Board(fen).legal_moves:
            fails.append(("illegal bestmove", fen, best))
# stderr panic check after quit (close() waits for the process and its stderr to finish)
rc = p.close()
if rc != 0:
    fails.append(("engine exit status after quit", "-", rc))
err = p.stderr_text()
if "panicked" in err:
    fails.append(("panic on stderr", "-", err[:300]))
for f in fails[:20]:
    print("FAIL", f)
print(f"seed={seed} cases={cases} failures={len(fails)}")
sys.exit(1 if fails else 0)
