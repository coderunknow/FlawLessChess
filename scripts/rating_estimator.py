#!/usr/bin/env python3
"""Rating estimator implementing docs/RATING_PROTOCOL.md Amendment §9 exactly.

Subcommands:
  batch          per-batch estimate from raw games.jsonl files (one per anchor)
  combine        combine Batch A + Batch B (shared calibration added ONCE)
  gate           FAIL-CLOSED gate: recompute everything from raw evidence and
                 pass only if all three lower CI bounds are STRICTLY > threshold
  control        null controls (anchor-vs-anchor +/-75 Elo; self-match ~ 0.5)

Method (protocol §9.6-9.8):
  * Opening-cluster bootstrap, B >= 10,000 replicates, fixed seed. In each
    replicate the opening clusters are resampled ONCE and the SAME draw is
    applied to every anchor (joint resampling -> correlated anchor errors).
  * d_a = -400*log10(1/s_a - 1) (Flawless - anchor, Elo). Boundary scores
    (s=0 or 1) are non-finite: the anchor is INELIGIBLE for gate evidence.
  * sigma_matched,a = SD of the joint bootstrap replicates of d_a (a standard
    deviation, NOT a CI half-width). Published anchor errors are converted to
    SD scale by their stated convention (sd/se as-is; ci95/1.96; ci90/1.645;
    ci99/2.576). sigma_a^2 = sigma_matched,a^2 + eps_a^2.
  * Anchor combination by GLS over the full covariance: Sigma_m = Cov(D) from
    the BxA joint replicate matrix, Sigma_c = diag(eps_a^2), Sigma = Sigma_m +
    Sigma_c. theta = (1' S+ (R+d)) / (1' S+ 1), Var = 1/(1' S+ 1) with pseudo-
    inverse; explicit singular handling falls back to diagonal WLS with a
    printed warning. Match-only and match+calibration intervals are reported
    separately (same point estimate).
  * Batch combination: match-noise inverse-variance pooled; the calibration
    component shared by the identical anchors is added ONCE:
        theta = (theta_A/v_A + theta_B/v_B)/(1/v_A + 1/v_B)
        v     = (1/v_A + 1/v_B)^-1
        c*    = sum_a (lam*w_A,a + (1-lam)*w_B,a)^2 * eps_a^2   (lam = weight of A)
        CI    = theta +/- 1.96*sqrt(v + c*)
    Calibration is never inverse-variance-pooled away.

No rating produced here is an official CCRL/CEGT rating. Gate evidence requires
the full preregistered protocol; this tool only computes what the evidence says.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
from collections import defaultdict

from reduced_sample import SampleDesignError, validate_counted_sample

ERROR_CONVENTION_TO_SD = {"sd": 1.0, "se": 1.0, "ci95": 1.96, "ci90": 1.645, "ci99": 2.576}
Z95 = 1.959963984540054  # two-sided 95% normal quantile (unrounded)


class EvidenceError(SystemExit):
    """Fail-closed: missing/invalid evidence never yields a number."""


# ---------------------------------------------------------------------------
# Loading and validation (fail closed)
# ---------------------------------------------------------------------------


def anchor_label(entry: dict) -> str:
    """Identity under which an anchor's games are recorded.

    The match harness records each engine under the dispatch label (the frozen
    pool's unique `key`); the pool's `name` field is the engine's display name
    and is NOT unique (e.g. two Topple versions). Game matching therefore uses
    `key` first, falling back to `name` for older descriptors.
    """
    return entry.get("key") or entry["name"]


def same_engine(a: str | None, b: str | None) -> bool:
    """Engine-label equality, case-insensitive.

    The match harness historically seats the focus engine under its display
    name ("Flawless") while pool keys and the estimator focus are the lowercase
    key ("flawless"). Labels are display metadata — engine identity is the
    binary SHA-256 verified in every manifest — so focus matching is
    case-insensitive. No two frozen pool keys differ only by case (keys are
    [a-z0-9._-]+), so this cannot merge distinct engines.
    """
    return (a or "").casefold() == (b or "").casefold()


def load_games(path: str, focus: str | None) -> list[dict]:
    games = []
    try:
        fh = open(path)
    except OSError as e:
        raise EvidenceError(f"cannot read games file {path!r}: {e}")
    with fh as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            g = json.loads(line)
            # Only counted, adjudicated games ever enter statistics.
            if g.get("engine_error") or g.get("counted") is False:
                continue
            if g.get("result") not in ("1-0", "0-1", "1/2-1/2"):
                continue
            if focus is not None and not (same_engine(g.get("white"), focus)
                                          or same_engine(g.get("black"), focus)):
                raise EvidenceError(f"{path}:{ln}: focus engine {focus!r} not in game")
            games.append(g)
    return games


def score_of(result: str, perspective: str) -> float:
    if result == "1/2-1/2":
        return 0.5
    if perspective == "white":
        return 1.0 if result == "1-0" else 0.0
    return 1.0 if result == "0-1" else 0.0


def focus_scores_by_opening(games: list[dict], focus: str) -> dict[str, list[float]]:
    out: dict[str, list[float]] = defaultdict(list)
    for g in games:
        if same_engine(g["white"], focus):
            out[g["opening"]].append(score_of(g["result"], "white"))
        else:
            out[g["opening"]].append(score_of(g["result"], "black"))
    return dict(out)


def elo_from_score(s: float) -> float:
    """Logistic Elo diff; s must be interior. Boundary handled by callers."""
    if s <= 0.0 or s >= 1.0:
        return math.inf if s >= 1.0 else -math.inf
    return -400.0 * math.log10(1.0 / s - 1.0)


# ---------------------------------------------------------------------------
# Small dense matrix helpers (A x A, A <= ~6: anchors)
# ---------------------------------------------------------------------------


def mat_inverse(m: list[list[float]]) -> list[list[float]] | None:
    n = len(m)
    aug = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(m)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < 1e-12:
            return None
        aug[col], aug[pivot] = aug[pivot], aug[col]
        p = aug[col][col]
        aug[col] = [x / p for x in aug[col]]
        for r in range(n):
            if r != col and aug[r][col] != 0.0:
                f = aug[r][col]
                aug[r] = [x - f * y for x, y in zip(aug[r], aug[col])]
    inv = [row[n:] for row in aug]
    # sanity: inverse must reconstruct identity
    for i in range(n):
        for j in range(n):
            got = sum(m[i][k] * inv[k][j] for k in range(n))
            if abs(got - (1.0 if i == j else 0.0)) > 1e-6:
                return None
    return inv


def mat_vec(m: list[list[float]], v: list[float]) -> list[float]:
    return [sum(row[j] * v[j] for j in range(len(v))) for row in m]


# ---------------------------------------------------------------------------
# Joint opening-cluster bootstrap
# ---------------------------------------------------------------------------


def joint_bootstrap(anchors: list[dict], n_boot: int, seed: int) -> dict:
    """anchors: [{name, published_elo, eps_sd, clusters: {opening: [scores]}}]

    Returns D (B x A replicate matrix of d_a), plus per-anchor observed values.
    Opening clusters are resampled ONCE per replicate, same draw for all anchors.
    """
    names = [a["name"] for a in anchors]
    # Common cluster universe: every anchor must cover the same openings.
    opening_sets = [set(a["clusters"]) for a in anchors]
    common = set.intersection(*opening_sets) if opening_sets else set()
    if len(common) != len(opening_sets[0]):
        missing = set.union(*opening_sets) - common
        raise EvidenceError(f"anchors do not share identical opening suites; divergent: {sorted(missing)[:5]}")
    openings = sorted(common)
    n = len(openings)
    if n < 2:
        raise EvidenceError("need >= 2 opening clusters for a clustered bootstrap")

    # Per-anchor per-opening score sums and game counts.
    sums = []
    ns = []
    for a in anchors:
        s_row, n_row = [], []
        for op in openings:
            sc = a["clusters"][op]
            s_row.append(sum(sc))
            n_row.append(len(sc))
        sums.append(s_row)
        ns.append(n_row)

    def d_of(a_idx: int, idxs: list[int]) -> float:
        ts = sum(sums[a_idx][i] for i in idxs)
        tn = sum(ns[a_idx][i] for i in idxs)
        return elo_from_score(ts / tn) if tn else math.nan

    observed = [d_of(i, list(range(n))) for i in range(len(anchors))]
    rng = random.Random(seed)
    D: list[list[float]] = []
    for _ in range(n_boot):
        idxs = [rng.randrange(n) for _ in range(n)]
        row = [d_of(i, idxs) for i in range(len(anchors))]
        D.append(row)
    # Boundary replicates (score 0/1 in a resample) are non-finite Elo draws.
    # Registered treatment (RATING_PROTOCOL §8.3/§9.4): such an anchor is
    # uninformative — exclude it from the WLS with a reported reason and replace
    # it with a nearer calibrated anchor via registered recovery. Never clamp
    # and never crash the estimator here; count the non-finite replicates per
    # anchor so `batch_estimate` can apply the exclusion.
    nonfinite_reps = [0] * len(anchors)
    for row in D:
        for i, v in enumerate(row):
            if not math.isfinite(v):
                nonfinite_reps[i] += 1
    return {"names": names, "D": D, "observed": observed, "openings": openings,
            "nonfinite_reps": nonfinite_reps}


def col_means_cov(D: list[list[float]]) -> tuple[list[float], list[list[float]]]:
    B = len(D)
    A = len(D[0])
    # math.fsum: exact, version-stable summation — bootstrap covariances must not
    # depend on interpreter float-accumulation behavior (reproducibility).
    means = [math.fsum(D[b][a] for b in range(B)) / B for a in range(A)]
    cov = [[0.0] * A for _ in range(A)]
    for i in range(A):
        for j in range(A):
            cov[i][j] = math.fsum(
                (D[b][i] - means[i]) * (D[b][j] - means[j]) for b in range(B)
            ) / (B - 1)
    return means, cov


# ---------------------------------------------------------------------------
# GLS estimation
# ---------------------------------------------------------------------------


def gls(suma: list[list[float]], y: list[float]) -> tuple[list[float], list[list[float]], str]:
    """Return (weights w with sum 1, inverse used, mode) for theta = w . y.

    mode = 'gls' or 'diagonal-wls-fallback' (printed warning by caller).
    """
    A = len(y)
    inv = mat_inverse(suma)
    if inv is not None:
        one = [1.0] * A
        iv1 = mat_vec(inv, one)
        denom = sum(iv1)
        if denom > 0:
            w = [x / denom for x in iv1]
            return w, inv, "gls"
    # Degenerate: documented fallback to diagonal WLS (§9.7).
    diag = [suma[i][i] for i in range(A)]
    if any(d <= 0 for d in diag):
        raise EvidenceError("degenerate covariance: non-positive diagonal, cannot estimate")
    w_raw = [1.0 / d for d in diag]
    s = sum(w_raw)
    w = [x / s for x in w_raw]
    inv_diag = [[0.0] * A for _ in range(A)]
    for i in range(A):
        inv_diag[i][i] = 1.0 / diag[i]
    return w, inv_diag, "diagonal-wls-fallback"


def eps_sd_from_entry(entry: dict) -> float:
    conv = str(entry.get("error_convention", "")).lower()
    if conv not in ERROR_CONVENTION_TO_SD:
        raise EvidenceError(f"anchor {entry.get('name')}: unknown error_convention {conv!r}")
    err = float(entry["published_error"])
    return err / ERROR_CONVENTION_TO_SD[conv]


# ---------------------------------------------------------------------------
# Batch estimate
# ---------------------------------------------------------------------------


def batch_estimate(games_by_anchor: dict[str, list[dict]], anchor_entries: list[dict],
                   focus: str, n_boot: int, seed: int) -> dict:
    anchors = []
    for entry in anchor_entries:
        name = anchor_label(entry)
        if name not in games_by_anchor:
            raise EvidenceError(f"no games file for anchor {name!r}")
        clusters = focus_scores_by_opening(games_by_anchor[name], focus)
        if not clusters:
            raise EvidenceError(f"no counted games for anchor {name!r}")
        anchors.append({
            "name": name,
            "published_elo": float(entry["published_elo"]),
            "eps_sd": eps_sd_from_entry(entry),
            "published_error_as_published": float(entry["published_error"]),
            "error_convention": entry["error_convention"],
            "clusters": clusters,
            "n_counted_games": sum(len(v) for v in clusters.values()),
        })

    def obs_score(a: dict) -> float:
        tot = math.fsum(sum(sc) for sc in a["clusters"].values())
        n = sum(len(sc) for sc in a["clusters"].values())
        return tot / n if n else math.nan

    # ------------------------------------------------------------------
    # Registered exclusion semantics (RATING_PROTOCOL §8.2/§8.3/§9.4):
    #   * observed s == 0/1 (boundary) -> non-finite Elo: excluded from the
    #     WLS and the gate set, reported with its raw score, NEVER clamped;
    #     registered recovery = replace with a nearer calibrated anchor and
    #     collect fresh pre-registered evidence (§9.4).
    #   * observed |d| > 400 (saturated) -> excluded from the gate and WLS,
    #     reported with its finite d (§8.2).
    #   * an eligible anchor whose bootstrap replicates hit a boundary score
    #     is uninformative (§9.4): excluded the same way and reported.
    # Nothing is silently dropped: every input anchor appears in per_anchor.
    # ------------------------------------------------------------------
    eligible = []
    excluded = []
    for a in anchors:
        s = obs_score(a)
        d = elo_from_score(s)
        base = {
            "name": a["name"],
            "published_elo": a["published_elo"],
            "published_error_as_published": a["published_error_as_published"],
            "error_convention": a["error_convention"],
            "eps_sd": a["eps_sd"],
            "score": s,
            "n_counted_games": a["n_counted_games"],
        }
        if not math.isfinite(d):
            excluded.append({
                **base,
                "d_flawless_minus_anchor": None,
                "boundary": True,
                "saturated": False,
                "gate_eligible": False,
                "abs_estimate_from_anchor": None,
                "excluded_reason": (
                    f"boundary score s={s:.3f} (non-finite Elo) — excluded from WLS and gate "
                    f"per RATING_PROTOCOL §8.3/§9.4; replace with a nearer calibrated anchor "
                    f"and collect fresh pre-registered evidence; never clamp"
                ),
            })
        elif abs(d) > 400.0:
            excluded.append({
                **base,
                "d_flawless_minus_anchor": d,
                "boundary": False,
                "saturated": True,
                "gate_eligible": False,
                "abs_estimate_from_anchor": a["published_elo"] + d,
                "excluded_reason": (
                    f"saturated: |d|={abs(d):.1f} > 400 — excluded from WLS and gate "
                    f"per RATING_PROTOCOL §8.2; report and replace per §8.3"
                ),
            })
        else:
            eligible.append(a)

    bootstrap_excluded = []
    boot = None
    while True:
        if not eligible:
            break
        boot = joint_bootstrap(eligible, n_boot, seed)
        bad = [i for i, n_ in enumerate(boot["nonfinite_reps"]) if n_ > 0]
        if not bad:
            break
        for i in reversed(bad):
            a = eligible.pop(i)
            n_ = boot["nonfinite_reps"][i]
            bootstrap_excluded.append(a["name"])
            excluded.append({
                "name": a["name"],
                "published_elo": a["published_elo"],
                "published_error_as_published": a["published_error_as_published"],
                "error_convention": a["error_convention"],
                "eps_sd": a["eps_sd"],
                "score": obs_score(a),
                "n_counted_games": a["n_counted_games"],
                "d_flawless_minus_anchor": None,
                "boundary": True,
                "saturated": False,
                "gate_eligible": False,
                "abs_estimate_from_anchor": None,
                "excluded_reason": (
                    f"bootstrap boundary: {n_}/{n_boot} replicates hit s=0/1 (non-finite Elo) — "
                    f"uninformative per RATING_PROTOCOL §9.4; excluded from WLS and gate; "
                    f"replace with a nearer calibrated anchor and collect fresh pre-registered evidence"
                ),
            })
    A = len(eligible)
    if A == 0 or boot is None:
        # No WLS exists, but the per-anchor report is still produced so the
        # gate can surface the registered exclusions instead of losing them.
        per_anchor = []
        order = {a["name"]: i for i, a in enumerate(anchors)}
        for e in sorted(excluded, key=lambda r: order[r["name"]]):
            per_anchor.append({
                "name": e["name"],
                "published_elo": e["published_elo"],
                "published_error_as_published": e["published_error_as_published"],
                "error_convention": e["error_convention"],
                "eps_sd": e["eps_sd"],
                "score": e["score"],
                "d_flawless_minus_anchor": e["d_flawless_minus_anchor"],
                "sigma_matched": None,
                "sigma_total": None,
                "abs_estimate_from_anchor": e["abs_estimate_from_anchor"],
                "gate_eligible": False,
                "n_counted_games": e["n_counted_games"],
                "saturated": e["saturated"],
                "boundary": e["boundary"],
                "excluded_reason": e["excluded_reason"],
            })
        return {
            "focus": focus,
            "seed": seed,
            "n_boot": n_boot,
            "openings": [],
            "n_openings": 0,
            "per_anchor": per_anchor,
            "eligible_anchors": [],
            "excluded_anchors": excluded,
            "bootstrap_boundary_exclusions": bootstrap_excluded,
            "theta": None,
            "weights": [],
            "weights_match_only": None,
            "mode_total": "no gate-eligible anchors after registered exclusions",
            "mode_match": "no gate-eligible anchors after registered exclusions",
            "var_match": None,
            "var_cal": None,
            "var_total": None,
            "ci95_match_only": None,
            "ci95_calibrated": None,
            "sigma_m": [],
            "sigma_c": [],
        }

    means, sigma_m = col_means_cov(boot["D"])
    sigma_c = [[0.0] * A for _ in range(A)]
    for i in range(A):
        sigma_c[i][i] = eligible[i]["eps_sd"] ** 2
    sigma_total = [[sigma_m[i][j] + sigma_c[i][j] for j in range(A)] for i in range(A)]
    y = [eligible[i]["published_elo"] + boot["observed"][i] for i in range(A)]

    w_total, _, mode_total = gls(sigma_total, y)
    # Match-only weights are REPORTING-ONLY. When the match covariance is
    # degenerate (e.g. zero within-opening variance), no match-only GLS exists;
    # that is recorded, never raised — the estimator's own variance uses w_total.
    inv_m = mat_inverse(sigma_m)
    if inv_m is not None:
        one = [1.0] * A
        iv1 = mat_vec(inv_m, one)
        denom = sum(iv1)
        w_match = [x / denom for x in iv1] if denom > 0 else None
        mode_match = "gls"
    else:
        w_match = None
        mode_match = "degenerate-match-covariance (match-only weights unavailable)"
    theta = sum(w_total[i] * y[i] for i in range(A))
    var_match = sum(w_total[i] * w_total[j] * sigma_m[i][j] for i in range(A) for j in range(A))
    var_cal = sum(w_total[i] * w_total[j] * sigma_c[i][j] for i in range(A) for j in range(A))
    var_total = var_match + var_cal

    per_anchor = []
    excluded_by_name = {e["name"]: e for e in excluded}
    elig_pos = {a["name"]: i for i, a in enumerate(eligible)}
    for a in anchors:
        if a["name"] in elig_pos:
            i = elig_pos[a["name"]]
            d = boot["observed"][i]
            per_anchor.append({
                "name": a["name"],  # label recorded in games (pool key)
                "published_elo": a["published_elo"],
                "published_error_as_published": a["published_error_as_published"],
                "error_convention": a["error_convention"],
                "eps_sd": a["eps_sd"],
                "score": elo_to_score(d),
                "d_flawless_minus_anchor": d,
                "sigma_matched": math.sqrt(sigma_m[i][i]),
                "sigma_total": math.sqrt(sigma_m[i][i] + sigma_c[i][i]),
                "abs_estimate_from_anchor": a["published_elo"] + d,
                "gate_eligible": abs(d) <= 400.0,
                "n_counted_games": a["n_counted_games"],
                "saturated": abs(d) > 400.0,
                "boundary": False,
                "excluded_reason": None,
            })
        else:
            e = excluded_by_name[a["name"]]
            per_anchor.append({
                "name": a["name"],
                "published_elo": a["published_elo"],
                "published_error_as_published": a["published_error_as_published"],
                "error_convention": a["error_convention"],
                "eps_sd": a["eps_sd"],
                "score": e["score"],
                "d_flawless_minus_anchor": e["d_flawless_minus_anchor"],
                "sigma_matched": None,
                "sigma_total": None,
                "abs_estimate_from_anchor": e["abs_estimate_from_anchor"],
                "gate_eligible": False,
                "n_counted_games": e["n_counted_games"],
                "saturated": e["saturated"],
                "boundary": e["boundary"],
                "excluded_reason": e["excluded_reason"],
            })

    return {
        "focus": focus,
        "seed": seed,
        "n_boot": n_boot,
        "openings": boot["openings"],
        "n_openings": len(boot["openings"]),
        "per_anchor": per_anchor,
        "eligible_anchors": [a["name"] for a in eligible],
        "excluded_anchors": excluded,
        "bootstrap_boundary_exclusions": bootstrap_excluded,
        "theta": theta,
        "weights": w_total,
        "weights_match_only": w_match,
        "mode_total": mode_total,
        "mode_match": mode_match,
        "var_match": var_match,
        "var_cal": var_cal,
        "var_total": var_total,
        "ci95_match_only": [theta - Z95 * math.sqrt(var_match), theta + Z95 * math.sqrt(var_match)],
        "ci95_calibrated": [theta - Z95 * math.sqrt(var_total), theta + Z95 * math.sqrt(var_total)],
        "sigma_m": sigma_m,
        "sigma_c": sigma_c,
    }


def elo_to_score(d: float) -> float:
    if not math.isfinite(d):
        return 1.0 if d > 0 else 0.0
    return 1.0 / (1.0 + 10.0 ** (-d / 400.0))


# ---------------------------------------------------------------------------
# Batch combination (§9.8): shared calibration added ONCE
# ---------------------------------------------------------------------------


def combine_batches(ba: dict, bb: dict) -> dict:
    v_a, v_b = ba["var_match"], bb["var_match"]
    if v_a <= 0 or v_b <= 0:
        raise EvidenceError("non-positive match variance in a batch")
    lam = (1.0 / v_a) / (1.0 / v_a + 1.0 / v_b)
    theta = lam * ba["theta"] + (1.0 - lam) * bb["theta"]
    v = 1.0 / (1.0 / v_a + 1.0 / v_b)
    # Shared calibration: identical anchors -> the SAME published errors appear in
    # both batch estimates. Effective per-anchor weight of the combined estimate.
    # Weights index each batch's gate-eligible WLS set (§8.2/§8.3 exclusions may
    # differ per batch; an anchor excluded from one batch contributes weight 0
    # there). Legacy result JSONs without eligible_anchors fall back to per_anchor
    # order (pre-exclusion semantics).
    names_a = [p["name"] for p in ba["per_anchor"]]
    names_b = [p["name"] for p in bb["per_anchor"]]
    if names_a != names_b:
        raise EvidenceError("batches must use identical anchors")
    elig_a = ba.get("eligible_anchors") or names_a
    elig_b = bb.get("eligible_anchors") or names_b
    pos_a = {n: i for i, n in enumerate(elig_a)}
    pos_b = {n: i for i, n in enumerate(elig_b)}
    eps_by_name = {p["name"]: p["eps_sd"] for p in ba["per_anchor"]}
    c = 0.0
    for n in names_a:
        w_a = ba["weights"][pos_a[n]] if n in pos_a else 0.0
        w_b = bb["weights"][pos_b[n]] if n in pos_b else 0.0
        w_bar = lam * w_a + (1.0 - lam) * w_b
        c += (w_bar ** 2) * (eps_by_name[n] ** 2)
    var_total = v + c
    return {
        "theta": theta,
        "weight_batch_a": lam,
        "var_match_pooled": v,
        "var_cal_shared": c,
        "var_total": var_total,
        "ci95_match_only": [theta - Z95 * math.sqrt(v), theta + Z95 * math.sqrt(v)],
        "ci95_calibrated": [theta - Z95 * math.sqrt(var_total), theta + Z95 * math.sqrt(var_total)],
        "note": "match-noise pooled inverse-variance; shared anchor calibration added once (§9.8)",
    }


# ---------------------------------------------------------------------------
# Null controls
# ---------------------------------------------------------------------------


def control_anchor_vs_anchor(games: list[dict], entry_a: dict, entry_b: dict,
                             n_boot: int, seed: int) -> dict:
    """Measured A-vs-B difference must recover R_a - R_b within +/-75 Elo."""
    a_name, b_name = anchor_label(entry_a), anchor_label(entry_b)
    clusters = focus_scores_by_opening(games, a_name)
    if not clusters:
        raise EvidenceError("anchor-vs-anchor control: no counted games")
    s = sum(sum(v) for v in clusters.values()) / sum(len(v) for v in clusters.values())
    d_meas = elo_from_score(s) if 0.0 < s < 1.0 else (math.inf if s >= 1.0 else -math.inf)
    d_pub = float(entry_a["published_elo"]) - float(entry_b["published_elo"])
    err = d_meas - d_pub if math.isfinite(d_meas) else math.inf
    ok = math.isfinite(err) and abs(err) <= 75.0
    return {
        "mode": "anchor-vs-anchor",
        "a": a_name, "b": b_name,
        "score_a": s, "d_measured": d_meas, "d_published": d_pub,
        "error": err, "tolerance": 75.0,
        "pass": ok,
    }


def self_match_seat_score(g: dict, focus: str) -> float:
    """Seat-A perspective score of one self-match game (0.5-fairness metric).

    The registered CTRL-2 definition ("identical binary must score 0.5 within
    its 95% CI") is a SEAT-symmetry quantity: the color advantage is real chess
    and cancels only under the schedule's AB/BA seat reversal. For self-match
    data both seat labels are identical, so the seat perspective must come from
    the recorded color_pair (AB: seat A was white; BA: seat A was black).
    """
    w = score_of(g["result"], "white")
    pair = g.get("color_pair")
    if pair == "AB":
        return w
    if pair == "BA":
        return 1.0 - w
    raise EvidenceError(
        f"self-match game missing color_pair (schedule {g.get('schedule_index')}): "
        "cannot compute the registered seat-perspective score")


def control_self_match(games: list[dict], focus: str, n_boot: int, seed: int) -> dict:
    """Swapped-color self-match must be statistically consistent with 0.5."""
    # Distinct-name data (synthetic/legacy): focus-perspective by name.
    distinct = any(not same_engine(g["white"], g["black"]) for g in games)
    if not distinct:
        # Real self-match records: identical labels both sides — seat perspective.
        clusters = defaultdict(list)
        for g in games:
            clusters[g["opening"]].append(self_match_seat_score(g, focus))
    else:
        clusters = focus_scores_by_opening(games, focus)
    if not clusters:
        raise EvidenceError("self-match control: no counted games")
    sums = [sum(v) for v in clusters.values()]
    ns = [len(v) for v in clusters.values()]
    point = sum(sums) / sum(ns)
    rng = random.Random(seed)
    n = len(sums)
    boot = []
    for _ in range(n_boot):
        idxs = [rng.randrange(n) for _ in range(n)]
        ts = sum(sums[i] for i in idxs)
        tn = sum(ns[i] for i in idxs)
        boot.append(ts / tn if tn else 0.5)
    boot.sort()
    lo = boot[int(0.025 * n_boot)]
    hi = boot[min(n_boot - 1, int(0.975 * n_boot))]
    ok = lo <= 0.5 <= hi
    return {
        "mode": "self-match",
        "focus": focus, "score": point,
        "seat_perspective": not distinct,
        "white_perspective_score": (sum(score_of(g["result"], "white") for g in games)
                                    / len(games)),
        "ci95_score": [lo, hi], "pass": ok,
    }


# ---------------------------------------------------------------------------
# Gate (fail closed)
# ---------------------------------------------------------------------------


def _registered_opening_names(path: str | None) -> list[str] | None:
    if path is None:
        return None
    names = []
    with open(path) as suite:
        for raw in suite:
            line = raw.strip()
            if line and not line.startswith("#"):
                if "|" not in line:
                    raise EvidenceError(f"invalid opening-suite row in {path}: {line!r}")
                names.append(line.split("|", 1)[0].strip())
    return names


def run_gate(args) -> int:
    pool = json.load(open(args.anchor_json))
    entries = pool["engines"]
    focus = args.focus

    # The gate covers the ELIGIBLE anchor set that actually has batch evidence in
    # BOTH batches (the preregistered selection from the frozen pool) — not every
    # pool entry. Pool anchors without batch evidence are reported, never required.
    games_a = load_batch(args.batch_a, focus)
    games_b = load_batch(args.batch_b, focus)
    if set(games_a) != set(games_b):
        raise EvidenceError(f"batch A/B anchor sets differ: {sorted(games_a)} vs {sorted(games_b)}")

    dimensions = (args.exact_games, args.required_openings, args.games_per_opening)
    if any(value is not None for value in dimensions):
        if any(value is None for value in dimensions):
            raise EvidenceError("exact sample validation requires --exact-games, "
                                "--required-openings and --games-per-opening together")
        if args.exact_games != args.required_openings * args.games_per_opening:
            raise EvidenceError("exact games must equal required openings × games per opening")
        suites = {
            "batch_a": _registered_opening_names(args.suite_a),
            "batch_b": _registered_opening_names(args.suite_b),
        }
        for label, batch_games in (("batch_a", games_a), ("batch_b", games_b)):
            expected = suites[label]
            if expected is None:
                raise EvidenceError(f"{label}: exact sample design requires its registered opening suite")
            for anchor_key, counted_games in batch_games.items():
                try:
                    report = validate_counted_sample(
                        counted_games,
                        exact_games=args.exact_games,
                        required_openings=args.required_openings,
                        games_per_opening=args.games_per_opening,
                        expected_openings=expected,
                    )
                except SampleDesignError as e:
                    raise EvidenceError(f"{label}/{anchor_key}: {e}") from e
                print(f"sample design {label}/{anchor_key}: {report}")

    used = [e for e in entries if anchor_label(e) in games_a]
    if len(used) < 3:
        raise EvidenceError(
            f"gate requires >= 3 eligible anchors with evidence in both batches, got "
            f"{[anchor_label(e) for e in used]}")
    unused = [anchor_label(e) for e in entries if anchor_label(e) not in games_a]
    if unused:
        print(f"note: pool anchors without batch evidence (excluded from the gate): {unused}")

    results = {}
    results["batch_a"] = batch_estimate(games_a, used, focus,
                                        args.bootstrap, args.seed)
    results["batch_b"] = batch_estimate(games_b, used, focus,
                                        args.bootstrap, args.seed + 1)
    # Registered gate eligibility (RATING_PROTOCOL §8.2/§8.3): an anchor
    # contributes to the gate only when it has evidence in BOTH batches and is
    # not excluded (boundary s=0/1 or saturated |d|>400) in EITHER batch.
    # Exclusions are reported with their registered reasons — never silent.
    per_a = {r["name"]: r for r in results["batch_a"]["per_anchor"]}
    per_b = {r["name"]: r for r in results["batch_b"]["per_anchor"]}
    joint_eligible = sorted(
        n for n in per_a if per_a[n]["gate_eligible"] and per_b[n]["gate_eligible"])
    exclusion_report = {
        n: {
            "batch_a": per_a[n].get("excluded_reason"),
            "batch_b": per_b[n].get("excluded_reason"),
        }
        for n in per_a if n not in joint_eligible
    }
    if results["batch_a"]["theta"] is not None and results["batch_b"]["theta"] is not None:
        results["combined"] = combine_batches(results["batch_a"], results["batch_b"])
    else:
        results["combined"] = None

    results["control_anchor_vs_anchor"] = control_anchor_vs_anchor(
        load_games(args.control_anchor, None),  # anchor-vs-anchor: neither side is focus
        next(e for e in entries if anchor_label(e) == args.control_anchor_names[0]),
        next(e for e in entries if anchor_label(e) == args.control_anchor_names[1]),
        args.bootstrap, args.seed,
    )
    results["control_self_match"] = control_self_match(
        load_games(args.control_self, focus), focus, args.bootstrap, args.seed)

    # ---- Decision (all conjunctive, unrounded, strictly greater) ----
    checks = []

    def need(cond: bool, msg: str) -> None:
        checks.append({"pass": bool(cond), "check": msg})

    thr = args.threshold
    need(len(joint_eligible) >= 3,
         f">= 3 gate-eligible anchors with evidence in both batches "
         f"(boundary/saturated excluded per §8.2/§8.3): jointly eligible {joint_eligible}; "
         f"excluded {exclusion_report or '{}'}")
    if results["combined"] is not None:
        for batch in ("batch_a", "batch_b", "combined"):
            lo = results[batch]["ci95_calibrated"][0]
            need(lo > thr, f"{batch}: calibrated 95% CI lower bound {lo!r} > {thr} (strict, unrounded)")
    else:
        need(False, "combined estimate unavailable (batch WLS empty after registered exclusions)")
    for batch in ("batch_a", "batch_b"):
        for p in results[batch]["per_anchor"]:
            if not p["gate_eligible"]:
                continue  # registered §8.2/§8.3 exclusion — reported, not a gate failure
            need(p["n_counted_games"] >= args.min_games,
                 f"{batch}/{p['name']}: counted games {p['n_counted_games']} >= {args.min_games}")
        if results[batch]["theta"] is not None:
            need(results[batch]["mode_total"] == "gls",
                 f"{batch}: GLS used (fallback would need explicit preregistered handling)")
    need(results["control_anchor_vs_anchor"]["pass"],
         f"null control anchor-vs-anchor within +/-75 (err={results['control_anchor_vs_anchor']['error']})")
    need(results["control_self_match"]["pass"],
         f"null control self-match consistent with 0.5 (CI={results['control_self_match']['ci95_score']})")

    ok = all(c["pass"] for c in checks)
    out = {
        "pass": ok,
        "threshold": thr,
        "checks": checks,
        "results": results,
        "gate_eligible_anchors": joint_eligible,
        "excluded_anchors": exclusion_report,
        "verdict": "PASS" if ok else "FAIL",
        "disclaimer": "private, CCRL/CEGT-anchored estimate — not an official rating",
    }
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)
    for c in checks:
        print(("PASS " if c["pass"] else "FAIL ") + c["check"])
    print(f"GATE: {out['verdict']}  (details in {args.out})")
    return 0 if ok else 1


def load_batch(paths: list[str], focus: str) -> dict[str, list[dict]]:
    if not paths:
        raise EvidenceError("gate requires per-anchor games files for each batch")
    out = {}
    for p in paths:
        # name syntax: 'anchor=path/to/file.jsonl', else derived from filename
        # '<anchor>.games.jsonl' / '<anchor>.jsonl'.
        if "=" in p:
            name, path = p.split("=", 1)
        else:
            path = p
            name = os.path.basename(p)
            for suffix in (".games.jsonl", ".jsonl"):
                if name.endswith(suffix):
                    name = name[: -len(suffix)]
                    break
            else:
                raise EvidenceError(f"cannot derive anchor name from {p!r}; use anchor=path")
        if not name:
            raise EvidenceError(f"empty anchor name for {p!r}")
        out[name] = load_games(path, focus)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    pb = sub.add_parser("batch", help="per-batch estimate")
    pb.add_argument("--games", nargs="+", required=True,
                    help="games.jsonl per anchor, named <anchor>.games.jsonl or anchor:path")
    pb.add_argument("--anchor-json", required=True)
    pb.add_argument("--focus", required=True)
    pb.add_argument("--bootstrap", type=int, default=10000)
    pb.add_argument("--seed", type=int, default=20261114)
    pb.add_argument("--out", required=True)

    pc = sub.add_parser("combine", help="combine two batch result JSONs")
    pc.add_argument("--batch-a", required=True)
    pc.add_argument("--batch-b", required=True)
    pc.add_argument("--out", required=True)

    pg = sub.add_parser("gate", help="fail-closed rating gate from raw evidence")
    pg.add_argument("--anchor-json", required=True)
    pg.add_argument("--focus", required=True)
    pg.add_argument("--batch-a", nargs="+", required=True)
    pg.add_argument("--batch-b", nargs="+", required=True)
    pg.add_argument("--control-anchor", required=True,
                    help="games.jsonl of anchor1 vs anchor2 null control")
    pg.add_argument("--control-anchor-names", nargs=2, required=True,
                    metavar=("ANCHOR1", "ANCHOR2"))
    pg.add_argument("--control-self", required=True, help="self-match games.jsonl")
    pg.add_argument("--min-games", type=int, default=2000)
    pg.add_argument("--exact-games", type=int, default=None,
                    help="require this exact number of counted games per anchor and batch")
    pg.add_argument("--required-openings", type=int, default=None,
                    help="require this exact number of distinct opening clusters")
    pg.add_argument("--games-per-opening", type=int, default=None,
                    help="require this many counted games in each opening cluster")
    pg.add_argument("--suite-a", default=None, help="registered Batch A opening-suite file")
    pg.add_argument("--suite-b", default=None, help="registered Batch B opening-suite file")
    pg.add_argument("--threshold", type=float, default=2000.0)
    pg.add_argument("--bootstrap", type=int, default=10000)
    pg.add_argument("--seed", type=int, default=20261114)
    pg.add_argument("--out", required=True)

    pn = sub.add_parser("control", help="null controls")
    pn.add_argument("--mode", choices=("anchor-vs-anchor", "self-match"), required=True)
    pn.add_argument("--games", required=True)
    pn.add_argument("--anchor-json")
    pn.add_argument("--names", nargs=2, metavar=("A", "B"))
    pn.add_argument("--focus", required=True)
    pn.add_argument("--bootstrap", type=int, default=10000)
    pn.add_argument("--seed", type=int, default=20261114)
    pn.add_argument("--out")

    args = ap.parse_args()

    if args.cmd == "batch":
        pool = json.load(open(args.anchor_json))
        res = batch_estimate(load_batch(args.games, args.focus), pool["engines"], args.focus,
                             args.bootstrap, args.seed)
        with open(args.out, "w") as f:
            json.dump(res, f, indent=2)
        print(f"theta = {res['theta']:.2f}  ci95_calibrated = "
              f"[{res['ci95_calibrated'][0]:.2f}, {res['ci95_calibrated'][1]:.2f}]")
        return 0
    if args.cmd == "combine":
        ba = json.load(open(args.batch_a))
        bb = json.load(open(args.batch_b))
        res = combine_batches(ba, bb)
        with open(args.out, "w") as f:
            json.dump(res, f, indent=2)
        print(f"combined theta = {res['theta']:.2f}  ci95_calibrated = "
              f"[{res['ci95_calibrated'][0]:.2f}, {res['ci95_calibrated'][1]:.2f}]")
        return 0
    if args.cmd == "gate":
        return run_gate(args)
    if args.cmd == "control":
        if args.mode == "self-match":
            games = load_games(args.games, args.focus)
            res = control_self_match(games, args.focus, args.bootstrap, args.seed)
        else:
            games = load_games(args.games, None)
            pool = json.load(open(args.anchor_json))
            ea = next(e for e in pool["engines"] if anchor_label(e) == args.names[0])
            eb = next(e for e in pool["engines"] if anchor_label(e) == args.names[1])
            res = control_anchor_vs_anchor(games, ea, eb, args.bootstrap, args.seed)
        if args.out:
            with open(args.out, "w") as f:
                json.dump(res, f, indent=2)
        print(json.dumps(res, indent=2))
        return 0 if res["pass"] else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
