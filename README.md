# README — Flawless Chess Engine

An independent, from-scratch chess engine written in Rust. **Not a Stockfish derivative.**

- **Engine name (UCI):** `Flawless`
- **License:** Apache-2.0 (see `LICENSE`)
- **Product:** FlawLessChess · **UCI engine name:** Flawless · **Cargo package:** `flawless` · **Version:** 0.1.0 (pre-V1; tag and GitHub Release pending the gates in FINAL_AUDIT_PROGRESS.md)
- **Status:** pre-V1 (`0.x`). V1 gates NOT met — and **no calibrated absolute rating exists in
  either direction** (it has not been measured; see `STATUS.md`). In-sandbox relative probes vs pinned
  Stockfish 19 WASM (e.g. ~0.44–0.53 score vs Skill 5) are internal trend signals only, never an Elo
  rating. No official CCRL/CEGT rating exists. See `STATUS.md` for the live checklist and
  `CHANGELOG.md` for releases.

## Quick start

```bash
cargo build --release   # Rust ≥ 1.80 (MSRV); rust-toolchain.toml pins 1.99.0
cargo +1.80 build --release   # force the MSRV toolchain instead of the pinned one
./target/release/flawless                  # no arguments: UCI mode on stdin/stdout (for GUIs)
./target/release/flawless uci              # same as above, explicit
./target/release/flawless perft 6          # perft from startpos
./target/release/flawless bench            # fixed-depth-10 search benchmark + signature
./target/release/flawless --help           # list the commands
```

Launching the executable **without arguments starts UCI mode** — the form conventional UCI GUIs use
when they start a custom engine. Explicit subcommands remain available and unchanged.

Commands (CLI): `perft <depth> [fen]` · `divide <depth> [fen]` · `bench` · `bench_eval` · `eval [fen]` · `moves` · `hash` · `uci` · `--version` · `--help` / `-h`.

## Using FlawLessChess in a chess GUI

1. Build or download `flawless` (Windows: `flawless.exe`).
2. In the GUI (Arena, Cute Chess, or any UCI client), add an engine, choose the executable, protocol `UCI`.
3. Time controls and `go movetime` are supported. `go movetime N` searches for about N ms.
4. Windows GUI test instructions and a checklist: `docs/WINDOWS_GUI_TEST.md`.

GUI playability has not yet been verified by the project; see the release-candidate report.

## What works (V1 scope)

Standard chess legal move generation · FEN · PGN export from match tooling (no PGN reader exists) ·
UCI (MultiPV, Hash, Threads=1, ponder) ·
perft · iterative-deepening alpha-beta with aspiration windows, transposition table, quiescence search,
move ordering, null-move pruning, late-move reductions · classical tapered evaluation · benchmark CLI ·
Windows + Linux release builds · CI.

## What does NOT work / is deferred

SMP search (`Threads` is capped at 1 and reports as such) · NNUE (classical eval only; NNUE is a
documented future step) · Chess960 · opening books · syzygy tablebases · any claim of an official
CCRL/CEGT rating (none exists — all probes so far are in-sandbox internal estimates with pinned
opponents; do not present them as official ratings).

## Documentation map

`ARCHITECTURE.md` (RFC) · `docs/adr/` · `TESTING.md` · `BENCHMARKING.md` · `RESEARCH_ROADMAP.md` ·
`DESIGN_LOG.md` · `AGENTS_LOG.md` · `FAILURE_LEDGER.md` · `STATUS.md` · `CHANGELOG.md` · `AGENTS.md`

## Known limitations (pre-V1)

- Single-threaded search (`Threads` is fixed at 1).
- `Hash` accepts 1–1024 MiB. The transposition table is capped at 1 GiB (2^27 entries), so larger values are rejected with an `info string` on stdout.
- `go searchmoves` that names only illegal moves does not return `bestmove 0000`. The search considers all legal moves and prints an `info string` saying so. This departs from the UCI wording ("restrict the search"); see DESIGN_LOG 2026-11-20.
- Classical evaluation only; no opening book; no tablebases.
- Search strength is not calibrated; no official rating exists.
- Windows artifact integrity and GUI playability are verified only when the release-candidate
  checklist in `docs/audit/2026-11-19-v0.1.0-release-candidate.md` is completed.

## Building on Windows

Install VS Build Tools (C++ workload) or MinGW-w64, plus Rust via rustup, then `cargo build --release`.
Windows builds are exercised by CI (fmt, clippy, tests, release build, UCI handshake, perft sanity).
CI also builds a Windows x64 executable (`x86_64-pc-windows-msvc`) and uploads it as a workflow
artifact named `flawless-windows-x64-<commit-sha>` containing `flawless.exe`, `SHA256SUMS.txt` and
`BUILD-MANIFEST.txt`. These are CI build artifacts, not a GitHub Release; the repository does not
publish binaries (see `.github/workflows/ci.yml`).
