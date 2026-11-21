# FAILURE_LEDGER.md (append-only)

<!-- 2026-11-14 (audit): the "No failures recorded yet" preamble was stale — the file already
contained entries. Entries are append-only and remain the live record. Required entry format:
what was attempted, why, exact commit/binary, conditions, raw evidence location,
result + uncertainty, suspected mechanism (hypothesis), what was learned, next experiment. -->

## 2026-11-14 — UCI bestmove never printed without trailing stdin input

- Attempt: `printf 'uci\nposition fen <kiwipete>\ngo depth 10\nquit\n' | engine uci` returned
  only `bestmove a2a3`-style fallback; an interactive session with `go depth 3` on a mate-in-1 FEN
  showed `score mate 1 pv b1b8` but NO bestmove line within 20 s.
- Root cause (hypothesis, verified): main thread blocked on blocking `stdin.lines().next()`; it never
  reaped the worker on natural completion. `stop_and_join` was only called on the *next* command.
  Fix: worker thread prints `bestmove [ponder X]` immediately after `search_root` returns;
  `stop_and_join` now only joins and stores the TT handoff; abort discards garbage root scores.
- Conditions: Rust 1.99.0 release build, Linux, 2 vCPU. No rating relevance.
- Result: fixed and smoke-verified (mate-in-1 prints `bestmove b1b8`; stop/ponderhit verified).
- Lesson: UCI engines must emit bestmove autonomously on search completion; never tie bestmove
  emission to the next GUI input.

## 2026-11-14 — Search worker panic (LMR table out-of-bounds) loses the game on the board

- Attempt: 40-game benchmark vs pinned Stockfish 19 WASM (Skill 0), opening `openings-20.txt`,
  `go movetime 100` per side.
- What happened: at game 1, move 30, our engine failed to reply for 300 s (harness timeout →
  `timeout_forfeit`, recorded 0-1). Root-caused to a thread panic printed to stderr:
  `index out of bounds: the len is 64 but the index is 64` at src/search.rs:484.
- Root cause: LMR reduction table `[[i32; 64]; 64]` indexed by `[depth][searched_count]` with
  **depth up to 64** (max_depth clamp) and **searched_count ≥ 64** (up to 218 legal moves).
  Two independent out-of-bounds paths.
- Fix: table enlarged to `[MAX_PLY+1][256]`; use-site indices clamped; and the UCI worker now wraps
  the whole search in `catch_unwind`, emitting a legal fallback `bestmove` on panic so the GUI
  never hangs. (The position — a mate-in-3 found at depth 16 — now searches cleanly at ~1.9M nps.)
- Result: match re-run; 2-game smoke passes (engine wins both, mate scores sane); full probe
  `benches/probe-001-sf19lite-skill0` launched.
- Lesson: any panic inside the search thread must not desynchronize the UCI loop — always emit
  bestmove; index tables must be sized for the true worst case (218 legal moves, depth 64).

## 2026-11-14 — Sandbox workspace reset (git HEAD reverted to 98b1a00; toolchain and venv lost)

- Attempt: continue session after a runtime interruption.
- What happened: `git log` showed only the starting commit `98b1a00` and all project files appeared
  as untracked; `/home/user/.toolchain` (Rust 1.99.0) and `/home/user/.venv` (python-chess) and
  `/home/user/opponents/` were gone. The repo working tree itself was intact.
- Recovery (all verified): origin still held branch tip `1dc2500`; re-pointed local branch ref and
  rebuilt the index with `git update-ref` + `git reset` — working tree matched the commit exactly
  (no data lost). Toolchain reinstalled from npm `@toolchain-bin/*` tarballs (rustc/cargo 1.99.0,
  clippy 0.1.99, rustfmt 1.10.0) — same versions as before; venv recreated (python-chess 1.11.2);
  pinned Stockfish 19 WASM reinstalled and SHA-256 re-verified identical (ccb130d7…, ee4f115b…).
- Lesson: push every commit immediately; keep raw-evidence artifacts committed; document toolchain
  provenance so it can be rebuilt from npm without network to rust-lang.org; the branch on origin is
  the source of truth.

## 2026-11-14 — Sandbox workspace re-materialized for the second time

- Attempt: continue the project after an interruption (Phase 1 start).
- What happened: git HEAD reverted to `98b1a00`; all tracked files showed as untracked;
  `/home/user/.toolchain`, `/home/user/.venv`, `/home/user/opponents/` wiped. CI/PR state on origin
  was unaffected.
- Root cause (hypothesis): sandbox host recycles the writable overlay between sessions; only the
  repository snapshot pushed to origin (and the mission-provided starting commit) are durable.
- Recovery: `git update-ref` to origin tip + `git reset` (index rebuild) — worktree verified clean
  vs a01fcaf; toolchain reinstalled from npm (same pinned versions); venv recreated; pinned SF
  WASM reinstalled and hash-verified (ccb130d7…/ee4f115b…); lld execute bits restored for lld-backed
  linking; full gate suite re-run.
- Lesson: push early and often; everything not pushed is at risk; keep this rebuild sequence
  documented (docs/ENVIRONMENT.md); verify gates after every restore.

## 2026-11-14 — Sandbox workspace reset (third materialization); full rebuild verified

- Attempt: continue Phase "CodeRabbit closure + re-verification".
- What happened: `/home/user/.toolchain`, `/home/user/.venv`, `/home/user/opponents`, and
  `node_modules` were wiped AGAIN; only the repository snapshot survived. This time the rebuild ran
  the full documented sequence and every gate was RE-VERIFIED before any commit: toolchain reinstall
  (@toolchain-bin pins: rustc/cargo 1.99.0, clippy 0.1.99, rustfmt 1.10.0 + find -exec chmod 755),
  venv (python-chess 1.11.2), pinned Stockfish 19 WASM reinstalled (hashes ccb130d7… / ee4f115b…
  re-verified byte-identical to BENCHMARKING.md), opponents/ mirrored, DIFTEST re-run
  (2295 perft-d2 positions, 0 mismatches, PASSED), bench re-measured (signature unchanged
  `fc907eba40b7869f`, 2,221,199 nodes), `cargo test --release --locked` 29/29 green, clippy clean.
- Latent defect found & fixed in the process: tt::store grew to 8 arguments (clippy too_many_arguments,
  -D warnings) — CI had gone blind to it (log access blocked); fixed by bundling a StoreRequest
  struct; the annotations-2.0 diagnostic step confirmed the exact error in one run.
- Lesson (unchanged, reinforced): after every restore, rebuild AND re-run gates before claiming
  anything; a green-looking CI rerun on a wiped tree proves nothing about local state.
- Also on restore #3: `git add -A` swept a locally-installed GPL Stockfish WASM tree (npm
  stockfish@19.0.1) into commit d6dc221 after node_modules was reinstalled for verification;
  removed in f0a2a55 (.gitignore now covers node_modules/). History keeps the blobs (no
  force-push — PR head stability); no further node_modules may be committed. Opponent remains
  pinned OUTSIDE the repo (/home/user/opponents, hash-verified).

## 2026-11-14 — Rating-anchor verification investigation (gate remains BLOCKED)

- Attempt: determine whether ANY eligible calibrated anchor (CCRL 40/15 preferred, CEGT 40/20,
  or another recognized list) can be verified from this sandbox.
- Commands and ACTUAL outputs:
  - `curl -I https://www.computerchess.org.uk/ccrl/40-15/` → 000 (blocked)
  - `curl -I https://www.cegt.net/40-15-chessengine-rating-list-6/` → 000 (blocked)
  - `curl -I https://ccrl40-15.herokuapp.com/` → 000 (blocked)
  - `gh api "search/repositories?q=ccrl+40%2F15"` → derivative mirrors only
    (`ahmad-luqman/chess-engine-nnue` scripts/anchors-ccrl.txt: user-maintained CCRL *Blitz*
    roster — cinnamon2.2a 2071, cinnamon2.3 2212, blunder7.4 2532, akimbo0.4 2723 — NOT the
    authoritative list, wrong scale (Blitz ≠ 40/15), ratings unverifiable, binaries local-only)
  - `gh api "search/repositories?q=cegt+chess"` → no usable rating list
  - `gh api "search/code?q=CCRL+40%2F15"` → index files only (CPWOffline/exported/CCRL.html is a
    hub page, wgArticleId 32, revision 24555 — no rating table; "Engine Rating Lists.html" is an
    index of external lists, external links all point to blocked hosts)
- Consequence: no anchor satisfies §2/§9 eligibility — verified name, version, SHA-256, published
  rating + error with convention, list publication date, retrieval date, and matching TC — so no
  gate batch may run and no absolute rating may be claimed. Anchoring from memory or from derivative
  GitHub files would be fabrication and is refused.
- Additional blocker (unchanged): ≥ 2,000 games × ≥ 3 anchors × 2 batches at 40/15-class TC
  (≥ 12,000 games; at CCRL 40/15 that is 40 moves per 15 minutes per game — infeasible on 2 vCPU).
- Next action for the gate (unchanged): execute RATING_PROTOCOL §§3–9 on a machine with access to
  the authoritative CCRL/CEGT lists and ratable opponent binaries (or their licensed redistribution),
  then commit benches/rating-batchA and benches/rating-batchB and update STATUS.md with the
  measured result and CIs.

- 2026-11-14: `cp -a <empty-var>/. sysroot/` after a failed `find` copied the filesystem root
  into /home/user/.toolchain/sysroot (unremovable cgroup pseudo-files inside). Cause: empty
  substitution in cp source. Fix: rm -rf + rebuild from npm packages; ALWAYS guard `cp` sources
  as non-empty. Also: npm strips execute bits — chmod +x sysroot/bin/* and
  sysroot/lib/rustlib/*/bin/* (incl. gcc-ld/) or linking fails with "cannot find 'ld'".
- 2026-11-14: synthetic anchor-vs-anchor null-control fixture was internally inconsistent
  (manufactured A1-vs-A2 games implied d=+235 while published diff was -100) -> control failed
  (correctly). Fix: build transitively consistent synthetic worlds (per-anchor score patterns
  matching published gaps). Uniform per-opening score clusters make Sigma_m degenerate (zero
  variance) and force the GLS fallback — synthetic fixtures must use heterogeneous clusters.

## 2026-11-14 — Anchor-verify hosted pipeline: 5 iterative failures resolved (evidence preserved)

- Attempt: rebuild all candidate anchors on hosted runners (anchor-verify.yml) with UCI identity
  + SHA-256 + license checks (mission §3.2).
- Failures, in order, each diagnosed via check-run annotations (the only runner readout):
  1. `ls LICENSE* COPYING* license*` exit-6 trap: unmatched globs make `ls` fail even when
     LICENSE matched. Fixed with `shopt -s nullglob` array test.
  2. `sed 's/\n/%0A/g'` line-based annotation escaping never matches (sed is line-oriented);
     replaced with python replace() chunking.
  3. WyldChess download 404: tags are `v1.2`/`v1.1` (script derived `1.2`). Fixed prefix.
  4. Raven binaries abort at startup on Ubuntu 24.04 (`*** buffer overflow detected ***`,
     rc=134): upstream `parsefen` 1-byte VLA overrun (position.c:27, ASAN: dynamic-stack-
     buffer-overflow, strcpy into `char fen[strlen(ofen)]`). Hardened gcc13/_FORTIFY_SOURCE=3
     traps it; author-era builds did not. Anchor source NEVER patched; built with
     -U_FORTIFY_SOURCE -D_FORTIFY_SOURCE=0 as documented accommodation (research evidence).
  5. SF10 node-count parse missed `Nodes searched  :` spacing → regex fixed; calibration job
     green (factor k=1.0291 vs i7-4770K).
- Raven 0.50–0.90 then EXCLUDED anyway: NO license file at any tested revision (LICENSE.md
  GPL-3.0 only added 2025-02-07 at HEAD) — unverifiable license under the fail-closed rule.
- Result: 6/6 pool anchors green on runners (run 43597866181) + verify-flawless (bench
  signature fc907eba40b7869f reproduced) + sf10-calibration. Pool frozen in
  benches/anchor-pool.json; rating-run acquire step implemented (artifact download + hash
  verify, rebuild fallback, fail-closed).
- Lesson: annotate real stderr/rc on every runner step; glob-listing tests must use nullglob;
  pin tag names verbatim from the tags API; license must exist at the EXACT revision.
## 2026-11-14 (seg-12) rating-run dispatch run 43601200490 (9ec9fb7) — FAILED, remediated

- Symptom: marker-file dispatch FIRED correctly (resolve job validated schema, matrix fanned out shard0+shard1), but both shard jobs failed at "Verify checkout is the frozen commit" (job names rendered "---shard1" = empty purpose/batch/anchor).
- Root cause: the resolve step wrote the `config` job output DOUBLE-encoded (`json.dumps(json.dumps(cfg))`); `fromJson` then yielded a JSON *string*, so `.resolved_target_commit` was null and actions/checkout fell back to the PR merge commit — SHA mismatch against the resolved target (expected fail-closed behavior doing its job).
- Fix: single-encode `config` (`json.dumps(cfg)`); dispatch.json revision bumped to 2 to deliberately re-dispatch (marker-file mechanism).
- Related historical note: run 43586802869 (10:45, head f53cb9c, job pilot-or-shard, 9s failure) came from the pre-rewrite rating-run.yml and is superseded by this mechanism; not investigated further.
## 2026-11-14 (seg-12) FALSE-GREEN local gate invocation — corrected

- `python -m unittest test_match` / `python -m unittest test_rating_estimator` run **0 tests** (both files use custom `main()` runners with `check()` counters, no unittest.TestCase). My local-gate claims invoking them ("104/104, 46/46 (unittest)") were mis-described: the counts are real but came from the proper runners (`python scripts/test_match.py` -> 104 checks; `python scripts/test_rating_estimator.py` -> 46 checks then, 50 now). CI (.github/workflows/ci.yml) was never affected — it runs the suite files directly. Correct invocation recorded; AGENTS_LOG entry 251/257 wording superseded by this entry.

## 2026-11-15 — Evidence-commit pushes failed from DETACHED HEAD ("src refspec ... does not match any") — FIXED + regression-tested

- Affected executions (all observed live):
  - evidence-bridge rev 2, run `43611827091` (head 93abb1e): aggregated pilot + pilot-dup
    evidence successfully, FAILED at the "Commit evidence to the branch" step — the commit
    existed only on the ephemeral runner and was never pushed (runner commits 6cbfdd2/0cb06ef
    are NOT on the remote branch).
  - SCREENING-1 run `43609372547` and SCREENING-2 run `43609636030`: all 15 shard jobs
    completed and uploaded shard artifacts + aggregate mirror artifacts, but the in-run
    `evidence` job failed at its commit step for the same reason → run conclusion = failure
    (fail-closed; no partial evidence claimed). Aggregate mirrors WERE uploaded (if: always()).
- Root cause: both workflows check out with `actions/checkout@v4` at
  `ref: ${{ github.event.pull_request.head.sha }}` → DETACHED HEAD. The publish step then ran
  `git push origin "$BRANCH"` — a local-ref refspec that matches no branch in detached HEAD,
  failing with `error: src refspec arena/... does not match any`. The preceding
  `git pull --rebase origin "$BRANCH"` succeeded (rebase onto the fetched remote branch works
  detached), which masked the real defect until the push step failed 5/5 retries.
- Fix (both `evidence-bridge.yml` and the `evidence` job in `rating-run.yml`):
  1. publish with the EXPLICIT refspec `HEAD:refs/heads/$BRANCH` (valid from detached HEAD);
  2. wrong-branch safeguard: refuse any destination that is not the PR's `arena/*` branch
     (never main, never another branch);
  3. verified rebase-retry loop for concurrent evidence commits: fetch the remote tip,
     `git rebase origin/$BRANCH` (patch-identical commits are dropped → idempotent no-op
     push), abort-with-diagnostics on conflict; ancestor-state check prevents force-like
     surprises;
  4. push/pull attempt diagnostics logged each attempt;
  5. evidence-bridge gained an `if: always()` aggregate mirror upload so an Actions-side
     aggregation can never again be lost to a failed commit.
- Regression coverage: `scripts/test_evidence_push.sh` (T1 detached-HEAD explicit-refspec
  push; T2 concurrent-advance rebase-retry; T3 wrong-branch refusal; T4 static guard on both
  workflow files) — 10/10 PASS 2026-11-15.
- Hosted verification: evidence-bridge revision 3 (deliberate marker dispatch) re-collected
  all recovered runs and its commit step PUSHED successfully from Actions — recorded in
  AGENTS_LOG.md with the run id. Not a green light for anything beyond pipeline correctness.

## 2026-11-15 — Estimator self-match metric could not implement the registered CTRL-2 definition — FIXED + regression-tested

- Observation: CTRL-2 (flawless vs identical binary, 240 games) evaluated from the committed
  evidence scored 0.6604 white-perspective, CI [0.571, 0.746] — outside the registered
  0.5-in-CI acceptance. The `control_self_match` implementation derives the score from engine
  NAME matching, which is degenerate for self-match records (both labels identical, "Flawless"):
  every game took the white branch, so the metric measured the CHESS color advantage, not the
  seat-symmetry quantity the registration defines ("identical binary must score 0.5 within its
  95% binomial CI" — the color advantage cancels only under the schedule's AB/BA seat reversal).
- Fix: when both seat labels are identical, the seat perspective is taken from the recorded
  `color_pair` field (AB: seat A white; BA: seat A black) — `self_match_seat_score()`; missing
  `color_pair` fails closed; `white_perspective_score` is reported for transparency. The
  registered threshold (0.5 in 95% CI) is UNCHANGED. Regression tests:
  `test_self_match_seat_perspective` + updated `test_focus_label_case_insensitive`.
- Re-evaluation (seed 20261116, unchanged inputs): seat-perspective score 0.5146, 95% CI
  [0.4792, 0.5500] → 0.5 inside → CTRL-2 PASS. White-perspective 0.6604 recorded as the
  chess color advantage (consistent with ~55-58% typical white edge plus a second-side time
  penalty; see the flag-race entry below).
- Related fix in the same change: focus-engine matching is now case-insensitive
  (`same_engine`, casefold) — the harness historically seated the focus engine under the
  display name "Flawless" while the estimator focus and pool keys are lowercase; the old
  exact-match `load_games` would have failed closed on ALL committed flawless evidence (and
  would have failed any confirmatory gate). Labels are display metadata; engine identity is
  the manifest-verified binary SHA-256; no two pool keys differ by case. Suite: 65/65.

## 2026-11-15 — SCREENING-1/2 root-cause: ~95% of Flawless losses are FLAG FALLS (time forfeits) — engine time-management defect identified

- Raw evidence (benches/evidence/screening/*): SCREENING-1 end reasons = 113 flag / 4 checkmate
  / 3 repetition; SCREENING-2 = 114 flag / 4 checkmate / 1 repetition / 1 stalemate. Flawless
  lost 116/120 and 118/120, ALL decisive losses but 3-4 by flag. Winner remaining clock at
  flag ≈ 2 s; loser (Flawless) at −1 ms. Flag plies concentrate in period 3 (p10/p50/p90 =
  81/84/87). The self-match (CTRL-2) shows the same regime: 199/240 flag ends.
- Root cause (code inspection, src/uci.rs clock_limits): `soft = clamp(t/mtg, 20, 30_000).min(t)`
  with `hard = min(6*soft, max(t-30, soft))`. The 30 s soft cap makes the engine OVERSPEND its
  period plan in the late period (soft pinned at 30 s while the clock shrinks below the plan),
  and hard = 6×soft permits single-move spends down to a ~30 ms remaining clock. Across the
  observed long games (83+ plies) the engine reaches period 3 with ~zero reserve and loses the
  flag race against anchors that budget with reserves. This is an implementation defect, not
  evidence that the search/eval strength equals a 1632-Elo level: the 100 ms-movetime probes
  (STATUS.md) measured search/eval strength without clock effects.
- Secondary observation (harness): in the self-match the second side to move loses flag races
  138:61 — a small per-move time-charging asymmetry (~tens of ms/move) consistent with the
  move-loop's second-side latency. The seat-perspective control passes (0.5146 ∈ CI); after
  reserve-bearing engine time management lands, flag races become rare and the asymmetry's
  impact shrinks; recorded here for the harness audit trail.
- Remediation: registered as ENGINE-1 (see PREREGISTRATION.md) BEFORE any new games: replace
  the budget formula with a reserve-bearing one (never plan past the period, keep a safety
  reserve, bound the hard limit), add clock-allocation regression tests, re-verify suites,
  re-screen the new candidate (SCREEN-2, fresh seeds), and only then re-apply the anchor
  selection rule. Batch A/B dispatch is DEFERRED — see PREREGISTRATION.

## 2026-11-15 — ENGINE-1 implemented and locally verified (registered 2026-11-15 before implementation)

- Change: `src/uci.rs clock_limits` replaced with the registered reserve-bearing budget:
  reserve = clamp(t/16, 300 ms, 8 s); soft = max(20 ms, (t−reserve)/mtg) with the old
  30 s upper clamp removed; hard = min(4·soft, (t−reserve)/2, t−reserve/2), floored at soft.
  Full-period utilization for repeating 'add' schedules is retained; a safety reserve now
  absorbs per-move overhead and the hard limit can no longer consume the whole clock.
- Verification (ENGINE-1 acceptance 1–3):
  (1) NEW regression test `clock_limits_engine1_no_flag_death_march` — full 40-move period
      simulation with 60 ms/move overhead completes with the reserve intact; no hard-limited
      move can flag; sudden-death drain stays within budget; the old starved-period trigger
      (45 s clock, movestogo lost) no longer overspends;
  (2) all suites green: cargo test --release 35/35 (lib 7 incl. the new test + clock_smoke 3
      + correctness 21 + uci_smoke 4), cargo fmt --check clean, cargo clippy --all-targets
      -D warnings clean, scripts/test_match.py 104/104, scripts/test_rating_estimator.py 65/65;
  (3) bench signature UNCHANGED `fc907eba40b7869f` (2,221,199 nodes @ depth 10) — the clock
      fix touches time allocation only; search/eval are byte-identical, so all prior
      correctness verification (perft 27/27, differential 76,240 positions) remains valid.
- Acceptance (4)/(5) are hosted/local play checks: SCREEN-2 (flag rate ≤ 10/120 per registered
  criterion) and the SF19-lite skill-5 A/B probe — to be recorded when executed. The new
  engine binary hash is UNFROZEN until the runner build records it (freeze mode), then pinned
  in PREREGISTRATION before any confirmatory dispatch.

## 2026-11-15 — anchor-verify ANCHOR-2 legs: 3 iterative failures resolved via runner annotations (evidence preserved)

- Run 43692582888 (head 4dbeeec): stockfish-5/8 rc=5 UCI ID MISMATCH — the SF id line is
  "Stockfish N 64"; I had wrongly embedded the AUTHOR banner into EXPECTED_ID (local smoke
  misread the banner line as the id). leorik-2.5 rc=4 BINARY MISSING — the repo root holds
  only Leorik.sln; the engine project is Leorik.Engine/ so `dotnet publish` at root has no
  project. akimbo-0.5.0 + weiss-1.2 + all 6 pool legs green on the first attempt.
- Run 43693256193 (head 56ef6a5): SF legs rc=0 (id now matches, binary recorded) but the
  WORKFLOW license step failed: "no LICENSE file" — the license glob is case-sensitive and
  SF ships `Copying.txt` (the pool anchors happened to use exact-case LICENSE/COPYING);
  leorik still BINARY MISSING — dotnet names the apphost after the PROJECT
  (publish/Leorik.Engine).
- Run 43693679899 (head 932ae99): SUCCESS — all 11 legs green; license glob now matches
  Copying*; leorik publishes its engine project and the apphost path corrected.
- Lessons: expected UCI ids must come from the actual id-name line (captured via the
  diagnostic run), not the banner; C# repos publish the ENGINE project, not the solution
  root; case-sensitive license globs must include Copying* for SF-family tags. All three
  fixes are in scripts/anchor_build.sh / anchor-verify.yml with annotated diagnosis trails.

## SCREEN-2-TIMEOUT (recorded 2026-11-15)

- **Experiment id:** SCREEN-2 (runs 43685671431 vs topple-0.1.1 seed 20261123; 43686056730
  vs topple-0.2.1 seed 20261124), marker rev 10.
- **Baseline SHA:** ENGINE-1 candidate, runner-built binary
  9663697da62e33229d516af3681c442e268287c59d6b97ff2cd13256b564d428 (30 builds, byte-identical).
- **Configuration:** 15 shards × 8 sequential games per run; TC 40/15 repeating 'add';
  batch-A suite 2c4a54d8…; workflow timeout-minutes 330.
- **Hypothesis under test:** ENGINE-1 flag rate ≤ 10/120 per screening + screening estimates.
- **Outcome:** FAILED (execution shape, not engine): all 30 shard jobs killed at the 330-min
  workflow timeout (started 06:29:43Z, killed 11:59:43Z/12:05Z); evidence jobs skipped
  (strict 15-shard aggregation precondition unmet).
- **Raw evidence location:** 30 artifacts (15 per run) downloaded to /tmp/scr2-<run_id> at
  inspection time; per-shard manifests + games.jsonl + games.pgn + runner-hardware.txt.
  Partial stats: 174 counted games, 1 flag, 0 engine errors, identities verified.
- **Measured uncertainty (selection-only, partial):** vs topple-0.1.1 score 0.3547 (n=86)
  → est ≈ 2428; vs topple-0.2.1 score 0.1724 (n=87) → est ≈ 2712. NOT acceptance evidence;
  recorded as exploratory signal only.
- **Failure/rejection reason:** shard sizing used PILOT-1's 29.43 min/game (old candidate,
  flag-shortened games); the fixed clock makes games run full-length (measured mean 52.0,
  max 147.5 min) ⇒ 8-game shards cannot fit any hosted timeout.
- **Lessons for subsequent experiments:** size every shard from MEASURED durations of the
  actual binary (SHAPE-1: 2 games/job, timeout 350; batches 1020 × 2 in 4 runs of 255;
  CTRL-2-R 120 × 2); a timeout kills jobs silently — check run conclusions, not just
  artifact presence; recovery = re-run failed jobs, never mix partial evidence.
- **2026-11-16 — SCREEN-2R run 2 (43714620645, vs topple-0.2.1), job 132843722744 (shard 17): FAILED, cause = runner/infrastructure failure.**
  Evidence: match step ("Run tournament shard (match.py)") frozen with conclusion=null;
  job window 17:20:05Z→19:33:10Z (~2h13m — longer than every successful sibling shard);
  NO error lines, NO artifact (upload step never ran), NO check-run annotation; the job
  log blob is gone (404 BlobNotFound) and the job is absent from the run logs archive
  (120 files = 59 shards x 2). This is a runner-level interruption mid-match, NOT an
  engine/harness failure (identical binaries completed 58/59 sibling shards + all 60 of
  run 1; aggregate job correctly skipped by needs.shard.result gate).
  Remediation: single-shard retry with identical frozen identity (marker rev 12, only
  shard_indices=[17]; seed 20261124, tc 40/15, pinned engine hash, suite hash, shard_count
  60 → shard 17 covers global indices 34,35). Workflow gained a marker-level run_evidence
  flag (this dispatch sets run_evidence=false) so the retry does NOT commit partial
  evidence at the canonical path; canonical aggregation happens offline via
  recover_screen2.py with merged artifacts (59 + 1) and explicit evidence commit.
  Tooling defects found & fixed during recovery prep (scripts/test_recover_download.py +
  scripts/verify_run1_both_paths.py): (a) REST artifact fallback passed b"" to ZipFile
  (text-mode stdout) — fallback could never succeed; now downloads zips to files (binary).
  (b) artifacts listing / gh download are paginated (default 30) — gh path silently
  truncated 60 shards to 29; now paginate (per_page=100) + post-download shard-count
  check with REST top-up. Both paths independently verified on run 43714600687:
  byte-identical aggregation matching committed evidence f4fc95c7c32f587b (120 games).
- **2026-11-16 ~07:00Z — SCREEN-2R run-2 recovery SUCCESS.** Retry run 43806800011 (shard 17
  only, run_evidence=false) completed/success; artifact downloaded via REST fallback path;
  merged 59+1 artifacts strict-aggregated fail-closed (60 shards, 120 counted games, engine
  hash = pin 9663697d…, 0 engine errors, 0 replays). Recovered evidence committed as 0cdeedf
  (benches/evidence/screening-2/topple-0.2.1/) and re-verified byte-identical on a second
  full recovery pass (bytes_match_committed=True for BOTH anchors; recover_screen2.py
  OVERALL: PASS). Result: W30 L82 D8, 0 flag losses (≤10 PASS), score 0.2833 →
  est = 2277.8 vs topple-0.2.1 (published 2439). Two tooling expectation bugs fixed during
  recovery (merged-slot per-run shard expectations; driver commit gate now validates the
  aggregation manifest rather than recover's overall exit code).
- **2026-11-16 ~07:25Z — draw-scoring bug in recover_screen2.py's REPORTING lambda (caught by cross-check, no evidence contamination).**
  The inline score lambda `((result=="1-0") == flawless_is_white ? 1.0 : draw? 0.5 : 0.0)`
  scored flawless-as-black DRAWS as 1.0 instead of 0.5, inflating the printed score/estimate:
  reported 0.3625/0.2833 (est 2225.9/2277.8) instead of the CORRECT 0.3000/0.2375
  (est 2176.8/2236.4; combined est 2206.6). make_gate_plan.py's focus_score (the registered
  perspective) is correct and was used as the reference; recover_screen2.py now matches it
  exactly (re-verified: identical scores on both anchors). UNAFFECTED: committed raw evidence
  (aggregate_shards.py output), manifest fields, flag-loss counts (decisive losses only),
  byte-match checks, and the SCREEN-3 anchor choice (ordering of |est−R_a| unchanged:
  akimbo-0.1.1 = 234.4 < wyldchess-1.2 = 238.4 < wyldchess-1.1 = 267.4; wowl = 357.6).
  The rev-14 marker description quotes the old numbers; its anchor/seed/sampling are correct
  (resolver does not validate description text) — this ledger entry is the authoritative
  correction. Same lambda in scripts/dry_validate_run2_59.py fixed too.
  NOTE for the 2000-gate: all screening estimates are selection-only; the gate uses
  confirmatory evidence via rating_estimator.py (audited separately vs §9).
- **2026-11-16 ~08:35Z — merge_batch_runs.py identity check was vacuous (found in pre-campaign
  audit, FIXED + regression-tested).** The cross-run identity comparison used manifest keys
  (white_name/black_name/time_control/openings_file_sha256/schedule/n_scheduled) that no
  per-run manifest actually contains (aggregate_shards.py writes batch/anchor/engine_sha256/
  anchor_sha256/opening_suite_sha256/...), so every identity compared equal on None and the
  promised drift detection could never fire. id_keys now match the real manifest shape and
  test_merge_batch_runs.py case 3 drifts engine_sha256 across runs (verified fail-closed).
  Defense-in-depth unchanged: verify_evidence.py re-checks engine/anchor/suite hashes at the
  canonical dir post-merge.
## 2026-11-17 — implementation defects caught before branch update

- **Incorrect first-pass opening subsets:** the initial 50-row candidate files did not match the stated SHA-256 lowest-50 selector. Recomputed both subsets from the original committed 60-row suites, discarded the first drafts, created exact deterministic subsets retaining source order, and added an automated verifier for selector, byte hashes and Batch A/B disjointness. Do not use the discarded suite hashes.
- **Workflow resolver validation order / source escaping:** an early draft checked shard count/repetition before parsing them and included a literal escaped newline in a Python source list. Reordered validation after parsing and corrected the malformed source line before commit.
- **Cross-batch evidence path collision:** the first evidence path used only the anchor key, so Batch A and Batch B could share a per-run evidence root. Updated to `confirmatory/batchA/<anchor>/run-<id>` and `confirmatory/batchB/<anchor>/run-<id>`.
- **One-leg recovery gap:** a two-game shard could count one color leg and abort before the reverse-color leg; rerunning the whole shard could duplicate the counted game. Added exact schedule-index selection to match.py, dispatcher-generated per-shard missing-index maps, and merge-level exact slot verification.
- **Skipped evidence jobs in completed screening/control workflows:** SCREEN-3 run 43820645420 and CTRL-2-R run 43820392119 completed all resolver/shard jobs but each skipped `aggregate-and-commit-evidence`. Their artifacts are not canonical committed evidence. Resolver config now defaults evidence capture on; only explicit `run_evidence: false` opts out. Historical runs are not retroactively relabelled or claimed aggregated.
- **SEE pruning reconsidered:** removed SEE-negative capture pruning from quiescence before implementation. SEE's pin-legality model is approximate; the candidate uses SEE for ordering only. No performance or Elo effect is asserted before testing.

## 2026-11-17 — validation issues caught before follow-up commit

- **Rustfmt:** first hosted CI found five formatting diffs in SEE helpers on Linux and Windows. Fixed to match rustfmt output exactly; no algorithm change.
- **Bench fingerprint:** the SEE ordering changed the deterministic depth-10 signature from the old `fc907eba40b7869f` to the measured `141943aa23b3fc68`. The old anchor-verifier expectation was stale; update it to the new measured fingerprint and rerun verification. Do not claim the candidate binary hash until the successful run writes it.
- **Evidence boundary:** rating-gate failure was the expected fail-closed result with no gate plan; rating-run resolver skipped all shards because `benches/dispatch.json` was unchanged. Neither failure is evidence of a rating or game result.

## 2026-11-17 — SHA-256 subset-generation defect caught by CI

- Symptom: Linux and Windows CI both rejected Batch A in scripts/verify_opening_subsets.py on run 44062359630. The failure occurred after Rust fmt, clippy, Rust tests and all Python regression suites had passed.
- Root cause: the one-off JavaScript helper used to select the 50 lowest SHA-256 digests omitted SHA-256 round constants. Therefore the selected opening sets were not the sets defined by the registered standard SHA-256 selector, despite the first helper's self-consistent output hashes. The repository's hashlib implementation correctly detected the mismatch.
- Containment: no confirmatory dispatch occurred; the power report remained BLOCKED; no games or rating results were created from these bad suites. The faulty files and hash pins are superseded, not reused.
- Correction: regenerated both suites with the standard SHA-256 constants and byte-tested hashes; Batch A 5abdcdbddec0f22d7e6eff8974ee402363c8c3df318b8110d7204adf69f5c1df, Batch B ccb4901742eca25b0b10f1a3c9fdfc17b2967a1939c2d7e466c2c5495b6d4253. Updated verifier pins, dispatch-tool pins, machine-readable report, CI assertions, append-only preregistration/protocol correction, and explicit LF checkout rules. The corrected suite bytes remain PENDING until hosted CI passes the verifier on the new commit.


## 2026-11-17 — resolution of selector CI failure and new engine provenance guard

- Corrected suites passed the deterministic selector check on both Ubuntu and Windows in CI 44066217195; each suite has 50 unique openings, zero overlap, and the exact registered byte SHA-256.
- Exact-head CI 44066217195 passed: Linux, Windows and MSRV 1.80; all Rust, Python harness, estimator, reduced-sample, dispatch-recovery, power-manifest, merge, suite selector and power smoke checks. The previous run 44062359630 remains a historical failure and is not overwritten.
- Added a fail-closed provenance guard so SCREEN-2 power data cannot be used for a different engine binary: both source manifests must prove the same ENGINE-1 hash, exact original screening-suite hash, 120 counted games/120 attempts and correct merged raw-game hashes; the dispatcher and workflow compare the report's engine SHA with the actual dispatch SHA.
- ENGINE-2 binary hash is now measured and pinned to source tree 75bc5633e1466d5abf1f4c7d5999bc4a3915e193 (branch source commit 5b63e273d77cfb097f0ad73bc28dda05cc19adad): 168dc0ab22749f8dc7a6be5248cd7426f9f2bfd3fda8077bc6218959ad6e41d7. No candidate-specific games or controls have been run.

## 2026-11-17 — provenance regression expected-error mismatch

- **Observed:** CI run 44067364552 on commit 29b627e failed the new power-analysis test suite (3/4 tests); the failing case expected an error string mentioning the later same-engine comparison.
- **Root cause:** the test supplied a non-SCREEN-2 engine hash. The production guard correctly rejected it earlier in read_screening_manifest because the power model is explicitly registered only for SCREEN-2 / ENGINE-1. The test asserted the wrong layer of the fail-closed path.
- **Correction:** change the expected message to "preregistered only for SCREEN-2". No production logic was changed or relaxed. Full CI on the follow-up exact HEAD is required before declaring validation green.

## 2026-11-17 — CRLF/LF mismatch in power evidence hash verification

- Observed: CI 44067826990 passed Ubuntu but Windows failed with merged_sha256 mismatch on a committed SCREEN-2 games.jsonl file.
- Root cause: tracked JSONL evidence was converted from LF to CRLF by Windows checkout; manifest hashes represent the original Linux LF bytes.
- Fix: hash canonical UTF-8 JSONL text after converting CRLF/CR line terminators to LF only. Add repository attributes forcing LF for the two SCREEN-2 evidence JSONL files. Add a test for CRLF checkout compatibility and another proving actual record edits still fail the SHA check.
- No data or benchmark result has been rewritten; no confirmatory dispatch occurred.

## 2026-11-17 — manual review disposition (session 2)

- Findings R-01, R-04, R-05, R-06 from REVIEW_MANUAL_03d2066.md did NOT reproduce at head 3ebf617 (reasons in REVIEW_MANUAL_071f875.md). The original file is unchanged; the dispositions live in the companion file.
- Fixed with evidence: R-02, R-03, R-07, R-08, R-10, R-12, R-13 (engine side).
- R-08 residual: one iteration whose time grows more than 3x can still overrun soft; bounded by the hard limit. Not eliminated.
- MSRV 1.80 build NOT VERIFIED: no 1.80 toolchain available (npm mirror has none; rustup blocked). Open blocker.
- Binary-identity blocker: R-02/R-03/R-07/R-08/R-10 change the engine binary. The ENGINE-1 hash frozen in PREREGISTRATION.md no longer identifies this code. Any gate or confirmatory evidence for the new behaviour needs a new candidate hash registered before dispatch. Not done; requires a decision.
- rating-gate (failed at 3ebf617 and at 071f875): cause not yet investigated; left as fail-closed.


## 2026-11-19 — GUI launch with no arguments exits 2 (UCI startup incompatibility)

- **Attempted:** CrispChess Extended (2.3.2-dev6+23, Windows 10 LTSC 2021) registered a custom engine `flawlessv1 patch2.exe`. The generic UCI launcher starts it with `Process.start(path, [])` and then sends `uci`.
- **Observed (raw evidence: user bundle `diagnostic-report.zip`, `application.log` and `errors.json`, 2026-11-19T21:12:56 local):** `engine.process.started` followed about 40 ms later by `engine.process.lost`, then `initialize.failed` with `Engine "flawlessv1 patch2.exe" exited while searching (exit code 2)` and stderr `usage: Flawless [uci|perft …]`.
- **Conditions:** the user's Windows binary's commit is not recorded in the bundle; its stderr reports `Flawless 0.1.0-dev.1`. The startup code of `main` at `5e36b06` has the same behaviour (verified locally). Local reproduction: Linux, Rust 1.99.0, release build, same commit: `flawless` with no arguments → exit 2 with usage on stderr; `flawless uci` → full handshake.
- **Root cause (verified from source and behaviour):** `src/main.rs`, the `None =>` arm of the argument match printed usage and called `std::process::exit(2)`. The engine's default startup was therefore not UCI.
- **Why the existing tests missed it:** `tests/uci_smoke.rs` always started the binary with the `uci` argument, so no test launched the engine the way GUIs do.
- **Result:** fixed in the session branch. Regression tests (no-argument lifecycle and handshake parity) fail on the old `src/main.rs` and pass on the fix. Exact-head CI and the Windows artifact are recorded in the audit report.
- **Learned:** a UCI engine must treat "no arguments" as UCI mode. Tests that only exercise the explicit subcommand cannot cover GUI launch behaviour.
- **Next experiment:** run the Windows artifact `flawless.exe` under a real UCI GUI launcher (CrispChess Extended) to confirm the engine is added without the exit-2 error. Not done in this session: no GUI is available here.

## 2026-11-19 — UCI smoke could accept a depth-0 bestmove when `quit` follows `go` in the same input

- **Attempted:** pipe `uci / isready / position startpos / go depth 2 / quit` into the release binary, as the CI smoke steps and the first version of the artifact checker did.
- **Observed:** the pipe run prints `bestmove a2a3` and no `info` lines. The same position in an interactive session (wait for each reply) prints `info depth 1` and `info depth 2`, then `bestmove b1c3 ponder b8c6`. Found during CodeRabbit review of PR #3 at `df0097e` (finding: "Wait for bestmove before sending quit").
- **Root cause (verified from source):** `src/uci.rs` `quit` calls `stop_and_join`, which sets the stop flag. Input already buffered when the search starts therefore stops it at depth 0, and the fallback root move is printed. The pipeline does not wait for a search reply.
- **Impact:** the existing CI step "UCI bestmove smoke test (search depth 2)" checks only the bestmove shape and legality, so it passes on a depth-0 result. It proves less than its name says. The Rust lifecycle test in `tests/uci_smoke.rs` is not affected: it reads `bestmove` before sending `quit`.
- **Conditions:** Linux, Rust 1.99.0, release build, commit `df0097e`. Engine behaviour is unchanged by this session; the pre-existing CI step was not changed.
- **Fix in this session:** `scripts/windows_artifact.py` now drives an interactive session and sends `quit` only after `bestmove` is read, with bounded waits. Its `bestmove` parser accepts the `ponder` suffix.
- **Open:** the existing ci.yml pipe-based smoke step should be made interactive or removed in favour of the Rust test. Not changed here; flagged for a decision.
- **Learned:** a protocol smoke test must synchronise on replies. A bestmove that is merely legal does not prove a search ran.

## 2026-11-19 — resolution: pipe-based bestmove smoke replaced by a synchronised check

- The CI step "UCI bestmove smoke test (search depth 2)" is replaced by `scripts/uci_bestmove_smoke.py`. It waits for each reply, sends `quit` only after `bestmove`, and requires a completed `info depth 2` line before `bestmove`. A depth-0 fallback is rejected; `scripts/test_windows_artifact.py` covers both paths.
- The Windows artifact smoke test uses the same session and depth check.
- Verification of the new step: local run against the release binary passed (`info depth 2 … bestmove b1c3 ponder b8c6`). The CI result is recorded in the audit report.

## 2026-11-19 — CodeRabbit a7b7eda findings: harness false-passes (fixed)

- Three checker bugs could hide defects in the Windows artifact harness: aliased handshake snapshot, unchecked stdout after `quit`, and an unreachable no-command stdout check. None affected the engine, which passed all probes. Fixed in the harness; regression tests added.

## 2026-11-19 — repeat of the quit-in-same-input pattern during the release validation

- An early movetime measurement sent `go` and `quit` in one stdin burst, so the engine returned a depth-0 fallback (`bestmove a2a3`) and gave a misleading "6–10% of budget" result. Caught before any conclusion was drawn. All timing claims now use interactive waits. The probe scripts document this.

## 2026-11-19 — FIXED: `go movetime N` returned after 39–100% of N

- Root cause: `src/search.rs` iterative deepening stopped when `now + 3 × last_iteration > soft_budget`. With `movetime`, soft equals the full budget, so the search stopped early (measured 39–100% of N, depth 7–16).
- Severity: medium (play strength and time use; no illegal moves, no hang).
- Fix: `fixed_time` flag disables the prediction stop for fixed-time searches only. Clock searches unchanged.
- Regression: `tests/movetime_smoke.rs` (restoring the old rule makes 2 tests fail: `movetime_uses_its_budget_within_tolerance` at 81 ms for 200 ms, and `repeated_movetime_searches_in_one_process`).
- Note: an earlier measurement of this symptom used `quit` in the same input as `go`, which is an invalid method (see the entry above). The fixed numbers use interactive waits.

## 2026-11-19 — FIXED: ponderhit answered at once after `go ponder movetime N`

- Root cause: `cmd_go` stored `last_clocks` on every `go`, including zeros when no clock was sent; `ponderhit` then recalculated a budget of about 20 ms from those zeros. Measured 1 ms (movetime ponder) on the candidate head before the fix.
- Severity: medium (ponder with GUIs that send `go ponder movetime`).
- Regression: `ponder_movetime_ponderhit_keeps_the_movetime_deadline` (fails on the previous uci.rs).

## 2026-11-20 — FINAL AUDIT: defects reproduced and fixed on arena/f668bde4-flawlesschess

- F-01 HIGH: a legal-looking dense FEN (`KQQQQQBk/Q5RB/Q6Q/Q6Q/Q6Q/Q6Q/Q1QQ3Q/QR3QQQ w - - 0 1`) crashed `go` with exit 101 (move-list overflow at types.rs). Fixed: FEN material limits + capacity 512 + hard push check. Regression tests added.
- F-02 HIGH: a non-UTF-8 stdin line ended the UCI session silently. Fixed: byte-level bounded reader. Regression tests added.
- F-03 HIGH: `go wtime N` alone had no time limit. Fixed: single-side clock bounds the search. Regression test added.
- F-04 MEDIUM: Hash 4096 was accepted but the table was silently capped at 1 GiB (RSS identical for 1024 and 4096). Fixed: advertised and accepted maximum is 1024. Regression test added.
- F-05 LOW: `clock_limits` could wrap on huge clocks. Fixed with saturating arithmetic. Unit test added.
- F-06 LOW: option rejection messages went to stderr only. Fixed: stdout info strings. Test added.
- NOT REPRODUCED (kept as regression tests): illegal-only `searchmoves` returned `bestmove 0000` (it returns a legal move); `go ponder nodes N` ignored its cap after `ponderhit` (with ponderhit sent immediately the search stops near N). Ponder node-cap test added.
- OBSERVATION (not a defect, not fixed): `go nodes N` stops below N (e.g. about 651 nodes for N=1000, 81,210 for N=100000). The cap is an upper bound and is not exceeded. The cause of the undershoot was not analysed.
- OPEN: MSRV 1.80 could not be run locally (the 1.80.0 toolchain is not on the npm mirror). The CI `msrv` job is the check of record.

## 2026-11-20 — FINAL AUDIT batch 2: checker validation and verification tools

- F-08 (MEDIUM): `from_fen` accepted positions with three checkers on the side to move, or two checkers on one line through its king (e.g. `1b4NQ/8/7R/3q4/3P1bn1/3k1K1P/3p4/2B1bN1q w - - 0 1`). Found by differential fuzzing against python-chess (14 such positions accepted in the seed-1 differential run: 40 random games plus placement fuzz). Fixed in `from_fen`. Regression tests added.
- EP-01: no saved self-play game contained an en passant capture, so full-game en passant was unverified. Added `scripts/fullgame_en_passant_probe.py` (python-chess referee, forced en passant, engine-vs-engine to the rule end). Passes; added to CI.
- S-14 (OPEN, informational): search is not colour-symmetric at depth 4 for 2 of 40 random positions (446 vs 493 cp, and 1284 vs 1262 cp). The static evaluation is symmetric on the same positions. Not treated as a bug; to be investigated only if a search defect is suspected.
- TEST ARTIFACT (not a defect): sending `go` and `quit` in one stdin burst returns the unsearched fallback move. Probes wait for `bestmove` before `quit`. Already documented in CHANGELOG.

## 2026-11-20 — PR #4 review findings in the audit harness (fixed)

- The UCI fuzzer accepted a session when any earlier `readyok` appeared, so a dropped final `isready` could pass. Fixed: exactly one `readyok` per session, generator never emits `isready`.
- The Windows artifact checker dropped a malformed extra `bestmove` before counting (regex filter). Fixed: count over the whole transcript first; regression tests added.
- The protocol and malformed probes validated only the first `bestmove`. Fixed; self-tested against a fake engine that prints two replies.
- Probes waited without a deadline (eval symmetry, en passant forced search) and the en passant probe ignored a failed quit. Fixed.
- The Rust protocol harness could block on a stdin write before its reply deadline. Fixed with a writer thread.
- A test named "double check" used a position with a single check (knight on g1). Fixed; the position is now a verified double check.

## 2026-11-20 — final-head review and symmetry diagnosis

- F-09 (LOW, UCI wording): Codex P2 on `3a280df` (`src/search.rs`): `go searchmoves` with no legal named move widens the search to all legal moves, outside the requested set. Decision recorded in DESIGN_LOG 2026-11-20. Fixed in part: the widening is now announced on stdout (`info string`). Kept by design: a null move is the defect the mission names. Tests: `illegal_only_searchmoves_still_returns_a_legal_move` (now asserts the notice), `legal_searchmoves_are_respected_without_widening_notice` (control).
- S-14 DIAGNOSED (informational, not a defect): the depth-4 search mismatch comes from Late Move Reductions. Evidence: static evaluation equal on each pair (`flawless eval`: 353/353 and 743/743; the depth-3 pair 44/44). In a scratch build outside the repo, disabling LMR makes both depth-4 pairs symmetric (446/446, 1262/1262); disabling null-move pruning alone does not (446/493 and 1284/1262). Mechanism: LMR reduces by move index, and the mirror position generates moves in a different order. No search change made; the hard symmetry gate is `static_evaluation_is_colour_symmetric`.
- Windows artifact `flawless-windows-x64-3a280dff77fcf1042dd49789b7442e63fd50a496`: retried at 13:26Z; `gh run download` still fails with EOF from `productionresultssa10.blob.core.windows.net` (curl to that host returns no HTTP status). Unverified. Not retried again in this session.

## 2026-11-20 — S-14 fixed, F-10 found (closed stdout), gate status

- S-14 FIXED (MEDIUM, supersedes the "informational, not a defect" wording above): a colour-relative tie-break
  (`relative_move_key` in `src/search.rs`) removes the depth-4 colour mismatch. Results: depth 4, 120 positions,
  default seed: 6 mismatches before, 0 after. Depth 5, 60 positions, seed 2027: 5 before, 0 after. The 11 recorded
  pairs in `tests/data/search_symmetry_pairs.tsv` pass (they fail on the previous `search.rs`). Cause: equal-score
  moves were ordered by raw square numbers, so the mirror could be searched in a different order; LMR is not
  the fix (disabling it gives 0/120 but costs 18× the nodes). Bench signature `849a85bf7e8e1eba`, 2,311,407 nodes.
- F-10 FIXED (LOW): when the reader closed stdout, the next `println!` panicked (`failed printing to stdout: Broken
  pipe`, exit 101). Found by the audit's pipe probe. All protocol output now uses `out_line!` (`src/lib.rs`), which
  exits 0 on a failed write. Regression: `protocol_regressions::closed_stdout_ends_the_process_quietly` (fails on
  the previous code). Scope: the engine has no other way to end on a closed pipe, so this is in scope and fixed.
- S-08 FIXED (LOW): `go nodes N` overshoot of up to 1,023 nodes came from checking the cap only every 1024 nodes.
  The node cap is now checked per node. Probe before the fix: N=1000 → 1024 nodes, N=5000 → 5,121. Now exact.
- Verification of this entry: fmt, clippy, and `cargo test --release --locked` pass on the working tree (see
  FINAL_AUDIT_PROGRESS.md for the SHA and the exact commands). The Windows artifact and CodeRabbit status are
  unchanged by this entry (NOT VERIFIED and NOT OBTAINED).

## 2026-11-20 — CodeRabbit review of 7d5b489 (five findings, all checked against code)

- F-11 (LOW, valid, fixed): an oversized input line was dropped without marking the position invalid. A dropped `position` left the old position in place, so a later `go` searched the wrong position and printed a bestmove. Fix: the TooLong branch sets `position_invalid`; a later valid `position` clears it. Test: `protocol_regressions::oversized_position_line_does_not_leave_the_old_position_in_use`.
- T-01 (test, valid, fixed): `ponder_node_cap_is_enforced_after_ponderhit` asserted an exact count, but the ponder search is uncapped until `ponderhit` is processed, so the count could pass the cap first (timing-dependent). The test now asserts termination and monotonic node count; exact caps are asserted in the non-ponder tests.
- T-02 (test, valid, fixed): `closed_stdout_ends_the_process_quietly` read the handshake without a deadline and had no kill-on-failure. It now uses the bounded harness; `Engine` kills the child on drop.
- D-01 (docs, valid, fixed): the audit document's blocker list still named the superseded head `c64b743`; the Phase H "Note on SHAs" claimed current HEAD was source-identical to `8370bed`. Both corrected; the historical gate table is unchanged.
- CI-1 (test, fixed): CI on c4fb22f failed in `Tests (release)` on ubuntu-latest (exit 101) and windows-latest (exit 1); `msrv`, the windows artifact job and anchor-verify passed. Logs could not be downloaded (results host EOF) and a rerun was refused (403), so the failing test was not seen directly. Cause (inferred from the code, not reproduced): `closed_stdout_ends_the_process_quietly` sent three `isready` lines after closing the reader. The reader can drain all three `readyok` lines in one read, close stdout, and leave the engine with nothing left to write, so the engine would wait on stdin and never exit. Fix: keep sending `isready` until the engine exits (the first write after the close fails). Locally: 30/30 isolated runs and the full release suite pass; the CI failure is not reproduced. Status: the cause is inferred; re-run CI on the next SHA is the check.

## 2026-11-20 (late) — Audit stretch: F-12, F-13 (corrected), F-14, S-08 provenance, CI hardening

- F-12 FIXED (MEDIUM): the batch modes `flawless moves` and `flawless hash` stopped at the first stdin line that was not
  valid UTF-8 (`lines()` plus `break`), so every later FEN got no reply. Probe before the fix: three input lines, one
  output line. Fix: `for_each_stdin_line` reads bytes with the bounded reader (64 KiB cap). A bad or overlong line gets one
  `error input line is not valid UTF-8 or too long` reply and the batch continues. Regression: `tests/cli_batch.rs`
  (3 tests). The two non-UTF-8 tests fail on the previous `main.rs`; the overlong-line test passes on both (coverage only).
- F-13 FIXED (LOW), with a CORRECTED reproduction. Earlier notes said closed stderr (`2>&-`) made the engine exit 101.
  That could not be reproduced in this sandbox: Rust's runtime reopens fds 0-2 at startup (a probe shows `fd 2` present
  and writes returning `Ok`). The real panic is a FAILED WRITE to stderr. With stderr a pipe whose reader is gone (EPIPE),
  the previous binary exits 101 before `readyok` on an oversized input line; the fixed binary exits 0 and answers
  `readyok`. Fix: `flawless::err_line!` (`src/lib.rs`) ignores write errors; all 17 diagnostic `eprintln!` sites in
  `uci.rs` and `main.rs` use it. Regression: `protocol_regressions::stderr_write_failure_does_not_stop_the_session_on_an_oversized_line`
  (fails on HEAD: no `readyok`; passes on the fix). The test uses a raw `pipe()` binding (test code only, with SAFETY comments).
- F-14 FIXED (LOW): in single-PV mode, a root position with insufficient material (K v K, K+B v K, K v K+N) returned after
  one node with an EMPTY PV. `bestmove` was then the first root move in move order, not a move from the search. Probe on
  HEAD: `info depth 1 seldepth 0 multipv 1 score cp 0 nodes 1 nps 1 time 0 pv ` (empty) and `bestmove e1d1`. Fix in
  `search()` (`src/search.rs`): the insufficient-material draw applies only at `ply > 0`, as the repetition rule already
  does, so the root is searched and yields a PV. The fixed build gives `pv e...` with nodes 6-13. Regression:
  `protocol_regressions::insufficient_material_root_is_searched_and_yields_a_pv` (fails on HEAD: "empty PV").
  No illegal move was ever produced (255 random insufficient-material positions, 0 illegal bestmoves on HEAD).
  Side effect: the bench node total changes from 2,311,407 to 2,311,437 (position 9, an insufficient-material
  position, now searches 40 nodes instead of 10). The bench SIGNATURE is unchanged (`849a85bf7e8e1eba`), because the
  signature covers (fen, depth, bestmove) only and bestmove is the same. BENCHMARKING.md is updated.
- Earlier false alarm, closed: an intermediate probe showed `go depth 3` on K v K answering `info nodes 1` with no
  depth line. Cause: the probe sent `go` and `quit` in one burst, and `quit` stopped the search before its first
  iteration. This is a probing artifact: wait for `bestmove` before sending `quit`. Not an engine defect.
- S-08 PROVENANCE: the overshoot came from the cap check `check_time` running only when `nodes & 1023 == 1023`. That
  mask was introduced in `7c065c2` (2026-11-14, "Phase 3/4 checkpoint"), found by `git log -S"nodes & 1023"` after a
  deepen of the shallow clone. It predates this audit and the base commit `c25e65e`.
- F-11 MUTATION CHECK (was pending): removing `self.position_invalid = true;` from the TooLong branch makes
  `oversized_position_line_does_not_leave_the_old_position_in_use` fail (`bestmove b1c3` where `0000` is expected).
  With the line, it passes. The regression is effective.
- CI-1 (cause still INFERRED, not reproduced): 40 runs of `closed_stdout_ends_the_process_quietly` under two CPU-bound
  processes on the current code: 0 failures. The inferred cause is unchanged (a reader that drained several `readyok`
  lines, so the engine had nothing to write and was waiting on stdin). The current test waits for exit, not for a line,
  so it does not depend on that timing.
- Hardening (no reproduced defect): the three `flush` mutex `unwrap()`s in `uci.rs` now recover a poisoned lock
  (`lock_ignoring_poison`). The guarded value is `()`, so there is no state to protect. The `unwrap()`s at
  `uci.rs` L333, L661, and L664 are guarded by an `is_some()`/`is_ok()` check on the line above, so they cannot panic.
  `position.rs:177` (`unreachable!("occupancy out of sync")`): reached only if the occupancy and piece boards disagree.
  New test `correctness::piece_bitboards_stay_in_sync_over_random_games` walks 160 random legal games (make and unmake)
  and checks every ply. Passes in release and debug (debug enables the `debug_assert!` sites).
- CI hardening: `ci.yml` has an explicit `permissions: contents: read` (the test workflow pushes nothing). All four
  `dtolnay/rust-toolchain@master` references (ci.yml x3, rating-run.yml x1) are pinned to the commit `master` pointed to
  on 2026-11-20, `df2a88e9fe4098bad09cb42c3dec7187f15861fc`. The same code runs; it can no longer change silently.
- Probes passed on this tree (not a gate by themselves; see FINAL_AUDIT_PROGRESS.md for the exact list): random-position
  perft differential seeds 2-7 (0 mismatches); debug search sweep seeds 2-6 (`scripts/search_sweep.py`, 0 failures);
  UCI grammar fuzz seeds 31-34 (200 sessions each, 0 failures); legal differential seeds 8-10 (all agree; 19 rejections,
  each justified by the material bound, checked by an independent necessary condition in the harness).
- Known limit, documented as a design choice (not changed): `position fen` rejects some legal-looking FENs that cannot
  arise from a real game (more than 16 pieces per side, more than 8 pawns, or promoted pieces above the missing pawns).
  DESIGN_LOG 2026-11-20 states the trade-off.
- Resource checks: 1,200 `go` cycles: threads 1-2, fds 3, RSS flat at about 69 MiB (Hash 64). Hash 1024: RSS grows only
  while the table fills (the table is lazily zeroed); increments fall from +90 to +9 MiB per 4 s search; the 1 GiB table
  is a single fixed allocation, so RSS cannot exceed it plus baseline. Resizing down releases the old table (1024 → 64
  gives 5 MiB).
- `ponderhit` with `go ponder movetime N`: the movetime deadline counts from `go`, so a `ponderhit` at 0.3 s of a
  1000 ms movetime answers at about 1.15 s, not 1.0 s after the hit. This matches the regression test
  `ponder_movetime_ponderhit_keeps_the_movetime_deadline` and is a deliberate, documented choice. Open question for
  GUI conformance: some GUIs expect the clock to start at `ponderhit`. Not changed in this stretch.

## 2026-11-20 (late, stretch 2) — F-15: negative clock or movetime made the search unbounded

- F-15 FIXED (MEDIUM, time management): `go wtime -1000 btime -1000` and `go movetime -5` searched with NO time limit and
  never answered without `stop`. `wtime`, `btime`, and `movetime` were parsed as `u64`, so `-1000` failed to parse and the
  token was dropped, which means "no clock". A GUI that reports a flagged clock as a negative number would therefore lose
  on time. Fix: `parse_time_ms` in `src/uci.rs`. A negative value is 0 (the time is already gone, so the engine answers
  at once, as `wtime 0` already did). A digits-only value above `u64::MAX` saturates to `u64::MAX`, not dropped. Winc/binc
  use the same parser. Non-numeric values are still ignored, as before.
  Regression: `protocol_regressions::negative_time_values_answer_at_once` (fails on HEAD: no bestmove within 5 s).
- Found by `scripts/uci_extreme_args_probe.py` (new, committed). 39 cases: `go` with 0, 1, negative, u64::MAX, i64::MAX,
  and malformed limits, plus 14 `setoption` values (Hash, MultiPV, Threads, Clear Hash, missing values). Result after the
  fix: 0 failures. Unbounded cases answer after `stop` (checked). Not defects by UCI design: `go depth 99999999999`,
  `go movetime 18446744073709551615`, and the other u64-maximum values are searches with an effectively infinite
  limit; `stop` ends them.
- Known limitation (not changed, LOW): `go mate N` is parsed but not implemented. The search runs until `stop`, as
  for `go infinite`. A GUI that expects a mate search will get a search without a mate target. Implementing it is a
  feature, not an audit fix.
- Informational: `go depth 0`, `go depth -1`, and `go nodes 0` answer at once with a root move that was not searched
  (a zero budget). UCI does not define those values. No illegal move is produced.
- Probe defect, NOT an engine defect (`scripts/time_budget_probe.py`, committed in 1d2cd24): `read_until` called
  `select()` on the raw stdout descriptor while `readline()` had already buffered the rest of the handshake. The
  probe then waited for data that was already in its buffer and failed with `no 'uciok' within 10s; saw ['id name
  Flawless']`. Fixed with a reader thread and a queue (no `select()` on a buffered stream). Two runs after the fix: 8/8
  each. Gate run on df6417d recorded `time_budget_probe rc=1` before this fix. Only this probe had the pattern (grep).
- Scratch checks (in `/tmp/fuzz`, not in the repository): `uci_fuzz.py` seeds 41 (150 sessions), 42, 43, 44 (300 each):
  0 failures. `fuzz_fen.py` seeds 1, 2 (3,000 FEN lines each through `moves`): every line answered, rc 0. The repository
  has no `scripts/fuzz_uci.py`; the queue item named a file that was never committed.

## 2026-11-20 (late, stretch 3) — F-16 and F-17: allocation refusal aborted or panicked the engine

- F-16 FIXED (MEDIUM, resources): a refused transposition-table allocation aborted the process (SIGABRT, rc 134, no
  `readyok`). Reproduced: `ulimit -v 400000` then `setoption name Hash value 1024` after `uci`. Rust aborts on a failed
  `vec!` allocation, so the GUI saw a crashed engine. The same happens at start-up under a limit below the default 64 MiB.
  Fix (`src/tt.rs`): `try_resize` and `try_new` reserve the size first with `try_reserve_exact` (a refusal becomes an
  error), then do the usual zeroed allocation. The table stays lazily zeroed; idle RSS after Hash 1024 is 4 MiB (unchanged).
  No `unsafe`. Fix (`src/uci.rs`): `setoption Hash` that cannot be allocated prints
  `info string option Hash N MiB could not be allocated; keeping M MiB` and keeps the old table. Start-up and the
  fallback re-allocation halve the size until the allocator accepts it (announced on stdout); a refusal at 1 MiB exits 1
  with a message on stderr (there is no memory for any search).
  Regression: `protocol_regressions::hash_allocation_refusal_does_not_abort_the_engine` (Linux only; fails on 2b10cd2 with a
  signal exit, passes on the fix).
- F-17 FIXED (MEDIUM, resources): when the OS refused the search thread (`WouldBlock`, under the same limit), `go` hit
  `expect("spawn search thread")` and the engine exited 101. Fix: on a failed spawn, the engine answers with the fallback
  move (the first legal move, or `0000` with no legal move) and prints `info string search thread unavailable (...)`
  on stdout. Limitation: under such pressure the engine answers without searching. Covered by the same regression test
  (50 MB case, which halves the table and then cannot spawn the thread).
- Checked after the fix: 400 MB limit + Hash 1024: readyok, exit 0, legal bestmove; 50 MB and 30 MB limits: exit 0,
  legal bestmove. No limit: bestmove unchanged (`b1a3` at depth 4 from startpos, identical before and after).
- F-18 FIXED (LOW, CI portability): CI `windows-latest` failed at `Clippy (deny warnings)` on `2b10cd2` (run 44775302570,
  job 136423393755; Ubuntu, MSRV and the Windows artifact job passed). Cause: the F-13 regression test
  `stderr_write_failure_does_not_stop_the_session_on_an_oversized_line` used `std::os::unix::io` and a raw `pipe` binding
  without a `cfg(unix)` gate, so the Windows build failed to compile. The `Read` import, used only by that test, would
  also have been an unused import under `-D warnings`. Fix (`tests/protocol_regressions.rs`): the test and its
  `extern "C"` block are `#[cfg(unix)]`; `Read` moved into the test body. The test still runs on Linux (17/17 pass).
  Not verifiable locally: no Windows target is installed, so the fix is confirmed by the CI run on the new head.
  Log for CI job 136423393755 downloads failed with EOF; the step result and annotation were used instead.
- F-14 EVIDENCE ADDED (2026-11-21 re-check; the classification above stands): the earlier note "not reproduced" was
  wrong. It looked only at bestmove legality, which is legal in both builds because the fallback picks the first legal
  move. Comparing the pre-fix build (`0d4fda1`) with HEAD on five insufficient-material roots (K v K, K+N v K, K+B v K,
  K+B v k as Black, K+N v k as Black), `go depth 4`, single PV: pre-fix gives `info depth 4 seldepth 0 ... nodes 4 ... pv`
  (empty) and bestmove legal; HEAD gives `seldepth 1`, nodes 24-52, a non-empty PV whose first move is the bestmove.
  The regression test `insufficient_material_root_is_searched_and_yields_a_pv` fails on `0d4fda1` with
  "empty PV" and passes on HEAD. Interior nodes keep the draw rule, so scores are unchanged (0).
- F-19 (LOW, hardening, NOT a reproduced defect): the three `flush` mutex `unwrap()`s in `src/uci.rs` now recover a
  poisoned lock (`lock_ignoring_poison`, introduced in `df6417d`). The guarded value is `()`, so a poisoned lock holds no
  state to protect. No regression test: the path needs a panic while the lock is held, and there is no way to produce one
  through the protocol. Recorded so the change is traceable; not claimed as a fixed defect.
- F-09 RE-RAISED (not a new defect): Codex review on `a400e80` (`src/search.rs:283`, P2) repeats the F-09 point that
  `go searchmoves` with no legal named move should preserve the empty intersection or reject. The documented decision
  (DESIGN_LOG 2026-11-20) is kept: refuse the null move, search the legal moves, and announce the widening on stdout.
  Reason: the earlier known defect was a `bestmove 0000` answer, and UCI requires a bestmove. This is a
  design disagreement and stays open for the user; it is not silently changed.
- ENVIRONMENT EVENT (2026-11-21 ~01:56 UTC): a sandbox restore left the repo as a fresh clone at `c25e65e` with the
  working tree restored. The local commits `1d2cd24`..`a400e80` were not in the clone, but `origin` held `a400e80`, so
  nothing pushed was lost. The one unpushed commit (`0105db2`, F-18) survived as working-tree changes, which were
  verified byte-for-byte against `a400e80` (exactly the two F-18 files) and recommitted as `ffd6b04` (same tree; new
  hash, since commit metadata differs). `/home/user/.toolchain` and `/home/user/.venv` were gone and were reinstalled from
  the pinned `@toolchain-bin` npm tarballs (rustc, cargo, rust-std, clippy 0.1.99, rustfmt 1.10.0; install.sh --prefix)
  and `chess==1.11.2` from PyPI. `/tmp/gates` scripts were lost; the gate script was rebuilt from the same steps.
- F-11 MUTATION CHECK DONE (2026-11-21): on a copy of HEAD with the `self.position_invalid = true;` line removed from the
  `LineRead::TooLong` arm, `oversized_position_line_does_not_leave_the_old_position_in_use` FAILS (`go` answers
  `bestmove b1c3`, i.e. it searches the old position; expected `bestmove 0000`). On the fix it passes.
- F-18 VERIFIED IN CI: run 44853133810 on `ffd6b04` (CI): success on ubuntu-latest, windows-latest, msrv (rust 1.80), and
  the windows x64 release artifact job. anchor-verify 44853133745: success. The failure on `a400e80` (run 44777328791,
  job 136430504382) was the same `Clippy (deny warnings)` step on Windows.
- RSS AT HASH 1024 (sustained search; `/tmp/audit/rss1024.py`, one process, `go movetime 2000-3000` per round, four
  positions): idle 4.8 MiB; after round 1, 272 MiB; round 12, 964 MiB; round 29, 1007 MiB, still rising at about 1-3
  MiB per round. Consistent with lazily zeroed table pages being touched as the 1024 MiB table fills, so the ceiling
  should be roughly table size plus overhead (earlier hash-cycle measurement: 1029-1046 MiB). NOT proven capped: no
  plateau was observed in the time available. Not a leak claim: the table size is fixed and no second table is
  allocated (`hash_cycle.py`: 30 resizes, exit 0).
- G3 (Windows artifact, `ffd6b04`, artifact 14686132529, 211,374 bytes): `gh run download` and the REST artifact zip both
  failed with EOF from the blob host. NOT VERIFIED. No manifest or SHA256 was checked from the downloaded file.
- F-20 OPEN (MAJOR, resources; found by CodeRabbit on `ce9f8d4`, `src/tt.rs:143`; verified in the code): `try_resize`
  reserves the size in a temporary `Vec` and drops it, then allocates the real table with `vec![0u64; entries]`. If that
  second allocation is refused, Rust aborts (allocation error path) instead of returning `TableAllocError`. So the F-16 fix
  is incomplete in a narrow window. NOT reproduced. Fix options: (a) keep the reserved `Vec` and fill it (fallible, but
  it touches every page, so RSS at Hash 1024 jumps to about 1 GiB at resize; this changes the idle-RSS claim and needs a
  decision); (b) keep lazy zeroing and document the window. Needs a source change and a full gate run.
- F-21 OPEN (MINOR, found by CodeRabbit; `src/uci.rs:596`; verified in the code): the F-17 spawn-failure fallback prints
  the unrestricted first legal move even when `go searchmoves` restricts the search. Not reproduced at run time (needs a
  refused spawn); code-verified. Fix: choose the fallback from the legal named moves. Needs a source change and a full gate.
- F-22 OPEN (MINOR, found by CodeRabbit; `src/uci.rs:599`; verified in the code): on spawn failure, `go infinite` and
  `go ponder` print `bestmove` at once and skip the output hold used for `stop`/`ponderhit`. Not reproduced at run time;
  code-verified. Fix: hold the fallback until `stop` or `ponderhit`. Needs a source change and a full gate.
- HARNESS FIXES (scripts only, found by CodeRabbit on `ce9f8d4`, verified): `scripts/time_budget_probe.py`: the black-only
  case sent `wtime` as well, so it did not test a lone `btime`; now sends `btime 1500` only (8/8 pass, black case 26.9 ms).
  `scripts/search_sweep.py` and `scripts/uci_extreme_args_probe.py`: `readline()` blocked without a deadline; both now read
  stdout in a thread and enforce the deadline while waiting (`search_sweep` seed 2, 20 positions, PASS; extreme-args probe
  0 failures). Targeted runs only; no full gate rerun for these harness changes.
- PROVENANCE ADDENDUM (CodeRabbit ledger comments on `ce9f8d4`; raw logs from earlier runs were lost in the 2026-11-21
  restore, so this says what is and is not still available):
  - F-11: fix in `c4fb22f` (`src/uci.rs`, TooLong arm). Regression fails on the `7d5b489` source (per the earlier review
    reply). Mutation check this stretch: a copy of HEAD (`ffd6b04`) with the `position_invalid = true` line removed gives
    `bestmove b1c3` where `0000` is expected; the regression test FAILS there and PASSES on the fix. Output was on the
    terminal, not saved to a file; the copy is `/tmp/mut_f11` (outside the repo).
  - F-12: fix in `df6417d`. The failing copy was `/tmp/mut4` (HEAD before the fix); its output is not retained.
  - F-15: fix in `2b10cd2`. The failing build was the pre-fix HEAD (`df6417d`); output not retained. Probe rerun on the
    fixed code: `scripts/uci_extreme_args_probe.py` 0 failures on `ffd6b04` and again after the harness change.
  - F-16/F-17: failing revision `2b10cd2` (signal exit under `ulimit -v`); fixed in `a400e80`. Resource-check outputs
    `/tmp/audit/vlim_*`, `vfix_*`, `vf2_*` were lost in the restore. Regression test passes on `ffd6b04` (CI success).
  - Current evidence (retained after this stretch): `/tmp/gates/final-ffd6b04/` (34 rows, rc=0) and `/tmp/audit/k/`.
- F-21 FIXED (MINOR, found by CodeRabbit on `ce9f8d4`, `src/uci.rs`; reproduced): with the search thread refused,
  `go searchmoves d2d4` answered `bestmove a2a3` (the first legal move in generation order, excluded by searchmoves) on the
  pre-fix code, under `ulimit -v 50000` (debug build of the pre-fix HEAD, `/tmp/mut_f11`). Fix: the fallback is the first
  legal move that is in `searchmoves`; if none is legal, the widened first legal move (as the search does). Regression:
  `protocol_regressions::spawn_fallback_respects_searchmoves` (Linux): fails on the pre-fix code (`bestmove a2a3`), passes on
  the fix (`bestmove d2d4`). F-22 (fallback bypasses the output hold for `go infinite`/`go ponder`) remains OPEN.
- F-20 FIXED (MAJOR, resources; found by CodeRabbit and Codex on `ce9f8d4`, `src/tt.rs:143-144`; code-verified, not
  reproduced): `try_resize` released a probe reservation and then allocated the table with `vec![0; n]`. If that second
  allocation was refused, Rust aborted. Fix: `zeroed_entries` (`src/tt.rs`) makes one `std::alloc::alloc_zeroed` call,
  checks for null, and returns `TableAllocError` on refusal. This is the only `unsafe` in `src/`; the invariants are in its
  doc comment (DESIGN_LOG "stretch 4", BENCHMARKING.md). The table stays lazily zeroed; `clear()` is no longer run on
  resize. Tests: unit `zeroed_entries_are_zero_and_sized`, `zeroed_entries_reject_impossible_sizes`,
  `try_resize_sets_the_entry_count_and_resets_counters`; process `hash_allocation_refusal_does_not_abort_the_engine`.
  Benchmark: first `go` 1.8–2.9 ms before and after; idle RSS 4.8 MiB before and after.
- F-22 FIXED (MINOR, protocol; found by CodeRabbit on `ce9f8d4`, `src/uci.rs:611`; reproduced): when the search thread
  was refused, `go infinite` (and `go ponder`, bare `go`) printed `bestmove` at once. Pre-fix build (debug copy of the
  pre-fix code): `bestmove a2a3` during the 1 s after `go infinite`, before `stop`. Fix: `pending_answer` holds the
  answer; `stop_and_join` prints it on `stop`, `quit`, EOF, or the next `go`, exactly once. Fixed-time and fixed-depth
  searches still answer at once, as before. Regression: `protocol_regressions::refused_thread_holds_bestmove_for_go_infinite_until_stop`
  (fails on the pre-fix code with "bestmove printed before stop", passes on the fix).
- REVIEW TRIAGE (CodeRabbit `ce9f8d4`, comments from 2026-11-20 that were still on the PR; checked against the current code):
  - `scripts/uci_malformed_probe.py` (every bestmove on the complete transcript): already handled. The probe counts all replies
    (`EXTRA_BESTMOVE`). Checked with a fake engine that prints each bestmove twice: the probe reports the extra replies.
  - `scripts/uci_protocol_probe.py` (count after draining): already handled. Same fake engine: `2 bestmove lines on stdout`
    failures.
  - `benches/movetime-20261119/measure_movetime.py` (cleanup when a measurement fails): already handled. `run()` runs the
    kill, wait, and close in a `finally` (lines 21-27), which covers `queue.Empty` and startup timeouts.
  - Codex `src/search.rs:283-284` (`searchmoves` with no legal named move): the F-09 design decision, kept (see above).
- F-21 STATUS UPDATE (append-only; the OPEN entry above is the record at discovery): FIXED in `7fe7e87`; the FIXED entry
  below it is the current status. CI on `d4b83a4` (run 44861510240) is green, including the Windows x64 artifact job.
- REVIEW NITPICK CLOSED (`tests/protocol_regressions.rs`, the stderr-failure test): the raw `extern "C" pipe` FFI and its
  two `unsafe` blocks were replaced by `std::os::unix::net::UnixStream::pair()` (std only; MSRV 1.80 is fine). The test
  file now has no `unsafe`. Mutation check: with `err_line!` changed to panic on a write error, the test FAILS
  (panic at `tests/protocol_regressions.rs`); `src/lib.rs` was restored (no diff).
- G3 (Windows x64 artifact) for `d4b83a4`: artifact `flawless-windows-x64-d4b83a4d633a73b9243c31ad71f777ac1d93298a`
  (id 14690190934, 211,600 bytes, API digest `sha256:91d435f32806122f85eaefd23c4e0e313dbe1efd7ad2bd2b795ec5e96d5d6a3c`).
  NOT VERIFIED: the download is blocked from this sandbox (the blob host is not on the outbound allowlist; EOF through
  `gh run download` and an SSL error on a direct request). The manifest and SHA256 of the zip are not checked. No Windows
  GUI test is part of the release.
- F-23 FIXED (MEDIUM, time management; found by the 2026-11-21 audit by reading `clock_limits`; reproduced in a unit
  test): the increment share `inc/2` was added after the division by `movestogo` and only clamped to the whole clock.
  With an increment larger than the clock, `soft` equalled the whole remaining time (`clock_limits(WHITE, 1000, 1000,
  2000, 2000, Some(40))` gave soft 1000 where the usable clock is 700), and `hard` followed. The GUI adds the increment
  after the move, so a move planned to use the whole clock could flag. This also broke the invariant written in the
  function's comment (planned spend <= t - reserve). Fix: `.min(usable)` before the floor and the clock clamp.
  Regression: `uci::tests::clock_limits_never_plan_past_the_usable_clock_with_large_increment` (failed before the fix,
  passes after; existing expected values unchanged). Process check (`wtime 1000 winc 2000`): bestmove after 0.36–0.40 s.
- F-24 FIXED (MEDIUM, time management; found by the 2026-11-21 audit by reading `cmd_ponderhit`; reproduced at process
  level): with a clock, `ponderhit` replaced the budget with a clock slice, but the search measured its elapsed time
  from `go`. Our clock runs only during our turn, so the time spent pondering on the opponent's move used up the slice:
  `go ponder wtime 20000 btime 20000`, 3 s of ponder, then `ponderhit` gave `bestmove` 2–5 ms later (the slice was about
  470 ms). Fix: `SearchLimits.clock_origin` (None = search start; `ponderhit` sets it to the hit); all budget checks and
  the iteration timing use `Searcher::budget_ms`; `info time` and nps still use the search start. Regression:
  `movetime_smoke::ponderhit_starts_the_clock_slice_at_the_hit` (fails on the old logic with "answered after only 2 ms",
  passes with the fix: about 1.87 s, the hard limit, because the iteration already running at the hit is cut only at the
  hard limit; see DESIGN_LOG stretch 6).
- F-25 FIXED (LOW, input validation; found by the 2026-11-21 audit with a FEN probe checked against python-chess
  `Board.is_valid()`): the FEN parser accepted a duplicated castling letter (`KK`) and any number of trailing fields
  (`… 0 1 extra`) without a notice. Fix: both are refused with `info string position error: fen: …` (R-07: the next `go`
  answers `bestmove 0000`). Regression: `position::ep_legality_tests::castling_letters_are_checked_for_form`,
  `position::ep_legality_tests::fen_with_extra_trailing_field_is_refused`. The mutation check (disable each check, expect
  the test to fail) was run on both.
- F-25 NOT CHANGED, decision for the owner: stale castling rights (a right whose king or rook is not on its home square,
  e.g. `4k3/8/8/8/8/8/8/4K3 w K - 0 1`) are still accepted. The contract is pinned by
  `tests/correctness.rs` (`stale_castling_rights_without_rooks_generate_no_castling`, comment "AUDIT-FEN-02"): they must
  never produce a castling move. Probe evidence: our `divide 1` move sets equal python-chess's `legal_moves` for eight
  stale or boundary FENs (counts 5, 16, 5, 26, 15, 26, 5, 5). Refusing them would change that contract, so it was not
  done silently; an owner decision is recorded in DESIGN_LOG (stretch 7).
- F-26 FIXED (LOW, UCI input; found by the 2026-11-21 audit's malformed-input probe): three silent cases.
  (a) `position startpos e2e4` (missing `moves`) searched the start position and dropped `e2e4` without a notice. Now refused
  with `info string position error: startpos takes no tokens before \`moves\``; `go` answers `bestmove 0000` (F-11/R-07).
  (b) An unknown option (`setoption name Clear Hash`) was reported only on stderr, and only when stderr logging was on.
  Now `info string unknown option: …` on stdout. (c) A `go` limit with a missing or bad value (`go depth`, `go depth abc`,
  `go nodes x`, …) was dropped silently, and a keyword after a missing value was consumed as the value: `go depth movetime
  100` lost `movetime`, so the search ran with no limit until `stop`. Now the bad value is reported on stdout
  (`info string go depth: missing or invalid value …; ignored`) and only the keyword is skipped. `go depth abc` alone still
  runs without a depth limit, as before (the value is ignored); that is the documented unbounded `go`.
  Regressions (tests/protocol_regressions.rs): `startpos_with_tokens_before_moves_is_refused_visibly`,
  `unknown_option_is_reported_on_stdout`, `go_bad_value_is_reported_and_the_next_keyword_survives`. Control: the same three
  tests run against the pre-fix tree (`60731d8`, exported with git archive) FAIL: no notice; no notice; bestmove never
  arrives (the unbounded search).
- RSS AT HASH 1024 (open item, closed with evidence; not a defect): `go movetime 1000` ×60 (seed 7) then `go movetime 500`
  ×200 (seed 99), on the fixed build: RSS 4 MiB idle, 247 MiB after 5 searches, 845 MiB after 60, 1029 MiB from search ~65
  and flat at 1029 MiB through search 200 (about 1024 MiB table plus baseline). No growth after the table is fully touched.
  Claim limited to this run (Linux sandbox); no leak was observed.
- F-26 addendum: a `go` token the engine does not act on is now reported on stdout (`info string go token ignored: …`), not
  only on stderr. `go mate N` is a standard UCI option that is NOT IMPLEMENTED: the search runs until `stop` as for a bare
  `go`, and the notice says so. Regression `unsupported_go_mate_is_reported_on_stdout` (fails on the pre-fix tree, passes on
  the fix). Implementing `go mate` is an open feature decision, not a defect fix; recorded in DESIGN_LOG stretch 8.
- VERIFICATION ADDED (2026-11-21, no defect; new probe scripts, committed in a78572d). Results below are only those
  that were run and recorded in this session: PV legality 150 positions / 900 PV lines at depth 6, seed 11, 0 failures
  (earlier run, `/tmp/audit/pv_legality.py`); PV legality repository run 40 positions / 160 lines, depth 4, seed 21, 0 failures
  (`scripts/pv_legality_probe.py`); mate-in-one 60 positions, seed 21, 0 failures (`scripts/mate1_probe.py`); MultiPV 3,
  20 positions, seed 21, 0 failures (`scripts/multipv_probe.py`). `scripts/clock_sweep_probe.py` was added but NOT yet run:
  no result is claimed for it. The FIDE insufficient-material unit test
  (`position::ep_legality_tests::insufficient_material_matches_the_fide_dead_positions`) passes; no random oracle run was recorded.
  An earlier draft of this entry claimed larger seed counts and oracle numbers that were not run; those claims were removed.
- F-27 FIXED (LOW, harness and test gaps; no engine defect), found by CodeRabbit review 6002624944 on `d4b83a4` (03:42Z,
  2 actionable): (a) `scripts/search_sweep.py` `next_line()` read the queue with a 0.1 s floor, so after the deadline a stream
  of `info` lines could keep it reading, and the child was not reaped on the timeout path. Now the remaining time is checked
  before each read, and every failure path kills and reaps the child. (b) `tests/protocol_regressions.rs`:
  `spawn_fallback_respects_searchmoves` and `refused_thread_holds_bestmove_for_go_infinite_until_stop` did not assert the
  "info string search thread unavailable" notice on stdout. Both now assert it. Mutation check (2026-11-21): replacing the
  notice text with `...unavailablX` in `src/uci.rs` fails exactly those two tests (21 pass, 2 fail); restored byte-for-byte.
  F-26 mutation (same session): restoring `60731d8`'s `src/uci.rs` fails 4 tests (`startpos_with_tokens_before_moves_is_refused_visibly`,
  `unknown_option_is_reported_on_stdout`, `go_bad_value_is_reported_and_the_next_keyword_survives`, and
  `unsupported_go_mate_is_reported_on_stdout`, which `330ebfa` added); restored byte-for-byte. `protocol_regressions` 23/0 on the fix.
- "ONE NODE" REPORT CLOSED AS A HARNESS ARTIFACT (2026-11-21; no engine change). Earlier probes sent `quit` right after
  `go`, so the search never started. On a clean release build of the current head, `/tmp/audit/wait_probe.py` (waits for
  `bestmove`): `6k1/5ppp/8/8/8/8/8/R5K1 w` `go depth 4` → 4 depth lines, `score mate 1`, `bestmove a1a8`; `go movetime 200` →
  17 depth lines, mate 1, `bestmove a1a8`; `4k3/8/8/8/8/8/8/R3K3 w` `go depth 3` → `bestmove a1a7`; startpos `go depth 4` →
  `cp 12`, 1,311 nodes, `bestmove b1c3`. Permanent regression added: `fixed_depth_search_finds_mate_in_one_and_reports_depth_lines`
  (waits for `bestmove`; asserts `bestmove a1a8`, a depth-4 line with `score mate 1`, and more than one node). It passes.
- GATE on f86f17f (2026-11-21, before F-28): 34/34 rc=0, dirty 0; release 122/0, debug 116/0 (`/tmp/gates/final-f86f17f/`).
- F-28 FIXED (LOW, UCI input silence; same class as F-26; found by the 2026-11-21 source audit of `cmd_setoption`,
  `cmd_go`, `cmd_position`, `ucinewgame`). Four cases: (a) a `setoption` with no `name`, or with an empty option name, was dropped
  without a word; now `info string setoption expects ...` / `names no option` on stdout. (b) `go searchmoves` with no move after it
  silently searched all moves; now announced (`searchmoves names no move; searching all legal moves`), and the search still runs.
  (c) a bare `position`, or `position moves ...` with no `startpos` or `fen`, was silent (the bare form kept the old position;
  the second searched the start position); now refused with `info string position error` and `go` answers `bestmove 0000`,
  matching other rejected positions. (d) `ucinewgame` replaced the board with the valid start position but kept the stale
  invalid flag, so the next `go` answered `bestmove 0000`; the flag is now cleared.
  Regressions: `malformed_setoption_is_reported_on_stdout`, `bare_searchmoves_is_announced_and_searches_all_moves`,
  `position_without_startpos_or_fen_is_refused_visibly`, `ucinewgame_clears_a_rejected_position`. Mutation check: restoring
  `f86f17f`'s `src/uci.rs` fails all four (24 pass, 4 fail); restored byte-for-byte. Protocol regressions 28/0 after the fix.
- GATE on f4b2a9e (2026-11-21, after F-28): 34/34 rc=0, dirty 0 (`/tmp/gates/final-f4b2a9e/`).
- TT STRESS (2026-11-21, new `scripts/tt_bestmove_probe.py`; one engine process, so the table is shared across searches;
  every bestmove legal per python-chess and equal to the first move of the deepest PV): 300 positions, depth 6, Hash 1, seed 1:
  0 failures. 1,000 positions, depth 7, Hash 1, seed 2: 0 failures. 1,000 positions, depth 6, Hash 64, seed 3: 0 failures.
- SCORE SIGN (2026-11-21): colour-flipped mate-in-one, `r5k1/8/8/8/8/8/5PPP/6K1 b`: `score mate 1`, `bestmove a8a1`, correct.
  A flipped FEN with the side to move attacking the king is refused with a notice (correct). A random search for a
  side-to-move-mated-in-one position found none (not a defect; no negative-mate check was run).
- NOT A DEFECT (2026-11-21): `position fen 8/P6k/8/8/8/8/8/K7 w` `go depth 2` returned `info nodes 1` / `bestmove a1b1` only when
  `quit` was sent right after `go`. Waiting for `bestmove` gives `bestmove a7a8q` (depth 2 +886, depth 6 stable). Harness artifact again.
- F-29 FIXED (LOW, debug builds only; found by the 2026-11-21 audit's unchecked-arithmetic scan): `Position::make_move` did
  `fullmove += 1` after a black move. A FEN with fullmove 4294967295 (accepted; the field is u32) and any black move panicked
  in a debug build ("attempt to add with overflow", position.rs:642), killing the engine on the main thread. A release build
  wrapped to 0 with no visible effect. Fix: `saturating_add`, as the halfmove clock already does. Regression:
  `position::ep_legality_tests::fullmove_counter_saturates_instead_of_overflowing` (debug). Mutation check: restoring `+= 1`
  fails the test with the overflow panic; restored. Debug suite after the fix: all pass (6 ignored are the release-only perft gates,
  run by `cargo test --release`).
- FRESH-SEED BATCH (2026-11-21, `/tmp/audit/k/fz2/summary.txt`, on f4b2a9e/F-28 build): `fuzz_uci_grammar` 33 (100 sessions) and 47
  (100): failures 0. `fuzz_legal_differential` 13 and 19: PASS. `perft_random_differential` 5 and 6 (30 games, depth 3): PASS.
  `search_sweep` 6 (50 positions, depth 4): PASS. `clock_sweep_probe` seed 9: 40/40 within the usable clock.
  `pv_legality_probe` 80 positions, depth 4, seed 31: 320 PV lines, 0 failures. `mate1_probe` 80 positions, seed 31: 0 failures.
  `multipv_probe` 20 positions, MultiPV 8, seed 31: 0 failures. `tt_bestmove_probe` 500 positions, Hash 1, depth 6, seed 4: 0 failures.
- F-30 FIXED (MEDIUM, robustness; found by the 2026-11-21 FEN extremes fuzzer, `scripts/fuzz_fen_extremes.py`, seed 9: the run
  hung at case 995): every refused `position` (and every oversized-line notice) was also written to stderr, unconditionally.
  A GUI that does not drain the engine's stderr fills the ~64 KiB pipe after several hundred refusals, and the engine then
  blocks in `write` and stops answering. Reproduced on f4b2a9e: 300 refusals answered; 1,000 refusals: no answer for the
  rest (harness timeout). Fix: stderr copies only after `debug on`; the search-panic stderr copy removed (stdout copy kept);
  "ended without result" and the table notices moved to stdout. Regression:
  `refused_positions_do_not_block_when_stderr_is_not_drained` (fails before the fix with "engine blocked on stderr?",
  passes after; 1,500 refusals). After the fix: `stderr_block` 1,000 of 1,000 answered; `fuzz_fen_extremes` seed 9, 1,000
  cases, release: 0 failures (the same run hung before the fix). The F-13 test sends `debug on` first so its path still runs.
  DESIGN_LOG stretch 9.
- F-31 NOT A DEFECT, recorded: `fuzz_fen_extremes` flagged two positions python-chess accepts and the engine refuses.
  (a) fullmove 4294967296: the engine stores fullmove as u32 and refuses a larger value with a notice (domain bound; the
  oracle now skips counters outside u16/u32). (b) `8/1r5N/R1rk4/pqp4P/b1pq3r/3pp1r1/3P3R/1KrB4 w`: black has 5 pawns (3
  missing), 5 rooks and 2 queens (4 promoted pieces): unreachable, refused by design; python-chess does not check this.
- CHECKED, NO DEFECT (2026-11-21): castling rights without the rook or king (10 FENs) match python-chess's move sets exactly.
  Fifty-move claim: `4k3/8/8/8/8/8/8/R3K3 w - - 100 60` gives `cp 0` at depth 3 (the side to move can claim the draw
  after white's move reaches halfmove 100, so every white move is worth at most 0 under the claim rule, as DESIGN_LOG R-12
  states); halfmove 96 and below give `cp 559`. Halfmove 100 with a mate in one still gives `mate 1` (mate precedence).
  MultiPV 5 with `searchmoves e1g1 a1a2`: exactly 2 lines, both restricted to the named moves.
- DEBUG BUILD (2026-11-21, `target/debug/flawless`, overflow checks on): `fuzz_uci_grammar` 61 and 73 (100 sessions each):
  failures 0. `fuzz_legal_differential` 23 (20 games): PASS. `tt_bestmove_probe` 200 positions, Hash 1, depth 4: 0 failures.
  `pv_legality_probe` 40 positions: 120 lines, 0 failures. `uci_malformed_probe` 37/37. `uci_extreme_args_probe`: 0 failures.
  `uci_protocol_probe` 12/12. `fullgame_en_passant_probe`: PASS (checkmate, every move legal). No panic in any run after F-29.
- GATE on a938e45 (2026-11-21, after F-30): 41/41 rc=0, dirty 0; release 128/0, debug 122/0. The gate adds `fuzz_fen_extremes`
  (seeds 9 and 3), `tt_bestmove_probe`, `clock_sweep_probe`, `pv_legality_probe`, `mate1_probe`, `multipv_probe` (`/tmp/gates/final-a938e45/`).
  CI on a938e45: CI 44873372449 success; anchor-verify 44873372453 success.
- F-32 OPEN, DEFECT, OWNER DECISION NEEDED (time management; found by `scripts/selfplay_clock_probe.py`, new, committed):
  the engine flags in sudden-death games with short clocks and no increment. Reproduced on ea942ac's binary, zero increment:
  base 1000 ms: white flagged at ply 110 (left −1 ms); base 300 ms: white flagged at ply 34 (left −1 ms); base 2000 ms: survives
  184 plies with 257 ms left (margin small); base 3000 ms + 50 ms inc, movestogo 40: no flag. Cause: ENGINE-1's soft limit
  `max(20 ms, (t − reserve)/mtg)`. For t < ~1.1 s (reserve 300 ms), the 20 ms floor exceeds the per-move share of the usable
  clock, so each move spends 20 ms until the reserve is drained, then the clock runs out.
  Why not fixed here: the formula is preregistered and frozen (PREREGISTRATION.md ENGINE-1, `engine_sha256` freeze, SCREEN-2
  provenance). Any change alters the engine hash and needs a new registration. `tests/clock_smoke.rs::tight_clock_returns_quickly`
  pins soft = 20 ms at 250 ms. The rating programme uses 40/15 (15 s base), which the floor does not touch.
  Candidate fix (prototype, not committed): floor = `min(20, t / (4·mtg))` instead of `20`. It changes soft only where the old
  floor binds with usable/mtg < 20 ms, that is t < ~1.1 s. Validation: see the entry below when run.
  Decision requested from the owner: (a) amend ENGINE-1 with a new preregistration and refreeze the hash; or (b) keep the formula
  and document that sudden-death clocks under ~1.1 s are unsupported.
- F-32 PROTOTYPE EVIDENCE (scratch copy only, not on the branch; 2026-11-21): candidate floor `max(min(20, t/(4·mtg)), 1)` instead of
  `max(20)`. Self-play (`selfplay_clock_probe.py`): 1000/0 → 165 plies, 387 ms left, no flag (old: flag at ply 110); 300/0 → 60 plies,
  no flag (old: flag at ply 34); 2000/0 → 157 plies, 608 left. Exact formula check: a Python mirror of `clock_limits` matches the
  Rust output on 4,515 (t, inc, movestogo) cases with 0 mismatches; the candidate changes 519 of them, all with t in 10..1090 ms.
  Existing unit test `uci::tests::clock_limits_respect_remaining_time` pins (20, 20) at t = 250 ms with the comment "20 ms floor
  moves", so the current floor is a pinned design choice, not an accident. That test fails under the candidate, as expected for a
  formula change, which is why the change is for the owner. Not committed.
- F-33 FIXED (LOW, documentation in tests; found while checking F-32): three comments in `tests/clock_smoke.rs` gave clock values
  from before ENGINE-1 (3000/40: "75 ms, hard 450"; 250/40: "hard 120"; 2000/10+50: "250 ms, hard 1500"). The assertions only check
  responsiveness and never used those numbers. Comments now give the values the code produces: 67/268, 20/20, 220/850.
- NEW PROBES, RESULTS (2026-11-21, release binary at 1ae5869 build):
  `scripts/fuzz_interleave.py` (stateful: go/stop/ponderhit/isready/position/setoption/ucinewgame in random order; every go must
  yield exactly one bestmove, every isready a readyok, no spurious bestmove, exit 0): seeds 1 (5×150), 2, 3, 4 (25×300 each),
  release: 0 failures. Seed 7 (20×300) on the debug build: 0 failures.
  `scripts/searchmoves_probe.py` (bestmove and every multipv-1 PV root inside the searchmoves set): 297 positions MultiPV 3 seed 1:
  0 failures; 300 positions MultiPV 1 seed 2: 0 failures; 197 positions MultiPV 8 seed 3: 0 failures.
- CAMPAIGN 1 (2026-11-21, `/tmp/campaign/run.sh`, release binary of 07dce9a plus debug copy; log `/tmp/campaign/out/summary.txt`):
  fen_extremes seeds 101–106 (400 each) 0 failures; fen_dbg seed 9 (debug, 150) 0 failures; interleave seeds 11–13 (25×300) 0;
  UCI grammar seeds 201–202 (100 sessions) 0; legal differential seeds 31–32 PASS; TT bestmove seeds 41–43 (400 each, depth 6) 0;
  searchmoves seeds 51–52 (299/298 positions) 0; perft random seeds 61–62 PASS; clock sweep seed 71 (60/60) 0; PV legality seed 81
  (120 positions, 600 PV lines) 0; mate-in-one seed 91 (120) 0; MultiPV seed 92 (k=4): 1 failure in 30 positions. See next entry.
- F-34 (PROBE BUG, not an engine defect; found by CAMPAIGN 1): `scripts/multipv_probe.py` mapped `score mate N` to
  `100000 - abs(N)·sign(N)`. For a mated line (`mate -2`) that gave +100002, which sorts above real cp scores, so the probe reported
  "scores not descending [-683, -901, 100002, 100002]" on FEN 1n1k2n1/r2p3r/1p1P1q2/1PpKN2P/4P3/2P4P/5P1R/BR6 w - - 1 37. Raw engine
  output for that position is correctly ordered (cp -683, cp -901, mate -2, mate -2; `bestmove e5c6`). Fix: mate N>0 → 100000−N,
  mate N<0 → −(100000+N). Verified by the mapping check (mate −2 → −99998, mate 2 → 99998). The assertion is unchanged. Re-run:
  seed 92 (k=4) 30/30 0 failures; seed 21 (k=3) 20/20 0 failures.
- NON-DEFECT (FEN clock fields, checked against python-chess 1.11.2): halfmove −1, fullmove −5, non-numeric, 2^64 and 2^32 values,
  and a seventh field are all refused with a specific `info string position error` (bad halfmove clock / bad fullmove number /
  expected at most 6 fields). Fullmove `0` and `+5 +1` are accepted, as python-chess accepts them (python-chess reads `0` as 1).
  Engine keeps the value 0; no effect on search or legality. Recorded, no code change.
- NON-DEFECT (movetime overrun): `go movetime N` finishes 1–7 ms over N for N in {0,1,5,20,50,100,300,1000}, 5 reps each, median ≤ 5.3 ms.
- NON-DEFECT (RSS at max settings, Hash 1024 + MultiPV 256): RSS 208 → 401 MiB over 25 searches, 414 MiB after 60, then 1029 MiB at round 69
  and flat after. A single step to the table size as its pages are touched; not a per-search leak (matches the earlier flat 1029 MiB
  at Hash 1024).
- NON-DEFECT (218-legal-move root, MultiPV 256): 218 `info ... multipv` lines, 218 distinct, `bestmove c1b3`, rc 0, 0.17 s.
- F-32 RISK MEASURED (2026-11-21, current binary 6b449c0; `scripts/selfplay_clock_probe.py`, 3 games each, 200-ply cap):
  zero increment, no movestogo (sudden death): base 300 ms: 3/3 games flagged (plies 32, 33, 34). Base 1000 ms: 2/3 flagged
  (plies 101, 114). Base 2000 ms: 1/3 flagged (ply 187; this game ended with 236 ms left for white). Base 5000 ms: 0/3.
  Other forms, no flag: 40000 ms with movestogo 40 (200 plies, 8.3 s left); 15000 ms + 150 ms inc with movestogo 40 (167 plies);
  60000 ms + 1000 ms inc (149 plies). So the defect is confined to sudden-death clocks under about 5 s with little or no increment.
  The registered 40/15 match is unaffected by this measurement. Earlier one-game results ("2000 ms survives") were too few to show
  the flag at 2 s; the 3-game figures above replace them.
- PONDER CHECK (non-defect): `go ponder wtime W` followed by `ponderhit` after a delay gives bestmove within the clock slice
  measured from the hit: W 300 → 14 ms; W 1000 (delay 200) → 82 ms; W 3000 (delay 500) → 269 ms (hard limit 268 ms); W 60000 → 1518 ms.
- NEGATIVE MATE (2026-11-21): the first `negative_mate_probe.py` draft expected `score mate -2` and failed 5/5 on positions where
  the engine printed `mate -1`. Checked with python-chess: in each position every legal move of the side to move allows an opponent
  mate in one, so the mate is one full move of the side to move, and UCI `score mate -1` is correct. The probe's assumption
  (counting plies as moves) was wrong; the engine was right. Also verified the convention on a constructed position
  (2r1qbnB/ppp1pp2/2k5/P1Pp4/3PQP1p/R1N4N/1P1B2PP/3K1BR1 b - - 0 30): engine `score mate -1`, legal bestmove. The probe was rewritten
  to expect `mate -1` and to construct positions with python-chess (every reply allows a mate in one). Result: 3/3 0 failures
  (seed 5). Seed 77: 12 positions constructed, 12 `mate -1` with legal bestmove, 0 failures.
- PM REPLY (2026-11-21): posted reply 4651140261 to CodeRabbit comment 4643719593 (tests/protocol_regressions.rs:339). The raw pipe FFI
  was removed in 17aedba; the file now has no `extern "C"`. The earlier note of this reply not being posted is closed.
- CI (2026-11-21): all completed jobs on ea942ac, a78572d, 0d14a08, f86f17f, f4b2a9e, 7287a2e, 199c92b are success; CodeRabbit check
  "skipped" on each (bot status on push, not a failure). c83046b: queued at time of check.
- RESOURCE / INPUT SIZE (2026-11-21, release): 60 KB setoption name → notice, answered at 0.00 s; 3000 repeated `e2e4` moves → first
  illegal move refused, answered at 0.00 s; 500 unknown setoptions → 500 notices; 200 KB token line → "input line exceeds 65536 bytes;
  ignored", engine still answers. No defect.
- RARE UCI PATHS (2026-11-21): `d`, unknown words, blank and whitespace lines are ignored without output; `register later` and
  `register name x code y` answer `registration ok`, which ARCHITECTURE.md (line 144) records as a deliberate choice; `go perft 2` is
  not a UCI command: the engine notes `go token ignored: perft` and `go token ignored: 2`, then searches. Not a defect; recorded
  because a GUI sending `go perft` gets a search, not a perft count.
- SECOND `go` WITHOUT `stop` (2026-11-21): `go infinite` then `go depth 3`: exactly one `bestmove` (after 10 info lines), no spurious
  answer for the superseded infinite search. UCI leaves this undefined and GUIs send `stop` first. Non-defect. Note: an earlier capture
  in this session printed two identical bestmove lines; that was a harness double-count (the reader loop re-read the same line), and
  the clean capture shows one.
- REPETITION (2026-11-21, release): (a) `ucinewgame` after warm searches: 3 positions, answers identical to a fresh engine (0 differ).
  (b) Same startpos reached by an 8-ply threefold shuffle vs from FEN: both cp 12, `b1c3`. Expected: the design scores in-tree
  repetition only at `ply > 0` (src/search.rs ~L535, ~L785), and the root is always searched (test `root_repetition_is_searched`,
  search.rs ~L1120). Non-defect. (c) After Nf3 Nf6 Ng1 (black to move, a repetition available inside the tree), the engine plays
  `b8c6` at cp 65 rather than taking the drawing line, consistent with draw scores compared against the alternative. Non-defect.
- GO NUMERIC PARSING, DEBUG BUILD (2026-11-21, `/tmp/campaign/flawless_dbg`, overflow checks on): 570 `go` lines (each key × 17
  edge values including 2^32, 2^64, 2^64+1, i64 limits, `+7`, empty, `0x10`, `1e9`, `1_000`, plus 400 random multi-key lines). Each
  `go` was followed at once by `stop`, so the test covers parsing and immediate-stop arithmetic, not long searches. Result: 0 missing
  bestmove, 0 panics, stderr 0 bytes, `isready` answered, rc 0. Non-defect.
- FULL GAMES (2026-11-21, release, `fullgame_en_passant_probe.py --max-plies 400`): default movetime 20 ms: 110 plies, en_passant 1,
  castles 2, promotions 1, CHECKMATE 0-1. Movetime sweep (5, 10, 30, 60, 120 ms): 133 plies CHECKMATE 1-0 (ep 1, castles 2, promo 1);
  271 plies CHECKMATE 1-0 (ep 1, castles 2, promo 1); 72 plies CHECKMATE 0-1 (ep 1, castles 2, promo 0); 96 plies THREEFOLD_REPETITION
  1/2-1/2 (ep 1, castles 2, promo 0); 175 plies CHECKMATE 1-0 (ep 1, castles 2, promo 1). All PASS: every engine move legal under
  python-chess. The probe varies only the time budget from a fixed opening, so variety is narrower than random play.
- F-32 RESOLVED (2026-11-21; owner decision "Amend ENGINE-1 and fix"; formal record PREREGISTRATION.md CLOCK-1 and DESIGN_LOG.md 2026-11-21):
  change in `src/uci.rs` `clock_limits`: soft floor `20 ms` → `clamp(t/(4·movestogo), 1, 20)`; `movestogo` multiplied with `saturating_mul` (overflow found while reviewing this change; the existing code had no such multiply, the new floor would have introduced one).
  Regressions: `clock_floor_f32_short_clock_keeps_reserve_over_a_period` (40 moves at 2 ms overhead from 300/500/800/1000/1100 ms keep half the reserve), `clock_floor_f32_exact_values_below_the_old_floor_range` (300→(1,1), 1000→(17,68), 800→(12,48), 3000→(67,268)), `clock_floor_f32_huge_movestogo_does_not_overflow`. Pinned value `clock_limits_respect_remaining_time` 250 ms updated `(20,20)` → `(1,1)`.
  Mutation (restore `.max(20)` in a scratch copy): exact-value, period, and respect-remaining tests FAIL (period: "move plans 16 ms of 14 ms (start 300)" = clock below zero; exact: left (20, 20) right (1, 1)).
  Unit tests: clock filter 8/8 pass on the fix. Full release 131/0; debug 125/0 (6 perft gates ignored in debug by design).
  Self-play (same 3-game series that flagged before, now on the fixed release binary, `selfplay_clock_probe.py`): 300 ms 3/3 clean (63 plies, 196–240 ms left); 1000 ms 3/3 clean (115–200 plies, 329–512 ms left); 2000 ms 3/3 clean (176–200 plies, 397–632 ms left). Other forms clean: 5000 ms 0 flags (192 plies); 15000+150 movestogo 40 ×2 clean (200 plies, 6.9–7.9 s left); 60000+1000 clean.
  Scope: `clock_limits` grid, 25,680 points, old vs new: 1,776 changed, all `t ≤ 1495`, all explained by the old 20 ms floor. 40/15 point unchanged.
  Clock probes on the fixed binary: `clock_sweep_probe.py` 30/30 within the usable clock (seed 71); `time_budget_probe.py` 8/8.
  Cost recorded: total thinking time per game falls on short clocks (300 ms: ~0.2 s; 1 s: ~1.1–1.4 s). Not measured in Elo.
  Naming: the amendment is CLOCK-1. "ENGINE-2" is already the SEE candidate in PREREGISTRATION.md and is not reused.
  Gate and CI for this change: recorded in the next entry, on the final head.
- CORRECTION to the F-32 RESOLVED entry (2026-11-21): that entry says an overflow was "found" while reviewing the change. That was wrong. No overflow was reproduced. `movestogo` was multiplied with `saturating_mul` as a precaution, because the new floor multiplies `movestogo` by 4. The regression `clock_floor_f32_huge_movestogo_does_not_overflow` covers that path.
- GATE RUNNER (2026-11-21): `scripts/final_gate.sh <out_dir>` runs the full local gate on the current HEAD and records the commit, the tree, the release binary SHA-256, each step's return code, and a dirty-tree check. Added so that the gate is versioned with the code. The earlier gate scripts in /tmp were lost in a workspace reset on 2026-11-21 and are not used.
- GATE RUN 1 on 56329fb (2026-11-21): stopped. Configuration error, not an engine result: the runner used the system `python3`, which lacks python-chess, so every probe that needs the oracle failed with `ModuleNotFoundError: No module named 'chess'`. Logs kept in /tmp/gates/final-56329fb (not evidence of the engine). Fix: the runner now defaults to `$HOME/.venv/bin/python3` when present. Gate re-run on the commit that contains the fix.
- GATE RUN 2 — PASS on 1e46819 (2026-11-21, `scripts/final_gate.sh /tmp/gates/final-1e46819`):
  commit 1e46819cf4b9ac7ba8433b546f99130c0810f9af; tree d8e675c9141becf014d550313ed0e75c691652a6; dirty 0 at start and end; 45 steps, 0 non-zero return codes, FAILS=0.
  Release binary SHA-256 c44cde869b8cc43af7b412ee34121be4e6394abae8cd39f51ebeb251752e09ff.
  Steps: fmt; clippy debug and release (-D warnings); build release and debug; cargo test --release 131 passed / 0 failed; cargo test (debug) 125 passed / 0 failed / 6 ignored (perft gates, debug by design); 9 Python test suites (aggregate_60, make_batch_dispatch, match 111 checks, merge_batch_runs, power_analysis, rating_estimator 65 checks, recover_download, reduced_sample 7/7, windows_artifact); perft random seeds 10, 11 PASS; legal differential seed 31 PASS; search sweep seed 4 PASS; uci protocol 12/12; malformed 37/37; extreme args 0 failures; UCI grammar seed 201 (100 sessions) 0; interleave seed 11 (25x300) 0; interleave debug seed 7 0; resource probe (Hash 1024, 200 ms) peak RSS 24.0 MiB; FEN extremes seed 101 (400) 0; FEN extremes debug seed 9 (150) 0; TT bestmove seeds 41 (Hash 1) and 43 (Hash 64) 0; searchmoves seed 51 0; PV legality seed 81 (600 lines) 0; mate-in-one seed 91 0; MultiPV seed 92 (k=4) 0; negative mate seed 77 (12 positions) 0; clock sweep seed 71 60/60; time budget 8/8; self-play sudden death 1000 ms clean (121 plies), 300 ms clean (63 plies), 15000+150 movestogo 40 clean (200 plies); full games en passant (movetime 20 ms and 60 ms) PASS.
  CI on 1e46819: CI 44884807385 success (ubuntu-latest, windows-latest, msrv 1.80, windows x64 release artifact); anchor-verify 44884807376 success; check-runs include verify-flawless success and the build-* jobs success. Kilo Code Review: action_required (billing block, not bypassed).
  Source identity: src/, tests/, Cargo.toml, Cargo.lock, rust-toolchain.toml are the gated tree; later commits are docs and ledger only (verified before the final head is recorded).
- INPUT EDGE CASES (2026-11-21, release 1e46819 binary; reader-thread harness; a first version of this harness used select() on a buffered pipe and read one line per session, so its output is discarded): CRLF line endings → uciok, readyok; NUL byte after `startpos` → `info string position error: fen: expected at least 4 fields, got 1`, `bestmove 0000`; NUL inside a FEN → `invalid piece char '\0'`, `bestmove 0000`; NUL in setoption name → readyok; leading NUL bytes line → ignored, readyok; `go depth 2` before any `position` → searches the start position (`bestmove b1c3 ponder b8c6`). All rc 0, stderr 0 bytes. Non-defects.
- G3 WINDOWS ARTIFACT (2026-11-21): NOT VERIFIED. Artifact `flawless-windows-x64-1e46819cf4b9ac7ba8433b546f99130c0810f9af` exists on run 44884807385 (212,820 bytes; API digest sha256:fd594239b75965f50253527be3adb5432537a12cde1c4e86981cfb5655456d83). `gh run download` (one attempt) failed: `error downloading ...: Get "https://productionresultssa17.blob.core.windows.net/...` (blob storage, same class as earlier attempts). Not retried in a loop. The artifact's content has not been downloaded, so its manifest and SHA-256 are not verified here.
- F-35 FIXED (LOW, reporting; found in review of the `info` line code, reproduced in output): when a search had taken 0 ms, `info ... nodes 43 nps 43 time 0` printed the bare node count as `nps`, while the next line read `nodes 146 nps 146000 time 1`. A GUI shows that as a 43 nps rate. Fix: `nps_of(nodes, elapsed_ms) = nodes*1000 / max(elapsed_ms, 1)` (src/uci.rs). Regression `info_nps_is_a_rate_when_no_time_has_passed` (43,0 → 43000; 146,1 → 146000; 146,2 → 73000; saturation). Mutation (old `checked_div(...).unwrap_or(nodes)` restored in a scratch copy): FAILS, left 43, right 43000. After the fix, live check on 20 info lines from 4 searches (depth 4, depth 5 after moves, movetime 30, nodes 3000): nps == nodes*1000/max(time,1) on every line; 4 lines at time 0.
- STOP LATENCY (2026-11-21, release, go infinite then stop, 12 trials each): default Hash 64 / MultiPV 1: median 0.4 ms, max 0.5 ms; Hash 1024 / MultiPV 1: median 0.4, max 0.5; Hash 64 / MultiPV 256: median 0.8, max 1.2; Hash 1024 / MultiPV 256: median 0.7, max 1.0. 0 missing bestmove. Non-defect.

- F-36 FIXED (LOW, CLI; found 2026-11-21 in audit by comparing `perft` and `divide` at depth 0): `flawless divide 0` printed one line per root move with count 1 and `total = 20`, while `perft 0` prints 1. Cause: `perft_divide` computes `perft(depth.saturating_sub(1))`, so at depth 0 each root move counts as perft(0) = 1 and the total is the number of root moves. The engine's perft and movegen are correct at depth 0 and were not changed. Fix in `src/main.rs` `cmd_divide`: depth must be ≥ 1 (`.filter(|&d| d >= 1)`); otherwise usage on stderr and exit 2, the same path as a missing depth. Regression: `tests/cli_divide.rs` (3 tests: depth 0 refused with rc 2 and no total or per-move lines; depth 1 totals 20; depth 2 totals 400). Mutation check (filter removed in a scratch copy) FAILED `divide_depth_zero_is_refused_with_usage` as intended ("divide 0 must exit with usage status 2"). `cargo test --release --test cli_divide` 3/0.
- DECISION (2026-11-21, not a defect): `flawless moves` exits 0 when a stdin line is a bad FEN. It prints `error: fen: ...` for that line and keeps reading. This is the F-12 batch contract (one reply line per input line; a bad line does not stop the batch), and `hash` follows the same pattern. `perft` and `divide` are single-shot commands and exit 1 on a bad FEN. No doc sets an exit-code contract for batch mode, so the behaviour is kept. A caller that needs per-line status reads the `error:` lines.
- TIME EXTREMES (2026-11-21, release build made after the F-36 edit, so it includes F-36; the F-36 `divide 0` check above ran on the binary before that build; `scripts/time_extremes_probe.py`, reader thread, 1.5 s wait then stop): `go movetime 2^63-1` and `2^64-1`: no bestmove in 1.5 s, bestmove 0.1 ms after stop. `movetime 18446744073709551616` (2^64, overflows u64): same, because overflowing digit strings saturate to `u64::MAX` by design in `parse_time_ms`. `movetime -1`: immediate bestmove (negative → 0). `wtime 1000 btime 1000 movestogo 2^64-1`, `movestogo 0`, and `wtime 3000 btime 3000 movestogo 2^63`: immediate bestmove within the time budget. `wtime/btime/winc/binc 2^63-1 movestogo 1`: no bestmove in 1.5 s, bestmove 0.1 ms after stop. stderr empty and rc 0 in every case. All behave as designed. Non-defect. (An earlier version of the probe closed stdin right after `go`, so the search ended by EOF. That run is discarded; it does not test time handling.)
- AUDIT PROBES (2026-11-21, release, non-defects unless stated): `divide` per-move counts and totals vs python-chess, 5 FENs × depths 1–2 (Kiwipete, pos3, pos4, pos5, startpos): 10/10 match, 0 mismatches. `hash`: transposition (Nf3 Nf6 Nc3 vs Nc3 Nf6 Nf3) equal; en passant without a capturer equals no-ep; capturable ep differs; halfmove clock ignored; side, castling differ; bad FEN rc 1 and stdin bad line → `error bogus`, batch continues. `bench` deterministic: two runs, same signature (849a85bf7e8e1eba) and node counts. Ponder: `ponderhit` idle, `stop` idle, `go ponder` + `stop`, `go ponder depth 3` + `ponderhit`, `go ponder nodes 5000` + `ponderhit`, double `ponderhit`: no crash, rc 0, exactly one bestmove where a search ran. Note: the probe wrote `go` and `stop` together, so `stop` arrived before depth 1 finished; the answer `b1a3` is a legal depth-1 result, not a defect (with a 1.2 s delay the answer is `b1c3`, three runs).
- OPEN, NOT CHANGED (see DESIGN_LOG 2026-11-21 audit entry): `go ponder movetime 1000`, `ponderhit` after 4 s of pondering → bestmove at 0.0 s. The movetime is counted from `go`. Pinned by test; spec ambiguous; owner decision.
- GATE on 000266e (2026-11-21, `scripts/final_gate.sh /tmp/gates/final-000266e`): commit 000266ec8d29b6fbc4958a133e67ecff3424825d; tree b369cf7976e8264965fe30210058e7aacc294025; dirty 0 at start and end; 45 steps, 0 non-zero return codes, FAILS=0. Release SHA-256 0d9c508d31e15170921641eedd59735a0a14c15f8ad17472c084848dc9663a6d (changed from c44cde… because `src/main.rs` (F-36) changed). Release tests 34+3+3+3+3+40 passed, 0 failed (see test_release.log); debug 34 passed, 6 ignored (perft gates in debug by design). CI on 000266e (run 44886526755) success; anchor-verify (44886526780) success. Same CI success on ad000f1 (44886396899, 44886396909) and c52c13b (44886186210, 44886186211).
- FRESH-SEED CAMPAIGN (2026-11-21, release binary at 000266e; seeds not used by the gate): perft random 12, 13 (20 games, depth 3) PASS; legal differential 32, 33 (40 games each) PASS; search sweep seed 6 (40) PASS; UCI grammar seed 202 (100 sessions) 0 failures; interleave seed 12 (25×300) 0; FEN extremes seeds 102 (400) and debug 10 (150) 0; TT bestmove seed 44 (hash 16) 0; searchmoves seed 52 0; PV legality seed 82 (120 positions, 720 lines) 0; mate-in-one seed 92 0; MultiPV seed 93 (k=4) 0; negative mate seed 78 0; clock sweep seed 72 60/60; UCI malformed 37/37; extreme args 0. Summary /tmp/fresh/summary.txt (scratch, not in repo). 18 of 18 rc 0.
- SELF-PLAY CLOCK (2026-11-21, release 000266e, `selfplay_clock_probe.py`, python-chess legality): base/inc (movestogo): 200/0: 63 plies, min left 96 ms; 500/0: 150 plies, min 257 ms; 1000/50: 150 plies, min 994 ms; 3000/0: 120 plies, min 894 ms; 400/20 (mtg 10): 150 plies, min 361 ms; 10000/100 (mtg 1): 60 plies, min 397 ms. failures 0 in all six. (F-32 flags were at 300–2000 ms; this series also covers 200 ms and movestogo 1.)
- DEEP SEARCH (2026-11-21, release): `go depth 100`, `255`, `4294967295`, `64`, `200` on startpos, Kiwipete, and K v K: all rc 0, stderr empty, stop-to-bestmove 7.5–7.7 ms. Depth is clamped to 1..64 by design (uci.rs `clamp(1, 64)`, DESIGN_LOG). K v K ends by itself at depth 64 (256 nodes). `go depth 4294967296` saturates to the same clamp. Six endgames at `go depth 64` with stop after 4 s (K+R v K, KP v K, KRP v KR-like rook ending, KP promotion race, Q mate in one, Q v K with black to move): each rc 0, legal bestmove, depth 19–26, stderr empty.
- PROTOCOL RACES (2026-11-21, release): `go infinite` then `position fen …` then `stop`: bestmove legal in the start position (the search keeps its own position). `go infinite wtime 500 btime 500`: no bestmove at 500 ms (infinite overrides the clock, as UCI says). `wtime 0 btime 0` and `wtime 1 btime 1`: immediate legal bestmove. `go nodes 1000 movetime 60000` and `go depth 3 movetime 60000`: end at the node or depth limit, not at the time limit. `setoption name MULTIPV value 2` (lower-case and mixed-case names are accepted) produces multipv 2 lines.
- INSUFFICIENT MATERIAL (2026-11-21, release): K v K, K+B v K, K+N v K, K+B v K+B same-colour bishops: `score cp 0` at every depth (FIDE dead draw). K+R v K: cp 537. Positions K+B v K+B (opposite colour) and K+N+N v K are ILLEGAL as written (the side to move attacks the enemy king), and the engine refuses them with `position error: fen: side to move is attacking the opponent's king`, `bestmove 0000`. Non-defect.
- F-14 RE-CHECK (2026-11-21): an apparent regression (`info nodes 1` and no PV for K v K) came from the probe, not the engine. Piping `printf … | flawless` closes stdin at once, and EOF during a search stops it before the first iteration (stdin EOF = quit, as Stockfish). With stdin held open (`sleep 1; quit`), K v K prints depth 1–4 with `pv e1d1` and `score cp 0`. The protocol regression `insufficient_material_root_is_searched_and_yields_a_pv` passes. Non-defect.
- STATIC PANIC REVIEW (2026-11-21, non-test code in src/): unwrap/expect/unreachable sites checked: `uci.rs` `searchmoves` unwrap follows an `is_some` check; `uci.rs` worker `take().unwrap()` follows an `is_none` return; `main.rs` bench FENs are constants; `position.rs` FEN writer `from_digit(1..=8)`; `position.rs` `unmake` expect and occupancy `unreachable!` are internal invariants; `tt.rs` `panic!` on allocation failure is the CLI `TranspositionTable::new` path (UCI uses `try_new`/`try_resize`). A worker panic is caught (`catch_unwind`) and answered with the fallback bestmove, so `stop` cannot hang. Non-defect.
- TT MOVE SAFETY (2026-11-21, read of src/search.rs): the TT move is used only to order moves that are already in `generate_legal`; a colliding key cannot put an illegal move on the board. Non-defect.
- OBSERVATION, NOT A DEFECT (perf, low): `Position::repetition_count` (position.rs ~L816) scans the whole `history`, not only since the last irreversible move. Results are the same (a position before a capture or pawn move cannot have the same Zobrist key, given material, pawn structure, or castling differ), so only speed is affected: a linear scan per node. Not changed this stretch; a candidate for a later, measured change.
- `bench` determinism, `divide`/`hash` checks, ponder probes: see the AUDIT PROBES entry above.
- CORRECTION to the GATE on 000266e entry (2026-11-21): the per-binary numbers there were mis-summed. The totals from `/tmp/gates/final-000266e/test_release.log` and `test_debug.log` are: release 135 passed, 0 failed, 0 ignored (10 result lines, incl. doc-tests); debug 129 passed, 0 failed, 6 ignored (perft gates, debug by design). The gate's FAILS=0 and the 45/45 rc=0 result stand.
- SOAK (2026-11-21, release 000266e binary, seeds 300–319 grammar and interleave, seeds 800–819 FEN extremes; 300 cases each): 60 of 60 steps rc 0, failures 0 (`/tmp/soak/summary.txt`, scratch). Grammar: 100 sessions per seed. Interleave: 25 sessions × 300 steps per seed.
- TACTICS (2026-11-21, release, `go depth 6`, python-chess checks the move): back-rank mate `a1a8` (mate 1); free queen `d1d5` (cp 541); queen hanging to a pawn, `d5e4` (black); Qxf7# `h5f7` (mate 1); mate with queen `g2a8` (python-chess: checkmate; `g2g8` is blocked by g7, so it was my expectation error, not an engine error). All legal. (A first attempt of this check was discarded: `subprocess.run` closed stdin right after `go`, which stops the search at once and returns the fallback first move. Re-run with stdin held open.)
- STRAY COMMANDS (2026-11-21, release): after a finished `go depth 1`, `stop`, `stop`, and `ponderhit` print nothing; the next `go depth 1` prints exactly one `bestmove`. Non-defect.
- RECOVERY (2026-11-21, release): `position startpos moves e2e5` (error, `bestmove 0000` for the following `go`), then a valid `position`: the next `go` answers `bestmove b8c6`. Non-defect.
- HASH RESIZE COST (2026-11-21, release): `setoption name Hash value 1024` then `isready`: 0 ms; RSS 4 MiB; first `go depth 1` 1 ms. The table is lazily zeroed. Non-defect.
- OUTPUT ATOMICITY (2026-11-21, read of src/lib.rs): `out_line!` holds the stdout lock for the whole `writeln!`, so lines from the search thread and the main thread cannot interleave. Non-defect.
- CLOCK-1 HASH FREEZE: attempted and NOT done. See PREREGISTRATION.md "CLOCK-1 binary identity freeze — ATTEMPTED, NOT FROZEN".
- CODERABBIT (2026-11-21): the request on 72dcf78 got "Head commit changed" (comment 7060057149), not run. New request on 3b26382: comment 7060490619. Result not yet read at this entry.
- F-37 FIXED (harness, found by CodeRabbit review 6004451960 on 2fe1118; verified in code and by reproduction; engine not changed):
  (a) `scripts/selfplay_clock_probe.py` checked for a flag AFTER adding the increment, and truncated the measured time to whole milliseconds. A move that overran the remaining clock by less than the increment was accepted (reproduced: base 100, increment 50, engine answering after 120 ms → old logic: 100−120+50 = 30, no flag; new logic: `left W -20`, `FAIL ply 0: white flagged (-20.5 ms)`, rc 1). The earlier self-play series with increments (including the gate's `selfplay_40_15`, 15000+150) therefore could not have shown this class of flag. The engine did not overrun in any of those runs, but the evidence was not capable of showing it.
  (b) Blocking stdout reads in `selfplay_clock_probe.py` and `tt_bestmove_probe.py` had no deadline: a stalled engine hung the probe. Fix: new `scripts/probe_io.py` (reader thread + queue; `read_until(prefix, timeout)`; `close()` always quits, kills, and reaps). Reproduced: a stalled fake engine now fails with `no 'bestmove' within 2 s` and exit status −9, no hang.
  (c) `scripts/final_gate.sh` end check only tested for a clean worktree. A checkout change during the run could pass. Fix: `head_unchanged_at_end` requires HEAD == recorded commit, tree == recorded tree, and a clean status.
  Re-run of the self-play series with the fixed probe (release 000266e binary; same engine source): sudden death 200/0 (63 plies, min 87 ms), 300/0 (63, min 184), 500/0 (150, min 248), 1000/0 (67, min 596), 2000/0 (200, min 482), 3000/0 (120, min 775), 5000/0 (150, min 1281); increments 1000/50 (63, min 841), 400/20 mtg 10 (142, min 344), 10000/100 mtg 1 (60, min 297), 15000/150 mtg 40 (152, min 6832), 60000/1000 (93, min 38272); all failures 0, flags 0, illegal 0. TT probe re-run on the new harness: 40 positions, hash 1, depth 6, failures 0.
  Still open (same class, not yet changed in this entry): other probe scripts that read stdout without a deadline (listed in the next entry).
- F-38 FIXED (harness, 2026-11-21; engine not changed): the seven remaining probes that read engine stdout without a deadline now use `scripts/probe_io.py`. Converted: `clock_sweep_probe.py` (one engine per case), `mate1_probe.py`, `multipv_probe.py`, `pv_legality_probe.py` (one-shot via `search_lines`, which always closes the engine), `negative_mate_probe.py` and `searchmoves_probe.py` (persistent engine, `read_until` with 60 s), `fuzz_fen_extremes.py` (persistent engine; a TimeoutError ends the run as a recorded failure, a crash is recorded and the engine restarted; exit status after quit is checked). Every wait now has a deadline and `close()` always runs.
  Verification (release binary, built from source identical to 000266e): clock sweep 6/6 (`71`), mate-in-one 5/5 (`91`), MultiPV 4 positions, 0 failures (`92`), PV legality 4 positions/24 lines, 0 failures (`81`), negative mate 4/4 (`77`), searchmoves 10 positions, 0 failures (`51`), FEN extremes seed 101 × 20, 0 failures.
  Stall test (`/tmp/fake_stall.py`, never answers `go`): `mate1_probe.py` exits 1 after 60 s with `no 'bestmove' within 60 s`; `fuzz_fen_extremes.py` exits 1 after one timeout (`no bestmove: ...`, then kill), no hang.
  The remaining stdout readers (`eval_symmetry_probe.py`, `fuzz_interleave.py`, `time_budget_probe.py`, `time_extremes_probe.py`, `uci_extreme_args_probe.py`, `uci_malformed_probe.py`, `uci_protocol_probe.py`, `windows_artifact.py`) are reader threads feeding a queue with a deadline on the main side; read at 09:59 UTC, not changed.
- F-39 FIXED (found by audit, 2026-11-21; confirmed on the release binary before the change): `go depth 4294967296`, `go depth 99999999999999999999`, `go depth -4294967296`, `go nodes 18446744073709551616` and `go nodes -1` printed `info string ... missing or invalid value ...; ignored` and then ran a search with no limit until `stop` (the `infinite` flag is set when no depth, nodes, movetime or clock is given). `go depth 100` already stopped at 64, so the same kind of value behaved differently by size. Fix in `src/uci.rs`: `parse_depth` saturates digit-only overflow to `i32::MAX` (clamped to 64) and negatives to `i32::MIN` (clamped to 1); `nodes` uses the saturating u64 parser that `wtime`/`movetime` already use (overflow → u64::MAX, negative → 0). Regression tests: `out_of_range_go_depth_and_nodes_saturate_instead_of_being_ignored` and `negative_go_depth_and_nodes_answer_at_once` (both time out on the pre-fix source, pass after the fix). Release tests 137 passed (was 135), `fmt`, `clippy -D warnings` clean.
- CORRECTION (append-only; 2026-11-21, re-checked against `/tmp/sp2/*.log` and a fresh run of the release binary):
  (a) The ledger entry "DEEP SEARCH" above said "`go depth 4294967296` saturates to the same clamp". That was NOT true before F-39: the value was ignored and the search was unlimited. After F-39 it is true (`parse_depth`). Verified after the fix: `go depth 4294967296` on `k7/8/8/8/8/8/8/K7 w - - 0 1` → `info depth 64 ... nodes 256` and `bestmove a1b1`, with no stop.
  (b) "K v K ends by itself at depth 64 (256 nodes)" holds for one position only. Fresh runs at `go depth 64`, release 000266e-equivalent source: `k7/8/8/8/8/8/8/K7 w - - 0 1` → 256 nodes; `8/8/8/4k3/8/8/8/4K3 w - - 0 1` → 384 nodes; `8/8/8/4k3/8/8/8/4K3 b - - 0 1` → 576 nodes (all end by themselves, time 0–1 ms). Pass.
  (c) The SELF-PLAY CLOCK entry above (min remaining clock 96, 257, 994, 894, 361 and 397 ms) came from the pre-F-37 probe, and `/tmp/sp/summary.txt` keeps only rc lines, so those margins cannot be re-derived from a saved log. They are NOT used. The current figures from the F-37 re-run (`/tmp/sp2`, release, 0 failures, 0 flags) are: 200/0 min 87 ms; 300/0 min 184; 500/0 min 248; 1000/0 min 596; 3000/0 min 775; 5000/0 min 1281; 1000/50 min 841; 400/20 mtg 10 min 344; 10000/100 mtg 1 min 297; 15000/150 mtg 40 min 6832; 60000/1000 min 38272 (`/tmp/sp2/summary.txt`).
- CLOCK-1 FREEZE ROUTE (2026-11-21, 10:30 UTC): the hosted `verify-flawless` line `binary_sha256=…` IS readable through the check-run annotations (`gh api repos/coderunknow/FlawLessChess/check-runs/<job-id>/annotations`): job 136810042858 (run 44892126479, head eb8fca3) → `binary_sha256=689b0f0150236bc630c67d340e985085982a9db6b5cfa87f26aea7b089219bda bench_signature=849a85bf7e8e1eba` (commit printed `a56c4c3d…`, the PR merge commit); job 136792890005 (run 44886526780, head 000266e) → its annotation text; the 08:47Z run for commit 16209719 printed the same binary hash. Nothing frozen yet: F-39 changed src/, so the freeze must use the final head's build. Caveat for the freeze entry: anchor-verify checks out the PR merge commit; the merge tree differs from the head tree only by main's `.gitattributes` (one line, `benches/` files). The hash is therefore for the head's source only if that line does not affect the build (it does not touch src/ or Cargo).
- LIMITATION (2026-11-21, not changed): `go mate N` and `go perft N` are unsupported. The keyword and value are reported with `info string go token ignored`, and the search runs until `stop`. The UCI `mate` mode is not implemented.
- CORRECTION to the CLOCK-1 FREEZE ROUTE entry above (append-only, 2026-11-21 10:20 UTC): the time was 10:19 UTC, not 10:30. The annotation of job 136792890005 (run 44886526780, anchor for source `000266e`) reads `=== verify-flawless (2026-11-21T08:47:56Z) === commit=16209719c3b5b32a2b7104bcd4897ed2d9319312 binary_sha256=689b0f0150236bc630c67d340e985085982a9db6b5cfa87f26aea7b089219bda bench_signature=849a85bf7e8e1eba`. The commit is the PR merge commit that run built, not `000266e`. Run 44892126479 (head eb8fca3, same engine source as 000266e) gives the same binary hash `689b0f01…` for merge commit `a56c4c3d…`. Two different merge commits with one binary hash: consistent with identical src trees. No freeze is recorded here: the final source (after F-39) will have its own hash, and that freeze must be recorded on the final head.
- F-40 FIXED (resource, found by audit 2026-11-21 by reading `src/tt.rs` and checking the README's claim; confirmed by a unit test on the pre-fix code path): `TranspositionTable::try_resize` rounded the entry count UP to a power of two (`(bytes/8).clamp(1024, 2^27).next_power_of_two()`). A Hash value that is not a power of two therefore allocated more than the GUI requested: `Hash 65` → 128 MiB, `Hash 129` → 256 MiB, `Hash 513` → 1 GiB, while the engine reported the requested value. Fix: round DOWN (`prev_power_of_two`), so the table never exceeds the request and is at least half of it (1 GiB cap unchanged). Power-of-two sizes (1, 16, 64, 1024 MiB) are unchanged: bench `849a85bf7e8e1eba` (2311437 nodes) before and after. Tests: `tt::size_tests_f40::allocated_table_never_exceeds_the_requested_size` (sizes 1…4096 MiB), `power_of_two_sizes_are_unchanged`. Release tests 139 passed (was 137), fmt and clippy clean.
  Note: the background soak (`/tmp/audit2/soak.sh`) was running while the binary was rebuilt. Steps that started before the rebuild used the F-39 binary, later steps used the F-40 binary. Both are recorded in the soak summary; the final gate re-runs everything on the final head.
- PROBE ARTIFACT (not a defect, 2026-11-21): a probe that wrote the whole input file at once (`cat` with `sleep` in the writer, then `flawless < file`) sent `stop` right after `go depth 64`; the engine answered `info nodes 0` and `bestmove a1b1` with no search. Re-run with the input streamed (`(cat file; sleep 3; echo stop) | flawless`): `info depth 7 … multipv 1..256`, `bestmove e2a6`. Same class as the earlier stop-before-search note. Non-defect.
- MID-SEARCH RACES (2026-11-21, release 64c691b-era binary, `/tmp/audit2/race_midsearch.py`, seeds 1–3, 120 rounds each): during `go infinite` / `go depth N` / `go wtime…`, random `setoption Hash` (1, 16, 64, 1024), `Clear Hash`, `MultiPV` (1, 2, 5), `ucinewgame`, `position`, `isready`, then `stop`: exactly one `bestmove` per `go`, no extra `bestmove`, no `0000`, exit 0 at every seed. 170–190 mid-search operations per seed. Non-defect.
- README CHECK (2026-11-21): README says the TT is capped at 1 GiB (2^27 entries) and entries are 8 bytes: matches `src/tt.rs` (`Entry` = u64). README says Windows CI runs fmt, clippy, tests, release build, UCI handshake and perft sanity: that is what the Linux `ci` job runs; the Windows job builds, checks PE architecture, and smoke-tests the exe (`scripts/windows_artifact.py`). Wording in README line 73 is broader than the Windows job. Recorded; README wording to be corrected in the release-doc step.
- CORRECTION to the README CHECK entry above (2026-11-21): the README Windows claim is ACCURATE. `ci.yml` job `test` has `os: [ubuntu-latest, windows-latest]` and runs fmt, clippy, tests (release), release build, UCI handshake, bestmove smoke test, protocol probes, resource probe and perft sanity on both. The separate Windows job adds the PE check, the exe smoke test and the artifact. No README change needed for this line.
- F-41 FIXED (search, found by audit 2026-11-21 with a mate-distance oracle on random endgames; cause shown by instrumenting the root with temporary prints, removed again): futility pruning at depth <= 2 (`search.rs`, "Futility pruning at low depths") compared the static evaluation with alpha without a mate-bound guard. With alpha at a mate score (e.g. after a mate-in-3 was found), every ordinary line looks futile, so the quiet mating move was pruned before it was searched. Example `8/3K4/8/2R5/8/8/7k/1R6 w - - 0 1`, `go depth 6`: before the fix `score mate 3` via `c5c3`; the shortest mate is `c5g5` (1. Rg5 Kh3 2. Rh1#), which the search now reports as `score mate 2 … pv c5g5 h2h3 b1h1`. Reverse futility and null-move already had `MATE_BOUND` guards; this one did not. Fix: `&& alpha.abs() < MATE_BOUND`. Regression test `quiet_mate_in_two_is_not_pruned_by_a_mate_alpha` (fails on the pre-fix source with `mate 3`, passes after).
  Bench: signature `849a85bf7e8e1eba` UNCHANGED (the signature covers fen, depth and bestmove only; the 12 bench bestmoves are the same); node count 2311437 → 2354774 (the node count is not part of the signature).
  New probe `scripts/mate_distance_probe.py` (python-chess proves the minimal mate in 1 or 2; the engine's `go depth 6` `score mate N` must equal N; every wait has a deadline). Results with the fixed binary: seed 1, 120 positions: 0 failures (mate1 33, mate2 87); seed 2: 1 failure; seed 3 (before the rewrite, scratch version): 1 failure. Before the fix, seed 1 (scratch version) had 10 failures and seed 3 11.
- OPEN, OWNER DECISION (NOT CHANGED): the remaining failures are all LMR misses. The reduction (`lmr[depth][count]`, child depth = depth-1-r, up to depth-1 from `clamp(0, depth-1)`) is applied to quiet moves that give check or are the only way to mate, with no exemption for checking moves. A quiet mate needs the child at depth >= 2 for mate in 2, so reduction 2 at depth 3 (child depth 0 = quiescence, which does not search quiet checks) and reduction 4 at depth 6 (child depth 1) hide the mate. Examples: `8/3K4/8/2R5/8/8/7k/1R6 w - - 0 1` at `go depth 3` (Rg5 is move 25, reduction 2); `5R2/8/8/3K4/1Q6/7k/8/8 w - - 0 1` at `go depth 6` (f8g8 is move 43, reduction 4, the mate is 1. Qb4xx… proven by python-chess as f8g8, h3h2, b4h4#); `4k3/8/8/5K2/6R1/2Q5/8/8 w - - 0 1` at depth 6 (f5e6 reduced). Fixing it (not reducing checking moves, and/or child depth >= 2) changes bestmoves, so the bench signature `849a85bf7e8e1eba` changes. That signature is pinned in `.github/workflows/anchor-verify.yml` and the CLOCK-1 identity work, so the change needs an owner decision (ENGINE-1 / CLOCK-1 governance). Not changed in this audit. The mate probe is not a gate row for this reason.
- F-42 (search, defensive, 2026-11-21): quiescence delta pruning (`sp + capture_gain + promo_gain + 200 < alpha`) had no mate-bound guard, the same gap as F-41. A capture that mates is worth MATE, so the margin test could prune it against a mate-score alpha. Fix: `alpha.abs() < MATE_BOUND &&` in front of the test. NOT REPRODUCED: 720 mate-distance probe positions (six seeds, 120 each) give the same failure count with the pre-fix and the post-fix binary (`/tmp/audit2`), and the bench signature `849a85bf7e8e1eba` is unchanged. Kept as the same rule as F-41; no regression test, because no position was found where it changes the result.
- CORRECTION to the F-41 OPEN entry above (append-only): the example line for `5R2/8/8/3K4/1Q6/7k/8/8 w - - 0 1` read "the mate is 1. Qb4xx… proven by python-chess as f8g8, h3h2, b4h4#". The proven mate-in-2 first move is `f8g8` (Black's only reply `h3h2`, then `b4h4#`). The example stands; the first move and the reply are as stated here.
- F-41 OWNER DECISION, MEASURED (2026-11-21, scratch copies in /tmp/audit2/exp; NOT applied to the repo). Baseline = HEAD `aa8eb8a` (futility guard F-41, quiescence guard F-42). Bench = `flawless bench` (12 positions, depth 10); oracle = `scripts/mate_distance_probe.py` (120 positions, depth 6):
  - baseline: bench signature `849a85bf7e8e1eba`, 2354774 nodes; oracle seed 2: 1 failure, seed 3: 1 failure.
  - A (no LMR for moves that give check, `in_check` after make_move): bench signature CHANGES to `141943aa23b3fc68` (bestmoves change; that value is the ENGINE-2 SEE-candidate signature in PREREGISTRATION.md, shown only as a fact); 3256820 nodes; oracle seeds 2 and 3: 1 and 1 failures (not fixed).
  - B (reduction ≤ depth−2, i.e. reduced child depth ≥ 1): signature `849a85bf7e8e1eba` unchanged; 2427488 nodes; oracle seeds 2 and 3: 1 and 1 failures (not fixed). Note: this does not keep the child at depth 2; the mate needs child depth ≥ 2 (reduction ≤ depth−3).
  - C (reduction ≤ depth−3, i.e. reduced child depth ≥ 2): signature `849a85bf7e8e1eba` unchanged; 3364367 nodes (+43% over baseline on the bench); oracle seeds 2 and 3: 0 and 0 failures (fixes all the known LMR misses).
  Recommendation for the owner: C fixes the misses with the bestmoves unchanged, at about 43% more nodes at fixed depth (roughly a 30% slower search at equal time). The choice between correctness at depth 3–6 and speed is a strength decision. Not applied: it changes engine speed and play, which is outside the amendment already made (CLOCK-1). If applied, it needs a new engine identity (hash, bench nodes) on the final head and a new preregistration entry.
- VERIFICATION (2026-11-21, no engine change): incremental Zobrist hash vs `zobrist_full()` across make/unmake, captures, promotions, en passant, and null moves: 24489 checks (4 FENs incl. ep `d6`, 150 seeds each, depth 40 single path), 0 mismatches. Scratch test in /tmp/audit2/hashchk/tests/zz_hash_null.rs, not in the repo. A first version branched on both null and move at each level (2^depth) and timed out; that was a harness bug, fixed before the result above.
- F-43 (scripts, no engine change): the main-side wait after `kill()` was unbounded in five probes (`eval_symmetry_probe.py`, `windows_artifact.py`, `probe_io.py`, `uci_protocol_probe.py`, `uci_malformed_probe.py`). Converted to `wait(timeout=10)` with the warning/pass path. Every other main-side wait in the eight listed reader-thread scripts already had a timeout (queue get with a deadline, `wait(timeout=…)`, `join(5)`). `uci_protocol_probe.py` 12/12 and `uci_malformed_probe.py` 37/37 pass after the edit.
- Gate `/tmp/gates/final-61ef017`: 45/45 FAILS=0, `head_unchanged_at_end` clean at 61ef017 (tree 769e898d), debug and release `cargo test` ok, clippy both profiles, fmt. Engine source at 61ef017 equals aa8eb8a (only the ledger changed). The F-43 script edits came after this gate run and need a gate on the final head.
- CI / anchor on committed heads (check-runs): 9086001, 6000601, 038249f, aa8eb8a, 61ef017 — all `verify-flawless` success; all check runs success except CodeRabbit `skipped` and Kilo Code Review `action_required` (billing; not bypassed). CI runs: 44894379829 (9086001), 44894391765 (6000601), 44895147186 (038249f), 44895467811 (aa8eb8a), 44895871701 (61ef017) success; anchor runs 44894379803, 44894391743, 44895147138, 44895467771, 44895871679 success.
- PROVENANCE (append-only, CodeRabbit review 6004886452 on 0e65b22; no engine change):
  - F-38 probe results: the converted probes are at commit `eb8fca3`. Raw gate output: `/tmp/gates/final-eb8fca3/summary.txt`. That path is in the sandbox `/tmp`, outside the repo, and may not survive a reset; the repo does not hold the raw transcripts.
  - F-39 before/after: the test changes are at commit `64c691b` (`tests/protocol_regressions.rs`). The raw before-fix transcript is UNAVAILABLE: it was not saved to the workspace. The after-fix result (release tests 137 passed at `64c691b`) is recorded above.
  - F-40 allocation tests and bench: the code and tests are at commit `9086001` (`tt::size_tests_f40::*`, release 139 passed). The raw allocation/bench transcripts are UNAVAILABLE in the repo; the bench signature `849a85bf7e8e1eba` at that commit is the only retained value.
  - F-41 / F-42 / F-43: revision `aa8eb8a` (F-41 guard and F-42 quiescence guard), `61ef017` (ledger), `0e65b22` (F-43 script bounds, F-43 gate). Gate `/tmp/gates/final-0e65b22/summary.txt`: 45/45, FAILS=0. Same sandbox-`/tmp` caveat.
  - F-43 scope correction: the bounded-reap change covers more files than the first entry listed. The review-driven change of the same day also closes engines on failure in `fuzz_fen_extremes.py` (`start()`), `negative_mate_probe.py` and `searchmoves_probe.py` (try/finally), `uci_malformed_probe.py` (bounded `finally`), and `probe_io.py` (`search_lines` now raises on a nonzero exit status after the reply; the `finally` reap is bounded). `mate_distance_probe.py` now fails an incomplete sample (`checked` < requested). Post-edit checks: `uci_malformed_probe.py` 37/37; `mate_distance_probe.py 1 20` 0 failures; `negative_mate_probe.py 3 1` 0 failures; `searchmoves_probe.py 30 1` 0 failures; `mate1_probe.py 30 1` 0 failures.
