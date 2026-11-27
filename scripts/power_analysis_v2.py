#!/usr/bin/env python3
"""ENGINE-3 prospective power assessment: measured covariances, pre-registered design rule.

This supersedes the ENGINE-1 sensitivity report (``scripts/power_analysis.py``) for dispatch
purposes. Where the v1 report had to ASSUME the third-anchor cluster distribution and the
disjoint Batch-B distribution (and therefore blocked dispatch), this assessment measures all
covariance inputs from the preregistered SCREEN-E3 evidence on the actual candidate binary and
both registered suites, and selects the confirmatory sample design by the decision rule fixed in
PREREGISTRATION.md (2026-11-25) BEFORE that evidence was played:

    among {50x1 (100 games), 60x1 (120), 60x2 (240), 60x3 (360)} per anchor per batch,
    pick the SMALLEST design whose simulated probability that all three lower-bound decisions
    pass (Batch A, Batch B, combined) is >= 0.80 at a true 2,100 Elo alternative under 1.5x
    cluster-SD inflation, using 250,000 deterministic Monte Carlo replicates.

If no design qualifies, the report stays BLOCKED and confirmatory dispatch remains closed. This
delta-method sensitivity model is a planning instrument; the final evidence method remains the
registered opening-cluster bootstrap. The report never authorizes itself: the workflow gate
requires a human review block (``approval``) in addition to ``status == "PASS"``.

Usage:
    scripts/power_analysis_v2.py [--out benches/rating-100-power-assessment.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from collections import defaultdict

ENGINE3_SHA256 = "733de4e54f076fc4684ec0ad127975b526037fdedafa4fc15fc9bffccea1a407"
SUITE_A_SHA256 = "2c4a54d8a16f36d597cb2378ff74c1faafc636568647a257313274bd0969fc96"
SUITE_B_SHA256 = "744a3981cc312a676ba259962309858b7d2fc645094bf2dccf5391e77f2f9dd4"
SUBSET_A_SHA256 = "5abdcdbddec0f22d7e6eff8974ee402363c8c3df318b8110d7204adf69f5c1df"
SUBSET_B_SHA256 = "ccb4901742eca25b0b10f1a3c9fdfc17b2967a1939c2d7e466c2c5495b6d4253"

# Pool key -> (published elo, published ci95). Campaign label sets address these
# anchors under their campaign suffix (-e3, -e4 for suite A, -e4b for suite B).
ANCHOR_META = {
    "topple-0.1.1": (2324.0, 17.0),
    "topple-0.2.1": (2439.0, 14.0),
    "akimbo-0.1.1": (2441.0, 19.0),
}

# Campaign label sets: SCREEN-E3 labels its A- and B-suite runs identically; the
# SCREEN-E4 registration gives the B-suite runs their own -e4b labels so each
# run's in-run evidence writes its own directory without an overwrite collision.
DEFAULT_LABELS_A = ("topple-0.1.1-e3", "topple-0.2.1-e3", "akimbo-0.1.1-e3")
DEFAULT_LABELS_B = DEFAULT_LABELS_A
E4_LABELS_A = ("topple-0.1.1-e4", "topple-0.2.1-e4", "akimbo-0.1.1-e4")
E4_LABELS_B = ("topple-0.1.1-e4b", "topple-0.2.1-e4b", "akimbo-0.1.1-e4b")

_LABEL_SUFFIX = re.compile(r"^(?P<key>.+)-e\d+b?$")


def pool_key(label: str) -> str:
    """Strip the campaign suffix (`-e3`, `-e4`, `-e4b`, ...) and validate the anchor."""
    match = _LABEL_SUFFIX.match(label or "")
    if not match:
        raise ValueError(f"screening label {label!r} lacks a campaign suffix like '-e3' or '-e4b'")
    key = match.group("key")
    if key not in ANCHOR_META:
        raise ValueError(f"screening label {label!r} addresses unknown anchor {key!r}")
    return key


def validate_label_sets(labels_a: list[str], labels_b: list[str]) -> None:
    """Fail closed unless both suites score the same registered anchors, each exactly once."""
    if len(labels_a) != len(labels_b):
        raise ValueError("labels-a and labels-b must list the same anchors")
    if not labels_a:
        raise ValueError("at least one anchor label is required")
    keys_a = [pool_key(label) for label in labels_a]
    keys_b = [pool_key(label) for label in labels_b]
    if keys_a != keys_b:
        raise ValueError("labels-a and labels-b must address the same anchors in the same order")
    if len(set(keys_a)) != len(keys_a):
        raise ValueError("each registered anchor must appear exactly once per batch (duplicate keys)")
    if sorted(keys_a) != sorted(ANCHOR_META):
        raise ValueError(
            f"labels must address the three registered anchors exactly, got {sorted(set(keys_a))}")

# (design label, clusters per batch, paired repetitions per opening)
DESIGNS = [
    ("rating-100-v1", 50, 1),
    ("rating-120-v1", 60, 1),
    ("rating-240-v1", 60, 2),
    ("rating-360-v1", 60, 3),
]

THETA_GRID = (2050.0, 2100.0, 2150.0, 2200.0)
INFLATION_GRID = (1.0, 1.5, 2.0)
REPLICATES = 250_000
POWER_BAR = 0.80
DESIGN_RULE = (
    "smallest of {rating-100-v1 (50 clusters x 1 rep), rating-120-v1 (60 x 1), "
    "rating-240-v1 (60 x 2), rating-360-v1 (60 x 3)} per anchor per batch whose simulated "
    "P(all three lower bounds > 2000) >= 0.80 at a true 2,100 Elo alternative under 1.5x "
    "cluster-SD inflation (250,000 deterministic replicates); fixed in PREREGISTRATION.md "
    "2026-11-25 before the SCREEN-E3 evidence was played"
)


def sha256_jsonl_records(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "r", encoding="utf-8", newline=None) as handle:
        for chunk in iter(lambda: handle.read(1 << 20), ""):
            digest.update(chunk.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8"))
    return digest.hexdigest()


def read_manifest(games_path: str, label: str, batch: str, suite_sha: str, engine_sha: str,
                  exclude: frozenset = frozenset()) -> dict:
    manifest_path = os.path.join(os.path.dirname(games_path), "manifest.json")
    try:
        with open(manifest_path, encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read screening manifest {manifest_path}: {exc}") from exc
    if manifest.get("batch") != batch:
        raise ValueError(f"{manifest_path}: expected batch {batch!r}, got {manifest.get('batch')!r}")
    if manifest.get("anchor") != label:
        raise ValueError(f"{manifest_path}: expected label {label!r}, got {manifest.get('anchor')!r}")
    if manifest.get("opening_suite_sha256") != suite_sha:
        raise ValueError(f"{manifest_path}: suite hash differs from the registered suite")
    if manifest.get("n_counted") is None or manifest.get("n_attempts") != 120:
        raise ValueError(f"{manifest_path}: expected 120 attempts with recorded counted totals")
    observed_sha = manifest.get("engine_sha256", "")
    if not re.fullmatch(r"[0-9a-f]{64}", observed_sha):
        raise ValueError(f"{manifest_path}: missing or malformed engine SHA-256")
    if observed_sha != engine_sha:
        raise ValueError(
            f"{manifest_path}: this report is computed only from the frozen engine binary "
            f"({engine_sha}); observed {observed_sha}"
        )
    if manifest.get("merged_sha256") != sha256_jsonl_records(games_path):
        raise ValueError(f"{manifest_path}: merged_sha256 does not match games.jsonl")
    def is_counted(game: dict) -> bool:
        return bool(game.get("counted") is True and not game.get("engine_error")
                    and game.get("adjudicated") is not False)

    attempts = counted = excluded_records = excluded_counted = 0
    with open(games_path, encoding="utf-8") as games_file:
        for line_no, raw in enumerate(games_file, 1):
            if not raw.strip():
                continue
            try:
                game = json.loads(raw)
            except ValueError as exc:
                raise ValueError(f"{games_path}:{line_no}: invalid JSON game record") from exc
            if game.get("opening") in exclude:
                excluded_records += 1
                excluded_counted += 1 if is_counted(game) else 0
                continue
            attempts += 1
            counted += 1 if is_counted(game) else 0
    if attempts != 120 - excluded_records or counted != attempts:
        raise ValueError(
            f"{games_path}: expected every non-excluded attempt counted once "
            f"({120 - excluded_records} expected, {counted}/{attempts} counted/attempts observed)")
    if manifest.get("n_counted") != counted + excluded_counted:
        raise ValueError(f"{manifest_path}: manifest counted total does not match the games records")
    return manifest


def load_cluster_games(path: str, focus: str = "flawless",
                       exclude: frozenset = frozenset()) -> dict[str, list[float]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    colors: dict[str, list[str]] = defaultdict(list)
    with open(path, encoding="utf-8") as handle:
        for line_no, raw in enumerate(handle, 1):
            if not raw.strip():
                continue
            game = json.loads(raw)
            if game.get("opening") in exclude:
                continue
            if game.get("counted") is not True or game.get("engine_error") or game.get("adjudicated") is False:
                continue
            result = game.get("result")
            if result == "1-0":
                white_score = 1.0
            elif result == "0-1":
                white_score = 0.0
            elif result == "1/2-1/2":
                white_score = 0.5
            else:
                raise ValueError(f"{path}:{line_no}: counted game has invalid result {result!r}")
            white = str(game.get("white", "")).casefold()
            black = str(game.get("black", "")).casefold()
            if white == focus.casefold():
                score = white_score
                focus_color = "white"
            elif black == focus.casefold():
                score = 1.0 - white_score
                focus_color = "black"
            else:
                raise ValueError(f"{path}:{line_no}: neither side is focus engine {focus!r}")
            opening = game.get("opening")
            if not isinstance(opening, str) or not opening:
                raise ValueError(f"{path}:{line_no}: missing opening label")
            grouped[opening].append(score)
            colors[opening].append(focus_color)
    if not grouped:
        raise ValueError(f"no counted opening clusters in {path}")
    for opening, values in grouped.items():
        if len(values) != 2:
            raise ValueError(f"{path}: screening input must contain exactly two counted games per opening cluster")
        # The registered pairing is one AB and one BA leg (the focus engine colours
        # must reverse). Two rows of the same colouring are not a pair: their
        # difference is not an AB/BA difference and must not feed the paired
        # variance estimator.
        if sorted(colors[opening]) != ["black", "white"]:
            raise ValueError(
                f"{path}: cluster {opening!r} does not have exactly one focus-white and one "
                f"focus-black counted game (got {sorted(colors[opening])})")
    return dict(grouped)


def restrict_clusters(batch_games: dict[str, dict[str, list[float]]], wanted: set[str],
                      labels: list[str], batch: str) -> dict[str, dict[str, list[float]]]:
    """Restrict every label's cluster map to the design's wanted clusters (fail-loud).

    ``batch_games`` maps LABEL -> {cluster name -> per-game scores}, so the
    restriction must iterate labels and filter each label's cluster keys. An
    earlier cut filtered ``batch_games.items()`` by cluster names directly, which
    matched nothing (its keys are labels) and failed every design with a
    fabricated "missing clusters" error.
    """
    restricted: dict[str, dict[str, list[float]]] = {}
    for lab in labels:
        restricted[lab] = {k: v for k, v in batch_games[lab].items() if k in wanted}
        missing = wanted - set(restricted[lab])
        if missing:
            raise ValueError(f"{batch}/{lab}: screening evidence missing clusters {sorted(missing)[:5]}")
    return restricted


def variance_components(cluster_games: dict[str, list[float]]) -> tuple[float, float]:
    """Return (between-opening variance, per-game match variance) of the score.

    With two paired games per opening, the within-opening pair difference cancels the opening
    effect: E[(s1 - s2)^2] / 2 estimates the match-noise variance of a single game. The cluster
    mean then has variance opening + match / 2.
    """
    means = [sum(v) / 2 for v in cluster_games.values()]
    n = len(means)
    mean = sum(means) / n
    var_cluster = sum((x - mean) ** 2 for x in means) / (n - 1)
    diffs = [v[0] - v[1] for v in cluster_games.values()]
    sigma_m2 = sum(d * d for d in diffs) / len(diffs) / 2
    sigma_op2 = max(0.0, var_cluster - sigma_m2 / 2)
    return sigma_op2, sigma_m2


def opening_covariance(a: dict[str, list[float]], b: dict[str, list[float]]) -> float:
    """Between-opening covariance of two anchors' scores over shared openings.

    With two games per opening per anchor, the sample covariance of the cluster means equals the
    between-opening covariance (match noise is independent across anchors' separate games).
    """
    shared = sorted(set(a) & set(b))
    if len(shared) != len(a) or len(shared) != len(b):
        raise ValueError("anchor cluster sets differ; SCREEN-E3 runs must share opening labels")
    xs = [sum(a[k]) / 2 for k in shared]
    ys = [sum(b[k]) / 2 for k in shared]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (len(xs) - 1)


def _is_psd(matrix: list[list[float]], tol: float = 1e-9) -> bool:
    """Symmetric positive-semidefinite check via all principal minors (dim is tiny)."""
    n = len(matrix)
    for mask in range(1, 1 << n):
        idx = [i for i in range(n) if mask >> i & 1]
        m = len(idx)
        minor = [[matrix[idx[i]][idx[j]] for j in range(m)] for i in range(m)]
        # determinant by elimination
        det = 1.0
        work = [row[:] for row in minor]
        for col in range(m):
            pivot = max(range(col, m), key=lambda r: abs(work[r][col]))
            if abs(work[pivot][col]) < 1e-300:
                det = 0.0
                break
            if pivot != col:
                det = -det
            work[col], work[pivot] = work[pivot], work[col]
            det *= work[col][col]
            for r in range(col + 1, m):
                factor = work[r][col] / work[col][col]
                for c in range(col, m):
                    work[r][c] -= factor * work[col][c]
        if det < -tol:
            return False
    return True


def cluster_covariance_at(sigma_op: list[float], sigma_m: list[float],
                          cov_op: list[list[float]], repetitions: int) -> list[list[float]]:
    """Score-space covariance of cluster means at the design's games per cluster (2 x reps).

    The repeated-opening design shrinks the diagonal (match noise averages down)
    while the estimated off-diagonal entries stay fixed; a noisy off-diagonal can
    then make the matrix non-positive-semidefinite and give the sum of scores a
    negative modeled variance. Fail loud instead of simulating with an invalid
    covariance (CodeRabbit review 2026-11-27).
    """
    dim = len(sigma_op)
    out = [[0.0] * dim for _ in range(dim)]
    for i in range(dim):
        for j in range(dim):
            if i == j:
                out[i][i] = sigma_op[i] + sigma_m[i] / (2.0 * repetitions)
            else:
                out[i][j] = cov_op[i][j]
    if not _is_psd(out):
        raise ValueError(
            "design covariance matrix is not positive-semidefinite; the assessment is blocked "
            "(estimate the between-opening covariance jointly under a PSD constraint before use)")
    return out


def invert(matrix: list[list[float]]) -> list[list[float]]:
    n = len(matrix)
    work = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(work[row][col]))
        if abs(work[pivot][col]) < 1e-12:
            raise ValueError("singular sensitivity covariance matrix")
        work[col], work[pivot] = work[pivot], work[col]
        divisor = work[col][col]
        work[col] = [x / divisor for x in work[col]]
        for row in range(n):
            if row == col:
                continue
            factor = work[row][col]
            work[row] = [x - factor * y for x, y in zip(work[row], work[col])]
    return [row[n:] for row in work]


def quadratic(weights: list[float], matrix: list[list[float]]) -> float:
    return sum(weights[i] * weights[j] * matrix[i][j]
               for i in range(len(weights)) for j in range(len(weights)))


class DeterministicRng:
    """Small deterministic LCG + Box-Muller; keeps reports reproducible cross-platform."""

    def __init__(self, seed: int):
        self.state = seed & 0xFFFFFFFF

    def uniform(self) -> float:
        self.state = (1664525 * self.state + 1013904223) & 0xFFFFFFFF
        return (self.state + 0.5) / 4294967296.0

    def normal(self) -> float:
        u = max(1e-12, self.uniform())
        v = self.uniform()
        return math.sqrt(-2.0 * math.log(u)) * math.cos(2.0 * math.pi * v)


def _wls_variance(cov_score: list[list[float]], clusters: int, ratings: list[float],
                  calibration_sd: list[float], theta: float, inflation: float) -> dict:
    scores = [1.0 / (1.0 + 10.0 ** ((rating - theta) / 400.0)) for rating in ratings]
    slopes = [400.0 / (math.log(10.0) * p * (1.0 - p)) for p in scores]
    dim = len(ratings)
    infl2 = inflation * inflation
    match = [
        [cov_score[i][j] * infl2 * slopes[i] * slopes[j] / clusters for j in range(dim)]
        for i in range(dim)
    ]
    calibration = [[calibration_sd[i] ** 2 if i == j else 0.0 for j in range(dim)] for i in range(dim)]
    total = [[match[i][j] + calibration[i][j] for j in range(dim)] for i in range(dim)]
    inv_total = invert(total)
    row_sums = [sum(row) for row in inv_total]
    denominator = sum(row_sums)
    weights = [x / denominator for x in row_sums]
    return {
        "weights": weights,
        "var_match": quadratic(weights, match),
        "var_cal": quadratic(weights, calibration),
    }


def validate_exclusion_completeness(exclude: frozenset, pair_complete: dict[str, list[bool]]) -> None:
    """The registered rule excludes only clusters that LACK a counted AB/BA pair
    in at least one input; excluding a fully counted opening would silently alter
    the measured covariance (CodeRabbit review 2026-11-27)."""
    for name, complete_flags in pair_complete.items():
        if complete_flags and all(complete_flags):
            raise ValueError(
                f"--exclude-openings {name!r} names a fully counted AB/BA pair in every "
                "screening input; the registered rule only permits excluding clusters that "
                "lack a counted pair in at least one input")


def verify_suite_digest(path: str, expected: str) -> None:
    """Verify a suite file's raw bytes against its registered SHA-256 before any
    registered hash is reported alongside its opening names."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise ValueError(
            f"{path}: suite bytes hash to {digest.hexdigest()}, registered digest is {expected}")


def report_eligibility(selected: dict | None, replicates: int) -> tuple[str, bool]:
    """A dispatch-eligible report requires the registered 250,000 replicates; dev
    runs are exploratory and can never authorize dispatch (CodeRabbit 2026-11-27)."""
    if selected is None:
        return "BLOCKED", False
    if replicates != REPLICATES:
        return "EXPLORATORY", False
    return "PASS", True


def combined_bound(wa: dict, wb: dict, calibration_sd: list[float]) -> dict:
    """Registered combined bound (combine_batches / RATING_PROTOCOL.md §9.8).

    Match noise is pooled inverse-variance; the shared anchor calibration is added
    ONCE with the effective per-anchor weight lam*w_a + (1-lam)*w_b. Treating the
    batches as independent (1/(1/var_a + 1/var_b) over the totals) understates the
    combined variance whenever the anchor calibrations are shared.
    """
    v_a, v_b = wa["var_match"], wb["var_match"]
    if v_a <= 0 or v_b <= 0:
        raise ValueError("non-positive match variance in a batch")
    lam = (1.0 / v_a) / (1.0 / v_a + 1.0 / v_b)
    pooled_match = 1.0 / (1.0 / v_a + 1.0 / v_b)
    shared_cal = sum(
        (lam * wa["weights"][i] + (1.0 - lam) * wb["weights"][i]) ** 2 * calibration_sd[i] ** 2
        for i in range(len(calibration_sd)))
    return {
        "lam": lam,
        "pooled_match": pooled_match,
        "shared_cal": shared_cal,
        "var_total": pooled_match + shared_cal,
    }


def joint_scenario(theta: float, inflation: float,
                   cov_a: list[list[float]], cov_b: list[list[float]], clusters: int,
                   ratings: list[float], calibration_sd: list[float], replicates: int) -> dict:
    """Simulate the three registered lower-bound decisions jointly.

    Batch A is estimated on suite A's measured covariance, Batch B on suite B's; the published
    anchor calibrations are shared across both batches and the combined estimate, so ONE
    calibration error draw per anchor is sampled per replicate and each batch's GLS weights are
    applied to the same draws. The combined bound is the registered construction
    (``combine_batches`` / RATING_PROTOCOL.md §9.8): match noise pooled inverse-variance, the
    shared anchor calibration added once with the effective per-anchor weight. A decision passes
    when its unrounded lower bound is strictly above 2,000.
    """
    wa = _wls_variance(cov_a, clusters, ratings, calibration_sd, theta, inflation)
    wb = _wls_variance(cov_b, clusters, ratings, calibration_sd, theta, inflation)
    z95 = 1.959963984540054
    half_a = z95 * math.sqrt(wa["var_match"] + wa["var_cal"])
    half_b = z95 * math.sqrt(wb["var_match"] + wb["var_cal"])
    cb = combined_bound(wa, wb, calibration_sd)
    lam = cb["lam"]
    half_c = z95 * math.sqrt(cb["var_total"])
    se_cal = math.sqrt(cb["shared_cal"])
    se_match_a = math.sqrt(wa["var_match"])
    se_match_b = math.sqrt(wb["var_match"])

    seed = (20261125 + round(theta * 10) + round(inflation * 100) + clusters * 7
            + round((wa["var_match"] + wb["var_match"]) * 1e6)) & 0xFFFFFFFF
    rng = DeterministicRng(seed)
    passed_all = passed_a = passed_b = passed_c = 0
    for _ in range(replicates):
        deltas = [calibration_sd[i] * rng.normal() for i in range(len(ratings))]
        cal_a = sum(wa["weights"][i] * deltas[i] for i in range(len(ratings)))
        cal_b = sum(wb["weights"][i] * deltas[i] for i in range(len(ratings)))
        noise_a = se_match_a * rng.normal()
        noise_b = se_match_b * rng.normal()
        est_a = theta + cal_a + noise_a
        est_b = theta + cal_b + noise_b
        est_c = lam * est_a + (1.0 - lam) * est_b
        a_pass = est_a - half_a > 2000.0
        b_pass = est_b - half_b > 2000.0
        c_pass = est_c - half_c > 2000.0
        passed_a += a_pass
        passed_b += b_pass
        passed_c += c_pass
        passed_all += a_pass and b_pass and c_pass
    return {
        "assumed_true_rating": theta,
        "cluster_sd_inflation": inflation,
        "clusters_per_batch": clusters,
        "batch_a_match_se_elo": se_match_a,
        "batch_b_match_se_elo": se_match_b,
        "shared_calibration_se_elo": se_cal,
        "batch_a_95_half_width_elo": half_a,
        "batch_b_95_half_width_elo": half_b,
        "combined_95_half_width_elo": half_c,
        "power_batch_a": passed_a / replicates,
        "power_batch_b": passed_b / replicates,
        "power_combined": passed_c / replicates,
        "power_all_three_gates": passed_all / replicates,
        "gls_weights": {"A": wa["weights"], "B": wb["weights"]},
        "monte_carlo_replicates": replicates,
    }


def read_suite_names(path: str, expected: int) -> list[str]:
    names = []
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if line and not line.startswith("#"):
                if "|" not in line:
                    raise ValueError(f"{path}: invalid opening-suite line {line!r}")
                names.append(line.split("|", 1)[0].strip())
    if len(names) != expected or len(set(names)) != expected:
        raise ValueError(f"{path}: expected exactly {expected} unique opening clusters")
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screening-a", default="benches/evidence/screening")
    parser.add_argument("--screening-b", default="benches/evidence/screening-b")
    parser.add_argument("--suite-a", default="benches/rating-openings-batchA.txt")
    parser.add_argument("--suite-b", default="benches/rating-openings-batchB.txt")
    parser.add_argument("--subset-a", default="benches/rating-openings-100-batchA.txt")
    parser.add_argument("--subset-b", default="benches/rating-openings-100-batchB.txt")
    parser.add_argument("--replicates", type=int, default=REPLICATES)
    parser.add_argument("--out", default="benches/rating-100-power-assessment.json")
    parser.add_argument(
        "--engine-sha", required=True,
        help="frozen engine binary SHA-256 the assessed campaign's runs were built from",
    )
    parser.add_argument(
        "--labels-a", default=",".join(DEFAULT_LABELS_A),
        help="comma-separated suite-A screening labels (campaign-suffixed anchor ids)",
    )
    parser.add_argument(
        "--labels-b", default=",".join(DEFAULT_LABELS_B),
        help="comma-separated suite-B screening labels (campaign-suffixed anchor ids)",
    )
    parser.add_argument(
        "--kind", default="SCREEN-E3 (PREREGISTRATION.md, 2026-11-25)",
        help="provenance string recorded in the report's screening_inputs",
    )
    parser.add_argument(
        "--exclude-openings", default="",
        help=("semicolon-separated opening names excluded from every screening input "
              "(registered complete-case cluster exclusion: a cluster lacking its counted "
              "AB/BA pair in any input is dropped from all inputs; fail-loud on names that "
              "match no record)"),
    )
    args = parser.parse_args()

    if not re.fullmatch(r"[0-9a-f]{64}", args.engine_sha or ""):
        raise ValueError("--engine-sha must be a full lowercase SHA-256 hex digest")
    exclude = frozenset(name.strip() for name in args.exclude_openings.split(";") if name.strip())
    labels_a = [label.strip() for label in args.labels_a.split(",") if label.strip()]
    labels_b = [label.strip() for label in args.labels_b.split(",") if label.strip()]
    validate_label_sets(labels_a, labels_b)

    games = {"A": {}, "B": {}}
    excluded_seen = {name: 0 for name in exclude}
    pair_complete: dict[str, list[bool]] = {name: [] for name in exclude}
    for batch, root, suite_sha, labels in (("A", args.screening_a, SUITE_A_SHA256, labels_a),
                                           ("B", args.screening_b, SUITE_B_SHA256, labels_b)):
        for label in labels:
            path = os.path.join(root, label, "games.jsonl")
            read_manifest(path, label, batch, suite_sha, args.engine_sha, exclude)
            games[batch][label] = load_cluster_games(path, exclude=exclude)
            counted_colors: dict[str, set] = defaultdict(set)
            with open(path, encoding="utf-8") as handle:
                for raw in handle:
                    if not raw.strip():
                        continue
                    rec = json.loads(raw)
                    opening = rec.get("opening")
                    if opening in excluded_seen:
                        excluded_seen[opening] += 1
                    if rec.get("counted") is not True or rec.get("engine_error") or rec.get("adjudicated") is False:
                        continue
                    if str(rec.get("white", "")).casefold() == "flawless":
                        counted_colors[opening].add("white")
                    elif str(rec.get("black", "")).casefold() == "flawless":
                        counted_colors[opening].add("black")
            for name in exclude:
                cols = counted_colors.get(name)
                # Pair complete here only if the input carries one counted game of
                # each colouring; absent clusters also count as "lacking".
                pair_complete[name].append(cols is not None and sorted(cols) == ["black", "white"])
    unmatched = sorted(name for name, n in excluded_seen.items() if n == 0)
    if unmatched:
        raise ValueError(
            f"--exclude-openings names match no screening record (typo or wrong campaign): "
            f"{unmatched}")
    validate_exclusion_completeness(exclude, pair_complete)

    # Variance components and between-opening covariances per suite.
    batch_labels = {"A": labels_a, "B": labels_b}
    components = {}
    for batch in ("A", "B"):
        labels = batch_labels[batch]
        sigma_op, sigma_m, cov_op = [], [], []
        for label in labels:
            op, m = variance_components(games[batch][label])
            sigma_op.append(op)
            sigma_m.append(m)
        for i, li in enumerate(labels):
            row = []
            for j, lj in enumerate(labels):
                row.append(opening_covariance(games[batch][li], games[batch][lj]) if i != j else sigma_op[i])
            cov_op.append(row)
        components[batch] = {"sigma_op": sigma_op, "sigma_m": sigma_m, "cov_op": cov_op}

    names_a = read_suite_names(args.suite_a, 60)
    names_b = read_suite_names(args.suite_b, 60)
    subset_a = read_suite_names(args.subset_a, 50)
    subset_b = read_suite_names(args.subset_b, 50)
    # Verify the raw bytes of every suite file against its registered digest before
    # any registered hash is reported alongside its opening names (CodeRabbit review
    # 2026-11-27): name-count checks alone would let a swapped opening pass.
    for path, want in ((args.suite_a, SUITE_A_SHA256), (args.suite_b, SUITE_B_SHA256),
                       (args.subset_a, SUBSET_A_SHA256), (args.subset_b, SUBSET_B_SHA256)):
        verify_suite_digest(path, want)

    ratings = [ANCHOR_META[pool_key(label)][0] for label in labels_a]
    calibration_sd = [ANCHOR_META[pool_key(label)][1] / 1.96 for label in labels_a]

    designs_out = []
    selected = None
    for design_label, clusters, reps in DESIGNS:
        # Covariance components are re-measured on the design's actual opening clusters:
        # the 50-opening registered subsets for rating-100-v1, the full 60-opening suites
        # otherwise. Repetitions enter through the measured variance components.
        # The registered design rule is unchanged (50/60 clusters); the exclusion
        # removes clusters from the MEASUREMENT only ("variance components are
        # measured on 59 clusters", PREREGISTRATION 2026-11-26).
        wanted = {"A": set(subset_a if clusters == 50 else names_a) - exclude,
                  "B": set(subset_b if clusters == 50 else names_b) - exclude}
        covs = {}
        design_components = {}
        for batch in ("A", "B"):
            restricted = restrict_clusters(games[batch], wanted[batch], batch_labels[batch], batch)
            sigma_op, sigma_m = [], []
            for label in batch_labels[batch]:
                op, m = variance_components(restricted[label])
                sigma_op.append(op)
                sigma_m.append(m)
            cov_op = []
            for i, li in enumerate(batch_labels[batch]):
                row = []
                for j, lj in enumerate(batch_labels[batch]):
                    row.append(opening_covariance(restricted[li], restricted[lj]) if i != j else sigma_op[i])
                cov_op.append(row)
            design_components[batch] = {"sigma_op": sigma_op, "sigma_m": sigma_m, "cov_op": cov_op}
            covs[batch] = cluster_covariance_at(sigma_op, sigma_m, cov_op, reps)
        grid = []
        ok = True
        for theta in THETA_GRID:
            for inflation in INFLATION_GRID:
                sc = joint_scenario(theta, inflation, covs["A"], covs["B"], clusters,
                                    ratings, calibration_sd, args.replicates)
                grid.append(sc)
                if theta == 2100.0 and inflation == 1.5 and sc["power_all_three_gates"] < POWER_BAR:
                    ok = False
        entry = {
            "design": design_label,
            "clusters_per_batch": clusters,
            "paired_repetitions_per_opening": reps,
            "counted_games_per_anchor_per_batch": clusters * 2 * reps,
            "variance_components": design_components,
            "grid": grid,
            "meets_design_rule": ok,
        }
        designs_out.append(entry)
        if ok and selected is None:
            selected = entry

    status, eligible = report_eligibility(selected, args.replicates)
    report = {
        "design": selected["design"] if selected else "none",
        "date": __import__("datetime").date.today().isoformat(),
        "status": status,
        "eligible_for_confirmatory_dispatch": eligible,
        "monte_carlo_replicates": args.replicates,
        "engine_sha256": args.engine_sha,
        "sample_design": selected["design"] if selected else "none",
        "decision_rule": DESIGN_RULE,
        "power_bar": POWER_BAR,
        "screening_inputs": {
            "kind": args.kind,
            "labels": labels_a if labels_a == labels_b else {"A": labels_a, "B": labels_b},
            "excluded_openings": {
                "rule": ("complete-case cluster exclusion: a cluster lacking its counted AB/BA "
                         "pair in any input is dropped from all inputs (analysis-only; committed "
                         "evidence untouched)"),
                "openings": sorted(exclude),
                "records_skipped_per_input": excluded_seen,
            },
            "roots": {"A": args.screening_a, "B": args.screening_b},
            "variance_components": {
                batch: {
                    "between_opening_var": components[batch]["sigma_op"],
                    "match_var_per_game": components[batch]["sigma_m"],
                    "between_opening_covariance": components[batch]["cov_op"],
                } for batch in ("A", "B")
            },
            "note": "Selection and power inputs only; never gate evidence.",
        },
        "opening_suites": {
            # The consumed binding (dispatch generator + rating-gate) must carry the
            # SELECTED design's suites: the 50-opening subsets for rating-100-v1, the
            # full 60-opening suites otherwise (CodeRabbit review 2026-11-27).
            "amended_a": args.subset_a if (selected and selected["clusters_per_batch"] == 50) else args.suite_a,
            "amended_b": args.subset_b if (selected and selected["clusters_per_batch"] == 50) else args.suite_b,
            "batch_a_sha256": SUBSET_A_SHA256 if (selected and selected["clusters_per_batch"] == 50) else SUITE_A_SHA256,
            "batch_b_sha256": SUBSET_B_SHA256 if (selected and selected["clusters_per_batch"] == 50) else SUITE_B_SHA256,
            "provenance": {
                "full_suite_a": {"path": args.suite_a, "sha256": SUITE_A_SHA256},
                "full_suite_b": {"path": args.suite_b, "sha256": SUITE_B_SHA256},
                "subset_a": {"path": args.subset_a, "sha256": SUBSET_A_SHA256},
                "subset_b": {"path": args.subset_b, "sha256": SUBSET_B_SHA256},
            },
        },
        "candidate_designs": designs_out,
        "limitations": (
            "Delta-method normal approximation over measured covariances; the registered "
            "opening-cluster bootstrap remains the final evidence method. Power at alternatives "
            "below 2,100 Elo is lower by construction: a true rating near the threshold can "
            "yield INCONCLUSIVE, which is fail-closed and never partial credit. Screening runs "
            "used one paired repetition per opening; the design's cluster-mean variances at "
            "higher repetitions derive from the measured variance components."
        ),
        "approval": None,
        "_approval_note": (
            "status PASS is prospective analysis only. eligible_for_confirmatory_dispatch turns "
            "usable only after a named reviewer records reviewer/reviewed_at/evidence_ref/"
            "decision_rule in approval (the rating-run dispatch gate enforces this)."
        ),
    }
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)
        handle.write("\n")
    print(f"status={status} selected={report['design']} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
