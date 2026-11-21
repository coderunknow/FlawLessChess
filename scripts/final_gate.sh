#!/usr/bin/env bash
# FlawLessChess final gate: runs every local check against the current HEAD source and records
# the commit, the tree, the release binary hash, each step's return code, and a dirty-tree check.
#
# Usage: scripts/final_gate.sh <out_dir>
# Environment: TOOLCHAIN_ENV (default $HOME/.toolchain/env), PY (default python3 in PATH).
# Writes only under <out_dir>. Exit status: 0 when every step passed and the tree is clean.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 2
OUT="${1:?usage: final_gate.sh <out_dir>}"
mkdir -p "$OUT" || exit 2
SUMMARY="$OUT/summary.txt"
: > "$SUMMARY"
# Interpreter with python-chess (the test oracle). Default: the venv if present, else python3.
PY="${PY:-$( [ -x "$HOME/.venv/bin/python3" ] && echo "$HOME/.venv/bin/python3" || echo python3 )}"
# shellcheck disable=SC1090
source "${TOOLCHAIN_ENV:-$HOME/.toolchain/env}" || { echo "no toolchain env" | tee -a "$SUMMARY"; exit 2; }

FAILS=0
SHA="$(git rev-parse HEAD)"
TREE="$(git rev-parse 'HEAD^{tree}')"
echo "commit $SHA" | tee -a "$SUMMARY"
echo "tree   $TREE" | tee -a "$SUMMARY"
echo "dirty-at-start $(git status --porcelain | wc -l)" | tee -a "$SUMMARY"

step() {
    local name="$1"; shift
    "$@" > "$OUT/$name.log" 2>&1
    local rc=$?
    echo "$name rc=$rc last: $(tail -n 1 "$OUT/$name.log" | cut -c1-150)" >> "$SUMMARY"
    if [ "$rc" -ne 0 ]; then FAILS=$((FAILS + 1)); fi
}

E_REL="$ROOT/target/release/flawless"
E_DBG="$ROOT/target/debug/flawless"

# Static checks and builds
step fmt cargo fmt --all -- --check
step clippy_debug cargo clippy --all-targets --locked -- -D warnings
step clippy_release cargo clippy --release --all-targets --locked -- -D warnings
step build_release cargo build --release --locked
step build_debug cargo build --locked
step sha256_release sha256sum "$E_REL"

# Unit and integration tests (release, then debug with overflow checks)
step test_release cargo test --release --locked
step test_debug cargo test --locked

# Python tooling tests
for t in scripts/test_*.py; do
    step "py_$(basename "$t" .py)" "$PY" "$t"
done

# Perft and legal-move differentials
step perft_random_s10 env FLAWLESS_ENGINE="$E_REL" "$PY" scripts/perft_random_differential.py 10 20 3
step perft_random_s11 env FLAWLESS_ENGINE="$E_REL" "$PY" scripts/perft_random_differential.py 11 20 3
step legal_s31 env FLAWLESS_ENGINE="$E_REL" "$PY" scripts/fuzz_legal_differential.py 31 40
step search_sweep_s4 env FLAWLESS_ENGINE="$E_REL" "$PY" scripts/search_sweep.py 4 40

# UCI protocol, malformed input, extreme arguments, resources
step uci_protocol "$PY" scripts/uci_protocol_probe.py "$E_REL"
step uci_malformed "$PY" scripts/uci_malformed_probe.py "$E_REL"
step uci_extreme_args "$PY" scripts/uci_extreme_args_probe.py "$E_REL"
step uci_grammar_s201 env FLAWLESS_ENGINE="$E_REL" "$PY" scripts/fuzz_uci_grammar.py 201 100
step interleave_s11 "$PY" scripts/fuzz_interleave.py "$E_REL" 25 300 11
step interleave_dbg_s7 "$PY" scripts/fuzz_interleave.py "$E_DBG" 20 300 7
step resource_probe "$PY" scripts/resource_probe.py "$E_REL" 200 1024

# FEN and search correctness probes
step fen_extremes_s101 env FLAWLESS_ENGINE="$E_REL" "$PY" scripts/fuzz_fen_extremes.py 101 400
step fen_extremes_dbg_s9 env FLAWLESS_ENGINE="$E_DBG" "$PY" scripts/fuzz_fen_extremes.py 9 150
step tt_bestmove_s41 "$PY" scripts/tt_bestmove_probe.py "$E_REL" 400 6 41 1
step tt_bestmove_s43 "$PY" scripts/tt_bestmove_probe.py "$E_REL" 400 6 43 64
step searchmoves_s51 "$PY" scripts/searchmoves_probe.py "$E_REL" 300 51 3
step pv_legality_s81 "$PY" scripts/pv_legality_probe.py "$E_REL" 120 5 81
step mate1_s91 "$PY" scripts/mate1_probe.py "$E_REL" 120 91
step multipv_s92 "$PY" scripts/multipv_probe.py "$E_REL" 30 92 4
step negative_mate_s77 "$PY" scripts/negative_mate_probe.py "$E_REL" 12 77

# Clocks and time management
step clock_sweep_s71 "$PY" scripts/clock_sweep_probe.py "$E_REL" 60 71
step time_budget "$PY" scripts/time_budget_probe.py "$E_REL"
step selfplay_1000_sd "$PY" scripts/selfplay_clock_probe.py "$E_REL" 1000 0 200
step selfplay_300_sd "$PY" scripts/selfplay_clock_probe.py "$E_REL" 300 0 200
step selfplay_40_15 "$PY" scripts/selfplay_clock_probe.py "$E_REL" 15000 150 200 40

# Full game with en passant, castling, promotion (python-chess referee)
step fullgame_mt20 "$PY" scripts/fullgame_en_passant_probe.py "$E_REL" --max-plies 400 --movetime-ms 20
step fullgame_mt60 "$PY" scripts/fullgame_en_passant_probe.py "$E_REL" --max-plies 400 --movetime-ms 60

# The checkout must still be the commit and tree we gated, with no local changes (F-37 / review on
# 2fe1118: a clean status alone passes when another commit was checked out during the run).
head_unchanged_at_end() {
    [ "$(git rev-parse HEAD)" = "$SHA" ] || { echo "HEAD moved: $(git rev-parse HEAD) != $SHA"; return 1; }
    [ "$(git rev-parse 'HEAD^{tree}')" = "$TREE" ] || { echo "tree changed"; return 1; }
    [ -z "$(git status --porcelain)" ] || { echo "dirty tree"; git status --porcelain | head -n 5; return 1; }
    echo "head $SHA tree $TREE clean"
}
step head_unchanged_at_end head_unchanged_at_end

echo "FAILS=$FAILS" | tee -a "$SUMMARY"
[ "$FAILS" -eq 0 ]
