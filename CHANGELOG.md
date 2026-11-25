# Changelog

All notable changes are documented here. SemVer 2.0.0. Versions before the V1 release gate are `0.x`.

## [Unreleased] — review disposition and evidence provenance (2026-11-25)

- **Fixed (CI): the benchmark workflow no longer interpolates dispatch inputs into shell source.** The
  dispatch profile and seed are passed through the step environment, validated there, and written to
  `GITHUB_OUTPUT` with `printf` and a quoted variable, so an input can never be executed as a command.
- **Fixed (CI): the quick regression screen now runs on every pull request of this repository**
  instead of PR #6 only. Pull requests from forks stay excluded: the job checks out and runs the
  pull request's own code while holding a `pull-requests: write` token.
- **Fixed (CI): the publishing step now receives `SEED_BASE`**, so the published title names the real
  seed range (`seeds 20261124..20261126`) instead of an empty base.
- **Fixed (CI): the rustfmt annotation encodes the diff correctly.** `tr '\n' '%0A'` replaced a newline
  with a bare `%` (the second argument of `tr` is a character *set*), which flattened a multiline diff.
  The percent sign, carriage return and newline are now encoded as `%25`, `%0D` and `%0A`.
- **Added (evidence): the effective `FLAWLESS_ABLATE` value is recorded in the manifests** written before
  the first game starts — in `scripts/match.py` (the batch manifest) and in `scripts/relative_benchmark.py`
  (the run manifest) — including the unset case. The aggregation step refuses to combine replicates whose
  masks differ, so a full run and an ablated run can never be pooled into one summary by accident.
  `docs/ABLATIONS.md` documents the field and the rule.
- **Fixed (benchmark harness): a game without the candidate is left out of the scorable set** as well, so
  the confidence interval is computed over exactly the games the point estimate is computed over.
- **Fixed (benchmark harness): the saved opening order is verified against its digest** before aggregation,
  and a damaged file is reported as a validation error instead of crashing the aggregator.
- **Fixed (diagnostics): `scripts/diagnose_weaknesses.py` reads the piece-square tables from the engine
  source** instead of keeping a copy that had drifted (the copied bishop table had 63 entries and would
  have raised `IndexError` on the last square). The evaluation sign now follows the side to move, a closed
  stdout is handled, the engine is reaped after a shutdown timeout, the material loss is measured through
  the opponent's reply with a reference material that is never stale, the returned UCI string is printed
  directly, and the losing games are written as PGN.
- **Fixed (diagnostics): `scripts/tactic_test.py` accepts the free rook capture** in the `win_rook` fixture
  (an exchange of equal value that the opponent cannot recapture is a win), handles EOF during UCI
  initialisation, and tolerates a closed stdin during cleanup.
- **Added (tests): the outpost advancing-pawn cases** — the b7 pawn, its colour mirror and the undefended
  variant — as regressions. The reported advancing-pawn defect in `src/eval.rs` was reproduced and is a
  **false positive**: the cited position scores outpost 0 because the piece is not pawn-defended, and the
  defended variant with the same b7 pawn also scores 0. The algorithm is unchanged.
- **Added (tests): four new benchmark-harness checks** covering the candidate exclusion, the opening-order
  digest and the ablation-mask consistency rule (benchmark suite 37/37), a check that a perfect score is a
  positive relative signal, and a resolver suite (33 checks) that pins both the push-request and the
  manual-dispatch branches of the benchmark request resolver.

- **Measured (relative benchmark, screening only):** the revision-2 extended run on the refined head
  (hosted run `45529006866`, candidate `5be7d7b`, 600 real UCI games, 100 opening clusters) finished
  **227 W / 156 D / 217 L**, score **305.0/600 = 50.8%**, relative Elo **-19.7 to +31.4** (95% CI),
  classification **INCONCLUSIVE**. The point estimate moved from 49.8% to 50.8% between the two
  revisions and the interval still straddles 50%: **no measurable strength difference against the
  pinned baseline**. Screening evidence only — not an absolute rating and not a strength claim.
- **Measured (relative benchmark, screening only):** the revision-3 extended run on the exact final head
  (hosted run `45546563480`, candidate `13f8162`, 600 real UCI games, 100 opening clusters, independent
  seed) finished **229 W / 163 D / 208 L**, score **310.5/600 = 51.7%**, relative Elo **-11.0 to +35.4**
  (95% CI), classification **INCONCLUSIVE**. The three extended runs now read 49.8%, 50.8% and 51.7%,
  and **every interval straddles 50%**: the point estimates drift while the interval keeps covering the
  baseline, which is what a small underlying effect looks like. **No measurable strength difference
  against the pinned baseline.** Screening evidence only — not an absolute rating and not a strength
  claim. The published title now reads `seeds 20261201..20261203`; the earlier run read `seeds ..2`
  because the publishing step did not receive the seed base, which the review found and this branch
  fixed.
- **Measured (ablation matrix, screening only):** the four variants of the ablation study (hosted run
  `45529550258`, candidate `d306cbc`, `screen` profile, seed `20261130`, 200 games each) came out at
  `full` 53.5%, `no-space` 53.8%, `no-counter-move` 47.8%, `no-new-terms` 46.8%, and **every variant is
  INCONCLUSIVE with completely overlapping intervals**. The study therefore **does not measure the
  contribution of any of the three terms** at this sample size. The switch itself is verified
  deterministically; the magnitude of each term's contribution is not measured. A sharper design
  would need a paired difference over the shared openings and a reproducible time control.

## [Unreleased] — outpost correction, tempo semantics, ablation switch, paired benchmark (2026-11-24)

- **Fixed (eval, EVAL-2): the outpost term.** White outposts are now on ranks 5-6 and Black outposts on
  ranks 3-4 (files b-g). The previous zone (ranks 5-8 / 1-4) included the opponent's back rank and the
  rank in front of it, where no enemy pawn can ever stand, so "cannot be attacked by an enemy pawn" was
  vacuously true and pieces deep in enemy territory scored as outposts. The term now also applies the two
  remaining classical conditions: the square must be **defended by one of our own pawns**, and no enemy
  pawn may be able to **step forward** and attack it (the push is blocked only by one of our own pieces).
  Values are unchanged (knight +30 mg / +15 eg, bishop +15 mg / +8 eg). The bench signature stays at
  `141943aa23b3fc68`, unchanged from the pinned baseline: none of the twelve bench positions contains a
  pawn-defended outpost square.
- **Changed (eval): the tempo bonus is computed explicitly** as `relative = +/- tapered; total = relative +
  TEMPO`, instead of one expression that relied on the binding of `+` to an `if` expression. The binding was
  verified against the rustc parser (the tempo was applied to both colours) and is now pinned by a
  regression test for both colours and for the colour mirror. `EvalBreakdown` additionally exposes `mg`,
  `eg` and `phase`.
- **Added (diagnostics): the `FLAWLESS_ABLATE` ablation switch** disables the `space` and `outpost`
  evaluation terms and the `counter_move` move ordering heuristic for one process. Off by default, read
  once, applied as a bit mask; the pinned baseline predates it and ignores the variable. See
  `docs/ABLATIONS.md`.
- **Added (tests): outpost boundary and symmetry cases** (opponent back rank, the rank in front of it, edge
  file, own half, pawn-challenged square, two outposts at once) and a tempo regression test.
- **Changed (CI): the relative strength benchmark** runs the quick paired profile on every pull request
  and the three-replicate extended tournament on demand; results are published to the job summary and
  to a pull request comment. The rustfmt gate reports its diff through annotations, because the Actions log
  host is not reachable from the development sandbox.
- **Changed (CI): the anchor-verify bench signature** follows the evaluation. The refined outpost term
  leaves the signature at `141943aa23b3fc68`, unchanged from the pinned baseline, so the expectation is
  unchanged; the intermediate, looser definition moved it to `ce6a84301216fadd`.

- **Measured (relative benchmark, screening only):** the three-replicate extended profile (600 real UCI
  games, candidate against the pinned baseline `6ab5b33`, 100 opening clusters, opening-clustered bootstrap)
  finished **217 W / 164 D / 219 L**, score **49.8%**, relative Elo **-23.2 to +21.5** (95% CI),
  classification **INCONCLUSIVE**. No strength difference against the pinned baseline is measurable. The
  Fourteen hosted quick runs of the same 20-opening profile, on heads with a **byte-identical release
  binary** (the last change to `src/` on the branch is the outpost refinement `98e5cd9`), ranged from
  **46.2% to 65.0%**, and the same unchanged engine produced the label
  `POSITIVE_RELATIVE_SIGNAL_SCREENING_ONLY` in one run and `INCONCLUSIVE` in the other thirteen. A fixed
  100 ms movetime makes the reached depth depend on the machine speed and the timing jitter, so the
  played games are not reproducible across runs even with the same opening seed: the seeded shuffle
  fixes the opening order, not the games. The 40-game profile therefore carries roughly ±30 Elo of
  pure sampling noise and its classification label must not be read as a strength signal; the 600-game
  profile is the meaningful one.

## [Unreleased] — engine improvements (2026-11-24)

- **Changed (search):** removed the predictive-overrun early stop that halted clock-based searches
  well before the soft budget. At 10 s the engine previously stopped at 116 ms of a 234 ms soft
  budget (depth 9); it now runs to depth 10 at ~253 ms. Hard budget still caps worst-case
  overspend; fixed-depth/movetime searches unaffected.
- **Changed (search, HIST-1 from PR #2 audit):** added counter move heuristic. When a quiet move
  causes a fail-high cutoff in reply to the opponent's previous move, store it as a counter move
  ordered just above killers (92,000) and below good captures. Counter table cleared each root
  search; not used in null-move search or quiescence.
- **Changed (eval, EVAL-2 from PR #2 audit):** added space evaluation, rewarding control of
  important squares weighted by centrality. Colour-symmetric via square mirroring; tapered full
  weight in middlegame / half in endgame. Added `space` field to `EvalBreakdown` and CLI `eval`
  output.
- **Docs:** Reconciled STATUS.md, CHANGELOG.md, AGENTS_LOG.md to the actual GitHub state as of
  `main` = `6ab5b33` (PR #5 merge). PRs #1/#3/#4/#5 merged; PR #1 not open or draft; PR #2 open,
  draft, conflicting and NOT merged/cherry-picked/touched. Recorded environment constraint
  (no Rust toolchain obtainable from static.rust-lang.org in this sandbox; toolchain recovered
  from npm `@toolchain-bin/*` 1.99.0 pins).

## [Unreleased] — documentation reconciliation & next-iteration plan (2026-11-24, superseded)

Kept as historical record; the engine changes above supersede the plan-only entry.

## [Unreleased] — independent audit remediation (2026-11-20)

- **Fixed (F-52, from external review of `bf026f8`): three engine defects and one probe gap.** `go ponder nodes N` now counts its cap from `ponderhit` (it was spent while pondering, so the search returned at once). `go movestogo` beyond `u64::MAX` saturates instead of falling back to 40 moves. `position fen` now rejects en-passant targets whose pawn came from an occupied square or whose halfmove clock is not 0 (`f6 0 1` with a bishop on `f7` was accepted). `uci_malformed_probe.py` no longer accepts `bestmove (none)` for a fully restricted search. Tests: `protocol_regressions` ponder cap, `uci` movestogo, `correctness` FEN (3).
- **Fixed (LOW, F-51): a refused search thread held `go ponder` until `stop`, even with a clock, movetime, depth or node limit.** `ponderhit` now releases that answer, because a limited ponder has no search left to wait for. A bare `go ponder` is still held until `stop`. Regression test `refused_thread_answers_go_ponder_with_clock_at_ponderhit`.
- **Fixed (MEDIUM, F-49): time checks ran only every 1024 nodes.** At small budgets (a 300 ms sudden-death clock, where the planned budget is the 1 ms floor), one move could overrun by up to ~5 ms, and a long game could run out of time. The clock is now checked every 128 nodes; the measured worst-case overrun at a 1 ms budget fell from about 5 ms to about 2.5 ms. The time-budget policy and the bench signature are unchanged.

- **Changed (owner decision 2026-11-22, F-46): `go searchmoves` is strict.** When no named move is legal, the engine
  answers `bestmove 0000` and prints `info string searchmoves names no legal move in this position; no move searched`
  on stdout (it used to search all legal moves). Malformed tokens are reported on stdout, and the list runs to the next
  `go` keyword. This supersedes the F-09 widening. Tests: `protocol_regressions` searchmoves (4), search unit tests (2).
- **Fixed (LOW, F-47): `table_entries` multiplied before clamping.** Library callers with a huge size overflowed; the
  size is now clamped to 1..=1024 MiB first. Test: `tt::size_tests_f40::table_entries_clamp_before_multiplying`.
- **Fixed (test tooling, F-48): probes could pass silently or wait without limit.** The mate-proof probe now classifies
  every position (unverified claims exit 3, not 0); the FEN fuzzer checks enough legal positions; the UCI probes stop at
  the first handshake stall; new `scripts/failure_mode_probe.py` runs every engine probe against broken engines
  (51/51 pairs as expected). Not an engine change.
- **Fixed (LOW, F-45): `setoption name Hash` rounded the size down without saying so.** `Hash 100` allocated 64 MiB
  silently. The engine now stores and reports the size it allocates (`info string option Hash 100 MiB allocates 64 MiB …`).
  The size rule has one definition (`tt::effective_table_mib`). Tests: `tt::size_tests_f40::effective_table_mib_matches_the_allocation`,
  `protocol_regressions::hash_rounding_is_reported_on_stdout`.
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
