#!/usr/bin/env python3
"""search_sweep.py — search legality and crash sweep over random reachable positions.

Audit tool (test-only; python-chess is never linked into the engine). For each seed, plays random
legal games with python-chess, then for sampled positions (including check, stalemate-adjacent and
endgame positions) runs the engine through UCI with `go depth D`, and checks:
  * the engine exits cleanly (rc 0) after `quit`, with no panic text on stderr;
  * exactly one `bestmove` line per `go`, and it is a legal move (or 0000 only when no legal move);
  * the `info` score is finite (no overflowed score values).

Usage:
    FLAWLESS_ENGINE=./target/debug/flawless python3 scripts/search_sweep.py <seed> <positions> [depth]

Debug builds check arithmetic overflow, so run the sweep against a debug build as well.
"""
from __future__ import annotations

import os
import random
import queue
import re
import subprocess
import sys
import threading
import time

import chess

ENGINE = os.environ.get("FLAWLESS_ENGINE", "./target/release/flawless")
SCORE = re.compile(r"score (cp|mate) (-?\d+)")


DEADLINE_S = 120


def _pump(stream, q: "queue.Queue[str | None]") -> None:
    # Reader thread: every line (and EOF as None) goes to the queue, so the caller can
    # wait with a deadline instead of blocking in readline() on a silent engine.
    for line in stream:
        q.put(line)
    q.put(None)


def search(fen: str, depth: int) -> tuple[list[str], int, str]:
    p = subprocess.Popen([ENGINE, "uci"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True)
    out_q: "queue.Queue[str | None]" = queue.Queue()
    err_q: "queue.Queue[str | None]" = queue.Queue()
    threading.Thread(target=_pump, args=(p.stdout, out_q), daemon=True).start()
    threading.Thread(target=_pump, args=(p.stderr, err_q), daemon=True).start()
    script = f"uci\nisready\nposition fen {fen}\ngo depth {depth}\n"
    out_lines: list[str] = []
    deadline = time.monotonic() + DEADLINE_S

    def fail(msg: str) -> None:
        # Kill and reap the child on every failure path so no engine outlives the probe.
        p.kill()
        p.wait()
        raise RuntimeError(msg)

    def next_line() -> str | None:
        # Check the remaining time before every read: a stream of `info` lines never empties the
        # queue, so a bare get() with a floor could keep reading past the deadline.
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            fail(f"no bestmove within {DEADLINE_S} s on {fen!r}")
        try:
            return out_q.get(timeout=remaining)
        except queue.Empty:
            fail(f"no bestmove within {DEADLINE_S} s on {fen!r}")

    try:
        p.stdin.write(script)
        p.stdin.flush()
        while True:
            line = next_line()
            if line is None:
                break
            out_lines.append(line.rstrip("\n"))
            if line.startswith("bestmove"):
                break
        p.stdin.write("quit\n")
        p.stdin.flush()
    except BrokenPipeError:
        pass
    while True:
        line = next_line()
        if line is None:
            break
        out_lines.append(line.rstrip("\n"))
    try:
        p.wait(timeout=max(1.0, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait()
        raise RuntimeError(f"engine did not exit after quit on {fen!r}")
    err_lines: list[str] = []
    while True:
        try:
            line = err_q.get(timeout=5)
        except queue.Empty:
            break
        if line is None:
            break
        err_lines.append(line)
    return out_lines, p.returncode, "".join(err_lines)


def main() -> int:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    depth = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    rnd = random.Random(seed)
    checked = failures = 0
    for i in range(count):
        board = chess.Board()
        for _ in range(rnd.randint(0, 120)):
            if board.is_game_over(claim_draw=True):
                break
            board.push(rnd.choice(list(board.legal_moves)))
        fen = board.fen()
        legal = list(board.legal_moves)
        lines, rc, err = search(fen, depth)
        checked += 1
        problems = []
        if rc != 0:
            problems.append(f"rc={rc}")
        if "panicked" in err or "panic" in err.lower():
            problems.append("panic on stderr: " + err.strip().splitlines()[0][:120])
        bms = [l for l in lines if l.startswith("bestmove")]
        if len(bms) != 1:
            problems.append(f"{len(bms)} bestmove lines")
        elif legal:
            move = bms[0].split()[1]
            if move == "0000" or chess.Move.from_uci(move) not in legal:
                problems.append(f"illegal bestmove {move}")
        else:
            if bms and bms[0].split()[1] != "0000":
                problems.append(f"terminal position answered {bms[0]}")
        for l in lines:
            if l.startswith("info depth") and " score " in l:
                m = SCORE.search(l)
                if m and m.group(1) == "cp" and abs(int(m.group(2))) > 31_000:
                    problems.append(f"cp score out of range: {m.group(2)}")
                if m and m.group(1) == "mate" and abs(int(m.group(2))) > 1_000:
                    problems.append(f"mate distance out of range: {m.group(2)}")
        if problems:
            failures += 1
            print(f"FAIL seed={seed} #{i} fen={fen} :: " + "; ".join(problems))
    print(f"seed={seed} positions={checked} depth={depth} failures={failures}")
    print("RESULT PASS" if failures == 0 else "RESULT FAIL")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
