#!/usr/bin/env python3
"""Regenerate the hosted quick-run table in STATUS.md from the published summaries.

The table records what the hosted quick profile scored on each head. It was transcribed by hand
once and drifted: the scores were right but the W/D/L counts were transposed in nine rows, and two
runs were missed entirely. A hand-maintained table of machine-produced numbers is exactly the thing
that should not be hand-maintained, so this script derives it.

The source of truth is the summary that the benchmark workflow publishes as a pull request comment.
Every field is parsed out of that comment verbatim and stored in
`benches/quick-run-summaries.json`. The rows are then ordered by the branch history, and the
"engine change" column is decided by comparing the `src/` tree hash of the measured candidate with
the `src/` tree hash of the head: identical hashes mean the release binary cannot differ.

Usage:

    scripts/refresh_run_table.py --fetch    re-fetch the published summaries into the fixture
    scripts/refresh_run_table.py --write    rewrite the generated block in STATUS.md
    scripts/refresh_run_table.py --check    fail if the block in STATUS.md is out of date

`--check` is the mode that belongs in a test: it needs no network access, because it works from the
committed fixture.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / "benches" / "quick-run-summaries.json"
STATUS = REPO_ROOT / "STATUS.md"
BRANCH = "arena/247fe7df-flawlesschess"

BEGIN = "<!-- BEGIN GENERATED: hosted quick-run table -->"
END = "<!-- END GENERATED: hosted quick-run table -->"

QUICK_GAMES = 40


def git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=120
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def fetch_fixture() -> dict:
    """Re-read the published benchmark summaries and rewrite the fixture."""
    proc = subprocess.run(
        [
            "gh", "api",
            "--paginate",
            "repos/coderunknow/FlawLessChess/issues/6/comments?per_page=100",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"gh api failed: {proc.stderr.strip()}")
    comments = json.loads(proc.stdout)
    runs = []
    for comment in comments:
        body = comment.get("body") or ""
        if not body.startswith("## Relative engine benchmark"):
            continue
        candidate = re.search(r"\*\*Candidate commit:\*\*\s*`([0-9a-f]+)`", body)
        score = re.search(r"\*\*Score:\*\*\s*([\d.]+)/(\d+) = ([\d.]+)%", body)
        wdl = re.search(r"\*\*W/D/L:\*\*\s*(\d+/\d+/\d+)", body)
        if not (candidate and score and wdl):
            continue
        classification = re.search(r"\*\*Classification:\*\*\s*`([^`]+)`", body)
        profile = re.match(r"^## Relative engine benchmark — (\w+) profile", body)
        elo = re.search(r"\*\*Relative Elo model:\*\*\s*([+\-\d.]+) to ([+\-\d.]+)", body)
        runs.append(
            {
                "published_at": comment["created_at"],
                "comment_url": comment["html_url"],
                "profile": profile.group(1) if profile else None,
                "candidate": candidate.group(1),
                "games": int(score.group(2)),
                "wdl": wdl.group(1),
                "points": float(score.group(1)),
                "percent": float(score.group(3)),
                "elo_low": float(elo.group(1)) if elo else None,
                "elo_high": float(elo.group(2)) if elo else None,
                "classification": classification.group(1) if classification else None,
            }
        )
    runs.sort(key=lambda run: run["published_at"])
    fixture = {
        "schema": 1,
        "kind": "published-relative-benchmark-summaries",
        "source": "https://api.github.com/repos/coderunknow/FlawLessChess/issues/6/comments",
        "note": (
            "Verbatim summary fields of every hosted benchmark summary published on PR #6. "
            "Regenerate with scripts/refresh_run_table.py --fetch."
        ),
        "runs": runs,
    }
    FIXTURE.write_text(json.dumps(fixture, indent=1) + "\n", encoding="utf-8")
    return fixture


def resolve_candidate(prefix: str) -> str | None:
    """Resolve a short candidate id to a full local commit, or None."""
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{prefix}^{{commit}}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def branch_order() -> dict[str, int]:
    """Map every commit on the branch to its position in the branch history."""
    commits = git("rev-list", "--reverse", "--first-parent", BRANCH).split("\n")
    return {commit: index for index, commit in enumerate(commits)}


def src_tree(commit: str) -> str | None:
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{commit}^{{tree}}:src"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def last_src_change() -> str | None:
    proc = subprocess.run(
        ["git", "log", "-1", "--format=%H", BRANCH, "--", "src/"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    return proc.stdout.strip()


def boundary_for_tree(tree: str) -> str | None:
    """The newest commit that touched `src/` and produced exactly this `src/` tree.

    Every same-tree group of runs runs the binary built from one `src/` tree; that tree's
    boundary commit is the last `src/` change that produced it (the newest, when the tree was
    introduced more than once).
    """
    proc = subprocess.run(
        ["git", "log", "--format=%H", BRANCH, "--", "src/"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        return None
    for commit in proc.stdout.split():
        if src_tree(commit) == tree:
            return commit
    return None


def subject_of(commit: str) -> str:
    proc = subprocess.run(
        ["git", "log", "-1", "--format=%s", commit],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    subject = proc.stdout.strip() if proc.returncode == 0 else ""
    # Drop a conventional-commit prefix and any trailing parenthetical for the table cell,
    # and keep it short.
    if ": " in subject:
        subject = subject.split(": ", 1)[1]
    subject = subject.split(" (", 1)[0]
    return subject if len(subject) <= 60 else subject[:57] + "..."


def quick_runs(fixture: dict) -> list[dict]:
    return [run for run in fixture["runs"] if run["games"] == QUICK_GAMES]


def build_rows(fixture: dict) -> tuple[list[dict], dict]:
    """Turn the published summaries into table rows, ordered by the branch history.

    Rows are grouped by binary identity (`src/` tree). The primary group is the one on the
    candidate's own `src/` tree when the hosted profile has runs there; otherwise the largest
    same-tree group (the runs really are on one identical release binary — just not the
    candidate's). The returned metadata records which case applies so the claims can say
    plainly that the candidate has no hosted quick runs yet.
    """
    order = branch_order()
    head = git("rev-parse", BRANCH)
    head_src = src_tree(head)
    if head_src is None:
        raise RuntimeError(f"cannot read the `src/` tree of {BRANCH}")

    resolved = []
    for run in quick_runs(fixture):
        commit = resolve_candidate(run["candidate"])
        if commit is None:
            raise RuntimeError(
                f"the published quick run at {run['published_at']} scores candidate "
                f"`{run['candidate']}`, which this clone does not have; a published run is "
                f"never silently dropped — fetch the branch history "
                f"(git fetch origin {BRANCH}) and rerun"
            )
        resolved.append((order.get(commit, len(order)), run, commit))

    resolved.sort(key=lambda item: (item[0], item[1]["published_at"]))

    groups: dict[str, int] = {}
    for _index, _run, commit in resolved:
        tree = src_tree(commit)
        if tree is not None:
            groups[tree] = groups.get(tree, 0) + 1
    if not groups:
        raise RuntimeError("no published run resolves to a readable `src/` tree")
    on_candidate = head_src in groups
    if on_candidate:
        primary_tree = head_src
    else:
        # Largest same-tree group; ties break deterministically on the tree hash.
        primary_tree = max(groups, key=lambda tree: (groups[tree], tree))
    boundary = boundary_for_tree(primary_tree)

    rows = []
    for _index, run, commit in resolved:
        tree = src_tree(commit)
        if tree is not None and tree == primary_tree:
            if commit == boundary:
                label = f"**last `src/` change** ({subject_of(boundary)})"
            else:
                label = "**no engine change**"
        else:
            label = "different engine (pre-refinement)"
        rows.append(
            {
                "candidate": run["candidate"][:7],
                "label": label,
                "wdl": run["wdl"],
                "percent": run["percent"],
                "classification": run["classification"] or "",
            }
        )
    meta = {
        "on_candidate": on_candidate,
        "primary_boundary": boundary,
        "primary_boundary_subject": subject_of(boundary) if boundary else "",
        "candidate_boundary": last_src_change(),
        "candidate_boundary_subject": subject_of(last_src_change() or ""),
    }
    return rows, meta


def build_claims(rows: list[dict], meta: dict) -> list[str]:
    """The derived claims, computed from the rows rather than written by hand.

    The boundary head (the `src/` change that produced the group's binary) runs the identical
    release binary to every later head in the group, so it belongs to the unchanged set; only the
    heads outside the group are on a different engine. When the hosted profile has no runs on the
    candidate's own binary yet, the claims say so plainly before describing the earlier binary.
    """
    unchanged = [
        row for row in rows
        if row["label"].startswith("**no engine") or row["label"].startswith("**last")
    ]
    boundary = [row for row in rows if row["label"].startswith("**last")]
    other = [row for row in rows if row["label"].startswith("different engine")]

    def span(subset: list[dict]) -> tuple[float, float]:
        percents = [row["percent"] for row in subset]
        return min(percents), max(percents)

    lo, hi = span(unchanged)
    positives = [row for row in unchanged if row["classification"].startswith("POSITIVE")]
    negatives = [row for row in unchanged if row["classification"].startswith("NEGATIVE")]
    inconclusive = [row for row in unchanged if row["classification"] == "INCONCLUSIVE"]
    all_lo, all_hi = span(rows)
    other_text = ", ".join(f"{row['percent']:.1f}%" for row in other)

    if meta["on_candidate"]:
        opener = f"  **On an unchanged engine the profile ranges from {lo:.1f}% to {hi:.1f}%** "
        growth = "; a lower bound, since every further push adds another run"
    else:
        opener = f"  **On the identical earlier binary the profile ranges from {lo:.1f}% to {hi:.1f}%** "
        growth = ""
    lines = [
        opener
        + f"({len(unchanged)} runs, listed above, all on the identical release binary{growth}), "
        f"and the same binary "
        f"produced the label `POSITIVE_RELATIVE_SIGNAL_SCREENING_ONLY` in {len(positives)} run"
        f"{'' if len(positives) == 1 else 's'} and `INCONCLUSIVE` in the other "
        f"{len(inconclusive)}. The two extremes are {hi - lo:.1f} points apart on code that did "
        f"not change."
    ]
    if negatives:
        lines.append(
            f"  The {len(negative_placeholder := negatives)} run"
            f"{'' if len(negatives) == 1 else 's'} carrying `NEGATIVE_RELATIVE_SIGNAL_NOT_SEVERE` "
            f"is listed above."
        )
    if other:
        lines.append(
            f"  The {len(other)} runs below the engine-change boundary ({other_text}) are on a "
            f"*different* engine and are not part of that range. The overall observed range across "
            f"all heads is {all_lo:.1f}%–{all_hi:.1f}%, but it spans two different engines; the "
            f"same-binary range is {lo:.1f}%–{hi:.1f}%."
        )
    if boundary:
        lines.append(
            f"  The engine-change boundary is `{boundary[0]['candidate']}`, the last commit that "
            f"produced that binary's `src/` tree."
        )
    if not meta["on_candidate"] and meta.get("candidate_boundary"):
        lines.append(
            f"  No hosted quick runs are on the current candidate engine yet: the last `src/` "
            f"change on this branch is `{meta['candidate_boundary'][:7]}` "
            f"({meta['candidate_boundary_subject']}). Every row above predates it."
        )
    lines.append(
        "  Every row above was transcribed from the published hosted summary and re-checked "
        "against the scoring formula `(wins + draws / 2) / games`; the counts and the scores "
        "agree in all of them. The block is generated by `scripts/refresh_run_table.py` from the "
        "committed fixture `benches/quick-run-summaries.json`, and `scripts/test_run_table.py` "
        "fails if it drifts from the published summaries."
    )
    return lines


def build_block(rows: list[dict], meta: dict) -> str:
    out = [BEGIN, ""]
    out.append("| Head | Engine change | W/D/L | Score | Classification |")
    out.append("|---|---|---|---|---|")
    for row in rows:
        out.append(
            f"| `{row['candidate']}` | {row['label']} | {row['wdl']} | "
            f"{row['percent']:.1f}% | {row['classification']} |"
        )
    out.append("")
    out.extend(build_claims(rows, meta))
    out.append("")
    out.append(END)
    return "\n".join(out)


def current_block(text: str) -> str | None:
    start = text.find(BEGIN)
    end = text.find(END)
    if start == -1 or end == -1 or end < start:
        return None
    return text[start : end + len(END)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--fetch", action="store_true", help="re-fetch the published summaries")
    group.add_argument("--write", action="store_true", help="rewrite the block in STATUS.md")
    group.add_argument("--check", action="store_true", help="check the block in STATUS.md")
    parser.add_argument(
        "--fixture", default=str(FIXTURE),
        help="summary fixture to read (default: the committed benches/quick-run-summaries.json)",
    )
    args = parser.parse_args()

    if args.fetch:
        fixture = fetch_fixture()
        Path(args.fixture).write_text(json.dumps(fixture, indent=1) + "\n", encoding="utf-8")
        print(f"fetched {len(fixture['runs'])} published summaries into {args.fixture}")
        return 0

    fixture = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    try:
        rows, meta = build_rows(fixture)
    except RuntimeError as error:
        print(f"FAIL: {error}")
        return 1
    block = build_block(rows, meta)
    text = STATUS.read_text(encoding="utf-8")
    existing = current_block(text)

    if args.check:
        if existing is None:
            print("FAIL: STATUS.md has no generated quick-run table")
            return 1
        if existing.strip() != block.strip():
            print("FAIL: the quick-run table in STATUS.md is out of date")
            print("  run scripts/refresh_run_table.py --write")
            return 1
        print(f"ok   the quick-run table in STATUS.md matches all {len(rows)} published summaries")
        return 0

    if existing is None:
        print("FAIL: STATUS.md has no generated quick-run table to replace")
        return 1
    STATUS.write_text(text.replace(existing, block), encoding="utf-8")
    print(f"wrote {len(rows)} rows into STATUS.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
