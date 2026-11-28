# PR #6 merge-readiness report — 2026-11-28 checkpoint

Branch `arena/247fe7df-flawlesschess`, base `main` = `6ab5b33`. Report head at the
deadline snapshot: `bdc6176` (branch tip is authoritative; each claim names the state it
was verified at).
Deadline context: the mission work window closed at 16:00 (UTC+7) on 2026-11-28 while the
registered ENGINE-4 campaign was still executing on hosted runners. Per the standing
instruction, PR #6 is left **OPEN** and unmerged — no tag, no release.

**VERDICT: `NOT MERGE-READY`.** Not because of any known defect: the registered evidence
campaign and its recovery protocol had not finished, and the absolute rating gate cannot be
computed — or claimed — before that evidence is committed. Every item below states exactly
what is verified and what remains, so the continuation is mechanical.

---

## A. State reconstruction (actual, from GitHub + repository)

- PR #6: OPEN, MERGEABLE, UNSTABLE. Head `1191f1a`; dispatch chain rev 51–57 committed
  (`d7393335…f4a0ba4`); bridge `evidence_out` schema + evidence-request rev 7 (`23d995c`);
  probe v6 marker (`710100e`); Phase E fixes `a9a276c`/`ada9fc2`/`3e7a7d0`; CI suite list +
  seating fixture `c0c6306`; review-debt fix `851bfc2`; docs `5f0f36a`/`1191f1a`.
- Freeze: target commit `cb7242cbb9a88a17e9c1a2b11437a507733e46eb`, ENGINE-4 binary
  `bbf9582db58b1fe8fb0aa8f3675e4bedcc7e62062e8f1fe41de9e6526af0c329`, bench signature
  `849a85bf7e8e1eba` (pinned in anchor-verify.yml). Registered suites A `2c4a54d8a16f36d5…`
  (`benches/rating-openings-batchA.txt`, re-hashed and matched) and B `744a3981cc312a67…`.
  Power assessment `benches/rating-100-power-assessment-e4.json` (`b364e6298d9a9f90…`),
  prospective power 0.80642 (A 0.8553 / B 0.9419 / combined 0.9957) — a design property,
  never a rating.
- Identity discipline: E3 (bench `141943aa23b3fc68`) evidence is never reused for E4; E5
  (queen-trap successor) does not exist in `src/`.
- 51 review threads re-fetched from GitHub; state matches the claims in section E.

## B. ENGINE-4 campaign + recovery (hard gate)

Verified from job-level API state (not run conclusions). **Deadline snapshot (16:00 UTC+7 /
09:00Z; data current to 08:50Z):** the evidence-bridge recovered and committed
run-45999016751's 58 shards (`1072d33`, verified: 58 shards with exactly [31, 37] missing,
232 counted games, identities matching the freeze), and the A/topple recovery dispatch rev
58 was pushed (`bdc6176`, shards 31 [124–127] + 37 [148–151]) with its resolve run queued.
The ladder is fully staged; the campaign itself was still executing at the deadline.

| Batch/anchor | Run | State at 06:44Z | Recovery needed |
|---|---|---|---|
| A / wowl-1.3.7 | 45998977117 | FAILURE; 236 counted games committed at `…/batchA/wowl-1.3.7/run-45998977117/` | slots 124–127 (shard 31) — dispatch rev 57 pushed (`f4a0ba4`), rating-run 46111280732 queued |
| A / topple-0.1.1 | 45999016751 | evidence COMMITTED via bridge (`1072d33`): 58 shards / 232 games, missing [31, 37] | recovery rev 58 pushed (`bdc6176`): shards 31+37 → slots 124–127 + 148–151, resolve run 46124193000 queued |
| A / wyldchess-1.1 | 45999052791 | 59 shards success, shard 17 FAILED, aggregate queued | slots 68–71 after the run resolves (rev 59 template ready) |
| B / wowl-1.3.7 | 45999096409 | 60/60 shards success, aggregate queued | — |
| B / topple-0.1.1 | 45999142482 | running at 08:50Z: 31 in progress / 30 success (≈3.2 h per 4-game shard) | — |
| B / wyldchess-1.1 | 45999195004 | 60 shards queued | — |

Recovery protocol verified end-to-end against `rating-run.yml`: deliberate-dispatch marker
gate (top commit must move `benches/dispatch.json`), `read_committed_runs` missing-slot
recomputation must equal `schedule_indices_by_shard` exactly, prior committed run evidence
required, duplicate counted slots rejected, seat identities enforced per pair leg
(AB/BA). `gh run rerun` is not a permitted recovery path. The three recovery templates sit
in `.arena-drafts/` with push preconditions spelled out. **No aggregate or estimate is
claimed here; `try_merge_confirmatory.py` exit 0 is not treated as completeness.**

## C. Absolute V1 rating gate

**NOT MEASURED** — correctly so: the raw records are incomplete. The tooling is ready and
was dry-run against committed evidence: `scripts/rating_estimator.py gate` with the
registered flags (`--exact-games 240 --required-openings 60 --games-per-opening 4
--suite-a/--suite-b` matching the registered digests, threshold 2000, bootstrap 10000,
seed 20261121 per `benches/gate-plan.json`) fails closed exactly as designed on the
incomplete A/wowl set ("counted games 236 != exact requirement 240"). Both null-control
evidence sets are committed (CTRL-3 topple-0.1.1-vs-topple-0.2.1; CTRL-4 flawless-self-e4).
The gate will run only when all six anchor/batch sets are committed; the decision rule is
unchanged and strict: unrounded `ci95_calibrated[0] > 2000` for Batch A, Batch B and
combined, both controls passing, ≥ 3 eligible anchors per batch, GLS mode, |d| ≤ 400.

## D. Queen-trap defect / ENGINE-5

The shipping engine is E4 and does **not** contain the queen-trap fix — correct under the
source freeze. The fix exists only as `benches/diagnostics/queen-trap-fix.patch` (410 lines,
`b615cec`) with its 13-case regression suite; probes are diagnostic only. Probe v6
(46110985046, `710100e`) is queued behind the campaign and must be read back before Phase D
implementation. ENGINE-5, when implemented, must complete its FULL own chain — binary hash,
anchor verification, controls, screening, own power assessment + independent review +
approval, own confirmatory + rating — before it can replace E4 as a merge candidate. That
chain has not started.

## E. Findings, reviews, tests (verified at `1191f1a`)

- Phase E: all five registered findings fixed with regression suites (paginated `--slurp`
  comment fetch + fixture-dest writes; en-passant captured square; pinned pseudo-attacker
  exclusion via legal-capture validation at all three detector sites; exact source-record
  flag identity `(rec, fen, ply, move)` with the 2-not-4 duplicate regression; engine
  protocol failures abort with exit code 3, child reaped, ply-cap truncation kept distinct).
  Plus the batch A/B colour-pair seating fixture and the reversed `check()` false-greens.
- Test battery: **18/18 suites green** locally at `1191f1a`, every suite output inspected
  (121 + 44 + 17 + 16 + 12 + 7 + … checks). CI now runs all 18 at the exact head.
- Review debt: 5 fixed threads replied with fix evidence and resolved; 1 thread
  (relative_benchmark saved opening-order digest strictness) open by design — `scripts/` is
  drift-frozen while confirmatory recovery dispatches may still be needed; it lands as
  Phase F after campaign close. All ten named review items verified against source.
- Phase H adversarial audit complete (10/10 areas): pruning, legality, TT, qsearch, UCI
  lifecycle, manifests, recovery, estimator, workflow injection (no `${{ }}` in any `run:`
  body), silent failures. Fresh full-diff pass covered src (5 files), workflows (6),
  scripts (23), tests/correctness.rs and the campaign control files field-by-field.

## F. Verdict and the exact remainder

**`NOT MERGE-READY`.** Remaining, in mandatory order (each with its completion evidence):

1. Campaign drain: B/topple + B/wyld shards complete; aggregates commit (or bridges
   commit the completed shards per protocol).
2. A/wowl rev-57 recovery (run 46111280732) plays slots 124–127 and commits `run-<id>`
   evidence; verify by job conclusion AND committed records.
3. A/topple recovery rev 58 (run 46124193000, queued at the deadline) plays shards 31+37
   (slots 124–127 + 148–151) and commits evidence.
4. A/wyld run 45999052791 resolves → dispatch shard-17 recovery rev 59 (68–71) → commit.
5. Every merged set independently re-aggregated; canonical counts = 240/anchor/batch.
6. Phase C gate recomputed from the committed raw records (strict, unrounded) — PASS on all
   three bounds and both controls.
7. Probe v6 read back → ENGINE-5 implemented with its full own chain (or the queen-trap
   defect formally blocking merge).
8. Phase F digest strictness + regression (post-campaign, per thread).
9. Phase I hosted CI green on the exact final head (Ubuntu/Windows/MSRV incl. perft,
   differential, UCI, clock, perf).
10. Fresh independent full-diff review of the final head + review threads resolved;
    docs reconciliation; gate checklist; then this report reissued with the final verdict.

Merge authorization itself is explicitly withheld: per the 2026-11-28 mission instruction
this PR is prepared for an authorized merge and then left open. Nothing in this session
merged, tagged, or released anything.
