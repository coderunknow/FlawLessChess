# STATUS — Flawless Chess Engine

**Project state: `ACTIVE / INCOMPLETE`** (V1 NOT complete; absolute rating is UNKNOWN / NOT MEASURED and the strict 2,000 Elo gate is NOT MET. SCREEN-3 run 43820645420 ended with resolver + 60/60 shard jobs successful, but its aggregate-and-commit-evidence job was skipped. CTRL-2-R run 43820392119 ended with resolver + 120/120 shard jobs successful, but its aggregate-and-commit-evidence job was also skipped. These shard artifacts are not canonical committed gate evidence. The RATING-100 amendment is implemented as a candidate design but its prospective power report remains BLOCKED; no confirmatory batch or gate plan has been dispatched. The SEE ordering candidate and new tooling await CI and fresh review.)

**Current branch:** `arena/247fe7df-flawlesschess` (based on `main` = `6ab5b33`, the PR #5 merge
commit; verified 2026-11-24).
**Starting commit (verified 2026-11-14):** `98b1a00203183d9c7ccb175f7d6eb8f5ef5eb429` (only an Apache-2.0 `LICENSE` present).
**Engine identity (UCI):** `Flawless`
**License:** Apache-2.0 (preserved)

> **Repository-state reconciliation (2026-11-24).** The entries above and much of the checklist and
> review history in this file were written during the development of PR #1 (branch
> `arena/b756c5f1-…`) and describe work that was in flight at that time. As of the current
> `main` HEAD (`6ab5b33`, the PR #5 merge):
> - Pull requests #1, #3, #4 and #5 are MERGED into `main`; PR #1 is no longer open or draft.
> - The only open PR is #2 (`arena/8259ce1c` → `main`, head `5f952b12912dc6c77f8339fd8216aa90e6338fc0`),
>   which is **Draft** and **CONFLICTING** with `main`. It holds the unvalidated SPEED-1 / HIST-1 /
>   EVAL-2 experiments (fast legality filter, continuation/counter/capture history, evaluation
>   upgrade behind ablation flags). Per the mission, PR #2 is NOT merged, NOT cherry-picked, and
>   NOT silently closed here; it is audited against `main` in this session's report and its
>   candidates remain for a later, gated iteration.
> - `STATUS.md`, `MERGE_READINESS.md`, `TESTING.md`, `BENCHMARKING.md` and `AGENTS_LOG.md` still
>   reference the pre-merge branch state and CI runs on commits (`ca61ea6`, `f2176b6`, `c24020b9`,
>   `071f875`, `5b63e27`, …) that are not the current `main` HEAD. Those records are preserved as
>   historical evidence; current-state claims below are re-scoped to `6ab5b33`.
> - The V1 release gate (absolute rating > 2,000, two-sided 95% CI lower bound strictly > 2,000)
>   remains NOT MEASURED and NOT MET; no absolute Elo claim is made.

> ### Current session (2026-11-24, branch arena/247fe7df-flawlesschess — PR #6 draft)
>
> Three engine improvements implemented, each committed separately with full local validation
> (fmt, clippy -D warnings, 172/172 tests, diftest 2321/0, perft(6)=119060324, bench signature
> 141943aa23b3fc68 unchanged):
>
> 1. **Time management** (commit d5305ee): removed the predictive-overrun early stop that halted
>    clock-based searches well before the soft budget. At 10 s the engine previously stopped at
>    116 ms of a 234 ms soft budget (depth 9); it now runs to depth 10 at ~253 ms. Hard budget
>    still caps worst-case overspend; fixed-depth/movetime searches unaffected.
> 2. **Counter move heuristic** (commit a162baa, HIST-1 from PR #2 audit): when a quiet move
>    causes a fail-high cutoff in reply to the opponent's previous move, store it as a counter
>    move ordered just above killers (92,000) and below good captures. Counter table cleared each
>    root search; not used in null-move search or quiescence.
> 3. **Space evaluation** (commit 4038b75, EVAL-2 from PR #2 audit): reward control of important
>    squares weighted by centrality. Colour-symmetric via square mirroring (sq ^ 56). Tapered:
>    full weight middlegame / half endgame. Added `space` field to `EvalBreakdown` and CLI `eval`
>    output.
>
> No claim of strength improvement is made for any of these changes; no rating evidence has been
> re-measured. PR #2 (open, draft, conflicting) remains NOT merged, NOT cherry-picked, NOT touched.

## Checklist (binary acceptance criteria — see TASK in prompt)

- [x] Repository recon complete (Phase 0)
- [x] Starting commit / remote state verified and recorded
- [x] Rust toolchain available (1.99.0, installed from npm `@toolchain-bin/*` because static.rust-lang.org is unreachable; see `docs/ENVIRONMENT.md`)
- [x] Architecture RFC published (Phase 1) — see ARCHITECTURE.md (accepted for v1 scope)
- [x] Chess foundation: perft COMPLETE 2026-11-14 — full CPW reference matrix 27/27 exact matches (startpos d1–d6, Kiwipete d1–d5, pos3 d1–d6, pos4 d1–d6 incl. d6 = 706,045,033, pos5 d1–d5; raw record `benches/perft_full_20261114.md`); python-chess oracle cross-check MATCH (`scripts/perft_oracle.py`); startpos d3 = 8902 additionally asserted in CI every push/PR, both OSs
- [x] Differential testing vs python-chess (pinned 1.11.2, GPL-3.0+, test-only oracle) — DIFTEST PASSED, 76,240 positions, 305 d3 perft comparisons, 0 mismatches
- [x] UCI protocol implemented and smoke-tested (async stop via worker thread + AtomicBool, clocks, MultiPV, ponder/ponderhit) — fuzzed smoke-level (seeded, deterministic; tests/uci_smoke.rs) — see TESTING.md; deep fuzzing NOT performed
- [x] Search baseline: iterative deepening + alpha-beta + TT (8-byte) + quiescence + null-move + LMR + aspiration + MultiPV (uncommitted until this phase checkpoint; see below)
- [x] Classical evaluation baseline (tapered PSTs, mobility, bishop pair, king zone, tempo); NNUE interface deferred, NNUE NOT default
- [x] Benchmark harness (fixed-time `movetime`/`depth`, paired openings, color reversal, opening-clustered CI) — `scripts/match.py` + `scripts/stats.py` + `benches/openings-20.txt`; verified end-to-end (smoke-match 2/2 wins vs SF 19 WASM Skill 0)
- [x] CI green on Linux + Windows (fmt, clippy -D warnings, release tests, release build, UCI handshake, UCI bestmove smoke, perft d3 sanity) + MSRV (1.80) job — PR #1, runs 43562935232 / 43563085939 / 43563499046 (clippy-fix regression, caught by CI, fixed in 837361f) / 43563628232 / 44c8369-era all green (except the known-bad b85b3f7); Kilo Code Review bot fails for account credits (not a code issue); CodeRabbit manually triggered (incremental) — see "Reviews" below
- [x] Match infrastructure: paired openings, color reversal, opening-clustered bootstrap CIs — `scripts/match.py` + `scripts/stats.py` (used for probes); panic-fallback games flagged `engine_error` and excluded from stats by default
- [x] **Rating harness v2 (2026-11-14)**: true UCI clock TC (`--tc 40/15` repeating schedule, `wtime/btime/winc/binc/movestogo`, actual-elapsed charging, flag fall, ponder off, `add`/`reset` period policy), historical deterministic repetition schedule (60×17×2=2,040/anchor/batch, superseded for future confirmation by append-only RATING-100) + exact AB/BA reversal, deterministic shard slicing (`--shard-index/--shard-count`), engine-error record→immediate-replay→abort-after-2 policy, move-cap recorded unadjudicated (never a silent draw), manifest v2 written before game 1 and finalized after (interrupted runs stay `in_progress`), opening-suite SHA-256 + schedule hash + shard identity in manifest, anchor-pool schema hardening (rejects TBD/null/placeholders, malformed SHA-256, ambiguous uncertainty conventions, unverified licenses/binaries). Regression suites: `scripts/test_match.py` (**104/104**), `tests/clock_smoke.rs` + `uci::tests::clock_limits_*` (Flawless clock-management verification; **34/34** cargo tests incl. the bestmove-handoff stress regression)
- [x] **Rating estimator (2026-11-14)**: `scripts/rating_estimator.py` implements RATING_PROTOCOL §9.6–9.8 — joint opening-cluster bootstrap (≥10,000, same cluster draw across anchors), per-anchor logistic d_a, σ_matched = SD of joint replicates, published-error → SD convention conversion (sd/se/ci95/ci90/ci99), GLS over Σ_m+Σ_c with documented diagonal-WLS fallback, separate match-only vs match+calibrated CIs, batch combination that pools match noise but adds shared calibration ONCE, null controls (anchor-vs-anchor ±75 Elo; self-match ~0.5), fail-closed `gate` subcommand that recomputes from raw evidence. Regression suite `scripts/test_rating_estimator.py` (**53/53**, incl. `scripts/verify_evidence.py` fail-closed checks on committed evidence). Shard aggregator `scripts/aggregate_shards.py` (fail-closed §5.2 rejection rules; smoke-verified both directions)
- [x] **Rating workflows (2026-11-14)**: `anchor-research.yml` (fetch official CCRL 40/15 list from a hosted runner — open egress — with full provenance), `rating-run.yml` (workflow_dispatch shard execution, frozen commit/engine-hash/suite-hash verification, hardware capture, fails CLOSED until a verified anchor pool exists), `rating-gate.yml` (stable `rating-gate` job: aggregate+verify then independent estimator recomputation; SUCCESS only if all three lower CI bounds strictly > 2,000 and both null controls pass). Note: GitHub delivers `workflow_dispatch`/`workflow_run` only to workflow files on the default branch (main has only `LICENSE`), so remote runs go through `pull_request`-path triggers until merge; the permanent dispatch path is `gh workflow run`.
- [x] Identity migration to Flawless (ADR-0002) — historical evidence kept under old identifiers
- [x] Correctness audit pass 1 + 2 (mate>draw precedence, quiesce/RFP terminals, searchmoves MultiPV=1, clock_limits panic, panic-fallback plumbing) — all reproduced by regression tests; bench signature `d790483532d87af0` → `3086f65159758c9d`
- [x] UCI integration smoke + seeded deterministic fuzz (`tests/uci_smoke.rs`)
- [x] **UCI no-argument startup compatibility (2026-11-19)**: launching `flawless` with no arguments enters UCI mode (previously exited 2 with usage text, which broke GUIs that start the engine with `Process.start(path, [])`). Regression tests run the real executable in both launch modes (`tests/uci_smoke.rs`). Windows x64 artifact job added to CI. Scope is UCI startup compatibility only: no search, evaluation or rating claim. See `docs/audit/2026-11-19-uci-no-args-compatibility.md`.
- [ ] Absolute rating > 2,000 (two-sided 95% CI lower bound STRICTLY GREATER THAN 2,000) — NOT MEASURED, NOT MET. CTRL-1 PASS remains candidate-independent; CTRL-2 PASS applies only to the pre-fix binary. CTRL-2-R run 43820392119: resolver + 120/120 shards succeeded, but aggregate-and-commit-evidence was SKIPPED, so no self-match estimate exists. SCREEN-2R remains selection-only (topple-0.1.1 2176.8, topple-0.2.1 2236.4, mean 2206.6). SCREEN-3 run 43820645420: resolver + 60/60 shards succeeded, but aggregate-and-commit-evidence was SKIPPED, so no third-anchor screening estimate exists. No gate plan or Batch A/B evidence exists.
- [ ] RATING-100 confirmatory sample — NOT AUTHORIZED / BLOCKED. Proposed 100 counted games per anchor per batch (50 opening clusters × AB/BA), with disjoint A/B suites; all historical gate conditions and controls remain unchanged. The delta-method prospective sensitivity report is BLOCKED because full third-anchor covariance and Batch-B cluster variance are absent and power is weak near the 2,000 threshold. No confirmatory dispatch may proceed until a reviewed evidence-backed PASS exists.
- [ ] SEE-based capture ordering candidate — implemented in source but NOT YET BUILT, TESTED, BENCHMARKED OR REVIEWED. No Elo gain or NPS improvement is claimed.
- [ ] Reviews: CodeRabbit review 5903125228 fully dispositioned (13/13 findings; 11/11 threads replied+resolved 2026-11-14); FRESH review at the exact final SHA still required; Copilot BLOCKED (quota, lower-effort retry needs web UI); Codex RATE_LIMITED; Qodo BLOCKED (trial ended); Kilo BLOCKED (credits)
- [x] PR #1 ("Flawless V1 checkpoint: identity + correctness audit + CI") is **MERGED** into `main`
  (`6ab5b33`). It is not open and not draft. The PR-stay-open statements here are historical only;
  PR #1 must not be re-opened, re-merged, or used as the basis of a new PR without explicit
  authorization.
- [ ] Correctness, reliability, documentation, release gates (see TESTING.md)
- [ ] v1.0.0 stable release (**NOT AUTHORIZED — gate not passed**)

## Hard constraints / environment notes

- No crates.io access (blocked): the engine is implemented with **zero external dependencies** (pure `std`).
- No static.rust-lang.org access: toolchain installed from npm packages `@toolchain-bin/{rustc,cargo,rust-std,rustfmt,clippy}-1.99.0-x86_64-unknown-linux-gnu` into `/home/user/.toolchain/sysroot`.
- Reference machine (target): Windows 10 LTSC 2021, i5-7300U (4 threads), 8 GB RAM. This dev sandbox: 2 vCPU, ~4 GB RAM, Linux.
- Opponent binaries for anchored rating testing are limited; see BENCHMARKING.md for the honest state of rating evidence.

## Measured strength probes (internal, in-sandbox; NOT a CCRL/CEGT rating)

Pinned opponent: Stockfish 19 WASM `stockfish-19-lite-single` (npm `stockfish@19.0.1`, single-threaded,
hashes recorded in BENCHMARKING.md). TC: 100 ms/move fixed; 20 openings ×2 colors paired; output
committed under `benches/probe-*`.

| Probe | SF setting | Ours W/D/L | Score | 95% opening-clustered CI | Logistic Elo diff vs this setting |
|-------|-----------|------------|-------|---------------------------|-----------------------------------|
| probe-001 | Skill 0 | 40/0/0 | 1.000 | [1.000, 1.000] | boundary: perfect observed score; no finite estimate (unbounded above) |
| probe-003 | Skill 5 (pre-RFP/CE) | 11/13/16 | 0.438 | [0.325, 0.550] | −44 (CI [−127, +35]) |
| probe-002 | Skill 10 | 1/7/32 | 0.113 | [0.050, 0.175] | −359 (CI [−512, −269]) |
| probe-004 | Skill 5 (RFP+CE build) | 14/14/12 | 0.525 | [0.412, 0.637] | +17 (CI [−61, +98]) |
| probe-005 | Skill 5 (post-refactor, 100 ms) | 20/8/12 | 0.600 | [0.463, 0.725] | +70 (CI [−26, +168]) |
| A/B 004 | vs pre-change build, 50 ms | 18/13/9 | 0.613 | [0.487, 0.725] | +80 (CI [−9, +168]) |

Conclusion (honest): our strength is bracketed between pinned SF-Skill-5 and SF-Skill-10 at
movetime 100 ms on this hardware. The RFP+check-extension change moved the needle in the right
direction (+80 in the A/B, +17 vs Skill 5, both CIs wide and overlapping zero at 40–120 games).
Absolute Elo is UNKNOWN and unverifiable from this sandbox — no calibrated anchor was available, so
no absolute number in either direction is supported by evidence; v1.0.0 gates NOT met; rating
estimate = **INCONCLUSIVE**. Do not present these numbers as official ratings.

## Next preregistered task

1. Keep engine development evidence-based: if time permits, probe skill 3/7 to tighten the bracket, or run
   longer-TC probes; do not tune to the probe opponent.
2. ~~NPS / bench regression tracking~~ DONE (2026-11-14): `cargo run --release -- bench` — fixed
   depth 10 over 12 positions, deterministic FNV-1a signature `3086f65159758c9d`
   (2,317,474 nodes); `bench_eval` for eval throughput; CI runs perft d3 + UCI handshake + bestmove smoke.
3. Remaining V1 gaps: benchmark CLI `bench`, time-management validation vs clocks, EF RN search-consistency
   checks, Windows-specific verification (CI covers build only), and documentation of the release gates.
4. NEVER claim v1.0.0 status; never present in-sandbox numbers as CCRL/CEGT.

## Local verification re-run (2026-11-14, workspace restore #3)

Toolchain (npm @toolchain-bin @1.99.0 pins) rebuilt per docs/ENVIRONMENT.md; DIFTEST re-passed
(legal-move sets identical; perft-d2 2295/2295, 0 mismatches, seed 20261114); `cargo test --release`
29/29 green; clippy clean (1 latent too_many_arguments fixed via StoreRequest); bench re-measured:
signature unchanged `fc907eba40b7869f`, 2,221,199 nodes @ d10 (43% reduction; 259,619 nps).

## CI status on current head (2026-11-14, verified via gh run list/view)

- Head `ca61ea6` (PR #1): CI run **43579289640 — SUCCESS** (ubuntu-latest, windows-latest, msrv rust 1.80 all green).
- Head `89189a6` (docs-only): CI run 43579193978 — SUCCESS (all three jobs).
- Head `e769d9a` (PR #1): CI run **43578826380 — SUCCESS** (ubuntu-latest, windows-latest, msrv rust 1.80 all green).
- Head `45f8507`: CI run 43578590768 — SUCCESS (all three jobs).
- Head `1fb14ae`: CI run 43578036659 — SUCCESS (all three jobs).
- (Failures 43577034924 on db174e4 and 43577274974 on 4aa7f06 were the clippy `too_many_arguments`
  episode — fixed by StoreRequest in d6dc221; remote annotations then confirmed the root cause.)
- CodeRabbit re-review: requested 2026-11-14T09:25Z on head `e769d9a` → returned **"Review rate
  limited"** (neutral, e769d9a check-run). The automatic push-review path is disabled for this OSS
  repository ("Review skipped: manual review required for this OSS repository" on 89189a6/ca61ea6).
  `@coderabbitai resume` posted 2026-11-14T09:47Z — awaiting result. **No review pass may be claimed
  until CodeRabbit completes on the exact final head SHA.**
- Evidence pipeline: scripts/match.py now records hardware/OS, per-side artifact SHA-256 (incl.
  dynamically loaded WASM), git commit, adjudication and color-pairing text in meta.json; pre-
  registered ≥60-line opening suites for batch A/B (`benches/rating-openings-batchA.txt`,
  `batchB.txt`, FEN-verified, mutually disjoint); value-free anchor descriptor template
  (`benches/anchor-pool.template.json`). Manifest is now written and closed before the first game
  so provenance survives an interrupted batch (fixed after observing it buffered for a whole run).
- probe-005 (post-refactor regression probe vs SF19-lite Skill 5, committed): 24/40 = 0.600,
  opening-clustered 95% CI [0.463, 0.725], logistic +70 (CI [-26, +168]), 0 engine-error games —
  same band as probe-004 (0.525), no regression. Relative statistic only; not a rating.

## Rating status (absolute; release-gate relevant)

- **Absolute rating: UNKNOWN.** The in-sandbox probes (SF Skill 0/5/10 WASM) are relative comparisons
  vs one unrated-for-our-purposes opponent configuration, not a calibrated absolute scale, and are NOT
  a CCRL/CEGT rating. Stockfish Skill Level is not a calibrated Elo anchor.
- **The V1 release gate (two-sided 95% CI of calibrated absolute rating, lower endpoint STRICTLY
  GREATER THAN 2,000 Elo — amended from ≥ 2,000 on 2026-11-14, docs/RATING_PROTOCOL.md §9;
  vs a credible pool with documented methodology, pinned opponents, paired openings, ≥2 independent
  confirmation batches with ≥2,000 games per anchor per batch, preregistered) is NOT measured and
  NOT met. Nothing may be claimed otherwise.**
- Blocker (exact, UPDATED 2026-11-14 late): the sandbox still cannot reach computerchess.org.uk, but
  GitHub-hosted runners CAN — `anchor-research.yml` has now captured the official CCRL 40/15 list
  (URL `https://computerchess.org.uk/4040/rating_list_all.html`, retrieved 2026-11-14T10:49:28Z,
  HTTP 200, 3,912,738 bytes, SHA-256 `ce365c55b2869502de6addeada4c261d3bd2f50a5a9aef484db9f571aabe15f0`;
  4,873 parsed rows; November 13, 2026 update; "Bayeselo" computed; **published errors are 95%
  confidence intervals** → anchor-pool `error_convention: ci95`). What remains external: (a) selecting
  ≥3 eligible anchors whose EXACT listed versions have legally downloadable binaries (open-source
  candidates mapped: akimbo 0.1.1=2441±19, Topple 0.2.1=2439±14, WyldChess 1.2=2445±21, Halogen 6=
  2441±23, Counter 1.2=2447±14, CT800 1.42=2441±23, Cheese 1.4=2448±17, Kimbo 0.3.0=2439±17 — all
  CCRL 40/15 Nov 13 2026; GitHub homes+licenses resolved via API), plus BELOW-2200 anchors (lower-band
  extraction in progress) so the pool brackets 2,000; (b) the match execution at scale (thousands of
  40/15-class games — GitHub Actions shards per rating-run.yml; local 2-vCPU screening cannot); (c) the
  hardware calibration (Stockfish 10 bench procedure → i7-4770k equivalence) before confirmatory runs.
- Pre-registered protocol for when the gate IS executed: `docs/RATING_PROTOCOL.md` §9.
- Next actions for the gate (in priority order): (1) finish anchor vetting: exact-version binary
  acquisition + SHA-256 + license verification on hosted runners (anchor-research → anchor-verify);
  fill `benches/anchor-pool.json` (NEVER the template) with verified values incl. ci95 conventions;
  (2) run null-control + pilot shards via rating-run.yml to measure throughput and TC equivalence;
  (3) preregister + freeze Batch A/B schedules; (4) execute ≥2 confirmation batches × ≥2,000 games
  per anchor (60×17×2 shards); (5) rating-gate must pass with all three lower bounds > 2,000;
  (6) publish raw evidence + stats; only then evaluate v1.0.0 authorization.

## Reviews (per-reviewer state, head SHA at time of record)

Current head: see `git log --oneline -1`. PR #1 is OPEN, unmerged, **Draft** (converted 2026-11-14).

| Reviewer | State | Notes |
|----------|-------|-------|
| CodeRabbit | **Not re-run on current `main` HEAD.** Last substantive review 5903125228 (13/13 dispositioned) was at PR #1 branch head `f07c4633`/e769d9a, before PRs #1–#5 were merged into `main` (`6ab5b33`). Push-triggered reviews are DISABLED for this OSS repo ("manual review required for this OSS repository"); `@coderabbitai resume` was posted 2026-11-14T09:47Z but the service is rate limited. No review pass may be claimed on the exact current `main` SHA until a reviewer completes there. | REVIEW: do not claim pass before a reviewer completes on `6ab5b33` (or the iteration's final HEAD). |
| GitHub Copilot | BLOCKED | quota insufficient at default effort (2026-11-14). API re-request rejected (`422: not a collaborator`). No findings recorded. |
| Codex | RATE_LIMITED | documented retry attempted 2026-11-14T05:47Z → usage limit; no findings available. |
| Qodo | BLOCKED | trial ended (billing-blocked, 2026-11-14). No code findings. |
| Kilo | BLOCKED | account out of credits (2026-11-14). No code findings. |

Review policy: a reviewer FINISHED only when the service actually completes and findings are dispositioned.

> **PR #1 status (corrected).** PR #1 ("Flawless V1 checkpoint: identity + correctness audit + CI",
> branch `arena/b756c5f1-…`) is **MERGED** into `main` (`6ab5b33`). It is NOT open and NOT draft.
> The earlier "open, unmerged, draft=true" statement in this file is stale and superseded by the
> merge. PR #1 remains open+unmerged only as a historical record; it must not be re-opened or
> re-merged here.

## CHECKPOINT — 2026-11-14T15:10Z (pre-waiting-boundary)

- HEAD `f2176b6` (branch arena/b756c5f1-…, PR #1 open/draft, mergeable).
- Completed this segment: rating-run marker-dispatch mechanism (revs 1–6) + fixes
  (config double-encoding; --white-cmd word-split; top-commit marker gate); PILOT-1
  dispatched + 2 harness defects found/fixed pre-game; runner engine hash frozen
  `fd75726d…` (2 reproducible builds); both null controls REGISTERED + dispatched;
  5 CodeRabbit threads dispositioned + resolved (uci.rs:433 stress regression added);
  estimator key-matching fix (pool names non-unique) + 4 tests (suite 50/50, match 104/104,
  rust 34); aggregate mixed-hardware policy; evidence job + evidence-bridge workflows.
- In flight (server-side): pilot 43602273258 + dup 43603558950 (4+4 games); CTRL-2
  43603826611 (240 games, shards running); CTRL-1 43604654709 (240 games, queued).
  In-flight runs predate the evidence job -> collect via evidence-bridge after completion.
- Next exact actions: (1) poll runs to completion; (2) dispatch evidence-bridge
  (benches/evidence-request.json: 43602273258->pilot, 43603558950->pilot-dup,
  43603826611->control, 43604654709->control); (3) evaluate controls vs fixed thresholds
  (±75 Elo; 0.5 in 95% binomial CI) + pilot throughput; (4) preregister Batch A/B
  (2,040 games/anchor, engine hash fd75726d…, suites hashes frozen, seeds fixed);
  (5) dispatch batches progressively; (6) aggregate + rating_estimator gate (all three
  unrounded lower bounds > 2000); (7) §4 audit finish + fresh CodeRabbit at final SHA;
  (8) MERGE_READINESS + final audit + "Is this complete?".
- Missing evidence: pilot results; CTRL-1/CTRL-2 results; batch A/B games + CIs;
  fresh final-head CodeRabbit review; final full CI on final SHA.

## CHECKPOINT — 2026-11-15T07:00Z (SCREEN-2 in flight; workspace restore #6 session)

- HEAD `c24020b9` on `arena/b756c5f1-asilzkkbatwabaieokwvfotrsioiij` (PR #1 open/draft/unmerged — verified).
- Completed this segment (all committed):
  1. Evidence pipeline: detached-HEAD push defect FIXED in evidence-bridge.yml + rating-run
     evidence job (explicit refspec HEAD:refs/heads/$BRANCH, arena-branch safeguard, verified
     rebase-retry, bridge aggregate mirror); regression suite scripts/test_evidence_push.sh
     10/10; HOSTED VERIFICATION: evidence-bridge rev 3 run **43683839993 SUCCESS** — pilot,
     pilot-dup, CTRL-1, CTRL-2 evidence committed to the branch (2ec762e).
  2. Evidence recovery COMPLETE: all six datasets committed under benches/evidence/
     (pilot, pilot-dup, control/flawless-self, control/topple-0.1.1-vs-topple-0.2.1,
     screening/topple-0.1.1, screening/topple-0.2.1); every dataset independently
     re-aggregated from original run artifacts = committed bytes (hashes in AGENTS_LOG).
  3. Evaluations: pilot throughput 29.43/29.53 min/game; CTRL-1 PASS (−125.32 vs −115 → err
     −10.3 ≤ 75); CTRL-2 PASS after estimator metric fix (self-match must measure the SEAT
     perspective via recorded color_pair; focus matching case-insensitive; suite 65/65;
     threshold unchanged): 0.5146, CI [0.4792, 0.5500].
  4. SCREENING-1/2 evaluated per the registered rule: est ≈ 1632 Elo (scores 0.0208/0.0083);
     selection rule yields only wowl-1.3.7 non-saturating → Batch A/B DEFERRED (a doomed
     ~300-runner-hour campaign was NOT dispatched; compute not wasted).
  5. Root cause: ~95% of rating losses are FLAG FALLS; src/uci.rs clock_limits overspend
     (soft clamp 20–30_000 ms; hard=6×soft). ENGINE-1 reserve-bearing budget REGISTERED then
     implemented; cargo 35/35, fmt/clippy clean, test_match 104/104, estimator 65/65; bench
     signature UNCHANGED fc907eba40b7869f.
- IN FLIGHT (server-side, GitHub Actions): SCREEN-2 re-screening of the ENGINE-1 candidate —
  rev 9 run **43685671431** (vs topple-0.1.1, seed 20261123) + rev 10 run **43686056730**
  (vs topple-0.2.1, seed 20261124); 15 shards × 8 games each at 40/15; engine_sha256 "freeze"
  (runner build records the new candidate hash); expected wall time ≈ 4–9 h; the evidence job
  (fixed push path) auto-commits benches/evidence/screening-2/<anchor>/ when all 15 shards of
  a run succeed.
- Next exact actions (resume procedure):
  1. `git fetch && git log --oneline -5` — expect 2 evidence commits (screening-2 dirs) after
     the runs complete; verify run conclusions + artifacts (both runs must be SUCCESS).
  2. Verify each screening-2 dataset: strict re-aggregation from the 15 shard artifacts,
     byte-compare vs committed; check flag rate ≤ 10/120 (ENGINE-1 acceptance 4); measure the
     freeze hash from manifests and PIN it in PREREGISTRATION (SCREEN-2 result section).
  3. Evaluate: d̂ per anchor; est = mean(R_a + d̂_a); re-apply the UNCHANGED selection rule.
  4. If ≥3 non-saturating anchors: commit benches/gate-plan.json (rule-derived set + documented
     span interpretation) with the Batch A dispatch revision BEFORE any batch game; update
     dispatch.json (confirmatory, pinned hash, seeds 20261121/20261122, 255 shards × 8,
     suites batchA/batchB); dispatch Batch A then B progressively; re-run CTRL-2 self-match
     with the new binary (registered decision — see ENGINE-1 acceptance notes) before the gate.
  5. If still no compliant set: continue the §8 improvement cycle (next most promising
     independently testable improvement; do not tune to the screening outcome).
  6. Fresh CodeRabbit review at the exact final SHA; CI green there; final manifest.
- Missing evidence: SCREEN-2 results (in flight); new-candidate controls (CTRL-2 re-run with
  the new binary registered as pre-gate requirement); Batch A/B games + CIs; fresh final-SHA
  CodeRabbit review; final full CI.
## Execution state (2026-11-16, segment 22)

- **SCREEN-2R COMPLETE (VERIFIED PASS):** both anchors' 120-game canonical evidence committed
  (topple-0.1.1 via run 43714600687; topple-0.2.1 via merged runs 43714620645+43806800011,
  evidence commit 0cdeedf). Byte-match verified via BOTH download paths; flag losses 0/120
  and 0/120 (acceptance <=10 PASS); 0 engine errors; engine hash = pinned 9663697d... in
  every shard manifest. Corrected screening estimates (after the draw-scoring reporting fix,
  see FAILURE_LEDGER 2026-11-16 ~07:25Z): 2176.8 (topple-0.1.1) and 2236.4 (topple-0.2.1);
  combined est 2206.6 — SELECTION-ONLY, not a rating claim.
- **In flight (server-side):** CTRL-2-R rev 13 = run 43820392119 (self-match, flawless vs
  flawless, 120 shards x 2, seed 20261125; evidence -> benches/evidence/control/flawless-self-r/);
  SCREEN-3 rev 14 = run 43820645420 (akimbo-0.1.1, mechanical anchor choice |est-R|=234.4
  minimum, 60 shards x 2, seed 20261126; evidence -> benches/evidence/screening-3/akimbo-0.1.1/).
- **Gate tooling audited vs RATING_PROTOCOL §9 (VERIFIED PASS):** rating_estimator.py joint
  cluster bootstrap / sigma_matched-as-SD / GLS / shared-calibration batch combination;
  verify_evidence.py identity+count fail-closed; rating-gate.yml strictly->2000 decision on
  all three unrounded CI lower bounds; GLS fallback fails the gate by design.
- **NOT yet done (binary):** CTRL-2-R result; SCREEN-3 result; gate-plan.json commit; Batch A
  revs 15-18; Batch B revs 19-22; merge+verify; 2000 gate; audit closeout; final CodeRabbit
  review at final SHA; final CI matrix; Ready-for-review flip.

## 2026-11-17 — first hosted validation and follow-up

The first PR CI at `7d368cd` passed the Rust 1.80 MSRV job; Linux and Windows stopped at rustfmt in the newly added SEE helpers before tests. The formatter layout has been corrected. Anchor verification recorded the new deterministic depth-10 signature `141943aa23b3fc68`; its expected value has been updated, but the new candidate binary SHA-256 remains pending a successful verification rerun. The rating gate failed closed due to no gate plan, and rating-run skipped all shard jobs; no tournament was dispatched.

## 2026-11-17T10:31Z — validation checkpoint

- Current HEAD at checkpoint: fe6d34067e776ca64e676617c2102966675b4744 (PR open, draft, not merged).
- New RATING-100 selector verifier failure on CI run 44062359630 is contained: both operating systems passed Rust formatting, clippy, Rust unit tests and the Python regression suites, then failed at the exact deterministic opening-subset check. The suite-generator SHA-256 constant defect was fixed; corrected suite hashes are recorded in PREREGISTRATION.md and the machine report. Hosted verification on the corrected commit is pending.
- ENGINE-2 SEE ordering candidate: hosted PR merge-tree bench signature 141943aa23b3fc68, binary SHA-256 168dc0ab22749f8dc7a6be5248cd7426f9f2bfd3fda8077bc6218959ad6e41d7. This is a deterministic build identity, not an Elo, speedup or playing-strength result.
- RATING-100 remains BLOCKED. The rating gate failed closed because no gate plan/evidence exists; no confirmatory batch was launched.


## 2026-11-17 — exact-head build validation

At commit 5b63e273d77cfb097f0ad73bc28dda05cc19adad, hosted CI run 44066217195 passed on Ubuntu, Windows and Rust 1.80. The amended opening-suite verifier, Python harness/estimator/reduced-sample/dispatch-recovery tests, power-model smoke and engine release/UCI/perft checks all passed. Anchor-verification run 44066217113 succeeded 13/13; the exact source tree built binary SHA-256 168dc0ab22749f8dc7a6be5248cd7426f9f2bfd3fda8077bc6218959ad6e41d7 with bench signature 141943aa23b3fc68.

The RATING-100 power file is sourced from ENGINE-1 SHA-256 9663697da62e33229d516af3681c442e268287c59d6b97ff2cd13256b564d428. New manifest and dispatch guards prevent its reuse for ENGINE-2. ENGINE-2 has an identified binary, but its own screening and controls have not been run. RATING-100 remains BLOCKED and no confirmatory games have been dispatched.

## 2026-11-17T10:43Z — provenance guard validation correction

Commit 29b627e added ENGINE-1/ENGINE-2 binary isolation for RATING-100. The first CI rerun caught a regression-test expectation mismatch: an unknown engine hash is rejected by the explicit SCREEN-2 allowlist before the same-binary comparison. Production behavior is the intended stricter fail-closed result; the test expectation is being corrected. The commit is not yet CI-green. Anchor verification 44067364568 remains successful, and no tournament ran.

## 2026-11-17T10:47Z — Windows hash portability correction

CI on c564c5c passed Ubuntu but failed the Windows power-analysis smoke because Windows Git checkout changed raw SCREEN-2 JSONL line endings to CRLF while manifest merged_sha256 was created on Linux LF bytes. The next commit makes hash verification OS-independent by canonicalizing line endings only, retaining the exact JSONL records, and adds tamper/CRLF regression tests. The c564c5 CI run is not green; exact-head rerun pending.

## Session update 2026-11-17 (manual review fixes)

- PR head (code): `071f875`. Commits this session: `5980d53` (R-02, R-12), `81ad551` (R-03, R-10), `1ec9eeb` (R-07), `b39df4e` (R-08), `071f875` (R-05 tests).
- Manual review disposition: `REVIEW_MANUAL_071f875.md`. Of 15 findings: 7 fixed, 4 not reproduced, 4 accepted (unchanged).
- Gates at head: fmt clean, clippy `-D warnings` clean, 45/45 tests (+2 R-05 tests), DIFTEST default 2,321 positions 0 mismatches, perft subset exact, bench signature `141943aa23b3fc68` unchanged.
- Preliminary Elo (internal, not gate evidence): NOT MEASURED this session. No match runs were executed.
- Open: MSRV 1.80 unverified; ENGINE-1 hash no longer matches the code (decision needed); rating-gate fail-closed cause not investigated; R-08 residual overrun.

## 2026-11-19 — UCI no-argument startup compatibility

- Trigger: user diagnostic bundle `diagnostic-report.zip` (CrispChess Extended 2.3.2-dev6+23, Windows 10 LTSC): engine `flawlessv1 patch2.exe` failed with `exited while searching (exit code 2)` and usage text on stderr.
- Root cause: `src/main.rs` treated a missing argument as an error. Fix: no arguments now run `flawless::uci::run_uci()`; `-h`/`--help` are explicit help. `uci` and all CLI subcommands are unchanged.
- Verification at the implementation commit (local, Linux, Rust 1.99.0): fmt, clippy `-D warnings`, `cargo test --release --locked` all green (11 uci_smoke tests incl. 3 new no-argument tests); perft(3)=8902; bench signature `141943aa23b3fc68` before and after (unchanged).
- Not verified locally: Rust 1.80 MSRV compile (no 1.80 toolchain obtainable in this sandbox; delegated to the CI `msrv` job), Windows execution (delegated to CI `windows-latest` and `windows-x64-artifact`). CI results in `docs/audit/2026-11-19-uci-no-args-compatibility.md` are historical, recorded through `07b68a8`. Current-head evidence (through `c64b743`, run 44700737123) is in `docs/audit/2026-11-19-v0.1.0-release-candidate.md`.
- Side effect: the engine binary changed, so previously registered ENGINE-2 binary hashes no longer identify this build. No rating gate, dispatch or power-report status changed; RATING-100 remains BLOCKED and V1 is NOT complete.

## 2026-11-19 — v0.1.0 pre-V1 release candidate (status update)

- Version `0.1.0` (pre-V1; not v1.0.0; not tagged; no release). Product: FlawLessChess. UCI name: Flawless. Cargo package: `flawless` (kept; the naming decision is made: the package stays `flawless` (user decision), see the release-candidate report).
- Fixed: `go movetime N` early return (search stopped at 39–100% of N). Now 100–101% of N. Clock searches unchanged. Tests: `tests/movetime_smoke.rs`.
- Verified locally on the candidate head: fmt, clippy `-D warnings`, `cargo test --release --locked` (all suites), release build, bench signature `141943aa23b3fc68` (unchanged), perft d3 8902 / d4 197281, diftest 2,321/0, six full games with python-chess referee (all legal), UCI protocol probes 10/10, malformed input 37/37, Python harness suites.
- Not verified: Windows artifact bytes (SHA-256, PE machine, manifest) by hand; real GUI playability in Arena or Cute Chess; independent AI review; MSRV 1.80 on the new head (depends on CI).
- Release gates: see `docs/audit/2026-11-19-v0.1.0-release-candidate.md`. The V1 rating gate remains NOT MET and does not apply to a pre-V1 claim.

## 2026-11-24 — current session (branch arena/247fe7df-flawlesschess at `4038b75`, PR #6 draft)

Toolchain recovered from npm `@toolchain-bin/*` 1.99.0 pins into `/home/user/.toolchain/sysroot` (static.rust-lang.org unreachable; crates.io unreachable). Python venv with python-chess 1.11.2 at `/home/user/.venv`.

### Changes implemented

1. **Time management** (src/search.rs): removed the predictive-overrun early stop that halted searches well before the soft budget on clock-based time controls. At 10 s the engine previously stopped at 116 ms of a 234 ms soft budget (depth 9); it now runs to depth 10 at ~253 ms. At 1 min it reaches depth 12 at ~1.65 s. Hard budget still caps worst-case overspend; fixed-depth/movetime searches unaffected (bench signature unchanged).

2. **Counter move heuristic** (src/search.rs, HIST-1 from PR #2 audit): when a quiet move causes a fail-high cutoff in reply to the opponent's previous move, store it as a counter move. Ordered just above killers (92,000) and below good captures. Counter table cleared each root search like killers/history; not used in null-move search or quiescence.

3. **Space evaluation** (src/eval.rs, src/main.rs, EVAL-2 from PR #2 audit): reward control of important squares weighted by centrality (centre squares weighted most). Colour-symmetric via square mirroring (sq ^ 56). Tapered: full weight in middlegame, half in endgame. Added `space` field to `EvalBreakdown` and CLI `eval` output.

### Validation (local, this sandbox)

- `cargo fmt --all -- --check`: clean
- `cargo clippy --release --all-targets -- -D warnings`: clean
- `cargo test --release`: **172/172 passed** (49 lib + 3 cli_batch + 3 cli_divide + 3 clock_smoke + 43 correctness + 12 movetime_smoke + 51 protocol_regressions + 11 uci_smoke)
- `scripts/diftest.py`: **2,321 positions d=2, 0 mismatches** (python-chess oracle)
- `./target/release/flawless perft 6`: **119,060,324** (matches CPW reference)
- `./target/release/flawless bench`: signature **141943aa23b3fc68** (unchanged from pre-change baseline)
- `scripts/test_match.py`: **111/111 passed**
- `scripts/test_rating_estimator.py`: 65/65 checks pass; null control FAIL is pre-existing (anchor/environment issue, not engine-related)

### Not done

- Absolute rating: UNKNOWN / NOT MET (V1 gate requires >2,000 with 95% CI lower bound strictly >2,000)
- Fresh CodeRabbit review at final SHA: not yet performed
- MSRV 1.80 compile: not locally verifiable (no 1.80 toolchain obtainable; delegated to CI)
- Windows execution: not locally verifiable (delegated to CI)
- Continuation history (remaining HIST-1 element): not yet implemented
- Outpost/other evaluation terms (remaining EVAL-2 elements): not yet implemented
- PR #2 (open, draft, conflicting): NOT merged, NOT cherry-picked, NOT touched

## 2026-11-24 — outpost correction, tempo semantics, ablation switch, paired benchmark (PR #6 draft)

Toolchain recovered again from the npm `@toolchain-bin/*` 1.99.0 pins into `/home/user/.toolchain/sysroot`
(rustc 1.99.0, cargo 1.99.0, rustfmt 1.10.0, clippy 0.1.99; `static.rust-lang.org`, `crates.io` and the
Actions log host are unreachable from this sandbox). Python venv with python-chess 1.11.2 at `/home/user/.venv`.
The Actions log host being blocked is why CI failures are surfaced through annotations and why the benchmark
summary is published to a pull request comment.

### Changes implemented

1. **Outpost evaluation corrected (src/eval.rs, EVAL-2).** The zone is now the classical one: White outposts
   are on ranks 5-6, Black outposts on ranks 3-4, files b-g. The previous zone (ranks 5-8 / 1-4) included the
   opponent's back rank and the rank in front of it, where no enemy pawn can ever stand; "cannot be attacked
   by an enemy pawn" held vacuously there, so any piece deep in enemy territory scored as an outpost. Values
   unchanged (knight +30 mg / +15 eg, bishop +15 mg / +8 eg).
   The audit of PR #2 (see below) then showed that the term was still missing two classical conditions, which
   are now implemented: the square must be **defended by one of our own pawns** (otherwise the piece is simply
   chased away), and no enemy pawn may be able to **step forward** and attack the square (the push is only
   blocked by one of our own pieces). Both directions are pinned by regression tests, and the 13 test
   position pairs were generated and verified with python-chess instead of being written by hand.
2. **Tempo semantics made explicit and pinned by a test (src/eval.rs, tests/correctness.rs).** The score is
   now computed as `relative = if side == WHITE { tapered } else { -tapered }; total = relative + TEMPO`. The
   previous single expression depended on how `+` binds to an `if` expression; that binding was checked
   against the rustc parser (the statement-expression restriction only applies in statement position, so the
   tempo was applied to both colours) and the behaviour is now pinned by the pre-existing 303-pair colour
   symmetry test plus a new dedicated test. `EvalBreakdown` additionally exposes `mg`, `eg` and `phase`.
3. **Ablation switch (src/ablation.rs, docs/ABLATIONS.md).** `FLAWLESS_ABLATE=space,counter_move,outpost`
   disables the listed terms for the process. Off by default, read once, applied as a bit mask. The pinned
   baseline predates the module and ignores the variable, so both engines of a benchmark can share the
   environment.
4. **Benchmark harness and workflow (scripts/, .github/workflows/relative-benchmark.yml).** The quick profile
   runs on every pull request of PR #6; the extended profile runs three replicates of 100 paired openings and
   aggregates them with an opening-clustered bootstrap. `scripts/match.py` propagates an explicit thread count
   and records schedule and replay metadata per game. Summaries are published to the job summary and to a
   pull request comment because the artifact host is not reachable from this sandbox.

### Validation (local, this sandbox, toolchain 1.99.0)

- `cargo fmt --all -- --check`: clean
- `cargo clippy --release --all-targets -- -D warnings`: clean
- `cargo test --release --locked`: **183/183 passed** (55 lib + 3 cli_batch + 3 cli_divide + 3 clock_smoke +
  45 correctness + 12 movetime_smoke + 51 protocol_regressions + 11 uci_smoke)
- `scripts/diftest.py --games 300 --seed 1234`: **2,321 positions d=2, 0 mismatches** (DIFTEST PASSED)
- `./target/release/flawless perft 6`: **119,060,324** (matches the CPW reference)
- `./target/release/flawless bench`: signature **141943aa23b3fc68**, identical to the pinned baseline
  `6ab5b33` on the same machine and stable over three runs. The signature covers the chosen moves, and with
  the refined definition none of the twelve bench positions contains a pawn-defended outpost square, so the
  outpost term contributes nothing there. The earlier, looser definition changed the signature to
  `ce6a84301216fadd`; the refinement restores it.
- `scripts/test_match.py`: **112/112 passed**; `scripts/test_relative_benchmark.py`: **20/20 passed**

### Relative benchmark evidence (screening only)

- **Extended profile, hosted CI, 3 replicates, 600 real UCI games** (candidate vs pinned baseline `6ab5b33`,
  100 paired openings per replicate, seeds 20261124/20261125/20261126, movetime 100 ms, hash 64 MB, one
  thread): **217 W / 164 D / 219 L**, score 299.0/600 = **49.8%**, relative Elo **-23.2 to +21.5**
  (95% CI, opening-clustered percentile bootstrap). Classification **INCONCLUSIVE**, `valid: true`.
  **No strength difference is measurable against the pinned baseline.**
- Quick profile, hosted CI, 40 games each on two consecutive heads: **9/14/17 (40.0%)** and **11/12/17
  (42.5%)**, both INCONCLUSIVE. A local run of the same profile scored 24/6/10 (67.5%). The spread across
  identical profiles is the important finding: at a fixed 100 ms movetime the played games depend on the
  machine speed and the timing jitter, so the games are **not** reproducible across machines even with the
  same seed, and a 40-game profile is dominated by noise. The 600-game profile is the meaningful one.
- Every one of these is a fixed-movetime screening comparison against a single opponent. None of them is an
  official or absolute rating, and none of them is a strength claim.

### PR #2 audit (read only, PR #2 untouched)

PR #2 (`arena/8259ce1c-flawlesschess`, head `5f952b1`, draft, conflicting with `main`) diverged from
`main` at `5e36b06` and carries 49 commits and 12,971 insertions across 66 files. It is **not** merged,
cherry-picked or modified. The audit found:

- **Overlap:** PR #2 also implements an outpost term, plus continuation/counter/capture history, a fast
  legality filter and a large rating-harness expansion. The space evaluation and the counter-move heuristic
  of this PR were taken from PR #2's ideas earlier and are reimplemented here independently.
- **Technical finding, acted upon here:** PR #2's outpost term requires the square to be defended by one of
  our own pawns and to be safe from an enemy pawn that can also step forward to attack it. This PR's term
  had neither condition and rewarded an undefended piece. The two classical conditions were ported into
  this PR's own implementation (not PR #2's code) and are covered by regression tests.
- **Technical finding, not acted upon:** PR #2's zone is "rank 4 or beyond for White", which includes the
  4th rank — White's own half — and its outpost value is a flat +16 mg / +8 eg for knight and bishop.
  This PR keeps its explicit zone (White ranks 5-6, Black ranks 3-4) and differentiated values
  (knight +30/+15, bishop +15/+8).
- **Not comparable:** PR #2's own screening results are recorded as INCONCLUSIVE for its evaluation and
  search work, and its branch is in conflict with `main`. Porting its fast legality filter or its
  continuation/capture history would need its own measurement and is out of scope for this iteration.

### Not done

- Absolute rating: **UNKNOWN / NOT MEASURED / NOT MET** (the V1 gate needs >2,000 with a 95% lower bound
  strictly above 2,000 against a defined anchor pool and time control; nothing here measures that).
- Fresh independent review at the final head SHA: not performed in this session.
- PR #2 (open, draft, conflicting): NOT merged, NOT cherry-picked, NOT touched.
