#!/usr/bin/env python3
"""Synchronised UCI bestmove smoke test for CI (Linux and Windows).

Replaces the pipe-based step that sent `quit` in the same input as `go depth 2`.
That pattern can stop the search at depth 0 and still print a legal move, so it
proved less than its name says. This check waits for each reply, requires a
completed depth-2 `info` line, and sends `quit` only after `bestmove`.

Usage: python scripts/uci_bestmove_smoke.py <path-to-flawless[.exe]>
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import windows_artifact as wa  # noqa: E402


def main(argv):
    if len(argv) != 2:
        print("usage: uci_bestmove_smoke.py <flawless executable>", file=sys.stderr)
        return 2
    exe = argv[1]
    if not os.path.isfile(exe) and os.path.isfile(exe + ".exe"):
        exe += ".exe"
    try:
        _, bestmove, code, lines = wa.uci_session_bestmove(exe, [], "uci bestmove smoke")
    except wa.CheckError as e:
        print(f"::error::UCI bestmove smoke failed: {e}")
        return 1
    if code != 0:
        print(f"::error::engine exited with {code} after quit")
        return 1
    print("\n".join(lines))
    print(f"ok: bestmove {bestmove} after completed depth-2 search; exit 0")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
