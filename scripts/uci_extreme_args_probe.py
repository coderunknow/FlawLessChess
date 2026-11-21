#!/usr/bin/env python3
"""uci_extreme_args_probe.py — extreme numeric arguments to `go` and `setoption`, real process.

Each case sends one command (after a `position`), then checks:
  * `go` cases: a `bestmove` arrives. Cases without a limit are unbounded by UCI design, so the
    probe waits 3 s, sends `stop`, and requires `bestmove` after `stop`. Any panic text on stderr,
    a non-zero exit after `quit`, or a hang is a failure.
  * `go movetime 1` must answer within 2 s.
  * `setoption` cases: `readyok` arrives, the exit status is 0, and no panic text appears.

Usage: python3 scripts/uci_extreme_args_probe.py [engine]    (default ./target/release/flawless)
Exit status 1 if any case fails.
"""
import queue
import subprocess
import sys
import threading
import time

E = sys.argv[1] if len(sys.argv) > 1 else "./target/release/flawless"
START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

GO_CASES = [
    "go depth 0",
    "go depth 1",
    "go depth 99999999999",
    "go depth -1",
    "go depth 2147483647",
    "go movetime 0",
    "go movetime 1",
    "go movetime 18446744073709551615",
    "go movetime -5",
    "go nodes 0",
    "go nodes 1",
    "go nodes 18446744073709551615",
    "go wtime 0 btime 0",
    "go wtime 1 btime 1",
    "go wtime 18446744073709551615 btime 18446744073709551615",
    "go wtime 9223372036854775807 btime 9223372036854775807 winc 9223372036854775807 binc 9223372036854775807",
    "go wtime 1000 btime 1000 movestogo 0",
    "go wtime 1000 btime 1000 movestogo 18446744073709551615",
    "go wtime 1000 btime 1000 movestogo 1",
    "go wtime -1000 btime -1000",
    "go mate 0",
    "go mate 1",
    "go mate 99999999999999999999",
    "go depth 3 movetime 100 nodes 50",
]

SET_CASES = [
    "setoption name Hash value 0",
    "setoption name Hash value -1",
    "setoption name Hash value 99999999999999999999",
    "setoption name Hash value 1024",
    "setoption name Hash value 1",
    "setoption name MultiPV value 0",
    "setoption name MultiPV value 256",
    "setoption name MultiPV value 257",
    "setoption name MultiPV value 99999999999999999999",
    "setoption name Threads value 0",
    "setoption name Threads value 2",
    "setoption name Hash",
    "setoption value 5",
    "setoption name Clear Hash",
]


def run_session(lines, wait_for, timeout=60):
    p = subprocess.Popen([E, "uci"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, bufsize=1)
    out = []

    def send(s):
        p.stdin.write(s + "\n")
        p.stdin.flush()

    # Reader thread: the deadline is enforced while waiting, even if the engine prints nothing
    # (a blocking readline() would not return and the limit would never be checked).
    q = queue.Queue()

    def pump():
        for line in p.stdout:
            q.put(line)
        q.put(None)

    threading.Thread(target=pump, daemon=True).start()

    def until(prefix, limit):
        t0 = time.monotonic()
        while True:
            remaining = limit - (time.monotonic() - t0)
            if remaining <= 0:
                return "TIMEOUT"
            try:
                line = q.get(timeout=remaining)
            except queue.Empty:
                return "TIMEOUT"
            if line is None:
                return None
            out.append(line.rstrip())
            if line.startswith(prefix):
                return line.rstrip()

    send("uci")
    until("uciok", 10)
    send("isready")
    until("readyok", 10)
    send(f"position fen {START}")
    send("isready")
    until("readyok", 10)
    t0 = time.monotonic()
    for ln in lines:
        send(ln)
    reply = until(wait_for, timeout)
    elapsed = time.monotonic() - t0
    if reply == "TIMEOUT" and wait_for == "bestmove":
        # Unbounded by UCI design: answer must come after `stop`. Record that, then check it.
        send("stop")
        stopped = until(wait_for, 10)
        reply = f"STOP->{stopped}"
    send("quit")
    try:
        rc = p.wait(timeout=20)
    except subprocess.TimeoutExpired:
        p.kill()
        rc = "HUNG"
    err = p.stderr.read()
    return reply, elapsed, rc, err, out


failures = []
for case in GO_CASES:
    reply, elapsed, rc, err, out = run_session([case], "bestmove", timeout=3)
    bad = []
    if reply in (None, "TIMEOUT") or reply.startswith("STOP->TIMEOUT"):
        bad.append("no bestmove, even after stop")
    elif reply.startswith("STOP->"):
        if not reply.startswith("STOP->bestmove"):
            bad.append("reply " + reply)
    elif not reply.startswith("bestmove"):
        bad.append("reply " + reply)
    if rc != 0:
        bad.append(f"rc={rc}")
    if "panicked" in err or "panic" in err.lower():
        bad.append("panic text on stderr")
    # a go with an explicit short limit must not run for many seconds
    if case.startswith("go movetime 1 ") or case == "go movetime 1":
        if elapsed > 2.0:
            bad.append(f"movetime 1 took {elapsed:.2f}s")
    status = "FAIL" if bad else "ok"
    print(f"{status:4s} {case[:70]:70s} reply={reply!s:22.22s} t={elapsed:7.3f}s rc={rc} {'; '.join(bad)}", flush=True)
    if bad:
        failures.append((case, bad))

for case in SET_CASES:
    reply, elapsed, rc, err, out = run_session([case, "isready"], "readyok", timeout=30)
    bad = []
    if reply in (None, "TIMEOUT"):
        bad.append("no readyok")
    if rc != 0:
        bad.append(f"rc={rc}")
    if "panicked" in err:
        bad.append("panic text on stderr")
    info = [l for l in out if l.startswith("info string")]
    status = "FAIL" if bad else "ok"
    print(f"{status:4s} {case[:70]:70s} rc={rc} info={info[-1][:60] if info else '-'} {'; '.join(bad)}", flush=True)
    if bad:
        failures.append((case, bad))

print("FAILURES:", len(failures))
for f in failures:
    print("  ", f)
sys.exit(1 if failures else 0)
