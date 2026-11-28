# benches/diagnostics/ — engine-defect diagnostics (never strength evidence)

## Trap adjudication, 2026-11-27 (trap-adjudication-2026-11-27.json)

`adjudicate_traps.py` outcome-adjudicates the game-loss scanner's queen-trap
flags: was the flagged quiet reply played, and did the mover's queen fall
within 5 plies?  Flags match game records by (fen, ply, move); replays rebuild
from ply 0.  The adjudicator reproduces the frozen E3 canon exactly
(480-game set 10/6/5, E3-own-360 6/5/4, Catalan ply-33 `Rfb1` the survivor).

ENGINE-4 (720 screening games, 6 sets): queen_trap **28 flags / 13 played /
13 fell** — the class the E3 review flagged as a search target is still open
in ENGINE-4 (`7ba0576` bounded check extensions; quiet-reply awareness was
never implemented).  moved_piece: 534/1612 collected (dest-scoped rule).

Of the 13 falls, 9 were decisive losses (~1.25% of games), 2 draws, 2 wins.
**8/13 are "needle" cases**: 33-49 legal moves and only 1-2 allow the trap —
the engine picks the uniquely trap-allowing move because the quiet refutation
sits beyond capture-only quiescence (the queen's flight moves are quiet, so
qsearch never sees the queen being taken at a flight square).

## trap_cases.json / uci_probe.py / engine-probe.yml

The 13 fall-case FENs with the played (trap-allowing) move and the trap reply.
`engine-probe.yml` builds the frozen engine (optionally with a candidate patch
applied in the runner's working copy — never committed) and probes each case
at fixed depths, committing `probe-<label>.json` here.  The baseline probe
separates time-pressure artifacts from genuine search blindness; a patched
probe must show the engine choosing a different move on the needle cases.

## Fix discipline (2026-11-27)

The confirmatory campaign in flight measures ENGINE-4 `bbf9582d…` from target
`cb7242c`.  The `src/` drift-freeze holds until the gate decision so the
evidence chain stays attached to the shipping head and recovery dispatches
remain possible.  The queen-trap fix is developed here as a verified patch and
applies only after the gate: PASS → ENGINE-4 ships as measured, the fix is the
next engine iteration (ENGINE-5 re-campaign); FAIL → the fix applies at once.
