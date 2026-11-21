#!/usr/bin/env python3
"""Full-game probe with an en passant capture (real process, python-chess referee).

The game starts from a position where White may capture en passant (f6). The first White move is
forced to be the en passant capture: the engine is asked for a search restricted to that move
(`go searchmoves e5f6`). The rest of the game is played engine against engine until the game ends
by the rules (python-chess `is_game_over(claim_draw=True)`) or a ply cap is reached.

Every engine reply must be a legal move in the referee's position. The probe fails on an illegal
move, a null move, a missing bestmove, a hang, or a bad exit code. Output records the counts of
en passant captures, castles, promotions and the termination, so the evidence is inspectable.

Usage: python3 scripts/fullgame_en_passant_probe.py ./target/release/flawless [--max-plies 400]
Requires: pip install chess==1.11.2
"""
import argparse
import sys

import chess
import chess.engine

START_FEN = "rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3"
FORCED_EP = "e5f6"


def fail(msg):
    print(f"FAIL: {msg}")
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("engine")
    ap.add_argument("--max-plies", type=int, default=400)
    ap.add_argument("--movetime-ms", type=int, default=20)
    args = ap.parse_args()

    board = chess.Board(START_FEN)
    forced = chess.Move.from_uci(FORCED_EP)
    if forced not in board.legal_moves or not board.is_en_passant(forced):
        fail("the forced move is not a legal en passant capture in the start position")

    eng = chess.engine.SimpleEngine.popen_uci(args.engine)
    played = []
    ep_count = castle_count = promo_count = 0
    try:
        # Ply 0: the forced en passant capture. searchmoves limits the root to that single move.
        # Depth-limited AND time-limited: python-chess applies no client deadline to a depth-only
        # limit, so the time limit bounds the wait (timeout + 5 s) if the engine stops replying.
        res = eng.play(board, chess.engine.Limit(depth=3, time=5.0), root_moves=[forced])
        if res.move is None or res.move.uci() == "0000":
            fail("no move for the forced en passant search")
        if res.move != forced:
            fail(f"searchmoves {FORCED_EP} returned {res.move}")
        ep_count += board.is_en_passant(res.move)
        board.push(res.move)
        played.append(res.move.uci())

        while len(played) < args.max_plies and not board.is_game_over(claim_draw=True):
            try:
                res = eng.play(board, chess.engine.Limit(time=args.movetime_ms / 1000.0))
            except chess.engine.EngineError as e:
                fail(f"engine error at ply {len(played)}: {e}")
            mv = res.move
            if mv is None or mv.uci() == "0000":
                fail(f"null move at ply {len(played)} in {board.fen()}")
            if mv not in board.legal_moves:
                fail(f"ILLEGAL move {mv.uci()} at ply {len(played)} in {board.fen()}")
            ep_count += board.is_en_passant(mv)
            castle_count += board.is_castling(mv)
            promo_count += bool(mv.promotion)
            board.push(mv)
            played.append(mv.uci())
    except BaseException:
        eng.close()
        raise
    # Clean shutdown is part of the result: quit must succeed and the process must exit with 0.
    try:
        eng.quit()
    except Exception as e:
        eng.close()
        fail(f"quit failed after the game: {e!r}")
    exit_code = eng.protocol.returncode.result()
    if exit_code != 0:
        fail(f"engine exit code {exit_code} after quit")

    if len(played) >= args.max_plies:
        termination = f"ply cap {args.max_plies} reached (no rule-based end)"
    else:
        claim = board.outcome(claim_draw=True)
        termination = f"{claim.termination.name} result={board.result(claim_draw=True)}" if claim else "unknown"

    # Independent replay: the recorded move list must replay legally from the start position.
    replay = chess.Board(START_FEN)
    for u in played:
        m = chess.Move.from_uci(u)
        if m not in replay.legal_moves:
            fail(f"replay: {u} illegal in {replay.fen()}")
        replay.push(m)
    if replay.fen() != board.fen():
        fail("replay final position differs")

    print(f"plies={len(played)} en_passant={ep_count} castles={castle_count} promotions={promo_count}")
    print(f"termination: {termination}")
    print(f"first moves: {' '.join(played[:8])}")
    if ep_count < 1:
        fail("no en passant capture was played")
    print("PASS: every engine move was legal; the game reached its end under the rules or the ply cap.")


if __name__ == "__main__":
    main()
