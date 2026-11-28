#!/usr/bin/env python3
"""approve_power_assessment.py — embed the reviewed approval block into a power
assessment report (bench output of scripts/power_analysis_v2.py).

The prospective power assessment gates the confirmatory campaign: per the
PREREGISTRATION.md decision rule it needs an explicit human authorization
before its selected design may be dispatched. This tool records that
authorization (who, when, on what evidence, under which decision rule) instead
of leaving ``approval`` null, so the reports are dispatch-eligible rather than
EXPLORATORY. It only ever ADDS the block to an existing report and refuses to
touch a report whose approval is already set (no silent rewriting).

Usage:
  approve_power_assessment.py REPORT [REPORT ...] \
      --reviewer "..." --reviewed-at ISO8601 --evidence-ref "..." \
      --decision-rule "..."
"""
import argparse
import json
import os
import sys


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("reports", nargs="+")
    ap.add_argument("--reviewer", required=True)
    ap.add_argument("--reviewed-at", required=True, help="ISO 8601 timestamp")
    ap.add_argument("--evidence-ref", required=True,
                    help="evidence chain the authorization rests on")
    ap.add_argument("--decision-rule", required=True,
                    help="registered decision rule the design was selected under")
    ap.add_argument("--machine-review", default=None,
                    help="optional machine code-review record (scope, findings, commits)")
    a = ap.parse_args()

    block = {
        "reviewer": a.reviewer,
        "reviewed_at": a.reviewed_at,
        "evidence_ref": a.evidence_ref,
        "decision_rule": a.decision_rule,
    }
    if a.machine_review:
        block["machine_review"] = a.machine_review

    for path in a.reports:
        with open(path, encoding="utf-8") as handle:
            report = json.load(handle)
        existing = report.get("approval")
        if existing:
            sys.exit(f"{path}: approval block already present ({existing.get('reviewer')}); "
                     "refusing to overwrite")
        if report.get("monte_carlo_replicates") != 250000:
            sys.exit(f"{path}: monte_carlo_replicates {report.get('monte_carlo_replicates')} — "
                     "only the registered 250,000-replicate runs are dispatch-eligible")
        if report.get("status") != "PASS":
            sys.exit(f"{path}: status {report.get('status')} — approval requires a PASS report")
        if not report.get("eligible_for_confirmatory_dispatch"):
            sys.exit(f"{path}: report is not dispatch-eligible")
        report["approval"] = block
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
            handle.write("\n")
        print(f"approved {path}: {block['reviewer']} at {block['reviewed_at']} -> "
              f"{report['design']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
