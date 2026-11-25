#!/usr/bin/env python3
"""Exchange-simulation checks for the game-analysis blame scanner.

`analyze_game_losses.py` flags the plies where a move let the opponent win material across a full
exchange (opponent capture + the mover's best recapture). The one-ply SEE it replaced flagged every
recapturable trade as a loss and missed that the mover's own capture nets out; the opponent-
validated scan of 600+ recorded games showed the flagged material was rarely collectable. These
checks pin the corrected exchange model: clean trades score 0, real hangs score the lost material,
queen-for-pawn counts the deficit, and the scan replays recorded games from the initial position.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import chess

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_game_losses import material_lost_after, scan  # noqa: E402

PASS = 0
FAIL = 0


def check(condition: bool, message: str) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"ok   {message}")
    else:
        FAIL += 1
        print(f"FAIL {message}")


def loss(fen: str, uci: str) -> int:
    board = chess.Board(fen)
    return material_lost_after(board, chess.Move.from_uci(uci))


def main() -> int:
    # 1. Clean queen trade: black Qxf3 takes the white queen, defended by the f1 rook -> net 0.
    trade = "r3k1nr/1pp2p1p/p1p2q2/b5p1/4P3/2P1BQ2/P3NPPP/R4RK1 b kq - 1 13"
    check(loss(trade, "f6f3") == 0, "recapturable queen trade is not a material loss")

    # 2. Queen sac for a pawn: Qxf7+ then Kxf7 -> the mover is down exactly 800.
    hang = "rnbqkbnr/pppp1ppp/8/4p2Q/4P3/8/PPPP1PPP/RNB1KBNR w KQkq - 1 2"
    check(loss(hang, "h5f7") == 800, "queen for pawn reports exactly the 800cp deficit")

    # 3. Quiet developing move -> nothing given away.
    start = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    check(loss(start, "e2e4") == 0, "quiet pawn move loses nothing")

    # 4. Rook takes defended rook: Re1xe4 then Re8xe4 -> equal trade, net 0.
    trade2 = "4r3/8/8/8/4r3/8/8/4KR2 w - - 0 1"
    check(loss(trade2, "e1e4") == 0, "equal recapturable trade is not a material loss")

    # 5. The move hangs its own piece: Rh1-h3 into the c8 bishop's attack, no recapture -> 500.
    hang2 = "2b5/8/8/8/8/8/8/K6R w - - 0 1"
    check(loss(hang2, "h1h3") == 500, "rook hanging to an unrecapturable bishop reports 500")

    # 6. Knight takes defended knight: Nf5xd4 then e3xd4 -> equal trade, net 0.
    trade3 = "7k/8/8/5n2/3N4/4P3/8/K7 b - - 0 1"
    check(loss(trade3, "f5d4") == 0, "knight-for-knight trade is not a material loss")

    # 7. Scan integration from the initial position (scan() replays startpos games):
    #    quiet play flags nothing; the line 1.e4 e5 2.Nf3 Nc6 3.Ng5?? h6 4.Nxf7?? Kxf7
    #    contains two real hangs the scanner must report at their exact plies.
    with tempfile.TemporaryDirectory() as tmp:
        games = Path(tmp) / "games.jsonl"
        quiet = {
            "game_index": 1,
            "white": "flawless",
            "black": "opp",
            "result": "*",
            "opening": "Test",
            "moves": ["e2e4", "a7a6", "g1f3", "a6a5"],
        }
        games.write_text(json.dumps(quiet) + "\n")
        out = scan(str(games), "flawless", 150)
        flagged = [f for f in out["flagged"] if f.get("material_lost_cp", 0) >= 150]
        check(not flagged, "scan flags nothing in a quiet game")

        blunder = {
            "game_index": 2,
            "white": "flawless",
            "black": "opp",
            "result": "*",
            "opening": "Test",
            "moves": ["e2e4", "e7e5", "g1f3", "b8c6", "f3g5", "h7h6", "g5f7"],
        }
        games.write_text(json.dumps(blunder) + "\n")
        out2 = scan(str(games), "flawless", 150)
        hangs = [f for f in out2["flagged"] if f.get("material_lost_cp", 0) >= 150]
        # The line contains two real hangs and the scanner must report both exactly:
        # 4.Ng5?? loses the knight to Qxg5 (d8-g5, unrecapturable) = 320,
        # 5.Nxf7?? Kxf7 is knight for pawn = 220.
        check(
            [(f["move"], f["material_lost_cp"]) for f in hangs] == [("f3g5", 320), ("g5f7", 220)],
            "scan reports both hangs at their exact plies (Ng5 320cp, Nxf7 220cp)",
        )

    print(f"{PASS} checks passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
