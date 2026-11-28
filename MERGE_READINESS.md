# MERGE_READINESS checklist — PR #1 (Flawless V1)

Policy (mission §7): an item is checked ONLY with verifiable evidence. Unmet items stay
unchecked; the mission stays `ACTIVE / INCOMPLETE` until every applicable item is verified.
Never merge/tag/release without explicit user authorization (§9).

Current PR head: see `git log --oneline -1` / `gh pr view 1 --json headRefOid`.

## Correctness & reliability

- [x] Project correctness and reliability audit complete — engine audit pass recorded in
      DESIGN_LOG.md (2026-11-14 adversarial review entry + TT clock-unsafety verification);
      differential perft 76,240 positions 0 mismatches (BENCHMARKING.md / AGENTS_LOG.md);
      full Rust suite 35/35, match.py 104/104, rating_estimator 65/65 at `2e46fc9`
      (evidence-push regression 10/10; ENGINE-1 clock regression included; bench signature
      unchanged fc907eba40b7869f).
- [x] Critical/major findings fixed or technically dispositioned — CodeRabbit review 5903125228
      (13 findings) dispositioned in AGENTS_LOG.md; TT halfmove-clock finding verified FIXED in
      src/tt.rs (clock-safe flag + probe suppression + regression test
      `clock_unsafe_entries_suppress_score_but_keep_move`).
- [x] Regression tests added for repaired defects — TT clock test (src/tt.rs), clock smoke
      (tests/clock_smoke.rs), shard partition + e2e manifest (scripts/test_match.py),
      estimator degenerate-Σ_m + covariances (scripts/test_rating_estimator.py).
- [ ] Full CI matrix green on the exact FINAL head SHA — new sample, recovery and SEE tests have not yet run on the implementation commit; final-head CI remains pending.
- [ ] No known unresolved correctness or security blockers — the earlier audit findings remain dispositioned, but the new SEE ordering candidate and RATING-100 workflow/recovery code still require hosted CI and exact-head review. Prior 5 review findings remain dispositioned; all 5 previously-open PR review
      threads verified against current code, replied with evidence and resolved 2026-11-14:
      covariance-between-anchors = valid/fixed (§9.6–8 + joint-cluster-bootstrap GLS estimator,
      46/46), match.py Windows pipe reader = valid/fixed (reader-thread + Event, no select on
      pipes), search.rs TT halfmove = valid/fixed (src/tt.rs clock-safe flag + probe suppression
      + regression test), uci.rs:433 hold/output race = invalid as described (worker
      hold-check+send and ponderhit clear+try_recv share one flush mutex; proven by analysis and
      locked in by new jittered stress regression
      `ponderhit_or_stop_racing_search_end_emits_exactly_one_bestmove`, 30 trials), uci_smoke
      wait robustness = valid/fixed (post-exit `drain_reader` through channel disconnection +
      full-line panic-marker scan in both tests).

## Rating methodology (docs/RATING_PROTOCOL.md §9)

- [x] Rating methodology fully implemented and independently tested — scripts/rating_estimator.py
      (65/65 re-run locally 2026-11-16) + scripts/aggregate_shards.py + match.py harness v2 (104/104).
- [x] Official anchor provenance verified — CCRL 40/15 list 2026-11-13 captured with HTTP 200,
      3,912,738 bytes, SHA-256 ce365c55b2869502de6addeada4c261d3bd2f50a5a9aef484db9f571aabe15f0;
      uncertainty convention = 95% CI (list text); record in benches/anchor-research-20261114.md.
- [x] ≥3 exact-version anchor binaries rebuilt and hash-verified on hosted runners — 6/6 anchors
      in anchor-verify.yml run 43597866181 (image ubuntu24 20261111.370.1, gcc 13.3.0):
      Wowl 1.3.7, Topple 0.1.1, Topple 0.2.1, akimbo 0.1.1, WyldChess 1.2, WyldChess 1.1.
- [x] Real `benches/anchor-pool.json` frozen and verified — 6 anchors, span 1849–2474, all
      runner SHA-256 + source SHA-256 + licenses + ci95 conventions; passes match.py
      fail-closed schema validation; exclusions recorded with reasons in the pool file.
- [x] SF10 hardware calibration complete — SF10 (official sf_10) bench on ubuntu-24.04 runner:
      3 runs 1998/1984/1996 ms vs i7-4770K reference 2054 ms for 3,939,338 nodes
      (Tors3/CCRL_ScirptsTests ccrl_bench.py) → factor k=1.0291, equivalent TC 40/14.58 min;
      batches play 40/15 wall-clock with the ~3% deviation documented (pool `calibration` block).
- [x] Throughput pilots complete — PILOT-1 (run 43602273258) + duplicate pilot (43603558950)
      both executed and RECOVERED: raw evidence committed via evidence-bridge rev 3
      (run 43683839993 SUCCESS, commit 2ec762e) and independently re-aggregated from the
      original shard artifacts (byte-identical, merged_sha256 aeb4d5a0… / a811d9d1…).
      Throughput re-verified from committed per-game records: 29.43 / 29.53 min/game
      (8-game batch shard ≈ 236 min < 330-min cap). Exploratory only, never gate evidence.
- [ ] Both null controls pass for the gate candidate (ENGINE-1, engine_sha256 9663697d…). CTRL-1 PASS (candidate-independent; −10.32 Elo calibration error within ±75; 240/240 counted). CTRL-2 PASS applies only to the pre-fix binary. CTRL-2-R run 43820392119 completed resolver + 120/120 successful shard jobs, but aggregate-and-commit-evidence was SKIPPED; no self-match estimate is available.
- [ ] Anchor selection finalized on ENGINE-1 candidate — SCREEN-2R remains selection-only (2176.8 / 2236.4 / mean 2206.6). SCREEN-3 run 43820645420 completed resolver + 60/60 successful shard jobs, but aggregate-and-commit-evidence was SKIPPED; no canonical third-anchor estimate or gate plan exists.
- [ ] RATING-100 prospective power gate — BLOCKED. The proposed design is 100 counted games/anchor/batch over 50 disjoint opening clusters; near 2,100 Elo sensitivity power for all three lower-bound decisions is insufficient under reasonable variance stress, and third-anchor / Batch-B covariance is unmeasured. No confirmatory dispatch is permitted until a reviewed, evidence-backed PASS exists.
- [ ] Batch A and Batch B independently pass the strict rating gate — NOT RUN.
- [ ] Combined calibrated 95% CI independently passes — NOT RUN.
- [ ] Every lower bound is strictly greater than 2,000, without rounding — NOT MEASURED.
- [ ] Exactly 100 counted games over 50 registered openings per eligible anchor/batch, committed and reproducible — NOT COLLECTED.
- [ ] Raw tournament evidence committed and reproducible — SCREEN-3 and CTRL-2-R shard artifacts have not been aggregated into canonical evidence; Batch A/B have not been run.

## Reviews & repository integrity

- [ ] CodeRabbit completed review on the exact final head SHA — last substantive review
      5903125228 at f07c4633; manual re-review at final head to be requested (path previously
      rate-limited: "manual review required for this OSS repository").
- [x] All relevant CodeRabbit findings dispositioned — 13/13 of review 5903125228 dispositioned
      (AGENTS_LOG.md) and all 11 of its review threads now carry evidence-based replies and are
      resolved (6 earlier + 5 on 2026-11-14; per-thread dispositions in the checklist above).
      Findings of the pending final-head review will be dispositioned the same way before merge.
- [ ] Documentation and PR description match the final implementation — sample-size amendment, exact-slot recovery and blocked power analysis documented; final-head PR body refresh and review remain pending.
- [ ] All mandatory GitHub branch-protection and review conditions satisfied — verify at merge
      time (repository rules; required checks where permitted, else documented privileged action).
- [ ] PR is no longer a draft and is genuinely ready for review/merge — PR #1 is currently
      **Draft** by policy until every checklist item is verified.

## 2026-11-25 — PR #6 iteration checkpoint (branch `arena/247fe7df-flawlesschess`)

**Verdict for this head: NOT MERGE-READY.** Nothing is technically blocked; the remaining gaps are the
rating gate, the pooled extended benchmark and an independent review, and they are listed below.

**Tested revision.** The full local gate suite (`scripts/final_gate.sh`) was run on commit
`c6ef5bbbfe16a6433d5ccd597b17266c93977b45` (tree `f83b722295a0717d695c5bed2e490e8e7dd7d1e6`): **51 of 51
steps passed, FAILS=0**, including the final check that the head, the tree and the working tree were
unchanged during the run. The release binary digest was
`284fdd226d65f8b366d59bf933e3c37d57450091e9df222a4808e675f31a4893`. A byte digest is not a stable
engine identity across build environments (it moves with the linker); the stable identity is the bench
signature `141943aa23b3fc68`, which `anchor-verify.yml` pins and CI re-checks at every head. The raw
output of that run — the summary and the log of every step — is retained in the repository under
`benches/gate-c6ef5bb/`, and `benches/gate-c6ef5bb/summary.txt` names the commit and the tree it ran on. The commit that follows
this one changes only these records and the retained evidence; it does not touch `src/` or any script
the gate covers, so the engine that produced the numbers is the engine on this branch.

What this iteration added and verified:

- [x] Outpost evaluation corrected to the classical definition (White ranks 5-6, Black ranks 3-4, files
      b-g, pawn-defended, safe from an enemy pawn that could step forward to attack) with boundary,
      symmetry, half-board and pawn-direction tests. The previous zone included the opponent's back rank
      and the rank where no enemy pawn can exist, and the term rewarded undefended pieces.
- [x] Tempo semantics resolved and pinned: the score is `+/- tapered + TEMPO` for the side to move, verified
      against the rustc parser source and by a dedicated regression test for both colours and the mirror.
- [x] The quick regression screen runs on every pull request of this repository (fork pull requests
      are excluded, because the job runs the pull request's own code with a `pull-requests: write`
      token). It remains a screen and not a strength measurement.
- [x] Local gate suite on the exact head `c6ef5bb`, with the raw output retained under
      `benches/gate-c6ef5bb/`: **51/51 steps, FAILS=0** (fmt, clippy debug and
      release, release and debug builds, release and debug test suites, every Python harness suite,
      the perft and legal-move differentials, the UCI protocol and fuzz probes, the clock and
      time-budget probes, the self-play probes, the full-game probe, and the head/tree/clean-tree
      check). Within it: `cargo test --release --locked` 183/183, difftest 2,275 positions d=2 with 0
      mismatches, perft(6) 119,060,324, match harness 112/112, benchmark suite 37/37, the
      weakness-diagnostic suite 31/31, the benchmark-request resolver suite 33/33, the run-table
      suite 105/105, release binary digest
      `284fdd226d65f8b366d59bf933e3c37d57450091e9df222a4808e675f31a4893` (this build environment;
      the stable engine identity is the bench signature `141943aa23b3fc68`).

  The definitive gate on `fc7407c` (the previous head) is retained in the session log rather than in
  the repository: its substantive 50 steps passed, and its only failure was the end-of-run clean-tree
  check, which caught this session's own mid-run refresh of `benches/quick-run-summaries.json` and
  `STATUS.md` (the fixture gained the `fc7407c` quick-run row while the gate was running). The run
  was repeated on the next committed head (`c6ef5bb`, above) with a clean tree and passed 51/51.
- [x] The 20 CodeRabbit review findings from the previous head are **dispositioned**: 19 were fixed in
      `67bee13` (workflow seed handling, PR scope, `SEED_BASE`, the rustfmt annotation encoding, the
      manifest ablation field, the aggregation rules, and the diagnostic/tactic harness defects), and
      the reported advancing-pawn defect in `src/eval.rs` was reproduced as a **false positive** — the
      cited position scores outpost 0 because the piece is not pawn-defended, and the defended variant
      with the same b7 pawn also scores 0. The algorithm is unchanged and the b7 case, its mirror and
      the undefended case are added as regressions.
- [x] The tactical diagnostic was re-run against the refined engine: **6/6**, recorded under
      `benches/tactic-test-20261124/` with the binary digest of the binary that produced it.
- [x] Hosted CI on the same head: Ubuntu and Windows format/clippy/test jobs, the MSRV 1.80 job and the
      Windows release artifact job are green, and the quick paired benchmark job completes and publishes its
      summary.
- [x] Relative screening evidence exists and was **read back**, three times. The first hosted
      three-replicate extended profile (600 real UCI games, 100 opening clusters, candidate `78f42ca`,
      run `45426475825`) finished **217 W / 164 D / 219 L**, score **49.8%**, relative Elo **-23.2 to
      +21.5** (95% CI), classification **INCONCLUSIVE**. The second, on the refined head (candidate
      `5be7d7b`, run `45529006866`), finished **227 W / 156 D / 217 L**, score **50.8%**, relative Elo
      **-19.7 to +31.4** (95% CI), classification **INCONCLUSIVE**. The third, on the final head
      (candidate `13f8162`, run `45546563480`, independent seed), finished **229 W / 163 D / 208 L**,
      score **51.7%**, relative Elo **-11.0 to +35.4** (95% CI), classification **INCONCLUSIVE**. Every
      interval straddles 50%: the candidate is **not** measurably different from the pinned baseline.
      Recorded as screening evidence only; it is not a strength claim.
- [x] The ablation study was run and **read back** (hosted run `45529550258`, candidate `d306cbc`,
      `screen` profile, seed `20261130`, 200 games per variant): `full` 53.5%, `no-space` 53.8%,
      `no-counter-move` 47.8%, `no-new-terms` 46.8%. **Every variant is INCONCLUSIVE with overlapping
      intervals**, so the study does not measure the contribution of any of the three terms at this
      sample size. The ablation switch itself is verified; the magnitude of each term's contribution
      is not. This is a diagnostic, not a strength claim.
- [x] The 40-game quick screen is **not** usable as a strength signal: the hosted runs of the
      identical profile on heads with a **byte-identical release binary** (the last change to `src/`
      on the branch is the outpost refinement `98e5cd9`, and every head from it on has the identical
      `src/` tree and identical `Cargo.toml`, `Cargo.lock` and `rust-toolchain.toml`) have ranged from
      **38.8% to 67.5%** — **28.7 points on code that did not change** — and the same unchanged engine
      has produced both the label `POSITIVE_RELATIVE_SIGNAL_SCREENING_ONLY` and plain `INCONCLUSIVE`.
      The generated table in `STATUS.md` carries every row and the current counts; the number of runs
      grows on every push, so no fixed count is repeated here. Every row was transcribed from the published hosted summary and re-checked
      against the scoring formula `(wins + draws / 2) / games`; an earlier transcription had the wrong
      W/D/L in six rows and had missed two runs, and the correction is appended to `AGENTS_LOG.md`. The
      table is now generated from the published summaries by `scripts/refresh_run_table.py`, with
      `scripts/test_run_table.py` failing on drift. A fixed 100 ms movetime makes the played games machine- and
      jitter-dependent, so the seed fixes the opening order but not the games. The quick screen stays a
      regression screen. The three runs below `98e5cd9` (40.0%, 42.5%, 36.2%) are on a different engine
      and are not part of that range.
- [ ] **Absolute V1 rating gate: NOT MET.** Still UNKNOWN / NOT MEASURED. The relative screening result above
      is not an absolute rating and cannot be used as one. **Campaign state (2026-11-27):** the ENGINE-3
      (PR #6 candidate) hosted binary hash `733de4e5…` is frozen from the `verify-flawless` annotation;
      its campaign evidence is COMPLETE and verified (CTRL-3 self-match 240/240 PASS, CI contains 0.5;
      SCREEN-E3 batch A 360 games + batch B 360 games, one registered unadjudicated attempt disposed of
      by complete-case cluster exclusion, PREREGISTRATION 2026-11-26/27). The ENGINE-3 prospective power
      assessment is a computed PASS (`benches/rating-100-power-assessment.json`, design `rating-240-v1`,
      power_all_three 0.944 at true 2,100 / 1.5x inflation) with `approval: null` - the confirmatory
      batches remain blocked until that approval block is granted, and the ENGINE-4 (current head)
      per-engine campaign evidence is closing out in parallel (its own controls/screening/reviewed power
      must PASS independently; per-engine evidence never transfers).
- [x] **Pooled extended benchmark.** Dispatched through `benches/benchmark-request.json`, executed and read
      back (see the item above). The result is INCONCLUSIVE, so it does not support a strength claim.
- [x] **Pooled extended benchmark on the refined head.** The revision-2 extended run on the refined head
      finished and was read back (see the item above): 227/156/217, 50.8%, relative Elo -19.7 to +31.4,
      INCONCLUSIVE. **Attribution (corrected per review 2026-11-27):** this is an ENGINE-3 measurement.
      Its engine source (`src/`) is byte-identical to the ENGINE-3 refined candidate `5be7d7b`, and only
      the harness, the workflow and the records changed within that engine's development line; the
      candidate SHA that was actually built and measured is recorded in `AGENTS_LOG.md`. It is NOT a
      measurement of the current ENGINE-4 head (`dd3dff2`): `src/search.rs` differs between the two
      engines (the ENGINE-4 queen-pin fix), so this benchmark cannot be cited as ENGINE-4 strength.
- [x] **Pooled extended benchmark on the final engine.** Revision 6 of the request marker dispatched
      the three-replicate extended profile with an independent seed (20261201/02/03). It finished and
      was read back: **229 W / 163 D / 208 L** of 600, score **51.7%**, relative Elo **-11.0 to +35.4**
      (95% CI), **INCONCLUSIVE** (hosted run `45546563480`). This is likewise an ENGINE-3 measurement
      of `13f8162`, not of the ENGINE-4 head.
- [ ] **Pooled extended benchmark on the exact head commit.** The run above measured the commit
      `13f8162`, **not** the commit that is the head. The two are not the same revision, and
      identical engine source does not make them one: the item is therefore left unchecked. What
      carries over is the engine identity, which is checked by hash rather than by assertion — the
      `src/` tree of `13f8162` is `daa6be83ad991ee16eb86986e9eaa676c9eea460`, the same tree as the
      head's, and `Cargo.toml`, `Cargo.lock` and `rust-toolchain.toml` are identical too, so the
      release binary that was measured is byte-for-byte the head's binary. The extended profile has
      **not** been re-run on the exact head commit, and it cannot be: every commit that records the
      result moves the head again. The three extended runs read 49.8%, 50.8% and 51.7%, every
      interval straddling 50%: the point estimates drift while the interval keeps covering the
      baseline. That is what small underlying effects look like, and reading the drift as a strength
      signal would be reading noise. No strength difference is measurable.
- [ ] **Fresh independent review at the final head SHA** (CodeRabbit or equivalent). Three review rounds
      have been read back and dispositioned on this branch: the first (20 findings) in `67bee13`, the
      second (14 findings, 9 still valid) in `25d7d66`, and the third, whose findings were all confirmed
      resolved by the reviewer itself. The last of those rounds was against `c428d66`, and this branch
      has moved on since, so a review of the exact final head still has to be requested and read back
      before this item can be checked.
- [x] **PR #2 audited read-only** and left untouched: 49 commits, 12,971 insertions, 66 files, draft and
      conflicting with `main`. The two classical outpost conditions that this branch was missing were found
      there and ported into this branch's own implementation; nothing of PR #2 was merged or cherry-picked.
- [ ] PR #6 stays a **draft**. No merge, tag or release has been performed; those require explicit user
      authorization (mission §9).

## Authorization record

- No merge, tag, or release has been performed. Those require explicit user authorization
  separate from merge-readiness (mission §9).

## 2026-11-17 validation checkpoint

The first CI run for the SEE + RATING-100 implementation passed Rust formatting, Clippy and unit tests on Linux and Windows and passed all five Python test suites; both jobs were rejected by the newly added opening-subset verifier. This was a real selector-generation defect, caught before any confirmatory dispatch. Corrected suites, hashes, CI assertions and append-only preregistration/protocol notes are prepared for the next commit. The exact-head CI checklist remains UNCHECKED until both OS jobs pass after that correction.


## 2026-11-17 — exact-head validation (commit 5b63e27)

CI run 44066217195 passed on Ubuntu + Windows + Rust 1.80, including the corrected suite selector, all Python/Rust tests, power smoke, release, UCI and perft checks. Anchor verification run 44066217113 passed 13/13 and recorded the exact source-tree binary SHA-256. This check describes commit 5b63e27; a follow-up commit adds the engine-provenance guard and must receive its own exact-head CI before any readiness item is checked. Fresh CodeRabbit review at the eventual final HEAD remains pending. PR stays Draft.

## 2026-11-17 — provenance test follow-up

The first CI run after adding engine-SHA isolation (44067364552) failed the new power-manifest suite on one overly specific expected-error message; production code rejected the non-SCREEN-2 hash at the earlier allowlist. The test expectation is corrected in the next commit. Exact-head CI remains unchecked until the follow-up run is green. Anchor verification itself passed 13/13.

## 2026-11-17 — Windows newline portability issue

The c564c5c exact-head CI was not green: Ubuntu and MSRV passed, but Windows failed the power-report smoke because of CRLF checkout conversion of committed raw evidence. A targeted cross-platform JSONL hash normalization and tamper test are prepared. Keep full CI unchecked until the follow-up commit is green on Linux and Windows.

## 2026-11-28 — mission Phases A–K checkpoint (branch `arena/247fe7df-flawlesschess`)

**Verdict for this head: NOT MERGE-READY.** The ENGINE-4 confirmatory campaign and its
registered recovery protocol are still executing on hosted runners; the absolute rating gate
cannot be recomputed until that evidence is committed. Nothing below claims an unverified
pass. Engine identities in use: **E4** = the frozen confirmatory candidate
(`bbf9582db58b1fe8fb0aa8f3675e4bedcc7e62062e8f1fe41de9e6526af0c329` at freeze target
`cb7242c`), **E3** = the previous engine generation (bench `141943aa23b3fc68`), **E5** = the
queen-trap successor that does not exist in `src/` yet and must complete its own
preregistered chain (dispatch-analysis-2026-11-27.md) before it can become a merge
candidate. Evidence produced under one identity is never reused for another.

### ENGINE-4 campaign + recovery (Phase B) — IN FLIGHT

- A / wowl-1.3.7: run 45998977117 = FAILURE with 236/240 counted games committed under
  `benches/evidence/confirmatory/batchA/wowl-1.3.7/run-45998977117/`; missing slots 124–127
  (shard 31, diagnosed `aborted_engine_errors`). Recovery dispatch rev 57 (pushed as
  `f4a0ba4`, rating-run 46111280732) will replay exactly those four slots.
- A / topple-0.1.1: run 45999016751 = CANCELLED with 58 complete shards and partial 31/37;
  evidence not yet committed — evidence-bridge request rev 7 (run-45999016751, `evidence_out`)
  is queued (46111148534 / 46111280738). Recovery of slots 124–127 + 148–151 must be
  dispatched (rev 58) only after that bridge commit exists, because the resolve gate requires
  prior committed run evidence for a recovery dispatch.
- A / wyldchess-1.1: run 45999052791 completed 60 shard jobs with shard 17 failed and the
  aggregate job queued; recovery of slots 68–71 only after the run resolves (aggregate
  commits 236 games; else bridge first).
- B / wowl-1.3.7: 60/60 shards succeeded, aggregate job queued (45999096409).
- B / topple-0.1.1: running (45999142482; ~3.2 h per 4-game shard on hosted runners).
- B / wyldchess-1.1: 60 shards queued (45999195004).
- `gh run rerun` is not a permitted recovery path (artifact-name collisions; replays counted
  slots). Only genuinely missing schedule indices are ever dispatched.

### What was completed and verified in this checkpoint

- [x] Phase E — all five registered findings fixed with regression suites, plus the review
      corrections: refresh_run_table paginated `--slurp` parse (`3e7a7d0`); en-passant captured
      square in adjudicate_traps (`a9a276c`); pinned pseudo-attacker exclusion via
      `legal_attackers()` (`a9a276c`); exact source-record flag identity `(rec, fen, ply, move)`
      with a duplicate-key 2-not-4 regression (`a9a276c`); engine failures abort with exit
      code 3 distinct from ply-cap truncation, child reaped (`ada9fc2`); batch A/B color-pair
      seating fixture (`c0c6306`); reversed `check()` arguments in test_run_table fixed — the
      real conditions pass (`851bfc2`). Full harness battery: **18/18 suites green** at
      `851bfc2` (each output inspected).
- [x] CI suite list complete: `.github/workflows/ci.yml` now runs all 18 Python suites at the
      exact head (`c0c6306`) — historical green on other SHAs is not claimed as current.
- [x] Phase G review debt: all 51 PR review threads re-fetched from GitHub; 5 fixed threads
      replied with fix evidence and resolved; the remaining open thread
      (relative_benchmark saved opening-order digest) is deliberately scheduled for Phase F
      after the campaign closes. The 10 named review items verified against source:
      evidence-bridge latest-attempt + completed-only artifact collection ✓;
      power_analysis_v2 skipped/excluded-row accounting + exclusion completeness + one-AB/one-BA
      colour reversal ✓; PREREGISTRATION wording "strictly > 2,000" ✓ (append-only, unchanged);
      candidate/player-color consistency ✓; recovery schedule validation ✓ (7/7 tests);
      manifest provenance checks ✓; focus-player handling ✓; queen-defence legality ✓.
- [x] Phase H adversarial audit complete — all ten areas: (1) pruning: search.rs diff coherent
      (EXT_BUDGET-bounded check extensions with per-line accounting through null-move;
      counter-move behind the ablation mask; soft-budget stop; LMR/NMP conditions unchanged);
      (2) legality: make/unmake restores the full state (castling, ep, clocks, hash,
      ep-inclusion) and the perft/legal differentials cover it in CI; (3) TT: clock-safe
      contextual keys, depth-preferred replacement with generation aging, key16 verification;
      (4) qsearch: terminal-before-stand-pat, fifty-move claim wrapper, mate-score margin
      exemption (F-42), SEE ordering-only; (5) UCI lifecycle: unchanged in this diff, prior
      race dispositions hold; (6) manifests: match.py records threads and `flawless_ablate`
      before the first game; read_committed_runs verifies identities/counts/duplicates;
      (7) recovery: the deliberate-dispatch marker gate and read_committed_runs missing-slot
      recomputation verified end-to-end (7/7 tests); (8) estimator: strict unrounded gate
      design verified in rating_estimator (65/65); (9) workflow injection: scan clean — no
      `${{ }}` reaches any `run:` body in any workflow (env-var indirection only);
      (10) silent failures: the Phase-E fixes (engine-failure abort, pagination crash,
      false-green check args) and fail-closed resolve/aggregate paths. Fresh full-diff pass
      covered src (5 files), workflows (6), scripts (23), tests/correctness.rs and the
      campaign control files (dispatch rev 57 / evidence-request rev 7 fields verified).

### Open gates (each must be verified before any merge)

- [ ] Phase B: recovery dispatches run and their evidence is committed; every shard verified
      by job conclusion AND committed evidence; aggregates independently recomputed.
- [ ] Phase C: absolute V1 gate recomputed from the committed raw records —
      unrounded `ci95_calibrated[0] > 2000` strictly, for Batch A, Batch B and combined,
      plus both null controls (CTRL-3 ±75, CTRL-4 self-match 0.5∈CI), 240 counted games per
      anchor/batch, every counted game reproducible, identities matching the freeze.
      Tooling ready: `scripts/rating_estimator.py gate` with `--exact-games 240
      --required-openings 60 --games-per-opening 4 --suite-a --suite-b`.
- [ ] Phase D: probe v6 (46110985046, `710100e`) read back and adjudicated; then ENGINE-5
      implemented with its FULL own chain (binary hash, anchor verification, controls,
      screening, own power assessment + independent review + approval, own confirmatory +
      rating). The queen-trap fix is NOT applied to `src/` in this checkpoint.
- [ ] Phase F: relative_benchmark missing-digest strictness + its regression (after the
      campaign closes, per plan).
- [ ] Phase G: fresh independent full-diff review of the final head.
- [ ] Phase I: full hosted CI matrix green on the exact final head (Ubuntu/Windows/MSRV,
      all 18 suites, perft/differential, UCI/clock/perf).
- [ ] Phase J: final docs reconciliation including PR description; no checklist item checked
      without evidence at that head.
- [ ] Phase K: gate checklist and final report with the verdict for the final head.

### Authorization record (unchanged)

- No merge, tag, or release has been performed. Per the 2026-11-28 mission instruction, PR #6
  must be left OPEN and merge-ready for an explicitly authorized merge; nothing here merges it.
