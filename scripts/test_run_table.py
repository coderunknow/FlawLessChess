#!/usr/bin/env python3
"""The hosted quick-run table in STATUS.md must match the published summaries.

The table was transcribed by hand once and drifted: the scores were right but the W/D/L counts were
transposed in nine rows, and two runs were missed entirely, because the extraction queried the pull
request comments without pagination. `scripts/refresh_run_table.py` now derives the table from the
committed fixture `benches/quick-run-summaries.json`, and this suite makes sure that

1. the fixture is internally consistent with the scoring formula,
2. the table in STATUS.md is exactly what the tool generates, and
3. the tool really would notice a drifted row.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "benches" / "quick-run-summaries.json"
STATUS = REPO_ROOT / "STATUS.md"
TOOL = REPO_ROOT / "scripts" / "refresh_run_table.py"

PASS = 0
FAIL = 0


def check(condition: bool, message: str) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"ok   {message}")
    else:
        FAIL += 1
        print(f"FAIL {message}")


def test_the_fixture_agrees_with_the_scoring_formula() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    runs = fixture["runs"]
    check(len(runs) > 0, "the fixture holds published summaries")
    for run in runs:
        wins, draws, losses = (int(part) for part in run["wdl"].split("/"))
        check(
            wins + draws + losses == run["games"],
            f"{run['candidate'][:7]}: the counts add up to the number of games",
        )
        percent = 100.0 * (wins + draws / 2) / run["games"]
        check(
            abs(percent - run["percent"]) <= 0.05,
            f"{run['candidate'][:7]}: the score matches (wins + draws / 2) / games",
        )
        check(
            abs(run["points"] - (wins + draws / 2)) <= 0.05,
            f"{run['candidate'][:7]}: the points match (wins + draws / 2)",
        )


def test_the_table_matches_the_tool() -> None:
    proc = subprocess.run(
        [sys.executable, str(TOOL), "--check"],
        capture_output=True,
        text=True,
        timeout=300,
    )
    check(
        proc.returncode == 0,
        f"the table in STATUS.md matches the published summaries ({proc.stdout.strip()})",
    )


def test_a_drifted_row_is_detected() -> None:
    """The check has to fail when the table and the fixture disagree."""
    original = STATUS.read_text(encoding="utf-8")
    try:
        broken = original.replace("| `98e5cd9` |", "| `98e5cd9` | x |", 1)
        # Change a count so that the row no longer agrees with the fixture.
        broken = re.sub(
            r"\| `98e5cd9` \| [^|]* \| (\d+)/(\d+)/(\d+) \|",
            lambda m: f"| `98e5cd9` | x | {m.group(1)}/{m.group(2)}/{int(m.group(3)) + 1} |",
            broken,
            count=1,
        )
        if broken == original:
            check(False, "the drifted-row fixture could not be built")
            return
        STATUS.write_text(broken, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(TOOL), "--check"],
            capture_output=True,
            text=True,
            timeout=300,
        )
        check(proc.returncode != 0, "a drifted row is detected by the check")
    finally:
        STATUS.write_text(original, encoding="utf-8")


def main() -> int:
    test_the_fixture_agrees_with_the_scoring_formula()
    test_the_table_matches_the_tool()
    test_a_drifted_row_is_detected()
    print(f"\n{PASS} checks passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
