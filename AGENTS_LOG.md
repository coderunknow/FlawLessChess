# AGENTS_LOG.md (append-only)

## 2026-11-14 — Session start (Phase 0)

- Agent: autonomous principal engineer (Arena Agent Mode).
- Actions: repository inspection (git status/log/branch/remote); environment probe; network reachability
  matrix; Rust 1.99.0 installed from npm under `/home/user/.toolchain/sysroot`; python-chess 1.11.2 in
  `/home/user/.venv` as test-only oracle (GPL-3.0+).
- Starting SHA: `98b1a00203183d9c7ccb175f7d6eb8f5ef5eb429`. No files modified at inspection time.
- Created: STATUS.md, AGENTS.md, ARCHITECTURE.md (RFC), docs/ENVIRONMENT.md, docs/adr/0001,
  DESIGN_LOG.md, AGENTS_LOG.md, FAILURE_LEDGER.md placeholder, initial docs skeleton.
- Next: Phase 2 — Rust project scaffold, bitboards, FEN, movegen, make/unmake, perft.

## 2026-11-14 — Phase 3/4/UCI session

- Built: eval.rs (tapered classical), tt.rs (Zobrist 8B TT), search.rs (ID/PVS/aspiration/quiescence/
  null-move/futility/LMR/killers/history/MultiPV/TT-PV), uci.rs (worker-thread search, stop/ponder/
  ponderhit, Hash/Threads/MultiPV options, clock time management soft/hard with movestogo clamp).
- main.rs: added `uci`, `eval [fen]` (breakdown), `bench_eval` subcommands.
- Build: `cargo build --release` clean (one unused-const warning, fixed). `cargo test --release` 14/14 PASS.
- Smoke tests: UCI handshake; mate-in-1 found (`bestmove b1b8`); Kiwipete MultiPV 3 to depth 10;
  abort/stop/ponderhit paths verified with nonblocking stdin reader; ~0.9M nps; 2 vCPU sandbox.
- Fixed two UCI-layer bugs found by smoke testing: (1) bestmove only printed on next stdin command
  (UCI protocol violation) → worker now prints bestmove directly; (2) mate-score formatting could
  overflow (`mate 499`) → clamped; (3) aborted root scores were used to build result → discarded.
- Committed: pending (this checkpoint not yet committed — see STATUS.md "Next preregistered task").

## 2026-11-14 — CI + benchmark harness + LMR panic fix

- Set up `.github/workflows/ci.yml` (Ubuntu+Windows: fmt, clippy -D warnings, release tests,
  release build, UCI handshake, perft d3). CI green on PR #1 (both OSs). Kilo bot: insufficient
  credits (not a code issue).
- Smoke match exposed LMR table out-of-bounds panic → engine silently lost on time.
  Fixed table bounds + worker catch_unwind fallback bestmove. 2-game smoke: engine wins both.
- Wrote match.py/stats.py + 20 verified openings; launched probe-001 (40 games vs SF 19 WASM,
  Skill 0, movetime 100ms) in background.
- Raw evidence committed to benches/ for reproducibility.

## 2026-11-14 — CI + probes session (cont.)

- PR #1 opened (branch pushed). CI: ubuntu-latest + windows-latest both green (fmt/clippy/tests/
  release build/UCI handshake/perft d3). Third-party Kilo bot: insufficient credits — reported as
  not a code issue.
- probes 001/002/003 committed with raw PGN/JSONL evidence.
- UCI fuzz (6 trials × 25 random commands, grammar of 30) — 0 crashes/hangs.
- Engine bracket: between SF-Skill-5 and SF-Skill-10 (pinned SF 19 WASM, 100 ms/move). No absolute
  rating claim; v1.0.0 gates untouched.

## 2026-11-14 — Environment rebuild + strength experiment

- Sandbox workspace was re-materialized (git HEAD reverted to 98b1a00; toolchain/venv/opponents lost).
  Restored branch ref + index from origin (tip 1dc2500) — working tree matched exactly, nothing lost.
  Toolchain reinstalled from npm (same versions); venv + python-chess reinstalled; pinned SF WASM
  re-fetched and hash-verified identical. FAILURE_LEDGER entry recorded.
- Re-ran all gates post-rebuild: fmt/clippy/tests/diftest PASSED; CI still green (PR #1).
- Implemented `cargo run --release -- bench` (fixed depth 10, 12 positions, deterministic signature).
- Search experiment: RFP + check extensions. All gates pass. A/B: +80 Elo (CI [-9,+168], 40 games).
- probe-004 (RFP+CE build) vs SF Skill 5, 40 games @100ms: 14/14/12 score 0.525 (CI [0.412,0.637]).

## 2026-11-14 — Identity migration to Flawless

- `flawless` package/binary/crate; `id name Flawless`; `id author coderunknow (Apache-2.0)`.
- CI workflow smoke tests de-masked (removed `|| true` swallowers); binary path updated.
- Historical raw evidence keeps the old identifiers by policy (see ADR-0002).
- Environment note: sandbox workspace was re-materialized (git HEAD → 98b1a00, toolchain/venv/
  opponents lost); restored branch ref + index from origin (a01fcaf), rebuilt toolchain from npm
  (rustc/cargo 1.99.0), and re-verified lld execute bits for linking; episode recorded in
  FAILURE_LEDGER.md.
- Repository was observed as `coderunknow/Flawless-Chess-Engine` (externally renamed); the old
  URL auto-redirects. This project did not and does not rename the repository.

## 2026-11-14 — Audit passes 1-2, docs integrity, panic-fallback e2e verification

- b85b3f7 FAILED CI (Clippy `write_with_newline` — shell pipe hid it locally); fixed in 837361f;
  lesson recorded: never chain a gating command through a pipe that swallows its exit status;
  CI is the backstop, not the first line of defense.
- CI for head-era commits: 43562935232 (b4acfcd SUCCESS), 43563085939 (bbb31f9 SUCCESS),
  43563499046 (b85b3f7 FAILURE), 43563628232 (44c8369 SUCCESS).
- Panic-fallback path verified end-to-end with a synthetic panic engine: games flagged
  engine_error=true with engine_error_turns; stats.py excludes them ("no scorable games after
  exclusions"). Normal 4-game match unaffected (4/4 vs SF19-lite Skill 0 @ 100ms).
- Match runner harvest fix (early-return paths dropped panic markers) committed 972161d.
- Docs integrity pass: ARCHITECTURE TT 16→8 bytes, SEE claims removed (zero SEE in code; roadmap),
  CLI docs match reality, fuzz status made reproducible (tests/uci_smoke.rs), ENVIRONMENT
  snapshot-restore runbook, RATING_PROTOCOL.md pre-registered (not executed; gate BLOCKED).
- 2026-11-14 commit b85b3f7 also contained a corrupted shell-chained clippy run; 837361f is the fix.
- 2026-11-14 workspace restore wiped target/ + toolchain + venv (~07:43Z); git repaired via
  `git fetch origin` (tip 13a316e) + re-applied uncommitted fixes; zero history lost.
- 2026-11-14 Copilot cloud agent pushed 6c749d8 (rustfmt fix identical to concurrent local work);
  its push did not auto-trigger CI; this session re-triggered CI with a log-only push. Never merged.
- 2026-11-14 local toolchain unavailable offline; rustfmt canonicality verified via npm WASM
  rustfmt (rustfmt@0.1.0) + CI; DIFTEST/bench re-verification PENDING until toolchain returns.
- 2026-11-14 MSRV job green with RUSTUP_TOOLCHAIN=1.80.0 + --locked (msrv job: 1.80.0 accepted
  the ep-hash/UCI changes without code changes).
- 2026-11-14 CI root cause via annotations-only channel: clippy `-D` driver args need the
  `cargo clippy ... -- -D warnings` separator; removing it produced `unexpected argument '-D'
  found`, masked as a clippy failure until json→`::error::` annotations surfaced it; real error
  was clippy::manual_range_contains @ src/position.rs:699 (fixed 2c777b5). CI fully green since
  2c777b5 / cd9b7d9 (msrv + ubuntu + windows). When logs are blocked, use the
  check-runs annotations API; do NOT retry gh run view --log / gh run download (blob storage EOF).
- 2026-11-14 workspace restore #3: toolchain/venv/opponents/node_modules wiped; full npm rebuild
  per docs/ENVIRONMENT.md (verified byte-identical SF WASM hashes); tests 29/29, diftest PASSED,
  bench signature unchanged fc907eba40b7869f with 2,221,199 nodes (-43%); clippy too_many_arguments
  fixed via StoreRequest; CodeRabbit 5903125228 (13 findings) dispositioned in source/docs;
  RATING_PROTOCOL Amendment §9 (strict > 2,000; both batches + combined pass; ≥2,000
  games/anchor/batch) appended; CI now uploads bench signature + binary SHA-256 + manifest.

- 2026-11-14 (rating-infra segment): workspace restore #4 clobbered local git to 98b1a00 +
  wiped .venv/toolchain; recovered history via `git fetch` + `git reset origin/<branch>`
  (working tree byte-identical to 0b70906, zero loss). PR #1 returned to Draft (gh pr ready
  --undo) — the earlier "not marked ready" claim was wrong; GitHub had it open/non-draft.
  match.py v2: clock TC (--tc 40/15 repeating, movestogo, elapsed charging, flag, ponder off,
  add/reset policy), 60x17x2 scheduling + shard slicing, engine-error record/immediate-replay/
  abort-after-2, move-cap unadjudicated, manifest v2 (pre + finalized), suite hash, anchor-schema
  hardening. scripts/test_match.py 104/104. tests/clock_smoke.rs + uci clock_limits tests: cargo
  33/33, clippy/fmt clean. scripts/rating_estimator.py (§9.6-9.8 joint bootstrap/GLS/combined/
  null-controls/fail-closed gate) + scripts/test_rating_estimator.py 46/46; scripts/aggregate_shards.py
  (fail-closed §5.2 rules, smoke-verified). Workflows: anchor-research.yml (CCRL 40/15 fetch from
  hosted runner), rating-run.yml, rating-gate.yml (stable fail-closed rating-gate job). Toolchain
  rebuilt from npm (rustc/cargo/clippy/rustfmt 1.99.0; remember chmod +x on bin/ and
  lib/rustlib/*/bin/* — npm strips exec bits and the linker needs gcc-ld/ld.lld executable).

- 2026-11-14 (seg 10 continued — anchor research → verified build ladder):
  anchor-research.yml extended 4× (error-convention extraction, candidate version rows,
  release-tag probes, lower-band rows, homepage links [regex fixed after empty match],
  full tag lists, buildable-family rows). Runner annotations (check 132426702372 /
  132427366210 / 132428391521 / 4ab675d-series) delivered: error convention "95% confidence
  intervals" (→ pool error_convention ci95); version↔rating maps for akimbo/Topple/Weiss/
  Demolito/FabChess/Igel/Halogen/Stash/Pirarucu/Raven/WyldChess/Monolith/Carballo; 342
  lower-band rows (1700–2200). Sandbox CAN reach api.github.com + codeload.github.com →
  tag verification + source downloads done locally. Built + UCI-smoked 4 anchors locally:
  Raven 0.50 (2081±25, id-string "Raven 0.40" caveat), Topple v0.2.1 (2439±14, exact id),
  akimbo v0.1.1 (2441±19, exact id), WyldChess v1.2 (2445±21). Ladder rungs identified:
  Raven 0.70 (2242), Topple 0.1.1 (2324), Raven 0.80 (2341), Raven 0.90 (2451), WyldChess 1.1
  (2474). Excluded with reason: Carballo 0.5/0.8 (no tags before v0.9), Pirarucu (Kotlin
  toolchain unreachable), Counter/CounterGo (version mapping ambiguous). Leads pending
  identity verification: Vice 1.0 (1997±21), Monolith 0.3 (2387), Daydreamer 1.5 (2298),
  Stash 14.0 (2085). benches/anchor-research-20261114.md records all provenance. STATUS.md
  Rating-status section updated (blocker + next actions revised). DESIGN_LOG adversarial
  review entry added (mission §3.8). Commits: 5823fff, d25b683, 82ca55b, 4ab675d, + docs.

- 2026-11-14 (seg 11 — anchor verification complete; pool frozen): workspace restore #5
  recovered via fetch+reset (d023ee8 intact on origin). Lower-band identity research:
  Vice 1.0 unverifiable (bluefeversoft/vice = "Vice 1.2" + Chapter 97+ branches only),
  Rival 1.18/Bubble 1.5/Schola 1.1.0 no verifiable repos (exclusions recorded), wowl 1.3.7
  FOUND (eric-ycw/wowl tag v1.3.7, MIT, CCRL 1849±22/630g). Built all ladder candidates
  locally (11 binaries; 3 hash-reproducible across the restore). anchor-verify.yml written
  (matrix rebuild + UCI id + SHA-256 + LICENSE + verify-flawless bench-signature + SF10
  calibration vs i7-4770K reference 2054ms/3,939,338 nodes from Tors3/CCRL_ScirptsTests).
  5 runner failures diagnosed and fixed via annotations (see FAILURE_LEDGER 2026-11-14 entry).
  Ravens excluded (no license at tested revisions). SF10 factor k=1.0291 → 40/15 wall-clock
  within ~3% of CCRL equivalence. RUNNER-VERIFIED POOL FROZEN: benches/anchor-pool.json
  (Wowl 1.3.7=1849±22, Topple 0.1.1=2324±17, Topple 0.2.1=2439±14, akimbo 0.1.1=2441±19,
  WyldChess 1.2=2445±21, WyldChess 1.1=2474±21; all ci95; run 43597866181 artifacts).
  rating-run.yml acquire step implemented (artifact download + hash-verify, rebuild fallback).
  MERGE_READINESS.md created (§7 checklist with evidence). Local gates: pool schema ✓ (match.py
  fail-closed validator), YAML ✓, test_match 104/104, test_rating_estimator 46/46, cargo 33/33.
  Commits: 5b2cc78, 5a77079, 59c8a0c, 5fd73b1, 086feb8, 0d8287b + this.
254. designed + implemented rating-run dispatch mechanism from the actual repo state (marker-file `benches/dispatch.json` + strict `resolve` job + matrix fan-out); fixed leftover fail-closed `exit 1` stub in the acquire step (would have failed every shard after successful verification); engine hash policy: pilot uses "freeze" (first runner build records hash), confirmatory requires literal frozen hash; wrote PREREGISTRATION.md with PILOT-1 (4 games, 2 shards x 2, excluded from gate evidence) BEFORE dispatch; local validation: YAML OK, dispatch schema OK, suite hash 2c4a54d8... matches, sh syntax OK.
255. dispatched PILOT-1 via marker-file push (workflow: rating-run, paths filter benches/dispatch.json); local engine build at 1127969 rustc 1.99.0 = 9d7b22d5d1af0c56b0d56f908edd679b8628d90126d2fe5efc3c4faf24144208 (local only — runner hash is the one that will be frozen via annotations/manifest).
256. run 43601528240 (c9399fd): resolve+checkout+build+freeze+suite+anchor-acquisition all GREEN (engine freeze hash fd75726dd3166640ddec75d94c416320b47c83e8d14bfa6309aed398d55b8e1d, reproducible across 2 runner builds); match.py step exited 2 (argparse: 'unrecognized arguments: uci') — ROOT-CAUSED LOCALLY: shell word-splitting of --white-cmd './target/release/flawless uci' (match.py splits the single cmd string internally); fixed step to drive match.py via python argv list + stderr->annotations capture (run logs unreachable from sandbox: blob endpoints EOF; annotations API is the working observation channel). dispatch.json rev 3 pins the frozen engine hash; re-dispatched.
257. PR-thread dispositions completed (verified against current code, replies + resolution via GraphQL addPullRequestReviewThreadReply/resolveReviewThread): DS covariance=valid/fixed (§9.6-8 + joint-bootstrap GLS estimator), DW Windows pipe=valid/fixed (reader-thread+Event), D5 TT halfmove=valid/fixed (tt.rs flag + regression), D- uci.rs:433 race=INVALID as described (flush-mutex proof) + NEW jittered stress regression ponderhit_or_stop_racing_search_end_emits_exactly_one_bestmove (30 trials, exactly-once bestmove without follow-up input), EC uci_smoke drain=valid/fixed (post-exit drain_reader + full-line scan). All 11 review threads resolved. Full suites: Rust 34 (lib 6 incl. tt regression + clock_smoke 3 + correctness 21 + uci_smoke 4), test_match 104/104, test_rating_estimator 46/46. MERGE_READINESS updated (2 checkboxes ticked with evidence).
258. registered CTRL-1 + CTRL-2 null controls in PREREGISTRATION.md BEFORE dispatch (thresholds = mission-defined: CTRL-1 published diff within +/-75 Elo; CTRL-2 0.5 within 95% binomial CI); generalized rating-run.yml engine slots (white_engine/black_engine: 'flawless' or pool key; confirmatory constrained to flawless-vs-anchor; control must use batch CTRL); dispatched CTRL-1 (rev 4): topple-0.1.1 vs topple-0.2.1, 240 games, 120 shards x 2, seed 20261115.
259. dispatched CTRL-2 (rev 5): flawless vs flawless self-match, 240 games, 120 shards x 2, seed 20261116.
260. dispatch-mechanism semantics hardened: GitHub's pull_request paths filter matches the WHOLE PR diff (dispatch.json differs from main forever) -> every push re-triggered the marker config; additionally the 4bb6016 push event (CTRL-1 rev 4) was DROPPED entirely by GitHub (no workflow ran; rapid successive pushes) so CTRL-1 never dispatched, while 9e01bf1 (no marker change) re-dispatched the pilot config (run 43603558950; cancel blocked: 403 actions:write — it runs to completion, extra exploratory data only). FIX: resolve now requires the TOP commit of the push to touch benches/dispatch.json ("dispatch push" = one commit moving the marker), else run=false and the shard matrix skips. Re-dispatched CTRL-1 as rev 6 (identical config).
261. estimator match-identity fix: frozen pool `name` fields are non-unique (two 'Topple', two 'WyldChess') while match.py records game engine names = pool `key`; added `anchor_label(entry)` (key-first, name fallback) at all game-matching sites in rating_estimator.py (batch_estimate lookup, control_anchor_vs_anchor, run_gate + control CLI lookups) — frozen pool kept BYTE-IDENTICAL; regression test `test_anchor_label_key_matching` (4 checks). aggregate_shards.py: mixed-runner hardware now WARNING + recorded (documented mixed environment: Azure EPYC 9V74 / AWS Xeon 6975P-C; metadata not identity; transferability validated by null controls; missing hardware record still fails). Suites via CORRECT runners: test_rating_estimator 50/50, test_match 104/104. NOTE correction: earlier "unittest" gate invocations ran 0 tests (see FAILURE_LEDGER false-green entry) — CI always ran the real runners.
262. added `evidence` job to rating-run.yml: after all shards of a dispatch succeed, a runner downloads the run's shard artifacts (blob endpoints unreachable from the sandbox), runs the STRICT aggregate_shards.py (fail-closed hash/TC/suite/shard-count checks), and bot-commits raw per-game evidence (benches/evidence/<purpose>/<label>/games.jsonl + manifest.json w/ merged_sha256) to the PR branch with rebase-retry — satisfies RATING_PROTOCOL §1.3 'reproducible from committed raw evidence' and makes evidence readable by the analysis stage. In-flight runs (pilots, CTRL-1/CTRL-2) predate this job -> a standalone evidence-bridge dispatch will collect them after completion (planned next). YAML OK.
263. wrote evidence-bridge.yml (collects artifacts from EXISTING runs: fail-closed on run completed+success, strict aggregation, disjoint evidence dirs per run, marker-file dispatch on benches/evidence-request.json with the same top-commit gate). Planned entries once runs complete: pilot 43602273258 -> evidence_purpose 'pilot'; duplicate pilot 43603558950 -> 'pilot-dup'; CTRL-2 43603826611; CTRL-1 43604654709.
264. STATUS.md checkpoint written (pre-waiting-boundary, exact next actions + missing evidence); PR #1 body refreshed via REST PATCH (pipeline/review/open items accurate at f2176b6).
265. PILOT-1 COMPLETED (run 43602273258, success 14:56:12Z): both shards 2/2 games; match step 13:57:13→14:56:06 (58.9 min / 2 games = **29.5 min/game measured**); engine hash annotations confirm fd75726d... at ac909e9. Throughput: 2 games/hr/shard; 8-game shards ≈ 4h/job fit the 330-min cap with margin (batch shard design: 255 shards x 8 games = 2,040). Evidence-request rev1 pushed to collect the pilot's raw games via evidence-bridge (run 43602273258 -> benches/evidence/pilot/topple-0.2.1/).
266. registered SCREENING-1/2 in PREREGISTRATION.md (anchor-selection only, never gate evidence; documented pool-gap tension w/ §2 span rule) + dispatched SCREENING-1 (rev 7): Flawless vs topple-0.1.1, 120 games (15 shards x 8), seed 20261119.
267. dispatched SCREENING-2 (rev 8): Flawless vs topple-0.2.1, 120 games (15 shards x 8), seed 20261120. Triggered only after the rev-7 event set was verified live (dropped-event lesson).
268. rewrote the gate path for committed evidence: NEW scripts/verify_evidence.py (fail-closed verification of committed games.jsonl+manifest vs preregistered gate-plan + frozen pool: white/black binary hashes, suite hash, merged_sha256 vs committed bytes, duplicate-game keys, counted totals vs minimum) + 3 regression checks (suite now 53/53); rating-gate.yml rewritten: plan-driven (benches/gate-plan.json, committed at batch preregistration), evaluates benches/evidence/** instead of the old broken in-run-artifact download (which targeted its own empty run), pool key lookups (old code used non-unique 'name' + nonexistent pool fields 'flawless_engine_sha256'/'opening_suites'), expected counts from the plan, correct control paths + registered pair names; fails closed with explicit message until gate-plan.json exists.
269. §4 perft audit COMPLETED: full CPW reference matrix (27 counts: startpos d1-d6, kiwipete d1-d5, pos3 d1-d6, pos4 d1-d6, pos5 d1-d5) ALL exact matches (raw record benches/perft_full_20261114.md; memory's '706045333' was a transcription slip — pos4 d6 = 706,045,033 per engine, committed log and CPW). NEW scripts/perft_oracle.py (referenced by TESTING.md but never committed — doc/reality gap closed): python-chess 1.11.2 cross-check MATCH at all 5 positions d3 + startpos d4. cargo fmt --check clean; cargo clippy --all-targets -D warnings clean. TESTING.md updated: perft table ALL PASS, suite counts 53/104, exact run commands incl. the false-green unittest warning.
270. §6 doc audit: STATUS.md reconciled to verified reality (perft 27/27 complete; estimator 53/53 + verify_evidence; 34/34 cargo; pool frozen + controls/screening in execution; CodeRabbit 11/11 threads resolved, fresh final-SHA review pending); MERGE_READINESS pilot/controls rows updated to measured/running state.
271. DESIGN_LOG §4 closure matrix appended (all audit areas PASS with in-repo evidence) + RESIDUAL RISK CLOSED: cutechess repeating-TC semantics verified at source (timecontrol.cpp onMoveMade: setTimeLeft(m_timePerTc + m_timeLeft) = period budget ADDS to remaining clock) -> match.py default --tc-policy add matches cutechess/CCRL exactly; 'reset' would deviate. Pilot clock behavior (29.5 min/game, no flag anomalies) consistent.
272. GATE WIRING DRY-RUN (synthetic evidence in /tmp, throwaway) caught + fixed a REAL gate bug: run_gate demanded games for ALL pool anchors (6) instead of the preregistered ELIGIBLE subset -> fixed to run on exactly the anchors with evidence in BOTH batches (>=3), reporting unused pool anchors; batch A/B anchor-set mismatch fails closed. Regression test test_gate_uses_eligible_subset_of_pool (2 checks). Suite now 55/55. End-to-end re-run: verify_evidence OK -> plan-driven args -> estimator gate verdict computed correctly (all batch/CI/GLS/saturation/game-count checks PASS on strong synthetic evidence; the deliberately-off synthetic anchor-vs-anchor control correctly FAILs at err=88>75 -> overall FAIL, proving fail-closed controls). The exact rating-gate.yml command chain is now de-risked before real batch evidence arrives.
273. batch suites verified DISJOINT (60+60 openings, 0 shared move-lines, 0 shared names, 0 internal dupes) — to cite in the batch registration; local gates at 855084d: test_match 104/104, test_rating_estimator 55/55, cargo test 6/6 targets (34 tests) all green; PR body refreshed to verified state.
274. BATCH-A/B PREREGISTERED before dispatch (all fixed inputs frozen now: engine fd75726d..., suite hashes + disjointness verified, 2,040 games/anchor/batch (60x17x2), 255 shards x 8, TC 40/15 cutechess-add, bootstrap seeds 20261121/20261122, threshold 2000.0 strict unrounded, adjudication rules); ONLY rule-derived input = anchor set via the already-registered SCREENING rule, committed in gate-plan.json together with the Batch-A dispatch, before any game.
275. bridge dispatch recovery: the 1eddd0e push event (evidence-request rev 1) was DROPPED by GitHub event processing (no workflow run was ever created — same failure mode as the 4bb6016 CTRL-1 dispatch); subsequent bridge runs correctly skipped via the top-commit marker gate (43609372543/43609636019/43609996200 = success, run=false). NOTE for the mechanism: a dropped marker dispatch cannot be recovered by later pushes (their top commits do not move the marker) — recovery = a NEW marker revision (deliberate re-dispatch), documented here. rev 2 dispatched with BOTH completed pilot runs (43602273258 -> evidence/pilot/, 43603558950 -> evidence/pilot-dup/, disjoint dirs per the never-mix rule).
276. Dispatches all covered (CTRL-1 resolves from the QUEUED run 43604654709 when scheduled; earlier drop already recovered by rev 6/7/8). BENCHMARKING.md = policy only, no stale claims. CHECKPOINT 15:55Z: local gates green at 315c6fc (104/55/34); runs: CTRL-2 43603826611 39 done/36 running/25 queued/0 failed; CTRL-1 resolve 43604654709 queued (starved behind CTRL-2); bridge rev 2 run 43611827091 queued; SCREENING-1 43609372547 queued; SCREENING-2 dispatched (rev 8); evidence not yet collected (bridge run queued). NEXT: poll runs; when bridge completes -> git fetch + verify benches/evidence/pilot{,-dup}/*/ (manifest counts, merged_sha256, engine hash, disjoint dirs) then ctrl entries in PREREGISTRATION.md; when CTRL-2 completes -> evidence-collection marker for it + run control self-match at the frozen threshold; when CTRL-1 resolve completes -> rev 9 dispatch with the resolved run id; when SCREENING-1/2 complete -> run the anchor selection rule + commit gate-plan.json + Batch-A dispatch (preregistered at a5a24c0).

- 2026-11-15 (seg 13 — workspace restore #6; evidence pipeline repair; artifact recovery start):
  fresh sandbox cloned coderunknow/FlawLessChess, checked out PR #1 branch
  arena/b756c5f1-asilzkkbatwabaieokwvfotrsioiij; local HEAD verified == live PR head
  4d9e828c5f498f12383dedc105d7580bc57fd81d (PR open/draft/unmerged). Reconciled live state:
  all six evidence runs completed server-side — PILOT-1 43602273258 success, pilot-dup
  43603558950 success, CTRL-2 43603826611 success (120 shard artifacts), CTRL-1 43604654709
  success (120 shard artifacts), SCREENING-1 43609372547 / SCREENING-2 43609636030 conclusion
  FAILURE with all 15 shard artifacts + aggregate mirrors uploaded each (failure isolated to
  the evidence-commit step; fail-closed, no partial evidence claimed). Artifact inventory
  fetched via API with pagination (583 repo artifacts, 0 expired). ROOT-CAUSED + FIXED the
  detached-HEAD evidence-push defect in BOTH evidence-bridge.yml and the rating-run evidence
  job: explicit refspec HEAD:refs/heads/$BRANCH, arena-branch safeguard, verified rebase-retry
  loop with ancestor-state check + diagnostics, bridge aggregate mirror upload (if: always());
  regression suite scripts/test_evidence_push.sh added (10/10 PASS local). FAILURE_LEDGER entry
  written. Next: hosted verification via evidence-bridge revision 3 (deliberate marker
  dispatch), local strict re-aggregation of all six datasets from original shard artifacts,
  controls + screening evaluation, anchor selection, gate-plan.json, Batch A dispatch.

- 2026-11-15 (seg 13 continued — evidence recovery COMPLETE; controls PASS; screening evaluates; ENGINE-1 registered):
  evidence-bridge rev 3 (run 43683839993, SUCCESS) committed pilot/pilot-dup/CTRL-2/CTRL-1
  evidence to the branch (2ec762e) with the FIXED detached-HEAD push — hosted verification of
  the repair. SCREENING-1/2 recovered locally from original shard artifacts (bridge fail-closed
  on their failed run conclusions; aggregate mirrors byte-match local re-aggregation) and
  committed. ALL SIX datasets independently re-aggregated from original artifacts = committed
  bytes (pilot aeb4d5a0…, pilot-dup a811d9d1…, ctrl-self dd8bb94a…, ctrl-av a bdc70d1e…,
  screening 147cec4f… / 9e26b8cd…). Pilot throughput re-verified 29.43/29.53 min/game.
  CTRL-1 PASS (err −10.3 ≤ 75). CTRL-2: estimator metric defect found (self-match white-
  perspective vs registered seat-perspective; case-sensitive focus matching) — FIXED with
  regression tests (suite 65/65); re-evaluated 0.5146 CI [0.4792, 0.5500] → PASS; threshold
  UNCHANGED. SCREENING-1/2: scores 0.0208 / 0.0083 → est ≈ 1632 Elo; selection rule yields
  only wowl-1.3.7 non-saturating → ≥3-anchor gate UNSATISFIABLE at frozen pool; Batch A/B
  DEFERRED (never dispatched — no doomed 300-runner-hour campaign). Root-cause analysis of
  the screening losses: ~95% flag falls (time forfeits), flags in period 3, winner reserve ≈2s
  — ENGINE DEFECT in src/uci.rs clock_limits (soft clamp 20–30_000 ms → late-period overspend;
  hard = 6×soft → zero-reserve death march). ENGINE-1 remediation + SCREEN-2 re-screening
  (seeds 20261123/20261124, freeze-mode hash) REGISTERED in PREREGISTRATION.md BEFORE any new
  game. Next: implement ENGINE-1, regression tests, full suites, bench signature, commit,
  dispatch SCREEN-2, pin new hash, re-apply selection.

- 2026-11-15 (seg 14 — ENGINE-1 implemented + verified locally; SCREEN-2 preparation):
  rustc/cargo 1.99.0 toolchain rebuilt from npm @toolchain-bin pins (docs/ENVIRONMENT.md
  procedure, sysroot assembled + chmod fix). ENGINE-1 implemented exactly as registered:
  reserve-bearing clock_limits in src/uci.rs (reserve=clamp(t/16,300ms,8s), soft without the
  30s cap, hard=min(4*soft,(t-reserve)/2,t-reserve/2)); NEW regression test
  clock_limits_engine1_no_flag_death_march (period simulation + hard-limit floors + starved-
  period trigger); suites: cargo 35/35, fmt clean, clippy -D warnings clean, test_match 104/104,
  test_rating_estimator 65/65; bench signature UNCHANGED fc907eba40b7869f (search/eval
  untouched). rating-run.yml purpose list extended with "screening-2" (registered fresh
  evidence dirs benches/evidence/screening-2/<anchor>/; resolve validator + evidence path +
  artifact names all derive from purpose). Next: commit, dispatch SCREEN-2 rev 9 (vs topple-
  0.1.1, seed 20261123) then rev 10 (vs topple-0.2.1, seed 20261124), engine_sha256 "freeze",
  verify each event fires (dropped-dispatch discipline), monitor, pin the runner hash,
  re-apply the selection rule.

- 2026-11-15 (seg 15 — ENGINE-1 acceptance 5 PASS; local TC smoke healthy; SCREEN-2 in flight at segment end):
  probe-006 (probe-005 methodology, 80 games = 2 reps, SF19-lite Skill 5, movetime 100 ms,
  pinned npm hashes verified): flawless 0.556, opening-clustered 95% CI [0.469, 0.644],
  logistic +39 — inside the probe-005 band; 0 engine errors; local build hash a3325011…
  (sandbox; runner hash pins at SCREEN-2). Local real-clock smoke (40/5 self-match, AB/BA):
  game 1 draw at 63 plies, BOTH clocks finished healthy (w 47.9 s / b 52.7 s of the 300 s
  period) — NO flag, exactly the reserve-bearing behavior ENGINE-1 registered (old code would
  have entered the period-end death march). Interim CodeRabbit review requested 06:37Z at
  91c4c08 (comment id 6890453480) — NO response recorded yet (rate-limit history known);
  the MANDATORY final review remains at the exact final SHA. SCREEN-2 runs 43685671431 (rev 9)
  + 43686056730 (rev 10) dispatched, events verified, all 15 rev-9 shards playing at segment
  end; rev-10 shards partially queued behind the 20-job concurrency cap. Segment boundary:
  turn quota exhausted while the server-side screening executes; classification
  ACTIVE / INCOMPLETE with WAITING_EXTERNAL execution boundary — the workflows continue on
  GitHub infrastructure independently of this session.
- EXACT RESUME POINT (next session):
  1. `git fetch` in /home/z/my-project/FlawLessChess; check runs 43685671431 + 43686056730
     concluded SUCCESS; two evidence commits expected on the branch
     (benches/evidence/screening-2/topple-0.1.1/ + …/topple-0.2.1/ via the FIXED evidence job).
  2. Download the 15 shard artifacts per run; strict aggregate_shards.py; byte-compare vs
     committed; verify flag rate ≤ 10/120 (ENGINE-1 acceptance 4); read the new engine hash
     from the manifests and PIN it in PREREGISTRATION.md (SCREEN-2 result section).
  3. Evaluate: python3 scripts/make_gate_plan.py --anchors topple-0.1.1 topple-0.2.1
     (est = mean(R_a + d̂_a)); apply the frozen selection rule (≥3 non-saturating anchors).
  4. If satisfied: commit benches/gate-plan.json + Batch A dispatch (confirmatory, pinned
     hash, seed 20261121, 255 shards × 8, suite batchA) BEFORE any batch game; then Batch B
     (seed 20261122, suite batchB); dispatch CTRL-2-R (registered) with the pinned hash.
  5. If unsatisfiable: continue the §8 improvement cycle with the next registered experiment.
  6. All tools ready in-repo: scripts/make_gate_plan.py, scripts/download_artifacts.py,
     scripts/aggregate_shards.py, scripts/rating_estimator.py (gate), scripts/verify_evidence.py.

- 2026-11-15 (seg 16 — SCREEN-2 wait utilized: ANCHOR-2 executed end-to-end; expansion pool frozen):
  live reconciliation (PR 19526a43 open/draft/unmerged; both SCREEN-2 runs in_progress, 30
  shards playing). ANCHOR-2 ladder verified: 5 candidates registered → tag/source/license
  checks (berserk-3.2.1 + seer-1.2.1 EXCLUDED fail-closed: no verifiable source tags) →
  local smokes (sf_8/sf_5 builds + ids; weiss-1.2 id exact; akimbo-0.5.0 id exact) →
  anchor-verify.yml matrix extended (+5 legs) → 3 annotated failures diagnosed+fixed
  (SF id line vs banner; leorik Engine project path; Copying* license glob) →
  HOSTED RUN 43693679899 SUCCESS all 11 legs → benches/anchor-pool-3000.json frozen
  (5 engines 2922-3358, 8,762 CCRL games, schema mirrors frozen pool). ENGINE-2 design
  draft (SEE) recorded in DESIGN_LOG; make_gate_plan.py + make_batch_dispatch.py tools
  ready; verify_screen2.py orchestrator ready for the evidence landing. Workspace-root
  append trap (cwd resets) hit twice — repaired both times, workspace repo restored.

- 2026-11-15 (seg 16 end — turn quota boundary at 09:15Z): SCREEN-2 runs 43685671431 +
  43686056730 still IN PROGRESS (all 30 shards playing, 0 artifacts yet — shard artifacts
  upload at completion; ETA ≈ 10:30-10:45Z + ~10-15 min evidence job → evidence commits
  ≈ 10:45-11:00Z). ANCHOR-2 fully executed + frozen this segment (hosted run 43693679899
  SUCCESS all 11 legs; benches/anchor-pool-3000.json at d42c751). All tools staged:
  verify_screen2.py (orchestrator), make_gate_plan.py, make_batch_dispatch.py,
  download_artifacts.py. NEXT SESSION: (1) git fetch; check both runs concluded success;
  (2) python3 /home/z/my-project/scripts/verify_screen2.py 43685671431 43686056730
  (downloads 15 shard artifacts per run, strict-aggregates, byte-compares vs committed
  evidence, checks flag rate ≤ 10/120 = ENGINE-1 acceptance 4, reports the runner engine
  hash); (3) PIN the hash in PREREGISTRATION (SCREEN-2 result section); (4) est =
  mean(R_a + d̂_a) via the screening data; re-apply the FROZEN selection rule
  (make_gate_plan.py --anchors topple-0.1.1 topple-0.2.1); (5) if ≥3 non-saturating anchors
  → gate-plan.json commit + Batch A dispatch (make_batch_dispatch.py --hash <pinned>
  --batch A --seed 20261121 --anchor <sel> --revision <next>) THEN Batch B (20261122);
  CTRL-2-R dispatch (seed 20261125) with the pinned hash; (6) if unsatisfiable → ENGINE-2
  registration (SEE design draft in DESIGN_LOG) with SCREEN-2 as the measured baseline.

- 2026-11-15 (seg 17 end — cutoff boundary ~11:45Z): remote tip 00e7401 (this log pending push).
  SCREEN-2 runs 43685671431 + 43686056730 STILL IN PROGRESS at 11:31Z (started 06:29/06:34Z;
  30/30 shards playing; 0 artifacts). Duration analysis: old-candidate SCREENING took ~3h40m;
  the ENGINE-1 clock fix makes games LONGER (flag ends ≈ 0 → full games); PILOT mean 29.43
  min/game with small sample; at ~36 min/game shards finish ≈ 12:00-12:10Z; GitHub job
  timeout 360 min → hard kill ~12:29Z. IF SHARDS TIME OUT: evidence job fails closed (strict
  15-shard aggregation) → recovery = re-dispatch the affected run via rating-run.yml
  workflow_dispatch inputs (registered config: purpose=screening-2, target_commit=HEAD at
  00e7401+, seed unchanged, engine_sha256=freeze or the pinned hash) — document the rerun in
  PREREGISTRATION when it happens; never mix partial evidence. This segment also: recover_
  screen2.py committed (9a61259, repo-portable gh/curl dual-path, smoke-tested); SCREEN-3
  conditional registration (f04e657); GATE-PLAN-V2 amendment registered (00e7401); PR body
  updated to current verified state; mode-only file churn from sandbox restore reverted
  (git restore); local suites re-verified 104/104 + 65/65 (local Rust toolchain lost in the
  recycle — hosted CI is authoritative for cargo tests, latest green at 9a61259); gate-plan
  chain rehearsed end-to-end on old screening evidence (exact reproduction: est=1632.0,
  rule unsatisfiable, escape clause intact; old candidate flagged 57/120 — SCREEN-2 must
  show ≤10 for ENGINE-1 acceptance 4).

- 2026-11-15 (seg 18 end — cutoff boundary ~14:25Z): remote tip 8bb5a84. SCREEN-2 attempt 1
  failure fully processed (SHAPE-1 registered 4166703 + hash pinned + ledger); SCREEN-2R
  dispatched (rev 11 = 430cc37 run 43714600687, rev 12 = bba4950 run 43714620645, 60×2
  shape); at 14:03Z rev11 has 3 shards COMPLETE (87 min/shard — faster than the 120-min
  estimate; run could finish ~15:00-15:15Z + evidence job), rev12 resolve queued behind
  runner capacity (no workflow-level concurrency block; capacity-limited only). Tooling
  validated for the new shape: recover_screen2.py (60 shards + pinned-hash fail-closed),
  test_aggregate_60.py (synthetic 60-shard aggregation PASS, 8bb5a84), merge_batch_runs.py
  self-tested (a5689b2), make_batch_dispatch.py SHAPE-1 slice gen (dcf0ea6, rev-99 dry run).
  PR body updated at head dcf0ea6. ENGINE-2 audit reconciled (search/eval unchanged since
  14e2e1c — implementation deferred past >2000). Next: monitor 43714600687/43714620645 →
  evidence commits → recover_screen2.py → flag rate + estimates → CTRL-2-R (rev 13) →
  SCREEN-3 (rev 14, conditional) → gate-plan commit → Batch A (revs 15-18) → Batch B
  (revs 19-22) → merge → verify_evidence → 2000 gate. Full commands in
  download/FLAWLESS_checkpoint_2026-11-15.md §3.
### Segment 23 (2026-11-16 ~12:15Z) — engine clock audit (Phase 5 item) + hygiene

- **clock_limits (src/uci.rs:539) audit: VERIFIED PASS.** The ENGINE-1 reserve-bearing
  budget (reserve = clamp(t/16, 300ms, 8s); soft = max(20, (t-reserve)/mtg + inc/2); hard =
  min(4*soft, (t-reserve)/2, t-reserve/2) floored at soft) implements exactly the registered
  invariants (planned period spend <= t - reserve; >= reserve/2 survives any hard-limited
  move; hard >= soft). Regression tests clock_limits_respect_remaining_time and
  clock_limits_engine1_no_flag_death_march present; SCREEN-2R flag losses 0/240 corroborate
  at tournament level. Search-side check_time fires every 1024 nodes vs hard_ms; go
  infinite/ponder correctly inert (uci.rs:132-146).
- **Hygiene:** sandbox tooling chmod'ed three tracked files to 100755 (mode-only drift, zero
  content change); restored to committed modes — evidence commits stay byte-clean.
- **Run state at 12:12Z:** CTRL-2R 43820392119: 79/120 shards success, 21 playing, 0 failed.
  SCREEN-3 43820645420: resolve done, 2/60 playing, 58 queued. No action needed; next
  milestone = CTRL-2R terminal -> evidence job -> self-match CI verdict; then SCREEN-3
  terminal -> 3-anchor est -> gate-plan commit WITH Batch A rev-15 dispatch.

### Segment 24 (2026-11-16 ~13:40Z) — mission re-entry, checkpoint, no dispatch

- Re-entry under the owner's mission prompt (V1 >2,000 and V2 >3,000). Fresh clone. Remote head verified
  at `74c3294`: PR #1 open, draft, base `main` 98b1a00, mergeable_state `unstable`.
- Workflow state verified via API at 13:38Z:
  - CTRL-2-R, run 43820392119 (dispatch rev 13): 113 of 120 shard jobs succeeded, 7 in progress, 0 failed. Evidence job not yet run.
  - SCREEN-3, run 43820645420 (dispatch rev 14): resolve succeeded 12:07:58Z after queuing from 06:59:56Z. 33 shards in progress, 27 queued, 0 failed.
  - Run 43864633370 (74c3294): resolve queued. No-op, because the top commit does not touch `benches/dispatch.json`.
  - rating-gate run 43864633449 (74c3294): failure, fail-closed. `benches/evidence/rating-gate-result.json` and the gate plan are absent. Expected until SCREEN-3 is terminal.
- Created `MISSION_CHECKPOINT.md` (authoritative resume document). Changed no dispatch marker. Created no gate plan: SCREEN-3 is not terminal.
- Not verified in this segment: STATUS.md and MERGE_READINESS.md reconciliation, CTRL-2-R pass criteria, SCREEN-3 aggregation, CodeRabbit status.

### Segment 24 (cont.) — reconciliation and local verification (2026-11-16 ~13:50Z)

- Re-checked runs at 13:43Z: CTRL-2-R 113/120 shard jobs succeeded, 7 in progress, 0 failed. SCREEN-3 resolve and 1 shard succeeded, 33 running, 26 queued, 0 failed.
- Reproduced SCREEN-2R screening estimate from raw evidence with `scripts/make_gate_plan.py --out /tmp/...` (not committed): topple-0.1.1 2176.8, topple-0.2.1 2236.4, est 2206.6. The SCREEN-3 choice (akimbo-0.1.1, |est − R| = 234.4) holds under the corrected estimate and under the pre-fix estimate.
- Local suites: test_rating_estimator 65/65 PASS; test_aggregate_60 PASS; test_merge_batch_runs self-test ALL PASS. test_match.py not run locally (python-chess 1.11.2 not available in this sandbox index; CI installs it).
- Found PREREGISTRATION BATCH-A/B pinned to the pre-ENGINE-1 hash fd75726d… while ENGINE-1 requires the new frozen hash. Registered BATCH-HASH amendment (append-only) binding Batch A/B to 9663697d… BEFORE any batch dispatch. No batch was dispatched.
- STATUS.md header and >2000 item, and MERGE_READINESS anchor-selection, null-control, CI and estimator-count items, updated to verified state. Previously STATUS/MERGE_READINESS listed SCREEN-2 as IN FLIGHT and listed CTRL-2 as passing for the ENGINE-1 candidate. Corrected: CTRL-2 PASS applies to the pre-fix candidate only; CTRL-2-R is pending.
- MISSION_CHECKPOINT.md rewritten with the verified state, the projection (labelled not evidence) and the resume procedure.
## 2026-11-17 — RATING-100 and exact-slot recovery implementation

- Implemented the append-only RATING-100 sample-design tooling: exact 100 counted games per anchor/batch, 50 named opening clusters, AB/BA, deterministic 50+50 disjoint suite subsets, machine-readable blocked power assessment, strict sample verifier, estimator wiring, batch merger and dispatch marker.
- Added exact schedule-index selection to `scripts/match.py` so a recovery dispatch can run only a missing color-reversal leg; added regression coverage for an in-shard requested index and an out-of-shard rejection.
- Added dispatch-reader regression coverage for partial pairs, complete pairs, duplicate counted schedule slots, wrong time control and opening mismatch. CI now includes these scripts and a power-model smoke check that asserts the design remains BLOCKED.
- SEE is ordering-only. No quiescence capture is discarded based on approximate SEE. No Elo/playing-strength benefit is claimed; all new tests await the PR CI run.
- Corrected defects found during pre-commit source review: the first draft 50-opening suites did not match the specified deterministic selector and were replaced; workflow resolver/evidence wiring was corrected for validation order, batch-separated run paths, exact recovery slots, explicit evidence default-on, and YAML/Python indentation.
- Live workflow audit: SCREEN-3 run 43820645420 = resolver success + 60/60 shard success; aggregate-and-commit-evidence skipped. CTRL-2-R run 43820392119 = resolver success + 120/120 shard success; aggregate-and-commit-evidence skipped. The shard artifacts exist but have not become canonical committed evidence; no gate/anchor-selection conclusion is inferred from them.
- No tournament was dispatched by these code changes: `benches/dispatch.json` is unchanged and the power assessment is BLOCKED. PR #1 remains draft/unmerged; no tag/release.

## 2026-11-17 — hosted validation correction

- First hosted CI at `7d368cd`: MSRV Rust 1.80 passed; Linux and Windows failed at rustfmt in new SEE helper layout before unit tests. Applied the exact rustfmt layout from both runner logs in the follow-up commit.
- The anchor verifier detected the expected depth-10 bench signature change: measured `141943aa23b3fc68`, old expected `fc907eba40b7869f`. The expected signature is updated to the newly measured value; binary SHA-256 was not emitted because verification exited at the signature check.
- rating-gate failed closed because no gate plan/canonical evidence exists. rating-run resolver succeeded and skipped shard jobs; no new tournament was launched. The RATING-100 power report remains BLOCKED.

## 2026-11-17 — post-commit validation and selector correction

- Rechecked PR #1 and the arena branch: HEAD fe6d34067e776ca64e676617c2102966675b4744, open + draft + unmerged. Two commits after the prior checkpoint contain RATING-100, exact-slot recovery and SEE ordering.
- CI run 44062359630: Ubuntu and Windows both passed cargo fmt --all -- --check, cargo clippy --release --all-targets -- -D warnings, and cargo test --release --locked (test groups 12, 3, 21 and 4 all successful). Python suites: match 111/111, estimator 65/65, reduced_sample 7/7, dispatch recovery 5/5, and merge-batch self-test all cases passed. Both OS jobs then failed only at the deterministic reduced-opening selector verifier. This is not an accepted CI pass.
- Root cause verified: the temporary JS generator used an incomplete SHA-256 constant table; Python hashlib in the repository verifier was correct. The verifier prevented bad suite bytes from being used. Rebuilt the two suite subsets with a corrected SHA-256 routine, added explicit LF checkout attributes, updated byte-hash pins in the dispatch tool, power report and CI assertions, and appended an integrity correction to PREREGISTRATION.md / RATING_PROTOCOL.md.
- Corrected Batch A SHA-256 5abdcdbddec0f22d7e6eff8974ee402363c8c3df318b8110d7204adf69f5c1df; Batch B ccb4901742eca25b0b10f1a3c9fdfc17b2967a1939c2d7e466c2c5495b6d4253. 50 unique opening names each; no overlap. The corrected bytes still require the hosted Python verifier to pass before use.
- Anchor verification 44062359732 succeeded on PR merge commit 4cdf57c5e0d898e9accc6ec9d51ef00d82290575: bench signature 141943aa23b3fc68, binary SHA-256 168dc0ab22749f8dc7a6be5248cd7426f9f2bfd3fda8077bc6218959ad6e41d7. Treat this as the merge-tree build identity pending branch-tree equivalence verification and a new exact-head run.
- No confirmatory workflow ran. 44062359728 failed closed for missing gate plan; 44062359655 resolver succeeded but skipped matrix/evidence because the dispatch marker was unchanged. SCREEN-3 and CTRL-2-R runs still lack canonical evidence because their evidence jobs were skipped. RATING-100 remains BLOCKED and the PR remains Draft.


## 2026-11-17 — green exact-head validation and engine-identity isolation

- PR head at this checkpoint: 5b63e273d77cfb097f0ad73bc28dda05cc19adad (open, draft, unmerged).
- CI run 44066217195 succeeded on Ubuntu + Windows + Rust 1.80. Both OS jobs passed rustfmt, clippy, all Rust tests, match 111/111, estimator 65/65, reduced_sample 7/7, dispatch recovery 5/5, merge self-test all cases, deterministic opening-suite verifier, and power-analysis smoke (36 scenarios, expected hashes, status BLOCKED). Release, UCI and perft sanity also passed.
- Anchor-verification run 44066217113 succeeded 13/13. The verify-flawless artifact records signature 141943aa23b3fc68 and binary SHA-256 168dc0ab22749f8dc7a6be5248cd7426f9f2bfd3fda8077bc6218959ad6e41d7. Merge commit 7434e948357eda05f9435e430c37da082f202741 is a two-parent synthetic merge with source branch commit 5b63e273d77cfb097f0ad73bc28dda05cc19adad as a parent and identical tree SHA 75bc5633e1466d5abf1f4c7d5999bc4a3915e193.
- The RATING-100 report is explicitly pinned to ENGINE-1 hash 9663697da62e33229d516af3681c442e268287c59d6b97ff2cd13256b564d428. Its generator verifies source manifests, merged raw-file hashes, attempt/count totals, frozen SCREEN-2 suite identity, anchor identities and identical engine hashes. Dispatcher and workflow resolver reject report/binary SHA mismatch.
- ENGINE-2 identity is now verified, but its own screening and candidate-specific controls have NOT been run. The ENGINE-1 power model cannot authorize ENGINE-2. RATING-100 remains blocked, no games dispatched.

## 2026-11-17 — provenance-guard test adjustment

- Run 44067364552 on 29b627e failed only in the new scripts/test_power_analysis.py assertion that expected a later cross-manifest mismatch string. The implementation rejected an out-of-scope engine SHA earlier, at the explicit SCREEN-2 / ENGINE-1 hash allowlist. This is the intended fail-closed path.
- Updated the assertion to match the earliest rejection. Other Linux suites before this point passed: match 111/111, estimator 65/65, reduced_sample 7/7 and dispatch recovery 7/7. Anchor verification 44067364568 completed 13/13; rating-run resolver skipped shards; rating-gate failed closed.
- A full exact-head CI rerun is required after the test-only correction.

## 2026-11-17 — Windows newline normalization defect

- CI 44067826990: Ubuntu passed; Windows failed during power-report smoke because the raw SCREEN-2 games file was checked out as CRLF while its manifest merged_sha256 was generated from LF on Ubuntu.
- The game records were unchanged; this was cross-platform Git newline conversion. Added a logical-JSONL SHA helper that canonicalizes line endings only, preserving every record, order and content. Added exact LF attributes for the two SCREEN-2 evidence files, plus regression tests simulating CRLF checkout and record tampering.
- No evidence was changed and no rating games launched. Power report remains ENGINE-1-specific and BLOCKED. Rerun exact-head CI.


## 2026-11-19 — UCI no-argument startup compatibility (arena session)

- **Scope:** fix the UCI startup failure reported in `diagnostic-report.zip` and deliver a verified Windows x64 executable as a CI artifact. No rating, search or engine-strength work.
- **Branch and base:** `arena/2d2d30b4-flawlesschess` from `main` at `5e36b06` (PR #1 merge). PR #2 belongs to another branch and was not touched. The mission's "prefer main" instruction was not applied because the session branch is fixed by Arena.
- **Toolchain:** Rust 1.99.0 installed from npm `@toolchain-bin/*` into `/home/user/.toolchain/sysroot`. Rust 1.80 is not published under that scope and rustup is blocked, so the MSRV compile is delegated to CI.
- **Reproduction:** before changes, no arguments → exit 2 with usage; `uci` → handshake. Baseline gates: fmt, clippy, `cargo test --release --locked` green; perft(3)=8902; bench signature `141943aa23b3fc68`.
- **Changes:** `src/main.rs` (no-argument UCI mode; `-h`/`--help`); `tests/uci_smoke.rs` (real-process no-argument lifecycle, handshake parity, EOF exit, CLI regressions; `Engine` guard kills children on drop); `scripts/windows_artifact.py` (PE x86-64 check, smoke tests on the exact exe, SHA256SUMS and BUILD-MANIFEST); `.github/workflows/ci.yml` (`windows-x64-artifact` job, no `continue-on-error`); README, CHANGELOG, STATUS, DESIGN_LOG, FAILURE_LEDGER, `docs/audit/2026-11-19-uci-no-args-compatibility.md`.
- **Negative control:** the three new no-argument tests fail against the pre-change `src/main.rs` ("engine exited before receiving any command") and pass after the fix.
- **Tooling check:** the artifact script rejects a Linux ELF, and on a stubbed-PE local run it passes the smoke tests, writes checksums, and `sha256sum -c` verifies them. The real PE check runs only in CI.
- **Push policy:** only the session branch is pushed. No tags, releases, merges, force-pushes, or PR creation without authorization. Exact-head CI is dispatched with `gh workflow run ci.yml --ref <branch>`, because the CI push trigger is limited to `main`.

## 2026-11-19 — correction to the push-policy note above

- The entry above says exact-head CI is dispatched with `gh workflow run ci.yml --ref <branch>`. That was attempted and refused with HTTP 403 (`Resource not accessible by integration`). Exact-head CI for this branch ran via draft PR #3 (`pull_request` trigger), with the operator's approval. No workflow file or trigger was changed for this.

## 2026-11-19 — CodeRabbit review on a7b7eda (3 findings, all valid, fixed)

- Handshake aliasing: `hs` was the live transcript list, so the no-args vs `uci` comparison included later search output. Now a snapshot.
- Post-quit stdout was not checked: `finish()` now drains stdout through EOF before validation.
- The "no stdout before any command" check was dead code (it read `s.lines` before any drain). It now runs after `finish()`.
- Regression tests added to `scripts/test_windows_artifact.py` using a fake engine through the real `Session` (15/15 pass).
- Artifact download for `a7b7eda` still fails with blob-storage EOF; the artifact remains NOT VERIFIED.

## 2026-11-19 — full-release validation pass (see docs/audit/2026-11-19-release-validation.md)

- Perft: 22/22 standard positions (d1–d4) and deeper counts match python-chess and CPW; diftest 2,321/0.
- Full games: 6 engine-vs-engine games with python-chess referee and clocks (benches/games-20261119/); all moves legal on replay; castling and promotions occurred; stalemate and threefold draws detected.
- UCI probes: 10/10 lifecycle and 37/37 malformed-input cases pass (scripts/uci_protocol_probe.py, scripts/uci_malformed_probe.py).
- Finding recorded, not changed: `go movetime` returns after 38–100% of budget (search.rs soft-budget rule). Changing it would invalidate rating-evidence timing.
- No merge, tag, or release performed. Release gates still open: CodeRabbit on final head (rate-limited), artifact verification (download EOF), real GUI test (not possible here), Windows runtime, and the rating/V1 gates.

## 2026-11-19 — v0.1.0 pre-V1 release-candidate remediation (local work)

- Version `0.1.0` (`Cargo.toml`, `Cargo.lock`). Package stays `flawless` (decision pending; the approved name `Flawless-Chess-Engine` does not match the repository).
- movetime fix: `fixed_time` flag; tests `tests/movetime_smoke.rs` (8 tests). Old rule re-inserted in a scratch copy: 2 tests fail. Restored: all pass.
- Self-review of the full Rust diff (not independent review): `ponderhit` now clears `fixed_time` with the clock recalculation; checked `ponderhit` after 400 ms ponder returns immediately (correct, the budget is already spent).
- Probes added to CI (both OSes): `scripts/uci_protocol_probe.py`, `scripts/uci_malformed_probe.py`, `scripts/selfplay_games.py` (python-chess 1.11.2 referee).
- `scripts/windows_artifact.py`: manifest now records `product`, `package_version`, `engine_version_output`; the exe must report `Flawless <Cargo version>`.
- Gates run locally on this tree: fmt, clippy `--all-targets -D warnings`, `cargo test --release --locked` (all suites green), build, bench `141943aa23b3fc68`, perft d3 8902 / d4 197281, diftest 2321/0, 6 full games (all legal), 10/10 UCI probes, 37/37 malformed, Python harness suites (test_match 111/0, estimator 65/0, etc.).
- Not done: merge, tag, release, asset upload; independent AI review (pending the user's decision).

## 2026-11-19 — audit fixes on the release-candidate tree (uncommitted at time of writing)

- src/uci.rs: `ponderhit` budget collapse after `go ponder movetime N` (regression test added; fails on the previous uci.rs).
- scripts/uci_malformed_probe.py: `go` lines now wait for `bestmove` before `quit`; unlimited searches (unparseable limits) are ended by `stop` and labelled as such.
- scripts/windows_artifact.py: git identity check fails closed; release profile read from Cargo.toml; version read from the [package] table only. Unit tests added (one caught a dropped hyphenated key before it shipped).
- scripts/uci_protocol_probe.py: python-chess required; stderr drained; dead code and stale comment removed.
- tests/movetime_smoke.rs: timing tests serialised with a static mutex.

## 2026-11-20 — CodeRabbit review of 4bc9ff3 (10 actionable comments): triage

Review text read from PR #3 (review posted 05:54:53Z). Each item checked against the code before acting.

- selfplay_games.py: exit status not checked after quit → FIXED (`returncode` must be 0; BAD_EXIT recorded). Verified with a fake engine that exits 3: script exits 1.
- selfplay_games.py: no client-side deadline around play → FIXED (play runs in a thread; deadline = clock + 5 s). Verified with a fake engine that never answers: TIMEOUT after 8 s, exit 1.
- selfplay_games.py: failing outcomes did not fail the run → FIXED (non-zero exit on ENGINE_TERMINATED, ILLEGAL_OR_NULL_MOVE, FLAG_FALL, TIMEOUT, BAD_EXIT, PLY_CAP).
- resource_probe.py: peak started at 0 and was sampled only on idle → FIXED (baseline included; sampled every loop). Deadline and cleanup added. Verified with fake engine (ok and hang paths).
- uci_protocol_probe.py: no cleanup after a failed check → FIXED (registry kills and reaps every engine after each check). Verified: no leftover processes after a run against the fake engine.
- uci_protocol_probe.py: lines before uciok not validated → FIXED (all stdout is checked at close; unknown lines fail). Fake-engine run exercised this path.
- windows_artifact.py: depth-2 check accepted output after bestmove → FIXED (only lines before the first bestmove count). Covered by the next remote run only (needs a Windows binary).
- tests/movetime_smoke.rs: pre-stop check ignored output in the channel → FIXED (`drain()` before each check). Duplicate-bestmove count now follows a readyok. NOT COMPILED LOCALLY: no Rust toolchain in this sandbox after re-provisioning; CI is the first check.
- WINDOWS_GUI_TEST.md: version check relied on PATH → FIXED (run from the extracted folder).
- ci.yml wording item: the selfplay step already fails on exit code; the script now sets that exit code.

Environment note: the sandbox was re-provisioned. The local clone was reset to the `main` base with the branch's working tree kept. Rust (1.99 sysroot) and /tmp/chessvenv are gone. Recovered with `git reset --mixed origin/arena/2d2d30b4-flawlesschess`; no commits were lost. A backup of the working tree is in /tmp (not in the repo).

## 2026-11-20 — CodeRabbit review of e029dff (6 findings) and the remaining release checks

Triage (each checked against the code):

- src/uci.rs ponderhit fallback: `go ponder nodes N` kept `infinite` set, so the node cap was never enforced after ponderhit → FIXED (fallback clears `infinite` when a node cap is set). Regression test `ponder_node_cap_is_enforced_after_ponderhit` added. CI-verified only (no Rust toolchain).
- tests/movetime_smoke.rs drain(): panic marker not checked → FIXED (same assertion as until()).
- scripts/uci_malformed_probe.py: a bestmove could be consumed while waiting for readyok → FIXED (go lines wait for bestmove before isready). The stderr snapshot now follows the reader join. Output after the final readyok is drained and validated. Each bestmove is checked for legality against the start position (the engine's default, confirmed in src/uci.rs `Position::startpos()`). Mechanics verified with a fake engine: 37/37 with a legal engine, 26/37 with an illegal-move engine (rejected).
- Resource probe: added to CI on Linux (`if: runner.os == 'Linux'`), since it reads /proc.
- En passant: `t_en_passant_capture` added to scripts/uci_protocol_probe.py. It forces the engine's root with `go searchmoves` to a single en passant capture (two positions: after 1.e4 a6 2.e5 d5, and the FEN with ep square f6). The test setup is checked with python-chess (both are legal en passant). Fake engine correctly FAILs it.

Still unverified in this session: the Windows GUI test (needs a human and Windows), the Windows artifact (blob EOF on every attempt), and any run of the real engine on this head beyond CI.

## 2026-11-20 — CodeRabbit review of 8db4b09 (3 actionable + 1 nitpick): triage

- tests/movetime_smoke.rs bare `go ponder`: the test never sent ponderhit, so the zero-clock fallback was not covered → FIXED (ponderhit, bounded silence, stop, readyok barrier, exactly one bestmove). CI-verified only.
- scripts/uci_protocol_probe.py close(): stdin was closed before waiting, so an engine that ignores quit but exits on EOF passed → FIXED (wait for exit first, then close stdin). Fake-engine check: an engine that ignores quit is now caught in 7 cases.
- scripts/uci_protocol_probe.py movetime: the result was not checked for legality → FIXED (legal_check from the start position).
- STATUS.md: the linked audit only records results through 07b68a8 → FIXED (wording marks it historical; current-head evidence points to the release-candidate report).

Environment: the sandbox was reset again. /tmp venv and fake-engine harness were rebuilt. The repo working tree was intact. A stray file created by a failed command was removed.

## 2026-11-20 — comprehensive source audit (second pass, head b5fb4f9)

Scope: panic sites in src/, input parsing (go/setoption/position), search root handling, clock formula, option bounds.

- src/search.rs `search_root`: `go searchmoves` naming only illegal moves left `roots` empty and returned `Move::NULL` (`bestmove 0000`) in a position with legal moves → FIXED (keep all legal roots when no named move is legal). Regression test added; CI-verified only (no Rust toolchain).
- src/uci.rs `searchmoves` unwrap (`Move::from_uci(args[i]).unwrap()`): guarded by `is_some()` in the same loop → safe, left unchanged.
- src/main.rs `bench_eval` unwrap on a constant FEN, and position.rs `expect`s on constant FENs/test FENs → safe.
- src/position.rs `char::from_digit(empty, 10).unwrap()` with empty in 1..=8 → safe.
- `clock_limits`: soft/hard clamped to remaining time; zero and tiny clocks handled by the existing unit test.
- `setoption`: Hash 1..=4096 MiB, MultiPV 1..=256, Threads ignored (single-threaded build). Hash 4096 MiB can exceed memory on small machines; the advertised maximum is kept, and this is recorded as a limitation, not a bug.
- Not changed: stderr diagnostics for setoption (`info string` goes to stderr; the UCI protocol does not forbid it).

## 2026-11-20 — CodeRabbit review of 9336913 (3 findings): triage

- scripts/selfplay_games.py `--only`: an unknown name silently ran zero games → FIXED (argparse `choices`). Checked: exit 2 with the valid list.
- scripts/selfplay_games.py: a protocol-level EngineError escaped play() without a log → FIXED (recorded as ENGINE_ERROR, a failure prefix; completed moves kept).
- scripts/windows_artifact.py finish(): stdin was closed before waiting after `quit`, so EOF could pass an engine that ignores quit → FIXED (quit callers use finish(eof=False); the EOF test keeps eof=True). Fake-engine regression test `test_engine_ignoring_quit_is_not_passed_by_eof` added; the local suite passes 19/19 (about 3 s).

## 2026-11-20 — Final audit execution (branch arena/f668bde4-flawlesschess)

- Fixes committed in 49fdecf: FEN material limits, bounded UCI line reader, single-side clock, Hash max 1024, stdout option messages, saturating clock math, 16 MiB search stack, MoveList capacity 512.
- Tests added: correctness (CPW perft references, material limits, castling rights), protocol_regressions (7 process tests), uci unit tests (clock saturation, line reader).
- Local gates run: `cargo fmt --all -- --check`, `cargo clippy --release --all-targets -- -D warnings`, `cargo test --release --locked`, Python suites (test_match, test_rating_estimator, test_reduced_sample, test_make_batch_dispatch, test_power_analysis, test_merge_batch_runs, test_windows_artifact, test_aggregate_60, test_recover_download), probes (uci_bestmove_smoke, uci_protocol_probe, uci_malformed_probe, selfplay_games, resource_probe), perft d3 = 8902, bench signature 141943aa23b3fc68.
- Not run locally: MSRV 1.80 (toolchain not available from the mirror), Windows x64 build (CI job is the check of record).
- Policy kept: append-only logs were extended, not edited. The older AGENTS_LOG entry that calls Hash 4096 a limitation is historical.

## 2026-11-20 — FINAL AUDIT batch 2 (checker validation and verification)

- Differential fuzzing (`scripts/fuzz_legal_differential.py`, seeds 1–6, 157k+ positions) found F-08 (checker rule). Fixed; differential rerun shows 0 mismatches and 0 accepted oracle-invalid positions.
- UCI grammar fuzzing (`scripts/fuzz_uci_grammar.py`, 1,350 sessions): 0 failures.
- Full-game en passant probe added (`scripts/fullgame_en_passant_probe.py`) and wired into CI after selfplay.
- Static evaluation colour-symmetry test added (303 pairs). The search-level probe `scripts/eval_symmetry_probe.py` is informational only (2 of 40 depth-4 mismatches; see FINAL_AUDIT_PROGRESS.md S-14).
- The CI `persist-credentials: false` nitpick fixed on the `test` and `msrv` checkouts.
- Naming decision (ADR 0002) stands: the Cargo package is `flawless`.

## 2026-11-20 — PR #4 CodeRabbit triage (12 inline comments, 1 nitpick)

- All comments are addressed. Details and evidence are in FINAL_AUDIT_PROGRESS.md, "Phase E".
- The one Major item (fuzz final readiness) and the CI-relevant one (malformed bestmove in the Windows artifact checker) were real defects in my or in pre-existing harness code, and both are now covered by tests or self-tests.
- Qodo (billing-blocked), Kilo (out of credits) and CodeRabbit's walkthrough are not counted as passed reviews. CodeRabbit's inline review is addressed; a re-review of the new head is requested.

## 2026-11-20 — correction to the batch-1 gate entry (L522–528)

- That entry said clippy was run as `cargo clippy --release --all-targets -- -D warnings`. That is the only clippy line it records. The debug invocation `cargo clippy --all-targets -- -D warnings` was run in the same session but is not in that entry. The release and debug logs are in `/tmp/gates/` (clippy_release.log, clippy_debug.log); both are re-run on the final commit.
- That entry says `protocol_regressions (7 process tests)`. The count at 49fdecf was 6 (`#[test]` count at the commit); 8 at 3a280df; 9 after the searchmoves control test. Counts are taken from `#[test]` attributes, not from the entry.
- Historical entries are left as written.

## 2026-11-23 — F-56 tactical-search correction

Applied the user's audit direction to resolve the previously documented LMR owner-choice after confirming an actual false negative on legal middlegame positions. The narrow quiet-check exemption is regression-tested and independently checked against two random-game oracle samples. A 13.1% depth-10 benchmark node increase and signature change are accepted/documented; no rating claim or reuse of frozen rating evidence. Full exact-head gate pending.

## 2026-11-23 — F-57 bounded work after a proven mate

The F-56 exact-head gate's sole failure was a valid timeout after the engine already had a mate-in-one proof at depth 3. Added a single-PV early termination check at the maximal root score; MultiPV is intentionally unaffected. Targeted regression and all 400 seed-41 TT/bestmove probes pass; exact-head full gate pending.

## 2026-11-23 — F-58 infinite-analysis guard

Follow-up review caught that F-57's early mate exit also stopped `go infinite` analysis. Restricted the optimization to finite single-PV searches and added a protocol regression requiring further depth output before stop. Focused tests and clippy pass; full gate pending.

## 2026-11-23 — F-64 (fresh root-LMR miss)

The <=10-reply root threat guard still missed a verified mate-in-two in a 14-piece legal-game position with 11 defender replies. Oracle proof: `...Qd2` forces mate, and every reply is covered. Extending only the root reply cutoff to 11 recovers `mate 2`/`d4d2`; across eight saved tactical sets (631 positions), mismatches 1→0 at +0.234% total nodes. Added a protocol regression. Focused debug/release test, fmt and both clippy profiles pass; exact-head comprehensive gate and CI pending. No strength claim.

## 2026-11-23 11:14 UTC — F-64 closeout

Code/test head `97f3c04` passed the clean exact-head comprehensive gate (`/tmp/gates/97f3c04-final`, `FAILS=0`; release SHA-256 `80b32250fe9cc7026488965190a57a5ecdd9ff2a4c93da5bd15fad4760581b25`). Hosted Ubuntu/Windows/MSRV/artifact/anchor/SF10/opponent-build checks passed. Kilo is blocked by insufficient credits; CodeRabbit skipped. No strength/release claim.

## 2026-11-23 — F-65 (13-piece NMP false fail-high)

Another verified legal-game mate-in-two miss occurred at 13 pieces: `...Rh2` forces mate against all 15 replies, but prior depth-6 search returned cp 1186. The <=12 NMP cutoff still misses; disabling NMP through <=13 restores mate 2 / `h8h2`. Nine stored oracle sets (691 positions) improve 1→0 mismatches, aggregate nodes -0.02%; fixed bench nodes +2.45%, signature unchanged. Added regression; focused debug/release test and clippy pass; full gate/CI pending. Not an Elo claim.

## 2026-11-23 11:49 UTC — F-65 closeout

Exact code/test head `8c8f8a1` passed the clean comprehensive gate (`/tmp/gates/8c8f8a1-final`, `FAILS=0`; binary SHA-256 `137112f172882be8300c57a153c2ba0fb9fbf152298f0048b15ae0417b639ca8`). Hosted Ubuntu/Windows/MSRV/artifact/anchor/SF10/opponent-build checks passed. Fresh seed-10222026 holdout had 0/60 mismatches. Kilo lacks credits, CodeRabbit skipped. No Elo/release-readiness claim.

## 2026-11-23 — F-66 qsearch entry optimization

Reused the legal move list already generated at main-search depth/futility exits instead of regenerating it at qsearch entry. Scratch full release/debug tests, both clippy profiles, and formatting passed; depth-10 signature/nodes unchanged. Five interleaved A/B runs show median NPS +14.5% in this sandbox (timing is noisy). Exact-head final gate/CI pending; no strength claim.

## 2026-11-23 12:13 UTC — F-66 closeout

Code head `c4c124e` passed the clean comprehensive gate (`/tmp/gates/c4c124e-final`, `FAILS=0`; release SHA-256 `39fbac27cd010ec1cc623f748dfd06a40b46770bbee1a92a6cb05b1c0fd6e3ab`). Hosted Ubuntu/Windows/MSRV/artifact/anchor/SF10/opponent checks passed. Kilo lacks credits; CodeRabbit skipped. Sandbox bench timing only; no strength/release claim.

## 2026-11-23 12:18 UTC — F-66 behavior comparison

F-66 vs pre-reuse F-65 on fresh oracle-proven legal-game mate sets (seeds 11222026/12222026, 60 each): 0 mismatches in both binaries, identical aggregate nodes per set (102,465,537; 32,870,468). This is behavior-preservation evidence only, not strength evidence.

## 2026-11-23 12:22 UTC — F-66 extra check/rejected experiment

F-65/F-66 A/B on 100 random legal positions at depth 5 matched exact bestmove, score and nodes (1,165,553 total each). Early-exit legal reply counting was tested in five paired benchmarks and was marginally slower, so it was rejected; no movegen code change.

## 2026-11-23 12:23 UTC — extra F-66 differential checks

F-66 release: perft seeds 12/13 passed (334+406 positions, 2,220 depth checks total); legal-move differential seed 32 had 7,832 exact agreements, with only documented material-bound rejections among oracle-valid FENs. No movegen change.

## 2026-11-23 12:41 UTC — comprehensive exact-head gate

Full `scripts/final_gate.sh /tmp/gates/6bfc833-final` passed at clean head 6bfc8335059e4f4090aa6c9b715ba14c04395c32 (tree be5388ce90f2157b5bad58fb7f7d8b58107de8e4), exit 0, FAILS=0. Release digest unchanged. Logs retained in `/tmp/gates/6bfc833-final`.

## 2026-11-23 12:44 UTC — current hosted checks

Confirmed hosted CI on da8c37f: platform, MSRV, artifact, verify, calibration and all opponent builds pass. Kilo failed due known credits limitation; CodeRabbit skipped. No source changes since full exact-head gate.

## 2026-11-23 12:48 UTC — close loop on F-66 audit

Reviewed all state touched by legal-move generation and unmake. Saved list remains valid at direct qsearch call site; it carries moves only, and same position is unchanged. No extra change. CI on bfbc9c3 passed platform/MSRV/artifact/verification/calibration/opponent checks; Kilo credit-blocked, CodeRabbit skipped.

## 2026-11-23 12:50 UTC — final head hosted checks

All hosted build/test checks pass on 2456223; external Kilo credit block, CodeRabbit skipped. No code/CI fixes required.

## 2026-11-23 12:55 UTC — depth-7 randomized A/B

92 fresh legal random positions at depth 7 yielded identical score, bestmove and nodes between F-65 and F-66; total 5,581,590 nodes each. No source changes.

## 2026-11-22 — F-67 intended fifty-move claim correction

Reproduced the halfmove-98 checking-line defect in UCI and traced it to the claim available by announcing a legal quiet move at clock 99. Added clock-boundary recognition in main search and qsearch, preserving terminal mate precedence, the existing qsearch move-list handoff, TT clock safety, and strict root `searchmoves`. Added two regressions. Targeted draw-rule suite (9 tests), TT clock-unsafe test, fmt, and release build passed; full mission gate/holdouts remain pending. No move-generation code changed and no performance or strength claim is made.

## 2026-11-22 — F-67 TT boundary and tactical holdouts

Updated TT clock safety to use the earliest announced-claim boundary (99); added a no-eligible-quiet-move regression for the clock-99 case. F-67 UCI restricted line returns 0 cp at clocks 98/99/100. All 15 saved tactical FENs passed exact mate-distance/legality checks where applicable. Independent python-chess legal-game holdout seed 20261122: 24 oracle-proven positions (11 mate-in-one, 13 mate-in-two), 24/24 exact depth-6 mate distance and legal bestmove, 2,155,784 nodes. Full final gate/CI remain pending. No Elo/strength claim.

## 2026-11-22 — saved-finding dispositions reconciled

Explicitly reconciled the named recent tactical residuals: F-61→F-62 root safeguard and F-62 sixth-sample residual→F-63 NMP exclusion; current replay confirms exact mate 2 at depth 6 for both. Named F-41/F-44 and F-56/F-59–F-65/F-67 tactical examples pass their current checks. This does not close general selective-search risk.

## 2026-11-22 — F-67 comprehensive gate closeout on code head

Commit a891f82c71e807c56f3d57cdb0996beb0956653a / tree 186ddb7d92c0c4920a5a1a5806e9f39ff6d439fb passed `scripts/final_gate.sh /tmp/gates/a891f82-final`: exit 0, clean, FAILS=0. Release binary SHA-256 686235c9d5171182fc60668dfa23e518149fce9f6054497a9b4b43aaa0486df0. Full gate includes Rust debug/release tests/clippy, Python tests, perft/legal differentials, UCI/search/mate/TT/resource/clock checks, self-play and full games. Docs-only follow-up exact-head validation and hosted checks remain pending.

## 2026-11-22 — exact audit-head gate rerun

Commit 63eaa1f99aed35452d5f6a3d5d61f5a6504f5868, tree 3c003b15cf89deb56ba81969c3a2033a4710a41f, passed full final_gate (`/tmp/gates/63eaa1f-final`), clean, `FAILS=0`; release SHA-256 unchanged. Current follow-up adds only this validation record; exact-head gate and hosted CI follow.

## 2026-11-24 — PR #3/#4/#5 integration reconciliation (merged-tree provenance audit)

Phase A recon (fresh, exact): `main` HEAD `55b0671` is a single orphan commit whose tree equals the
stack's common ancestor `5e36b06` plus exactly one `.gitattributes` line (`*.py
linguist-detectable=false`); `git diff 5e36b06 55b0671` touches only `.gitattributes` (+1 line).
Ancestry verified with `git merge-base --is-ancestor`: PR #3 head `c25e65e` ⊂ PR #4 head `0795260`
⊂ PR #5 head `c96ab6a`; commit ranges base..P3=19, P3..P4=86, P4..P5=43, base..P5=148, linear, no
drops, duplicates, reverts, or rewrites. Reconciliation table: PR #3 scope INCLUDED, PR #4 scope
INCLUDED, PR #5 scope INCLUDED, main updates PRESERVED (via the merge below), duplicates: none.

Reconciliation commit `c37d75e7bfb5bdb1e9a18bb28437b614cb2cd58f` merges `55b0671` into
`arena/7584c0ca-flawlesschess` with `--allow-unrelated-histories` (main's squash is an orphan
branch; the stacked branch history is NOT rewritten — normal merge commit, no force-push). All 26
add/add conflicts were individually audited against the common ancestor before resolution: for 25
files main's content is byte-identical to `5e36b06`, so the PR-branch side preserves both sides'
intent; `.gitattributes` is resolved to main's version, preserving the sole main-side change.
Post-merge invariant verified by diff: merged tree differs from PR #5 head `c96ab6a` only in
`.gitattributes`, and that file is byte-identical to main `55b0671`. PR #5 base retargeted to
`main`; `gh pr view 5` reports MERGEABLE against `main` at `c37d75e`.

Phase A–C findings verification at `c37d75e` (all four outstanding review threads, fixed upstream in
the stack and re-verified here): (1) `scripts/uci_protocol_probe.py` bounded terminate/kill/reap,
pipe closure, reader joins, cleanup-as-failure in `check()` finally block — PASS 12/12;
(2) strict `searchmoves` (`bestmove 0000` on empty legal intersection, no widening, root filtering,
fallback, MultiPV consistent) — probe 299 positions/0 failures + unit regressions; (3)
`scripts/uci_extreme_args_probe.py` reader-thread/queue deadline applied to every wait, `stop`
after unbounded searches, bounded cleanup on every exceptional path — FAILURES: 0; (4)
`scripts/probe_io.py` bounded escalation and reap, explicit failure on unreaped child or stuck
reader, idempotent close, exit-code preservation — `scripts/test_probe_io.py` 3/3 OK.

Phase D exact-head gate at `c37d75e`: `scripts/final_gate.sh` on a clean worktree
(dirty-at-start 0), 47/47 steps rc=0, FAILS=0, exit 0, head/tree unchanged at end
(tree `f13b05481c0bbabf928aa3974ec2ed371a86385c`). Release binary SHA-256
`423d7f323c245ff0dc7ac03a849280f4de53b5d26d6d1475df90f9ba59e7a1a2`. Includes fmt, clippy
(debug/release, -D warnings), release+debug cargo suites (175 release tests; perft gates run in
release), 12 Python test suites, perft differentials s10/s11, legal differential s31, search sweep
s4, UCI protocol 12/12, malformed 37/37, extreme args 0 failures, grammar fuzz seed 201 (100
sessions), interleave fuzz seeds 11/7, resource probe, FEN extremes s101/s9, TT bestmove s41/s43,
searchmoves s51 (299 pos, MultiPV 3), PV legality s81, mate-in-1 s91, MultiPV s92, negative mate
s77, clock sweep s71 (60/60), time budget 8/8 (movetime elapsed/requested: 50 ms→1.014, 500
ms→1.002, 2000 ms→1.0004), selfplay 1000ms/300ms/40+15 clocks, full games with python-chess
referee at 20/60 ms movetime. Raw logs retained in untracked workspace copy
`audit-evidence/pr5-integration-c37d75e-final/` (repository path unavailable; see FAILURE_LEDGER).
No correctness fix was required on the integration head; no strength/Elo claim is made.

## 2026-11-24 — independent review round 1 on the integration head (CodeRabbit, full main...HEAD diff)

Requested an independent review of the combined `main...HEAD` diff at `0329d15`; CodeRabbit completed
with conclusion `success` and posted three inline findings, all Major and all about test-harness
robustness (no engine-code defect was found in the integrated diff):

1. `tests/movetime_smoke.rs` `legal_startpos_moves` used blocking `wait_with_output()` for the
   `moves` CLI child. VERIFIED VALID: a future regression that keeps the CLI alive would hang the
   suite while it holds the timing lock. FIXED: stdout drained on a reader thread with a 30 s
   `recv_timeout`; every exceptional return kills and reaps the child; the normal path preserves
   the real exit status (kill is a no-op after normal exit).
2. `tests/protocol_regressions.rs` closed-stderr oversized-line test used synchronous 200 KiB
   stdin writes and deadline-free read/wait. VERIFIED VALID: a child that stops draining stdin
   could block the test before any assertion. FIXED: stdin fed by a writer thread, stdout drained
   by a reader thread, 60 s deadlines on both, kill+reap on every exceptional return.
3. `tests/protocol_regressions.rs` `run_under_address_limit` killed the child without reaping on
   timeout and used an unbounded final `wait()`. VERIFIED VALID. FIXED: kill+wait on the timeout
   path; the final wait is preceded by a no-op-unless-alive kill so a stdout-closed-but-alive
   child cannot block and the real exit status is preserved.

Post-fix gates: fmt clean; clippy debug+release `-D warnings` clean; `cargo test` —
movetime_smoke 12/12, protocol_regressions 51/51 green. Codex review unavailable (account usage
limits); Kilo/Qodo unavailable (credits); CodeRabbit is the independent reviewer for this round.
No engine source changed; no strength/Elo claim.

## 2026-11-24 — hosted CI on the fix commit: one transient infra failure, rerun via re-push

Hosted CI (`CI`) passed on `33cbeb3`; `anchor-verify` reported one failed matrix job
(`build-wowl-1.3.7`) whose failed step is `actions/checkout@v4` — an infrastructure/checkout
failure, not a build, UCI-identity, bench-signature, or SF10-calibration failure (the same job
passed on the immediately preceding heads `0329d15` and `c37d75e`, and 12 sibling anchor jobs in
the same run succeeded; this commit changed only two test files under `tests/`). `gh run rerun`
was refused by the API ("workflow file may be broken"; the file is unchanged and valid — the same
refusal for a `workflow_dispatch` retry returned 403 for this token), so the run is retriggered by
pushing this documentation-only commit; hosted validation is re-required on the new exact head.
CodeRabbit's incremental check on `33cbeb3` concluded `neutral` (no new findings on the fix
commit). The exact-head local gate was restarted on `33cbeb3` (clean tree, dirty-at-start 0) and
will be re-run on the final head.

## 2026-11-24 — next-iteration session on `main` = `6ab5b33` (PR #5 merge)

### Phase 0 — actual baseline (verified)
- HEAD `6ab5b33` "Merge pull request #5 …" = origin/main; branch `arena/247fe7df-flawlesschess`;
  working tree clean; shallow snapshot (1 commit).
- `gh pr list` (state all): #1 MERGED, #2 OPEN/Draft/CONFLICTING (head `5f952b1`, 66 files,
  ~12,971 additions / 365 deletions), #3 MERGED, #4 MERGED, #5 MERGED.
- No Rust toolchain in this sandbox: `find / -name rustc` empty; `static.rust-lang.org` TLS
  blocked (SSL_ERROR_SYSCALL); `deb.debian.org` unreachable. `github.com`/`api.github.com` and
  `pypi.org`/`registry.npmjs.org` reachable.
- `lichess.org` TLS blocked → Phase 1 live game export not possible from this sandbox.

### Phase 0 — PR #2 audit reconciliation (NOT merged, NOT cherry-picked)
PR #2 "Flawless: throughput, move ordering, and evaluation work (screening evidence)" contains
experimental categories matching the mission's SPEED-1 / HIST-1 / EVAL-2 framing. Commits on its
branch include, among others: analytic fast legality filter (+78% nps, identical bench signature
`141943aa23b3fc68`, tree provably unchanged); static-evaluation reuse per node through quiescence;
precomputed file/ahead-rank masks; continuation history + counter moves + capture history;
evaluation upgrade behind per-feature ablation flags; EVAL-2 evaluation changes; Windows static-CRT
artifact hardening; CodeRabbit review dispositions; control/seed-robustness registrations.

Reconciliation against `main` (`6ab5b33`): none of these changes are present in `main`. Per the
mission, PR #2 is NOT merged, NOT cherry-picked, and NOT silently closed. Its candidates remain
unvalidated on `main` and cannot be ported in this session because no compiler is available to run
the perft/difftest/UCI/gates required to accept or reject them. They are documented here as the
input to a later, gated iteration.

### Environment constraints (binding for this session)
- No `cargo build / test / clippy` can run → no engine source was changed without compile-testing,
  per the "correctness before complexity" principle. No benchmark, NPS, perft, or strength number
  was measured here; no unmeasured Elo/strength claim is made.
- No live Lichess API → Phase 1 real-game analysis could not be executed against actual
  Flawless games; the limitation is recorded rather than fabricating observations.

### Phase 5 — prioritized engineering plan (next gated iteration)
When a Rust toolchain is available, execute in this order, each behind its own commit with
`cargo test` + perft + a strength screening gate:
1. Correctness first: re-run the full existing gate suite on `6ab5b33` (fmt, clippy -D warnings,
   release tests, perft CPW matrix, diftest vs python-chess 1.11.2, UCI protocol regressions,
   clock/movetime smoke) and confirm green on the exact final HEAD before any change.
2. PR #2 candidates, audited individually against `main` (feature isolation + ablation; do not
   combine unrelated changes): (a) fast legality filter — verify identical bench signature and
   node count, then measure NPS; (b) continuation/counter/capture history — measure fixed-time
   strength with opening-clustered CI; (c) evaluation upgrade — gate each ablation flag on its
   own measured result, no silent defaults. Reject any change whose CI lower bound contains zero.
3. Only after correctness + isolated, statistically supported candidates pass: port them, each
   with a regression test, on separate commits (correctness / search / evaluation / performance /
   tests / documentation).
4. Documentation: keep STATUS.md / CHANGELOG.md / AGENTS_LOG.md synchronized; record exact SHAs
   and benchmark identifiers; never claim an unmeasured Elo.
5. Merge readiness: one clean dev branch from `main`, focused PR to `main`, CI green on final
   HEAD, review findings dispositioned, PR not merged without authorization.

### Changes made in this session (documentation / plan only)
- `STATUS.md`: reconciled current-state claims (PRs #1/#3/#4/#5 merged; PR #2 open/draft/conflicting;
  current branch `arena/247fe7df-flawlesschess` at `6ab5b33`; V1 rating gate still NOT MET).
- `CHANGELOG.md`: added `[Unreleased]` entry for documentation reconciliation + environment
  constraints + plan (2026-11-24).
- `AGENTS_LOG.md`: this entry.
- No `src/` or `tests/` changes (cannot compile-test).

## 2026-11-24 — current session (branch arena/247fe7df-flawlesschess, PR #6 draft)

Toolchain recovered from npm `@toolchain-bin/*` 1.99.0 pins into `/home/user/.toolchain/sysroot`
(static.rust-lang.org unreachable; crates.io unreachable). Python venv with python-chess 1.11.2 at
`/home/user/.venv`.

### Changes implemented

1. **Time management** (src/search.rs, commit d5305ee): removed the predictive-overrun early stop
   that halted clock-based searches well before the soft budget. At 10 s the engine previously
   stopped at 116 ms of a 234 ms soft budget (depth 9); it now runs to depth 10 at ~253 ms. At
   1 min it reaches depth 12 at ~1.65 s. Hard budget still caps worst-case overspend; fixed-depth
   / movetime searches unaffected (bench signature unchanged).

2. **Counter move heuristic** (src/search.rs, commit a162baa, HIST-1 from PR #2 audit): when a
   quiet move causes a fail-high cutoff in reply to the opponent's previous move, store it as a
   counter move. Ordered just above killers (92,000) and below good captures. Counter table
   cleared each root search like killers/history; not used in null-move search or quiescence.

3. **Space evaluation** (src/eval.rs, src/main.rs, commit 4038b75, EVAL-2 from PR #2 audit):
   reward control of important squares weighted by centrality (centre squares weighted most).
   Colour-symmetric via square mirroring (sq ^ 56). Tapered: full weight in middlegame, half in
   endgame. Added `space` field to `EvalBreakdown` and CLI `eval` output.

### Validation (local, this sandbox)

- `cargo fmt --all -- --check`: clean
- `cargo clippy --release --all-targets -- -D warnings`: clean
- `cargo test --release`: **172/172 passed** (49 lib + 3 cli_batch + 3 cli_divide + 3 clock_smoke +
  43 correctness + 12 movetime_smoke + 51 protocol_regressions + 11 uci_smoke)
- `scripts/diftest.py`: **2,321 positions d=2, 0 mismatches** (python-chess oracle)
- `./target/release/flawless perft 6`: **119,060,324** (matches CPW reference)
- `./target/release/flawless bench`: signature **141943aa23b3fc68** (unchanged from pre-change
  baseline)
- `scripts/test_match.py`: **111/111 passed**
- `scripts/test_rating_estimator.py`: 65/65 checks pass; null control FAIL is pre-existing
  (anchor/environment issue, not engine-related)

### Not done

- Absolute rating: UNKNOWN / NOT MET (V1 gate requires >2,000 with 95% CI lower bound strictly
  >2,000)
- Fresh CodeRabbit review at final SHA: not yet performed
- MSRV 1.80 compile: not locally verifiable (no 1.80 toolchain obtainable; delegated to CI)
- Windows execution: not locally verifiable (delegated to CI)
- Continuation history (remaining HIST-1 element): not yet implemented
- Outpost/other evaluation terms (remaining EVAL-2 elements): not yet implemented
- PR #2 (open, draft, conflicting): NOT merged, NOT cherry-picked, NOT touched

## 2026-11-24 — PR #6 iteration: outpost correction, tempo semantics, ablation switch, paired benchmark

Branch `arena/247fe7df-flawlesschess`, PR #6 (draft, base `main` = `6ab5b33`). No merge, no tag, no
release, PR #2 untouched.

### Environment

The Rust toolchain was recovered a third time from the npm `@toolchain-bin/*` 1.99.0 pins into
`/home/user/.toolchain/sysroot` (rustc 1.99.0, cargo 1.99.0, rustfmt 1.10.0, clippy 0.1.99), because
`static.rust-lang.org` and `crates.io` are blocked. The crate has zero dependencies, so cargo builds offline.
Python venv with python-chess 1.11.2 at `/home/user/.venv`.

Two sandbox limits shaped the tooling work:
* The **Actions log host is unreachable**, so CI failures are surfaced through annotations (`::error::`)
  instead of the log, and the benchmark summary is published to the job summary and a pull request comment.
* The **workflow dispatch API is forbidden for this token** (HTTP 403), so the extended benchmark is started
  by moving `benches/benchmark-request.json`, the deliberate-dispatch pattern of `evidence-bridge.yml`.

### Engine changes

1. **Outpost zone (src/eval.rs).** Corrected to the classical definition: White ranks 5-6, Black ranks 3-4,
   files b-g. The old zone (ranks 5-8 / 1-4) included the opponent's back rank and the rank in front of it,
   where no enemy pawn can exist, so the "safe from enemy pawns" test was vacuous there.
2. **Tempo semantics (src/eval.rs).** `relative` and `total` are now separate statements. The old expression
   `if side == WHITE { tapered } else { -tapered } + TEMPO` was checked against the rustc parser source
   (`parse_expr_assoc_rest` only stops at a complete statement expression in statement position, so the `+`
   binds to the whole `if` expression) and against the pre-existing 303-pair colour-symmetry test, which is
   green on the PR head and would fail if the tempo were applied to one colour only. The behaviour is now
   pinned by a dedicated test for both colours and the colour mirror, and `EvalBreakdown` exposes `mg`, `eg`
   and `phase`.
3. **Ablation switch (src/ablation.rs, docs/ABLATIONS.md).** `FLAWLESS_ABLATE` with the terms `space`,
   `counter_move`, `outpost`. Off by default, read once per process, applied as a bit mask so the hot path
   pays one atomic load and a bit test.
4. **Benchmark tooling.** `scripts/match.py` (explicit thread count, schedule and replay metadata per game),
   `scripts/relative_benchmark.py` (quick and extended profiles, opening-clustered bootstrap, fail-closed
   validation), `scripts/publish_benchmark_summary.py`, `.github/workflows/relative-benchmark.yml`.

### Validation

Local (toolchain 1.99.0): fmt clean; clippy `-D warnings` clean; `cargo test --release --locked` 183/183
(55 lib, 3 cli_batch, 3 cli_divide, 3 clock_smoke, 45 correctness, 12 movetime_smoke, 51 protocol_regressions,
11 uci_smoke); difftest 2,321 positions d=2, 0 mismatches; perft(6) 119,060,324; bench signature
`141943aa23b3fc68`, identical to the pinned baseline and stable over three runs — with the refined
definition none of the twelve bench positions has a pawn-defended outpost square, so the term contributes
nothing there; match harness
112/112; benchmark suite 20/20.

Hosted CI on the same head: fmt, clippy, tests, MSRV 1.80 and the Windows artifact job green; the quick
paired benchmark job completes in about ten minutes and publishes its summary.

One real defect was caught by the local toolchain run and not by review: the rank-6 outpost fixture used a
black pawn on b5, which does not attack a knight on c6 (the pawn has to stand on b7), so the expectation was
wrong, not the engine.

### Relative evidence and its limits

**The decisive measurement of this iteration is negative.** The hosted three-replicate extended profile —
candidate against the pinned baseline `6ab5b33`, 100 paired openings per replicate, seeds 20261124/25/26,
movetime 100 ms, hash 64 MB, one thread — finished **217 W / 164 D / 219 L of 600**, score **299.0/600 =
49.8%**, relative Elo **-23.2 to +21.5** (95% CI, opening-clustered percentile bootstrap), classification
**INCONCLUSIVE**, `valid: true`. No strength difference against the pinned baseline is measurable.

The quick profile is far noisier than the profile size suggests. Seven hosted runs of the same 20-opening
profile with the same seed, over heads whose engine code differs in at most one term, scored 40.0%, 42.5%,
36.2%, 48.8%, 50.0%, 65.0% and 52.5%. **Three of those heads have no engine change at all** — `5be7d7b`,
`6aae7f7` and `40b3556` differ from `98e5cd9` only in documentation and workflow files — and they scored
50.0%, 65.0% and 52.5%. The same profile therefore swings from 36.2% to 65.0% on an unchanged engine, and
it produced both a `NEGATIVE_RELATIVE_SIGNAL_NOT_SEVERE` label and a
`POSITIVE_RELATIVE_SIGNAL_SCREENING_ONLY` label for the same code.

The reason is that a fixed 100 ms movetime makes the reached depth depend on the machine speed and the
timing jitter, so the played games are **not** reproducible across runs even with the same opening seed.
The seeded shuffle fixes the *opening order*, not the games. A 40-game profile at this time control carries
roughly ±30 Elo of pure sampling noise, and its classification label must not be read as a strength
signal. The 600-game profile is the only one of these worth reading.

All of this is a fixed-movetime screening comparison against a single opponent. It is not an official
rating, not an absolute rating, and not a strength claim.

### PR #2 audit (read only)

PR #2 (`arena/8259ce1c-flawlesschess`, head `5f952b1`) diverges from `main` at `5e36b06`: 49 commits,
12,971 insertions, 66 files, draft and in conflict with `main`. It was **not** merged, cherry-picked,
modified or closed. Findings:

- **Overlap.** PR #2 also implements an outpost term, the counter-move heuristic, continuation and capture
  history, a fast legality filter and a large rating-harness expansion. The space evaluation and the
  counter-move heuristic in this PR are independent reimplementations of the same ideas.
- **Acted upon.** PR #2's outpost term requires a pawn-defended square and a square that an enemy pawn
  cannot even step forward to attack. This PR's term had neither condition and rewarded an undefended
  piece. Both conditions were added to this PR's own implementation, with regression tests.
- **Not acted upon.** PR #2's zone ("rank 4 or beyond for White") includes White's own fourth rank, and its
  outpost value is a flat +16/+8 for knight and bishop. This PR keeps the explicit zone and the
  differentiated values.
- **Not comparable.** PR #2's own screening results are recorded as INCONCLUSIVE and its branch conflicts
  with `main`; porting its fast legality filter or its history heuristics would need its own measurement.

### Not done

- Absolute V1 rating gate: UNKNOWN / NOT MEASURED / NOT MET.
- Fresh independent review at the final head SHA: not performed here.
- PR #2: NOT merged, NOT cherry-picked, NOT touched.

---

## 2026-11-25 — Addendum: provenance of the hosted relative benchmark runs

The 2026-11-24 entry above records the 600-game result but not the identifiers needed to trace it.
This addendum supplies them. **It does not change any result and does not weaken any conclusion.**

### The revision-1 extended run that produced 217 W / 164 D / 219 L

* **Candidate commit measured:** `78f42ca4c382dd40d425b13fc0e204fadc1e73fc` (`78f42ca`).
* **Pinned baseline:** `6ab5b3349264c6c0a740c433ce454f8e1fed698a` (`6ab5b33`).
* **Hosted workflow run:** `45426475825` ("ci: dispatch the extended benchmark through a request
  marker"), workflow *Relative strength benchmark*, status completed/success.
* **Result:** 217 W / 164 D / 219 L, score 49.8%, relative Elo **-23.2 to +21.5** (95% CI),
  classification **INCONCLUSIVE**. Screening evidence only — not an absolute rating, not a strength
  claim.

The three replicates and their artifacts. The seed of a replicate is `20261124 + replicate - 1`:

| Replicate | Seed | Hosted artifact name | Artifact id |
| --------- | ---- | -------------------- | ----------- |
| 1 | 20261124 | `relative-strength-extended-45426475825-1` | `14940617228` |
| 2 | 20261125 | `relative-strength-extended-45426475825-2` | `14940712905` |
| 3 | 20261126 | `relative-strength-extended-45426475825-3` | `14942235054` |
| pooled | — | `relative-strength-extended-aggregate-45426475825` | `14942210869` |

The pooled summary is the aggregate artifact; the three replicate artifacts hold the raw
`games.jsonl`, the PGN, the seeded opening order and the per-replicate summary. Artifact download
from this sandbox fails with an EOF from the GitHub blob host, so the numbers above were read from
the published job summary and pull request comment, and the identifiers above come from the runs and
artifacts API.

### The revision-2 extended run on the refined head

Dispatched against candidate `5be7d7bbcc03ccb63d12138bef6a390be90aa957`, a descendant of the
refined-outpost commit `98e5cd9`. Hosted workflow run `45529006866`, completed/success.

| Replicate | Seed | Hosted artifact name | Artifact id |
| --------- | ---- | -------------------- | ----------- |
| 1 | 20261124 | `relative-strength-extended-45529006866-1` | `14985947939` |
| 2 | 20261125 | `relative-strength-extended-45529006866-2` | `14987270574` |
| 3 | 20261126 | `relative-strength-extended-45529006866-3` | `14987315209` |
| pooled | — | `relative-strength-extended-aggregate-45529006866` | `14986247256` |

Result read back from the published summary: **227 W / 156 D / 217 L** of 600, score
**305.0/600 = 50.8%**, relative Elo **-19.7 to +31.4** (95% CI, opening-clustered), classification
**INCONCLUSIVE**, 100 opening clusters, elapsed 8547.3 s.

**Still no measurable strength difference against the pinned baseline.** The point estimate moved
from 49.8% to 50.8% between the two revisions, and the confidence interval still straddles 50%.
Both revisions are inconclusive; neither is a strength claim, and neither is an absolute rating.

The published title of that summary reads `seeds ..2` instead of `seeds 20261124..20261126`. That is
the `SEED_BASE` defect that was found by review and fixed afterwards: the publishing step did not
receive the seed base. The title is cosmetic — the seeds are in the manifests and in the artifact
names above — but it is the reason the fix was made.

### The ablation matrix

Dispatched against candidate `d306cbcefc07e46c1c239eb3dfe3318f864d8286`, also a descendant of
`98e5cd9`. Hosted workflow run `45529550258`, `screen` profile, seed `20261130`, 100 paired openings
per variant (200 real UCI games per variant). All four variants completed/success.

| Variant | `FLAWLESS_ABLATE` | W/D/L | Score | Relative Elo (95% CI) | Artifact id |
| ------- | ----------------- | ----- | ----- | -------------------- | ----------- |
| `full` | (unset) | 81 / 52 / 67 | 53.5% | -17.4 to +68.6 | `14986197901` |
| `no-space` | `space` | 72 / 71 / 57 | 53.8% | -12.2 to +65.0 | `14986616605` |
| `no-counter-move` | `counter_move` | 72 / 47 / 81 | 47.8% | -57.9 to +27.9 | `14987251123` |
| `no-new-terms` | `space,counter_move,outpost` | 63 / 61 / 76 | 46.8% | -59.6 to +17.4 | `14986133518` |

**Every variant is INCONCLUSIVE, and every confidence interval overlaps every other one.** The
ablated variants score slightly below the full engine, which is the direction one would expect, but
the differences are inside the noise of the profile: the `full` variant of the *same* profile scored
between 36.2% and 65.0% across the hosted runs recorded above, a spread far wider than the spread
between these four variants.

So the honest reading is: **this ablation study does not measure the contribution of any of the
three terms.** It cannot distinguish them from noise at this sample size and time control. The
switch itself is verified — the terms are removed from the evaluation and the scores change
accordingly, deterministically — but the *magnitude* of each term's contribution is not measured by
this run. A study that could measure it needs either many more games or a time control that makes
the played games reproducible; the quick/screen profiles have neither.

All of this is a fixed-movetime screening comparison against a single opponent. It is not an
official rating, not an absolute rating, and not a strength claim.

### The runs that were dispatched against earlier heads

Both runs above were dispatched against heads that precede the current head (`3e0fe75` at the time
of writing). Neither result may be attributed to the current head. The engine source is the same
for the extended revision-2 run and the ablation matrix as for the current head, because the commits
in between changed only the workflow and the request marker; but the recorded candidate SHA is the
one that was actually built and measured, and it is recorded above rather than the head.

### Review disposition

The 20 CodeRabbit findings raised on the previous head were read back and dispositioned in commit
`67bee13`. Nineteen were fixed. The twentieth, a reported advancing-pawn defect in `src/eval.rs`,
was reproduced and is a **false positive**: the cited position
`4k3/1p6/8/2N5/8/8/8/4K3 w - - 0 1` scores outpost 0 because the knight is not pawn-defended, and
the defended variant `4k3/1p6/8/2N5/3P4/8/8/4K3 w - - 0 1` also scores outpost 0, because the b7 pawn
steps to b6 and attacks c5. The algorithm is unchanged; the b7 case, its colour mirror and the
undefended case were added as regressions.

---

## 2026-11-25 — Addendum: the quick-profile variance, corrected

The 2026-11-24 entry above claims that the 40-game quick profile "swings from 36.2% to 65.0% on an
unchanged engine" and that it produced both a `NEGATIVE_RELATIVE_SIGNAL_NOT_SEVERE` and a
`POSITIVE_RELATIVE_SIGNAL_SCREENING_ONLY` label "for the same code". **Both claims are wrong as
written.** This addendum corrects them; the entry above is left untouched because the log is
append-only.

The error: the 36.2% run used `dcdc4b4`, which is **before** `98e5cd9` (the refined outpost term, the
last change to `src/` on this branch). The 65.0% run used `6aae7f7`, which is **after** it. The two
runs therefore used different engines, and they cannot be paired as "the same code".

What the runs actually show. The last change to `src/` on this branch is `98e5cd9`; `Cargo.toml`,
`Cargo.lock`, `rust-toolchain.toml` and `build.rs` are unchanged since then, so every head below
`98e5cd9` in this list produced a **byte-identical release binary**:

| Head | Engine change | W/D/L | Score | Classification |
|---|---|---|---|---|
| `504924b` | outpost fixture fix | 9/14/17 | 40.0% | INCONCLUSIVE |
| `78f42ca` | benchmark dispatch | 11/12/17 | 42.5% | INCONCLUSIVE |
| `dcdc4b4` | docs only | 9/11/20 | 36.2% | NEGATIVE_RELATIVE_SIGNAL_NOT_SEVERE |
| `98e5cd9` | refined outpost term (last `src/` change) | 13/13/14 | 48.8% | INCONCLUSIVE |
| `794a465` | **no engine change** | 13/13/14 | 48.8% | INCONCLUSIVE |
| `5be7d7b` | **no engine change** | 16/8/16 | 50.0% | INCONCLUSIVE |
| `6aae7f7` | **no engine change** | 21/10/9 | 65.0% | POSITIVE_RELATIVE_SIGNAL_SCREENING_ONLY |
| `40b3556` | **no engine change** | 17/8/15 | 52.5% | INCONCLUSIVE |
| `90227a6` | **no engine change** | 23/9/8 | 58.8% | INCONCLUSIVE |
| `7510ded` | **no engine change** | 23/9/8 | 58.8% | INCONCLUSIVE |
| `d306cbc` | **no engine change** | 22/12/6 | 55.0% | INCONCLUSIVE |
| `c2cc288` | **no engine change** | 16/9/15 | 51.2% | INCONCLUSIVE |
| `3e0fe75` | **no engine change** | 15/13/12 | 53.8% | INCONCLUSIVE |
| `f0316b0` | **no engine change** | 22/8/10 | 55.0% | INCONCLUSIVE |

The corrected claims:

* **On an unchanged engine the profile ranges from 48.8% to 65.0%** — eleven runs of a
  byte-identical binary over the same 20 openings and the same seed.
* **On that same unchanged engine the label is not stable**: one run produced
  `POSITIVE_RELATIVE_SIGNAL_SCREENING_ONLY` (`6aae7f7`, 65.0%) and the other ten produced
  `INCONCLUSIVE`.
* The `NEGATIVE_RELATIVE_SIGNAL_NOT_SEVERE` label belongs to `dcdc4b4`, a **different** engine.
* The overall range across all heads is 36.2%–65.0%, but that range spans two different engines and
  must not be quoted as an unchanged-engine spread.

The conclusion does not change: the 40-game quick profile is a regression screen, not a strength
signal. The corrected numbers make the case stronger rather than weaker — the spread on *identical*
code is 16.2 points, and the label flips on identical code.

### Consequence for the ablation study

The ablation entry above compares the spread between the four variants against "the 36.2%-65.0%
spread that the same profile produced across repeated runs of an unchanged engine". That comparison
is corrected to the unchanged-engine spread of **48.8%-65.0%**. Note that the ablation matrix uses the
`screen` profile (200 games) and the variance figures come from the `quick` profile (40 games), so
the two are not the same instrument; the conclusion rests on the overlapping confidence intervals,
which stand on their own.

The honest statement of what the ablation study establishes:

* Each variant is **INCONCLUSIVE** against the baseline, and the four intervals overlap completely.
* The point estimates differ (46.8% to 53.8%), which is the direction one would expect, but the
  design cannot separate that difference from the profile's own noise.
* The switch itself is verified deterministically: the named terms are removed from the evaluation
  and the scores change accordingly.
* The **magnitude** of each term's contribution is **not** measured. A sharper design would need a
  paired difference over the shared openings and a time control that makes the played games
  reproducible; the artifacts of this run cannot be downloaded from the development sandbox, so that
  paired analysis was not performed here.

### Addendum to the addendum: the unchanged-engine run set grew

The quick profile now runs on every push to this branch, so every push adds one more run of the
**same byte-identical release binary**. The corrected table above was written when eleven such runs
had been observed; three more have since appeared, and they widen the range:

| Head | W/D/L | Score | Classification |
|---|---|---|---|
| `13f8162` | 12/13/15 | 46.2% | INCONCLUSIVE |
| `25d7d66` | 24/9/7 | 61.3% | INCONCLUSIVE |
| `02b58bd` | 22/8/10 | 55.0% | INCONCLUSIVE |

**On an unchanged engine the profile therefore ranges from 46.2% to 65.0% over fourteen runs**, and
the same unchanged engine produced the label `POSITIVE_RELATIVE_SIGNAL_SCREENING_ONLY` in one run
(`6aae7f7`) and `INCONCLUSIVE` in the other thirteen. This is a lower bound: every further push adds
another run, and the spread is not expected to narrow.

The three runs above `98e5cd9` in the earlier table (`504924b` 40.0%, `78f42ca` 42.5%, `dcdc4b4`
36.2%) remain on a *different* engine and are not part of this range.

---

## 2026-11-25 — Addendum: the extended profile on the final head

A third extended run was dispatched against the exact head of the branch and read back.

* **Candidate commit measured:** `13f8162ebe66af286447603e4026e2c990351538` (`13f8162`).
* **Pinned baseline:** `6ab5b3349264c6c0a740c433ce454f8e1fed698a` (`6ab5b33`).
* **Hosted workflow run:** `45546563480` (push dispatch of revision 6 of the request marker),
  completed/success.
* **Seeds:** 20261201, 20261202, 20261203 — independent of the seeds of the two earlier extended runs.

| Replicate | Seed | Hosted artifact name | Artifact id |
| --------- | ---- | -------------------- | ----------- |
| 1 | 20261201 | `relative-strength-extended-45546563480-1` | `14994002536` |
| 2 | 20261202 | `relative-strength-extended-45546563480-2` | `14993832110` |
| 3 | 20261203 | `relative-strength-extended-45546563480-3` | `14994391549` |
| pooled | — | `relative-strength-extended-aggregate-45546563480` | `14994810229` |

Result read back from the published summary: **229 W / 163 D / 208 L** of 600, score
**310.5/600 = 51.7%**, relative Elo **-11.0 to +35.4** (95% CI, opening-clustered), classification
**INCONCLUSIVE**, 100 opening clusters, elapsed 8467.4 s.

The published title reads `seeds 20261201..20261203`. It read `seeds ..2` for the previous run,
because the publishing step did not receive the seed base; that defect was found by review and is
fixed, and this run confirms the fix.

The engine source at `13f8162` is byte-identical to the final head of the branch: the last change
to `src/` is still the outpost refinement `98e5cd9`, and `Cargo.toml`, `Cargo.lock`,
`rust-toolchain.toml` and `build.rs` are unchanged since then. The commits between `13f8162` and
the final head change the request marker, the review fixes and the records only.

### The three extended runs, side by side

| Revision | Candidate | Run | Games | W/D/L | Score | Relative Elo (95% CI) | Classification |
|---|---|---|---|---|---|---|---|
| 1 (pre-refinement) | `78f42ca` | `45426475825` | 600 | 217 / 164 / 219 | 49.8% | -23.2 to +21.5 | INCONCLUSIVE |
| 2 (refined) | `5be7d7b` | `45529006866` | 600 | 227 / 156 / 217 | 50.8% | -19.7 to +31.4 | INCONCLUSIVE |
| 3 (final head) | `13f8162` | `45546563480` | 600 | 229 / 163 / 208 | 51.7% | -11.0 to +35.4 | INCONCLUSIVE |

The point estimates drift upward across the three runs — 49.8%, 50.8%, 51.7% — and **every interval
straddles 50%**. That is what a sequence of inconclusive results looks like when the underlying
effect is small: the estimates wander around the baseline in the direction the noise allows, and the
intervals keep covering it. Reading the upward drift as a strength signal would be reading noise.

**The honest conclusion is unchanged: no strength difference against the pinned baseline `6ab5b33` is
measurable.** This is screening evidence against a single opponent at a fixed movetime. It is not an
official rating, not an absolute rating, and not a strength claim. The absolute V1 rating gate
remains UNKNOWN / NOT MEASURED / NOT MET.

### Addendum: two more unchanged-engine runs

The quick profile runs on every push, so two more runs of the same byte-identical release binary
landed after the previous addendum: `c428d66` 60.0% (24/7/9) and `ff10c55` 55.0% (22/8/10). Both are
inside the recorded range.

**On an unchanged engine the profile ranges from 46.2% to 65.0% over sixteen runs**, and the same
unchanged engine produced the label `POSITIVE_RELATIVE_SIGNAL_SCREENING_ONLY` in one run and
`INCONCLUSIVE` in the other fifteen. The range is a lower bound: every further push adds another run,
and the spread is not expected to narrow.

### Addendum: the unchanged-engine range widens to 28.7 points

Two more quick runs on the same byte-identical release binary: `97c8a81` 67.5% (22/10/8), classified
`POSITIVE_RELATIVE_SIGNAL_SCREENING_ONLY`, and `e61d635` 38.8% (9/13/18), classified `INCONCLUSIVE`.

**On an unchanged engine the profile now ranges from 38.8% to 67.5% over eighteen runs** — 28.7 points
apart on code that did not change — and the same unchanged engine produced
`POSITIVE_RELATIVE_SIGNAL_SCREENING_ONLY` in two runs and `INCONCLUSIVE` in the other sixteen.

The byte-identity was verified directly rather than asserted: all eighteen measured heads have the
identical `src/` tree `daa6be83ad991ee16eb86986e9eaa676c9eea460` and identical `Cargo.toml`
`12660a71`, `Cargo.lock` `38aa7239` and `rust-toolchain.toml` `b6cff89e`, so they cannot differ in the
release binary. The range is a lower bound: the profile runs on every push, so every further push adds
another run.

This is the clearest possible demonstration that the 40-game quick profile carries no strength
information at all, and it is why the 600-game extended profile is the only one of these worth reading.

### Correction: the quick-run table was mis-transcribed

CodeRabbit flagged that six rows of the quick-run table in `STATUS.md` had W/D/L counts that do not
match their own scores. It was right, and checking the published hosted summaries directly showed the
error was wider than the flag: the **scores** in the table were correct, but the **W/D/L counts** were
transposed in nine rows, and **two runs had been missed entirely** (`ad9915d` and `68f5111`). The
earlier extraction had queried the PR comments with `per_page=100` and no pagination and did not
re-read the full set.

Every row below is transcribed from the published hosted summary and checked against the scoring
formula `(wins + draws / 2) / games`. All twenty-three quick runs agree with the formula:

| Head | W/D/L | Score | Classification | Engine |
|---|---|---|---|---|
| `504924b` | 9/14/17 | 40.0% | INCONCLUSIVE | pre-refinement |
| `78f42ca` | 11/12/17 | 42.5% | INCONCLUSIVE | pre-refinement |
| `dcdc4b4` | 9/11/20 | 36.2% | NEGATIVE_RELATIVE_SIGNAL_NOT_SEVERE | pre-refinement |
| `98e5cd9` | 13/13/14 | 48.8% | INCONCLUSIVE | **last `src/` change** |
| `5be7d7b` | 16/8/16 | 50.0% | INCONCLUSIVE | unchanged |
| `6aae7f7` | 21/10/9 | 65.0% | POSITIVE_RELATIVE_SIGNAL_SCREENING_ONLY | unchanged |
| `40b3556` | 17/8/15 | 52.5% | INCONCLUSIVE | unchanged |
| `90227a6` | 17/13/10 | 58.8% | INCONCLUSIVE | unchanged |
| `7510ded` | 20/7/13 | 58.8% | INCONCLUSIVE | unchanged |
| `d306cbc` | 16/12/12 | 55.0% | INCONCLUSIVE | unchanged |
| `794a465` | 15/9/16 | 48.8% | INCONCLUSIVE | unchanged |
| `c2cc288` | 16/9/15 | 51.2% | INCONCLUSIVE | unchanged |
| `3e0fe75` | 15/13/12 | 53.8% | INCONCLUSIVE | unchanged |
| `f0316b0` | 16/12/12 | 55.0% | INCONCLUSIVE | unchanged |
| `13f8162` | 12/13/15 | 46.2% | INCONCLUSIVE | unchanged |
| `25d7d66` | 19/11/10 | 61.3% | INCONCLUSIVE | unchanged |
| `02b58bd` | 17/10/13 | 55.0% | INCONCLUSIVE | unchanged |
| `ad9915d` | 19/9/12 | 58.8% | INCONCLUSIVE | unchanged (**missed before**) |
| `68f5111` | 18/13/9 | 61.3% | POSITIVE_RELATIVE_SIGNAL_SCREENING_ONLY | unchanged (**missed before**) |
| `c428d66` | 19/10/11 | 60.0% | INCONCLUSIVE | unchanged |
| `ff10c55` | 17/10/13 | 55.0% | INCONCLUSIVE | unchanged |
| `97c8a81` | 22/10/8 | 67.5% | POSITIVE_RELATIVE_SIGNAL_SCREENING_ONLY | unchanged |
| `e61d635` | 9/13/18 | 38.8% | INCONCLUSIVE | unchanged |

The derived claims, restated:

- **On an unchanged engine the profile ranges from 38.8% to 67.5% over twenty runs**, and the same
  unchanged engine produced `POSITIVE_RELATIVE_SIGNAL_SCREENING_ONLY` in **three** runs and
  `INCONCLUSIVE` in the other **seventeen**. The spread is **28.7 points** on code that did not change.
- The three pre-refinement runs read 40.0%, 42.5% and 36.2%; they are on a different engine and are
  not part of that range. The overall observed range across all heads is 36.2%–67.5% and spans two
  different engines.
- The range and the counts are a lower bound: the profile runs on every push, so every further push
  adds another run, and the spread is not expected to narrow.

The earlier figures (a 46.2%–65.0% range over "fourteen" runs, later "sixteen", later "eighteen", and
"one" positive run) were each correct only for the incomplete set that had been extracted at the time,
and the count of runs was wrong from the start. The corrected set above is the complete one as of this
commit.

This does not change the conclusion the table supports: the 40-game quick profile carries no strength
information at all, and the 600-game extended profile is the only one of these worth reading.

### Correction: the losing-games PGN corrupted every record after the first

CodeRabbit flagged that `scripts/diagnose_weaknesses.py` joined the PGN records with a single newline.
`str(chess.pgn.Game())` has no trailing newline and a PGN reader ends a game at the blank line, so the
next game's headers were consumed by the preceding record.

Reproduced against python-chess 1.11.2: with a single newline the second record is still parsed, but
its headers come back as the unknown marker `?` — `Round` and `White` are gone, so the record no longer
says which game it is or who played it. With a blank line both records keep their headers and their
move histories.

Fixed by joining the records with `"\n\n"`. The regression in `scripts/test_diagnose_weaknesses.py`
writes two records, reads the file back with `chess.pgn.read_game` until it is exhausted, and checks
that both games keep their own round header, player headers and move history; it also checks that the
single-newline form is what strips the later headers, so the regression cannot silently stop guarding
the defect. The suite is now 31 checks.

The latest local diagnostic run (`benches/diagnose-20261124/`) found no losses at all, so its
`losing-games.pgn` is empty and the defect was invisible there. It would have bitten the first run
that produced two or more losses.

### The gate on the corrected head

The full local gate suite ran on `99bef0133f1bc5e2f1d5aab6a5ffc122df349cc7` (tree
`cfd3ef51263e782c4efbd675d2f01afa9b409af4`) with **50 of 50 steps passing, FAILS=0**, including the
final check that the head, the tree and the working tree were unchanged during the run. The raw output
is retained under `benches/gate-99bef01/`. The gate covers the corrected diagnostic (including the
blank-line PGN separator) and the corrected Python suites: the weakness-diagnostic suite is 31 checks
and the benchmark-request resolver suite is 33.
