#!/usr/bin/env python3
"""Colour-mirror symmetry probe for evaluation and search (real process).

For random positions from random legal games, a fixed-depth search of each position is compared
with its colour-mirror (`chess.Board.mirror()`). The HARD symmetry gate for evaluation is the Rust
test `tests/correctness.rs::static_evaluation_is_colour_symmetric` (303 pairs, static evaluation).
This probe is INFORMATIONAL for search: null-move pruning, late-move reductions and move-order
ties make a depth-4 search legitimately order-dependent, so a mismatch is reported, not failed.
A mismatch at depths where the static evaluation is symmetric points to search heuristics.

Usage: python3 scripts/eval_symmetry_probe.py ./target/release/flawless [--positions 40] [--depth 4]
Requires: pip install chess==1.11.2
"""
import argparse
import queue
import random
import re
import subprocess
import sys
import threading
import time

import chess

SCORE_RE = re.compile(r"score (cp|mate) (-?\d+)")


class Searcher:
    """One engine process; each `go` is waited to its `bestmove` before anything else is sent.

    Sending `go` and `quit` in one burst lets `quit` stop the search before an iteration completes,
    which returns the unsearched fallback move (see CHANGELOG). This probe never does that.
    Every wait has a deadline; on any failure the child is killed and reaped.
    """

    def __init__(self, engine):
        self.p = subprocess.Popen([engine], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self.q = queue.Queue()
        self.reader = threading.Thread(target=self._pump, daemon=True)
        self.reader.start()
        try:
            self.send("uci")
            self.wait_for("uciok")
            self.send("isready")
            self.wait_for("readyok")
        except BaseException:
            self.kill()
            raise

    def _pump(self):
        for line in self.p.stdout:
            self.q.put(line.rstrip("\n"))
        self.q.put(None)  # EOF marker

    def send(self, line):
        self.p.stdin.write(line + "\n")
        self.p.stdin.flush()

    def wait_for(self, token, timeout=120.0):
        lines = []
        end = time.monotonic() + timeout
        while True:
            remaining = end - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(f"timeout after {timeout}s waiting for {token!r}; last={lines[-3:]}")
            try:
                line = self.q.get(timeout=min(remaining, 0.2))
            except queue.Empty:
                continue
            if line is None:
                raise RuntimeError(f"engine exited while waiting for {token!r}: {lines[-5:]}")
            lines.append(line)
            if line.startswith(token):
                return lines

    def score(self, fen, depth):
        self.send("ucinewgame")
        self.send("isready")
        self.wait_for("readyok")
        self.send(f"position fen {fen}")
        self.send(f"go depth {depth}")
        lines = self.wait_for("bestmove")
        found = None
        for line in lines:
            if line.startswith(f"info depth {depth} "):
                m = SCORE_RE.search(line)
                if m:
                    found = (m.group(1), int(m.group(2)))
        if found is None:
            raise RuntimeError(f"no depth-{depth} score for {fen}")
        return found

    def kill(self):
        if self.p.poll() is None:
            self.p.kill()
        try:
            self.p.wait(timeout=10)  # SIGKILL cannot be ignored; bounded anyway (F-43)
        except subprocess.TimeoutExpired:
            print("warning: engine did not reap within 10 s after kill", file=sys.stderr)
        for f in (self.p.stdin, self.p.stdout):
            try:
                f.close()
            except Exception:
                pass

    def close(self):
        """Ask for quit, require a clean exit within a deadline, otherwise kill and fail."""
        try:
            self.send("quit")
            self.p.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.kill()
            raise RuntimeError("engine did not exit within 30s after quit")
        finally:
            self.kill()
        if self.p.returncode != 0:
            raise RuntimeError(f"engine exit {self.p.returncode}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("engine")
    ap.add_argument("--positions", type=int, default=40)
    ap.add_argument("--depth", type=int, default=4)
    ap.add_argument("--seed", type=int, default=2026)
    args = ap.parse_args()
    rnd = random.Random(args.seed)

    fens = []
    while len(fens) < args.positions:
        b = chess.Board()
        for ply in range(rnd.randint(8, 60)):
            moves = list(b.legal_moves)
            if not moves or b.is_game_over(claim_draw=True):
                break
            b.push(rnd.choice(moves))
        if not b.is_game_over(claim_draw=True) and not b.is_check():
            fens.append(b.fen())

    mismatches = []
    eng = Searcher(args.engine)
    try:
        for fen in fens:
            mirror = chess.Board(fen).mirror().fen()
            a = eng.score(fen, args.depth)
            b = eng.score(mirror, args.depth)
            if a != b:
                mismatches.append((fen, a, mirror, b))
    except BaseException:
        eng.kill()
        raise
    eng.close()

    print(f"positions={len(fens)} depth={args.depth} search_mismatches={len(mismatches)} (informational)")
    for m in mismatches[:10]:
        print("SEARCH-MISMATCH", m)
    print("Probe completed. Static evaluation symmetry is gated by the Rust test, not by this probe.")


if __name__ == "__main__":
    main()
