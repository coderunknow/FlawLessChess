# PREREGISTRATION — confirmatory and exploratory experiments (append-only)

Policy (docs/RATING_PROTOCOL.md §9 / mission §8): every experiment is registered here with
objective, hypothesis, methodology, acceptance criteria, inputs and expected evidence BEFORE
its games are played. Entries are append-only; superseded plans are annotated, never deleted.
Confirmatory batches must not be tuned, re-anchored or re-opened after observing results.

---

## PILOT-1 — rating-run pipeline pilot (registered 2026-11-14, before dispatch)

- **Purpose:** exploratory (pipeline measurement only; its games are EXCLUDED from all gate
  evidence and never counted toward confirmatory sample sizes).
- **Objective:** measure end-to-end pipeline reliability and throughput of the GitHub-hosted
  rating-run workflow at real CCRL-class 40/15: game duration, games/hour/shard, timeout
  behavior, artifact integrity, manifest completeness, anchor-acquisition reliability.
- **Hypothesis:** the pipeline completes a 2-game shard with full manifests and hash-verified
  identities; average game wall-clock is ≤ 60 minutes; no engine or harness errors occur.
- **Methodology:** dispatch.json (purpose=pilot) → matrix of 2 shards, each the first
  contiguous 2-game slice of the frozen Batch-A schedule (60 openings × 17 paired reps ×
  AB/BA = 2,040 games; shard_count=1020 → 2 games per shard; indices 0 and 1 → 4 games
  total). Frozen suite `benches/rating-openings-batchA.txt` (SHA-256
  2c4a54d8a16f36d597cb2378ff74c1faafc636568647a257313274bd0969fc96), seed 20261114,
  TC 40/15, anchor topple-0.2.1 (frozen pool). engine_sha256 = "freeze" (first runner build
  of the target commit records the hash; nothing is claimed until it is pinned).
- **Acceptance criteria:** ≥ 3 of 4 games complete and are counted (unadjudicated);
  manifests contain engine/anchor/suite hashes that verify; artifacts upload; throughput
  numbers recorded in AGENTS_LOG.md; any failure triggers diagnosis + registered remediation.
- **Inputs:** benches/dispatch.json (schema 1) committed with this entry.
- **Expected evidence:** artifacts `rating-pilot-A-topple-0.2.1-shard{0,1}-<run_id>` +
  annotations with engine_sha256 and per-game JSONL.

### PILOT-1 result (filled after execution — see AGENTS_LOG.md for the raw record)

- status: IN EXECUTION (revision 3)
- freeze observations (annotations of run 43601528240): runner engine build of the frozen
  source (rustc 1.99.0, ubuntu-24.04) = SHA-256
  `fd75726dd3166640ddec75d94c416320b47c83e8d14bfa6309aed398d55b8e1d`, identical across two
  independent runner builds (runs 43597866181 verify-flawless and 43601528240) → byte-reproducible
  on this image/toolchain. Revision 3 pins this hash (strict mode). Any later hash mismatch
  fails closed and requires a documented re-freeze before further games.
- harness defects found by the pilot before any game completed (recorded in FAILURE_LEDGER):
  (1) config job-output double-encoding → checkout fallback to merge commit (rev 2);
  (2) shell word-splitting of `--white-cmd` argv (match.py: "unrecognized arguments: uci",
  exit 2) → step now drives match.py via an explicit argv list with stderr annotation capture.
- game/throughput results: PENDING (games run in revision 3+).

---

## CTRL-1 — anchor-vs-anchor null control (registered 2026-11-14, before dispatch)

- **Purpose:** control (null control #1 of §3.3 / mission). Validates that the pipeline +
  runners + 40/15 TC transfer relative ratings: a match between two frozen-pool anchors must
  recover their published CCRL rating difference within **±75 Elo** (mission-defined threshold;
  not adjusted here).
- **Pair:** white topple-0.1.1 (published 2324±17) vs black topple-0.2.1 (2439±14). Published
  diff (white − black) = **−115 Elo**. Same engine family, both verified id-mapped, both MIT.
- **Methodology:** 60 openings (`benches/rating-openings-batchA.txt`, SHA-256 2c4a54d8…)
  × 2 paired repetitions × AB/BA = **240 games**; shards of 2 games (shard_count=120,
  indices 0–119); TC 40/15 wall-clock; seed 20261115; engine_sha256 fd75726d… (flawless not
  seated; uniform strict check retained); batch CTRL, label `topple-0.1.1-vs-topple-0.2.1`.
- **Acceptance criterion (fixed):** |d̂ − (−115)| ≤ 75 Elo, where d̂ = −400·log10(1/s̄−1) from
  the completed-game score s̄ (white perspective), games counted per §9 adjudication rules.
  Failure → investigate transferability (runner TC/hardware), record in FAILURE_LEDGER, register
  remediation; never adjust the threshold.
- **Expected evidence:** artifacts `rating-CTRL-topple-0.1.1-vs-topple-0.2.1-shard*-<run_id>` +
  manifests (per-game JSONL with engine hashes).

## CTRL-2 — flawless self-match null control (registered 2026-11-14, before dispatch)

- **Purpose:** control (null control #2). Validates harness symmetry (colors, clocks, opening
  application): Flawless vs the identical binary must score **0.5 within its 95% binomial
  CI** (mission-defined threshold).
- **Methodology:** identical binary both sides (engine_sha256 fd75726d…), 60 openings (batch-A
  suite) × 2 paired repetitions × AB/BA = **240 games**; shards of 2 games (shard_count=120,
  indices 0–119); TC 40/15; seed 20261116; batch CTRL, label `flawless-self`.
- **Acceptance criterion (fixed):** 0.5 ∈ 95% binomial CI of the total score (wins + ½·draws)
  over the completed games. Failure → investigate asymmetry, record in FAILURE_LEDGER, register
  remediation; never adjust the threshold.
- **Expected evidence:** artifacts `rating-CTRL-flawless-self-shard*-<run_id>` + manifests.

### CTRL-1 / CTRL-2 results (filled after execution)

- status: PENDING EXECUTION

---

## SCREENING-1 / SCREENING-2 — anchor-selection screening estimates (registered 2026-11-14, before dispatch)

- **Purpose:** screening (exploratory; NEVER gate evidence; used ONLY to choose the
  confirmatory anchor set within §2's span/±400 rules — the protocol's prescribed use of a
  brief screening estimate). Pilot/CTRL data are likewise excluded from gate counts.
- **Objective:** bound the absolute estimate well enough to select ≥ 3 confirmatory anchors
  that are non-saturating (|d| ≤ 400 expected) and satisfy §2's span/coverage rules as the
  frozen pool allows (KNOWN TENSION: the pool gap 1849 → 2324 may make the literal
  [est−200, est+200] span rule unsatisfiable for est > 2249; the chosen interpretation will
  be documented explicitly at registration of the batches).
- **Methodology:** Flawless (engine_sha256 fd75726d…) vs topple-0.1.1 (published 2324±17,
  SCREENING-1) and vs topple-0.2.1 (2439±14, SCREENING-2): 60 openings
  (`benches/rating-openings-batchA.txt`, 2c4a54d8…) × 1 paired repetition × AB/BA = **120
  games each** (15 shards × 8 games); TC 40/15; seeds 20261119 (S-1) / 20261120 (S-2).
- **Analysis (pre-defined):** d̂ = −400·log10(1/s̄−1) per anchor from counted games; est =
  mean of (R_a + d̂_a) across the two anchors; uncertainty ~ binomial/cluster bootstrap (for
  SELECTION only — never reported as a rating). Selection rule: pick ≥ 3 pool anchors with
  expected |d| ≤ 400 around the screening estimate and straddling it within ±200 where the
  pool permits; include the widest low/high discriminators available.
- **Expected evidence:** `benches/evidence/screening/topple-0.1.1/` and `.../topple-0.2.1/`
  via the in-run evidence job.

### SCREENING results (filled after execution)

- status: PENDING EXECUTION

---

## BATCH-A / BATCH-B — confirmatory batches (registered 2026-11-14, BEFORE dispatch; anchor set filled per the fixed rule below before any game)

- **Purpose:** confirmatory (gate evidence). Thresholds and all inputs below are frozen now.
- **Acceptance (mission §9, unrounded):** for EACH of Batch A, Batch B and the combined
  estimate, the two-sided 95% calibrated CI lower bound must be strictly > 2,000 Elo;
  every eligible anchor: |d| ≤ 400 and ≥ 2,000 counted games **per batch**; both null
  controls pass their registered thresholds. No rounding, no clamping, no extrapolation.
- **Engine:** Flawless, engine_sha256 `fd75726dd3166640ddec75d94c416320b47c83e8d14bfa6309aed398d55b8e1d`
  (strict mode; any mismatch fails the shard).
- **Suites:** Batch A `benches/rating-openings-batchA.txt` SHA-256
  `2c4a54d8a16f36d597cb2378ff74c1faafc636568647a257313274bd0969fc96`; Batch B
  `benches/rating-openings-batchB.txt` SHA-256
  `744a3981cc312a676ba259962309858b7d2fc645094bf2dccf5391e77f2f9dd4`. VERIFIED DISJOINT
  2026-11-14: 60+60 lines, zero shared move-lines, zero shared names, zero internal
  duplicates (checked programmatically; see AGENTS_LOG 273).
- **Sample:** 60 openings × 17 paired repetitions × AB/BA = **2,040 games per eligible
  anchor per batch**; counted per §9 adjudication (move-cap games recorded `*`
  unadjudicated, never silently drawn; engine-error games excluded and replayed per policy).
- **Sharding:** 255 shards × 8 games per (batch, anchor) (deterministic contiguous slices of
  the frozen schedule; one marker dispatch per (batch, anchor); failed shards re-run into
  FRESH output only, never overwriting/mixing).
- **TC:** 40/15 wall-clock repeating (cutechess `add` semantics — verified at source), ponder
  off; SF10 factor_k 1.0291 deviation documented in the pool.
- **Bootstrap seeds (estimator):** Batch A `20261121`, Batch B `20261122` (combined uses the
  registered joint procedure). Dispatch seed fields carry the same values.
- **Anchor set (the ONLY rule-derived input):** chosen by the SCREENING-1/2 selection rule
  already registered above, from the frozen pool only: ≥ 3 anchors, all expected
  non-saturating (|d| ≤ 400) at the screening estimate, straddling the estimate within ±200
  where the pool permits, including the widest available low/high discriminators. The exact
  keys and the documented §2-span interpretation are committed in `benches/gate-plan.json`
  (machine plan consumed by rating-gate.yml) in the same commit that dispatches Batch A,
  BEFORE any batch game runs. If the rule cannot be satisfied by the frozen pool at the
  screening estimate, the tension is documented and the nearest compliant set is chosen and
  justified — never tuned to the outcome.
- **Expected evidence:** `benches/evidence/batchA/<anchor>/` and `.../batchB/<anchor>/`
  (committed raw per-game results + manifests), then the fail-closed gate:
  `scripts/verify_evidence.py` + `scripts/rating_estimator.py gate`.

### BATCH results (filled after execution)

- status: PENDING EXECUTION (anchor set pending SCREENING-1/2)

### PILOT-1 / PILOT-dup results (filled 2026-11-15 after evidence recovery)

- status: COMPLETE (both pilot collections recovered via evidence-bridge rev 3, run
  43683839993, commit 2ec762e; independently re-aggregated from original shard artifacts —
  byte-identical merged_sha256 aeb4d5a0… / a811d9d1…).
- throughput: PILOT-1 29.43 min/game (4/4 games, per-record wall_seconds 1776.7/1755.0/1776.8/
  1755.4); duplicate pilot 29.53 min/game (4/4). 8-game batch shard ≈ 236 min < 330-min job cap.
- engine hash freeze verified on runners (fd75726d…, two independent builds byte-identical).
- Both pilot collections remain EXPLORATORY ONLY (pipeline measurement; excluded from gate).

### CTRL-1 / CTRL-2 results (filled 2026-11-15 after evaluation)

- CTRL-1 anchor-vs-anchor: **PASS.** 240/240 counted, 0 engine errors. Measured
  topple-0.1.1 − topple-0.2.1 = −125.32 vs published −115.00 → error −10.32, |err| ≤ 75 ✓
  (estimator seed 20261115). Evidence: benches/evidence/control/topple-0.1.1-vs-topple-0.2.1/.
- CTRL-2 self-match: **PASS** (see FAILURE_LEDGER 2026-11-15 metric-defect entry). Seat-
  perspective score 0.5146, 95% CI [0.4792, 0.5500] → 0.5 inside ✓ (estimator seed 20261116).
  White-perspective 0.6604 recorded as the color advantage. Evidence:
  benches/evidence/control/flawless-self/.

### SCREENING-1 / SCREENING-2 results (filled 2026-11-15 after evaluation)

- status: COMPLETE (120/120 counted each, recovered from original shard artifacts; byte-
  identical to the in-run aggregate mirrors 147cec4f… / 9e26b8cd…).
- SCREENING-1 (vs topple-0.1.1, 2324±17): score 0.0208 → d̂ = −668.8 → abs estimate 1655.2
  (cluster-bootstrap 95% score CI [0.004, 0.046]).
- SCREENING-2 (vs topple-0.2.1, 2439±14): score 0.0083 → d̂ = −830.2 → abs estimate 1608.8.
- Screening estimate (registered rule, mean of R_a + d̂_a): **est ≈ 1632 Elo**.
- Selection rule outcome: at est ≈ 1632 the only non-saturating pool anchor is wowl-1.3.7
  (expected |d| = 217 ≤ 400); every other anchor (2324+) is saturating (|expected d| ≥ 692).
  The ≥3-anchor gate requirement is UNSATISFIABLE at the frozen pool — the registered
  anchor-set rule produces no compliant set. Per the registered escape clause the tension is
  documented (not silently tuned); per mission §8 the batch dispatch is DEFERRED and the
  engine-improvement cycle is registered below. NOTE: the screening root-cause analysis found
  ~95% of Flawless losses are flag falls (time forfeits) from a clock-management defect —
  the 1632 figure measures the DEFECTIVE candidate, not the engine's search/eval strength.
- Screening data remain SELECTION-ONLY, never gate evidence.

## ENGINE-1 — time-management remediation (registered 2026-11-15, BEFORE any new game)

- **Purpose:** improvement cycle step 1 (mission §8). Hypothesis: the flag-fall defect in
  `clock_limits` (soft clamp 20–30_000 ms causing late-period overspend; hard = 6×soft
  permitting near-zero-reserve single-move spends) causes ~95% time forfeits at 40/15;
  fixing it converts forfeits into real chess results.
- **Change (frozen before implementation):** replace the budget with a reserve-bearing
  formula — reserve = clamp(t/16, 300 ms, 8 s); soft = max(20 ms, (t − reserve)/mtg) with NO
  upper clamp; hard = min(4×soft, (t − reserve)/2, t − max(300 ms, reserve/2)); keep the
  never-exceed-remaining invariant. Rationale: full-period utilization is correct for
  repeating 'add' schedules, but with a safety reserve that absorbs per-move overhead and
  bounded hard limits that cannot consume the whole remaining clock.
- **Acceptance (fixed now):** (1) new clock-allocation regression tests pass (period-plan
  sums stay ≤ t; no single move can spend more than half the usable clock; reserve always
  positive); (2) all existing suites stay green (cargo 34+, test_match 104, estimator suite);
  (3) bench signature change recorded; (4) hosted SCREEN-2 (below) shows flag rate ≈ 0
  (registered: ≤ 10 flag ends out of 120 games per screening); (5) no regression in the
  SF19-lite skill-5 A/B probe band (relative statistic, in-sandbox only).
- **Expected measurable effect:** screening score vs topple-0.1.1 rises from 0.0208 to
  ≥ 0.10 (est ≥ ~1920); if the engine's true 40/15 strength is ≥ ~2000, ≥3 non-saturating
  anchors become selectable and Batch A/B proceed with the new frozen hash. If the new
  screening estimate still yields no compliant ≥3-anchor set, the improvement cycle
  continues (mission §8) — the threshold and selection rule remain frozen.

## SCREEN-2 — re-screening of the ENGINE-1 candidate (registered 2026-11-15, before dispatch)

- **Purpose:** exploratory screening (selection-only, never gate evidence) of the
  time-management-fixed candidate, identical methodology to SCREENING-1/2.
- **Methodology:** Flawless (engine_sha256 "freeze" — first runner build records the new
  hash, pinned in PREREGISTRATION before any confirmatory dispatch) vs topple-0.1.1 AND
  topple-0.2.1; 60 openings (batch-A suite, suite hash 2c4a54d8…) × 1 paired rep × AB/BA =
  120 games each (15 shards × 8); TC 40/15; seeds 20261123 (vs 0.1.1) / 20261124 (vs 0.2.1);
  marker-file dispatches with distinct revisions; fresh evidence dirs
  benches/evidence/screening-2/<anchor>/.
- **Analysis (pre-defined):** identical to SCREENING-1/2 (d̂ per anchor; est = mean(R_a + d̂_a);
  selection-only uncertainty); then re-apply the UNCHANGED anchor-set selection rule.
- **Expected evidence:** benches/evidence/screening-2/topple-0.1.1/ and …/topple-0.2.1/.

## CTRL-2-R — self-match null control re-run for the ENGINE-1 candidate (registered 2026-11-15, before dispatch)

- **Purpose:** mission §8.16 — the candidate changed (ENGINE-1 clock budget), so the old
  CTRL-2 evidence (binary fd75726d…) no longer covers the candidate's clock interaction with
  the harness. CTRL-1 (anchor-vs-anchor) does not seat the candidate and its PASS stands.
- **Methodology:** identical binary both sides at the PINNED SCREEN-2 hash (freeze recorded
  by SCREEN-2 runners, pinned in PREREGISTRATION before this dispatch); 60 openings (batch-A
  suite, 2c4a54d8…) × 2 paired reps × AB/BA = **240 games**; 120 shards × 2; TC 40/15;
  dispatch seed 20261125; purpose control, batch CTRL, label flawless-self-r; evidence dir
  benches/evidence/control/flawless-self-r/.
- **Acceptance criterion (fixed, unchanged):** seat-perspective score 0.5 within its 95%
  opening-cluster bootstrap CI (the registered CTRL-2 definition with the color_pair metric
  fix; estimator seed 20261125). White-perspective score is recorded for transparency.
- **Timing:** runs BEFORE any confirmatory gate evaluation (the gate consumes both controls
  at their registered paths; gate-plan.json will point the self-match control at the
  CTRL-2-R evidence for the ENGINE-1 candidate).
- **Expected evidence:** artifacts rating-control-CTRL-flawless-self-r-shard*-<run_id> +
  manifests; strict aggregation identical to CTRL-2.

### ENGINE-1 acceptance record (updated 2026-11-15 after local verification)

- (1) clock regression test: PASS (cargo 35/35 incl. `clock_limits_engine1_no_flag_death_march`).
- (2) suites: cargo 35/35, fmt clean, clippy -D warnings clean, test_match 104/104,
      test_rating_estimator 65/65.
- (3) bench signature UNCHANGED fc907eba40b7869f (search/eval byte-identical; the fix touches
      time allocation only).
- (4) SCREEN-2 flag rate ≤ 10/120 per screening: PENDING (runs 43685671431 + 43686056730).
- (5) SF19-lite skill-5 probe: probe-006 (probe-005 methodology, 80 games = 2× repetitions,
      movetime 100 ms, skill_black 5, hash 16, batch PROBE): flawless 44.5/80 = 0.556,
      opening-clustered 95% CI [0.469, 0.644], logistic +39 vs this setting — inside the
      probe-005 band (0.600, CI [0.463, 0.725], +70 [−26, +168]; overlapping CIs). 0 engine
      errors. Raw evidence committed: benches/probe-006-engine1-validation/. Local build hash
      a3325011… (sandbox build; the RUNNER build hash is the one pinned for batches).

## ANCHOR-2 — anchor pool expansion for the >3,000 Elo phase (registered 2026-11-15, before any verification build or game)

- **Purpose:** mission §2 (anchor coverage) — the frozen 6-anchor pool (1849–2474) CANNOT
  calibrate ratings above ~2,600; the 3,000 milestone requires independently rated anchors
  bracketing and exceeding 3,000. This registration PRE-COMMITS the expansion procedure; the
  2,000 gate proceeds UNCHANGED on the frozen pool.
- **Rating source (provenance):** CCRL 40/15 list, computed 2026-11-13 (Bayeselo, ponder off,
  3-4-5 EGTB, i7-4770K equivalence — same reference machine as pool calibration k=1.0291);
  fetched by anchor-research workflow run 43587593393 (artifact `ccrl-4015-fetch-43587593393`,
  SHA256SUMS.txt inside, 200 OK on the runner); parsed locally (1,480 single-CPU rows with
  ≥1 game; 4CPU rows excluded — our engines are single-threaded; error convention ci95 per
  the verified list text).
- **Candidate ladder to verify (single-CPU published ratings; repos verified reachable with
  the listed SPDX license AT HEAD — license AT THE EXACT TAG is checked during verification,
  fail-closed):**
  | candidate | repo | tag to verify | CCRL 40/15 single-CPU | license (HEAD) |
  |---|---|---|---|---|
  | Leorik 2.5 | lithander/Leorik | release for v2.5 | 2922±18 (g=684) | MIT |
  | Berserk 3.2.1 | jhonnold/berserk | v3.2.1 | 2958±20 (g=504) | GPL-3.0 |
  | Seer 1.2.1 | connormcmonigle/seer-nnue | v1.2.1 | 3088±18 (g=659) | GPL-3.0 |
  | Stockfish 5 | official-stockfish/Stockfish | sf_5 | 3238±10 (g=1936) | GPL (verify at tag; historically GPL-2.0) |
  | Stockfish 6 | official-stockfish/Stockfish | sf_6 | 3280±10 (g=2272) | GPL (verify at tag) |
  | Stockfish 7 | official-stockfish/Stockfish | sf_7 | 3302±9 (g=2692) | GPL (verify at tag) |
  | Stockfish 8 | official-stockfish/Stockfish | sf_8 | 3358±7 (g=3886) | GPL (verify at tag) |
  | Leorik 3.1 | lithander/Leorik | release for v3.1 | 3367±11 (g=1670) | MIT |
  | (reserve rungs) Berserk 4.7.0 3445±17; Seer 2.x; SF 9 3422±9; SF 10 3443±7; SF 11 3494±11; Caissa 1.24 3593±9 (MIT, Witek902/Caissa) |
  Mid-band (2,475–2,920) additions are required later for interpolation (Berserk 1.x/2.x,
  Leorik 2.3/2.4, Igel/Halogen/Viridithas older versions) — registered as ANCHOR-2b when the
  candidate's level makes them decisive; NOT needed for the 2,000 gate.
- **Verification procedure (identical discipline to the frozen pool):** rebuild from SOURCE at
  the exact tag on the hosted runner (anchor-verify.yml pattern: matrix build + UCI
  identity-string check + SHA-256 recording + LICENSE-at-revision check + verify-flawless
  control; fail closed on any mismatch); record runner binary SHA-256 + toolchain + image in
  the new pool file `benches/anchor-pool-3000.json`; NO source patches (Raven-style hardened-
  build accommodations documented if ever needed, with ASAN evidence).
- **Usage rule (pre-committed):** the 3,000-phase gate plan (gate-plan v2) will select anchors
  by the SAME registered selection rule applied to the expanded pool; the plan, the pool file,
  and any protocol amendment are committed BEFORE any 3,000-phase confirmatory games; the
  2,000 gate (gate-plan v1, frozen pool) is untouched. UCI id-string mapping quirks (tag vs
  printed id) documented per engine, as done for Topple 0.1.1.
- **No games are played under this registration; it registers verification + expansion work
  only.** Every verification failure (unverifiable license, id mismatch, build failure) is
  recorded with the exclusion reason in the pool file, mirroring the frozen-pool discipline.

### ANCHOR-2 execution notes 1 (2026-11-15 — tag availability verified, rungs adjusted)

- Stockfish 8: tag `sf_8`, **COPYING at tag = GPL-3.0**, local build smoke SUCCESS (g++,
  ARCH=x86-64, bench 5.9M nodes @ 2.42M nps, UCI id "Stockfish 8 64 by T. Romstad, …"
  matching the CCRL row). Hosted verification still required.
- Berserk 3.2.1: NO tag/release exists (tags start 8.5.1, releases start 4.3.0) → EXCLUDED
  under the fail-closed source-identity rule; substituted by Seer/akimbo/Weiss rungs below.
- Seer 1.2.1: repo tags start `v2.1.0`; only CCRL row = 1.2.1 (3088±18) → EXCLUDED unless a
  verifiable source revision is found; lower priority given alternatives.
- SUBSTITUTED RUNGS (3,000-straddle band, all with known repos): **akimbo 0.5.0 (3026,
  amanjpro/akimbo — same repo as the frozen-pool akimbo 0.1.1, existing verification flow,
  tags to be checked at execution)**; **Weiss 1.2 (3017, version↔rating map already extracted
  by anchor-research run 43587593326-series)**; Leorik 2.5 (2922, release tags 2.4/2.5/3.1
  verified present); SF 5 (3238, tag sf_5); SF 8 (3358, tag sf_8, smoke-verified).
- Revised ANCHOR-2 ladder (order of hosted verification): akimbo 0.5.0 → Weiss 1.2 →
  Leorik 2.5 → SF 5 → SF 8 (reserves: SF 9/10/11, Caissa 1.24, Berserk 4.7.0).

### ANCHOR-2 verification result (2026-11-15 — COMPLETE for the registered ladder)

- **Hosted verification run 43693679899 (SUCCESS, head 932ae99): ALL 11 legs green** —
  6 frozen-pool anchors (re-verified) + 5 ANCHOR-2 rungs: leorik-2.5 (bin 84e1d60d…),
  akimbo-0.5.0 (eee14678…), weiss-1.2 (fb9e0434…), stockfish-5 (3cb291f2…),
  stockfish-8 (6ec5eda2…) — each with exact UCI identity match, license-at-tag verified,
  source + binary SHA-256 recorded, artifacts `anchor-<key>-43693679899`.
- **Expansion pool frozen: benches/anchor-pool-3000.json** (schema mirrors the frozen pool;
  5 engines spanning 2922–3358, 8,762 CCRL games total; exclusions berserk-3.2.1 / seer-1.2.1
  documented with reasons). Consumed only by the preregistered gate-plan v2 for the 3,000
  phase — the 2,000 gate uses the frozen pool unchanged.
- Reserves for later rungs (registered in execution notes 1): weiss-1.3/1.4, sf_9/10/11,
  caissa-1.24, berserk-4.7.0 — added to the same matrix when the candidate's level makes
  them decisive.

## SCREEN-3 — conditional third screening to complete the ≥3-anchor selection set (registered 2026-11-15, BEFORE any SCREEN-2 result is observed)

- **Purpose:** the frozen anchor-set rule requires ≥3 non-saturating screened anchors;
  SCREEN-2 screens exactly two (topple-0.1.1, topple-0.2.1). If the SCREEN-2 estimate makes
  ≥3 frozen-pool anchors non-saturating (|est − R_a| ≤ 400), a third screening is required
  before gate-plan.json; if it does not, SCREEN-3 is NOT dispatched and the improvement
  cycle continues (registration is a plan, not an obligation to run).
- **Anchor choice (mechanical, rule-derived):** among non-saturating pool anchors NOT yet
  screened in SCREEN-2, pick the one minimizing |est − R_a|; deterministic tie-break =
  higher published_elo. No human discretion.
- **Methodology:** identical to SCREEN-2 (120 games = 60 openings × 1 paired rep × AB/BA,
  batch-A suite 2c4a54d8…, 15 shards × 8, TC 40/15, marker-file dispatch revision = next
  sequential, purpose "screening", white flawless at the PINNED SCREEN-2 hash, seed
  20261126, fresh evidence dir benches/evidence/screening-3/<anchor>/).
- **Analysis:** identical (d̂_a; per-anchor estimate R_a + d̂_a; selection-only uncertainty);
  then make_gate_plan.py --anchors <all screened anchors> applies the UNCHANGED rule to
  produce the gate plan. Screening remains selection-only, never gate evidence.

## GATE-PLAN-V2 — protocol amendment for the >3,000 phase (registered 2026-11-15; implementation deferred until the >2,000 gate is resolved)

- **Purpose:** enable confirmatory evidence against `benches/anchor-pool-3000.json` without
  weakening anything used by the >2,000 gates.
- **Amendment content (to be implemented + tested BEFORE any 3,000-phase dispatch):**
  1. `benches/dispatch.json` gains an OPTIONAL `pool_file` field (default
     `benches/anchor-pool.json`, exactly the current behavior). When set to
     `benches/anchor-pool-3000.json`, the resolver validates anchor slots against the
     pool-3000 keys and `rating_estimator.py`/`make_gate_plan.py` consume the same pool.
  2. `purpose` remains `confirmatory`; the gate workflow requires the plan file
     (`benches/gate-plan-3000.json`) produced by the UNCHANGED registered selection rule
     applied to the expanded pool (make_gate_plan.py --pool benches/anchor-pool-3000.json).
  3. Controls: both null controls re-run at the candidate hash with pool-3000 anchors
     (CTRL-1R: anchor-vs-anchor pair from pool-3000; CTRL-2R: self-match) — fail-closed
     thresholds identical to the registered CTRL values.
- **Estimator/statistics:** UNCHANGED (same estimator, same opening-cluster bootstrap, same
  three unrounded CI lower bounds, same ≥2,000-games-per-anchor-per-batch floor — target
  3,000 instead of 2,000).
- **No affected evidence is collected until this amendment is implemented, tested, and the
  gate-plan-3000.json is committed.** The >2,000 pipeline never reads pool-3000.

## SCREEN-2 partial evidence & SHAPE-1 execution-shape amendment (recorded 2026-11-15, after the timeout, BEFORE the SCREEN-2R re-dispatch)

- **What happened:** both SCREEN-2 runs (43685671431, 43686056730; 15 shards × 8 sequential
  games each) were killed by the workflow's own `timeout-minutes: 330` at 11:59:43Z/12:05Z
  (shards started 06:29:43Z). All 30 shard jobs cancelled; evidence jobs skipped; 15
  artifacts per run recovered. This is a WORKFLOW-SHAPE failure, not an engine defect:
  the shards played correctly until the kill.
- **Root cause (measured):** the shard shape was sized from PILOT-1's 29.43 min/game mean
  (4 games, OLD candidate whose flagged games ended early). The ENGINE-1 clock fix makes
  games use their full clock budget. Empirical duration over the 173 hash-verified counted
  games recovered from the cancelled runs: mean 52.0, median 50, p95 82.8, p99 125.9,
  max 147.5 minutes. 8 × mean ≈ 416 min + build ≫ 330 → guaranteed timeout. SHAPE failure
  predicted in registration ("longer games"), magnitude under-estimated.
- **Partial evidence status (fail-closed):** 87 counted games per run (174 total), identities
  verified per shard (engine binary byte-identical across all 30 runner builds, anchor
  binaries match the frozen pool, suite hash matches, schedule ranges contiguous, 0 engine
  errors, 1 flag end total). These games are VALID per-game records but do NOT constitute
  the registered 120-game screenings (incomplete schedule ⇒ strict aggregation fails). They
  are exploratory/selection-support evidence only; the official SCREEN-2 measurement is the
  full re-run below. No partial aggregation is used for any acceptance decision.
- **Runner engine hash (PINNED NOW, provenance recorded):** the ENGINE-1 candidate binary
  built by all 30 independent hosted-runner builds across both runs:
  `9663697da62e33229d516af3681c442e268287c59d6b97ff2cd13256b564d428`
  (byte-identical across every shard manifest in both runs; recorded in
  `white_artifact.sha256`). This is the pinned hash for ALL confirmatory dispatches
  (CTRL-2-R, Batch A/B). SCREEN-2R re-verifies it fail-closed (aggregation compares each
  shard's recorded hash against this pin).
- **SHAPE-1 rule (applies to every future dispatch of this mission):**
  1. `rating-run.yml` shard job timeout: 330 → **350 minutes** (hosted max 360).
  2. Games per shard job: **2** (worst observed shard 2 × 147.5 + ~15 build = 310 < 350;
     empirical p99 shard 2 × 125.9 + 15 = 267).
  3. Screening shape: shard_count **60** (120 games = 60 × 2), matrix 60 jobs.
  4. Batch shape: **1020 shard_count per anchor per batch** (2040 games = 1020 × 2),
     dispatched as **4 sequential runs of 255 shard-indices each** (GitHub matrix cap 256);
     same registered openings/suite/seeds/TC; ≥2,000 counted games per anchor per batch
     unchanged.
  5. CTRL-2-R: 240 games = **120 shards × 2**, one run.
  6. Tail risk accepted and documented: a single game longer than ~165 min times out its
     job; that run then fails closed; recovery = GitHub "re-run failed jobs" (successful
     shards' artifacts persist and are reused). No acceptance criterion changes.
  7. Seeds, suites, repetitions, TC, anchor identities, engine hash: **UNCHANGED**. The
     schedule (schedule_sha256 87ee566f…) is seed-derived and shard-count-independent —
     shard_count only changes how the SAME 120/2040-game schedule is sliced (verified at
     match.py:799-800: lo = i*n // count, hi = (i+1)*n // count).
- **SCREEN-2R (re-dispatch, registered here BEFORE execution):** identical to SCREEN-2
  except shard_count 60 (2 games/shard) and marker revisions 11 (vs topple-0.1.1, seed
  20261123) and 12 (vs topple-0.2.1, seed 20261124). Fresh evidence dirs; the in-run
  evidence job aggregates strictly (all 60 shards × 2 games = 120 counted games required).
  Acceptance unchanged: flag rate ≤ 10/120 per screening; hash must equal the pin.

## SHAPE-1 addendum — batch evidence aggregation across the 4 runs (registered 2026-11-15, before any batch dispatch)

- **Problem:** a confirmatory batch (2,040 games/anchor) is 4 rating-run instances of 255
  shards each (SHAPE-1). The evidence job previously wrote one dir per (purpose, anchor);
  run 2 would have overwritten run 1's committed evidence.
- **Design (fail-closed):**
  1. For purpose=confirmatory only, the evidence job now writes per-run dirs
     `benches/evidence/confirmatory/<anchor>/run-<run_id>/` (each strictly aggregating its
     own 255 shards → 510 games, 60 openings × 17 reps × AB/BA slice, identities checked).
  2. The canonical batch dir `benches/evidence/batchA/<anchor>/` (the layout
     verify_evidence.py/rating_estimator.py consume) is produced EXACTLY ONCE by
     `scripts/merge_batch_runs.py` after the batch's 4th run completes. Checks: per-run
     manifest merged_sha256 matches games.jsonl bytes; identical identities across runs
     (engine/anchor/suite hashes, tc, seed, schedule_sha256); counted schedule_index must
     cover 0..2039 exactly once (no gaps/dupes); uncounted replays must reference a counted
     index and are excluded. Self-tested: 1 happy path + 4 fail-closed cases all pass
     (scripts/test_merge_batch_runs.py).
  3. Single-run purposes (screening/screening-2/control) keep the existing layout
     (benches/evidence/<purpose>/<anchor>/); unchanged behavior.
- **No acceptance criterion changes.** The gate recomputes from the canonical dir only.

### SHAPE-1 clarification (recorded 2026-11-15, verified from live SCREEN-2R shards)

- `schedule_sha256` in each shard manifest is computed over the SHARD'S OWN scheduled-game
  slice (match.py:450/861), not the global 120-game list — so it legitimately differs
  between shard shapes (SCREEN-2 attempt 1: 87ee566f… for the 8-game slice; SCREEN-2R:
  shard-scoped values). The identity guarantee that matters was verified EMPIRICALLY:
  the games at global schedule_index 114/115 in SCREEN-2R shard 57 are field-identical
  (opening, seats, color_pair, repetition) to the same global indices played in the
  cancelled SCREEN-2 run — the global 120-game schedule is seed-derived and
  shard-count-independent, as registered. Strict aggregation binds the schedule via
  schedule_index coverage + per-shard lo/hi ranges, not via this hash.

### SCREEN-3 execution-shape note (recorded 2026-11-16, before dispatch)

- The SCREEN-3 registration (above) predates the hosted-timeout discovery. Per the
  SHAPE-1 amendment and FAILURE_LEDGER lessons (8-game shards cannot fit any hosted
  timeout; shard size must come from MEASURED durations), SCREEN-3 executes with the
  SHAPE-1 shape: **60 shards × 2 games** (same 120-game sampling: 60 openings × 1 paired
  rep × AB/BA, batch-A suite, seed 20261126, TC 40/15, pinned ENGINE-1 hash, purpose
  "screening-3", evidence dir benches/evidence/screening-3/<anchor>/). The registered
  SAMPLING and seed are unchanged; only the job slicing changes. Anchor choice remains
  mechanical (min |est − R_a| among unscreened non-saturating anchors; tie = higher
  published_elo).

## BATCH-HASH — engine-hash binding for BATCH-A / BATCH-B (registered 2026-11-16, BEFORE any batch dispatch)

- **Scope (append-only amendment):** supersedes ONLY the `engine_sha256` field of BATCH-A / BATCH-B (registered 2026-11-14, "Engine: Flawless, engine_sha256 fd75726d…"). That value was pinned for the pre-ENGINE-1 candidate. ENGINE-1 (registered 2026-11-15) states that Batch A/B "proceed with the new frozen hash".
- **Batch engine (registered now):** Flawless, engine_sha256 `9663697da62e33229d516af3681c442e268287c59d6b97ff2cd13256b564d428`, the ENGINE-1 candidate hash pinned in the SCREEN-2 partial-evidence / SHAPE-1 amendment and used by SCREEN-3 (dispatch rev 14) and CTRL-2-R (dispatch rev 13).
- **Unchanged:** suite files and their SHA-256 values, bootstrap seeds (20261121 / 20261122), sample design (60 openings × 17 paired reps × AB/BA = 2,040 games per eligible anchor per batch), TC 40/15, anchor-set rule, thresholds, and SHAPE-1 sharding.
- **Not retroactive:** no batch dispatch appears in the `benches/dispatch.json` history (verified 2026-11-16 with `git log`). No executed evidence is altered. CTRL-1, CTRL-2 and SCREEN-1/2 results under fd75726d… remain historical and are not gate evidence for the ENGINE-1 candidate.
- **Consequence if not registered:** rating-run shards run in strict hash mode and fail on any mismatch, so this binding must be pushed BEFORE the gate-plan commit that dispatches Batch A.


## RATING-100 — reduced confirmatory sample design (registered 2026-11-16; append-only)

- **Scope:** this amendment supersedes ONLY the historical sample-size / shard-count requirements in BATCH-A and BATCH-B (registered 2026-11-14) for any future new confirmatory execution. It does not rewrite or invalidate those registrations, SCREEN-2/SCREEN-2R/SCREEN-3 evidence, CTRL-1/CTRL-2/CTRL-2-R evidence, prior manifests, or prior results. The original 2,040-game registration remains part of the historical record.
- **New target sample:** exactly **100 counted games per eligible anchor per batch**, formed from **50 distinct opening clusters × 1 paired repetition × AB/BA exact color reversal**. A game is counted only under the existing match harness rules: engine-error attempts remain uncounted and are replayed under the registered replay policy; unadjudicated/move-cap records remain uncounted. Attempts/replays do not inflate the 100 counted-game target.
- **Two independent batches:** Batch A uses benches/rating-openings-100-batchA.txt; Batch B uses benches/rating-openings-100-batchB.txt. Each contains 50 openings. The suites are disjoint and the same mechanically selected eligible anchor set must be used in both batches. The actual suite files, selected lines, selector, and byte-level SHA-256 values are committed before any dispatch.
- **Deterministic suite selector:** for each original suite line normalized with strip(), compute SHA-256 over FlawLessChess|rating-100|amendment-2026-11-16|sha256-v1|<batch>|<normalized line>. Select the 50 lines with the lowest digests, then retain their original suite order. scripts/verify_opening_subsets.py recomputes the selector, exact line order, SHA-256 values, and cross-batch disjointness.
- **Schedule / dispatch shape:** the existing opening-major schedule emits AB then BA consecutively. Therefore the 100 schedule entries are divided into 50 contiguous two-game shards; each shard contains both color reversals for one opening. One matrix wave is 50 jobs (below the GitHub 256-job matrix limit). Partial retries use separate immutable run evidence; the canonical merge is produced only when counted schedule indices 0–99 occur exactly once.
- **Preserved methodology:** 40/15 repeating wall-clock control; frozen engine and anchor binary identities and SHA-256 verification; FIDE termination/adjudication and replay rules; opening-cluster bootstrap; joint resampling across anchors; GLS covariance; published calibration uncertainty; shared calibration uncertainty between batches; both null controls and their registered thresholds; same mechanically selected anchor set. The gate still requires the two-sided 95% calibrated CI lower bounds for Batch A, Batch B, and the combined estimate each to be **strictly greater than 2,000 Elo, unrounded**. No threshold or CI weakening is authorized.
- **Arithmetic:** original 3-anchor campaign = 3 × 2 × 2,040 = 12,240 counted games. RATING-100 = 3 × 2 × 100 = 600 counted games. Reduction = 11,640 games (95.0980%). The reduction is sample-size-only; it does not change 40/15 or the decision rule.
- **Prospective power decision (recomputed 2026-11-17; amendment registered 2026-11-16): BLOCKED.** benches/rating-100-power-assessment.json records a delta-method multivariate-normal sensitivity analysis with 50 clusters, observed covariance for the first two anchors on the actual selected Batch-A subset, three third-anchor correlation assumptions (0/0.25/0.5), cluster-SD inflation (1/1.5/2), published anchor calibration SDs, independent A/B match noise, and a shared cross-batch calibration draw. At a true 2,100 Elo alternative, the estimated probability that all three lower bounds pass is only about 63–77% with no variance inflation, and about 9–23% under 1.5–2× cluster-SD stress (depending on third-anchor correlation). The full third-anchor cluster distribution and new disjoint Batch-B cluster distribution are unavailable, so those assumptions are unverified. This approximation is sensitivity analysis, not the final registered bootstrap.
- **Dispatch restriction:** the present assessment is explicitly not a PASS. scripts/make_batch_dispatch.py and rating-run.yml fail closed unless status == PASS and eligible_for_confirmatory_dispatch == true in the committed assessment. Therefore no RATING-100 confirmatory dispatch is authorized by this amendment yet. Do not dispatch it as confirmatory while BLOCKED. An explicitly exploratory run would require a separately labelled screening purpose and must never enter the gate.
- **Historical evidence:** no old games are resampled, dropped, relabelled, or reused as confirmation. SCREEN-2R and SCREEN-3 remain selection-only. Existing controls remain valid only for the exact candidate identities they registered and verified.

### RATING-100 recovery clarification — 2026-11-17

A recovered matrix shard can contain only the missing member(s) of its original AB/BA schedule pair. The canonical schedule identity remains the original 0–99 schedule; recovery does not renumber the requested indices or create a new statistical sample. Per-run manifests preserve each selected index, and canonical merge rejects every duplicate counted index or wrong opening/color-pair mapping. The 100-game design remains BLOCKED pending a reviewed PASS power assessment; this clarification does not authorize dispatch.

### RATING-100 evidence-state clarification — 2026-11-17

The 100-game amendment is currently **BLOCKED** for confirmatory dispatch. The sensitivity analysis uses the actual selected Batch-A 50-opening subset for the two available screening anchors; it does not have complete cluster data for the third anchor or disjoint Batch B. The report remains `status=BLOCKED` and `eligible_for_confirmatory_dispatch=false`. Do not change these fields or dispatch the design as confirmatory without a reviewed, evidence-backed prospective power PASS.

### ENGINE-2 — SEE ordering candidate validation record (2026-11-17; no games authorized)

- **Scope:** candidate search change uses material-only SEE for capture ordering; SEE is ordering-only and is not used to prune quiescence captures. The previous ENGINE-1 benchmark signature `fc907eba40b7869f` is historical and is no longer the expected signature for this source candidate.
- **Preliminary hosted measurement:** fixed-depth-10 benchmark signature `141943aa23b3fc68` on the first Ubuntu verification build. This is a deterministic source/build fingerprint only. It is not an Elo, tactical-strength, or NPS improvement claim.
- **Binary identity:** NOT YET FROZEN. The first verification job stopped after the signature comparison and did not emit its SHA-256 manifest. A successful exact-head anchor-verification run must publish the binary SHA-256 before this candidate is eligible for any future engine-specific preregistration.
- **Validation:** Rust 1.80 MSRV passed on the initial implementation; Linux/Windows CI stopped at rustfmt before tests. Those formatting-only diffs were corrected in the follow-up. No rating games, screening games or controls were dispatched for ENGINE-2.
- **Dispatch restriction:** ENGINE-2 is not covered by the previous ENGINE-1 CTRL-2-R / SCREEN-3 evidence or BATCH-HASH binding. No RATING-100 or legacy confirmatory dispatch may use ENGINE-2 until the binary hash, candidate-specific controls and screening evidence are separately preregistered and the power assessment is reviewed PASS. RATING-100 remains BLOCKED.


### RATING-100 selector-integrity correction — 2026-11-17 (append-only)

The first hosted verifier run (CI run 44062359630, Linux + Windows) correctly rejected the two reduced suites: their initial selector generation used an incorrect local SHA-256 helper. No confirmatory job was dispatched and no rating evidence was produced. The faulty suite bytes are superseded by the two files in this commit; the original 60-opening suites and all historical records remain unchanged.

The corrected selector is now recomputed with standard-library `hashlib.sha256` exactly as implemented by `scripts/verify_opening_subsets.py`: normalize each original non-comment line with Python `strip()`, hash the UTF-8 bytes of `FlawLessChess|rating-100|amendment-2026-11-16|sha256-v1|<batch>|<line>`, choose the 50 lexicographically lowest lowercase hexadecimal digests, and emit the chosen lines in their original suite order. The verifier independently checks selected line identity, order, byte-level suite SHA-256 and disjointness.

- Corrected Batch A SHA-256: `5abdcdbddec0f22d7e6eff8974ee402363c8c3df318b8110d7204adf69f5c1df`.
- Corrected Batch B SHA-256: `ccb4901742eca25b0b10f1a3c9fdfc17b2967a1939c2d7e466c2c5495b6d4253`.
- Both suites contain exactly 50 unique opening labels; their intersection is empty. The CI verifier is mandatory before any dispatch-marker tooling can be used.
- The pre-registered 100-game design remains BLOCKED for confirmatory dispatch. Fixing selector integrity does not change the power assessment, sample-size rule, time control, anchors, confidence-bound threshold or null controls.


### ENGINE-2 binary identity capture — 2026-11-17 (append-only)

The previously recorded ENGINE-2 entry's "NOT YET FROZEN" statement was accurate when written. The exact candidate tree is now identified and its hosted binary hash has been measured:

- Source branch commit: 5b63e273d77cfb097f0ad73bc28dda05cc19adad.
- Source tree: 75bc5633e1466d5abf1f4c7d5999bc4a3915e193.
- Anchor verification run: 44066217113, all 13 jobs successful. Its verify-flawless job built merge commit 7434e948357eda05f9435e430c37da082f202741 (parents: base main 98b1a002… and the exact source branch commit above). GitHub compare reports no changed files between that merge commit and the source branch commit; both have the same tree SHA.
- Binary SHA-256: 168dc0ab22749f8dc7a6be5248cd7426f9f2bfd3fda8077bc6218959ad6e41d7.
- Fixed-depth-10 bench signature: 141943aa23b3fc68.

This freezes the binary identity for the ENGINE-2 source tree only. It is not an Elo estimate, playing-strength gain, NPS improvement, or authorization to run games. No ENGINE-2 screening or candidate-specific control has been run. ENGINE-1's CTRL-2-R / SCREEN-3 evidence does not transfer to ENGINE-2.

The RATING-100 power assessment remains ENGINE-1-specific. Its screening inputs are SCREEN-2 manifests with engine SHA-256 9663697da62e33229d516af3681c442e268287c59d6b97ff2cd13256b564d428. New guards in power_analysis.py, make_batch_dispatch.py, and rating-run.yml require that exact power-report engine SHA to equal the proposed dispatch binary. A report computed from ENGINE-1 cannot authorize ENGINE-2. A fresh ENGINE-2 assessment must use its own preregistered screening evidence and still satisfy the prospective power requirement before any confirmatory dispatch.

## CLOCK-1 — per-move floor amendment to ENGINE-1 (registered 2026-11-21, after owner decision; no game authorized by this entry)

- **Owner decision:** on 2026-11-21 the owner chose "Amend ENGINE-1 and fix" for defect F-32 (FAILURE_LEDGER F-32), with the trade-off stated in the question below. The owner was told that this changes a frozen formula and invalidates the ENGINE-1 hash evidence (see Consequences).
- **Trigger (measured, not inferred):** sudden-death games, zero increment, no `movestogo`, 200-ply cap, 3 games per base, `scripts/selfplay_clock_probe.py`, on the build whose `src/` is identical to commit a938e45 (the ENGINE-1-era source):
  - base 300 ms: 3 of 3 games flagged (plies 32, 33, 34);
  - base 1000 ms: 2 of 3 flagged (plies 101, 114);
  - base 2000 ms: 1 of 3 flagged (ply 187);
  - base 5000 ms: 0 of 3.
  Cause: the fixed 20 ms soft floor in `clock_limits` exceeds the per-move share `(t − reserve)/mtg` for every clock under about 1.1 s, so each move spent 20 ms until the reserve was gone.
- **Change (the only formula change):** the soft floor `20 ms` becomes `clamp(t / (4·movestogo), 1 ms, 20 ms)`, so `soft = max(floor, (t − reserve)/mtg + inc/2, capped at usable)`, then `min(t)`. Unchanged: the reserve `clamp(t/16, 300 ms, 8 s)`, the hard limit `min(4·soft, (t − reserve)/2, t − reserve/2)` floored at soft, the increment cap (F-23), and the time-control registrations (anchors, batches, openings, seeds).
- **Scope (measured):** a grid of 25,680 `(t, increment, movestogo)` points, old and new formula compared directly: 1,776 changed, all with `t ≤ 1495 ms`, and every change is a point where the old 20 ms floor was the output (or where `min(t)` clamped it). Unchanged at 40/15 (`t = 15000 ms`, `increment 150 ms`, `movestogo 40`) and at every `t ≥ 3200 ms` with `movestogo 40`.
- **Acceptance (run on the CLOCK-1 build):**
  - tests: `tests/clock_smoke.rs` 3/3; new regressions `clock_floor_f32_short_clock_keeps_reserve_over_a_period`, `clock_floor_f32_exact_values_below_the_old_floor_range`, `clock_floor_f32_huge_movestogo_does_not_overflow` pass; `clock_limits_respect_remaining_time` is updated from its pinned `(20, 20)` at 250 ms to `(1, 1)` (owner-approved expected value); `clock_limits_engine1_no_flag_death_march` unchanged and passing;
  - mutation: restoring the fixed 20 ms floor fails the three exact or period tests above and `clock_limits_respect_remaining_time`;
  - self-play, sudden death, same 3-game series: 300 ms 3 of 3 clean (63 plies, 0.19–0.21 s total think, 196–240 ms left); 1000 ms 3 of 3 clean (115–200 plies); 2000 ms 3 of 3 clean (176–200 plies);
  - self-play, other forms: 5000 ms 0 flags (192 plies); 15000 ms + 150 ms increment, `movestogo 40` 2 of 2 clean (200 plies each, 6.9–7.9 s left); 60000 ms + 1000 ms increment clean.
- **Known cost (stated, not measured in Elo):** on clocks of 300 ms to about 1 s, the engine now spends about 1 ms to 17 ms per move instead of 20 ms, and total thinking time per game falls (300 ms: about 0.2 s per game; 1 s: about 1.1 to 1.4 s per game). Playing strength at very short clocks is expected to be lower. Strength at 40/15 is not affected by the formula.
- **Consequences for frozen evidence:**
  - the change alters the engine binary, so the ENGINE-1 hash `9663697da62e33229d516af3681c442e268287c59d6b97ff2cd13256b564d428` and the ENGINE-2 (SEE) candidate hash `168dc0ab…` do not describe the CLOCK-1 binary;
  - the RATING-100 power report and its guard in `scripts/power_analysis.py` stay pinned to ENGINE-1 and will fail closed on the CLOCK-1 binary; this is intended;
  - no screening, control, or confirmatory game is authorized by this entry. Before any use of the CLOCK-1 binary in rating evidence, its hash must be frozen in a later append-only entry, and screening and controls must be re-registered on that hash.
- **Question put to the owner (verbatim options):** (a) amend ENGINE-1 and fix; (b) keep the formula and document the limit; (c) defer to a later release. Owner selected (a).

### CLOCK-1 binary identity freeze — ATTEMPTED, NOT FROZEN (2026-11-21, append-only)

- Purpose: the CLOCK-1 entry above says the new binary's hash must be frozen in a later append-only entry before any rating use. The owner's F-32 decision also asked for the refreeze and a gate and CI run on the new head.
- Head checked: `000266e` (source identical to the gated tree; later commits are ledger and docs only). Full local gate PASS (45 steps, FAILS=0; FAILURE_LEDGER.md). CI on `000266e`: `CI` run 44886526755 success; `anchor-verify` run 44886526780 success; its job `verify-flawless` (136792890005) success.
- Required by line 512 of this file: a successful exact-head anchor-verification run must publish the binary SHA-256. That value is NOT readable from this sandbox. Attempts, all failed with blob-storage EOF: `gh run download 44886526780 -n flawless-verify-44886526780` (blob URL), `gh api .../actions/artifacts/14700342084/zip`, and `gh api .../actions/jobs/136792890005/logs`. The check-run summary is empty.
- Therefore no hash is frozen by this entry. The local release SHA-256 of `000266e` (`0d9c508d…`, local build only) is NOT the hosted identity and is not recorded here as a freeze.
- Consequences (unchanged): ENGINE-1 hash `9663697d…` and ENGINE-2 (SEE) hash `168dc0ab…` still describe the pre-CLOCK-1 binary. No screening, control, rating, or confirmatory game is authorized. The RATING-100 power guard continues to fail closed.
- Next step, when the manifest is readable: take the SHA-256 of the `verify-flawless` binary from the exact-head anchor-verification run for the final head, append a new entry with that value, its run ID, and the source commit, and only then re-register screening on it.
