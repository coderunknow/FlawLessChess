# Usage: FLAWLESS_ENGINE=./target/release/flawless python3 scripts/fuzz_uci_grammar.py <seed> <sessions>
"""UCI grammar fuzzer: random sessions against the real process.

Each session sends a random mix of valid and malformed commands (including random FENs and go
variants), then `isready`, which must be answered by `readyok` within a timeout, then `quit`,
which must end the process with exit code 0. Any hang, crash, missing readyok, or bad exit code
is recorded with the full session so it can be replayed.
"""
import os
import random
import subprocess
import sys
import time

E = os.environ.get("FLAWLESS_ENGINE", "./target/release/flawless")
seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
sessions = int(sys.argv[2]) if len(sys.argv) > 2 else 100
rnd = random.Random(seed)

FILES = "abcdefgh"
MOVES_POOL = ["e2e4", "d2d4", "g1f3", "e7e5", "e2e5", "a1a8", "e1g1", "e8c8", "b7b8q", "h7h8n", "zz", "", "0000", "e5d6"]
PIECES = "PNBRQpnbrq"


def rand_fen():
    rows = []
    for r in range(8):
        s, e = "", 0
        for f in range(8):
            if rnd.random() < 0.7:
                e += 1
            else:
                if e:
                    s += str(e)
                    e = 0
                s += rnd.choice(PIECES)
        if e:
            s += str(e)
        rows.append(s)
    side = rnd.choice(["w", "b", "x"])
    return "/".join(rows) + f" {side} {rnd.choice(['-', 'KQkq', 'Kq', 'Z'])} {rnd.choice(['-', 'e3', 'zz'])} {rnd.randint(-2, 60)} {rnd.randint(0, 99)}"


def rand_line():
    # Retry until the line does not contain the token `isready`: every readyok must then come from
    # the single sentinel `isready` appended to each session.
    while True:
        line = _rand_line()
        if "isready" not in line:
            return line


def _rand_line():
    c = rnd.random()
    if c < 0.10:
        return "position startpos" + (" moves " + " ".join(rnd.choice(MOVES_POOL) for _ in range(rnd.randint(0, 6))) if rnd.random() < 0.5 else "")
    if c < 0.20:
        return "position fen " + rand_fen() + (" moves " + " ".join(rnd.choice(MOVES_POOL) for _ in range(rnd.randint(0, 3))) if rnd.random() < 0.3 else "")
    if c < 0.40:
        parts = ["go"]
        for key in ["depth", "nodes", "movetime", "wtime", "btime", "winc", "binc", "movestogo"]:
            if rnd.random() < 0.3:
                parts += [key, str(rnd.choice([0, 1, 2, 5, 50, -1, 10**12, 99999999999999999999]))]
        if rnd.random() < 0.2:
            parts.append("ponder")
        if rnd.random() < 0.2:
            parts += ["searchmoves"] + [rnd.choice(MOVES_POOL) for _ in range(rnd.randint(1, 3))]
        if rnd.random() < 0.15:
            parts.append("infinite")
        if rnd.random() < 0.4:
            parts += ["movetime", str(rnd.randint(1, 30))]
        return " ".join(parts)
    if c < 0.50:
        return rnd.choice(["stop", "ponderhit", "ponderhit", "stop"])
    if c < 0.62:
        name = rnd.choice(["Hash", "Threads", "MultiPV", "Clear Hash", "Nope", "hash"])
        val = rnd.choice(["1", "16", "1024", "1025", "4096", "0", "-3", "abc", "", "300", "99999999999999999999"])
        return f"setoption name {name} value {val}" if rnd.random() < 0.9 else f"setoption {name} {val}"
    if c < 0.70:
        return rnd.choice(["ucinewgame", "debug on", "debug off", "register later", "uci", "d", "eval"])
    if c < 0.80:
        return "perft " + str(rnd.randint(0, 2))
    # random garbage, including control characters and long tokens
    n = rnd.randint(0, 80)
    return "".join(chr(rnd.choice([rnd.randint(32, 126), rnd.randint(1, 31), rnd.randint(127, 0x2FF)])) for _ in range(n)).replace("\n", " ").replace("\r", " ")


failures = []
for s in range(sessions):
    lines = [rand_line() for _ in range(rnd.randint(1, 25))]
    script = "uci\n" + "\n".join(lines) + "\nisready\nquit\n"
    try:
        p = subprocess.run([E], input=script.encode("utf-8", "surrogateescape"), capture_output=True, timeout=60)
    except subprocess.TimeoutExpired:
        failures.append(("HANG", s, lines))
        continue
    out = p.stdout.decode("utf-8", "replace").splitlines()
    if p.returncode != 0:
        failures.append((f"EXIT {p.returncode}", s, lines, p.stderr.decode("utf-8", "replace")[:300]))
        continue
    if "uciok" not in out:
        failures.append(("NO-UCIOK", s, lines))
        continue
    # Exactly one readyok: it answers the final `isready`, sent after every generated line. No
    # generated line contains `isready`, so an earlier reply cannot be mistaken for it.
    if out.count("readyok") != 1:
        failures.append((f"READYOK x{out.count('readyok')} (expected 1)", s, lines))
        continue
print(f"seed={seed} sessions={sessions} failures={len(failures)}")
for f in failures[:5]:
    print("FAIL", f)
sys.exit(0 if not failures else 2)
