# BENCHMARKING.md — measurement policy & infrastructure

## Measurement categories (never conflate)

1. Fixed-node search efficiency (nodes to reach depth at fixed search).
2. Fixed-time playing strength (games, Elo vs pool).
3. NPS / microbenchmarks (mach reproduces only the implementation, not strength).
4. Tactical suite results (e.g., WAC-style puzzles once wired).
5. Rating estimates vs a pinned opponent pool.

## Pinned environment template (record per experiment)

- Commit SHA, binary SHA-256, build flags (`-C target-cpu`? none — portable default), profile.
- UCI options: Hash, Threads, MultiPV.
- Opponent(s): name, version, binary SHA-256, options.
- Time control; opening suite + seed; color-reversal plan; adjudication rules.
- Hardware + OS; date; operator (agent session id).

## Rating policy (see ARCHITECTURE §9)

- Primary reference scale: CCRL 40/15 (i7-4770k equivalence; Stockfish 10 calibration reference;
  ponder disabled; same hash policy; generic opening books). As close as resources permit locally.
- Secondary: CEGT 40/20. **No cross-scale subtraction.**
- No batch has yet been run against documented-Elo anchors, so **every result to date is a private
  relative estimate** (opening-clustered CI), NOT "CCRL-anchored" and never an official rating. Only a
  batch meeting all of RATING_PROTOCOL §2–§6 (documented anchors, verified binary SHA-256, null
  controls) may carry a *CCRL-anchored (private)* label.
- Paired openings, reversed colors, opening-clustered bootstrap CIs, ≥2 confirmation batches,
  staged sample sizes (200–500 / 1,000–2,000 / 4,000–6,600).
- Null controls included (e.g., baseline vs itself must score ≈ 50%).

## Infrastructure in this repo

- `cargo run --release -- bench` — fixed-depth-10 search benchmark over 12 fixed positions; prints
  per-position depth/score/nodes and a total + FNV-1a `bench signature` (deterministic for identical
  engine code; node counts are the regression signal). Signature history (all 2026-11-14):
  `d790483532d87af0` → `3086f65159758c9d` (2,317,474 nodes; audit fixes) → `f1aceef5a9dbc812`
  (2,367,196 nodes; FIDE ep-hash semantics + castling-origin-king guard) → `fc907eba40b7869f`
  (3,899,001 nodes; draw/TT/delta-prune corrections — NPS cost accepted for soundness) → **re-measured
  2026-11-14 on db174e4 (restored npm toolchain; `cargo run --release --locked -- bench`): signature
  unchanged (`fc907eba40b7869f`, i.e. depth/score/PV line stable) but 2,221,199 nodes @ d10 — a 43%
  node reduction from the per-capture delta-pruning rework — 8.56 s, 259,619 nps on this 2-vCPU
  sandbox. CI runs an informational bench step which also uploads the signature as an artifact.**
  The stale
  "2,326,103 nodes in ~3.1 s" line was a mixed-build measurement error and has been removed.
- `cargo run --release -- bench_eval` — fixed-node eval micro-benchmark (1000 evals/FEN, ~100–500 ns/eval in sandbox).
- `cargo run --release -- perft <depth> [fen]`.
- `cargo run --release -- uci [uci|perft ...]` — full UCI engine; `go movetime/depth/clocks`, `ucinewgame`, MultiPV, ponder.
- `scripts/match.py` — game runner (UCI subprocess), writes PGN + JSONL records, supports opening files
  (`name|moves` UCI lines), color reversal (paired mode), adjudication via python-chess outcomes,
  timeout/illegal-move forfeits, and wall-clock accounting. Verified end-to-end.
- `scripts/stats.py` — score, Elo difference (logistic model), opening-clustered 95% bootstrap CI
  (bootstrap over opening clusters, not games).
- `scripts/diftest.py` — differential correctness vs python-chess.

## Pinned benchmark opponents

- **Stockfish 19 WASM (lite-single, single-threaded)**, npm package `stockfish@19.0.1`
  (`buildVersion 19`, GPL-3.0), files at `node_modules/stockfish/bin/stockfish-19-lite-single.*`.
  SHA-256 (recorded 2026-11-14): `stockfish-19-lite-single.js` ccb130d7ff29408531c47d859a49f91d59d4f482d05a53eb1a3231a4f624c91a,
  `stockfish-19-lite-single.wasm` ee4f115bdb2d32cadf96cada104a05b5ec257d7ad6f57582190b49bc71f096de.
  (Full-strength `stockfish-19.js` also present: 623ee70a10d6dc202375127b49e2e1822635f9ab07693ae7be28e50a787f6218; `stockfish-19.wasm`: a599d78d72e0722d8895be84aca8b492d12e8bba3cdfcbcbc4a64017888c6667).
  Run via `node`. Used ONLY as a pinned benchmark opponent, never as a code source.
  Invoked with `setoption name Skill Level value <0..20>` to build a strength ladder; CCRL-equivalence
  of any skill level is NOT claimed.
- Location on disk: `/home/user/opponents/` (outside the repository; not committed).

## Completed probes (2026-11-14)

See STATUS.md "Measured strength probes" for the table. Raw evidence: `benches/probe-001-sf19lite-skill0/`
(40 games), `benches/probe-003-sf19lite-skill5/` (40, pre-RFP/CE build, 2026-11-14T03:28:59Z),
`benches/probe-002-sf19lite-skill10/` (40), `benches/probe-004-sf19lite-skill5-rfp/` (40, RFP+CE
build, 2026-11-14T04:26:01Z), `benches/ab-004-rfp-checkext/`
(40 A/B vs pre-change build, movetime 50 ms), `benches/probe-005-postfix-validation/`
(40, post-refactor builds, 100 ms/move; Flawless 24/40 = 0.600, 95% CI [0.463, 0.725],
logistic +70 CI [−26, +168]; engine binary SHA-256 9d7b22d5d1af0c56b0d56f908edd679b8628d90126d2fe5efc3c4faf24144208, git commit 45f8507 in meta.json) — PGN + games.jsonl + meta.json committed.
**Binary-hash caveat:** probe-003 and probe-004 meta.json predate the binary-hashing instrumentation
(added 2026-11-14); they record the probe command line but NOT the probed binary's SHA-256 or the
git commit — their engine identity rests on the recorded cmd + timestamps, not a verifiable hash.
New batches record `white_artifact`/`black_artifact` ({binary path, sha256}) and `git_commit` in
meta.json (see `scripts/match.py`). Method limitations (honest): fixed 100 ms/move, single pinned
WASM opponent, no CCRL-equivalent TC, Skill Level ≠ Elo, 2 vCPU sandbox, bootstrap CIs over 20 opening
clusters only.

## Current status (2026-11-14)

No rated games exist yet. Opponent availability is limited by the sandbox network (only github.com /
codeload.github.com / api.github.com / pypi.org / files.pythonhosted.org / registry.npmjs.org).
Candidate anchored opponents: Stockfish WASM from npm (`stockfish@…`, to be pinned and hash-verified
before any match) — its exact CCRL equivalence is NOT claimed; only internal A/B strength measurements.
Any Elo number produced here is an in-sandbox estimate with stated uncertainty, not an official rating.

## Raw evidence retention

`benches/<experiment-id>/` contains: PGN, JSONL, match config (meta.json incl. binary SHA-256 +
git commit for new batches), engine logs, stats output. Never overwrite; `scripts/match.py` refuses
to write into a directory holding non-empty batch artifacts, and new batches go in new directories.

## Rating batch pre-registration (2026-11-14)

- `benches/rating-openings-batchA.txt`, `benches/rating-openings-batchB.txt` — 60 distinct,
  FEN-legality-verified opening lines each, curated 2026-11-14 from standard opening theory,
  **mutually disjoint**; every line is played as an AB/BA pair (exact color reversal). Batch B is
  used for the independent confirmation batch.
- `benches/anchor-pool.template.json` — schema template for the anchor descriptor embedded in
  batch manifests via `scripts/match.py --anchor-json`. Contains NO anchor values; filling it with
  independently verified CCRL 40/15 or CEGT 40/20 data is a prerequisite for any gate run.
- Batch manifest (`meta.json`) now records: binary SHA-256 for launcher AND every hashed artifact
  (including WASM loaded dynamically, via `--white-artifact`/`--black-artifact`), git commit, CPU/RAM/OS,
  hostname, python version, full adjudication rules, color-pairing rule, and (with `--anchor-json`)
  the complete anchor-pool descriptor. `scripts/match.py` refuses to start unless the anchor pool
  passes the schema check.
## 2026-11-17 — reduced sample design and runner telemetry

RATING-100 reduces the proposed counted sample from 2,040 to 100 games per anchor per batch: 50 opening clusters × one paired repetition × AB/BA. For three anchors and two disjoint batches the arithmetic is 12,240 → 600 counted games (95.0980%). This is a design/sample-count reduction only; it is not evidence of faster chess search, higher games-per-hour, or a stronger engine.

The new workflow records per-shard `/usr/bin/time -v` output and pre/post cgroup values including CPU quota (`cpu.max`), throttling counters (`cpu.stat`), effective cpuset and memory limit. Future throughput reports must compare elapsed wall time, user/system CPU, peak RSS, cpu throttling, runner model/image, actual shard count/concurrency and counted-game totals. Do not infer a concurrency win from vCPU labels alone.

The 100-game design is currently **BLOCKED** for confirmatory use: selected-subset variance is available for only two screening anchors; the third-anchor covariance and disjoint Batch-B cluster distribution remain unmeasured. Near a 2,100 Elo true-rating alternative, the sensitivity analysis shows only ~63–77% power for all three lower-bound conditions without variance inflation, ~22–31% at 1.5× cluster SD and ~8.7–12.4% at 2×. The registered strict 95% lower-bound rule and both null controls are unchanged.

## 2026-11-17 — ENGINE-2 SEE-ordering candidate (preliminary hosted build)

- Candidate source: the RATING-100 / SEE-ordering implementation commit. The SEE change is limited to capture ordering; no SEE-based quiescence pruning is used.
- Hosted Ubuntu fixed-depth-10 bench signature: `141943aa23b3fc68` (12 fixed positions, 2,530,885 nodes in 7.09 s on the recorded runner). This is a deterministic implementation fingerprint, not a playing-strength or throughput comparison.
- The earlier `fc907eba40b7869f` signature belongs to the pre-SEE ordering candidate and is retained only as historical evidence. The anchor verifier now expects the new signature.
- The new candidate binary SHA-256 remains pending a successful exact-head anchor-verification run. No rating games have been dispatched for this candidate.

## 2026-11-17 — reduced-suite byte-integrity correction

The initial reduced-suite bytes were rejected by the Python standard-library selector verifier in CI; no confirmatory work ran. Corrected selector uses hashlib.sha256 over the documented domain-separated normalized original line, selecting the 50 lowest digests and retaining source order. Corrected suite byte hashes: Batch A 5abdcdbddec0f22d7e6eff8974ee402363c8c3df318b8110d7204adf69f5c1df; Batch B ccb4901742eca25b0b10f1a3c9fdfc17b2967a1939c2d7e466c2c5495b6d4253. The power assessment remains BLOCKED; no dispatch is authorized.


## 2026-11-17 — ENGINE-2 identity and power-report scope

- Exact branch tree: source commit 5b63e273d77cfb097f0ad73bc28dda05cc19adad, tree 75bc5633e1466d5abf1f4c7d5999bc4a3915e193.
- Anchor verification run 44066217113 built the matching PR merge tree: bench signature 141943aa23b3fc68; binary SHA-256 168dc0ab22749f8dc7a6be5248cd7426f9f2bfd3fda8077bc6218959ad6e41d7. This is a source/binary identity, not a strength or throughput comparison.
- Current RATING-100 power inputs belong to ENGINE-1 SHA-256 9663697da62e33229d516af3681c442e268287c59d6b97ff2cd13256b564d428. The report is now engine-pinned; the generator checks both SCREEN-2 manifests and raw data hashes, and dispatch tooling refuses any binary SHA mismatch. It cannot authorize ENGINE-2.
- ENGINE-2-specific screening and controls are still absent. No game-count or games/hour performance result has been measured for this candidate.

## 2026-11-20 — S-14 colour-relative move tie-break (current bench reference)

- Change: `relative_move_key` in `src/search.rs` orders equal-score moves by a colour-relative key, so the search
  no longer depends on the side's raw square numbering. Found by `scripts/eval_symmetry_probe.py` (see FAILURE_LEDGER S-14).
- Current hosted reference: fixed-depth-10 bench signature `849a85bf7e8e1eba` (12 fixed positions, 2,311,437 nodes after F-14; 2,311,407 before it,
  in about 6.1 s on the local release build, 380k–391k nps). This replaces `141943aa23b3fc68` as the active reference.
- Comparison on this change: disabling LMR also makes the depth-4 probe symmetric (0/120), but needs 45,805,850 nodes
  for the same bench (about 18× more nodes, 117 s). LMR stays enabled.
- The `141943aa23b3fc68` entry above is historical and is kept unchanged.


### 2026-11-21 — TT allocation change (F-20, `unsafe` in `src/tt.rs`): before/after

- Script: `/tmp/audit/tt_bench.py` (scratch; not in the repo). For each size: 5 cold starts; `setoption Hash N`, `isready`;
  the first `go movetime 1` is timed (the table is allocated at the first `go`); RSS is read at idle and after a
  `go movetime 500` search. Linux, 2 vCPU sandbox (not the reference machine).
- Before: release build of the pre-change `src/tt.rs` (`52d6510`). After: working tree at this change.

| Hash MiB | first-go ms before (median) | first-go ms after (median) | idle RSS MiB before / after | RSS after 500 ms before / after |
|---|---|---|---|---|
| 64 | 2.2 | 1.9 | 4.9 / 4.8 | 38.3 / 39.8 |
| 256 | 1.8 | 2.9 | 4.8 / 4.8 | 50.2 / 44.9 |
| 1024 | 2.2 | 2.9 | 4.8 / 4.8 | 49.8 / 33.2 |

- Reading: the allocation stays lazy in both builds (about 2 ms for a table of up to 1 GiB, so pages are not written).
  The RSS-after-search columns vary from run to run in both builds (33–50 MiB); no systematic difference is shown.
  This is a sandbox measurement, not a claim about the reference machine.
