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
