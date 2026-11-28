#!/usr/bin/env python3
"""Regression tests for scripts/rating_estimator.py (RATING_PROTOCOL Amendment §9).

Run: python3 scripts/test_rating_estimator.py   (stdlib only; no pytest required)

Synthetic-scenario coverage: balanced-match recovery, perfect/zero boundaries,
known anchor differences, correlated opening difficulty, anchor-uncertainty
conversion, GLS + covariance + singular fallback, shared calibration across
batches, combined CI math, missing/invalid evidence rejection, fixed-seed
reproducibility, null-control verdicts, and a full fail-closed gate run.
"""
import json
import math
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rating_estimator as re  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PASS = 0
FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"FAIL: {msg}")


def close(a, b, tol=1e-6):
    return abs(a - b) <= tol


# ---------------------------------------------------------------------------
# Synthetic evidence generators
# ---------------------------------------------------------------------------

FOCUS = "Flawless"


def make_games(anchor: str, opening_scores, white_is_focus=True):
    """opening_scores: list of (opening_name, wins, losses, draws) from FOCUS view.

    Colors alternate per game so both sides are covered deterministically.
    """
    games = []
    gi = 0
    for oname, w, l, d in opening_scores:
        seq = ["1-0"] * w + ["0-1"] * l + ["1/2-1/2"] * d
        for k, res in enumerate(seq):
            gi += 1
            if k % 2 == 0:
                white, black = FOCUS, anchor
                result = res
            else:
                white, black = anchor, FOCUS
                # res is from focus view; flip decisive results
                result = {"1-0": "0-1", "0-1": "1-0", "1/2-1/2": "1/2-1/2"}[res]
            games.append({
                "opening": oname, "white": white, "black": black,
                "result": result, "counted": True, "engine_error": False,
                "game_index": gi,
            })
    return games


def write_jsonl(path, games):
    with open(path, "w") as f:
        for g in games:
            f.write(json.dumps(g) + "\n")


def pool_entry(name, elo, err, conv="ci95"):
    return {
        "name": name, "version": "1.0", "sha256": "b" * 64,
        "published_elo": elo, "published_error": err, "error_convention": conv,
        "license": "GPL-3.0", "license_verified": True,
        "binary_source_url": "https://example.org/x", "binary_downloaded": True,
        "binary_sha256_verified": True,
    }


def uniform_openings(n_open, w, l, d, prefix="op"):
    return [(f"{prefix}{i:03d}", w, l, d) for i in range(n_open)]


def varied_openings(n_open, prefix="v"):
    """Heterogeneous clusters (required: uniform clusters make Sigma_m degenerate).

    Per opening: wins 24..26, losses 4..6, draws fill to 34. Points per opening
    25..29/34 -> s in [0.735, 0.853] -> |d| < 400 (no saturation), and every
    cluster is interior so no bootstrap replicate hits a boundary.
    """
    out = []
    for i in range(n_open):
        w = 24 + (i % 3)
        l = 4 + ((i // 3) % 3)
        d = 34 - w - l
        out.append((f"{prefix}{i:03d}", w, l, d))
    return out


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


def test_eps_conversion():
    check(close(re.eps_sd_from_entry({"error_convention": "ci95", "published_error": 19.6}), 10.0),
          "ci95 -> /1.96")
    check(close(re.eps_sd_from_entry({"error_convention": "ci90", "published_error": 16.45}), 10.0),
          "ci90 -> /1.645")
    check(close(re.eps_sd_from_entry({"error_convention": "ci99", "published_error": 25.76}), 10.0),
          "ci99 -> /2.576")
    check(close(re.eps_sd_from_entry({"error_convention": "sd", "published_error": 10.0}), 10.0),
          "sd as-is")
    check(close(re.eps_sd_from_entry({"error_convention": "se", "published_error": 10.0}), 10.0),
          "se as-is")
    try:
        re.eps_sd_from_entry({"error_convention": "plusminus", "published_error": 10})
        check(False, "ambiguous convention rejected")
    except SystemExit:
        check(True, "ambiguous convention rejected")


def test_gls_math():
    # Identity covariance -> simple average.
    w, _, mode = re.gls([[1.0, 0.0], [0.0, 1.0]], [2000.0, 2100.0])
    check(mode == "gls" and close(sum(w), 1.0) and close(w[0], 0.5), "GLS identity -> average")
    theta = sum(w[i] * y for i, y in enumerate([2000.0, 2100.0]))
    check(close(theta, 2050.0), "GLS theta 2050")
    # Singular covariance -> documented diagonal fallback.
    w2, _, mode2 = re.gls([[1.0, 1.0], [1.0, 1.0]], [2000.0, 2100.0])
    check(mode2 == "diagonal-wls-fallback" and close(sum(w2), 1.0), "singular -> diagonal WLS fallback")
    # Weighted: diag variances 1 and 3 -> weights 3/4, 1/4.
    w3, _, _ = re.gls([[1.0, 0.0], [0.0, 3.0]], [2000.0, 2100.0])
    check(close(w3[0], 0.75) and close(w3[1], 0.25), "GLS inverse-variance weights")


def test_joint_bootstrap_correlation():
    # Both anchors do better in the same openings -> d_a co-move -> positive cov.
    easy = [(f"e{i}", 20, 2, 2) for i in range(30)]
    hard = [(f"h{i}", 8, 14, 2) for i in range(30)]
    scores = easy + hard
    a1 = {"name": "A1", "published_elo": 2000, "eps_sd": 10.0,
          "clusters": {t[0]: make_cluster_list(t) for t in scores}}
    a2 = {"name": "A2", "published_elo": 2100, "eps_sd": 10.0,
          "clusters": {t[0]: make_cluster_list(t) for t in scores}}
    boot = re.joint_bootstrap([a1, a2], 2000, 42)
    _, cov = re.col_means_cov(boot["D"])
    check(cov[0][1] > 0, f"shared opening difficulty -> positive off-diagonal cov ({cov[0][1]:.3f})")
    check(cov[0][0] > 0 and cov[1][1] > 0, "positive variances")
    # Reproducibility under fixed seed.
    boot2 = re.joint_bootstrap([a1, a2], 2000, 42)
    check(boot["D"] == boot2["D"], "fixed seed -> identical replicates")
    boot3 = re.joint_bootstrap([a1, a2], 2000, 43)
    check(boot["D"] != boot3["D"], "different seed -> different replicates")


def make_cluster_list(triple):
    _, w, l, d = (triple[0], triple[1], triple[2], triple[3]) if len(triple) == 4 else (None,) + triple
    return [1.0] * w + [0.0] * l + [0.5] * d


def test_boundaries_excluded_and_reported():
    # Registered RATING_PROTOCOL §8.3/§9.4 semantics (supersedes the
    # pre-2026-11-28 fail-closed crash contract, which diverged from the
    # protocol): boundary scores are never clamped and never fatal — the anchor
    # is excluded from the WLS, reported with its raw score and a §8.3/§9.4
    # reason, and flagged for replacement by a nearer calibrated anchor.
    a = {"name": "A", "published_elo": 1900, "eps_sd": 10.0,
         "clusters": {f"op{i}": [1.0] * 20 for i in range(5)}}
    boot = re.joint_bootstrap([a], 100, 7)
    check(boot["nonfinite_reps"] == [100],
          "perfect score: every bootstrap replicate counted non-finite")
    a2 = {"name": "A", "published_elo": 1900, "eps_sd": 10.0,
          "clusters": {f"op{i}": [0.0] * 20 for i in range(5)}}
    boot2 = re.joint_bootstrap([a2], 100, 7)
    check(boot2["nonfinite_reps"] == [100],
          "zero score: every bootstrap replicate counted non-finite")
    # end-to-end through batch_estimate: exclusion recorded, nothing clamped.
    sweep = make_games("S", uniform_openings(5, 20, 0, 0))
    res = re.batch_estimate({"S": sweep}, [pool_entry("S", 1900, 20)], FOCUS, 50, 7)
    p = res["per_anchor"][0]
    check(p["d_flawless_minus_anchor"] is None and p["boundary"] and not p["gate_eligible"],
          "boundary anchor excluded and reported (d null, never clamped)")
    check(res["theta"] is None and res["eligible_anchors"] == [],
          "no WLS exists when every anchor is boundary — reported, not crashed")
    check("§8.3" in p["excluded_reason"] and "replace" in p["excluded_reason"],
          "exclusion reason names the registered replacement recovery")


def test_batch_estimate_recovery():
    # Flawless scores 28/34 = 0.8235 vs anchor at 2000 -> d = +262.5.
    scores = uniform_openings(60, 27, 5, 2)
    games = make_games("A1", scores)
    entries = [pool_entry("A1", 2000, 30)]
    res = re.batch_estimate({"A1": games}, entries, FOCUS, 2000, 20261114)
    s = 28.0 / 34.0
    d_expected = -400.0 * math.log10(1.0 / s - 1.0)
    check(close(res["per_anchor"][0]["d_flawless_minus_anchor"], d_expected, 1e-6),
          f"per-anchor d recovery ({res['per_anchor'][0]['d_flawless_minus_anchor']:.2f} vs {d_expected:.2f})")
    check(close(res["theta"], 2000 + d_expected, 1e-6), "single-anchor theta = R + d")
    check(res["ci95_calibrated"][0] < res["theta"] < res["ci95_calibrated"][1], "CI brackets theta")
    lo_m, hi_m = res["ci95_match_only"]
    lo_c, hi_c = res["ci95_calibrated"]
    check((hi_c - lo_c) > (hi_m - lo_m), "calibration widens the CI")
    check(res["per_anchor"][0]["gate_eligible"], "d within saturation limit")
    check(res["per_anchor"][0]["n_counted_games"] == 60 * 34, "game count")


def test_saturation_flagged():
    # d = +500 saturates: recorded, ineligible for gate.
    scores = uniform_openings(60, 33, 1, 0)
    games = make_games("A1", scores)
    res = re.batch_estimate({"A1": games}, [pool_entry("A1", 2000, 30)], FOCUS, 500, 1)
    p = res["per_anchor"][0]
    check(p["d_flawless_minus_anchor"] > 400 and not p["gate_eligible"] and p["saturated"],
          "saturation recorded and excluded from gate eligibility")


def test_boundary_anchor_excluded_not_fatal():
    # REGRESSION (protocol §8.2/§8.3/§9.4 divergence, discovered on the real
    # ENGINE-4 confirmatory evidence 2026-11-28): an anchor with a boundary
    # score (s = 1.0 sweep) used to abort the whole gate with
    # "bootstrap replicate 0 hit a boundary score (non-finite Elo)".
    # Registered treatment is exclusion + reporting + replacement, never clamp
    # and never a crash: the WLS must run on the remaining anchors and the
    # exclusion must be reported with its raw score and the §8.3/§9.4 reason.
    sweep = make_games("W", uniform_openings(60, 34, 0, 0))
    h1 = make_games("H1", varied_openings(60, prefix="a"))
    h2 = make_games("H2", varied_openings(60, prefix="a"))
    entries = [pool_entry("W", 1800, 22), pool_entry("H1", 2300, 17), pool_entry("H2", 2400, 14)]
    res = re.batch_estimate({"W": sweep, "H1": h1, "H2": h2}, entries, FOCUS, 500, 7)
    pw = res["per_anchor"][0]
    check(pw["d_flawless_minus_anchor"] is None, "boundary d reported as null (never clamped)")
    check(pw["boundary"] and not pw["gate_eligible"] and not pw["saturated"],
          "boundary anchor marked, gate-ineligible")
    check("§8.3" in pw["excluded_reason"] and "§9.4" in pw["excluded_reason"],
          "exclusion reason cites the registered protocol clauses")
    check(pw["score"] == 1.0, "raw boundary score still reported")
    check(res["eligible_anchors"] == ["H1", "H2"], "WLS runs on the non-boundary anchors")
    check(math.isfinite(res["theta"]), "theta finite after exclusion")
    check(len(res["weights"]) == 2, "WLS dimension equals the eligible set")
    check(res["bootstrap_boundary_exclusions"] == [], "no bootstrap-boundary exclusions here")
    # The excluded anchor must not influence theta: single-anchor world H1.
    solo = re.batch_estimate({"H1": h1}, [pool_entry("H1", 2300, 17)], FOCUS, 500, 7)
    combined = re.batch_estimate({"H1": h1, "H2": h2},
                                 [pool_entry("H1", 2300, 17), pool_entry("H2", 2400, 14)],
                                 FOCUS, 500, 7)
    check(abs(combined["theta"] - res["theta"]) < 1e-6,
          "boundary anchor excluded from WLS: estimate equals the eligible-only estimate")


def test_saturated_anchor_excluded_from_wls():
    # §8.2: saturated anchors are excluded from the gate; §8.3: from the WLS.
    sat = make_games("S", uniform_openings(60, 33, 1, 0))
    h1 = make_games("H1", varied_openings(60, prefix="a"))
    entries = [pool_entry("S", 2000, 30), pool_entry("H1", 2300, 17)]
    res = re.batch_estimate({"S": sat, "H1": h1}, entries, FOCUS, 500, 3)
    ps = res["per_anchor"][0]
    check(ps["saturated"] and not ps["gate_eligible"] and ps["d_flawless_minus_anchor"] > 400,
          "saturated anchor keeps its finite d and is marked")
    check(res["eligible_anchors"] == ["H1"], "saturated anchor excluded from WLS")
    check(close(res["theta"], 2300.0 + re.elo_from_score(
        sum(sum(v) for v in re.focus_scores_by_opening(h1, FOCUS).values()) /
        sum(len(v) for v in re.focus_scores_by_opening(h1, FOCUS).values())), 1e-6),
        "single eligible anchor: theta = published + observed d exactly")


def test_bootstrap_boundary_anchor_excluded():
    # §9.4 face 2: an anchor whose OBSERVED score is interior (|d| <= 400) but
    # whose cluster composition makes bootstrap resamples hit s = 0/1 is
    # uninformative — excluded with a reported reason, never fatal, never
    # clamped. Two win-clusters + one loss-cluster: observed 4/6 (interior) but
    # (2/3)^3 of resamples sweep.
    bad = make_games("BAD", [("o0", 2, 0, 0), ("o1", 2, 0, 0), ("o2", 0, 2, 0)])
    h1 = make_games("H1", [("o0", 1, 1, 0), ("o1", 1, 1, 0), ("o2", 1, 1, 0)])
    h2 = make_games("H2", [("o0", 1, 1, 0), ("o1", 1, 1, 0), ("o2", 1, 1, 0)])
    entries = [pool_entry("BAD", 1800, 22), pool_entry("H1", 2300, 17), pool_entry("H2", 2400, 14)]
    res = re.batch_estimate({"BAD": bad, "H1": h1, "H2": h2}, entries, FOCUS, 100, 5)
    pbad = res["per_anchor"][0]
    check(pbad["d_flawless_minus_anchor"] is None and pbad["boundary"],
          "bootstrap-boundary anchor reported as boundary, d null")
    check("§9.4" in pbad["excluded_reason"], "bootstrap exclusion cites §9.4")
    check(res["bootstrap_boundary_exclusions"] == ["BAD"],
          "bootstrap-boundary exclusion recorded by name")
    check(res["eligible_anchors"] == ["H1", "H2"], "WLS proceeds on the informative anchors")
    check(math.isfinite(res["theta"]), "theta finite after bootstrap-boundary exclusion")


def test_shared_calibration():
    # Two near-identical batches: shared calibration must be added ONCE.
    scores = varied_openings(60)
    games = make_games("A1", scores)
    entries = [pool_entry("A1", 2000, 30), pool_entry("A2", 2100, 30), pool_entry("A3", 1900, 30)]
    g2 = {"A1": games, "A2": make_games("A2", scores), "A3": make_games("A3", scores)}
    ba = re.batch_estimate(g2, entries, FOCUS, 1000, 11)
    bb = re.batch_estimate(g2, entries, FOCUS, 1000, 12)
    comb = re.combine_batches(ba, bb)
    check(comb["var_match_pooled"] < ba["var_match"], "match noise pools down")
    check(comb["var_cal_shared"] > 0.5 * ba["var_cal"],
          "shared calibration NOT halved by pooling")
    check(close(comb["var_cal_shared"], ba["var_cal"], 0.1 * max(ba["var_cal"], 1.0)),
          "identical batches: shared calibration added once (within bootstrap jitter)")
    check(comb["var_total"] > comb["var_match_pooled"], "calibration still in the total variance")
    lam = comb["weight_batch_a"]
    check(close(lam, 0.5, 0.05), "near-identical batches -> ~equal weights")
    check(close(comb["theta"], lam * ba["theta"] + (1 - lam) * bb["theta"]),
          "combined theta weighted mean")
    lo_m, hi_m = comb["ci95_match_only"]
    lo_c, hi_c = comb["ci95_calibrated"]
    check((hi_c - lo_c) > (hi_m - lo_m), "combined calibrated CI wider than match-only")


def test_missing_invalid_evidence():
    try:
        re.load_games("/nonexistent/games.jsonl", FOCUS)
        check(False, "missing file rejected")
    except SystemExit:
        check(True, "missing file rejected (fail closed)")
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "g.jsonl")
        write_jsonl(p, [{"opening": "x", "white": "Someone", "black": "Else",
                         "result": "1-0", "counted": True}])
        try:
            re.load_games(p, FOCUS)
            check(False, "games without focus rejected")
        except SystemExit:
            check(True, "games without focus engine rejected")
        write_jsonl(p, [{"opening": "x", "white": FOCUS, "black": "A",
                         "result": "1-0", "counted": False, "engine_error": True}])
        games = re.load_games(p, FOCUS)
        check(games == [], "uncounted/engine-error games excluded from statistics")


def test_null_controls():
    scores = uniform_openings(60, 20, 2, 2)  # focus A1 view: s=0.647
    # A1 (2000) vs A2 (2100) should measure A1 - A2 ~ +117 - ... construct so the
    # measured diff equals published: give A1 score 0.647 vs A2 -> d = +111.
    games = []
    for oname, w, l, d in scores:
        seq = ["1-0"] * w + ["0-1"] * l + ["1/2-1/2"] * d
        for res in seq:
            games.append({"opening": oname, "white": "A1", "black": "A2",
                          "result": res, "counted": True, "engine_error": False})
    s = 21.0 / 24.0  # 20 wins + 2 draws out of 24 per opening
    d_meas = -400.0 * math.log10(1.0 / s - 1.0)
    # Published diff crafted to match exactly -> pass.
    e1 = pool_entry("A1", 2000, 30)
    e2 = pool_entry("A2", 2000 - d_meas, 30)
    res = re.control_anchor_vs_anchor(games, e1, e2, 1000, 5)
    check(res["pass"] and abs(res["error"]) < 1e-6, "null control exact recovery passes")
    # Published diff off by 100 -> fail.
    e3 = pool_entry("A2", 2000 - d_meas + 100, 30)
    res2 = re.control_anchor_vs_anchor(games, e1, e3, 1000, 5)
    check(not res2["pass"], "null control off by 100 Elo fails")
    # Self-match: fair scores -> pass; biased -> fail.
    fair = make_games("Opp", uniform_openings(60, 10, 10, 4))
    r = re.control_self_match(fair, FOCUS, 1000, 5)
    check(r["pass"], "fair self-match passes")
    biased = make_games("Opp", uniform_openings(60, 30, 2, 2))
    r2 = re.control_self_match(biased, FOCUS, 1000, 5)
    check(not r2["pass"], "biased self-match fails")




def test_anchor_label_key_matching():
    # Frozen-pool reality: display names are NOT unique (two 'Topple' versions);
    # games are recorded under the unique pool key (the match harness label).
    e1 = pool_entry("Topple", 2000, 30)
    e1["key"] = "topple-0.1.1"
    e2 = pool_entry("Topple", 2100, 30)
    e2["key"] = "topple-0.2.1"
    check(re.anchor_label(e1) == "topple-0.1.1", "anchor_label prefers unique key")
    check(re.anchor_label(pool_entry("Solo", 2000, 30)) == "Solo",
          "anchor_label falls back to name for older descriptors")

    g1 = make_games("topple-0.1.1", uniform_openings(20, 8, 4, 2))
    g2 = make_games("topple-0.2.1", uniform_openings(20, 4, 8, 2))
    res = re.batch_estimate({"topple-0.1.1": g1, "topple-0.2.1": g2},
                            [e1, e2], FOCUS, 500, 7)
    names = [p["name"] for p in res["per_anchor"]]
    check(names == ["topple-0.1.1", "topple-0.2.1"],
          "batch_estimate matches anchors by key despite duplicate display names")

    games = []
    for oname, w, l, d in uniform_openings(20, 12, 4, 2):
        seq = ["1-0"] * w + ["0-1"] * l + ["1/2-1/2"] * d
        for r_ in seq:
            games.append({"opening": oname, "white": "topple-0.1.1", "black": "topple-0.2.1",
                          "result": r_, "counted": True, "engine_error": False})
    cr = re.control_anchor_vs_anchor(games, e1, e2, 500, 5)
    check(math.isfinite(cr["error"]),
          "anchor-vs-anchor control scores via key labels (not display names)")

def test_verify_evidence_fail_closed():
    import verify_evidence as ve
    import shutil, hashlib, os
    td = tempfile.mkdtemp()
    try:
        # Build a minimal committed-evidence fixture for one batch/anchor + one control.
        def mk_evidence(base, records, suite="s" * 64, eng="e" * 64, anc="a" * 64):
            os.makedirs(base, exist_ok=True)
            gp = os.path.join(base, "games.jsonl")
            with open(gp, "w") as f:
                for r in records:
                    f.write(json.dumps(r) + "\n")
            man = {"engine_sha256": eng, "anchor_sha256": anc,
                   "opening_suite_sha256": suite,
                   "n_counted": sum(1 for r in records if r.get("counted")),
                   "merged_sha256": hashlib.sha256(open(gp, "rb").read()).hexdigest()}
            with open(os.path.join(base, "manifest.json"), "w") as f:
                json.dump(man, f)
            return man

        rec = [{"moves": "e2e4 e7e5", "result": "1-0", "counted": True,
                "engine_error": False, "_shard_id": "s0", "schedule_index": 0,
                "replay_depth": 0}]
        eng = "e" * 64
        anc = "a" * 64
        mk_evidence(f"{td}/benches/evidence/batchA/topple-x", rec, eng=eng, anc=anc)
        mk_evidence(f"{td}/benches/evidence/control/pair", rec, eng=eng, anc=anc)
        pool = {"engines": [{"key": "topple-x", "name": "Topple", "sha256": anc}]}
        plan = {"schema": 1, "engine_sha256": eng, "min_games": 1,
                "batches": {"A": {"suite_sha256": "s" * 64, "anchors": ["topple-x"]}},
                "controls": {"pair": {"evidence": f"{td}/benches/evidence/control/pair/games.jsonl",
                                      "suite_sha256": "s" * 64,
                                      "white_sha256": eng,
                                      "black_sha256": anc,
                                      "min_counted": 1}}}
        pp = f"{td}/pool.json"; json.dump(pool, open(pp, "w"))
        pl = f"{td}/plan.json"; json.dump(plan, open(pl, "w"))

        cwd = os.getcwd()
        os.chdir(td)
        try:
            rep = ve.verify_all(pl, pp)
            check(rep["batches"]["A"]["anchors"][0]["n_counted"] == 1,
                  "verify_evidence accepts intact committed evidence")
            # Corrupt the committed games bytes -> merged_sha256 must fail closed.
            gp = f"{td}/benches/evidence/batchA/topple-x/games.jsonl"
            open(gp, "a").write(json.dumps({"moves": "d2d4", "result": "*", "counted": False,
                                            "engine_error": False, "_shard_id": "s0",
                                            "schedule_index": 1, "replay_depth": 0}) + "\n")
            try:
                ve.verify_all(pl, pp)
                check(False, "tampered games.jsonl must fail closed")
            except ve.EvidenceError:
                check(True, "tampered games.jsonl must fail closed")
            # Wrong suite hash in the plan -> fail closed.
            plan["batches"]["A"]["suite_sha256"] = "x" * 64
            json.dump(plan, open(pl, "w"))
            # restore games file
            mk_evidence(f"{td}/benches/evidence/batchA/topple-x", rec, eng=eng, anc=anc)
            try:
                ve.verify_all(pl, pp)
                check(False, "suite-hash divergence must fail closed")
            except ve.EvidenceError:
                check(True, "suite-hash divergence must fail closed")
        finally:
            os.chdir(cwd)
    finally:
        shutil.rmtree(td, ignore_errors=True)


def test_gate_uses_eligible_subset_of_pool():
    # Frozen pools may hold more anchors than the preregistered batch selection:
    # the gate must run on exactly the anchors with evidence in BOTH batches.
    import tempfile, os, json as _json
    with tempfile.TemporaryDirectory() as td:
        e = [pool_entry(f"P{i}", 2000 + 30 * i, 20) for i in range(6)]
        for i, ent in enumerate(e):
            ent["key"] = f"p{i}"
        pj = os.path.join(td, "pool.json")
        _json.dump({"engines": e}, open(pj, "w"))
        sel = ["p1", "p2", "p4"]  # 3 of 6 anchors selected
        files = {}
        for b, pref in (("A", "a"), ("B", "b")):
            for k in sel:
                p = os.path.join(td, f"{pref}-{k}.jsonl")
                # SAME opening clusters within a batch (joint bootstrap requirement);
                # disjoint prefixes across batches A/B.
                write_jsonl(p, make_games(k, varied_openings(25, prefix=pref)))
                files[b] = files.get(b, []) + [f"{k}={p}"]
        # Dedicated anchor-vs-anchor control file (neither side is the focus).
        ctrl = os.path.join(td, "ctrl-a1a2.jsonl")
        rows = []
        for oname, w, l, d in varied_openings(25, prefix="c"):
            seq = ["1-0"] * w + ["0-1"] * l + ["1/2-1/2"] * d
            for r_ in seq:
                rows.append({"opening": oname, "white": "p1", "black": "p2", "result": r_,
                             "counted": True, "engine_error": False})
        write_jsonl(ctrl, rows)
        selfp = files["B"][0].split("=", 1)[1]

        def gate_argv(batch_a, out):
            return ["rating_estimator.py", "gate", "--anchor-json", pj, "--focus", FOCUS,
                    "--batch-a"] + batch_a + ["--batch-b"] + files["B"] + [
                    "--control-anchor", ctrl, "--control-anchor-names", "p1", "p2",
                    "--control-self", selfp,
                    "--min-games", "10", "--threshold", "0", "--bootstrap", "100",
                    "--seed", "1", "--out", out]

        # A-only extra anchor in batch A -> sets differ -> fail closed.
        extra = os.path.join(td, "x.jsonl")
        write_jsonl(extra, make_games("p5", varied_openings(25, prefix="a")))
        outp = os.path.join(td, "out.json")
        sys.argv = gate_argv(files["A"] + [f"p5={extra}"], outp)
        try:
            re.main()
            check(not os.path.exists(outp), "A/B anchor-set mismatch must fail closed")
        except SystemExit:
            check(True, "A/B anchor-set mismatch must fail closed")
        # Matching 3-of-6 selection: gate runs on the subset and evaluates.
        sys.argv = gate_argv(files["A"], outp)
        try:
            re.main()
        except SystemExit:
            pass  # exit code reflects the gate verdict
        out = _json.load(open(outp))
        used = {p["name"] for p in out["results"]["batch_a"]["per_anchor"]}
        check(used == set(sel), f"gate evaluated exactly the eligible subset (got {used})")


# ---------------------------------------------------------------------------
# Full gate end-to-end (subprocess, fail closed both ways)
# ---------------------------------------------------------------------------


def anchor_openings(prefix, base_w, l, n=60):
    """Heterogeneous per-opening (w, l, d) with 34 games per opening, common names
    across anchors (the joint bootstrap requires identical opening suites)."""
    out = []
    for i in range(n):
        w = base_w + (i % 3)
        d = 34 - w - l
        out.append((f"{prefix}{i:03d}", w, l, d))
    return out


def build_gate_inputs(td, self_bias=False):
    # Transitively consistent world: published A1=1900, A2=2000, A3=2100 and
    # manufactured Flawless scores imply d(A1-A2) = (F-A2)-(F-A1) = -100, which
    # the anchor-vs-anchor control must then recover.
    scores = {
        "A1": anchor_openings("x", 25, 6),   # d(F-A1) ~ +233 -> F ~ 2133
        "A2": anchor_openings("x", 21, 9),   # d(F-A2) ~ +137
        "A3": anchor_openings("x", 15, 12),  # d(F-A3) ~ +41
    }
    anchors = [("A1", 1900), ("A2", 2000), ("A3", 2100)]
    pool = {
        "rating_source": "CCRL 40/15 list",
        "list_publication_date": "2026-11-13",
        "retrieval_date": "2026-11-14",
        "time_control": "40 moves in 15 minutes",
        "engines": [pool_entry(n, e, 30) for n, e in anchors],
    }
    pj = os.path.join(td, "pool.json")
    json.dump(pool, open(pj, "w"))
    for batch in ("A", "B"):
        for n, _e in anchors:
            games = make_games(n, scores[n])
            write_jsonl(os.path.join(td, f"{batch}-{n}.games.jsonl"), games)
    # anchor-vs-anchor control: A1 vs A2 with d(A1-A2) = -95.6 ~= published -100.
    ctrl = []
    for oname, w, l, d in anchor_openings("c", 10, 19):
        seq = ["1-0"] * w + ["0-1"] * l + ["1/2-1/2"] * d
        for res in seq:
            ctrl.append({"opening": oname, "white": "A1", "black": "A2", "result": res,
                         "counted": True, "engine_error": False})
    write_jsonl(os.path.join(td, "ctrl-anchor.jsonl"), ctrl)
    self_scores = uniform_openings(60, 2, 30, 2) if self_bias else uniform_openings(60, 10, 10, 4)
    write_jsonl(os.path.join(td, "ctrl-self.jsonl"), make_games("Opp", self_scores))
    return pj


def gate_args(td, pj, batch_b=None, out="gate.json"):
    names = ("A1", "A2", "A3")
    return [sys.executable, os.path.join(HERE, "rating_estimator.py"), "gate",
            "--anchor-json", pj, "--focus", FOCUS,
            "--batch-a"] + [f"{n}={os.path.join(td, f'A-{n}.games.jsonl')}" for n in names] + \
           ["--batch-b"] + (batch_b or [f"{n}={os.path.join(td, f'B-{n}.games.jsonl')}" for n in names]) + \
           ["--control-anchor", os.path.join(td, "ctrl-anchor.jsonl"),
            "--control-anchor-names", "A1", "A2",
            "--control-self", os.path.join(td, "ctrl-self.jsonl"),
            "--min-games", "2000", "--threshold", "2000",
            "--bootstrap", "2000", "--seed", "20261114",
            "--out", os.path.join(td, out)]


def test_gate_full():
    with tempfile.TemporaryDirectory() as td:
        pj = build_gate_inputs(td, self_bias=False)
        proc = subprocess.run(gate_args(td, pj), capture_output=True, text=True, timeout=600)
        res = json.load(open(os.path.join(td, "gate.json")))
        check(proc.returncode == 0, f"gate passes on strong evidence (rc={proc.returncode})")
        check(res["pass"] is True, "gate verdict PASS")
        check(res["results"]["batch_a"]["ci95_calibrated"][0] > 2000, "A lower bound > 2000")
        check(res["results"]["batch_b"]["ci95_calibrated"][0] > 2000, "B lower bound > 2000")
        check(res["results"]["combined"]["ci95_calibrated"][0] > 2000, "combined lower bound > 2000")
    with tempfile.TemporaryDirectory() as td:
        pj = build_gate_inputs(td, self_bias=True)  # self-match control poisoned
        proc = subprocess.run(gate_args(td, pj), capture_output=True, text=True, timeout=600)
        res = json.load(open(os.path.join(td, "gate.json")))
        check(proc.returncode != 0, "gate FAILS when a null control fails")
        check(res["pass"] is False, "verdict FAIL recorded")
        check(any("self-match" in c["check"] and not c["pass"] for c in res["checks"]),
              "failed control named in checks")
    with tempfile.TemporaryDirectory() as td:
        pj = build_gate_inputs(td, self_bias=False)
        out = os.path.join(td, "gate.json")
        # Missing batch-B evidence -> must fail closed.
        proc = subprocess.run(
            gate_args(td, pj, batch_b=["A1=/nonexistent/B-A1.games.jsonl"]),
            capture_output=True, text=True, timeout=600)
        check(proc.returncode != 0, "missing evidence -> gate refuses (fail closed)")


def _build_exclusion_gate_world(td, n_healthy, with_sweep=True):
    """n_healthy transitively-consistent anchors (+1 sweeping boundary anchor)."""
    anchors = [(f"A{i+1}", 1900 + 100 * i) for i in range(n_healthy)]
    scores = {}
    for i, (n, _e) in enumerate(anchors):
        scores[n] = anchor_openings("x", 25 - 4 * i, 6 + 3 * i)
    names = [n for n, _ in anchors]
    if with_sweep:
        scores["SWEEP"] = uniform_openings(60, 34, 0, 0)
        anchors.append(("SWEEP", 1800))
    pool = {"rating_source": "CCRL 40/15 list", "list_publication_date": "2026-11-13",
            "retrieval_date": "2026-11-14", "time_control": "40 moves in 15 minutes",
            "engines": [pool_entry(n, e, 30) for n, e in anchors]}
    pj = os.path.join(td, "pool.json")
    json.dump(pool, open(pj, "w"))
    for batch in ("A", "B"):
        for n, _e in anchors:
            write_jsonl(os.path.join(td, f"{batch}-{n}.games.jsonl"), make_games(n, scores[n]))
    ctrl = []
    for oname, w, l, d in anchor_openings("c", 10, 19):
        for res_ in ["1-0"] * w + ["0-1"] * l + ["1/2-1/2"] * d:
            ctrl.append({"opening": oname, "white": names[0], "black": names[1], "result": res_,
                         "counted": True, "engine_error": False})
    write_jsonl(os.path.join(td, "ctrl-anchor.jsonl"), ctrl)
    write_jsonl(os.path.join(td, "ctrl-self.jsonl"),
                make_games("Opp", uniform_openings(60, 10, 10, 4)))
    allnames = names + (["SWEEP"] if with_sweep else [])
    argv = [sys.executable, os.path.join(HERE, "rating_estimator.py"), "gate",
            "--anchor-json", pj, "--focus", FOCUS,
            "--batch-a"] + [f"{n}={os.path.join(td, f'A-{n}.games.jsonl')}" for n in allnames] + \
           ["--batch-b"] + [f"{n}={os.path.join(td, f'B-{n}.games.jsonl')}" for n in allnames] + \
           ["--control-anchor", os.path.join(td, "ctrl-anchor.jsonl"),
            "--control-anchor-names", names[0], names[1],
            "--control-self", os.path.join(td, "ctrl-self.jsonl"),
            "--min-games", "2000", "--threshold", "2000",
            "--bootstrap", "2000", "--seed", "20261114",
            "--out", os.path.join(td, "gate.json")]
    return argv, [n for n, _ in anchors]


def test_gate_boundary_anchor_reported_not_fatal():
    # REGRESSION: a boundary (sweep) anchor must not crash the gate; it must be
    # excluded per §8.2/§8.3 with a reported reason, and the >=3 check must
    # count only jointly-eligible anchors. With 3 healthy + 1 sweep the gate
    # runs the CI checks on the healthy set (same world as test_gate_full -> PASS).
    with tempfile.TemporaryDirectory() as td:
        argv, names = _build_exclusion_gate_world(td, n_healthy=3, with_sweep=True)
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=600)
        res = json.load(open(os.path.join(td, "gate.json")))
        check(res["gate_eligible_anchors"] == sorted(names[:3]),
              f"jointly-eligible anchors = the healthy three (got {res['gate_eligible_anchors']})")
        check("SWEEP" in res["excluded_anchors"], "sweep anchor reported in the exclusion record")
        check(res["excluded_anchors"]["SWEEP"]["batch_a"] and
              "§8.3" in res["excluded_anchors"]["SWEEP"]["batch_a"],
              "exclusion reason cites §8.3 in the gate output")
        check(any(c["pass"] and ">= 3 gate-eligible anchors" in c["check"] for c in res["checks"]),
              "eligibility check present and passing with 3 eligible")
        check(res["results"]["batch_a"]["per_anchor"][3]["d_flawless_minus_anchor"] is None,
              "boundary per-anchor row carries null d (never clamped)")
        check(proc.returncode == 0 and res["pass"] is True,
              f"gate evaluates the eligible subset to a verdict (rc={proc.returncode})")


def test_gate_fail_closed_under_three_eligible():
    # With the sweep excluded only 2 eligible anchors remain -> the registered
    # >=3 design requirement must fail the gate with the exclusion named.
    with tempfile.TemporaryDirectory() as td:
        argv, names = _build_exclusion_gate_world(td, n_healthy=2, with_sweep=True)
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=600)
        res = json.load(open(os.path.join(td, "gate.json")))
        check(proc.returncode != 0, "gate FAILS with <3 jointly-eligible anchors")
        check(res["pass"] is False and res["verdict"] == "FAIL", "verdict FAIL recorded")
        elig = [c for c in res["checks"] if ">= 3 gate-eligible anchors" in c["check"]]
        check(elig and not elig[0]["pass"], "the failing check is the >=3 eligibility check")
        check("SWEEP" in elig[0]["check"], "failing check names the excluded anchor and reason")


def test_focus_label_case_insensitive():
    # Harness history: the focus engine was seated under the display name
    # "Flawless" while pool keys / estimator focus are lowercase. Labels are
    # display metadata (identity = binary SHA-256); matching must be
    # case-insensitive or valid committed evidence fails closed.
    games = make_games("topple-0.1.1", uniform_openings(20, 12, 4, 4))
    res = re.batch_estimate({"topple-0.1.1": games},
                            [pool_entry("topple-0.1.1", 2324, 17)], "flawless", 400, 3)
    check(math.isfinite(res["theta"]),
          "batch_estimate: lowercase focus matches 'Flawless'-recorded games")
    s = sum(re.score_of(g["result"], "white" if g["white"] == "Flawless" else "black")
            for g in games) / len(games)
    check(close(res["per_anchor"][0]["d_flawless_minus_anchor"], re.elo_from_score(s)),
          "case-insensitive focus matching preserves the observed d")

    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "games.jsonl")
        with open(p, "w") as f:
            for g in games:
                f.write(json.dumps(g) + "\n")
        try:
            loaded = re.load_games(p, "flawless")
            check(len(loaded) == len(games),
                  "load_games accepts 'Flawless'-recorded games under focus 'flawless'")
        except re.EvidenceError:
            check(False, "load_games accepts 'Flawless'-recorded games under focus 'flawless'")
        p2 = os.path.join(td, "other.jsonl")
        with open(p2, "w") as f:
            f.write(json.dumps({"opening": "op0", "white": "topple-0.1.1",
                                "black": "topple-0.2.1", "result": "1-0",
                                "counted": True, "engine_error": False}) + "\n")
        try:
            re.load_games(p2, "flawless")
            check(False, "load_games rejects games without the focus engine")
        except re.EvidenceError:
            check(True, "load_games rejects games without the focus engine")

    self_games = []
    for oname, w, l, d in uniform_openings(20, 6, 6, 8):
        for i, r_ in enumerate(["1-0"] * w + ["0-1"] * l + ["1/2-1/2"] * d):
            self_games.append({"opening": oname, "white": "Flawless", "black": "Flawless",
                               "result": r_, "counted": True, "engine_error": False,
                               "color_pair": "AB" if i % 2 == 0 else "BA"})
    sm = re.control_self_match(self_games, "flawless", 500, 11)
    check(close(sm["score"], 0.5),
          "self-match control: display-cased games score via lowercase focus")


def test_self_match_seat_perspective():
    # Registered CTRL-2 semantics: identical binaries must score ~0.5 FROM THE
    # SEAT perspective — the chess color advantage cancels only via the AB/BA
    # seat reversal. Self-match records cannot distinguish seats by name (both
    # 'Flawless'), so the seat perspective comes from the recorded color_pair.
    # Construct data with a strong white advantage: AB games white wins, BA
    # games (seat A = black) white still wins -> seat A scores 1 and 0.
    games = []
    for oname, w, l, d in uniform_openings(30, 7, 3, 0, prefix="sm"):
        games.append({"opening": oname, "white": "Flawless", "black": "Flawless",
                      "result": "1-0", "counted": True, "engine_error": False,
                      "color_pair": "AB"})
        games.append({"opening": oname, "white": "Flawless", "black": "Flawless",
                      "result": "1-0", "counted": True, "engine_error": False,
                      "color_pair": "BA"})
    sm = re.control_self_match(games, "flawless", 2000, 20261116)
    check(close(sm["score"], 0.5),
          f"seat perspective cancels white advantage (score={sm['score']:.4f})")
    check(sm["pass"] is True, "balanced seat data passes the 0.5-in-CI control")
    check(close(sm["white_perspective_score"], 1.0),
          "white-perspective score reported for transparency (1.0 here)")
    # Unbalanced seat colors must fail closed (cannot measure seat fairness).
    bad = [dict(g, color_pair=None) for g in games]
    try:
        re.control_self_match(bad, "flawless", 100, 1)
        check(False, "self-match without color_pair fails closed")
    except re.EvidenceError:
        check(True, "self-match without color_pair fails closed")
    # All-BA data: seat A always black -> seat score = 1 - white score.
    ba_only = [dict(g, color_pair="BA") for g in games]
    sm2 = re.control_self_match(ba_only, "flawless", 1000, 7)
    check(close(sm2["score"], 0.0), "BA-only: seat A scores the black side exactly")


def main():
    test_eps_conversion()
    test_gls_math()
    test_joint_bootstrap_correlation()
    test_boundaries_excluded_and_reported()
    test_batch_estimate_recovery()
    test_saturation_flagged()
    test_boundary_anchor_excluded_not_fatal()
    test_saturated_anchor_excluded_from_wls()
    test_bootstrap_boundary_anchor_excluded()
    test_shared_calibration()
    test_missing_invalid_evidence()
    test_null_controls()
    test_anchor_label_key_matching()
    test_focus_label_case_insensitive()
    test_self_match_seat_perspective()
    test_verify_evidence_fail_closed()
    test_gate_uses_eligible_subset_of_pool()
    test_gate_full()
    test_gate_boundary_anchor_reported_not_fatal()
    test_gate_fail_closed_under_three_eligible()
    print(f"\n{PASS} checks passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
