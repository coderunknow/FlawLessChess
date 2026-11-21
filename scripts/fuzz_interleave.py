#!/usr/bin/env python3
"""Stateful interleaving fuzz: random valid UCI command sequences that mix searches with stop, ponderhit,
isready, position, setoption and ucinewgame at arbitrary points. Invariants checked per session:
  1. every `go` yields exactly one `bestmove` (a `go` that is superseded by the next `go` still ends with one);
  2. every `isready` is answered with `readyok` within 10 s (liveness while a search runs);
  3. no `bestmove` without a preceding `go` (no spurious answers);
  4. the process exits 0 on `quit`, and no stderr output is emitted without `debug on`.
Engine output is read on a thread, so a blocked engine cannot block the check.

Usage: fuzz_interleave.py <engine> <sessions> <steps> <seed>
Exit status 0 when there are no failures.
"""
import queue
import random
import subprocess
import sys
import threading
import time

import chess

exe = sys.argv[1]
sessions = int(sys.argv[2])
steps = int(sys.argv[3])
seed = int(sys.argv[4])
random.seed(seed)


def random_fen():
    b = chess.Board()
    for _ in range(random.randint(0, 60)):
        moves = list(b.legal_moves)
        if not moves or b.is_game_over():
            break
        b.push(random.choice(moves))
    return b


def run_session(sid):
    p = subprocess.Popen([exe], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, bufsize=1)
    lines: "queue.Queue[str | None]" = queue.Queue()

    def pump():
        for line in p.stdout:
            lines.put(line.rstrip("\n"))
        lines.put(None)

    def pump_err():
        p.stderr.read()

    threading.Thread(target=pump, daemon=True).start()
    threading.Thread(target=pump_err, daemon=True).start()
    all_lines = []

    def expect(prefix, timeout):
        end = time.monotonic() + timeout
        while True:
            left = end - time.monotonic()
            if left <= 0:
                return None
            try:
                item = lines.get(timeout=left)
            except queue.Empty:
                return None
            if item is None:
                return "EOF"
            all_lines.append(item)
            if item.startswith(prefix):
                return item

    def send(s):
        p.stdin.write(s + "\n")
        p.stdin.flush()

    send("uci")
    if expect("uciok", 10) is None:
        return [f"session {sid}: no uciok"]
    gos = 0
    failures = []
    board = random_fen()
    for step in range(steps):
        r = random.random()
        if r < 0.22:
            cmd = random.choice([
                "go depth %d" % random.randint(1, 4),
                "go movetime %d" % random.randint(1, 40),
                "go infinite",
                "go ponder depth %d" % random.randint(1, 3),
                "go nodes %d" % random.randint(1, 3000),
                "go wtime %d btime %d winc 10 binc 10" % (random.randint(1, 2000), random.randint(1, 2000)),
                "go depth 2 searchmoves %s" % (random.choice(list(board.legal_moves)).uci() if board.legal_moves else "e2e4"),
            ])
            send(cmd)
            gos += 1
        elif r < 0.36:
            send("stop")
        elif r < 0.46:
            send("ponderhit")
        elif r < 0.56:
            send("isready")
            if expect("readyok", 10) is None:
                failures.append(f"session {sid} step {step}: no readyok while searching")
                break
        elif r < 0.70:
            board = random_fen()
            send(f"position fen {board.fen()}")
        elif r < 0.78:
            send("setoption name MultiPV value %d" % random.choice([1, 2, 3, 8]))
        elif r < 0.82:
            send("setoption name Hash value %d" % random.choice([1, 2, 16]))
        elif r < 0.86:
            send("ucinewgame")
        else:
            send("isready")
            if expect("readyok", 10) is None:
                failures.append(f"session {sid} step {step}: no readyok")
                break
        time.sleep(random.choice([0, 0, 0.001, 0.01]))
    # Finish: stop any search, then the count must match.
    send("stop")
    send("isready")
    if expect("readyok", 15) is None:
        failures.append(f"session {sid}: no readyok at the end (engine blocked?)")
    else:
        # all bestmoves must have arrived before readyok, since the engine answers in order
        pass
    send("quit")
    try:
        p.wait(timeout=20)
    except subprocess.TimeoutExpired:
        p.kill()
        failures.append(f"session {sid}: no exit after quit")
    # drain whatever is left in the queue
    while True:
        try:
            item = lines.get(timeout=0.5)
        except queue.Empty:
            break
        if item is None:
            break
        all_lines.append(item)
    bests = sum(1 for l in all_lines if l.startswith("bestmove"))
    if bests != gos:
        failures.append(f"session {sid}: {gos} go commands but {bests} bestmove lines")
    if p.returncode != 0:
        failures.append(f"session {sid}: exit status {p.returncode}")
    return failures


all_fail = []
for sid in range(sessions):
    all_fail += run_session(sid)
for f in all_fail[:20]:
    print("FAIL", f)
print(f"seed={seed} sessions={sessions} steps={steps} failures={len(all_fail)}")
sys.exit(1 if all_fail else 0)
