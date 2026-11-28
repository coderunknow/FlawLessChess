#!/usr/bin/env python3
"""Regression tests for the benchmark request resolver in the workflow.

The resolver decides what a hosted benchmark run measures. Two of its decisions are easy to get
wrong in a way that is silent: a request that names something the job would ignore is accepted and
then measured as something else. The tests below exercise the resolver's own Python, extracted from
the committed workflow, so the rules are pinned:

* the `extended` profile runs the full candidate and the frozen batch suites, and a request that
  asks for anything else is rejected instead of quietly measured as something else;
* the `screen` profile does run the ablation variants, so those requests stay valid;
* an unknown profile is rejected.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "relative-benchmark.yml"

PASS = 0
FAIL = 0

FULL = {"name": "full", "ablate": ""}
ABLATED = {"name": "no-space", "ablate": "space"}
BATCH_SUITES = [
    "benches/rating-openings-100-batchA.txt",
    "benches/rating-openings-100-batchB.txt",
]


def check(cond: bool, message: str) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"ok   {message}")
    else:
        FAIL += 1
        print(f"FAIL {message}")


def resolver_source() -> str:
    """The resolver's Python, extracted from the committed workflow."""
    text = WORKFLOW.read_text(encoding="utf-8")
    start_marker = "python3 - <<'PY' >> \"$GITHUB_OUTPUT\"\n"
    start = text.index(start_marker) + len(start_marker)
    # The heredoc terminator is the first following line whose stripped content is exactly "PY".
    rest = text[start:]
    lines = rest.splitlines(keepends=True)
    collected: list[str] = []
    for line in lines:
        if line.strip() == "PY":
            break
        collected.append(line)
    return textwrap.dedent("".join(collected))


def dispatch_source() -> str:
    """The resolver's shell for a manual dispatch, extracted from the committed workflow."""
    text = WORKFLOW.read_text(encoding="utf-8")
    start_marker = 'if [ "$EVENT_NAME" = "workflow_dispatch" ]; then\n'
    start = text.index(start_marker)
    end = text.index("\n          fi\n", start) + len("\n          fi\n")
    return textwrap.dedent(text[start:end])



def resolve(request: dict) -> tuple[int, str, str]:
    """Run the resolver against a request; return (rc, stdout, last stderr line)."""
    code = resolver_source()
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "benches").mkdir()
        (Path(td) / "benches" / "benchmark-request.json").write_text(
            json.dumps(request), encoding="utf-8"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, cwd=td
        )
    stderr = proc.stderr.strip().splitlines()
    return proc.returncode, proc.stdout.strip(), stderr[-1] if stderr else ""


def test_the_extended_profile_rejects_what_it_cannot_measure() -> None:
    rc, out, _err = resolve(
        {
            "schema": 1,
            "profile": "extended",
            "seed": 20261201,
            "variants": [FULL],
            "opening_suites": BATCH_SUITES,
        }
    )
    check(rc == 0, "the shipped extended request resolves")
    check("profile=extended" in out, "the extended profile is exported")
    check(
        "suites=benches/rating-openings-100-batchA.txt,benches/rating-openings-100-batchB.txt" in out,
        "the frozen batch suites are exported",
    )

    rc, _out, err = resolve(
        {
            "schema": 1,
            "profile": "extended",
            "seed": 20261201,
            "variants": [ABLATED],
            "opening_suites": BATCH_SUITES,
        }
    )
    check(rc != 0, "an extended request with an ablation variant is rejected")
    check("ablation variants" in err, "the rejection names the ablation variants")

    rc, _out, err = resolve(
        {
            "schema": 1,
            "profile": "extended",
            "seed": 20261201,
            "variants": [FULL, ABLATED],
            "opening_suites": BATCH_SUITES,
        }
    )
    check(rc != 0, "an extended request with more than one variant is rejected")

    rc, _out, err = resolve(
        {
            "schema": 1,
            "profile": "extended",
            "seed": 20261201,
            "variants": [FULL],
            "opening_suites": ["benches/openings-20.txt"],
        }
    )
    check(rc != 0, "an extended request with other opening suites is rejected")
    check("frozen to the two batch opening suites" in err, "the rejection names the frozen suites")


def test_the_screen_profile_still_runs_the_ablation_variants() -> None:
    variants = [
        FULL,
        ABLATED,
        {"name": "no-counter-move", "ablate": "counter_move"},
        {"name": "no-new-terms", "ablate": "space,counter_move,outpost"},
    ]
    rc, out, _err = resolve(
        {
            "schema": 1,
            "profile": "screen",
            "seed": 20261130,
            "variants": variants,
            "opening_suites": BATCH_SUITES,
        }
    )
    check(rc == 0, "the ablation request resolves")
    check("profile=screen" in out, "the screen profile is exported")
    for variant in variants:
        check(variant["name"] in out, f"the variant {variant['name']} is exported")
    check("counter_move" in out, "the ablation mask of the counter-move variant is exported")


def test_an_unknown_profile_is_rejected() -> None:
    rc, _out, err = resolve(
        {"schema": 1, "profile": "nonsense", "seed": 1, "variants": [FULL]}
    )
    check(rc != 0, "an unknown profile is rejected")
    check("unknown benchmark profile" in err, "the rejection names the unknown profile")


def dispatch(profile: str, seed: str) -> tuple[int, str]:
    """Run the manual-dispatch branch; return (rc, the resolved outputs)."""
    script = dispatch_source()
    with tempfile.TemporaryDirectory() as td:
        out_file = Path(td) / "github_output"
        env = {
            "EVENT_NAME": "workflow_dispatch",
            "INPUT_PROFILE": profile,
            "INPUT_SEED": seed,
            "GITHUB_OUTPUT": str(out_file),
        }
        proc = subprocess.run(
            ["bash", "-c", script], capture_output=True, text=True, env=env, timeout=60
        )
        resolved = out_file.read_text(encoding="utf-8") if out_file.is_file() else ""
    return proc.returncode, resolved


def test_the_manual_dispatch_branch_resolves_the_right_suites() -> None:
    rc, resolved = dispatch("quick", "20261124")
    check(rc == 0, "a manual quick dispatch resolves")
    check("profile=quick" in resolved, "the quick profile is exported")
    check("seed=20261124" in resolved, "the seed is exported")
    check("suites=benches/openings-20.txt" in resolved, "the quick profile uses the 20-opening suite")
    check(
        "suites=benches/rating-openings-100-batchA.txt,benches/rating-openings-100-batchB.txt"
        not in resolved,
        "the quick profile does not use the 100-opening batch suites",
    )

    for profile in ("screen", "extended"):
        rc, resolved = dispatch(profile, "20261201")
        check(rc == 0, f"a manual {profile} dispatch resolves")
        check(f"profile={profile}" in resolved, f"the {profile} profile is exported")
        check(
            "suites=benches/rating-openings-100-batchA.txt,benches/rating-openings-100-batchB.txt"
            in resolved,
            f"the {profile} profile uses the frozen 100-opening batch suites",
        )
        check(
            "suites=benches/openings-20.txt" not in resolved,
            f"the {profile} profile does not use the 20-opening quick suite",
        )

    rc, _resolved = dispatch("nonsense", "20261201")
    check(rc != 0, "a manual dispatch with an unknown profile is rejected")
    rc, _resolved = dispatch("quick", "not-a-number")
    check(rc != 0, "a manual dispatch with a non-numeric seed is rejected")
    rc, _resolved = dispatch("quick", "")
    check(rc != 0, "a manual dispatch with an empty seed is rejected")



def main() -> int:
    test_the_manual_dispatch_branch_resolves_the_right_suites()
    test_the_extended_profile_rejects_what_it_cannot_measure()
    test_the_screen_profile_still_runs_the_ablation_variants()
    test_an_unknown_profile_is_rejected()
    print(f"\n{PASS} checks passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
