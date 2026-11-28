#!/usr/bin/env python3
"""Regression suite for scripts/refresh_run_table.py pagination and fixture safety.

The old `--fetch` path called `json.loads` on `gh api --paginate` output as if it
were a single JSON document: with more than one page the documents run together
and the fetch crashed; and the fetch wrote the committed default fixture before
honouring `--fixture`, so an alternate destination could not be used without
corrupting `benches/quick-run-summaries.json`. This suite pins the fixed
behaviour: multi-page parsing, empty responses, malformed-response refusal,
deterministic ordering/fixture generation, and destination-only writes.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOL = REPO_ROOT / "scripts" / "refresh_run_table.py"
FIXTURE = REPO_ROOT / "benches" / "quick-run-summaries.json"

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


def load_tool():
    spec = importlib.util.spec_from_file_location("refresh_run_table", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def summary_comment(url: str, created: str, body: str) -> dict:
    return {"body": body, "created_at": created, "html_url": url}


SUMMARY_BODY = (
    "## Relative engine benchmark — quick profile\n"
    "**Candidate commit:** `0123456789abcdef0123456789abcdef01234567`\n"
    "**Score:** 21.5/40 = 53.75%\n"
    "**W/D/L:** 17/9/14\n"
    "**Classification:** `candidate-clearly-better`\n"
    "**Relative Elo model:** +12.5 to +25.0\n"
)


def test_two_pages_flatten() -> None:
    mod = load_tool()
    page1 = [{"id": 1, "created_at": "2026-01-01T00:00:00Z", "html_url": "u1", "body": "x"}]
    page2 = [
        {"id": 2, "created_at": "2026-01-02T00:00:00Z", "html_url": "u2", "body": "y"},
        {"id": 3, "created_at": "2026-01-03T00:00:00Z", "html_url": "u3", "body": "z"},
    ]
    slurped = json.dumps([page1, page2])
    items = mod.parse_comments_output(slurped)
    check(len(items) == 3, "two slurped pages flatten to three comments")
    check(items[0]["id"] == 1 and items[2]["id"] == 3, "page order is preserved")
    flat = json.dumps(page1 + page2)
    check(len(mod.parse_comments_output(flat)) == 3, "a flat single-page list still parses")


def test_empty_response() -> None:
    mod = load_tool()
    check(mod.parse_comments_output("") == [], "empty stdout yields an empty list")
    check(mod.parse_comments_output("[]") == [], "an empty JSON list yields an empty list")
    check(mod.parse_comments_output("[[], []]") == [], "empty pages yield an empty list")


def test_malformed_response_refused() -> None:
    mod = load_tool()
    for bad, label in [
        ("not json at all", "garbage"),
        ("[[{\"id\": 1}]", "truncated JSON"),
        ("{\"comments\": []}", "a JSON object instead of a list"),
        ("[[], {\"id\": 1}]", "mixed page/object shapes"),
    ]:
        try:
            mod.parse_comments_output(bad)
            check(False, f"malformed response refused: {label}")
        except RuntimeError:
            check(True, f"malformed response refused: {label}")


def test_deterministic_fixture_generation() -> None:
    mod = load_tool()
    comments = [
        summary_comment("u2", "2026-01-02T00:00:00Z", SUMMARY_BODY),
        summary_comment("u1", "2026-01-01T00:00:00Z", SUMMARY_BODY),
        summary_comment("u3", "2026-01-01T00:00:00Z", SUMMARY_BODY),
    ]
    first = mod.build_fixture(list(comments))
    second = mod.build_fixture(list(reversed(comments)))
    check(first == second, "fixture generation is order-independent")
    urls = [run["comment_url"] for run in first["runs"]]
    check(urls == ["u1", "u3", "u2"], "runs are ordered by (published_at, url) deterministically")
    check(
        json.dumps(first, indent=1) == json.dumps(second, indent=1),
        "the serialized fixture is byte-stable",
    )


def test_fetch_writes_only_the_selected_fixture() -> None:
    mod = load_tool()
    original = FIXTURE.read_text(encoding="utf-8")
    mod.fetch_comments = lambda: json.dumps([[summary_comment("u1", "2026-01-01T00:00:00Z", SUMMARY_BODY)]])
    with tempfile.TemporaryDirectory() as td:
        dest = Path(td) / "alternate.json"
        fixture = mod.fetch_fixture(dest)
        check(dest.exists(), "the selected fixture is written")
        check(len(fixture["runs"]) == 1, "the fetched fixture holds the parsed summaries")
        check(
            json.loads(dest.read_text(encoding="utf-8"))["runs"][0]["comment_url"] == "u1",
            "the alternate fixture holds the fetched data",
        )
    check(
        FIXTURE.read_text(encoding="utf-8") == original,
        "the committed default fixture is untouched by an alternate fetch",
    )


def main() -> int:
    test_two_pages_flatten()
    test_empty_response()
    test_malformed_response_refused()
    test_deterministic_fixture_generation()
    test_fetch_writes_only_the_selected_fixture()
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
