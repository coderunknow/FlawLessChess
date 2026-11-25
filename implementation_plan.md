# PR #6 Implementation Plan (current state)

## Current state

- Branch `arena/247fe7df-flawlesschess`, PR #6 (draft), base `main` = `6ab5b33`.
- Time management fix: DONE (removed the predictive early stop).
- Counter move heuristic: DONE (HIST-1 partial).
- Space evaluation: DONE (EVAL-2 partial).
- Outpost evaluation: DONE and corrected to the classical zone (White ranks 5-6, Black ranks 3-4,
  files b-g) with boundary and symmetry tests.
- Tempo semantics: DONE and pinned by a regression test for both colours and the colour mirror.
- Ablation switch (`FLAWLESS_ABLATE`): DONE, documented in `docs/ABLATIONS.md`.
- CI benchmark workflow: DONE (`.github/workflows/relative-benchmark.yml`, quick profile per pull request,
  extended three-replicate profile on request).
- Gates on the head: fmt clean, clippy `-D warnings` clean, `cargo test --release --locked` 183/183,
  difftest 2,321 positions d=2 with 0 mismatches, perft(6) 119,060,324.

## Remaining work

### 1. Continuation history (HIST-1 remaining)
- Add a continuation history table indexed by (side, previous move, current move)
- Used for move ordering: moves that followed the opponent's previous move successfully get a bonus
- Distinct from counter moves (which respond to the opponent's last move)
- Not used in null-move or quiescence

### 2. Capture history (HIST-1 remaining)
- Add a capture history table indexed by (side, captured piece type, to_square)
- Used to order captures within quiescence and main search
- Complements SEE-based capture ordering

### 3. Rating gate re-evaluation
- The three-replicate extended relative profile (600 games) was executed and read back: 49.8%,
  INCONCLUSIVE, relative Elo -23.2 to +21.5. The candidate is not measurably different from the
  pinned baseline, so no relative strength claim can be made.
- Investigate whether the 2,000 Elo threshold is well-defined
- Document rating system, platform, TC, opponent pool, game count, CI method
- The absolute gate is still UNKNOWN / NOT MEASURED / NOT MET; the relative paired benchmark does not
  measure an absolute rating

### 4. Final validation and documentation
- Read back the pooled extended benchmark result and record it
- Fresh independent review (CodeRabbit) at the final head SHA
- Keep the PR a draft until the checklist in `MERGE_READINESS.md` is satisfied

## Execution order
1. ~~Read back and record the pooled extended benchmark result~~ (done: INCONCLUSIVE, 49.8%)
2. Trigger the CodeRabbit review at the final head SHA
3. Re-check `MERGE_READINESS.md` and report the merge verdict
