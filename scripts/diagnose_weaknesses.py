#!/usr/bin/env python3
"""Diagnose Flawless engine weaknesses by playing games against a simple opponent.

**Diagnostic output, not strength evidence.** The opponent is a greedy evaluation opponent, so the
games say nothing about playing strength against a real opponent. What the script looks for is
*blunders*: positions where the engine gives away material.

The opponent uses the engine's own piece-square tables, read from `src/eval.rs` at run time, so the
opponent cannot drift away from the engine it is supposed to resemble.

Outputs (in the output directory):
* `weaknesses.jsonl` — one record per position where the engine lost material after the opponent's
  reply. Quiet replies are never flagged.
* `losing-games.pgn` — the full games the engine lost.
* `summary.json` — the run summary.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import time
from pathlib import Path

import chess
import chess.pgn

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE = "./target/release/flawless"  # overridable with --binary
OUT = Path("benches/diagnose-20261124")

PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}

# The engine source that holds the piece-square tables.
EVAL_SOURCE = REPO_ROOT / "src" / "eval.rs"


class EngineError(RuntimeError):
    """The engine process failed in a way that makes the diagnostic meaningless."""


def load_pst_from_source(path: Path) -> dict[int, list[int]]:
    """Read the middlegame piece-square tables from the engine source.

    Reading them from the source is deliberate: a copy of the tables in this script can drift from
    the engine (a short table raises IndexError only for the squares past the end, which is exactly
    the kind of defect that hides in a diagnostic).
    """
    if not path.is_file():
        raise SystemExit(f"engine source not found: {path}")
    text = path.read_text(encoding="utf-8")
    names = {
        "PAWN": chess.PAWN,
        "KNIGHT": chess.KNIGHT,
        "BISHOP": chess.BISHOP,
        "ROOK": chess.ROOK,
        "QUEEN": chess.QUEEN,
        "KING": chess.KING,
    }
    tables: dict[int, list[int]] = {}
    for name, piece_type in names.items():
        match = re.search(rf"const PST_{name}_MG: \[i32; 64\] = \[(.*?)\];", text, re.S)
        if not match:
            raise SystemExit(f"cannot find PST_{name}_MG in {path}")
        values = [int(v) for v in re.findall(r"-?\d+", match.group(1))]
        if len(values) != 64:
            raise SystemExit(f"PST_{name}_MG has {len(values)} entries, expected 64")
        tables[piece_type] = values
    return tables


PST = load_pst_from_source(EVAL_SOURCE)


def mirror_sq(sq: int) -> int:
    return sq ^ 56


def board_eval(board: chess.Board) -> int:
    """Material plus piece-square score, from White's point of view."""
    score = 0
    for sq, piece in board.piece_map().items():
        pt = piece.piece_type
        val = PIECE_VALUES[pt]
        pst = PST[pt][mirror_sq(sq) if not piece.color else sq]
        score += val + pst if piece.color else -(val + pst)
    return score


def opponent_best_move(board: chess.Board) -> chess.Move | None:
    """The greedy evaluation move for the side to move."""
    legal = list(board.legal_moves)
    if not legal:
        return None
    mover_is_white = board.turn
    best_move = None
    best_score = None
    for move in legal:
        board.push(move)
        # The evaluation is from White's point of view, so it has to be flipped for a Black move.
        score = board_eval(board) if mover_is_white else -board_eval(board)
        board.pop()
        if best_score is None or score > best_score:
            best_score = score
            best_move = move
    return best_move


def engine_bestmove(fen: str, movetime_ms: int, binary: str) -> str | None:
    proc = subprocess.Popen(
        [binary, "uci"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=0,
    )
    try:
        proc.stdin.write("uci\n")
        proc.stdin.flush()
        while True:
            line = proc.stdout.readline()
            if not line:
                raise EngineError("the engine closed stdout before answering 'uciok'")
            if line.strip() == "uciok":
                break
        proc.stdin.write(f"position fen {fen}\n")
        proc.stdin.flush()
        proc.stdin.write(f"go movetime {movetime_ms}\n")
        proc.stdin.flush()
        bestmove = None
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            if line.startswith("bestmove"):
                parts = line.split()
                bestmove = parts[1] if len(parts) > 1 else None
                break
        return bestmove
    finally:
        try:
            proc.stdin.write("quit\n")
            proc.stdin.flush()
        except (BrokenPipeError, ValueError, OSError):
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def material_for(board: chess.Board, color: chess.Color) -> int:
    return sum(
        PIECE_VALUES[piece.piece_type]
        for piece in board.piece_map().values()
        if piece.color == color
    )


def build_pgn(
    moves: list[chess.Move], game: int, engine_is_white: bool, outcome: str
) -> str:
    """The full move history of one lost game, as a PGN record.

    A board diagram would not be a game: a PGN reader has to be able to replay the moves.
    """
    pgn_game = chess.pgn.Game()
    pgn_game.headers["Event"] = "Flawless weakness diagnostic"
    pgn_game.headers["Site"] = "local"
    pgn_game.headers["Round"] = str(game + 1)
    pgn_game.headers["White"] = "candidate" if engine_is_white else "greedy-eval-opponent"
    pgn_game.headers["Black"] = "greedy-eval-opponent" if engine_is_white else "candidate"
    pgn_game.headers["Result"] = outcome
    node: chess.pgn.GameNode = pgn_game
    for move in moves:
        node = node.add_variation(move)
    return str(pgn_game)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=10)
    parser.add_argument("--movetime-ms", type=int, default=500)
    parser.add_argument("--max-plies", type=int, default=150)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--binary", default=ENGINE)
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    binary = args.binary
    if not Path(binary).is_file() or not os.access(binary, os.X_OK):
        print(f"engine binary missing or not executable: {binary}")
        return 2
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    random.seed(args.seed)
    flagged: list[dict] = []
    losing_games: list[str] = []
    results: list[dict] = []

    for game in range(args.games):
        board = chess.Board()
        moves: list[chess.Move] = []
        engine_is_white = game % 2 == 0
        engine_color = chess.WHITE if engine_is_white else chess.BLACK
        game_start = time.time()

        while not board.is_game_over() and len(moves) < args.max_plies:
            if board.turn == engine_color:
                fen = board.fen()
                best = engine_bestmove(fen, args.movetime_ms, binary)
                if best is None or best in ("0000", "(none)"):
                    print(f"game {game}: the engine returned no bestmove at {fen}")
                    break
                try:
                    move = chess.Move.from_uci(best)
                except ValueError:
                    print(f"game {game}: the engine returned an unparsable move {best!r} at {fen}")
                    break
                if move not in board.legal_moves:
                    print(f"game {game}: illegal move {best} at {fen}")
                    break
                board.push(move)
                moves.append(move)
                engine_move = move
            else:
                reply = opponent_best_move(board)
                if reply is None:
                    break
                # The material loss of the engine is measured through the opponent's reply: the
                # engine's own move cannot reduce its own material, so measuring across that move
                # alone would never flag anything. The reference material is therefore read here,
                # from the position the engine has just left, and not carried over from an earlier
                # turn — the opponent may move first when the engine plays Black.
                before = material_for(board, engine_color)
                board.push(reply)
                moves.append(reply)
                after = material_for(board, engine_color)
                lost = before - after
                if lost >= 250:
                    flagged.append(
                        {
                            "game": game,
                            "engine_color": "W" if engine_is_white else "B",
                            "ply": len(moves),
                            "fen_before": fen,
                            "engine_move": engine_move.uci(),
                            "opponent_reply": reply.uci(),
                            "material_lost_cp": lost,
                            "board_after": board.fen(),
                        }
                    )

        outcome = board.result()
        engine_won = (outcome == "1-0" and engine_is_white) or (
            outcome == "0-1" and not engine_is_white
        )
        engine_drew = outcome == "1/2-1/2"
        # A game that hit the ply cap has the result "*". It is not a loss: it is unfinished.
        # Counting it as one would turn a truncated game into a reported defeat.
        engine_lost = (outcome == "1-0" and not engine_is_white) or (
            outcome == "0-1" and engine_is_white
        )
        unfinished = outcome == "*"
        print(
            f"game {game}: engine={'W' if engine_is_white else 'B'} result={outcome} "
            f"engine_won={engine_won} plies={len(moves)} time={time.time() - game_start:.1f}s"
        )
        if engine_lost:
            losing_games.append(build_pgn(moves, game, engine_is_white, outcome))
        results.append(
            {
                "game": game,
                "engine_color": "W" if engine_is_white else "B",
                "result": outcome,
                "plies": len(moves),
                "engine_won": engine_won,
                "engine_drew": engine_drew,
                "engine_lost": engine_lost,
                "unfinished": unfinished,
            }
        )

    with (out / "weaknesses.jsonl").open("w", encoding="utf-8") as handle:
        for entry in flagged:
            handle.write(json.dumps(entry) + "\n")
    # The file is always rewritten, so a run without losses cannot leave the losing games of an
    # earlier run next to a summary that reports none.
    #
    # The records are separated by a blank line. `str(pgn_game)` has no trailing newline, and a
    # PGN reader ends a game at the blank line: with a single newline the next game's headers
    # would be swallowed by the preceding record, so a run with two losses would produce one
    # corrupted record instead of two games.
    with (out / "losing-games.pgn").open("w", encoding="utf-8") as handle:
        handle.write("\n\n".join(losing_games))
        if losing_games:
            handle.write("\n")

    summary = {
        "schema": 1,
        "kind": "weakness_diagnostic",
        "binary": binary,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "games": args.games,
        "movetime_ms": args.movetime_ms,
        "max_plies": args.max_plies,
        "seed": args.seed,
        "note": (
            "Diagnostic only. The opponent is a greedy evaluation opponent, so these games say "
            "nothing about playing strength and nothing about any rating."
        ),
        "flagged_material_losses": len(flagged),
        "losing_games": len(losing_games),
        "results": results,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(f"\nflagged {len(flagged)} material-loss positions -> {out / 'weaknesses.jsonl'}")
    for entry in flagged[:10]:
        print(
            f"  game {entry['game']} ({entry['engine_color']}) ply {entry['ply']}: "
            f"lost {entry['material_lost_cp']}cp after {entry['opponent_reply']}"
        )
        print(f"    FEN: {entry['fen_before']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
