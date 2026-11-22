# TESTING.md — correctness & reliability gates

Status legend: `PASS` (evidence below) / `FAIL` / `PENDING`.

## Move generation — perft (release build)

| Position | FEN | d1..dN | Expected | Status |
|---|---|---|---|---|
| Startpos | `rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1` | 1–6 | 20, 400, 8902, 197281, 4865609, 119060324 | ALL PASS 2026-11-14 (d3 = 8902 additionally asserted in CI every push/PR, both OSs) |
| Kiwipete | `r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1` | 1–5 | 48, 2039, 97862, 4085603, 193690690 | ALL PASS 2026-11-14 |
| CPW pos 3 | `8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1` | 1–6 | 14, 191, 2812, 43238, 674624, 11030083 | ALL PASS 2026-11-14 |
| CPW pos 4 | `r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1` | 1–6 | 6, 264, 9467, 422333, 15833292, 706045033 | ALL PASS 2026-11-14 (d6 log `benches/perft_pos4_d6.log`) |
| CPW pos 5 | `rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8` | 1–5 | 44, 1486, 62379, 2103487, 89941194 | ALL PASS 2026-11-14 |

Full raw record: `benches/perft_full_20261114.md` (27/27 exact matches; python-chess
oracle cross-check MATCH at all five positions d3 + startpos d4 via the now-committed
`scripts/perft_oracle.py`).

Reference counts: Chess Programming Wiki "Perft Results" page (public community reference values);
independently cross-verified with python-chess (`scripts/perft_oracle.py`).

## Differential testing vs python-chess (pinned 1.11.2, GPL-3.0+, test-only)

- Random legal-move sequence sampling with deterministic seeds: compare legal move sets, SAN/FEN round
  trips, castling/en-passant/promotion handling, terminal states, 50-move and repetition logic.
- See `scripts/diftest.py`. Target: ≥ 2000 positions per run, zero mismatches.
- Property tests (Rust): make/unmake round trip; incremental vs recomputed hash; Zobrist key consistency;
  mirror evaluation test.

## State & invariant tests

Castling rights through capture/castle/promotion · en passant pin legality · promotions · repetition
detection (positions array) · fifty-move rule · insufficient material (K v K, K+B v K, K+N v K,
K+B v K+B same color bishops) · stalemate · checkmate · search state restoration after `stop`.

## UCI / reliability

Covered today (all verified locally on Rust 1.99.0): `uci` handshake (`id`/`uciok`), `isready`,
`position startpos`/`fen`/`moves`, `go depth`/`movetime`/`infinite`/`wtime,btime,winc,binc,movestogo`,
`stop` mid-search, `ponderhit` (ponder→clock conversion), `ucinewgame`, `setoption Hash/Threads/MultiPV`
(unknown options ignored), `quit`. Randomized command-sequence fuzz is now a committed, deterministic
test: `tests/uci_smoke.rs` (seeded splitmix64, 6 trials × 25 commands over a ~19-token grammar, plus an
unknown-command tolerance test and a handshake/quit test) — 0 crashes, 0 hangs; runs in CI via `cargo test`.
It replaces the earlier one-off session check that was not reproducible from the repo.
Deep/black-box fuzzing (e.g. cargo-fuzz/libFuzzer): NOT performed (no network access to crates.io; zero-dependency policy).
Panic resilience: search thread wrapped in `catch_unwind`; on internal panic the engine emits a legal fallback
`bestmove` and a stdout `info string search thread panicked; emitting fallback bestmove` marker (GUI never
hangs); match runner tags such games `engine_error` and stats.py excludes them by default.
CI additionally runs a UCI handshake + perft d3 sanity on every push/PR (both OSs).

## Static quality

`cargo fmt --check` · `cargo clippy --all-targets -- -D warnings` · `cargo test` ·
`cargo build --release` (Linux + Windows in CI) · `cargo deny`-style dependency audit (zero deps ⇒ trivial) ·
license scan (zero deps + Apache-2.0 headers).

## CI

`.github/workflows/ci.yml` — ubuntu-latest & windows-latest: fmt, clippy -D warnings, release tests,
release build, UCI handshake, perft d3 sanity — green on PR #1 (runs 43549500632, 43550978076).

## Running the suites (exact commands)

The two Python suites use custom `main()` runners with `check()` counters — they contain NO
`unittest.TestCase` classes, so `python -m unittest` discovers **0 tests** (false green; see
FAILURE_LEDGER 2026-11-14). Run them as scripts (CI does exactly this):

```
python3 scripts/test_match.py            # 104 checks
python3 scripts/test_rating_estimator.py # 53 checks
/home/user/.venv/bin/python3 scripts/test_mate_proof_classify.py # 10 checks: mate-proof verdicts (F-48)
# Manual, about 15 min: every engine-driving probe against silent, exit-after and null-move fake engines.
# Each pair must fail in bounded time (protocol-only probes must pass the null-move engine). Expect 51/51.
/home/user/.venv/bin/python3 scripts/failure_mode_probe.py --bound 120
```

Rust: `cargo test --release` (lib 6 + clock_smoke 3 + correctness 21 + uci_smoke 4).

## Evidence policy

Raw outputs are stored under `benches/` and summarized in `STATUS.md` / `BENCHMARKING.md`. No test
result is claimed without a command + output line.

## Rating harness & estimator regression suites (2026-11-14)

| Suite | Scope | Status |
|---|---|---|
| `scripts/test_match.py` (104 checks) | clock-TC parsing + repeating period (`add`/`reset`) + flag; 60×17×2=2,040 schedule determinism + shard partitioning; engine-error record/immediate-replay/abort-after-2; move-cap unadjudicated (`*`) vs explicit draw policy; manifest v2 finalization (in_progress→completed/aborted); opening-suite hash; anchor-schema hardening (template rejected; TBD/null/bad-hash/ambiguous-convention/unverified-license all rejected) | PASS 2026-11-14 |
| `tests/clock_smoke.rs` (3) + `uci::tests::clock_limits_*` (2) | Flawless clock management: full `go wtime/btime/winc/binc/movestogo` commands return a legal bestmove within budget (crash-net bounds from `clock_limits`); increment + movestogo continuation; `clock_limits` invariants (soft ≤ t, hard ≥ soft, hard ≤ cap, movestogo 0 no-panic) | PASS 2026-11-14 (cargo 35/35) |
| `scripts/test_rating_estimator.py` (53 checks, incl. `verify_evidence`) | balanced-match recovery; perfect/zero boundary rejection; known anchor diffs; correlated opening difficulty (joint bootstrap covariance > 0); uncertainty conversion sd/se/ci90/ci95/ci99; GLS weights + singular fallback; shared calibration added once across batches; combined CI math; missing/invalid evidence rejection; fixed-seed reproducibility; null-control verdicts; full fail-closed gate (PASS on strong evidence; FAIL on poisoned control; FAIL on missing evidence); committed-evidence verification (`verify_evidence.py`: tampered bytes / suite-hash divergence / identity mismatch all fail closed) | PASS 2026-11-14 (53/53) |
| `scripts/aggregate_shards.py` | fail-closed §5.2 rules (missing shards, duplicate shard ids/games, engine/anchor/suite hash mismatches, TC mismatches, incomplete records, hardware divergence) | smoke-verified both directions 2026-11-14 |

Gate note: `scripts/rating_estimator.py gate` independently recomputes every reported number
from raw `games.jsonl` evidence (never trusts a hand-entered rating). It is the implementation
behind the `rating-gate` check (`.github/workflows/rating-gate.yml`) and fails closed on any
missing artifact.

## Evidence pipeline push regression suite (2026-11-15)

| Suite | Scope | Status |
|---|---|---|
| `scripts/test_evidence_push.sh` (10 checks) | evidence-commit push from DETACHED HEAD (actions/checkout ref=sha): explicit refspec `HEAD:refs/heads/$BRANCH` publishes; concurrent remote advancement → rebase-retry publishes; wrong-branch safeguard refuses non-arena destinations; static guard that both `evidence-bridge.yml` and `rating-run.yml` keep the explicit refspec and never reintroduce `git push origin "$BRANCH"` | PASS 2026-11-15 (10/10) |

| `clock_limits_engine1_no_flag_death_march` (src/uci.rs) | ENGINE-1 time-management regression: full 40-move period simulation with per-move overhead stays within the clock and preserves the reserve; hard limits can never flag; starved-period trigger (small clock, large movestogo) cannot overspend | PASS 2026-11-15 (cargo 35/35) |
## RATING-100 and exact-slot recovery — added 2026-11-17 (CI pending)

| Test / tool | Added coverage | Current result |
|---|---|---|
| `scripts/verify_opening_subsets.py` | Recomputes both deterministic 50-row selections, exact original row order, byte-level SHA-256 values, uniqueness and Batch A/B disjointness | PENDING hosted CI |
| `scripts/power_analysis.py` | 36 delta-method sensitivity cells; inputs use the selected 50 Batch-A clusters; verifies the report stays BLOCKED without third-anchor and Batch-B distributions | PENDING hosted CI smoke |
| `scripts/test_reduced_sample.py` | Exact 100 counted indices, 50 clusters, two records per cluster, AB/BA and expected suite order | PENDING hosted CI |
| `scripts/test_make_batch_dispatch.py` | Partial AB/BA pair recovery, complete-pair suppression, duplicate-slot rejection, time-control identity and opening-name mismatch | PENDING hosted CI |
| `scripts/test_match.py` | New end-to-end exact schedule-index recovery and out-of-shard rejection | PENDING hosted CI |

SCREEN-3 and CTRL-2-R have terminal successful shard jobs but skipped their evidence aggregation jobs. Their shard artifacts are not canonical gate evidence and have not been scored in this checkpoint.

## RATING-100 hosted validation record — 2026-11-17

CI run 44062359630 (before the SHA-256 subset correction): Linux and Windows each passed Rust fmt, clippy and Rust test groups (12, 3, 21 and 4 tests), match.py 111/111, rating_estimator 65/65, reduced_sample 7/7, dispatch recovery 5/5 and merge-batch self-test. Both operating systems then failed verify_opening_subsets.py because the initially generated reduced suites did not match the standard SHA-256 selector. The files/hash pins are superseded. Rerun result on the corrected commit is PENDING; do not mark the verifier PASS based on this failed run.


## RATING-100 selector correction — successful hosted validation

CI run 44066217195 on commit 5b63e273d77cfb097f0ad73bc28dda05cc19adad passed on Ubuntu, Windows and Rust 1.80. Both OS jobs reported match.py 111/111, rating_estimator 65/65, reduced_sample 7/7, dispatch-recovery 5/5, merge-batch self-test ALL CASES PASS, and the deterministic suite verifier confirmed 50 Batch A openings, 50 Batch B openings, zero overlap and the registered hashes. The 36-scenario power smoke completed and asserted status BLOCKED. Rust test groups passed (12, 3, 21 and 4); release build, UCI smoke and perft d3 passed. Anchor verification run 44066217113 passed all 13 jobs; candidate tree binary SHA-256 168dc0ab22749f8dc7a6be5248cd7426f9f2bfd3fda8077bc6218959ad6e41d7, bench signature 141943aa23b3fc68.

A subsequent commit adds engine-SHA provenance checks to the power generator, dispatch CLI and rating-run workflow; its tests and exact-head CI are still pending.

## 2026-11-17 — power-provenance test correction

CI run 44067364552 on 29b627e: test_make_batch_dispatch passed (7/7); test_power_analysis had 3/4 passing, with one error-message expectation mismatch. An unknown engine hash was correctly rejected at the SCREEN-2/ENGINE-1 manifest allowlist before the subsequent A/B engine-hash equality check. The test now expects the earlier fail-closed message. No CI pass is claimed for 29b627e; a new full run is required on the follow-up commit.

## 2026-11-17 — Windows CRLF regression

CI run 44067826990: Ubuntu success; Windows failed power smoke on a raw SCREEN-2 games.jsonl merged hash due CRLF checkout. A unit test now simulates CRLF while preserving the manifest hash, and another confirms modifying a record still fails the hash check. Exact LF attributes are added for both SCREEN-2 games files. Full CI rerun is required.
