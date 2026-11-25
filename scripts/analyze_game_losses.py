#!/usr/bin/env python3
"""Blame-assignment scan over recorded match games (diagnostic, not evidence).

Replays every recorded game in an evidence ``games.jsonl`` and flags the plies where the focus
engine's move let the ACTUAL opponent reply win material (same quiet-reply rule as
``diagnose_weaknesses.py``). Used to mine real 40/15 anchor games for defect patterns; outputs are
diagnostic only and never strength evidence.

Usage:
    scripts/analyze_game_losses.py benches/evidence/screening-3/akimbo-0.1.1/games.jsonl \
        [--focus flawless] [--min-loss-cp 150] [--out /tmp/blunder-scan.json]
"""

from __future__ import annotations

import argparse
import json
import sys

import chess

PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}


def material(board: chess.Board) -> int:
    total = 0
    for piece_type, value in PIECE_VALUES.items():
        total += value * (len(board.pieces(piece_type, chess.WHITE)) - len(board.pieces(piece_type, chess.BLACK)))
    return total


def material_lost_after(board: chess.Board, move: chess.Move) -> int:
    """Material the mover gives away across the exchange, in centipawns (0 = nothing lost).

    Simulates the mover's move, every opponent capture reply, and the mover's best recapture,
    and reports the worst net material swing against the mover. Wins the mover made on his own
    move (e.g. a queen trade) net out correctly.
    """
    perspective = 1 if board.turn == chess.WHITE else -1
    before = material(board) * perspective
    board.push(move)
    worst_reply_outcome = None
    for reply in board.legal_moves:
        if not board.is_capture(reply):
            continue
        board.push(reply)
        outcomes = [material(board) * perspective - before]
        for recapture in board.legal_moves:
            if not (board.is_capture(recapture) and recapture.to_square == reply.to_square):
                continue
            board.push(recapture)
            outcomes.append(material(board) * perspective - before)
            board.pop()
        board.pop()
        # We keep the best of recapturing or not; the opponent picks the reply that hurts most.
        best_for_us = max(outcomes)
        worst_reply_outcome = best_for_us if worst_reply_outcome is None else min(worst_reply_outcome, best_for_us)
    board.pop()
    return int(max(0, -(worst_reply_outcome if worst_reply_outcome is not None else 0)))


def scan(path: str, focus: str, min_loss_cp: int) -> dict:
    records = []
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            if raw.strip():
                records.append(json.loads(raw))
    focus = focus.casefold()
    out = {"source": path, "games": len(records), "flagged": []}
    for rec in records:
        board = chess.Board()
        moves = rec.get("moves") or []
        if isinstance(moves, str):
            moves = json.loads(moves.replace("'", '"'))
        is_focus_white = str(rec.get("white", "")).casefold() == focus
        for ply, uci in enumerate(moves):
            move = chess.Move.from_uci(uci)
            if move not in board.legal_moves:
                out["flagged"].append({
                    "game": rec.get("game_index"), "ply": ply, "error": f"illegal move {uci}",
                    "fen": board.fen(),
                })
                break
            mover_is_focus = (board.turn == chess.WHITE) == is_focus_white
            if mover_is_focus:
                lost = material_lost_after(board, move)
                if lost >= min_loss_cp:
                    out["flagged"].append({
                        "game": rec.get("game_index"),
                        "result": rec.get("result"),
                        "opening": rec.get("opening"),
                        "ply": ply,
                        "fen": board.fen(),
                        "move": uci,
                        "material_lost_cp": lost,
                    })
            board.push(move)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("games_jsonl")
    parser.add_argument("--focus", default="flawless")
    parser.add_argument("--min-loss-cp", type=int, default=150)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    result = scan(args.games_jsonl, args.focus, args.min_loss_cp)
    text = json.dumps(result, indent=1)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    print(f"{args.games_jsonl}: {result['games']} games, {len(result['flagged'])} flagged plies")
    return 0


if __name__ == "__main__":
    sys.exit(main())
