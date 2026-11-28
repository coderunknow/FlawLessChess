# Dispatch Analysis — Queen-Trap Fix (ENGINE-5 candidate, 2026-11-27)

Scope: gameplay impact assessment of `queen-trap-fix.patch` (v2) before it is
allowed anywhere near the merge. Probes are diagnostic only (mission 2026-11-27).

## 1. Deployability decision and recommendation

**Provisionally deployable — pending probe evidence. Do NOT ship the v1
qsearch-only patch.** The full fix (v2) addresses the defect at every layer
found in the static audit:

| Layer | Status |
|---|---|
| qsearch move filter (drops queen flights) | fixed — full list kept when mover's queen is attacked |
| qsearch stand pat (queen counted alive) | fixed — disabled at attacked-queen nodes (also disables delta pruning there) |
| RFP `depth <= 3` (seals node blind) | fixed — explicit guard, skipped when mover's queen is attacked |
| futility `depth <= 2` (returns qsearch) | audited safe — only return path descends through the fixed quiesce |
| null-move pruning | audited safe — opponent's queen capture after the pass is a capture and is searched |
| TT cutoffs | audited safe once all nodes store fixed values |

Recommendation: hold merge; run ENGINE-5's own evidence chain after probes
confirm the patch on real cases.

## 2. Gameplay impact on standard positions

- The two qsearch changes activate **only** when the mover has an attacked
  queen. Quiet middlegames and endgames take byte-identical code paths (same
  filter, same stand-pat). Verified by the regression test
  `quiet_quiescence_still_stands_pat`.
- The RFP guard costs one queen scan (popcount-only loop) plus at most two
  `is_attacked` probes per RFP-eligible node (depth ≤ 3, non-PV, not in check),
  and only for positions whose side to move has a queen. Expected node inflation
  is below measurement noise outside of tactical positions.
- Positions with an attacked queen now search their quiet defences inside
  qsearch: slightly more nodes there, in exchange for not blundering the queen.
  Captures in qsearch are unchanged; delta pruning is unchanged outside
  attacked-queen nodes.
- `searchmoves` filtering happens in `search_root` before the search; the
  widened qsearch list cannot leak past it (regression test
  `searchmoves_strictness_holds_with_attacked_queen`).

## 3. Preservation obligations

- ENGINE-4 records (target `cb7242c`, binary `bbf9582db58b1fe8fb0aa8f3675e4bedcc7e62062e8f1fe41de9e6526af0c329`)
  stay valid for ENGINE-4 and only ENGINE-4. The pre-merge diagnostic probes
  are not measurement channels and never attach to the rating contract.
- The original campaign running now is bound to ENGINE-4; it completes on
  ENGINE-4. This patch must not alter `src/` until the original campaign has
  closed with its evidence merged (freeze holds — the patch ships as a file
  under `benches/diagnostics/` and is applied in runner working copies only).
- ENGINE-5 (this patch landed on `cb7242c`) requires its own full chain:
  fmt, clippy, locked release tests, differential-vs-reference, perf, protocol
  suites, 13 probes, anchor verification with its own binary hash, screening
  with its own output, power assessment, approval, confirmatory campaign under
  `rating-240-v1` (same TC / openings / adjudication / thresholds / sample).
  No evidence transfers in either direction.

## 4. Provisional limitation score: **6 / 10**

Deducted for: probe results not yet in hand (no empirical confirmation on the
patched binary yet); the 3 losses where the pre-fall move escapes detection
(theoretical horizon cases) are only mitigated, not proven gone; the RFP guard's
interaction with zugzwang-style null-move positions is theoretical; regression
fixtures are real-game FENs but the "queen lost by force" premises rest on the
adjudicator's defence checks, which the confirmatory campaign must confirm.
Score is provisional until the probe outputs and the ENGINE-5 confirmatory
campaign land.

## 5. Recommendation

1. Ship the **v2** patch (this file's companion `queen-trap-fix.patch`) — never
   the v1 qsearch-only patch.
2. Confirm with the diagnostic probe (`patched-queen-trap-v2`): the 8 needle
   moves must disappear at depths 8/10/12/14 and the fixed binary must pass the
   full `cargo test` suite including `queen_trap_tests`.
3. Keep the campaign and merge gates on ENGINE-4 records as planned; land this
   patch only after the original campaign closes, then run the ENGINE-5 chain.
4. Blockers to merge remain exactly: campaign conclusion (or the separately
   authorized termination protocol), rating gate, and the ENGINE-5 chain.
