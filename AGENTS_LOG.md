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
