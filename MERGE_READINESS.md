# MERGE_READINESS checklist — PR #1 (Flawless V1)

Policy (mission §7): an item is checked ONLY with verifiable evidence. Unmet items stay
unchecked; the mission stays `ACTIVE / INCOMPLETE` until every applicable item is verified.
Never merge/tag/release without explicit user authorization (§9).

Current PR head: see `git log --oneline -1` / `gh pr view 1 --json headRefOid`.

## Correctness & reliability

- [x] Project correctness and reliability audit complete — engine audit pass recorded in
      DESIGN_LOG.md (2026-11-14 adversarial review entry + TT clock-unsafety verification);
      differential perft 76,240 positions 0 mismatches (BENCHMARKING.md / AGENTS_LOG.md);
      full Rust suite 35/35, match.py 104/104, rating_estimator 65/65 at `2e46fc9`
      (evidence-push regression 10/10; ENGINE-1 clock regression included; bench signature
      unchanged fc907eba40b7869f).
- [x] Critical/major findings fixed or technically dispositioned — CodeRabbit review 5903125228
      (13 findings) dispositioned in AGENTS_LOG.md; TT halfmove-clock finding verified FIXED in
      src/tt.rs (clock-safe flag + probe suppression + regression test
      `clock_unsafe_entries_suppress_score_but_keep_move`).
- [x] Regression tests added for repaired defects — TT clock test (src/tt.rs), clock smoke
      (tests/clock_smoke.rs), shard partition + e2e manifest (scripts/test_match.py),
      estimator degenerate-Σ_m + covariances (scripts/test_rating_estimator.py).
- [ ] Full CI matrix green on the exact FINAL head SHA — new sample, recovery and SEE tests have not yet run on the implementation commit; final-head CI remains pending.
- [ ] No known unresolved correctness or security blockers — the earlier audit findings remain dispositioned, but the new SEE ordering candidate and RATING-100 workflow/recovery code still require hosted CI and exact-head review. Prior 5 review findings remain dispositioned; all 5 previously-open PR review
      threads verified against current code, replied with evidence and resolved 2026-11-14:
      covariance-between-anchors = valid/fixed (§9.6–8 + joint-cluster-bootstrap GLS estimator,
      46/46), match.py Windows pipe reader = valid/fixed (reader-thread + Event, no select on
      pipes), search.rs TT halfmove = valid/fixed (src/tt.rs clock-safe flag + probe suppression
      + regression test), uci.rs:433 hold/output race = invalid as described (worker
      hold-check+send and ponderhit clear+try_recv share one flush mutex; proven by analysis and
      locked in by new jittered stress regression
      `ponderhit_or_stop_racing_search_end_emits_exactly_one_bestmove`, 30 trials), uci_smoke
      wait robustness = valid/fixed (post-exit `drain_reader` through channel disconnection +
      full-line panic-marker scan in both tests).

## Rating methodology (docs/RATING_PROTOCOL.md §9)

- [x] Rating methodology fully implemented and independently tested — scripts/rating_estimator.py
      (65/65 re-run locally 2026-11-16) + scripts/aggregate_shards.py + match.py harness v2 (104/104).
- [x] Official anchor provenance verified — CCRL 40/15 list 2026-11-13 captured with HTTP 200,
      3,912,738 bytes, SHA-256 ce365c55b2869502de6addeada4c261d3bd2f50a5a9aef484db9f571aabe15f0;
      uncertainty convention = 95% CI (list text); record in benches/anchor-research-20261114.md.
- [x] ≥3 exact-version anchor binaries rebuilt and hash-verified on hosted runners — 6/6 anchors
      in anchor-verify.yml run 43597866181 (image ubuntu24 20261111.370.1, gcc 13.3.0):
      Wowl 1.3.7, Topple 0.1.1, Topple 0.2.1, akimbo 0.1.1, WyldChess 1.2, WyldChess 1.1.
- [x] Real `benches/anchor-pool.json` frozen and verified — 6 anchors, span 1849–2474, all
      runner SHA-256 + source SHA-256 + licenses + ci95 conventions; passes match.py
      fail-closed schema validation; exclusions recorded with reasons in the pool file.
- [x] SF10 hardware calibration complete — SF10 (official sf_10) bench on ubuntu-24.04 runner:
      3 runs 1998/1984/1996 ms vs i7-4770K reference 2054 ms for 3,939,338 nodes
      (Tors3/CCRL_ScirptsTests ccrl_bench.py) → factor k=1.0291, equivalent TC 40/14.58 min;
      batches play 40/15 wall-clock with the ~3% deviation documented (pool `calibration` block).
- [x] Throughput pilots complete — PILOT-1 (run 43602273258) + duplicate pilot (43603558950)
      both executed and RECOVERED: raw evidence committed via evidence-bridge rev 3
      (run 43683839993 SUCCESS, commit 2ec762e) and independently re-aggregated from the
      original shard artifacts (byte-identical, merged_sha256 aeb4d5a0… / a811d9d1…).
      Throughput re-verified from committed per-game records: 29.43 / 29.53 min/game
      (8-game batch shard ≈ 236 min < 330-min cap). Exploratory only, never gate evidence.
- [ ] Both null controls pass for the gate candidate (ENGINE-1, engine_sha256 9663697d…). CTRL-1 PASS (candidate-independent; −10.32 Elo calibration error within ±75; 240/240 counted). CTRL-2 PASS applies only to the pre-fix binary. CTRL-2-R run 43820392119 completed resolver + 120/120 successful shard jobs, but aggregate-and-commit-evidence was SKIPPED; no self-match estimate is available.
- [ ] Anchor selection finalized on ENGINE-1 candidate — SCREEN-2R remains selection-only (2176.8 / 2236.4 / mean 2206.6). SCREEN-3 run 43820645420 completed resolver + 60/60 successful shard jobs, but aggregate-and-commit-evidence was SKIPPED; no canonical third-anchor estimate or gate plan exists.
- [ ] RATING-100 prospective power gate — BLOCKED. The proposed design is 100 counted games/anchor/batch over 50 disjoint opening clusters; near 2,100 Elo sensitivity power for all three lower-bound decisions is insufficient under reasonable variance stress, and third-anchor / Batch-B covariance is unmeasured. No confirmatory dispatch is permitted until a reviewed, evidence-backed PASS exists.
- [ ] Batch A and Batch B independently pass the strict rating gate — NOT RUN.
- [ ] Combined calibrated 95% CI independently passes — NOT RUN.
- [ ] Every lower bound is strictly greater than 2,000, without rounding — NOT MEASURED.
- [ ] Exactly 100 counted games over 50 registered openings per eligible anchor/batch, committed and reproducible — NOT COLLECTED.
- [ ] Raw tournament evidence committed and reproducible — SCREEN-3 and CTRL-2-R shard artifacts have not been aggregated into canonical evidence; Batch A/B have not been run.

## Reviews & repository integrity

- [ ] CodeRabbit completed review on the exact final head SHA — last substantive review
      5903125228 at f07c4633; manual re-review at final head to be requested (path previously
      rate-limited: "manual review required for this OSS repository").
- [x] All relevant CodeRabbit findings dispositioned — 13/13 of review 5903125228 dispositioned
      (AGENTS_LOG.md) and all 11 of its review threads now carry evidence-based replies and are
      resolved (6 earlier + 5 on 2026-11-14; per-thread dispositions in the checklist above).
      Findings of the pending final-head review will be dispositioned the same way before merge.
- [ ] Documentation and PR description match the final implementation — sample-size amendment, exact-slot recovery and blocked power analysis documented; final-head PR body refresh and review remain pending.
- [ ] All mandatory GitHub branch-protection and review conditions satisfied — verify at merge
      time (repository rules; required checks where permitted, else documented privileged action).
- [ ] PR is no longer a draft and is genuinely ready for review/merge — PR #1 is currently
      **Draft** by policy until every checklist item is verified.

## 2026-11-24 — PR #6 iteration checkpoint (branch `arena/247fe7df-flawlesschess`)

**Verdict for this head: NOT MERGE-READY.** Nothing is technically blocked; the remaining gaps are the
rating gate, the pooled extended benchmark and an independent review, and they are listed below.

What this iteration added and verified:

- [x] Outpost evaluation corrected to the classical definition (White ranks 5-6, Black ranks 3-4, files
      b-g, pawn-defended, safe from an enemy pawn that could step forward to attack) with boundary,
      symmetry, half-board and pawn-direction tests. The previous zone included the opponent's back rank
      and the rank where no enemy pawn can exist, and the term rewarded undefended pieces.
- [x] Tempo semantics resolved and pinned: the score is `+/- tapered + TEMPO` for the side to move, verified
      against the rustc parser source and by a dedicated regression test for both colours and the mirror.
- [x] Local gate suite on the exact head: fmt clean, clippy `-D warnings` clean, `cargo test --release
      --locked` 183/183, difftest 2,321 positions d=2 with 0 mismatches, perft(6) 119,060,324, match harness
      112/112, benchmark suite 20/20.
- [x] Hosted CI on the same head: Ubuntu and Windows format/clippy/test jobs, the MSRV 1.80 job and the
      Windows release artifact job are green, and the quick paired benchmark job completes and publishes its
      summary.
- [x] Relative screening evidence exists and was **read back**: the hosted three-replicate extended profile
      (600 real UCI games, 100 opening clusters) finished **217 W / 164 D / 219 L**, score **49.8%**, relative
      Elo **-23.2 to +21.5** (95% CI), classification **INCONCLUSIVE**. The candidate is **not** measurably
      different from the pinned baseline. Recorded as screening evidence only; it is not a strength claim.
- [ ] **Absolute V1 rating gate: NOT MET.** Still UNKNOWN / NOT MEASURED. The relative screening result above
      is not an absolute rating and cannot be used as one.
- [x] **Pooled extended benchmark.** Dispatched through `benches/benchmark-request.json`, executed and read
      back (see the item above). The result is INCONCLUSIVE, so it does not support a strength claim.
- [ ] **Fresh independent review at the final head SHA** (CodeRabbit or equivalent) has not been performed
      at this head; a review was requested for the previous head and its result has to be read back and
      dispositioned.
- [x] **PR #2 audited read-only** and left untouched: 49 commits, 12,971 insertions, 66 files, draft and
      conflicting with `main`. The two classical outpost conditions that this branch was missing were found
      there and ported into this branch's own implementation; nothing of PR #2 was merged or cherry-picked.
- [ ] PR #6 stays a **draft**. No merge, tag or release has been performed; those require explicit user
      authorization (mission §9).

## Authorization record

- No merge, tag, or release has been performed. Those require explicit user authorization
  separate from merge-readiness (mission §9).

## 2026-11-17 validation checkpoint

The first CI run for the SEE + RATING-100 implementation passed Rust formatting, Clippy and unit tests on Linux and Windows and passed all five Python test suites; both jobs were rejected by the newly added opening-subset verifier. This was a real selector-generation defect, caught before any confirmatory dispatch. Corrected suites, hashes, CI assertions and append-only preregistration/protocol notes are prepared for the next commit. The exact-head CI checklist remains UNCHECKED until both OS jobs pass after that correction.


## 2026-11-17 — exact-head validation (commit 5b63e27)

CI run 44066217195 passed on Ubuntu + Windows + Rust 1.80, including the corrected suite selector, all Python/Rust tests, power smoke, release, UCI and perft checks. Anchor verification run 44066217113 passed 13/13 and recorded the exact source-tree binary SHA-256. This check describes commit 5b63e27; a follow-up commit adds the engine-provenance guard and must receive its own exact-head CI before any readiness item is checked. Fresh CodeRabbit review at the eventual final HEAD remains pending. PR stays Draft.

## 2026-11-17 — provenance test follow-up

The first CI run after adding engine-SHA isolation (44067364552) failed the new power-manifest suite on one overly specific expected-error message; production code rejected the non-SCREEN-2 hash at the earlier allowlist. The test expectation is corrected in the next commit. Exact-head CI remains unchecked until the follow-up run is green. Anchor verification itself passed 13/13.

## 2026-11-17 — Windows newline portability issue

The c564c5c exact-head CI was not green: Ubuntu and MSRV passed, but Windows failed the power-report smoke because of CRLF checkout conversion of committed raw evidence. A targeted cross-platform JSONL hash normalization and tamper test are prepared. Keep full CI unchecked until the follow-up commit is green on Linux and Windows.
