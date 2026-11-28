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


def loss_if_captured_at(board: chess.Board, move: chess.Move) -> int:
    """Like ``material_lost_after``, but only opponent captures AT the move's
    destination count.

    Used to judge whether an escape square is safe for the queen: only the
    queen's own exchange at its destination matters. ``material_lost_after``
    scans opponent captures ANYWHERE on the board, which would taint every
    escape with unrelated material hanging elsewhere.
    """
    perspective = 1 if board.turn == chess.WHITE else -1
    before = material(board) * perspective
    board.push(move)
    worst_reply_outcome = None
    for reply in board.legal_moves:
        if not (board.is_capture(reply) and reply.to_square == move.to_square):
            continue
        board.push(reply)
        outcomes = [material(board) * perspective - before]
        for recapture in board.legal_moves:
            if board.is_capture(recapture) and recapture.to_square == reply.to_square:
                board.push(recapture)
                outcomes.append(material(board) * perspective - before)
                board.pop()
        board.pop()
        # We keep the best of recapturing or not; the opponent picks the reply that hurts most.
        best_for_us = max(outcomes)
        worst_reply_outcome = best_for_us if worst_reply_outcome is None else min(worst_reply_outcome, best_for_us)
    board.pop()
    return int(max(0, -(worst_reply_outcome if worst_reply_outcome is not None else 0)))


def _interpose_squares(board: chess.Board, attacker: chess.Square, victim: chess.Square) -> set[chess.Square]:
    """Squares strictly between a sliding attacker and its victim on the shared line."""
    out: set[chess.Square] = set()
    if not (chess.SQUARE_NAMES[attacker][0] == chess.SQUARE_NAMES[victim][0]
            or chess.SQUARE_NAMES[attacker][1] == chess.SQUARE_NAMES[victim][1]
            or abs(chess.square_file(attacker) - chess.square_file(victim))
            == abs(chess.square_rank(attacker) - chess.square_rank(victim))):
        return out  # not a straight line
    step_file = (chess.square_file(victim) - chess.square_file(attacker))
    step_rank = (chess.square_rank(victim) - chess.square_rank(attacker))
    length = max(abs(step_file), abs(step_rank))
    step_file = (step_file > 0) - (step_file < 0)
    step_rank = (step_rank > 0) - (step_rank < 0)
    sq = attacker
    for _ in range(length - 1):
        sq = chess.square(chess.square_file(sq) + step_file, chess.square_rank(sq) + step_rank)
        if sq != victim:
            out.add(sq)
    return out


def _safe_defense_exists(board: chess.Board, mover: chess.Color, qs: chess.Square,
                         attackers: set[chess.Square], min_loss_cp: int) -> bool:
    """Can a non-queen piece of the mover safely defuse the attack?

    Two mechanical defenses are checked: capturing the attacker, or interposing
    on the attacker-to-queen line (sliding attackers only). A defense counts
    when the move itself keeps the material loss at its destination below
    ``min_loss_cp``. Counter-threats against other targets are out of scope.
    """
    interpose: set[chess.Square] = set()
    for asq in attackers:
        if board.piece_type_at(asq) in (chess.ROOK, chess.BISHOP, chess.QUEEN):
            interpose |= _interpose_squares(board, asq, qs)
    for m in board.legal_moves:
        if m.from_square == qs:
            continue  # queen's own escapes are judged separately
        if m.to_square not in attackers and m.to_square not in interpose:
            continue
        if loss_if_captured_at(board, m) < min_loss_cp:
            return True
    return False


def queen_traps_after(board: chess.Board, move: chess.Move, min_loss_cp: int) -> list[dict]:
    """Quiet-reply queen traps the mover's ``move`` allows ("queen cornered/trapped" class).

    ``material_lost_after`` only sees opponent CAPTURE replies. The studied 2026-11-26 loss
    chain (16...Qh4 17.Rb4 17...Qg5 18.Rg4) was built from QUIET replies that cornered the
    queen before any capture existed, so this detector covers that class: after ``move``,
    some QUIET opponent reply attacks the mover's queen and EVERY legal queen response
    (move away or capture the attacker) still loses the queen at its destination
    (``loss_if_captured_at`` >= ``min_loss_cp``) -- or the queen has no legal response at all.

    Diagnostic only. The rule judges queen-local safety; defensive resources of OTHER pieces
    (recapturing the attacker with a knight, interpositions) are intentionally not considered,
    so flags are candidates for adjudication, not verdicts.
    """
    nb = board.copy()
    nb.push(move)
    mover = not nb.turn
    queens = list(nb.pieces(chess.QUEEN, mover))
    if not queens:
        return []
    attacked_before = {qs: nb.is_attacked_by(not mover, qs) for qs in queens}
    traps: list[dict] = []
    for reply in nb.legal_moves:
        if nb.is_capture(reply) or reply.promotion:
            continue
        reply_san = nb.san(reply)  # SAN must be taken before the push
        nb.push(reply)
        if nb.is_check():
            nb.pop()  # a checking reply adds king obligations this rule cannot adjudicate
            continue
        for qs in queens:
            if attacked_before[qs]:
                continue  # a pre-existing hang is the moved_piece detector's job
            if not nb.is_attacked_by(not mover, qs):
                continue
            escapes = [m for m in nb.legal_moves if m.from_square == qs]
            safe = False
            for escape in escapes:
                if loss_if_captured_at(nb, escape) < min_loss_cp:
                    safe = True
                    break
            if safe:
                continue
            attackers = nb.attackers(not mover, qs)
            if _safe_defense_exists(nb, mover, qs, attackers, min_loss_cp):
                continue
            traps.append({
                "reply": reply_san,
                "square": chess.SQUARE_NAMES[qs],
                "queen_escapes": len(escapes),
                "loss_cp": min_loss_cp,
            })
        nb.pop()
    return traps


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
                        "kind": "moved_piece",
                    })
                for trap in queen_traps_after(board, move, min_loss_cp):
                    out["flagged"].append({
                        "game": rec.get("game_index"),
                        "result": rec.get("result"),
                        "opening": rec.get("opening"),
                        "ply": ply,
                        "fen": board.fen(),
                        "move": uci,
                        "material_lost_cp": trap["loss_cp"],
                        "kind": "queen_trap",
                        "queen_square": trap["square"],
                        "reply": trap["reply"],
                        "queen_escapes": trap["queen_escapes"],
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
