# Changelog

All notable changes are documented here. SemVer 2.0.0. Versions before the V1 release gate are `0.x`.

## [0.1.0] — pre-V1 release candidate (2026-11-19, not yet tagged)

**Pre-V1. Not v1.0.0. The V1 rating gate is not met and no absolute rating is claimed.**
Product name: FlawLessChess. UCI engine name: Flawless. Cargo package: `flawless`.

- **Fixed: `go movetime N` returned after only 39–100% of N (measured on this branch's pre-fix search code).** Iterative deepening stopped on a
  growth prediction that was meant only for clock budgets. A fixed-time search now runs until the
  requested time (measured 100–101% of N at 300, 1000 and 3000 ms). Clock-based searches are unchanged.
  Regression tests: `tests/movetime_smoke.rs` (real process, interactive waits; fails on the old rule).
- **Fixed: `ponderhit` answered immediately after `go ponder movetime N` or a clock-free `go ponder`.**
  `last_clocks` was recorded on every `go` (zeros when no clock was sent), so `ponderhit` recalculated
  a ~20 ms budget. A movetime ponder now keeps its deadline; a bare `go ponder` waits for `stop`.
  Regression tests: `ponder_movetime_ponderhit_keeps_the_movetime_deadline`, `bare_go_ponder_keeps_searching_until_stop`.
- **Fixed: `go ponder nodes N` ignored its node cap after `ponderhit`.** The ponderhit fallback left
  `infinite` set, so the cap was never checked. Regression test: `ponder_node_cap_is_enforced_after_ponderhit`.
- **Fixed: `go searchmoves` naming only illegal moves returned `bestmove 0000`** in a position with legal moves.
  The search now keeps all legal root moves in that case. Regression test: `searchmoves_with_no_legal_move_still_searches_the_position`.
- **Added: en passant forced-root test** (`t_en_passant_capture` in `scripts/uci_protocol_probe.py`) and a Linux resource
  probe step in CI. Full-game en passant is still NOT VERIFIED (no played game in the set contains one).
- **Fixed: no-argument launch starts UCI mode** (see the next section).
- **Added:** `tests/movetime_smoke.rs` (8 real-process timing and lifecycle tests); CI steps for
  `scripts/uci_protocol_probe.py`, `scripts/uci_malformed_probe.py` and `scripts/selfplay_games.py`
  (python-chess referee, full games).
- **Added:** the Windows artifact manifest records the product name, package version and the
  `--version` output of the exact exe; the artifact job refuses an exe whose version differs from
  `Cargo.toml`.
- **Added:** `docs/WINDOWS_GUI_TEST.md` (Arena / Cute Chess test checklist) and
  `docs/audit/2026-11-19-v0.1.0-release-candidate.md` (gate table).
- **Version:** `0.1.0-dev.1` → `0.1.0`. `flawless --version` prints `Flawless 0.1.0`.
- **Not claimed:** GUI playability (not yet tested by the project), Windows artifact integrity (not yet
  inspected by hand), independent review (pending), V1 status (not met).

## [Unreleased] — UCI no-argument startup compatibility + Windows x64 artifact (2026-11-19)

- **Fixed: launching `flawless` with no command-line arguments now starts UCI mode** (stdin/stdout).
  Previously it printed usage to stderr and exited with code 2, so conventional UCI GUIs that start
  a custom engine as `Process.start(path, [])` and then send `uci` failed with
  `Engine "…exe" exited while searching (exit code 2)` (reproduced from a user diagnostic bundle).
  `flawless uci` behaves exactly as before; the handshake bytes are identical in both modes.
- **CLI**: `-h` / `--help` are now explicit (stdout, exit 0) and list the subcommands. Unknown
  commands still exit 2 with the message on stderr, now with a pointer to `--help`. `perft`,
  `divide`, `bench`, `eval`, `bench_eval`, `moves`, `hash` and `version` / `--version` are unchanged.
- **Tests**: `tests/uci_smoke.rs` now runs the real executable with zero arguments through the
  full lifecycle (uci → uciok, isready → readyok, position startpos, go depth 2 → legal bestmove,
  quit → exit 0), checks no unsolicited stdout and no usage banner, checks no-arg/explicit-`uci`
  handshake parity, EOF exit, and CLI regressions. The new no-argument tests fail on the previous
  binary and pass on this one.
- **CI**: new job `windows-x64-artifact` (windows-latest, `x86_64-pc-windows-msvc`, Rust 1.99.0)
  builds `flawless.exe`, verifies the PE machine type is x86-64 (0x8664), smoke-tests the exact file,
  and uploads `flawless.exe`, `SHA256SUMS.txt` and `BUILD-MANIFEST.txt` as the workflow artifact
  `flawless-windows-x64-<commit-sha>`. The upload is mandatory (no `continue-on-error`).
- **Engine binary identity changed** by this release (source change in `src/main.rs`). Search,
  evaluation and the bench signature (`141943aa23b3fc68`) are unchanged. Previously registered
  ENGINE-2 binary hashes in the rating documents no longer identify this build; no rating evidence
  is reused or re-authorized by this change.

## [Unreleased] — Flawless identity migration + correctness audit (2026-11-14)

- **Identity migration** (ADR-0002): engine, package, library and binary renamed to **Flawless**;
  `id name Flawless`; `id author coderunknow (Apache-2.0)` (authorship unchanged). Repository
  observed as `coderunknow/Flawless-Chess-Engine` (externally renamed; this project did not rename
  it; old URL auto-redirects). Historical benchmark evidence, PGNs and append-only logs keep the old
  identifiers by policy.
- **Audit pass 1 (correctness)** — each defect reproduced by a failing→passing test:
  (1) checkmate now outranks the fifty-move and repetition draw rules in search (FIDE 9.6.2);
  (2) quiescence: terminal (mate/stalemate) check moved before stand-pat cutoffs and delta pruning;
  (3) main search: no-legal-moves terminal check moved before null-move/futility/RFP, and claimable
  draw rules require !in_check — mate can no longer be pruned or mis-scored as a draw;
  (4) `go searchmoves` was silently ignored by the MultiPV=1 PVS path — root restriction now
  enforced at ply 0 for both MultiPV paths; empty `searchmoves` falls back to all legal moves;
  (5) panic-fallback turns are now detectable by the match runner (`engine_error` / `engine_error_turns`
  in JSONL), excluded from stats by default, and the engine emits a GUI-visible stdout marker;
  (6) bench signature `d790483532d87af0` → `3086f65159758c9d` (2,317,474 nodes) — expected consequence.
- **Audit pass 2**: `clock_limits` `u64::clamp` min>max panic at `t<30ms` fixed; UCI bestmove smoke
  (depth 2) and MSRV (Rust 1.80) CI jobs added; remaining `|| true` masks removed from CI.
- **Tests**: 24 integration + 4 unit tests, incl. seeded deterministic UCI fuzz (`tests/uci_smoke.rs`)
  replacing the non-reproducible one-off fuzz claim.
- **Reviews**: CodeRabbit manually triggered (incremental; see PR #1) — review in progress/recorded
  by SHA; Codex documented retry attempted — usage-limited; Copilot quota (lower-effort retry needs
  web UI, API cannot request); Qodo/Kilo billing-blocked (not code findings).
- Absolute Elo remains **UNKNOWN**; the ≥2,000 Elo release gate is NOT measured and NOT met;
  no calibrated pool reachable from this sandbox. v1.0.0 NOT authorized.

## [Unreleased] — Phase 3 (evaluation) + Phase 4 (search) + UCI (2026-11-14)

- Tapered classical evaluation (`src/eval.rs`): material + PST (MG/EG), mobility baselines,
  bishop pair, king-zone pressure (MG only), tempo bonus. `bench_eval` reports ~100–500 ns/eval.
- Zobrist transposition table (`src/tt.rs`): 8-byte entries, power-of-two sizing, generation aging,
  mate-score ply-relative adjustment, TT-move extraction for PV recovery.
- Alpha-beta search (`src/search.rs`): iterative deepening + aspiration windows + PVS + quiescence
  (delta-pruning, MVV-LVA ordering), null-move pruning (non-PV, non-check, non-pawn material),
  futility pruning (depth ≤ 2, non-PV), LMR (log-based table, re-search on fail-high), killer +
  history heuristics, MultiPV full-window root iterations, TT-based PV extraction, seldepth tracking.
- UCI layer (`src/uci.rs`): full V1 command set — `position` (startpos/fen/bare fen + moves),
  `go` (depth/nodes/movetime/infinite/wtime/btime/winc/binc/movestogo/searchmoves/ponder), `stop`,
  `ponderhit`, `setoption` (Hash, MultiPV honest, Threads capped at 1), `ucinewgame`, `debug`.
  Search runs on a worker thread; `bestmove` is printed by the worker as soon as search ends
  (fixed: previously `bestmove` was only emitted on the next stdin command / EOF).
- `stop_and_join`: aborts search via shared AtomicBool, joins worker, hands the TT back to the
  main thread exactly once per `go`.
- Abort safety: root move scores collected after an abort are discarded (they are garbage), preventing
  corrupt PV/TT handoff after `stop` / `quit` / time abort.
- `format_score`: mate scores only reported when genuinely mate-bounded (|score| ≥ MATE_SCORE−100),
  clamped rather than overflowing.
- Score 13/12 cp found at depth 6 from startpos (b1c3); ~900k nps in-sandbox (2 vCPU).
- No claim of playing strength yet; perft/diftest gates unchanged (14/14 tests pass).
- UCI worker now catches search-thread panics and always emits a bestmove (GUI never hangs);
  LMR table sized to worst case ([MAX_PLY+1][256]) — fixes move-30 search-thread panic on
  high-material/mate positions.
- Match harness: `scripts/match.py` (UCI game runner: paired openings, color reversal,
  adjudication, PGN+JSONL evidence) + `scripts/stats.py` (logistic Elo diff, opening-clustered
  95% bootstrap CI) + `benches/openings-20.txt` (20 openings, both colors).
- GitHub Actions CI (`.github/workflows/ci.yml`): Ubuntu + Windows, fmt, clippy -D warnings,
  release tests, release build, UCI handshake, perft d3 sanity — green on PR #1.
- Strength probes vs pinned Stockfish 19 WASM (Skill 0/5/10, movetime 100 ms, 20 paired openings ×2 colors):
  40/40 checkmate wins vs Skill 0; 11/13/16 vs Skill 5 (Elo diff −44, CI [−127,+35]); 1/7/32 vs Skill 10
  (Elo diff −359, CI [−512,−269]). Internal in-sandbox bracket; not a CCRL/CEGT rating.
- UCI fuzz: 6 trials × 25 commands — 0 crashes, 0 hangs.
- Search experiment (kept, directional): reverse futility pruning (depth ≤ 3, non-PV,
  mate-bound-safe) + check extensions. A/B vs previous build: score 0.613 (Elo +80, CI overlapping 0);
  vs pinned SF Skill 5 score improved 0.438 → 0.525 (CI overlapping). Not conclusive at 40 games.
- `bench`: fixed-depth-10 search benchmark over 12 fixed positions; deterministic FNV-1a
  `bench signature` (current: `3086f65159758c9d`, 2,317,474 nodes; see DESIGN_LOG 2026-11-14 audit entry); node count is the regression signal.
- Not committed tags; v1.0.0 NOT authorized.

## [0.1.0-dev.1] — 2026-11-14

- Project bootstrap: repository recon, environment record, architecture RFC, ADRs, docs skeleton.
- No engine code yet. Perft gates pending. Not released.
