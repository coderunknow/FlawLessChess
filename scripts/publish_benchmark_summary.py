#!/usr/bin/env python3
"""Publish a relative-benchmark summary to channels that can be read back.

The Actions log host and the artifact storage host are not reachable from every
sandbox, so the benchmark evidence is also written to the job summary and, when a
pull request is associated with the branch, to a pull request comment. Both are
readable through the GitHub API alone.

Usage:
    publish_benchmark_summary.py --summary PATH [--title TEXT] [--no-comment]

The script never fails the workflow because of the comment step: a missing pull
request or a missing token only means that the summary stays in the job summary.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_ROOT = "https://api.github.com"


def render(summary: dict, title: str) -> str:
    elo = summary.get("relative_elo", {})
    score = summary.get("score", {})
    wdl = summary.get("wdl", {})
    display = elo.get("display") or ["?", "?"]
    lines = [
        f"## {title}",
        "",
        f"- **Classification:** `{summary.get('classification')}` (valid: `{summary.get('valid')}`)",
        f"- **W/D/L:** {wdl.get('W')}/{wdl.get('D')}/{wdl.get('L')} of {summary.get('games')}",
        f"- **Score:** {score.get('points', 0):.1f}/{summary.get('games', 0)} = {score.get('percent', 0):.1f}%",
        f"- **Relative Elo model:** {display[0]} to {display[1]} "
        "(opening-clustered 95% CI; not official and not absolute)",
        f"- **Candidate commit:** `{str(summary.get('candidate_commit'))[:12]}`",
        f"- **Baseline commit:** `{str(summary.get('baseline_commit'))[:12]}`",
        f"- **Opening clusters:** {summary.get('opening_clusters')}; "
        f"elapsed {summary.get('elapsed_seconds', 0):.1f}s",
        "- **Interpretation:** screening evidence only. An inconclusive or positive "
        "relative signal is not a strength claim and not an official rating.",
    ]
    errors = summary.get("validation_errors") or []
    if errors:
        lines += ["", "**Validation errors:**"] + [f"- {e}" for e in errors]
    return "\n".join(lines) + "\n"


def api_request(method: str, path: str, token: str, payload: dict | None = None) -> object:
    url = f"{API_ROOT}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    request.add_header("User-Agent", "flawless-benchmark-publisher")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if body.strip() else {}


def find_pull_request(repo: str, branch: str, token: str) -> int | None:
    if not repo or not branch:
        return None
    try:
        pulls = api_request(
            "GET", f"/repos/{repo}/pulls?state=open&per_page=100&head={repo.split('/')[0]}:{branch}", token
        )
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if isinstance(pulls, list) and pulls:
        return int(pulls[0]["number"])
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", required=True, help="path to summary.json")
    parser.add_argument("--title", default="Relative engine benchmark")
    parser.add_argument("--no-comment", action="store_true", help="only write the job summary")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--branch", default=os.environ.get("HEAD_BRANCH") or os.environ.get("GITHUB_HEAD_REF", ""))
    parser.add_argument("--token", default=os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", ""))
    args = parser.parse_args(argv)

    summary_path = Path(args.summary)
    if not summary_path.is_file():
        print(f"::error::benchmark summary not found: {summary_path}")
        return 1
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    body = render(summary, args.title)

    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as handle:
            handle.write(body)

    print(body)
    if args.no_comment:
        return 0

    pull_request = find_pull_request(args.repo, args.branch, args.token)
    if pull_request is None:
        print(f"::notice::no open pull request found for {args.branch or '?'}; summary kept in the job summary")
        return 0
    try:
        api_request(
            "POST",
            f"/repos/{args.repo}/issues/{pull_request}/comments",
            args.token,
            {"body": body},
        )
    except (urllib.error.URLError, OSError, ValueError) as error:
        print(f"::warning::could not post the benchmark summary to PR #{pull_request}: {error}")
        return 0
    print(f"::notice::benchmark summary posted to PR #{pull_request}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
