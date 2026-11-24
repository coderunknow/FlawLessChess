# Ablation switch (`FLAWLESS_ABLATE`)

Diagnostic mechanism for measuring how much each heuristic of this engine contributes. It is
**not** a user-facing feature and it is **not** a way to weaken the shipped engine: the default
build has it switched off.

## Usage

The engine reads one environment variable at start-up:

```text
FLAWLESS_ABLATE=space,outpost
```

The value is a comma-separated list of term names. Every listed term is disabled in that
process. The variable is read exactly once per process, so a running search cannot change
behaviour half-way through a game.

```bash
# Full engine (default).
./target/release/flawless uci

# Same binary with the space term switched off.
FLAWLESS_ABLATE=space ./target/release/flawless uci

# Two terms at once; unknown names are ignored.
FLAWLESS_ABLATE=space,outpost,typo ./target/release/flawless uci
```

## Terms

| Term          | Effect when disabled                                                     | Location            |
|---------------|--------------------------------------------------------------------------|---------------------|
| `space`       | The `space` evaluation term contributes nothing to the score.            | `src/eval.rs`       |
| `counter_move`| The counter-move heuristic is neither recorded nor used for move order.  | `src/search.rs`     |
| `outpost`     | The `outpost` evaluation term contributes nothing to the score.          | `src/eval.rs`       |

Unknown or empty names are ignored: a typo can never silently disable a different term. The
shipped default (variable unset) disables nothing.

## Design guarantees

* **Default off.** With `FLAWLESS_ABLATE` unset the mask is `0` and every term behaves exactly as
  it does in a normal build. A regression test asserts this
  (`outposts_follow_the_classical_definition_and_are_colour_symmetric`).
* **Process-wide and read once.** The mask is computed once from the environment and cached in a
  `OnceLock`. The evaluation reads one bit mask per side and the search captures it once per
  `Searcher`, so the hot path pays an atomic load and a bit test — never a string comparison.
* **Baseline unaffected.** The pinned baseline commit `6ab5b33` predates this module and ignores
  the variable entirely. A benchmark can therefore hand the same environment to both engines:
  the baseline plays exactly as it always does.
* **Deterministic.** The switch only changes which terms contribute to the score. It never
  changes the search's determinism or the move ordering contract of the remaining heuristics.

## Measuring a term

The relative benchmark harness (`scripts/relative_benchmark.py`) inherits the environment of the
runner, so an ablation run is the same benchmark with one extra variable set:

```bash
# Full candidate versus the pinned baseline.
python scripts/relative_benchmark.py run --profile quick \
  --candidate ./target/release/flawless --baseline ./baseline/flawless \
  --opening-suite benches/openings-20.txt --seed 20261124 \
  --candidate-sha "$CANDIDATE_SHA" --baseline-sha "$BASELINE_SHA" --out bench/full

# Same games, with the space term switched off in the candidate.
FLAWLESS_ABLATE=space python scripts/relative_benchmark.py run --profile quick \
  --candidate ./target/release/flawless --baseline ./baseline/flawless \
  --opening-suite benches/openings-20.txt --seed 20261124 \
  --candidate-sha "$CANDIDATE_SHA" --baseline-sha "$BASELINE_SHA" --out bench/no-space
```

The difference between the two summaries is the measured contribution of the ablated term. The
two runs use the same seed and the same opening suite, so the schedule is identical and the
comparison is paired.

**Ablation output is a diagnostic, not a strength claim.** It says how much a term moves the
score of a fixed opponent pool; it is not a rating, and a term that measures as "important" does
not by itself prove that the engine got stronger with it.

## Source

* `src/ablation.rs` — the switch, the mask, and its unit tests.
* `src/eval.rs` — the `space` and `outpost` terms consult the mask.
* `src/search.rs` — the counter-move heuristic consults the mask.
