#!/usr/bin/env python3
"""Create a fail-closed RATING-100 confirmatory dispatch marker.

A full dispatch schedules all 50 two-game opening shards. A recovery dispatch
re-reads every committed per-run evidence directory and schedules only missing
schedule indices, including a single missing AB or BA leg. Identity drift,
duplicate counted slots, or a pre-existing canonical result are fatal.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys

# Sample designs eligible for confirmatory dispatch. Each design fixes its registered suites,
# its opening-cluster count and its paired repetitions per opening (one repetition = 2 games,
# AB/BA). The power assessment selects the design (PREREGISTRATION.md decision rule); this
# generator and the rating-run dispatch gate refuse anything else.
DESIGNS = {
    "rating-100-v1": {
        "suites": {
            "A": ("benches/rating-openings-100-batchA.txt",
                  "5abdcdbddec0f22d7e6eff8974ee402363c8c3df318b8110d7204adf69f5c1df"),
            "B": ("benches/rating-openings-100-batchB.txt",
                  "ccb4901742eca25b0b10f1a3c9fdfc17b2967a1939c2d7e466c2c5495b6d4253"),
        },
        "clusters": 50,
        "repetitions": 1,
    },
    "rating-120-v1": {
        "suites": {
            "A": ("benches/rating-openings-batchA.txt",
                  "2c4a54d8a16f36d597cb2378ff74c1faafc636568647a257313274bd0969fc96"),
            "B": ("benches/rating-openings-batchB.txt",
                  "744a3981cc312a676ba259962309858b7d2fc645094bf2dccf5391e77f2f9dd4"),
        },
        "clusters": 60,
        "repetitions": 1,
    },
    "rating-240-v1": {
        "suites": {
            "A": ("benches/rating-openings-batchA.txt",
                  "2c4a54d8a16f36d597cb2378ff74c1faafc636568647a257313274bd0969fc96"),
            "B": ("benches/rating-openings-batchB.txt",
                  "744a3981cc312a676ba259962309858b7d2fc645094bf2dccf5391e77f2f9dd4"),
        },
        "clusters": 60,
        "repetitions": 2,
    },
    "rating-360-v1": {
        "suites": {
            "A": ("benches/rating-openings-batchA.txt",
                  "2c4a54d8a16f36d597cb2378ff74c1faafc636568647a257313274bd0969fc96"),
            "B": ("benches/rating-openings-batchB.txt",
                  "744a3981cc312a676ba259962309858b7d2fc645094bf2dccf5391e77f2f9dd4"),
        },
        "clusters": 60,
        "repetitions": 3,
    },
}
TIME_CONTROL = {"mode": "clock", "period_moves": 40, "period_seconds": 900.0}


def die(message: str) -> None:
    print(f"make_batch_dispatch: BLOCKED — {message}", file=sys.stderr)
    raise SystemExit(1)


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_suite(path: str, wanted_sha: str, expected_rows: int) -> list[str]:
    if sha256_file(path) != wanted_sha:
        die(f"{path}: SHA-256 does not match the append-only preregistration")
    with open(path, encoding="utf-8") as handle:
        rows = [
            line.partition("|")[0].strip()
            for line in handle
            if line.strip() and not line.lstrip().startswith("#")
        ]
    if len(rows) != expected_rows or len(set(rows)) != expected_rows:
        die(f"{path}: expected exactly {expected_rows} unique opening-cluster names")
    return rows


def load_anchor_sha(pool_path: str, anchor: str) -> str:
    try:
        with open(pool_path, encoding="utf-8") as handle:
            pool = json.load(handle)
    except (OSError, ValueError) as exc:
        die(f"cannot read frozen anchor pool: {exc}")
    matches = [entry for entry in pool.get("engines", []) if entry.get("key") == anchor]
    if len(matches) != 1:
        die(f"anchor {anchor!r} is not present exactly once in the frozen pool")
    value = matches[0].get("sha256", "")
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        die(f"anchor {anchor!r} has no valid frozen binary SHA-256")
    return value


def validate_power(path: str, design: str, suite_a_sha: str, suite_b_sha: str, engine_sha: str) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            power = json.load(handle)
    except (OSError, ValueError) as exc:
        die(f"cannot read prospective power assessment: {exc}")
    if power.get("design") != design or power.get("sample_design") != design:
        die(f"power assessment is not for sample design {design!r}")
    if power.get("status") != "PASS" or power.get("eligible_for_confirmatory_dispatch") is not True:
        die("prospective power assessment is not an evidence-backed PASS")
    suites = power.get("opening_suites", {})
    if suites.get("batch_a_sha256") != suite_a_sha or suites.get("batch_b_sha256") != suite_b_sha:
        die("power assessment opening-suite hashes differ from the dispatch suites")
    if power.get("engine_sha256") != engine_sha:
        die("power assessment was computed from a different engine binary SHA-256")
    approval = power.get("approval")
    if not isinstance(approval, dict) or not all(
        isinstance(approval.get(field), str) and approval[field].strip()
        for field in ("reviewer", "reviewed_at", "evidence_ref", "decision_rule")
    ):
        die("PASS assessment requires reviewer, timestamp, evidence reference and decision rule")
    return power


def read_committed_runs(
    runs_root: str,
    *,
    batch: str,
    anchor: str,
    engine_sha: str,
    anchor_sha: str,
    suite_sha: str,
    opening_names: list[str],
    clusters: int,
    repetitions: int,
) -> dict[int, list[int]]:
    """Return missing frozen schedule indices per opening shard.

    Partial AB/BA pairs are valid recovery state; duplicate counted indices,
    identity drift and malformed records are rejected.
    """
    if not os.path.isdir(runs_root):
        return {}
    run_names = sorted(name for name in os.listdir(runs_root) if name.startswith("run-"))
    if not run_names:
        return {}

    seen: dict[int, dict] = {}
    for run_name in run_names:
        root = os.path.join(runs_root, run_name)
        games_path = os.path.join(root, "games.jsonl")
        manifest_path = os.path.join(root, "manifest.json")
        if not (os.path.isfile(games_path) and os.path.isfile(manifest_path)):
            die(f"{run_name}: missing committed games.jsonl or manifest.json")
        try:
            with open(manifest_path, encoding="utf-8") as handle:
                manifest = json.load(handle)
        except (OSError, ValueError) as exc:
            die(f"{run_name}: cannot read manifest: {exc}")
        wanted_identity = {
            "batch": batch,
            "anchor": anchor,
            "engine_sha256": engine_sha,
            "anchor_sha256": anchor_sha,
            "opening_suite_sha256": suite_sha,
            "time_control": TIME_CONTROL,
        }
        actual_identity = {key: manifest.get(key) for key in wanted_identity}
        if actual_identity != wanted_identity:
            die(f"{run_name}: manifest identity/time-control mismatch: {actual_identity}")
        if manifest.get("merged_sha256") != sha256_file(games_path):
            die(f"{run_name}: manifest merged_sha256 does not match committed games.jsonl")

        records = []
        counted = []
        with open(games_path, encoding="utf-8") as handle:
            for line_no, raw in enumerate(handle, 1):
                if not raw.strip():
                    continue
                try:
                    game = json.loads(raw)
                except ValueError as exc:
                    die(f"{run_name}:{line_no}: invalid JSON: {exc}")
                records.append(game)
                if game.get("counted") is True:
                    counted.append(game)
        if manifest.get("n_counted") != len(counted):
            die(f"{run_name}: n_counted disagrees with games.jsonl")
        if manifest.get("n_attempts") != len(records):
            die(f"{run_name}: n_attempts disagrees with games.jsonl")

        schedule_len = clusters * 2 * repetitions
        for game in counted:
            index = game.get("schedule_index")
            if type(index) is not int or not 0 <= index < schedule_len:
                die(f"{run_name}: counted record has invalid schedule_index {index!r}")
            if index in seen:
                die(f"duplicate counted schedule_index {index} across committed runs")
            if game.get("engine_error") or game.get("adjudicated") is False:
                die(f"{run_name}: invalid counted record at schedule_index {index}")
            if game.get("result") not in ("1-0", "0-1", "1/2-1/2"):
                die(f"{run_name}: invalid counted result at schedule_index {index}")
            slots = 2 * repetitions
            shard_index = index // slots
            offset = index - shard_index * slots
            expected_opening = opening_names[shard_index]
            expected_pair = "AB" if offset % 2 == 0 else "BA"
            if game.get("opening") != expected_opening or game.get("color_pair") != expected_pair:
                die(f"{run_name}: schedule_index {index} does not match "
                    f"{expected_opening}/{expected_pair}")
            # Seated engine identities follow the schedule's pair leg: AB seats
            # Flawless white / anchor black, BA reverses them. An earlier cut
            # hard-coded the AB seating for every slot and rejected valid BA
            # records, making partial-run recovery impossible (CodeRabbit
            # review 2026-11-27).
            white = str(game.get("white", "")).casefold()
            black = str(game.get("black", "")).casefold()
            if expected_pair == "AB":
                ok_seats = white == "flawless" and black == anchor.casefold()
            else:
                ok_seats = white == anchor.casefold() and black == "flawless"
            if not ok_seats:
                die(f"{run_name}: counted slot {index} has wrong seated engine identities")
            seen[index] = game

    missing_by_shard = {}
    slots = 2 * repetitions
    for shard_index in range(clusters):
        expected_indices = {shard_index * slots + offset for offset in range(slots)}
        missing = sorted(expected_indices - set(seen))
        if missing:
            missing_by_shard[shard_index] = missing
    return missing_by_shard


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hash", required=True, help="frozen engine binary SHA-256")
    parser.add_argument("--design", required=True, choices=sorted(DESIGNS),
                        help="sample design selected by the reviewed power assessment")
    parser.add_argument("--target-commit", required=True, help="full 40-character source commit")
    parser.add_argument("--batch", required=True, choices=("A", "B"))
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--anchor", required=True)
    parser.add_argument("--revision", required=True, type=int)
    parser.add_argument("--recovery", action="store_true",
                        help="schedule only shards missing from committed per-run evidence")
    parser.add_argument("--power-assessment", default="benches/rating-100-power-assessment.json")
    parser.add_argument("--pool", default="benches/anchor-pool.json")
    parser.add_argument("--out", default="benches/dispatch.json")
    args = parser.parse_args()

    if not re.fullmatch(r"[0-9a-f]{64}", args.hash):
        die("--hash must be 64 lowercase hexadecimal characters")
    if not re.fullmatch(r"[0-9a-f]{40}", args.target_commit):
        die("--target-commit must be a full 40-character SHA")
    if not re.fullmatch(r"[a-z0-9._-]+", args.anchor):
        die("--anchor contains unsupported characters")
    if args.revision < 1:
        die("--revision must be positive")

    design = DESIGNS[args.design]
    clusters = design["clusters"]
    repetitions = design["repetitions"]
    suite_path, suite_sha = design["suites"][args.batch]
    opening_names = read_suite(suite_path, suite_sha, clusters)
    power = validate_power(args.power_assessment, args.design,
                           design["suites"]["A"][1], design["suites"]["B"][1], args.hash)
    anchor_sha = load_anchor_sha(args.pool, args.anchor)

    if os.path.exists(args.out):
        try:
            with open(args.out, encoding="utf-8") as handle:
                previous = json.load(handle)
        except (OSError, ValueError) as exc:
            die(f"cannot read current dispatch marker: {exc}")
        old_revision = previous.get("revision")
        if type(old_revision) is not int or args.revision <= old_revision:
            die(f"revision {args.revision} must be greater than current revision {old_revision!r}")

    runs_root = f"benches/evidence/confirmatory/batch{args.batch}/{args.anchor}"
    canonical = f"benches/evidence/batch{args.batch}/{args.anchor}"
    if os.path.exists(canonical):
        die(f"canonical evidence already exists at {canonical}; refusing another dispatch")

    missing_by_shard = read_committed_runs(
        runs_root, batch=args.batch, anchor=args.anchor, engine_sha=args.hash,
        anchor_sha=anchor_sha, suite_sha=suite_sha, opening_names=opening_names,
        clusters=clusters, repetitions=repetitions,
    )
    if args.recovery:
        if not os.path.isdir(runs_root) or not any(
            name.startswith("run-") for name in os.listdir(runs_root)
        ):
            die("no prior per-run evidence exists; use a full dispatch instead of --recovery")
        if not missing_by_shard:
            die(f"all {clusters * 2 * repetitions} counted schedule indices are already "
                "present in committed evidence")
        indices = sorted(missing_by_shard)
    else:
        if os.path.isdir(runs_root) and any(
            name.startswith("run-") for name in os.listdir(runs_root)
        ):
            die("prior per-run evidence already exists; use --recovery to fill missing schedule indices")
        indices = list(range(clusters))
        slots = 2 * repetitions
        missing_by_shard = {
            index: [index * slots + offset for offset in range(slots)] for index in indices
        }

    dispatch = {
        "schema": 1,
        "revision": args.revision,
        "purpose": "confirmatory",
        "sample_design": args.design,
        "description": (
            f"{clusters * 2 * repetitions} counted games = {clusters} disjoint opening clusters "
            f"x {repetitions} paired repetition(s) x AB/BA; "
            f"{len(indices)} of {clusters} shards for batch {args.batch}, anchor {args.anchor}; "
            f"40/15 wall-clock; engine SHA-256 {args.hash}; source commit {args.target_commit}."
        ),
        "preregistration": "PREREGISTRATION.md#rating-100-amendment-2026-11-16",
        "target_commit": args.target_commit,
        "engine_sha256": args.hash,
        "batch": args.batch,
        "anchor_id": args.anchor,
        "white_engine": "flawless",
        "black_engine": args.anchor,
        "shard_count": clusters,
        "shard_indices": indices,
        "schedule_indices_by_shard": {
            str(index): missing_by_shard[index] for index in indices
        },
        "opening_suite": suite_path,
        "opening_suite_sha256": suite_sha,
        "repetitions": repetitions,
        "seed": args.seed,
        "tc": "40/15",
        "recovery_dispatch": bool(args.recovery),
        "run_evidence": True,
        "power_assessment": args.power_assessment,
        "power_assessment_sha256": sha256_file(args.power_assessment),
    }
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(dispatch, handle, indent=2)
        handle.write("\n")
    print(f"wrote RATING-100 dispatch rev {args.revision}: batch={args.batch}, "
          f"anchor={args.anchor}, shards={indices}, recovery={args.recovery}; "
          f"power report sha256={dispatch['power_assessment_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
