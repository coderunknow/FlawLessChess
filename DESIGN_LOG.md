# DESIGN_LOG.md (append-only)

## 2026-11-14 — Phase 0/1 kickoff

- Verified repository state: starting commit `98b1a00` ("Initial commit"), tree contains only `LICENSE`
  (Apache-2.0). Branch `arena/b756c5f1-asilzkkbatwabaieokwvfotrsioiij`. No tags, no workflows, no other branches.
- Environment: crates.io + static.rust-lang.org unreachable → zero-dependency Rust, toolchain from npm
  `@toolchain-bin/*` (see `docs/ENVIRONMENT.md`).
- Decisions: bitboards + startup-generated magic sliders (ADR-0001); pseudo-legal movegen with
  make/unmake legality filter; single-threaded V1 with future-SMP-safe encapsulation; NNUE deferred
  behind classical baseline; honest `Threads max 1`.
- Risks recorded: (1) rating gate unlikely to be measurable in this sandbox; will report INCONCLUSIVE
  rather than claim pass. (2) Toolchain provenance: npm redistribution of official binaries, checksums
  recorded in ENVIRONMENT.md.

## 2026-11-14 — Phase 3/4/UCI checkpoint (search + evaluation + UCI)

- Decisions: classical tapered eval first (MG/EG PSTs, mobility baselines, bishop pair, king-zone,
  tempo=12 cp); NNUE deliberately NOT built yet (no measured win, no teacher pipeline).
- TT: Zobrist 8-byte entries, power-of-two, generation aging, ply-relative mate scores, TT-move
  extraction for PV recovery (no separate PV array).
- Search: ID + aspiration (depth ≥ 6, ±25 initial, widen ×3+20) + PVS + quiescence (delta 200,
  MVV-LVA) + null-move (depth ≥ 3, non-PV, beta < MATE_BOUND, non-pawn material) + futility
  (depth ≤ 2) + LMR (r = ln d · ln n · 0.6, re-search on fail-high) + killers/history.
  Repetition (2-fold path), 50-move, insufficient material are draws inside search; no-legal-moves
  handled for mate/stalemate.
- UCI: single worker thread; `go` returns immediately; `stop` sets AtomicBool and joins; bestmove
  printed by the worker so it appears even without further stdin commands (fixed — previously
  bestmove was only printed on the next stdin line / EOF, violating the UCI protocol).
- Abort safety: root scores after an abort are discarded; mate scores reported only for genuinely
  mate-bounded |score| ≥ MATE_SCORE−100 (clamped otherwise).
- UCI smoke: depth-limited search on Kiwipete (FEN r3k2r/...) reaches depth 8–10 with MultiPV 3;
  mate-in-1 FEN (6k1/8/6K1/8/8/8/8/1Q6 w - - 0 1) → `bestmove b1b8` at any depth; ~0.9M nps
  single-threaded in sandbox.
- Known gaps (honest): no strength measurement yet; no match/CI; `Threads` hard-capped at 1;
  UCI not fuzzed; see STATUS.md / FAILURE_LEDGER.md (no rating claims).

## 2026-11-14 — First strength probes + CI + match infrastructure

- GitHub Actions CI (Windows+Linux: fmt, clippy -D warnings, release tests, release build, UCI
  handshake, perft d3) — green on PR #1. Kilo review bot fails (insufficient account credits);
  not a code verdict.
- Match infrastructure implemented (`scripts/match.py`, `scripts/stats.py`); 20 verified openings;
  paired games with color reversal; opening-clustered bootstrap 95% CIs.
- Two engine bugs found by benchmarking and fixed: (1) LMR table out-of-bounds panic at depth 64 /
  move-count 64+ (thread died, GUI starved → timeout loss); (2) no fallback bestmove on thread
  panic (worker now wraps search in catch_unwind and emits legal fallback; main thread rebuilds TT).
- Probes vs pinned Stockfish 19 WASM (movetime 100 ms): SF Skill 0 → 40/40 wins (checkmates);
  SF Skill 5 → 11/13/16 (≈ −44 Elo diff); SF Skill 10 → 1/7/32 (≈ −359). Engine is between
  pinned Skill 5 and Skill 10; far from any 2000-Elo gate; results are in-sandbox internal
  estimates only, never to be presented as official ratings.
- NNUE still NOT built; classical eval unchanged pending measured need.

## 2026-11-14 — Search strength experiment: reverse futility pruning + check extensions

- Change (src/search.rs): (1) reverse futility pruning at depth ≤ 3, non-PV, not in check,
  mate-bound-safe (s − 150·depth ≥ beta → fail high); (2) check extension — when in check, child
  searches are made at depth−1+1 instead of depth−1.
- Correctness re-verified: fmt/clippy −D warnings/tests 18/18/diftest PASSED.
- bench signature changed a7a9f01893e9f1a5 → d790483532d87af0 (2,798,466 nodes @ depth 10) — expected.
- A/B (benches/ab-004-rfp-checkext, 40 paired games vs the previous build at movetime 50 ms):
  ours-rfp-cext 18 W / 13 D / 9 L vs ours-before → score 0.613, opening-clustered 95% bootstrap CI
  [0.487, 0.725], logistic Elo diff +80 (CI [−9, +168]). Positive direction; NOT conclusive at this
  sample size/TC; lesson: treat as directional only, keep change since standard and safe, verify
  no correctness regressions (all gates pass).

## 2026-11-14 — Identity migration to Flawless

- Engine public identity migrated from ASILZKKBATWABAIEOKWVFOTRSIOIIJOAZPODB to Flawless (user
  decision; repo now exists as `coderunknow/Flawless-Chess-Engine`, old name auto-redirects).
- Package/library/binary renamed to `flawless`; `flawless::` crate paths; `id name Flawless`;
  `id author coderunknow (Apache-2.0)` keeps authorship (not the product name).
- ADR-0002 recorded. Historical benchmark artifacts/PGNs/append-only logs NOT rewritten (old name
  retained there deliberately). Branch name unchanged (mission: do not rename existing branch).
- Verified: build OK, UCI id line reports Flawless, 18/18 tests pass.

## 2026-11-14 — Audit pass 1: terminal/draw precedence + panic-fallback plumbing

Defects found and fixed (all reproduced by failing→passing tests in tests/correctness.rs):

1. `search()` returned `DRAW_SCORE` for repetition/fifty-move nodes BEFORE detecting checkmate —
   a mated position at halfmove ≥ 100 (or reached off a repeating path) scored as a draw.
   Fix: insufficient-material remains an immediate draw (FIDE dead position); repetition/fifty-move
   shortcuts now require `!in_check`; the no-legal-moves terminal check runs BEFORE null-move/
   futility/RFP and scores mate as -MATE+ply (mate precedence, FIDE 9.6.2). Stalemate → DRAW_SCORE.
2. `quiesce()` applied the stand-pat beta cutoff and delta pruning BEFORE the terminal check —
   a stalemate qsearch node could return a fail-high (beta) or a bogus upper bound (alpha).
   Fix: generate legal moves first; terminal check before any stand-pat cutoff.
3. Reverse futility pruning could fire on a terminal (stalemate) node returning `beta` — now
   unreachable (terminal check precedes RFP).
4. `go searchmoves X` was silently ignored by the MultiPV=1 search path (root restriction was
   only applied to the MultiPV>1 enumeration, not to the PVS main line). Fix: root filter applied
   at ply 0 inside `search()` via a `root_moves` field on `Searcher`; `go searchmoves` with an
   empty move list now falls back to all legal moves instead of emitting `bestmove 0000`.
5. Panic fallback (search thread dies): engine now emits a GUI-visible
   `info string search thread panicked; emitting fallback bestmove` on stdout; match.py detects it,
   tags the game `engine_error=true` with `engine_error_turns`; stats.py excludes such games from
   statistics unless `--include-engine-error` is passed. Previously the fallback was invisible
   (marker went to stderr, which match.py devnull'd) so panicking games were counted as normal.
6. CI: removed remaining `|| true` masks on smoke steps; added a UCI bestmove smoke (depth 2) and
   an MSRV (Rust 1.80) job; Windows + Linux both run smoke tests at runtime.

Consequences:
- bench signature changed d790483532d87af0 → 3086f65159758c9d (2,317,474 nodes): positions 4/6/7
  PVs shifted after the unsound-pruning removal and mate-precedence fix (deterministic per build).
- 24/24 tests incl. 6 new audit regressions. DIFTEST (perft d=2, 2321 positions): 0 mismatches.
- The bench change is a correctness consequence, NOT an optimization; no strength gain claimed.

## 2026-11-14 — CodeRabbit 13a316e findings addressed + sandbox restore survival incident

Context: workspace restore (~07:43Z) wiped `target/`, the entire Rust toolchain
(`/home/user/.toolchain`, `.rustup`, `.cargo`) and the Python venv (`python-chess`). Only the repo
(excluding `target/`) and a base-only `.git` pack survived.

Recovery (no data lost from history — remote is authoritative):
- `.git` objects for the branch were missing locally; `git fetch origin` restored them (tip
  `13a316e` verified). Uncommitted source fixes on disk were preserved and re-applied.
- Toolchain is unrecoverable offline (static.rust-lang.org unreachable; npm `rustc@1.74.0` too old
  for `std::sync::LazyLock`/MSRV 1.80 semantics). Local builds are IMPOSSIBLE until a toolchain
  returns; verification moved to (a) CI and (b) a pinned npm WASM rustfmt
  (`rustfmt@0.1.0`, only for files without `let-else`; its `single_line_if_else_max_width` rule = 50).
- Copilot cloud agent ("Agent Merge on PR #1") pushed `6c749d8` "Fix rustfmt CI formatting diffs"
  (co-authored copilot-swe-agent[bot]) with the same two canonical transforms this session derived
  (position.rs if-else expansion; search.rs if-condition collapse). Local duplicate was discarded.
- Bot push does not auto-trigger `pull_request` CI (GITHUB_TOKEN recursion guard) and
  `workflow_dispatch` is 403 for this integration — CI for 6c749d8 was re-triggered by an ordinary
  session push instead. PR remains OPEN, never merged by this project.

Engine/UCI fixes (9548467, 15526ed, 6c749d8):
- FIDE "same position" ep-hash (file included only when an ep capture is actually legal, incl.
  rank-pin probes); unpack FEN validation for ep squares and side-to-move-attacking-king rejection;
  castling emission now requires the king on e1/e8.
- Mate takes precedence over claimable draws; draws honored in check and in qsearch; NOT-in-check
  draw fast path before the TT probe; TT score cutoffs disabled past halfmove ≥ 90; delta pruning
  is per-capture (victim + promotion swing), sound vs the stand_pat<alpha queen-capture example;
  restricted-root (`go searchmoves`) scores never stored as unrestricted TT bounds; root PV head
  comes from an explicit `root_best`.
- `go infinite`/`go ponder`/bare `go`: clock/node abort inert until ponderhit/stop (should_stop_now);
  bestmove printed exactly once per `go`; ponder holds bestmove until ponderhit/stop; ponderhit
  converts to timed search; `bestmove 0000` on NULL; clock caps soft ≤ remaining, hard ∈ [soft, cap].
- match.py: deadline-safe buffered line reader; broken pipes → engine-error losses (never batch
  crashes); full-move-history `position startpos moves ...`; batch artifacts write-fresh-only with
  refusal to overwrite; meta.json records artifact binary path + SHA-256 and git commit.
- stats.py: 0/1 scores are boundary notation, never clamped finite "Elo" (probe-001 +2400 artifact).
- CI: MSRV job explicit RUSTUP_TOOLCHAIN=1.80.0 + --locked; informational bench step (signature may
  be read from run logs). Note bench signature pending re-measurement on this tree — expect it to
  differ from `fc907eba40b7869f` (3,899,001 nodes @ d10, pre-per-capture-delta-pruning measurement).

Process honesty:
- DIFTEST/bench local verification NOT re-run (needs toolchain + venv, both gone) — PENDING.
- Kilo ACTION_REQUIRED remains a billing limitation, not a code issue. CodeRabbit SKIPPED (bot
  auto-skip); its findings are being addressed commit-by-commit regardless.

2026-11-14 (clippy root cause + CI diagnostics channel):
- CI clippy (deny warnings) failed on ubuntu-latest and windows-latest for several pushes with
  no retrievable log (`gh run view --log*`, `gh api .../actions/jobs/<id>/logs`, and
  `gh run download` all EOF against productionresults*.blob.core.windows.net). Root cause was
  isolated by temporarily rewriting the clippy step to `--message-format=json` piped through an
  embedded python3 converter that re-emitted each level=error compiler-message as an `::error>`
  check annotation (plus a raw head/tail dump in `::notice::`/`::error::`); the annotations API
  (`gh api repos/<owner>/<repo>/commits/<sha>/check-runs` + `/check-runs/<id>/annotations` on
  api.github.com) is the only working diagnostics channel this environment has. The converter's
  first run surfaced `error: unexpected argument '-D' found` — the edit had dropped the `--`
  separator before driver args (`cargo clippy -- -D warnings`, not `cargo clippy ... -D warnings`);
  annotations then showed the true error: `src/position.rs:699` `clippy::manual_range_contains`
  (`if f < 0 || f > 7` → `if !(0..=7).contains(&f)`, fixed in 2c777b5). A prior speculative
  `needless_range_loop` fix (da178a6, `legal.iter()`) was real but not the failure.
- With the fix in place the whole workflow is green (msrv, ubuntu-latest, windows-latest, run
  43574593496 on 2c777b5). The temporary clippy scaffold (continue-on-error + tee + artifact
  upload + verdict step) was removed and the plain step restored (cd9b7d9); run 43574700347
  confirms green with the restored simple step. The JSON→annotations converter remains documented
  here for future log-blocked episodes.
- apt-get is unusable (deb.debian.org unreachable, partial lists root-owned); local toolchain
  remains unavailable. CI is the build oracle. Bench signature still requires a real build;
  informational CI bench step remains the channel, but its output is not machine-readable here
  without log access — re-measurement remains PENDING until toolchain or log access returns.

2026-11-14 (workspace restore #3 — full rebuild, all gates re-verified):
- /home/user/.toolchain, .venv, /home/user/opponents, node_modules wiped again; only pushed origin
  state survived. Rebuilt exactly per docs/ENVIRONMENT.md: npm @toolchain-bin pins
  (rustc/cargo 1.99.0, clippy 0.1.99, rustfmt 1.10.0) + `install.sh --prefix` per component +
  execute-bit fix; venv (python-chess 1.11.2); pinned SF 19 WASM reinstalled and SHA-256 verified
  identical to BENCHMARKING.md (ccb130d7…/ee4f115b…); opponents/ mirrored and re-hashed.
- Local verification on the restored tree (first real build since the wipe):
  `cargo test --release --locked` 29/29 green; `cargo fmt --all --check` clean; clippy 1.99.0
  found ONE latent error invisible while CI logs were blocked: tt::store grew to 8 args
  (clippy::too_many_arguments, -D warnings) — fixed by bundling `StoreRequest` (key, best_move,
  score, depth, bound, ply, halfmove); CI failure on db174e4 (ubuntu exit 101 / windows exit 1)
  was exactly this. CodeRabbit review-2 instrumentation was NOT required in the SAME run — the
  local toolchain displaced blind debugging; the temporary diagnostic step remains on the branch
  pending CI green, then returns to the plain step.
- DIFTEST re-run (seed 20261114, 300 games): legal-move sets identical, perft-d2 2295/2295,
  0 mismatches — PASSED. Bench re-measured (db174e4): signature UNCHANGED `fc907eba40b7869f`
  (depth/score/PV stable) with 2,221,199 nodes @ d10 — 43% fewer nodes than the recorded
  3,899,001, i.e. the per-capture delta-pruning rework is active and effective; 8.56 s,
  259,619 nps on 2 vCPU. BENCHMARKING.md updated.
- CodeRabbit review 5903125228 (13 findings) dispositioned: src (null-move ep-hash inclusion,
  in-check draw-before-TT, restricted-root extract_pv confinement, CLOCK-UNSAFE TT entries for
  fifty-move-horizon subtrees, ponderhit/worker flush mutex, smoke-test drain-after-exit),
  scripts (select-free reader thread, launcher+script artifact hashing, O_EXCL batch reservation,
  stats.py boundary endpoints as no-finite-estimate + bootstrap SD), docs (STATUS de-clamp;
  RATING_PROTOCOL Amendment §9: strict > 2,000 gate, both batches + combined must pass,
  ≥ 2,000 games/anchor/batch, no predictions/clamping, sequential-stopping rules, SD-based
  σ_matched, covariance-aware GLS combination, batch combination retaining shared calibration).

2026-11-14 (CodeRabbit 5903125228 disposition — 13 findings, all verified against current code):
Recorded here so the review trail is complete; each fix is in db174e4 (source/docs) plus CI
evidence-artifacts work in 45f8507 (suites + manifest). Verification: `cargo test --release`
29/29, DIFTEST PASSED (2295/2295), clippy clean, UCI smoke 2-game live match vs pinned SF-lite
Skill 0/5 ran clean through the rewritten handshake (meta.json shows per-side artifact hashes,
hardware/OS, git commit).
1.  RATING_PROTOCOL σ_matched CI-half-width → fixed as Amendment §9 item 6 (SD of joint bootstrap
    replicates; published errors converted to SD via 1/1.96 for 95% half-widths, quantiles otherwise).
2.  RATING_PROTOCOL independent anchor weighting → §9 item 7 (joint opening-cluster bootstrap;
    Σ = Σ_match + diag(ε²); GLS with pseudo-inverse fallback; separate match-only / match+calib CIs).
3.  match.py select() Windows-hostility → reader thread + Condition-free wake event; hard deadline
    per line; EOF surfaces as EngineExited; verified on Linux handshake + quit path.
4.  match.py artifact fingerprinting → launcher (PATH-resolved) + every file-like token hashed;
    --white-artifact/--black-artifact for wrapper-loaded WASM; meta.json "artifacts" list +
    back-compat binary_path/sha256 (first artifact).
5.  match.py output reservation → O_CREAT|O_EXCL on games.pgn/games.jsonl/meta.json BEFORE any
    engine starts; concurrent/rerun invocations fail fast instead of mixing or truncating.
6.  stats.py boundary clamping → fmt_elo reports "boundary: ... no finite estimate" for 0/1 scores
    at point AND interval endpoints; bootstrap SD now printed for downstream anchor math.
7.  search.rs restricted-root override leaking into child continuations → extract_pv(pos, depth,
    from_root); override only when from_root; MultiPV tails bypass it entirely.
8.  search.rs checked repetition/fifty-move vs TT cutoff → in-check draws (insufficient-material
    outright; repetition/fifty-move after confirming legal evasions — mate precedence) resolved
    BEFORE the TT probe; post-movegen guard kept.
9.  search.rs TT clock-context reuse → tt.rs entries whose stored subtree can reach the fifty-move
    horizon (halfmove+depth ≥ 100) store bit-7 CLOCK-UNSAFE in the depth byte; probe never reuses
    their score; move ordering preserved; unit test at 99/1 boundary; horizon self-describes so the
    old current-clock-only 90 constant was removed.
10. uci.rs ponderhit/worker bestmove race → one flush Arc<Mutex<()>> serializes hold-clear with the
    publish/print decision on BOTH sides; send inside the critical section; exactly one bestmove
    prints regardless of order; stop_and_join unchanged (join+recv, swap-guarded).
11. tests/uci_smoke.rs early stop at first readyok → drain_reader collects post-exit lines until
    channel disconnect (bounded) in unknown_commands_do_not_crash and seeded_fuzz trials; all
    collected lines go through assert_no_panic_markers.
12. RATING_PROTOCOL shared calibration across batches → §9 item 8 (batch match-noise pooled by
    inverse variance; calibration variance added ONCE; combined CI reports θ ± 1.96√(v+c)).
13. position.rs null-move ep-hash drift → make_null_move XORs the ep file only when ep_included;
    clears ep_included/ep to -1 consistently; unmake_null_move(prev_ep, prev_ep_included) restores
    both; search.rs call site passes both.
None of the 13 were invalid on inspection; three were documentation-of-method corrections (1,2,12),
ten were implementation defects/footguns fixed in code or its tests.

- 2026-11-14 (rating harness + estimator): (1) Time-control period policy implemented as
  --tc-policy add (default; unused time carries, a fresh period is ADDED at each 40-move
  boundary — classic repeating control) and reset (clock set to period); the preregistration
  must freeze which policy the confirmatory batches use, and the manifest always records it.
  Verify against cutechess/CCRL semantics before freezing. (2) Engine-error replay is
  depth-first (immediate) so a second consecutive failure aborts the batch promptly (§3).
  (3) move_cap termination is recorded unadjudicated '*' and never scored; --move-cap-policy
  draw exists for exploratory runs only. (4) §9.8 combined calibration: exact combined
  calibration variance is c* = sum_a (lam*w_A,a + (1-lam)*w_B,a)^2 * eps_a^2 with
  lam = (1/v_A)/(1/v_A+1/v_B); shared anchor errors are added ONCE and never inverse-variance
  pooled. (5) Match-only vs calibrated intervals use the SAME point estimate (total-GLS
  weights); match-only variance = w' Sigma_m w. (6) Boundary bootstrap replicates (score 0/1
  in any resample) fail closed (EvidenceError) instead of clamping. (7) anchors: error_convention
  must be one of sd/se/ci95/ci90/ci99 — ambiguity is rejected, matching §9.6 conversion rules.

- 2026-11-14 (adversarial review, mission §3.8 — independent pass over high-risk paths):
  * match.py clock: charged time = set_position+go round-trip wall time (IPC latency charged
    to the mover — conservative: never grants extra time; may flag ~ms early). ACCEPTED.
  * match.py go() crash-net in clock mode = remaining clock + 60 s: a hung engine blocks the
    worker up to that bound, then counts toward the per-side abort limit. ACCEPTED (bounded).
  * GameClock tracks periods per side independently (each side gets its own 40-move counter
    and period grants) — correct for repeating TC. Verified by unit tests.
  * Manifest identity: white_artifact/black_artifact hash the --white-cmd/--black-cmd of the
    BATCH (colors swap per game via AB/BA); aggregate_shards checks frozen hashes against
    those top-level artifacts — consistent, no per-game ambiguity.
  * aggregate_shards duplicate-key = (shard_id, schedule_index, replay_depth): replayed
    attempts share schedule_index but differ in replay_depth — no false duplicate hits.
  * rating_estimator: load_batch 'name=path' splits on '=' (paths never contain '=' on POSIX/
    Windows runners); boundary scores raise EvidenceError (fail closed, never clamped);
    mat_inverse verifies A*inv=I to 1e-6 before use; combine_batches λ from match-only
    variances per §9.8 and shared calibration c* added ONCE (never pooled).
  * Gate has NO sequential-testing path: sample size fixed (--min-games), no alpha-spending
    entry points — matches §9.5 (fixed preregistered samples; new batches need new
    preregistration). REPORTED, nothing to change.
  * Residual risk accepted: clock policy 'add' vs cutechess/CCRL semantics not yet verified
    against cutechess source (pilot task); Flawless clock-management verified at smoke level
    (tests/clock_smoke.rs), deeper budget behavior under real 40/15 load is a pilot task.

## 2026-11-14 — §4 engine correctness/reliability audit: closure matrix

Every audit area has reproducible evidence in-repo. Verdicts: PASS = evidence complete and
green at `5eb6ee9`; regression = committed automated test that guards the fix.

| Area | Evidence | Verdict |
|---|---|---|
| FEN handling | `scripts/diftest.py` SAN/FEN round-trips over 76,240 sampled positions (0 mismatches); `tests/correctness.rs` terminal-state FENs; uci `position fen` smoke + fuzz grammar incl. malformed FENs tolerated | PASS |
| Move generation | Perft full CPW matrix **27/27 exact** (startpos d1–d6, Kiwipete d1–d5, pos3 d1–d6, pos4 d1–d6, pos5 d1–d5) + python-chess oracle MATCH; CI asserts startpos d3 on every push (both OSs) | PASS |
| Perft depth ≥6 | startpos d6 = 119,060,324; pos3 d6 = 11,030,083; pos4 d6 = 706,045,033 (`benches/perft_full_20261114.md`) | PASS |
| Zobrist | `tests/correctness.rs` make/unmake round trip + incremental-vs-recomputed hash consistency; DIFTEST repetition detection matches python-chess | PASS |
| TT | `tt::tests::*` (6): store/probe roundtrip, wrong-key miss, depth-preferred replacement, mate scores ply-relative, **clock-unsafe entries suppress score but keep move** (regression for the halfmove-clock defect found by CodeRabbit) | PASS |
| Mate handling | mate>draw precedence + mate-distance ply adjustments (regression `mate_scores_are_ply_relative`); no-startpos crash root-caused (illegal opening `e2e5`) + opener hardening + regression in `scripts/test_match.py` | PASS |
| UCI | `tests/uci_smoke.rs` (4): handshake/quit, unknown-command tolerance with post-exit full drain + panic-marker scan, seeded command fuzz (6×25), **bestmove handoff stress** (30 jittered trials, exactly-once emission without follow-up input — guards the uci.rs hold/ponderhit mutex design) | PASS |
| Clock | repeating 40/15 UCI clock (`scripts/test_match.py` 104 checks: parsing, add/reset periods, flag fall) + `tests/clock_smoke.rs` (3) + `uci::tests::clock_limits_respect_remaining_time`; stop/ponderhit mid-search | PASS |
| Threads | search worker + main-thread command loop handoff proven by the stress regression; `setoption Threads` accepted; panic isolation via `catch_unwind` + legal fallback bestmove (fuzz-verified); single-worker design documented (ARCHITECTURE.md) | PASS |
| Search-vs-oracle | DIFTEST 76,240 positions / 305 d3 perft comparisons / 0 mismatches (`benches/diftest-final-compressed.log` SHA `c3be9174…`) | PASS |
| Engine errors in harness | record → immediate replay → abort-after-2 policy (104-check suite); panic games flagged `engine_error`, excluded from statistics | PASS |

Lint/quality gates: `cargo fmt --check` clean; `cargo clippy --all-targets -- -D warnings` clean;
`cargo test --release` 34/34; Python suites 104/104 + 53/53 (real runners — the custom `main()`
suites are invisible to `python -m unittest`, see FAILURE_LEDGER).

### Residual-risk closure (same day): `--tc-policy add` == cutechess semantics — VERIFIED at source

Verified against `cutechess/cutechess` `projects/lib/src/timecontrol.cpp` (`TimeControl::onMoveMade`,
fetched via the GitHub API 2026-11-14): at a repeating-TC period boundary cutechess executes
`setMovesLeft(m_movesPerTc); setTimeLeft(m_timePerTc + m_timeLeft);` — the new period budget is
**ADDED** to the remaining clock (unused time carries over and accumulates). Flag expiry is
`m_lastMoveTime > m_timeLeft + m_expiryMargin`. Therefore match.py's default `--tc-policy add`
matches cutechess (and hence CCRL 40/15) semantics exactly; `--tc-policy reset` would DEVIATE from
cutechess. The earlier residual risk is CLOSED; the default stands and is the one used by PILOT-1,
the null controls and the planned batches.

## 2026-11-15 — ENGINE-2 design draft (SEE-based pruning) — baseline-gated, registration after SCREEN-2

Audit of src/search.rs (18 fns) + src/eval.rs at 14e2e1c: implemented = PVS-style null-window
re-search (first move full window, rest −alpha−1), iterative deepening, TT, quiescence with
per-capture delta pruning, reverse futility (150·depth), null-move, LMR table (quiet, ≥3rd
move, ≥d3, not-in-check), aspiration, killers + history (±depth²), passed-pawn terms
(passed_pawn_bits @ eval.rs:200). Verified ABSENT (grep): SEE, singular extensions,
countermove heuristic, check-extension policy audit (an `extension` term exists in the
re-search path; its assignment needs review when ENGINE-2 lands).

ENGINE-2 hypothesis (smallest justified change with the largest classical search gain among
verified gaps): add a static exchange evaluation and use it (a) in quiescence to prune
captures losing material after swaps (SEE < 0 when not in check, stand-pat-aware), and
(b) in move ordering so winning captures sort above losing ones (bad-capture demotion after
TT/killer moves). Expected effect (classical-engine literature + our anchors' lineage):
+30–80 Elo at fixed time; measurable at 40/15 via the registered A/B probe (vs SF19-lite
skill-5 band) and, if adopted, via a fresh screening. Risks: SEE mis-scoring promotions/king
captures → guarded implementation (king-capture truncation, promotion add-back), regression
suite (new unit tests with hand-computed SEE values incl. x-rays), bench signature WILL change
(pruning alters node counts) — perft/differential must stay identical (move legality
untouched). Acceptance criteria will be fixed in the registration BEFORE implementation,
using the SCREEN-2 + (candidate) batch baseline as the reference. This entry is a DESIGN
DRAFT ONLY — no code changes under this entry.

## 2026-11-16 — Mission re-entry: FlawLessChess V1 (>2,000) and V2 (>3,000)

- INTENT (owner mission prompt, verbatim scope): complete V1 (strictly above 2,000 Elo: Batch A and Batch B
  lower bounds plus combined lower bound each > 2,000, both null controls pass, ≥ 2,000 games per eligible
  anchor per batch) and V2 (strictly above 3,000 Elo on `benches/anchor-pool-3000.json`, GATE-PLAN-V2).
  Continuous checkpoints via `MISSION_CHECKPOINT.md`. Never merge, force-push, tag, release, or rename.
  No Stockfish-derived code.
- DONE (verified 2026-11-16 ~13:38Z): `MISSION_CHECKPOINT.md` created; AGENTS_LOG segment 24 appended. CTRL-2-R
  and SCREEN-3 are in progress. No gate plan exists yet. No dispatch marker changed in this segment.
- CONTRADICTION (recorded, not resolved): AGENTS.md names the repo `coderunknow/Flawless-Chess-Engine`; the mission
  and GitHub API use `coderunknow/FlawLessChess`. Owner declined repository-name changes; references left as-is.
- NOTE: the owner-supplied GitHub token is not stored in the repository, logs, or memory.

## 2026-11-16 — reconciliation (mission segment 24, cont.)

- CONTRADICTION (documentation only, resolved): dispatch rev 14 (commit 9890407, 06:59Z) quotes SCREEN-2R estimates 2225.9 / 2277.8 and |Δ| ~163–215. These predate commit a495085 (07:07Z, draw-scoring fix). Corrected estimates are 2176.8 / 2236.4, est 2206.6. The mechanical choice (akimbo-0.1.1) is unchanged under both estimates, verified with make_gate_plan.py to /tmp. The committed dispatch description is not rewritten.
- CONTRADICTION (protocol, resolved before any batch dispatch): BATCH-A/B pinned engine_sha256 fd75726d… (pre-ENGINE-1). ENGINE-1 requires the new frozen hash. Resolved by the append-only BATCH-HASH amendment binding Batch A/B to 9663697d…, registered before any batch dispatch. No batch existed under either hash.
- DONE: STATUS.md and MERGE_READINESS.md corrected (stale SCREEN-2 in-flight text; CTRL-2 pass claimed for the ENGINE-1 candidate). MISSION_CHECKPOINT.md rewritten.
- NOT YET VERIFIED: CTRL-2-R result, SCREEN-3 result, CodeRabbit status, python-chess-dependent test_match.py run.
## 2026-11-17 — RATING-100 implementation and SEE ordering candidate (validation pending)

- **Sample-design arithmetic:** the historical registered design is 60 openings × 17 paired repetitions × AB/BA = 2,040 counted games per anchor per batch. The proposed append-only RATING-100 amendment is 50 unique openings × 1 paired repetition × AB/BA = exactly 100 counted games per anchor per batch. With three anchors and two disjoint batches this is 600 counted games instead of 12,240, a 95.0980% reduction. This is a sample-size reduction, not a measured throughput or playing-strength improvement.
- **Suite integrity:** both 50-opening subsets are derived from their respective frozen 60-opening originals by the registered domain-separated SHA-256 selector and retain original line order. Batch A SHA-256: `abf1627495d3ad9c42240f076921e2453e5e30cac42782856ea5f0673ca60239`; Batch B: `f7414154ce2fe38faeac15dadc9f9c250245a54e908422e37451d089ff352219`. They are disjoint. `scripts/verify_opening_subsets.py` independently recomputes the selection, order, hashes and disjointness.
- **Prospective power: BLOCKED.** On the actual selected Batch-A 50-cluster subset, the two available screening anchors have cluster-score SDs 0.26578 and 0.29662 and paired-opening correlation 0.15888. The third-anchor cluster distribution and the disjoint Batch-B distribution are not available. The delta-method sensitivity model (250,000 Monte Carlo replications per scenario) varies third-anchor correlation 0/0.25/0.5 and cluster-SD inflation 1/1.5/2; at a true 2,100 Elo alternative the probability that both batch lower bounds and the combined lower bound all exceed 2,000 is about 63–77% with no variance inflation, 22–31% at 1.5× SD and 8.7–12.4% at 2× SD. This is not a substitute for the registered bootstrap or observed third-anchor/Batch-B covariance. `benches/rating-100-power-assessment.json` therefore remains `BLOCKED` and confirmatory dispatch is fail-closed.
- **Preserved gate:** 40/15 repeating wall-clock TC, frozen engine and anchor binary hashes, opening-cluster bootstrap, joint anchor resampling, GLS, calibration uncertainty, shared cross-batch calibration, both null controls, and the strict unrounded two-sided 95% calibrated CI lower-bound requirement (>2,000 for Batch A, Batch B and combined) remain unchanged. The original BATCH-A/B registrations remain historical and untouched.
- **Recovery integrity:** shard execution can now select exact frozen schedule indices within a shard. This allows a recovery to rerun only the missing AB or BA leg when the other leg was already counted. The batch dispatcher reads committed run manifests, calculates missing schedule indices, rejects identity drift and duplicate counted slots, and emits a per-shard schedule-index map. The canonical merger still requires counted schedule indices 0–99 exactly once, 50 expected opening clusters and exact AB/BA reversal.
- **Evidence lifecycle:** SCREEN-3 run 43820645420 completed with its resolver and all 60 shard jobs successful; its aggregate-and-commit-evidence job was skipped. CTRL-2-R run 43820392119 completed with its resolver and all 120 shard jobs successful; its aggregate-and-commit-evidence job was also skipped. Shard artifacts exist, but no canonical committed aggregate or recomputed screening/control decision was produced by those runs. Do not promote these jobs to completed evidence.
- **Runner observability:** future match shards are instrumented with GNU `time -v` resource records and pre/post cgroup CPU, throttling, cpuset and memory snapshots. These measurements are for subsequent actual throughput analysis; no parallelism speedup or runtime gain is claimed here.
- **Engine candidate:** `src/search.rs` adds material-only SEE for capture ordering (including en passant, slider x-rays and promotions) and demotes losing captures below ordinary quiet moves. SEE-based quiescence pruning was deliberately removed: the approximate pinned-piece model must not prune a potentially forcing capture. Unit tests cover free captures, losing exchanges, x-rays, en passant and capture promotions. This change alters the engine binary hash; the previous ENGINE-1 hash and its screening/control results do not automatically identify or validate this candidate. No playing-strength gain is claimed.
- **Validation status at this checkpoint:** source and workflow changes await the new commit's hosted CI and fresh CodeRabbit review. Tests for exact 100-game sample shape, deterministic suites, dispatch recovery and one-leg schedule-index recovery are pending. Keep PR #1 draft and gate mission ACTIVE / INCOMPLETE.

## 2026-11-17 — first hosted CI findings and correction

- The first CI run on implementation commit `7d368cd` identified rustfmt-only layout differences in the new SEE helper functions on both Linux and Windows. The five formatter diffs have been applied exactly; this is whitespace-only and does not change the search behavior.
- The fixed-depth-10 hosted bench produced signature `141943aa23b3fc68` for the SEE-ordering candidate, compared with the historical pre-SEE signature `fc907eba40b7869f`. The verifier's expected signature is being updated to the measured candidate value. This is an implementation fingerprint, not a strength or NPS improvement.
- The anchor-verification run stopped at the old signature comparison before writing the binary SHA-256 artifact. The new candidate binary SHA-256 is therefore still **NOT VERIFIED** and remains pending a successful exact-head verification run.
- The CI MSRV (Rust 1.80) check passed on `7d368cd`; Linux and Windows stopped at rustfmt before unit tests. No Rust test suite passed on that commit. The gate workflow failed closed because no gate plan exists. The rating-run resolver passed and skipped all shard jobs because this commit did not change `benches/dispatch.json`.

## 2026-11-17 — RATING-100 suite verifier incident and correction

- Hosted CI run 44062359630 on both Ubuntu and Windows passed Rust formatting, Clippy, and all Rust tests (test groups: 12, 3, 21 and 4; no failures). Python harness suites passed: match 111/111, estimator 65/65, reduced-sample 7/7, dispatch-recovery 5/5, merge self-test all cases. Both jobs then failed at scripts/verify_opening_subsets.py because the two selected-suite files did not match the registered lowest-50 SHA-256 selector. No rating games were dispatched.
- Root cause: the first suite-generation helper used an incorrectly populated SHA-256 round-constant table. This was a defect in the generation helper, not in Python's hashlib verifier. The verifier caught it before any confirmation run. The two reduced suite files and all dependent hash pins have been regenerated with the standard SHA-256 algorithm and new expected values; the original 60-opening suites and historical registrations are untouched.
- Corrected byte SHA-256: Batch A 5abdcdbddec0f22d7e6eff8974ee402363c8c3df318b8110d7204adf69f5c1df; Batch B ccb4901742eca25b0b10f1a3c9fdfc17b2967a1939c2d7e466c2c5495b6d4253. Both contain 50 unique opening names and have an empty intersection. The CI smoke step now asserts these exact hashes as well as BLOCKED power state.
- Separate anchor verification run 44062359732 succeeded. The verify-flawless job built the SEE-ordering candidate on PR merge commit 4cdf57c5e0d898e9accc6ec9d51ef00d82290575, measured bench signature 141943aa23b3fc68, and binary SHA-256 168dc0ab22749f8dc7a6be5248cd7426f9f2bfd3fda8077bc6218959ad6e41d7. This identifies that PR merge tree; do not yet register it against the branch source SHA until tree equivalence / exact-head verification is recorded.
- Rating-gate run 44062359728 failed closed as expected because no gate plan or canonical rating evidence exists. Rating-run run 44062359655 resolved successfully and skipped shard/evidence jobs because the dispatch marker was unchanged. No tournament was launched. CTRL-2-R and SCREEN-3 terminal shard artifacts remain unaggregated because their evidence jobs were skipped.
- Current decision: RATING-100 stays BLOCKED; no confirmatory dispatch, merge, tag, release or strength claim. Re-run exact-head CI and anchor verification after the selector correction is committed.


## 2026-11-17 — ENGINE-2 identity verification and power-report scope lock

- Exact-head CI run 44066217195 on PR source commit 5b63e273d77cfb097f0ad73bc28dda05cc19adad: Ubuntu, Windows and Rust 1.80 jobs all succeeded. Linux/Windows passed fmt, Clippy, all Rust test groups, match.py 111/111, rating_estimator 65/65, reduced_sample 7/7, dispatch recovery 5/5, power-manifest tests, merge self-test, deterministic suite verifier, 36-cell power smoke and release/UCI/perft smoke.
- Exact-tree anchor verification run 44066217113: 13/13 jobs succeeded. verify-flawless built merge commit 7434e948357eda05f9435e430c37da082f202741, whose second parent is branch commit 5b63e273d77cfb097f0ad73bc28dda05cc19adad. Both commits have the exact tree 75bc5633e1466d5abf1f4c7d5999bc4a3915e193 (GitHub compare reports zero changed files). Bench signature = 141943aa23b3fc68; binary SHA-256 = 168dc0ab22749f8dc7a6be5248cd7426f9f2bfd3fda8077bc6218959ad6e41d7.
- ENGINE-2 binary identity is now frozen for this exact source tree. This is an identity/build result only, not a strength or throughput measurement.
- New fail-closed provenance guard: the RATING-100 power data come from SCREEN-2 / ENGINE-1, frozen SHA-256 9663697da62e33229d516af3681c442e268287c59d6b97ff2cd13256b564d428. The power-analysis script now verifies the source manifests, raw-game merged hashes, original screening-suite hash, 120 attempts/120 counted games per anchor, both anchor identities and the same ENGINE-1 binary hash before generating a report. The dispatcher and rating-run resolver also require the power report engine hash to equal the candidate binary hash. ENGINE-1 evidence can no longer be reused to authorize ENGINE-2.
- Candidate-specific ENGINE-2 screening and controls remain NOT RUN. RATING-100 remains BLOCKED, no confirmatory dispatch has run, and no playing-strength or throughput claim is made.

## 2026-11-17 — power provenance regression test correction

- CI run 44067364552 on commit 29b627e: Rust / MSRV passed; existing Python suites passed through dispatch recovery 7/7. The new power provenance suite reported 3/4, with one expected-error-string mismatch.
- The test passed a new/unknown engine SHA; production code correctly rejected it in read_screening_manifest at the candidate allowlist, before comparing A and B manifest hashes. Updated the test to expect that earlier, stricter rejection. No weakening or production-code workaround.
- Commit 29b627e is not an accepted CI pass. The follow-up must rerun full CI at its exact HEAD.

## 2026-11-17 — Windows CRLF checkout broke raw screening-manifest verification

- CI run 44067826990 passed Ubuntu but failed Windows in the power-analysis smoke when checking the committed SCREEN-2 games.jsonl against merged_sha256. Git for Windows checked out LF JSONL as CRLF, while the evidence aggregator computed manifest hashes on Linux LF bytes.
- The power analyzer now hashes logical UTF-8 JSONL content after canonicalizing only line endings to LF. Record content, ordering, whitespace and record boundaries remain covered by SHA-256. Exact LF attributes were added for the two source evidence files, plus tests for CRLF portability and actual record tampering.
- No evidence was modified or rewritten; no confirmatory game ran. The power report remains ENGINE-1-specific and BLOCKED. Full exact-head CI is required.


## 2026-11-19 — UCI startup contract: no arguments means UCI mode

- **Decision:** the engine's default startup is the UCI protocol loop. Conventional UCI GUIs (for example CrispChess Extended's generic launcher, `Process.start(profile.path, [])`) start the executable with no arguments and then send `uci` on stdin. A missing argument is therefore a valid launch, not a usage error.
- **Evidence:** user diagnostic bundle `diagnostic-report.zip` (Google Drive, 2026-11-19): `engine.process.lost` 41 ms after start, then `initialize.failed` with `Engine "flawlessv1 patch2.exe" exited while searching (exit code 2)` and the usage text on stderr. Reproduced locally on the pre-change binary: no arguments → exit 2; `uci` → full handshake.
- **Implementation:** `src/main.rs` dispatches `None` and `Some("uci")` to `flawless::uci::run_uci()`. `-h`/`--help` print help to stdout (exit 0). Unknown commands keep exit 2 with the diagnostic on stderr. No banner or other text is written to stdout in UCI mode; diagnostics stay on stderr.
- **Rejected alternative:** matching the executable filename or special-casing the GUI. The contract is the engine's own default, so the fix applies to every launcher that follows the UCI convention.
- **Dependency and search impact:** none. Zero external dependencies; no search, evaluation or move-generation code changed. Bench signature `141943aa23b3fc68` is unchanged.
- **Identity impact:** the release binary changes, so ENGINE-2 hash pins in the rating documents do not describe this build. No rating evidence is reused.
- **Verification boundary:** local Linux results and exact-head CI (Linux, Windows, MSRV, Windows x64 artifact) are recorded in `docs/audit/2026-11-19-uci-no-args-compatibility.md`.

## 2026-11-19 — movetime soft-budget behaviour (observed, deliberately unchanged)

- Observation: `go movetime N` returns after roughly 38–100% of N (interactive, startpos/kiwipete/pos3). Cause: iterative deepening stops when the predicted next iteration (3× the last iteration time) would exceed the soft limit (`src/search.rs`).
- Decision: keep the current behaviour. Changing it alters the timing under which the rating evidence was collected. Any change needs its own evidence and a preregistration note.

## 2026-11-19 — REVERSAL of the movetime "keep current behaviour" entry above

- The earlier entry decided to keep the soft-budget early stop for `go movetime`. The user then authorised a fix. The earlier entry is kept unchanged as history.
- Decision now: `SearchLimits.fixed_time` is set only for `go movetime`. For such searches the growth-prediction stop is disabled; the hard deadline (= N) ends the search, so the search runs to about N (measured 100–101% at 300/1000/3000 ms).
- Clock-based searches (`wtime`/`btime`) keep the prediction rule. `ponderhit` clears `fixed_time` when it recalculates clock limits.
- Known consequence: a fixed-time search can still stop early at `MAX_DEPTH`/`max_depth` 64, or on a forced single-move root, which is legal UCI behaviour.
- Evidence: `tests/movetime_smoke.rs` (fails when the old rule is restored, verified by mutation in a scratch copy); `benches/movetime-20261119/movetime-after-fix.txt`; bench signature `141943aa23b3fc68` unchanged (fixed depth).

## 2026-11-19 — naming decision (user answer)

- The Cargo package stays `flawless` (binary `flawless`). The user declined a rename because it would break crate imports and CI paths.
- `Cargo.toml` `repository` now points to the verified remote `https://github.com/coderunknow/FlawLessChess`. The earlier `Flawless-Chess-Engine` URL is recorded as historical and was not used by CI.
- The product name remains FlawLessChess.

## 2026-11-20 — Audit remediation decisions

- Hash: the advertised maximum is lowered from 4096 to 1024 MiB to match the real 1 GiB TT ceiling (`MAX_HASH_MB`). Raising it needs a TT change and a memory test first.
- MoveList: capacity 512, not 256. The bound is 335 pseudo-legal moves (reachable positions under the FEN material limits: at most 16 pieces and 8 pawns per side); the hard check in `push` makes any future violation a panic in debug and release, never silent corruption.
- FEN material limits: >16 pieces per side, >8 pawns per side, or promoted pieces exceeding the missing pawns are rejected. Such positions cannot arise from a legal game from startpos. Positions from other sources may be rejected, which is the intended trade-off.
- Naming: the Cargo package stays `flawless` (ADR 0002). The GitHub repository and product name are `FlawLessChess` / `Flawless-Chess-Engine`. This is not a rename.
- Threads: stays a single-threaded build. The option is advertised as 1..1 and non-1 values are reported on stdout. No multithreaded search is claimed.

## 2026-11-20 — searchmoves with no legal named move (PR #4 Codex P2)

- Question: `go searchmoves` names only illegal moves. Options were (a) return `bestmove 0000` (the defect the mission lists), (b) refuse the request, (c) search all legal moves.
- Decision: (c). A null move answers nothing in a position that has legal moves. Refusing leaves the GUI with no move. Widening keeps the engine playing, and the widening is announced on stdout with `info string searchmoves names no legal move in this position; searching all legal moves` before the search starts.
- Known departure: the UCI text says `searchmoves` restricts the search. In this one case it does not. The departure is documented in README (Known limitations) and tested: `illegal_only_searchmoves_still_returns_a_legal_move` asserts the notice; `legal_searchmoves_are_respected_without_widening_notice` is the control.
- Revisit if a GUI reports a problem with widening; the alternative is option (b).

## 2026-11-20 — Output on a closed stdout ends quietly; search node cap is exact

- Question: when the GUI or reader closes stdout, should the engine panic (Rust `println!` default) or exit?
- Decision: exit with status 0 and no panic message. The `out_line!` macro is the only output path for protocol
  and CLI text. A GUI that has closed the pipe no longer needs the engine, so a panic adds only a nonzero exit
  and noise on stderr. Errors and diagnostics still go to stderr through `eprintln!`, which is unchanged.
- Question: should `go nodes N` spend exactly N nodes, or stop at the 1024-node check cadence?
- Decision: exactly N. The cap is checked on every node in search and quiescence, so UCI output and the bench
  reflect the requested limit. The cost is one comparison per node, and the bench change (`849a85bf7e8e1eba`) includes it.
- Related: S-14 colour symmetry fixed by a colour-relative move tie-break, not by disabling LMR (LMR off costs 18× the nodes).

## 2026-11-20 (late) — Batch input, stderr writes, root search with insufficient material, lock poisoning

- Question: what should `flawless moves` and `flawless hash` do with a stdin line that is not UTF-8 or is too long?
- Decision: answer that line with one `error` line and keep reading. A batch of FENs is a list of independent requests;
  one bad line must not drop the replies to the rest. Same bounded reader and 64 KiB cap as the UCI loop.
- Question: should a failed write to stderr end the process?
- Decision: no. Diagnostics go through `err_line!`, which ignores write errors, the same policy as `out_line!` for
  stdout (F-10). A failed diagnostic must never change the protocol outcome.
- Question: with insufficient material at the root, should single-PV search return at once?
- Decision: no. The root is searched like any other position, so the PV and `bestmove` come from the search. Only
  interior nodes take the insufficient-material draw (`ply > 0`). This mirrors the repetition rule, which already
  exempts the root (R-02a). Cost: the bench node total changes by 30 (2,311,437); the signature does not change.
- Question: what should a poisoned stdout-ordering mutex do?
- Decision: recover and continue. The lock guards only the order of stdout writes and holds no data. A panic elsewhere
  must not turn into a second panic at the next print.
- Note on the ponder clock (not changed): `go ponder movetime N` counts the movetime from `go`, so `ponderhit` does not
  restart it. Recorded in FAILURE_LEDGER as an open GUI-conformance question.

## 2026-11-20 (late, stretch 2) — Negative time values mean "no time left"

- Question: what should `go wtime -1000` (or `go movetime -5`) do?
- Decision: answer at once, as `wtime 0` does. A negative time is how a GUI reports that the clock has run out; treating
  it as "no limit" would search forever and lose on time. Overflow above `u64::MAX` saturates to a huge limit.
- Not changed: `go mate N` is parsed and ignored (see FAILURE_LEDGER). Unparseable values are still dropped.

## 2026-11-20 (late, stretch 3) — Memory refusal is reported, not fatal

- Question: when the allocator refuses the transposition table, or the OS refuses the search thread, should the engine
  abort?
- Decision: no. A refused table keeps the previous table (for `setoption`) or halves until the allocator accepts it (at
  start-up and in fallbacks). A refused search thread answers with the first legal move, with a stdout notice. The engine
  must stay usable for a GUI on a small machine. The notices go on stdout so a GUI can see them.
- Question: how to make a fallible allocation without `unsafe`?
- Decision: reserve the size with `try_reserve_exact` and release it, then allocate normally. The allocation that
  follows is the same size in a single-threaded process, so it normally succeeds; the lazy zeroing is kept.
  A `std::alloc::alloc_zeroed` path would be fallible too, but needs `unsafe` and a benchmark, and was not needed.

## 2026-11-21 (stretch 4) — F-20: one fallible zeroed allocation for the table (supersedes the probe decision above)

- Problem: the probe-then-allocate pattern in `try_resize` (reserve, release, then `vec![0; n]`) left a window in which
  the second allocation could be refused and abort the process. CodeRabbit and Codex both flagged it (F-20).
- Decision: `zeroed_entries` (`src/tt.rs`) calls `std::alloc::alloc_zeroed` once, checks for null, and wraps the result in
  `Box<[u64]>`. This is the only `unsafe` in `src/`. Its invariants, tests, fallback, and benchmark are written out at the
  function (see its doc comment) and in BENCHMARKING.md.
- The table is still lazily zeroed by the OS. The old `clear()` call on resize wrote every entry; it is no longer
  used, so laziness no longer depends on the compiler removing a `memset` after `calloc`. The counters are reset
  explicitly.
- Rejected alternative: eager `try_reserve` plus `resize(n, 0)`. Fallible, but it writes every page at resize (about
  1 GiB resident at Hash 1024 at the first search). That is a resource change that needs an owner's decision.

## 2026-11-21 (stretch 5) — F-23: the increment never widens the planned spend past the usable clock

- Question: with an increment larger than the remaining clock, should the engine spend the whole clock?
- Decision: no. The planned spend (soft, and hard) stays within `t - reserve`, whatever the increment. The increment
  share (`inc/2`) still counts toward the plan, but only inside the usable clock. The reserve is what protects against
  per-move overhead and a flag; spending the whole clock on one move gives the GUI nothing to absorb it.
- Effect: only when `usable/movestogo + inc/2 > usable`, i.e. `movestogo` 1 or a very large increment. Normal
  schedules (for example 40 moves in 15 minutes) are unchanged; the existing expected values still pass.
- Evidence: unit regression `clock_limits_never_plan_past_the_usable_clock_with_large_increment`; process timing in
  FAILURE_LEDGER F-23.

## 2026-11-21 (stretch 6) — F-24: a clock slice granted at ponderhit counts from the hit

- Question: when the GUI sends `ponderhit`, does our clock slice start at `go` or at the hit?
- Decision: at the hit. Our clock runs only during our own turn, so the time spent pondering is the opponent's time. The
  slice (`clock_limits`) is counted from `ponderhit` through `SearchLimits.clock_origin`. The code already said so
  ("the budget becomes a clock slice now"); the elapsed time was measured from `go`, so the slice was used up at once.
- Not changed: `go ponder movetime N` still counts from `go` (the open conformance question recorded before; the test
  `ponder_movetime_ponderhit_keeps_the_movetime_deadline` pins it). A fixed movetime is not our clock.
- Known behaviour: an iteration already running at the hit is not cut at soft; it ends at its own completion or at the
  hard limit (completed iterations are always kept). For a 20 s clock the answer after the hit took about 1.9 s (hard),
  not 0.47 s (soft). Within our clock and the designed hard limit. The owner may want the soft limit applied to that
  iteration; that would change search completion, so it is recorded here, not changed.

## 2026-11-21 (stretch 7) — FEN form: duplicated castling letters and trailing fields are refused; stale castling rights are kept

- Question: what should `position fen` do with `KK`, a seventh field, or a castling right with no rook (or the king off
  its home square)?
- Decision: refuse a duplicated castling letter and more than six FEN fields (malformed input, no contract conflicts).
- Decision kept: stale castling rights are accepted, as the contract in `tests/correctness.rs` (AUDIT-FEN-02) requires:
  they are ignored for castling, and no castling move is generated. Movegen was checked against python-chess on the
  stale and boundary cases (identical move sets). The stricter rule (refuse stale rights, as python-chess does, and as
  the en-passant check does here) is a real option; it changes AUDIT-FEN-02 and needs the owner's decision.

## 2026-11-21 (stretch 8) — Rejected or ignored UCI input is visible on stdout (F-26)

- Question: which silent UCI input cases should become visible? Rule applied: input the engine does not act on is
  reported on stdout as an `info string` (F-06), and the existing behaviour is otherwise kept.
- Decisions: (a) `position startpos` followed by tokens other than `moves` is refused (all-or-nothing, R-07), because
  the start position is not what the GUI asked for; (b) an unknown option gets an `info string`, always, on stdout;
  (c) a `go` limit with a missing or unparseable value is reported and ignored (the search is unbounded, as before), and
  a keyword is never consumed as a value. Unknown `go` tokens were already reported on stderr only; they are unchanged
  (UCI says to ignore them, and GUIs send harmless extras).
- Not changed: `go depth` with a bad value remains an unbounded search (until `stop`), not a refusal. A refusal would
  need a new `bestmove` rule; the owner may prefer it.

## 2026-11-21 (stretch 9) — The engine never blocks on stderr (F-30); UCI notices are on stdout

- Question: the engine wrote every refused `position` to stderr as well as stdout, unconditionally. A GUI that does not
  read the engine's stderr fills the pipe after a few hundred refusals, and the engine then blocks on the write and stops
  answering (reproduced: 300 refusals answered, 1,000 hung). Which channel carries UCI diagnostics?
- Decision: stdout is the channel the GUI always reads, so every notice the GUI needs is an `info string` on stdout.
  stderr carries a copy only after `debug on` (the same rule as unknown commands). The search-panic line keeps its
  stdout copy only; startup/allocation messages (table refused, fatal no memory) became stdout `info string` lines.
  The CLI one-shot commands (`perft`, `divide`, `eval`, `bench`) are unchanged: they write a bounded number of lines.
- Not changed: `debug on` still writes to stderr, so a GUI that enables debug and never drains stderr can still stall;
  that is the price of diagnostics the GUI asked for. Owner may prefer a bounded or non-blocking debug channel.
- Tests: `refused_positions_do_not_block_when_stderr_is_not_drained` (1,500 refusals, stderr piped and never read), and the
  F-13 stderr write-failure test now sends `debug on` first, so its stderr path still runs.

## 2026-11-21 — CLOCK-1: per-move floor in clock_limits (F-32 fix, owner-approved)

- Decision: owner selected "Amend ENGINE-1 and fix" for F-32 (sudden-death flags under the fixed 20 ms soft floor).
- Change: soft floor `20 ms` → `clamp(t / (4·movestogo), 1 ms, 20 ms)`. Nothing else in the budget formula changes. Hard limit, reserve, and increment cap are unchanged.
- Evidence and scope: PREREGISTRATION.md, entry CLOCK-1 (2026-11-21). Grid: 1,776 of 25,680 points changed, all with `t ≤ 1495 ms`; the 40/15 point and every `t ≥ 3200 ms` at movestogo 40 are unchanged.
- Accepted cost: shorter thinking time on clocks of 300 ms to about 1 s (about 1 ms to 17 ms per move). Strength at those clocks is expected to fall. Not measured in Elo.
- Frozen-evidence rule: the engine binary changes, so ENGINE-1 (`9663697d…`) and SEE-candidate (`168dc0ab…`) hashes no longer describe the head. No rating or screening is authorized by this entry. A new hash must be frozen and re-screened before rating use.
- Pinned test value `clock_limits_respect_remaining_time` changed from `(20, 20)` to `(1, 1)` at 250 ms. This is the owner-approved expectation change, recorded here and in the test comment. The test was not weakened.

## 2026-11-21 — audit: `go ponder movetime N` measured again (decision still open; not changed)
- Measured on release (`ad000f1`-era, reader-thread harness): `go ponder movetime 1000` with no `ponderhit` for 4 s: no bestmove (the engine does not exit in ponder mode, as the UCI spec requires). After `ponderhit`: bestmove after 0.0 s (`b1c3 ponder b8c6`), because the 1000 ms budget was spent while pondering.
- The UCI spec (wbec-ridderkerk.nl UCIProtocol, `ponder`) requires no exit in ponder mode. It does not say when a `movetime` budget starts. So this is not clearly a violation.
- Decision: unchanged. The existing decision (2026-11-21 F-24 entry) and the test `ponder_movetime_ponderhit_keeps_the_movetime_deadline` pin the current rule. Changing it would change a pinned expectation, so it is escalated to the owner in the final report instead.
- Effect on play: a GUI that ponders with `movetime` gets no extra thinking after `ponderhit`. Clock-based ponder (`wtime`/`btime`) is unaffected (F-24).

## 2026-11-21 — F-39: out-of-range `go depth` / `go nodes` values saturate (were ignored → unlimited)
- Found by audit (`go depth 4294967296` on the release binary printed `info string go depth: ... ignored` and then searched until `stop`, while `go depth 100` stops at 64). Cause: `depth` parsed as `i32` and `nodes` as a plain `u64` parse, so a digit-only overflow or a negative value failed and was dropped. With no depth, no nodes and no clock, `cmd_go` sets `infinite`.
- Decision: the rule already used for time values applies to these two as well. A digit-only value beyond the type saturates (depth to `i32::MAX`, then clamped to 64; nodes to `u64::MAX`). A negative depth saturates to `i32::MIN` (clamped to 1, as `-1` already was). A negative node count is 0, as a negative time is 0 (answers at once).
- Not changed: `go movestogo` (parsed as `u64`, overflow already saturates through the parser; it is not `Option<u32>`), `setoption` values, and the `go ponder movetime` decision above.
- Tests: `out_of_range_go_depth_and_nodes_saturate_instead_of_being_ignored`, `negative_go_depth_and_nodes_answer_at_once` (tests/protocol_regressions.rs). Both time out (20 s) on the pre-fix source and pass on the fix.

## 2026-11-21 — F-40: Hash sizes round down to a power of two (the table never exceeds the request)
- Found by audit: `try_resize` rounded the entry count up, so a non-power-of-two Hash allocated up to 2× the requested size (`Hash 513` → 1 GiB). The engine reported the requested size.
- Decision: round down. The table is at least half the requested size and never more; the 1 GiB cap and the 1024-entry floor are unchanged. Power-of-two sizes are unchanged, so the bench signature `849a85bf7e8e1eba` is unchanged.
- Cost: `Hash 100` now gives 64 MiB, not 128 MiB. A user who wants the full 100 MiB gets 64 MiB; the info string on the reduction path is not printed for this (the table is smaller than requested by design, not refused).

## 2026-11-21 — F-41: futility pruning is off while alpha is a mate score; LMR mate misses left for the owner
- Fixed: futility pruning at depth <= 2 now requires `alpha.abs() < MATE_BOUND` (as reverse futility and null-move already did). Before, a mate-in-3 alpha pruned the quiet mate in two. The bench signature (fen, depth, bestmove) is unchanged.
- Not changed, owner decision: LMR can reduce a quiet move that is the only mating move to a child at depth 0 or 1, where the mate is invisible (quiescence does not search quiet checks). Evidence and examples: FAILURE_LEDGER F-41 OPEN entry. A fix changes bestmoves and therefore the pinned bench signature `849a85bf7e8e1eba` (anchor-verify.yml). Options for the owner: (a) never reduce checking moves; (b) child depth >= 2 for reduced moves; (c) keep as is and document the depth-limited mate blindness. This is a search-strength change, not a legality issue; the engine's moves stay legal.
