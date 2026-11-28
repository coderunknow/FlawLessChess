#!/usr/bin/env python3
"""Attempt the canonical confirmatory merge without treating missing slots as success.

A not-yet-complete campaign is a normal, explicit state while failed shards are
being recovered. Any identity/manifest/duplicate error remains fatal.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs-root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--expected-games", type=int, default=100)
    ap.add_argument("--suite", required=True,
                    help="registered opening suite for exact opening and AB/BA checks")
    args = ap.parse_args()
    if os.path.exists(args.out):
        raise SystemExit(f"refusing to overwrite existing canonical evidence: {args.out}")
    if not os.path.isdir(args.runs_root):
        print("canonical confirmatory evidence: INCOMPLETE — no completed shard-run evidence yet")
        return 0
    if not any(name.startswith("run-") for name in os.listdir(args.runs_root)):
        print("canonical confirmatory evidence: INCOMPLETE — no run-* evidence directories yet")
        return 0
    command = [
        sys.executable, "scripts/merge_batch_runs.py",
        "--runs-root", args.runs_root, "--out", args.out,
        "--expected-games", str(args.expected_games), "--suite", args.suite,
    ]
    proc = subprocess.run(command, text=True, capture_output=True)
    if proc.returncode == 0:
        print(proc.stdout, end="")
        print("canonical confirmatory evidence: COMPLETE")
        return 0
    diagnostic = proc.stderr + proc.stdout
    coverage = re.search(
        r"schedule coverage broken: (\d+) missing .*?, (\d+) out-of-range",
        diagnostic,
    )
    if coverage and int(coverage.group(1)) > 0 and int(coverage.group(2)) == 0:
        print("canonical confirmatory evidence: INCOMPLETE — completed shard artifacts preserved; "
              "recover missing schedule indices before retrying merge")
        print(diagnostic, file=sys.stderr)
        return 0
    print(diagnostic, file=sys.stderr)
    return proc.returncode or 1


if __name__ == "__main__":
    raise SystemExit(main())
