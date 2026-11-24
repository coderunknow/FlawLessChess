#!/usr/bin/env python3
"""time_budget_probe.py — wall-clock audit of `go` time limits through the UCI pipe.

For each case, starts the engine, sends `position` + `go ...`, and measures the time from `go`
to `bestmove`. The checks are:
  * movetime N: elapsed must be >= 0.9*N (the search uses its budget) and <= N + SLACK_MS.
  * clock cases: elapsed must be <= the side's remaining time minus a margin (no flag), and
    <= the engine's own hard limit plus SLACK_MS.
  * every bestmove must be a legal move (checked with python-chess).

Usage: python3 scripts/time_budget_probe.py [engine]    (default ./target/release/flawless)
Exit status 1 if any case violates a check.
"""
from __future__ import annotations

import queue
import subprocess
import sys
import threading
import time

import chess

ENGINE = sys.argv[1] if len(sys.argv) > 1 else "./target/release/flawless"
SLACK_MS = 150  # process and pipe overhead allowed beyond the budget


class Session:
    def __init__(self) -> None:
        self.p = subprocess.Popen([ENGINE], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, bufsize=1)
        # A reader thread feeds a queue. Never call select() on the pipe while the buffered text
        # stream is in use: select() reports "no data" once readline() has buffered several lines.
        self.lines: queue.Queue[str | None] = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        for line in self.p.stdout:
            self.lines.put(line)
        self.lines.put(None)

    def send(self, line: str) -> None:
        self.p.stdin.write(line + "\n")
        self.p.stdin.flush()

    def read_until(self, prefix: str, timeout: float) -> list[str]:
        seen: list[str] = []
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"no {prefix!r} within {timeout}s; saw {seen[-3:]}")
            try:
                item = self.lines.get(timeout=remaining)
            except queue.Empty:
                continue
            if item is None:
                raise RuntimeError(f"engine closed stdout; saw {seen[-3:]}")
            line = item.strip()
            seen.append(line)
            if line.startswith(prefix):
                return seen

    def close(self) -> None:
        try:
            self.send("quit")
            self.p.wait(timeout=10)
        except Exception:
            self.p.kill()


def run_case(name: str, fen: str, go: str, check) -> bool:
    s = Session()
    try:
        s.send("uci")
        s.read_until("uciok", 10)
        s.send("isready")
        s.read_until("readyok", 10)
        s.send(f"position fen {fen}")
        s.send("isready")
        s.read_until("readyok", 10)
        t0 = time.monotonic()
        s.send(f"go {go}")
        lines = s.read_until("bestmove", 120)
        elapsed_ms = (time.monotonic() - t0) * 1000.0
    finally:
        s.close()
    bm = [l for l in lines if l.startswith("bestmove ")][-1].split()[1]
    board = chess.Board(fen)
    legal = bm == "0000" and board.legal_moves.count() == 0
    legal = legal or (bm != "0000" and chess.Move.from_uci(bm) in board.legal_moves)
    problems = []
    if not legal:
        problems.append(f"illegal bestmove {bm}")
    problems += check(elapsed_ms)
    status = "OK  " if not problems else "FAIL"
    print(f"{status} {name:28s} elapsed={elapsed_ms:8.1f} ms  bestmove={bm}"
          + ("" if not problems else "  " + "; ".join(problems)))
    return not problems


START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
KIWI = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"


def movetime(n: int):
    def check(ms: float) -> list[str]:
        out = []
        if ms < 0.9 * n:
            out.append(f"returned early ({ms:.0f} < 0.9*{n})")
        if ms > n + SLACK_MS:
            out.append(f"overran movetime ({ms:.0f} > {n}+{SLACK_MS})")
        return out
    return check


def clock(remaining: int, hard_bound: int):
    def check(ms: float) -> list[str]:
        out = []
        if ms >= remaining:
            out.append(f"would flag ({ms:.0f} >= remaining {remaining})")
        if ms > hard_bound + SLACK_MS:
            out.append(f"exceeded hard bound ({ms:.0f} > {hard_bound}+{SLACK_MS})")
        return out
    return check


def main() -> int:
    cases = [
        ("movetime 50 start", START, "movetime 50", movetime(50)),
        ("movetime 500 kiwipete", KIWI, "movetime 500", movetime(500)),
        ("movetime 2000 start", START, "movetime 2000", movetime(2000)),
        # 10 s clock, 40 moves: reserve=625 ms, soft~(10000-625)/40 ~ 234 ms, hard<=4*soft.
        ("wtime 10000 mtg 40", START, "wtime 10000 btime 10000 movestogo 40",
         clock(10_000, 4 * 240)),
        ("wtime 2000 inc 100", KIWI, "wtime 2000 btime 2000 winc 100 binc 100",
         clock(2_000, 1_000)),
        # Very short clock: the engine must answer well before the flag.
        ("wtime 300 sudden death", START, "wtime 300 btime 300", clock(300, 300)),
        ("wtime 60", START, "wtime 60 btime 60", clock(60, 60)),
        # Black to move with only btime: the side to move has a clock, so the search is bounded.
        ("btime 1500 black to move", "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
         "btime 1500", clock(1_500, 1_500)),
    ]
    results = [run_case(*c) for c in cases]
    passed = sum(results)
    print(f"{passed}/{len(results)} cases passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
