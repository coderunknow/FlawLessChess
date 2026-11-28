#!/usr/bin/env python3
"""Outcome adjudication for game-loss scanner flags (diagnostic, not evidence).

For every ``queen_trap`` flag: was the flagged quiet reply actually played in
the game, and if so did the mover's queen on ``queen_square`` fall within 5
plies after that reply?  For every ``moved_piece`` flag: did the opponent's
actual reply capture the moved piece at its destination?

Flags are matched to game records by (fen, ply, move) — ``game_index`` repeats
across shards and is never used as a key.  Replays rebuild from ply 0.
"""
import json
import sys

import chess


def captured_square(board: chess.Board, move: chess.Move):
    """Square of the piece ``move`` captures, or None.

    En passant captures the pawn beside the capturing pawn, not on the move's
    ``to_square``: the victim sits on the to-file at the mover's own rank.
    """
    if not board.is_capture(move):
        return None
    if board.is_en_passant(move):
        return chess.square(chess.square_file(move.to_square), chess.square_rank(move.from_square))
    return move.to_square

sys.path.insert(0, "scripts")  # scanner lives in scripts/ (drift-frozen during campaigns)
from analyze_game_losses import scan  # noqa: E402


def adjudicate(path, focus="flawless", min_loss_cp=150):
    result = scan(path, focus, min_loss_cp)
    records = []
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            if raw.strip():
                records.append(json.loads(raw))
    flags = result["flagged"]
    # Source-occurrence identity: (rec ordinal, fen, ply, move). ``game_index``
    # repeats across shards and two transposed games can share (fen, ply, move);
    # the record ordinal within this exact file is unique, so every flag is
    # applied to exactly one source occurrence and never cross-joined.
    by_key = {}
    for f in flags:
        if "error" in f:
            continue
        by_key.setdefault((f.get("rec"), f["fen"], f["ply"], f["move"]), []).append(f)

    qt_played = qt_fell = qt_total = 0
    mp_total = mp_collected = 0
    details = []
    for rec_ordinal, rec in enumerate(records):
        moves = rec.get("moves") or []
        if isinstance(moves, str):
            moves = json.loads(moves.replace("'", '"'))
        is_focus_white = str(rec.get("white", "")).casefold() == focus.casefold()
        board = chess.Board()
        for ply, uci in enumerate(moves):
            key = (rec_ordinal, board.fen(), ply, uci)
            move = chess.Move.from_uci(uci)
            mover_is_focus = (board.turn == chess.WHITE) == is_focus_white
            if mover_is_focus:
                for f in by_key.get(key, ()):
                    if f["kind"] == "queen_trap":
                        qt_total += 1
                        board.push(move)
                        try:
                            reply_move = board.parse_san(f["reply"])
                        except ValueError:
                            reply_move = chess.Move.from_uci(f["reply"])
                        played = ply + 1 < len(moves) and moves[ply + 1] == reply_move.uci()
                        fell = False
                        fell_ply = None
                        if played:
                            qt_played += 1
                            mover = board.turn ^ 1  # mover of the flagged move
                            board.push(reply_move)
                            depth_pushed = 0
                            for k in range(5):
                                if ply + 2 + k >= len(moves):
                                    break
                                nxt = chess.Move.from_uci(moves[ply + 2 + k])
                                # The trap "falls" when the mover's queen is
                                # captured within 5 plies of the reply —
                                # counting the mover's queens anywhere, since
                                # a fleeing queen is usually taken off its
                                # original square.
                                cap_sq = captured_square(board, nxt)
                                cap = (cap_sq is not None
                                       and board.piece_type_at(cap_sq) == chess.QUEEN
                                       and board.color_at(cap_sq) == mover)
                                board.push(nxt)
                                depth_pushed += 1
                                if cap:
                                    fell = True
                                    fell_ply = ply + 2 + k
                                    break
                            for _ in range(depth_pushed):
                                board.pop()
                            board.pop()  # reply
                            board.pop()  # flagged move
                            if fell:
                                qt_fell += 1
                        else:
                            board.pop()  # flagged move
                        details.append({
                            "source": path.split("/")[-2], "game": f["game"],
                            "ply": ply, "opening": f.get("opening"),
                            "reply": f["reply"], "played": played,
                            "fell": fell, "fell_ply": fell_ply,
                            "queen_escapes": f.get("queen_escapes"),
                        })
                    elif f["kind"] == "moved_piece":
                        mp_total += 1
                        if ply + 1 < len(moves):
                            nxt = chess.Move.from_uci(moves[ply + 1])
                            # The reply is played after the flagged move: the
                            # en passant right only exists there, so evaluate
                            # the capture on the post-move position.
                            board.push(move)
                            collected = captured_square(board, nxt) == move.to_square
                            board.pop()
                            if collected:
                                mp_collected += 1
            board.push(move)
    return {
        "source": path, "games": result["games"],
        "queen_trap": {"flags": qt_total, "played": qt_played, "fell": qt_fell},
        "moved_piece": {"flags": mp_total, "collected": mp_collected},
        "details": details,
    }


if __name__ == "__main__":
    out = {}
    for path in sys.argv[1:]:
        r = adjudicate(path)
        out[path] = {k: v for k, v in r.items() if k != "details"}
        print(f"{path.split('/')[-2]}: games={r['games']} "
              f"queen_trap {r['queen_trap']['flags']}/{r['queen_trap']['played']}"
              f"/{r['queen_trap']['fell']} (flags/played/fell)  "
              f"moved_piece {r['moved_piece']['collected']}/{r['moved_piece']['flags']} collected")
        for d in r["details"]:
            print("   ", json.dumps(d))
    if len(sys.argv) > 2:
        with open("/tmp/trap-adjudication.json", "w") as f:
            json.dump(out, f, indent=1)
