#!/usr/bin/env python3
"""Mate-distance probe (F-41): the engine's `score mate N` must equal the minimal mate that
python-chess proves, for mates in 1 and 2 (side to move = White in every generated position).

Positions are random sparse endgames (White K + 1-2 heavy pieces, Black K, sometimes one Black rook
or queen). For each position with a proven mate in 1 or 2, the engine searches `go depth 6` and the
last `info depth 6` score must be `mate N` with the same N. Positions with no mate in 2 are skipped.
Every engine wait has a deadline (scripts/probe_io.py); a stalled engine fails the run.

usage: mate_distance_probe.py <engine> <seed> <positions-with-mate> [--depth 6]
exit 0 = all agree; 1 = a disagreement or a stalled/crashed engine.
Requires python-chess (use the venv: /home/user/.venv/bin/python3).
"""
import os
import random
import sys

import chess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_io import Engine  # noqa: E402


def mate_distance(board):
    """Minimal mate distance for the side to move: 1, 2, or None (no mate in 2 proven)."""
    for m in board.legal_moves:
        board.push(m)
        mated = board.is_checkmate()
        board.pop()
        if mated:
            return 1
    for m in board.legal_moves:
        board.push(m)
        good = bool(list(board.legal_moves))
        for r in list(board.legal_moves):
            board.push(r)
            answered = False
            for x in list(board.legal_moves):
                board.push(x)
                answered = board.is_checkmate()
                board.pop()
                if answered:
                    break
            board.pop()
            if not answered:
                good = False
                break
        board.pop()
        if good:
            return 2
    return None


def random_endgame(rng):
    while True:
        board = chess.Board(None)
        wk, bk = rng.sample(chess.SQUARES, 2)
        if chess.square_distance(wk, bk) <= 1:
            continue
        board.set_piece_at(wk, chess.Piece(chess.KING, chess.WHITE))
        board.set_piece_at(bk, chess.Piece(chess.KING, chess.BLACK))
        for _ in range(rng.choice([1, 1, 2])):
            sq = rng.choice(chess.SQUARES)
            if board.piece_at(sq) is None:
                kind = rng.choice([chess.QUEEN, chess.ROOK, chess.ROOK, chess.BISHOP, chess.KNIGHT])
                board.set_piece_at(sq, chess.Piece(kind, chess.WHITE))
        if rng.random() < 0.3:
            sq = rng.choice(chess.SQUARES)
            if board.piece_at(sq) is None and chess.square_rank(sq) not in (0, 7):
                board.set_piece_at(sq, chess.Piece(rng.choice([chess.ROOK, chess.QUEEN]), chess.BLACK))
        board.turn = chess.WHITE
        if board.is_valid() and not board.is_game_over():
            return board


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    exe, seed, wanted = argv[0], int(argv[1]), int(argv[2])
    depth = int(argv[argv.index("--depth") + 1]) if "--depth" in argv else 6
    rng = random.Random(seed)
    checked = {1: 0, 2: 0}
    failures = []
    tries = 0
    eng = Engine(exe)
    try:
        eng.send("uci")
        eng.read_until("uciok", 10)
        eng.send("isready")
        eng.read_until("readyok", 10)
        while sum(checked.values()) < wanted and tries < wanted * 80:
            tries += 1
            board = random_endgame(rng)
            d = mate_distance(board)
            if d is None:
                continue
            eng.send("position fen " + board.fen())
            eng.send(f"go depth {depth}")
            lines = eng.read_until("bestmove", 60)  # raises on a stalled engine
            info = [l for l in lines if l.startswith(f"info depth {depth} ")]
            parts = info[-1].split(" score ")[1].split() if info else []
            checked[d] += 1
            if parts[:1] != ["mate"] or parts[1:2] != [str(d)]:
                failures.append((board.fen(), d, parts[:2]))
    except TimeoutError as e:
        failures.append(("engine stalled", str(e)[:120], None))
    finally:
        rc = eng.close()
    if sum(checked.values()) < wanted:
        failures.append(("incomplete sample", sum(checked.values()), wanted))
    print(f"seed={seed} depth={depth} mate1={checked[1]} mate2={checked[2]} tries={tries} failures={len(failures)} exit={rc}")
    for f in failures[:10]:
        print("FAIL", f)
    return 0 if not failures and rc == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
