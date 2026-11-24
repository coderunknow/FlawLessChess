# Release validation — 2026-11-19 (branch arena/2d2d30b4-flawlesschess)

Scope: the full-release mission (audit, chess validation, UCI robustness, full games, resource
use). This document records only evidence that was actually produced. It does NOT declare a
release. Status: **NOT READY** (see "Release gates" below).

Tooling (test-only, stdlib or python-chess 1.11.2 from PyPI; never linked into the engine):
- `scripts/selfplay_games.py` — full games through python-chess's UCI client, wtime/btime/inc, logs in `benches/games-20261119/`.
- `scripts/uci_protocol_probe.py` — 10 interactive UCI lifecycle probes (exit codes, timeouts, stop/quit).
- `scripts/uci_malformed_probe.py` — 37 hostile inputs (no panic, no hang, UCI-only stdout).

## Perft (engine vs python-chess vs CPW reference counts)

- Standard positions, depths 1–4 (startpos d4, Kiwipete d3, pos3 d4, pos4 d3, pos5 d3, pos6 d3): 22/22 match engine = python-chess = known counts, 0 mismatches.
- Deeper: Kiwipete d4 = 4,085,603; pos4 d4 = 422,333; pos5 d4 = 2,103,487; pos3 d5 = 674,624 — all match the reference.
- `scripts/diftest.py` (random games, legal move set identical to python-chess): 2,321 positions, 0 mismatches, DIFTEST PASSED.

## Full games (engine vs engine, python-chess referee, 3 s + 50 ms)

| Opening | Plies | Termination | Replay check |
|---|---|---|---|
| startpos | 155 | checkmate, 1-0 | all moves legal; 2 castlings |
| kiwipete | 144 | checkmate, 0-1 | all legal; 3 promotions |
| promo-race | 23 | checkmate, 1-0 | all legal; 1 promotion |
| castle-both | 15 | checkmate, 1-0 | all legal |
| stalemate-trap | 0 | stalemate, draw (correct) | — |
| ep-setup | 100 | threefold repetition, draw | all legal; 2 castlings |

Every move was checked by python-chess against its own legal-move generator and replayed from the
logged FEN. No flag falls, illegal moves, crashes or hangs. Slowest single move: 0.35 s.

## UCI lifecycle (10/10 pass)

handshake; no banner before commands; depth-4 search after `position startpos moves` (completed
`info depth 4` required); 10 ms clock returns promptly; `go movetime 300` no overrun; `go infinite`
then `stop` (no premature bestmove, stop latency < 2 s); `quit` during infinite exits 0; setoption and
junk tolerated; FEN promotion position legal; stalemate returns `0000` (no invented move).

## Malformed input (37/37 OK)

Empty/missing/invalid FENs, out-of-range FEN counters, illegal and repeated moves, huge and negative
`depth`/`movetime`/clock/`nodes` values, bad `setoption` values, `debug`, NUL/UTF-8 junk. No panic,
hang, non-zero exit or non-UCI stdout.

## Findings

1. **Time use under `go movetime` is conservative (not a correctness bug; NOT changed).**
   Interactive measurement (startpos/kiwipete/pos3, movetime 300/1000/3000): engine returns after
   38–100% of the budget, reaching depth 7–16. Cause: `src/search.rs` stops iterative deepening when
   the predicted next iteration (3× last iteration) would overrun the soft limit. Changing it would
   alter the timing behaviour the rating evidence in `benches/` was collected under, so it is
   deliberately left for a separately evidenced change.
2. **Measurement pitfall (not an engine bug).** An early attempt measured `movetime` with `quit` in the
   same stdin burst as `go`. The engine stopped at depth 0 (`bestmove a2a3`), which is the known
   FAILURE_LEDGER pattern. All timing claims here use the interactive method (wait for each reply).

## Performance (2-vCPU sandbox, Linux, release build)

- `bench` (depth 10, 12 positions): 2,530,885 nodes in 5.71 s = 443,569 nps; signature `141943aa23b3fc68` (unchanged).
- Peak VmRSS during a 5 s search: 68.8 MiB (default 64 MB hash). No runaway memory observed.
- Startup to `readyok`: about 0.06 s per probe session.
- CPU utilisation of the child process was NOT measured reliably (the first attempt was invalid).

## Release gates (status)

- Engine correctness (perft, diftest, games, UCI lifecycle, malformed input): VERIFIED locally as above.
- CI on the final head: see the head-specific entry in AGENTS_LOG.md.
- CodeRabbit review on the final head: NOT VERIFIED (rate-limited, see AGENTS_LOG.md).
- Windows artifact contents (SHA-256, manifest, PE 0x8664): NOT VERIFIED (blob-storage download fails from this sandbox).
- Real GUI test (Arena, Cute Chess, Banksia): NOT PERFORMED — no GUI can be installed from the allowed hosts. python-chess's UCI client is an independent UCI client, not a GUI.
- Windows runtime of the exact release exe: only CI windows-latest runs it (the synchronised bestmove smoke and the artifact smoke). No local Windows runtime.
- Rating / V1 gates: NOT MET (STATUS.md). Nothing here changes that.
- MSRV 1.80: CI msrv job (see AGENTS_LOG.md); not re-run locally.

## Naming

`Cargo.toml` `repository` and `docs/ENVIRONMENT.md` use `Flawless-Chess-Engine`, which ADR-0002 records as
deliberate (external rename, URL not changed by the project). The verified remote is `coderunknow/FlawLessChess`.
Unchanged; needs a decision.

## Decision

No merge, tag or GitHub Release is made by this document. The release gates above that are NOT VERIFIED
block a release, and the project's own gates (STATUS.md) say v1.0.0 is not authorised.

## Superseded by the v0.1.0 candidate

- Finding 1 above (movetime early return, "deliberately left") is **superseded**: the fixed-time
  stop rule was changed in the v0.1.0 candidate. See `docs/audit/2026-11-19-v0.1.0-release-candidate.md`
  and `benches/movetime-20261119/`. The original text is kept as the historical record.

