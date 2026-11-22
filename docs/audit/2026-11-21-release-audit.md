# Release audit — 2026-11-21

Scope: full pre-release audit of Flawless 0.1.0 at head `e2a58f0` (F-44 source, ledger-only head),
with one defect fixed (F-45). This document records what was checked, how, and the results. It is
evidence for the audit only. It is **not** a release: no tag, GitHub Release, or publication has been
made, and the release conditions below are still open.

## Verdict

- Correctness, stability and protocol behaviour pass every check listed below.
- One defect was found and fixed (F-45, `Hash` size reported silently wrong). See `FAILURE_LEDGER.md`.
- The project is **not yet releasable**. Open conditions (unchanged by this audit): G2 (CodeRabbit
  review passes on the final head — the latest review on `e2a58f0` was completed with no new findings,
  but the owner has not signed it off), G3 (Windows artifact not verified: downloads from the hosted
  runs fail from the sandbox), CLOCK-1 (not frozen; no frozen hash in `PREREGISTRATION.md`),
  F-41 LMR quiet-mate options A/B/C (owner decision, OPEN), and the `searchmoves` widening (owner decision).

## Checks and results

| Area | Check | Result |
|---|---|---|
| Format | `cargo fmt --check` | PASS |
| Lints | `cargo clippy --all-targets -- -D warnings` | PASS |
| Docs | `cargo doc --no-deps` | 3 warnings → 0 (two doc-comment markup fixes, no behaviour change) |
| Unit and integration tests | `cargo test --release`, `cargo test` (debug) | PASS on the pre-fix tree; re-run in the final gate |
| Perft | startpos, Kiwipete, CPW positions (in the test suite) | PASS |
| Protocol | `scripts/uci_protocol_probe.py` | 12/12 |
| Malformed input | `scripts/uci_malformed_probe.py` | 37/37 OK |
| UCI grammar | `scripts/fuzz_uci_grammar.py 7 60` | 0 failures |
| Interleaving | `scripts/fuzz_interleave.py <exe> 30 40 9` | 0 failures |
| FEN extremes | `scripts/fuzz_fen_extremes.py 5 150` | 0 failures |
| Legal-move differential | `scripts/fuzz_legal_differential.py 3 20` | 4210/4210 agree; the 3 rejected FENs are unreachable positions (more than 16 pieces, or more promoted pieces than missing pawns), which the engine refuses correctly |
| Random perft differential | `scripts/perft_random_differential.py 4 10` | 171 positions, 513 checks, 0 failures |
| Full games (playability) | `scripts/selfplay_games.py <exe> <out> --tc 1000+20` (6 openings) | 5 checkmates, 1 stalemate (as expected), 0 flags, 0 timeouts, 0 illegal moves |
| Python tests | `scripts/test_*.py` (9 files) | all PASS |
| Bench | `flawless bench` | signature `849a85bf7e8e1eba` (pinned, unchanged); 4135406 nodes |
| Responsiveness | `isready` during `go infinite` | `readyok` in 0.2 ms; `stop` yields one `bestmove` |
| Infinite search | `go infinite` in a dead-draw K-vs-K position (search reaches the depth cap in ~1 ms) | `bestmove` is held until `stop`, as UCI requires |
| Large hash | `setoption Hash 1024`, `ucinewgame`, `go movetime 2000` | resize 0.06 s; `ucinewgame` 0.56 s; movetime honoured (2.002 s) |
| Hash reporting | `setoption Hash 100` | **defect F-45**: silently 64 MiB before the fix; now reported (fixed) |
| FEN forms | 4-field FEN without move counters, en-passant field | accepted; search returns legal moves |
| CLI | `--help`, `--version`, `perft`, `divide`, `eval`, `moves`, unknown command | match README; exit codes as documented |
| Documentation links | every relative link in `*.md`, `docs/**/*.md` | no broken links |
| Licence and dependencies | `LICENSE` (Apache-2.0), `[dependencies]` empty, `Cargo.lock` single package | PASS |
| No Stockfish code | grep for Stockfish identifiers in `src/` | none |
| Unsafe code | `grep unsafe src/` | one `unsafe` block, in `tt::zeroed_entries` (documented) |
| Secrets | pattern scan of tracked files | none |
| Repository size | largest tracked files | largest 384 KiB (evidence JSONL); no binaries |
| MSRV | hosted job `msrv (rust 1.80)` on `e2a58f0` | success |
| CI | hosted checks on `e2a58f0` | all success except `Kilo Code Review` (billing `action_required`, not bypassed) |

## Defect fixed in this audit

**F-45 — `Hash` rounding was silent.** The transposition table has a power-of-two entry count, so a
requested size is rounded down (`Hash 100` → 64 MiB). The engine did not say so, and it stored the
requested value as the current size. Fix: `tt::effective_table_mib` is the single definition of the
rule; the engine stores and reports the size it actually allocated; and when no table exists, a
requested size is now allocated instead of silently keeping the old one. Tests:
`tt::size_tests_f40::effective_table_mib_matches_the_allocation` and
`protocol_regressions::hash_rounding_is_reported_on_stdout`. The new protocol test fails on the previous
commit (its `Hash 100` reply was only `readyok`) and passes after the fix.

## Behaviour noted, not changed

- A `setoption` sent during a search ends that search (one `bestmove` is printed) before the option is
  applied. This is documented in `README.md`. It keeps the table owned by one thread and still gives
  exactly one `bestmove` per `go`.
- `flawless perft` prints `magic sliders active: true` on stderr. This is a diagnostic only.

## Reproduce

```
source /home/user/.toolchain/env
cargo fmt --check && cargo clippy --all-targets -- -D warnings
cargo test --release && cargo test
cargo build --release
./target/release/flawless bench                       # signature 849a85bf7e8e1eba
/home/user/.venv/bin/python3 scripts/uci_protocol_probe.py target/release/flawless
/home/user/.venv/bin/python3 scripts/uci_malformed_probe.py target/release/flawless
/home/user/.venv/bin/python3 scripts/selfplay_games.py target/release/flawless /tmp/sp --tc 1000+20
```

Raw outputs of the sandbox run were kept in scratch space (`/tmp/audit4/`), which is not part of the
repository; the results above are the record. Scratch files may not survive a sandbox reset.

## Correction (2026-11-22)

- The `searchmoves` item above ("the `searchmoves` widening (owner decision)") is superseded. The owner direction of 2026-11-22 makes `go searchmoves` strict: a named list with no legal move answers `bestmove 0000` and announces it on stdout, with no widening. See DESIGN_LOG.md (2026-11-22) and FAILURE_LEDGER.md F-46. The F-09 entry stays as history.
- The probe-stability results above were produced before F-48 (2026-11-22). Several probes passed silently or waited without limit against broken engines; those defects are fixed and listed in FAILURE_LEDGER.md F-48. The real-engine results for the changed probes are recorded there.
- Release state is unchanged: G2 (CodeRabbit on the final head), G3 (Windows artifact) and CLOCK-1 are still blockers. This correction does not claim release readiness.
