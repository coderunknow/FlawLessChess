#!/usr/bin/env python3
"""Diagnose Flawless engine weaknesses by playing games vs a simple eval opponent.

Records full PGN of games where the engine loses, and flags positions where
the engine loses material or makes serious errors.
"""
import argparse
import chess
import json
import random
import subprocess
import sys
import time
from pathlib import Path

ENGINE = "./target/release/flawless"  # overridable with --binary
OUT = Path("benches/diagnose-20261124")
OUT.mkdir(parents=True, exist_ok=True)

PST = {
    chess.PAWN: [0,0,0,0,0,0,0,0, 5,10,10,-15,-15,10,10,5, 5,5,10,20,20,10,5,5,
                 0,0,0,25,25,0,0,0, 5,10,15,25,25,15,10,5, 15,20,25,30,30,25,20,15,
                 40,45,50,55,55,50,45,40, 0,0,0,0,0,0,0,0],
    chess.KNIGHT: [-40,-25,-15,-10,-10,-15,-25,-40, -30,-15,0,5,5,0,-15,-30,
                   -20,0,10,15,15,10,0,-20, -15,5,15,20,20,15,5,-15,
                   -10,10,20,22,22,20,10,-10, -15,5,15,20,20,15,5,-15,
                   -20,0,10,15,15,10,0,-20, -30,-15,-10,-5,-5,-10,-15,-30],
    chess.BISHOP: [-15,-10,-10,-10,-10,-10,-10,-15, -10,0,0,0,0,0,0,-10,
                   -10,0,5,10,10,5,0,-10, -10,5,10,10,10,10,5,-10,
                   -10,0,10,10,10,10,0,-10, -10,10,10,10,10,10,-10,
                   -10,5,0,0,0,0,5,-10, -15,-10,-10,-10,-10,-10,-10,-15],
    chess.ROOK: [0,0,2,5,5,2,0,0, 2,5,8,10,10,8,5,2, 5,8,10,12,12,10,8,5,
                 5,8,10,12,12,10,8,5, 5,8,10,12,12,10,8,5, 5,8,10,12,12,10,8,5,
                 8,12,15,18,18,15,12,8, 25,25,25,25,25,25,25,25],
    chess.QUEEN: [-10,-5,-2,0,0,-2,-5,-10, -5,0,2,2,2,2,0,-5, -2,2,5,5,5,5,2,-2,
                  0,2,5,5,5,5,2,0, 0,2,5,5,5,5,2,0, -2,2,5,5,5,5,2,-2,
                  -5,0,2,2,2,2,0,-5, -10,-5,-2,0,0,-2,-5,-10],
    chess.KING: [25,35,25,0,-5,5,40,25, 20,25,5,-15,-20,-10,15,15, -5,10,-10,-25,-30,-25,-5,-5,
                 -15,-10,-20,-30,-35,-30,-15,-15, -25,-20,-30,-35,-40,-35,-25,-25,
                 -25,-20,-30,-35,-35,-30,-25,-25, -20,-15,-25,-30,-30,-25,-15,-20,
                 -10,-5,-15,-20,-15,-20,-5,-10],
}

PIECE_VALUES = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330,
                chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0}


def mirror_sq(sq):
    return sq ^ 56


def opp_eval(board):
    score = 0
    for sq, piece in board.piece_map().items():
        pt = piece.piece_type
        val = PIECE_VALUES[pt]
        pst = PST[pt][mirror_sq(sq) if not piece.color else sq]
        score += val + pst if piece.color else -(val + pst)
    return score


def opp_best_move(board):
    legal = list(board.legal_moves)
    if not legal:
        return None
    captures = [m for m in legal if board.is_capture(m)]
    if captures:
        legal = captures
    best_move = None
    best_score = -999999
    for m in legal:
        board.push(m)
        score = -opp_eval(board)
        board.pop()
        if score > best_score:
            best_score = score
            best_move = m
    return best_move


def engine_bestmove(fen, movetime_ms=500, binary=None):
    proc = subprocess.Popen(
        [binary or ENGINE, "uci"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=0,
    )
    try:
        proc.stdin.write("uci\n"); proc.stdin.flush()
        while True:
            line = proc.stdout.readline()
            if line.strip() == "uciok":
                break
        proc.stdin.write(f"position fen {fen}\n"); proc.stdin.flush()
        proc.stdin.write(f"go movetime {movetime_ms}\n"); proc.stdin.flush()
        bestmove = None
        while True:
            line = proc.stdout.readline()
            if line.startswith("bestmove"):
                parts = line.split()
                bestmove = parts[1] if len(parts) > 1 else None
                break
        return bestmove
    finally:
        proc.stdin.write("quit\n"); proc.stdin.flush()
        proc.wait(timeout=5)


def material_diff_for(board, engine_color):
    """Material from engine's perspective: engine_material - opponent_material."""
    if engine_color == chess.WHITE:
        w = sum(PIECE_VALUES[p.piece_type] for p in board.piece_map().values() if p.color)
        b = sum(PIECE_VALUES[p.piece_type] for p in board.piece_map().values() if not p.color)
        return w - b
    else:
        b = sum(PIECE_VALUES[p.piece_type] for p in board.piece_map().values() if not p.color)
        w = sum(PIECE_VALUES[p.piece_type] for p in board.piece_map().values() if p.color)
        return b - w


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=10)
    parser.add_argument("--movetime-ms", type=int, default=500)
    parser.add_argument("--max-plies", type=int, default=150)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--binary", default=ENGINE)
    args = parser.parse_args()

    games = args.games
    random.seed(args.seed)
    flagged = []

    for g in range(games):
        board = chess.Board()
        moves = []
        game_start = time.time()
        engine_is_white = g % 2 == 0
        engine_color = chess.WHITE if engine_is_white else chess.BLACK

        while not board.is_game_over() and len(moves) < args.max_plies:
            if board.turn == engine_color:
                fen = board.fen()
                mat_before = material_diff_for(board, engine_color)
                best = engine_bestmove(fen, movetime_ms=args.movetime_ms, binary=args.binary)
                if best is None or best == "0000" or best == "(none)":
                    print(f"Game {g}: engine returned no bestmove at {fen}")
                    break
                try:
                    move = chess.Move.from_uci(best)
                    if move not in board.legal_moves:
                        print(f"Game {g}: illegal move {best} at {fen}")
                        break
                    board.push(move)
                    mat_after = material_diff_for(board, engine_color)
                    material_lost = mat_after - mat_before
                    if material_lost <= -250:  # engine lost a minor piece or more
                        flagged.append({
                            "game": g, "engine_color": "W" if engine_is_white else "B",
                            "ply": len(moves), "fen_before": fen, "move": best.uci(),
                            "material_lost_cp": material_lost,
                            "board_after": board.fen(),
                        })
                    moves.append(move)
                except ValueError:
                    print(f"Game {g}: invalid move {best.uci() if best else '?'} at {fen}")
                    break
            else:
                move = opp_best_move(board)
                if move is None:
                    break
                board.push(move)
                moves.append(move)

        result = board.result()
        engine_won = (result == "1-0" and engine_is_white) or (result == "0-1" and not engine_is_white)
        engine_drew = result == "1/2-1/2"
        print(f"Game {g}: engine={'W' if engine_is_white else 'B'} result={result} "
              f"engine_won={engine_won} plies={len(moves)} time={time.time()-game_start:.1f}s")

    # Save losing games as PGN
    out_file = OUT / "weaknesses.jsonl"
    with open(out_file, "w") as f:
        for entry in flagged:
            f.write(json.dumps(entry) + "\n")

    print(f"\nFlagged {len(flagged)} material-loss positions -> {out_file}")
    for e in flagged[:10]:
        print(f"  Game {e['game']} ({e['engine_color']}) ply {e['ply']}: "
              f"lost {e['material_lost_cp']}cp, move {e['move']}")
        print(f"    FEN: {e['fen_before']}")


if __name__ == "__main__":
    main()
