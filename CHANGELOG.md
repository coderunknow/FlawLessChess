# Changelog

All notable changes are documented here. SemVer 2.0.0. Versions before the V1 release gate are `0.x`.

## [Unreleased] — independent audit remediation (2026-11-20)

- **Fixed (MEDIUM, F-12): `flawless moves` and `flawless hash` stopped at the first non-UTF-8 stdin line.** Later
  FENs got no reply. Each bad or overlong line now gets one `error` reply and the batch continues. Tests:
  `tests/cli_batch.rs` (3 tests).
- **Fixed (LOW, F-13): a failed stderr write panicked the engine (exit 101).** Diagnostics now use `err_line!`, which
  ignores write errors, so an oversized input line no longer ends the session. Test:
  `protocol_regressions::stderr_write_failure_does_not_stop_the_session_on_an_oversized_line` (fails on the previous code).
- **Fixed (LOW, F-14): a root position with insufficient material returned an empty PV.** Single-PV search now
  searches the root (interior nodes keep the draw rule), so `bestmove` comes from the search. Test:
  `protocol_regressions::insufficient_material_root_is_searched_and_yields_a_pv` (fails on the previous code).
  Bench node total: 2,311,437 (signature unchanged `849a85bf7e8e1eba`).
- **Fixed (MEDIUM, F-15): a negative `wtime`/`btime`/`movetime` made the search unbounded.** The value failed to parse,
  so `go` had no time limit and never answered without `stop`. A negative time is now 0 (answer at once); values above
  `u64::MAX` saturate. Test: `protocol_regressions::negative_time_values_answer_at_once` (fails on the previous code).
  Probe: `scripts/uci_extreme_args_probe.py`.
- **Fixed (MEDIUM, F-16): a refused hash-table allocation aborted the engine.** `setoption name Hash value 1024` under
  a low memory limit killed the process (SIGABRT). The refusal is now reported on stdout and the previous table is kept;
  start-up halves the default table until the allocator accepts it. Test:
  `protocol_regressions::hash_allocation_refusal_does_not_abort_the_engine` (Linux; fails on the previous code).
- **Fixed (MEDIUM, F-17): a refused search thread panicked `go`.** The engine now answers with the first legal move and a
  stdout notice instead of exiting 101. Same test.
- **Hardened:** stdout-ordering locks recover from poisoning instead of panicking. Piece-bitboard invariant test over
  random legal games: `correctness::piece_bitboards_stay_in_sync_over_random_games`.
- **CI:** the test workflow declares `permissions: contents: read`; `dtolnay/rust-toolchain` is pinned to a commit SHA
  (was `@master`) in `ci.yml` and `rating-run.yml`.

- **Fixed (LOW, F-10): closed stdout panicked the engine.** When the reader closed the pipe, the next
  `println!` panicked with `Broken pipe` (exit 101). All protocol and CLI output now goes through
  `out_line!`, which exits with status 0. Test: `protocol_regressions::closed_stdout_ends_the_process_quietly`
  (fails on the previous code with the panic).
- **Fixed (MEDIUM, S-14): search scores were not colour-symmetric.** Equal-score moves were ordered by raw square
  numbers, so a position and its mirror could search differently at depth 4 (2 of 40 positions in the first probe,
  6 of 120 in a later probe). A colour-relative tie-break removes this with no LMR change. Tests:
  `correctness::search_scores_are_colour_symmetric_on_recorded_pairs` (11 pairs, `tests/data/search_symmetry_pairs.tsv`)
  and the existing 303-pair static-evaluation check. The bench signature changes to `849a85bf7e8e1eba`.
- **Fixed (LOW, S-08): `go nodes N` spent up to 1,023 extra nodes.** The cap is now checked on every node in
  search and quiescence, so the search spends exactly N nodes. Tests: `correctness::node_cap_is_spent_exactly`,
  `protocol_regressions::go_nodes_limit_is_spent_exactly_and_reported`.
- **Fixed (LOW, CodeRabbit on 7d5b489): an oversized input line could leave a stale position in use.** A dropped line may be a
  `position` command, so the position is now marked invalid: `go` answers `bestmove 0000` until a valid `position` arrives.
  Test: `protocol_regressions::oversized_position_line_does_not_leave_the_old_position_in_use`.
- **Test hardening (CodeRabbit on 7d5b489):** the closed-stdout test waits with bounded reads and kills the child on failure; the ponder
  test no longer asserts an exact count (the search is uncapped until `ponderhit`; the exact cap is tested elsewhere).
- **Tests:** `protocol_regressions::ponder_node_cap_is_enforced_after_ponderhit` now asserts the exact cap (20,000)
  after the first `info depth`. `protocol_regressions::mixed_searchmoves_restricts_to_the_legal_named_move` covers
  mixed legal and illegal `searchmoves`.

- **Fixed (HIGH): a legal-looking FEN could crash the engine in release builds.** `position fen` accepted
  up to 27 white pieces (`KQQQQQBk/Q5RB/Q6Q/Q6Q/Q6Q/Q6Q/Q1QQ3Q/QR3QQQ w - - 0 1` has 22 queens), overflowing the
  fixed move list (`MoveList`). FEN parsing now rejects material no game can reach (more than 16 pieces,
  more than 8 pawns, or promoted pieces exceeding the missing pawns). `MoveList` capacity is 512 with a
  documented bound (335 pseudo-legal moves) and a hard check on push. Tests: `correctness` material tests,
  `protocol_regressions::impossible_material_fen_is_rejected_without_crashing`.
- **Fixed (HIGH): a non-UTF-8 input line ended the UCI session.** Stdin is now read as bytes with a 64 KiB
  line bound; invalid UTF-8 is decoded lossily, and oversized lines are dropped with an `info string`.
  Tests: `protocol_regressions::non_utf8_input_line_does_not_end_the_session`,
  `oversized_input_line_is_dropped_and_session_continues`, and the `uci` line-reader unit tests.
- **Fixed (HIGH): `go wtime N` (or `btime` alone) had no time limit.** A single side's clock now bounds the
  search. Test: `protocol_regressions::single_side_clock_bounds_the_search`.
- **Changed: the advertised Hash maximum is 1024 MiB (was 4096).** The transposition table is capped at
  1 GiB, so 4096 was accepted and silently capped. Values outside 1..=1024 are rejected with an `info string`
  on stdout. Test: `protocol_regressions::hash_limit_is_advertised_and_enforced`.
- **Fixed: Threads, Hash and MultiPV rejections are reported on stdout** (they were on stderr, which GUIs do
  not show). The build is single-threaded: `Threads` other than 1 is reported and ignored. Test:
  `protocol_regressions::threads_other_than_one_is_reported_on_stdout`.
- **Fixed (LOW): clock arithmetic saturates** (`clock_limits` could wrap on enormous clocks). Test:
  `uci::tests::clock_limits_saturate_instead_of_wrapping`.
- **Fixed (LOW): the search thread has a 16 MiB stack** (was the 2 MiB default).
- **Added tests:** CPW perft references (startpos d1–d4, Kiwipete d1–d3, positions 3–6), castling-rights
  tests (stale rights generate no castling), the ponder node cap after `ponderhit`
  (`protocol_regressions::ponder_node_cap_is_enforced_after_ponderhit`), and the illegal-only `searchmoves`
  process test.
- **CI:** `persist-credentials: false` on the checkouts of the `test` and `msrv` jobs.
- **Fixed (MEDIUM): FENs with two checkers on one line through the king, or with three checkers, were accepted.**
  Found by differential fuzzing against python-chess. Such positions cannot occur in a legal game. Tests:
  `correctness::fen_rejects_two_checkers_on_one_line_through_the_king`, `fen_rejects_more_than_two_checkers`,
  and `fen_accepts_a_legal_double_check_from_knight_and_queen`.
- **Added: verification tools** `scripts/fuzz_legal_differential.py` (random legal games vs python-chess legal move
  sets), `scripts/fuzz_uci_grammar.py` (random UCI sessions), `scripts/fullgame_en_passant_probe.py` (full engine game
  with a forced en passant capture; in CI), `scripts/eval_symmetry_probe.py` (informational search symmetry), and the
  static-evaluation colour-symmetry test over 303 pairs (`tests/data/eval_symmetry_fens.tsv`).

## [0.1.0] — pre-V1 (2026-11-20 audit remediation; tag and Release pending the gates in FINAL_AUDIT_PROGRESS.md)

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
