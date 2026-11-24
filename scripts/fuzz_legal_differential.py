# Usage: FLAWLESS_ENGINE=./target/release/flawless python3 scripts/fuzz_legal_differential.py <seed> <games>
# Requires: pip install chess==1.11.2
"""Differential fuzz: random legal games (python-chess as oracle) vs. flawless `moves` legal-move lists.

Also runs a placement fuzz with both kings present (mutated positions), checking that the engine
never crashes and that every accepted position has exactly python-chess's legal move set when
python-chess considers the position valid.
"""
import os
import random
import subprocess
import sys

import chess

E = os.environ.get("FLAWLESS_ENGINE", "./target/release/flawless")
seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
games = int(sys.argv[2]) if len(sys.argv) > 2 else 40
rnd = random.Random(seed)

fens = []
ep_positions = 0
for g in range(games):
    b = chess.Board()
    for ply in range(300):
        if b.is_game_over(claim_draw=True):
            break
        # Remember en passant positions (en passant right exists after a double push).
        if b.ep_square is not None:
            ep_positions += 1
        fens.append(b.fen())
        moves = list(b.legal_moves)
        # Bias towards captures and pawn moves to reach en passant, castling, promotions.
        weights = []
        for m in moves:
            w = 1.0
            if b.is_capture(m):
                w += 2.0
            if b.piece_type_at(m.from_square) == chess.PAWN:
                w += 1.5
            if b.is_castling(m):
                w += 2.0
            weights.append(w)
        b.push(rnd.choices(moves, weights)[0])

# Placement fuzz: random positions with exactly one king per side, mutated.
PIECES = "PNBRQpnbrq"
for _ in range(max(1, games * 20)):
    board = chess.Board(None)
    board.set_piece_at(rnd.randrange(64), chess.Piece(chess.KING, chess.WHITE))
    k = rnd.randrange(64)
    if board.piece_at(k) is None:
        board.set_piece_at(k, chess.Piece(chess.KING, chess.BLACK))
    for _ in range(rnd.randint(0, 60)):
        sq = rnd.randrange(64)
        if board.piece_at(sq) is None:
            ch = rnd.choice(PIECES)
            pt = {"p": chess.PAWN, "n": chess.KNIGHT, "b": chess.BISHOP, "r": chess.ROOK, "q": chess.QUEEN}[ch.lower()]
            if pt == chess.PAWN and chess.square_rank(sq) in (0, 7):
                continue
            color = chess.WHITE if ch.isupper() else chess.BLACK
            board.set_piece_at(sq, chess.Piece(pt, color))
    board.turn = rnd.choice([chess.WHITE, chess.BLACK])
    board.castling_rights = chess.BB_EMPTY
    board.ep_square = None
    fens.append(board.fen())

inp = "\n".join(fens) + "\n"
p = subprocess.run([E, "moves"], input=inp, capture_output=True, text=True, timeout=1800)
out = p.stdout.splitlines()
print(f"seed={seed} engine exit={p.returncode} lines={len(out)} fens={len(fens)} ep_positions={ep_positions}")
if p.returncode != 0 or len(out) != len(fens):
    print("STDERR:", p.stderr[:800])
    sys.exit(1)

checked = agree = engine_rejected = oracle_invalid = 0
mismatches = []
for fen, line in zip(fens, out):
    board = chess.Board(fen)
    if board.status() != chess.STATUS_VALID:
        oracle_invalid += 1
        if line.startswith("ok"):
            # Engine accepted a position python-chess rejects: record for review.
            mismatches.append(("engine-accepts-oracle-invalid", fen, board.status()))
        continue
    if line.startswith("error"):
        engine_rejected += 1
        # Independent necessary condition for reachability (must hold for any legal game):
        # <=16 pieces per side, <=8 pawns, and promotions needed (excess over the start counts)
        # must not exceed the missing pawns. A rejection is justified only if one of these fails.
        justified = False
        for color in (chess.WHITE, chess.BLACK):
            n = {t: len(board.pieces(t, color)) for t in chess.PIECE_TYPES}
            total = sum(n.values())
            pawns = n[chess.PAWN]
            excess = max(0, n[chess.QUEEN] - 1) + max(0, n[chess.ROOK] - 2) + max(0, n[chess.BISHOP] - 2) + max(0, n[chess.KNIGHT] - 2)
            if total > 16 or pawns > 8 or excess > 8 - pawns:
                justified = True
        if justified:
            justified_rejects = globals().get("justified_rejects", 0) + 1
            globals()["justified_rejects"] = justified_rejects
        else:
            mismatches.append(("engine-rejects-reachable?", fen, line))
        continue
    parts = line.split()
    eng = set(parts[2:])
    ref = {m.uci() for m in board.legal_moves}
    checked += 1
    if eng == ref:
        agree += 1
    else:
        mismatches.append(("move-set", fen, sorted(ref ^ eng)[:6]))

print(f"checked={checked} agree={agree} engine_rejected_valid={engine_rejected} (justified by material bound: {globals().get('justified_rejects', 0)}) oracle_invalid={oracle_invalid}")
for m in mismatches[:15]:
    print("MISMATCH", m)
print("RESULT", "PASS" if not mismatches else f"FAIL ({len(mismatches)})")
sys.exit(0 if not mismatches else 2)
