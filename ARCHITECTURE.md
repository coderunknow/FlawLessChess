# ARCHITECTURE RFC — Flawless

Status: **Accepted (v1 scope)** · Created: 2026-11-14 · Authors: engine team (agent)
Decision log: see `DESIGN_LOG.md` and `docs/adr/`

This document evaluates the major design choices for the engine, records the alternatives considered,
and selects based on testable evidence. Where a decision is provisional until measurement, it is marked
**provisional**.

## 0. Constraints from the specification

- Independent Rust implementation. No Stockfish-derived code. No third-party engine tables/weights.
- Zero external crate dependencies (crates.io is unreachable from the build environment, and a minimal
  dependency footprint is desirable anyway). Everything is `std`-only.
- V1: standard chess, UCI, perft, benchmark CLI, MultiPV, time management, honest `Threads`.
- Reference machine: i5-7300U, 8 GB RAM. Single-threaded V1; architecture must not preclude SMP later.
- Apache-2.0 license preserved.

## 1. Board representation

### 1.1 Alternatives considered

| Option | Movegen correctness | Attack detection | Make/unmake | Perft speed | Complexity | Notes |
|---|---|---|---|---|---|---|
| A. 0x88 mailbox | good | incremental/loop-based | medium | slow-medium | low | Classic; simple; branchy inner loops, poor cache use for bulk ops |
| B. Bitboards + lookup tables (knight/king/pawn) + **magic bitboards** (sliders) | excellent | table/magic lookup | very fast (XOR) | fast | medium (magic generation) | Industry standard; branch-light; SIMD-friendly |
| C. Bitboards + hyperbola quintessence (sliders) | excellent | arithmetic on occupancy | very fast | medium (slightly slower than magic) | lowest for sliders | No big tables, no init cost, fully portable, deterministic startup |
| D. Hybrid (bitboards for attacks/occupancy + mailbox for piece lookup) | excellent | fast | fast | fast | medium | Used by several engines; duplicates state (sync bug surface) |

### 1.2 Decision (ADR-0001)

**Option B — bitboards with magic bitboards for sliding attacks**, with the following properties:

- 12 piece bitboards (`pieces[2][6]`) + 6 type occupancy + 2 color occupancy + 1 total occupancy cached.
- Knight/king attack tables: 64-entry `u64` LUTs (embedded constants, computed).
- Pawn attacks: branchless shifts with file-edge masks.
- Slider attacks: fancy magic bitboards. **Magics are generated at startup with a fixed-seed PRNG**
  (splitmix64), not copied from any engine or table compilation. Startup generation cost is measured;
  if it exceeds ~1 s on the reference machine, we fall back to hyperbola quintessence (Option C) behind a
  build-time feature or change the default. Deterministic seed ⇒ deterministic tables ⇒ reproducible.
- Occupancy iteration via `u64::trailing_zeros` + `reset lowest bit`.
- Zobrist hashing incremental; keys generated from splitmix64 fixed seed.

Rationale: best-measured perft speed and search efficiency potential; fully independent (magics are found
by search, not copied); the startup cost is acceptable if measured. Option A rejected (slower, branchy).
Option D rejected (state duplication sync risk). Option C retained as the documented fallback and as a
cross-check implementation for correctness testing (two independent slider generators compared in tests).

### 1.3 Evidence plan

- Perft node throughput for startpos/Kiwipete to depth 5–6 in release build.
- Correctness: magic attacks vs hyperbola attacks must agree exactly on all 64 squares × all
  occupancies (property test over random blockers). This is a strong differential test of slider attacks.
- Make/unmake round-trip + incremental-vs-full hash recomputation property tests.

## 2. Move generation

**Pseudo-legal generation, filtered by make/unmake legality** (a move is legal iff after applying it our
own king is not attacked). This is the standard, simple, correct approach; legal-move generation with
pin/mask scissors is a later optimization if profiling justifies it.

- Move list: fixed-capacity stack array (`[Move; 256]`), `Move` is a packed `u16`
  (from:6 | to:6 | promotion:2 | special:2) with `const` constructors; no heap allocation in search.
- Bitscan-driven loops for pieces; pawn logic with direction tables; castling with full legality checks
  (rights + squares empty + not through/into check + not in check); en passant with the discovered-check
  pin case handled by make/unmake legality filtering (correct by construction).
- Promotions: generate all four promotion pieces.

## 3. Transposition table

- Zobrist keyed, fixed size from `Hash` option (MiB, default 64 MiB — safe on 8 GB reference machine;
  range 1–1024 MiB, the table is capped at 2^27 entries = 1 GiB),
  power-of-two bucket count, 1 entry/bucket (V1), 8-byte entries packed:
  `key16 | move16 | score16 (i16, cp, side-to-move-relative, mated-in-1 offset) | depth8 | gen8 | bound8(2 bits used)`.
- Depth-preferred replacement + generation counter for aging across `ucinewgame`.
- Probe/store with always-replace on deeper depth; TT move used for ordering; TT cutoffs only on
  non-PV nodes with sufficient depth (exact/lower/upper bounds semantics per standard AB).
- Cleared on `ucinewgame` and `setoption Hash`.

## 4. Search

Iterative deepening driver from the root, with:

- Negamax alpha-beta with **PVS** (principal variation search).
- **Aspiration windows** around the previous iteration's score (researched bounds; widened on fail).
- **Quiescence search**: captures + promotions (+ check evasions if in check), standing pat,
  delta pruning (200 cp), MVV-LVA capture/promotion ordering.
- **Move ordering** (as implemented): TT move → captures/promotions by MVV-LVA (+promotion bonus) → killer 1/2 → quiet history. No SEE anywhere in the current code; SEE-based pruning/ordering is an unscheduled roadmap item, NOT implemented.
- **Null-move pruning** (guarded by beta > value window and non-trivial non-pawn material to limit
  zugzwang risk), with adaptive reduction based on depth and score margin.
- **Late move reductions** (logarithmic, gated by depth ≥ 3, reduction reduced for captures/promotions and PV nodes).
- **Check extension** (+1 ply when the move gives check, bounded).
- Futility pruning at depth 1–2 in near-quiet nodes.
- Draw by repetition (2-fold in-search = draw score), fifty-move rule, insufficient material.
- Mate score handling with ply offset; TB-free.
- Time management: soft/hard limits from `wtime/btime/winc/binc/movestogo`, plus `movetime`, `depth`,
  `nodes`, `infinite`; `stop` and ponder handling with a shared atomic stop flag; node counter checked
  every 1024 nodes for time and stop; the `nodes` limit is checked on every node, so `go nodes N` spends exactly N
  nodes. Stop must be responsive (<50 ms).
- MultiPV: root-level — each iteration records scores for the top-N root moves; aspiration disabled;
  MultiPV=1 path identical to normal search.
- **Threads**: option exposed, hard-capped at `max 1` in V1 and reported as such; search state is
  encapsulated (`SearchContext`) so a future Lazy SMP can iterate without global mutable state.
  No `unsafe` in v1 outside the (optional) SIMD eval module; search is plain safe Rust.

Feature acceptance rule: **every** search feature lands behind its own commit with `cargo test` +
perft + a strength screening run; a feature that gains NPS but loses fixed-time strength is rejected.

## 5. Evaluation

Modular `Evaluator` design (object-safe trait, side-to-move relative, centipawn scores):

1. **Classical evaluator (V1 default)** — handcrafted, self-contained:
   - Tapered evaluation (midgame/endgame interpolation by material phase).
   - Material + piece-square tables (own tables written for this project).
   - Pawn structure: isolated, doubled, passed (with square control), candidate-ish encouragement via mobility.
   - Mobility: pseudo-legal move counts for N/B/R/Q (from attack tables).
   - Bishop pair bonus; rook on open/semi-open file; rook on 7th rank.
   - King safety: pawn shield integrity + chebyshev-distance-weighted enemy attack units near king.
   - Tempo bonus.
2. **NNUE evaluator (deferred, feature-gated `nnue`, NOT default)** — same trait; only activated after a
   documented strength win. A `NNUE` UCI option will list `none` (classical) until then.
3. Interface: `fn evaluate(&mut self, pos: &Position, ply: usize) -> i32` with an incremental
   accumulator slot reserved in `SearchContext` for NNUE-style updates.

Evaluation correctness gates: side-ness symmetry (mirror test by color-swapped FEN must negate score),
capture-the-queen sanity, known-extreme positions (KQvK > 0, KQ vs K checkmating pattern), bench
determinism.

## 6. Concurrency

V1 is single-threaded by design, but:

- No global mutable state; `TT`, `SearchContext`, `Position` are passed explicitly.
- Time/stop via `AtomicBool`/`AtomicU64` to allow future cross-thread stop.
- `Threads` UCI option exists with `min 1 max 1 default 1` and the engine states plainly that only
  one thread is used. Not claiming SMP.

## 7. UCI protocol

Hand-rolled line parser (no deps), robust to malformed input (never panics; ignores/notes unknown
commands; `err:` replies for command errors). Implemented: `uci`, `isready`, `ucinewgame`, `position
(startpos|fen ...) [moves ...]`, `go` (depth/nodes/movetime/wtime../movestogo/searchmoves/infinite/ponder),
`stop`, `ponderhit`, `setoption name (Hash|Threads|MultiPV)`, `register` (answer ok), `quit`, `debug`.
Asynchronous search on a worker thread; `go` returns immediately; `bestmove` printed on completion.

## 8. Build & distribution

- `Cargo.toml` with `[profile.release] lto = "fat"`, `codegen-units = 1`, `panic = "abort"`? — **No**: keep
  unwind to keep UCI error paths safe; `panic="abort"` rejected (a panicking search must not hard-crash
  the host process silently; we clamp panics at thread boundary instead).
- Runtime SIMD dispatch: V1 keeps everything scalar/portable; the first unsafe/SIMD block will be the
  NNUE/accumulator kernel with `is_x86_feature_detected!("avx2")` + scalar fallback, documented invariants.
- `rust-toolchain.toml` pins `1.99.0`; `Cargo.lock` committed; zero dependencies ⇒ trivial license audit.
- CI (GitHub Actions): fmt, clippy `-D warnings`, tests, Windows + Linux release builds, UCI handshake + bestmove smoke tests on both, MSRV (Rust 1.80) check job.

## 9. Rating measurement (policy)

- Primary reference: CCRL 40/15 conditions as closely as our resources permit; label all local results as
  **private, CCRL-anchored estimates**, never as official CCRL/CEGT ratings.
- Secondary reference: CEGT 40/20 (no cross-scale comparison).
- Method: paired openings, reversed colors, pinned opponent pool with anchors near the threshold,
  opening-clustered bootstrap 95% CIs, ≥2 independent confirmation batches, null controls, raw PGN kept.
- Staged sample sizes: 200–500 screening → 1,000–2,000 candidate eval → 4,000–6,600 confirmation.
- Resource reality: this environment cannot run multi-thousand-game 3+2 matches. Any number produced here
  is reported with its (large) uncertainty and marked INCONCLUSIVE where applicable. The 2,000 Elo release
  gate cannot be declared passed without the required evidence.

## 10. PGN & CLI

- Subcommands (as implemented): `uci`, `perft <depth> [fen]`, `divide <depth> [fen]`, `bench`
  (fixed-depth-10 signature benchmark), `eval [fen]`, `bench_eval`, `moves`. No `pgn` subcommand exists
  yet; `makefen` does not exist.
- PGN: **write-only**, from `scripts/match.py` (game evidence records). The engine has no PGN reader
  and none exists anywhere in this repository; there is no `pgn` subcommand and no SAN output.
  python-chess (pinned 1.11.2, GPL-3.0+, **test-only**, never linked) is the differential oracle in
  `scripts/` (in particular `scripts/perft_oracle.py`, `scripts/diftest.py`).

## 11. Rejected alternatives (kept for the record)

- Copying public "standard" magic number tables (rejected: independence policy).
- Stockfish-derivative evaluation or NNUE weights (rejected: license/independence policy).
- crates.io dependencies (rejected: unavailable + footprint policy).
- hyperbola quintessence as default (kept as verified fallback; magic chosen for speed, subject to measurement).

## 12. Consequences & risks

- Zero-dependency code means we hand-roll protocol/parsing/statistics glue; mitigated by fuzz-ish tests.
- Runtime magic generation adds startup time; measured and gated.
- Rating gates may remain unmet in this environment — project remains ACTIVE/INCOMPLETE rather than
  claiming false completion.
