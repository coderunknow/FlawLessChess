#!/usr/bin/env python3
"""Failure-mode harness for the probe scripts (release audit 2026-11-22).

Every probe that drives an engine must FAIL (non-zero exit) and must FINISH within a bound when the
engine is broken. A probe that passes, or hangs, against a broken engine can hide a defect, so each
probe is run against three fake engines:

  silent       prints nothing at all (a stalled or dead handshake)
  exit_after   answers the handshake, prints one legal `bestmove`, then exits with status 1
  nullmove     answers everything with `bestmove 0000`, no `info` lines, and exits 0 on quit

Usage: python3 scripts/failure_mode_probe.py [--only NAME] [--bound SECONDS]
Exit 0 when every probe/engine pair fails in bounded time. Run with the python-chess venv.
"""
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable

FAKES = {
    "silent": """import sys
for _ in sys.stdin:
    pass
""",
    "exit_after": """import os, sys
for line in sys.stdin:
    t = line.split()
    if not t:
        continue
    if t[0] == "uci":
        print("id name fake"); print("uciok")
    elif t[0] == "isready":
        print("readyok")
    elif t[0] == "go":
        print("info depth 1 seldepth 1 multipv 1 score cp 0 nodes 1 nps 1 time 0 pv e2e4")
        print("bestmove e2e4")
        sys.stdout.flush()
        os._exit(1)
    sys.stdout.flush()
""",
    "nullmove": """import sys
for line in sys.stdin:
    t = line.split()
    if not t:
        continue
    if t[0] == "uci":
        print("uciok")
    elif t[0] == "isready":
        print("readyok")
    elif t[0] == "go":
        print("bestmove 0000")
    elif t[0] == "quit":
        break
    sys.stdout.flush()
""",
}

# Protocol and robustness probes check sequencing, grammar, or survival (no panic, hang, or bad exit),
# not move quality. A well-formed `bestmove 0000` is valid there, so they must PASS against `nullmove`;
# against silent and exit_after they must fail.
PROTOCOL_ONLY = {"fuzz_interleave.py", "fuzz_uci_grammar.py", "uci_extreme_args_probe.py"}

# (script, argument template; {eng} is replaced by the fake engine path, env for FLAWLESS_ENGINE)
PROBES = [
    ("eval_symmetry_probe.py", ["{eng}", "--positions", "2", "--depth", "2"], {}),
    ("fullgame_en_passant_probe.py", ["{eng}", "--max-plies", "4"], {}),
    ("selfplay_clock_probe.py", ["{eng}", "1000", "20", "4"], {}),
    ("tt_bestmove_probe.py", ["{eng}", "2", "4", "1"], {}),
    ("fuzz_fen_extremes.py", ["1", "5"], {"FLAWLESS_ENGINE": "{eng}"}),
    ("fuzz_uci_grammar.py", ["1", "3"], {"FLAWLESS_ENGINE": "{eng}"}),
    ("fuzz_interleave.py", ["{eng}", "2", "5", "1"], {}),
    ("mate_distance_probe.py", ["{eng}", "1", "2", "--depth", "2"], {}),
    ("mate_proof_probe.py", ["{eng}", "2", "1", "--limit", "2", "--depth", "3"], {}),
    ("negative_mate_probe.py", ["{eng}", "2", "1"], {}),
    ("searchmoves_probe.py", ["{eng}", "2", "1", "1"], {}),
    ("multipv_probe.py", ["{eng}", "2", "1", "2"], {}),
    ("pv_legality_probe.py", ["{eng}", "2", "3", "1"], {}),
    ("uci_malformed_probe.py", ["{eng}"], {}),
    ("uci_protocol_probe.py", ["{eng}"], {}),
    ("uci_extreme_args_probe.py", ["{eng}"], {}),
    ("time_budget_probe.py", ["{eng}"], {}),
]


def run_one(script, args, env_extra, eng, bound):
    env = dict(os.environ)
    for k, v in env_extra.items():
        env[k] = v.replace("{eng}", eng)
    cmd = [PY, os.path.join(HERE, script)] + [a.replace("{eng}", eng) for a in args]
    t0 = time.monotonic()
    try:
        out = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=bound)
        rc = out.returncode
        tail = (out.stdout + out.stderr).strip().splitlines()[-1:] if (out.stdout + out.stderr).strip() else [""]
    except subprocess.TimeoutExpired:
        rc = None
        tail = [f"TIMEOUT after {bound} s"]
    return rc, time.monotonic() - t0, tail[0][:150]


def main(argv):
    only = argv[argv.index("--only") + 1] if "--only" in argv else None
    bound = float(argv[argv.index("--bound") + 1]) if "--bound" in argv else 240.0
    failures = []
    with tempfile.TemporaryDirectory() as td:
        engs = {}
        for name, src in FAKES.items():
            path = os.path.join(td, f"fake_{name}.py")
            with open(path, "w") as f:
                f.write(f"#!{PY}\n" + src)
            os.chmod(path, 0o755)
            engs[name] = path
        for script, args, env_extra in PROBES:
            if only and only not in script:
                continue
            for name, eng in engs.items():
                rc, dt, last = run_one(script, args, env_extra, eng, bound)
                expect_fail = not (name == "nullmove" and script in PROTOCOL_ONLY)
                ok = rc is not None and ((rc != 0) == expect_fail)
                print(f"{'PASS' if ok else 'FAIL'}  {script:28s} vs {name:11s} rc={rc} {dt:6.1f}s  {last}", flush=True)
                if not ok:
                    failures.append((script, name, rc, dt))
    print(f"RESULT {'PASS' if not failures else 'FAIL'}: {len(failures)} probe/engine pairs were not classified as expected")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
