#!/usr/bin/env python3
"""Full-game validation: Flawless vs Flawless through the python-chess UCI client.

python-chess (pinned, TEST-ONLY) acts as the referee and the UCI client: it validates every
move the engine returns against its own legal-move generator, enforces wall-clock
time controls (wtime/btime/winc/binc sent via `go`), and records termination reasons.
Usage: python3 scripts/selfplay_games.py <engine> <outdir> [--games N] [--tc ms+inc]
"""
import argparse, json, os, sys, threading, time
import chess
import chess.engine

OPENINGS = [
    ("startpos", chess.STARTING_FEN),
    ("kiwipete", "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"),
    ("promo-race", "4k3/1P6/8/8/8/8/6p1/4K3 w - - 0 1"),
    ("castle-both", "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"),
    ("stalemate-trap", "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"),
    ("ep-setup", "rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3"),
]

# Termination reasons that make a game a failure (the script exits non-zero if any occur).
FAILURE_PREFIXES = ("ENGINE_TERMINATED", "ENGINE_ERROR", "ILLEGAL_OR_NULL_MOVE", "FLAG_FALL", "TIMEOUT", "BAD_EXIT", "PLY_CAP")
GRACE_S = 5.0  # client-side slack beyond the clock budget before a search counts as hung

def play_with_deadline(eng, board, limit, deadline_s):
    """Run eng.play in a daemon thread; return (result, None) or (None, reason) on timeout/error."""
    box = {}
    def worker():
        try:
            box["res"] = eng.play(board, limit)
        except Exception as e:  # propagated to the caller as a termination reason
            box["err"] = e
    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(deadline_s)
    if t.is_alive():
        return None, f"TIMEOUT no bestmove within {deadline_s:.1f}s"
    if "err" in box:
        raise box["err"]
    return box["res"], None

def play(engine_path, name, fen, outdir, base_ms, inc_ms, max_plies=400):
    board = chess.Board(fen)
    eng = chess.engine.SimpleEngine.popen_uci([engine_path])
    clocks = {chess.WHITE: base_ms / 1000.0, chess.BLACK: base_ms / 1000.0}
    log = {"opening": name, "fen0": fen, "moves": [], "termination": None, "events": []}
    try:
        eng.configure({})  # no options; exercises the handshake
        ply = 0
        while not board.is_game_over(claim_draw=True) and ply < max_plies:
            side = board.turn
            t0 = time.monotonic()
            limit = chess.engine.Limit(
                white_clock=clocks[chess.WHITE], black_clock=clocks[chess.BLACK],
                white_inc=inc_ms / 1000.0, black_inc=inc_ms / 1000.0)
            res, timeout_reason = play_with_deadline(eng, board, limit, max(clocks[side], 0.0) + GRACE_S)
            if timeout_reason:
                log["termination"] = timeout_reason + f" at ply {ply}"
                break
            spent = time.monotonic() - t0
            mv = res.move
            if mv is None or mv not in board.legal_moves:
                log["termination"] = f"ILLEGAL_OR_NULL_MOVE {mv} at ply {ply}"
                break
            clocks[side] -= spent
            if clocks[side] <= 0:
                log["termination"] = f"FLAG_FALL side={side} at ply {ply}"
                break
            clocks[side] += inc_ms / 1000.0
            log["moves"].append({"ply": ply, "move": mv.uci(), "fen_before": board.fen(),
                                 "spent_s": round(spent, 4), "clock_left_s": round(clocks[side], 3)})
            board.push(mv)
            ply += 1
        if log["termination"] is None:
            if board.is_game_over(claim_draw=True):
                log["termination"] = f"GAME_OVER: {board.outcome(claim_draw=True).termination.name} result={board.result(claim_draw=True)}"
            else:
                log["termination"] = f"PLY_CAP {max_plies}"
        log["final_fen"] = board.fen()
        log["ply_count"] = len(log["moves"])
        # Clean shutdown: the engine must exit with status 0 after quit.
        try:
            eng.quit()
            code = eng.returncode.result(timeout=10)
        except Exception as e:  # a hung engine cannot be quit; record it, never crash the run
            code = None
            log["exit"] = f"quit failed: {type(e).__name__}"
            log["termination"] = (log["termination"] or "") + f" BAD_EXIT quit failed: {type(e).__name__}"
        if code == 0:
            log["exit"] = "quit ok"
        elif code is not None:
            log["exit"] = f"exit status {code}"
            log["termination"] = (log["termination"] or "") + f" BAD_EXIT status={code}"
    except chess.engine.EngineTerminatedError as e:
        log["termination"] = f"ENGINE_TERMINATED: {e}"
    except chess.engine.EngineError as e:
        # Protocol-level failure (e.g. a malformed or unexpected reply). Recorded as a failure;
        # the moves completed so far stay in the log.
        log["termination"] = f"ENGINE_ERROR: {type(e).__name__}: {e}"
    finally:
        try:
            eng.close()
        except Exception:
            pass
    with open(os.path.join(outdir, f"game-{name}.json"), "w") as f:
        json.dump(log, f, indent=1)
    return log

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("engine"); ap.add_argument("outdir")
    ap.add_argument("--tc", default="3000+50", help="base_ms+inc_ms")
    ap.add_argument("--only", default=None, choices=[name for name, _ in OPENINGS],
                    help="run one opening; an unknown name is an argument error, not an empty run")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    base, inc = (int(x) for x in a.tc.split("+"))
    summary = []
    for name, fen in OPENINGS:
        if a.only and a.only != name:
            continue
        t = time.monotonic()
        log = play(a.engine, name, fen, a.outdir, base, inc)
        dt = time.monotonic() - t
        print(f"{name:15s} plies={log.get('ply_count')} term={log['termination']} wall={dt:.1f}s", flush=True)
        summary.append({"opening": name, "plies": log.get("ply_count"), "termination": log["termination"], "wall_s": round(dt, 1)})
    with open(os.path.join(a.outdir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1)
    # Non-zero exit if any game failed, so CI cannot pass on a broken game.
    failures = [g for g in summary if g["termination"] and g["termination"].startswith(FAILURE_PREFIXES)
                or (g["termination"] and " BAD_EXIT" in g["termination"])]
    if failures:
        print(f"FAILED games: {[g['opening'] for g in failures]}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
