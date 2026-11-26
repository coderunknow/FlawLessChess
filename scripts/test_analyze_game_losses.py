#!/usr/bin/env python3
"""Tests for the blunder-scan detectors in ``analyze_game_losses.py``.

The fixtures pin the two detector classes used in the Phase-4 game review:

* ``moved_piece``  -- the mover's move lets the opponent WIN A CAPTURE exchange
  (the registered one-ply SEE; covers plain hanging pieces).
* ``queen_trap``   -- the mover's move allows a QUIET reply that corners the
  queen ("queen cornered/trapped" class): after the reply the queen is attacked
  and every legal queen response still loses material -- or none exists at all.

Fixture geometry (derived, do not simplify away):
* The trap knight must START on d4, not d2: from d2 it could capture the b1
  rook, turning the "quiet" reply into a capture. Knights attacking a1 land on
  b3/c2 -- neither is on the queen's capture lines from a1 -- so the "queen
  captures the attacker" escape needs a b1/a2/b2 attacker instead (the rook
  lift below).
* A black pawn on a2 DEFENDS b1 (pawns capture diagonally), so a white king on
  c2 cannot actually recapture on b1 there. The capture-escape fixture instead
  puts the attacker on c3 (defended by the d2 pawn) and covers b2 with the c1
  pawn.
* Rooks lifting along rank 1 to attack a1 would already attack a1 from their
  start square, so the rook-lift fixture uses the a1-h8 diagonal (bishop b4-c3).
"""

from __future__ import annotations

import unittest

import chess

from analyze_game_losses import (
    _safe_defense_exists,
    material_lost_after,
    queen_traps_after,
)

MIN_LOSS = 150


def _move(uci: str) -> chess.Move:
    return chess.Move.from_uci(uci)


# Black queen a1 is boxed by its own rook b1 and pawns a2/b2: zero legal queen
# moves. White's quiet knight hops d4-c2 / d4-b3 attack the queen over the box.
TRAP_BOXED = "4k3/4p3/8/8/3N4/7K/pp6/qr6 b - - 0 1"
# Same, but b2 is empty: the queen flees to b2 and is safe.
TRAP_ESCAPES = "4k3/4p3/8/8/3N4/7K/p7/qr6 b - - 0 1"
# White's quiet bishop move b4-c3 attacks the queen over the empty b2. The
# queen's responses are Qxc3 (defended by the d2 pawn) and Qb2 (covered by the
# c1 pawn): both lose material. The a2 pawn does not defend c3, and the only
# interposition (Rb2) loses the rook, so no safe defense vetoes the trap.
TRAP_CAPTURE_ESCAPE_DEFENDED = "4k3/4p3/8/8/1B6/7K/p2P4/qrP5 b - - 0 1"
# Black's queen is already hanging to a plain capture (Ra4 x a1): the capture-
# reply detector must flag black's quiet pawn move.
HANGING_QUEEN = "4k3/4p3/8/8/R7/8/6K1/q7 b - - 0 1"
# TRAP_BOXED plus a black knight d4 that safely captures the attacking knight:
# the mechanical defense vetoes the trap flag (the Berlin-class over-flag).
DEFENSE_CAPTURE = "4k3/4p3/8/8/3n4/4N3/pp6/qr6 b - - 0 1"
# Black's queen a1 is attacked on the a-file by Ra5; the black knight c3 can
# interpose on a4, defended by the b5 pawn (Rxa4 bxa4 wins the exchange):
# a safe interposition defense.
DEFENSE_INTERPOSE = "4k3/8/8/Rp6/8/2n5/6K1/q7 b - - 0 1"


class TestBlunderDetectors(unittest.TestCase):
    def test_queen_boxed_by_own_pieces_is_trapped(self) -> None:
        board = chess.Board(TRAP_BOXED)
        traps = queen_traps_after(board, _move("e7e6"), MIN_LOSS)
        self.assertTrue(traps, "boxed queen must be flagged")
        self.assertEqual({t["reply"] for t in traps}, {"Nc2", "Nb3"})
        for t in traps:
            self.assertEqual(t["square"], "a1")
            self.assertEqual(t["queen_escapes"], 0)

    def test_queen_with_safe_escape_is_not_trapped(self) -> None:
        board = chess.Board(TRAP_ESCAPES)
        self.assertEqual(queen_traps_after(board, _move("e7e6"), MIN_LOSS), [])

    def test_capture_escape_that_loses_material_is_trapped(self) -> None:
        board = chess.Board(TRAP_CAPTURE_ESCAPE_DEFENDED)
        traps = queen_traps_after(board, _move("e7e6"), MIN_LOSS)
        self.assertEqual({t["reply"] for t in traps}, {"Bc3"})
        # Qxc3 and Qb2, both losing material
        self.assertEqual(traps[0]["queen_escapes"], 2)

    def test_capture_reply_flag_sees_hanging_queen(self) -> None:
        board = chess.Board(HANGING_QUEEN)
        self.assertGreaterEqual(material_lost_after(board, _move("e7e6")), 900)

    def test_quiet_move_hanging_nothing_is_not_a_moved_piece_flag(self) -> None:
        board = chess.Board(TRAP_BOXED)
        # e7e6 may drop the pawn to Nxe6 (100cp) but nothing worth the 150cp
        # flag threshold: only the quiet-reply trap detector fires.
        self.assertLess(material_lost_after(board, _move("e7e6")), MIN_LOSS)
        self.assertTrue(queen_traps_after(board, _move("e7e6"), MIN_LOSS))

    def test_trap_reply_is_quiet(self) -> None:
        # The trap reply itself is quiet (no capture, no promotion) and corners
        # the queen exactly like the studied rook-lift class.
        board = chess.Board(TRAP_BOXED)
        board.push(_move("e7e6"))
        reply = chess.Move.from_uci("d4c2")
        self.assertIn(reply, board.legal_moves)
        self.assertFalse(board.is_capture(reply))
        self.assertIsNone(reply.promotion)
        board.push(reply)
        self.assertTrue(board.is_attacked_by(chess.WHITE, chess.A1))

    def test_safe_capture_of_attacker_vetoes_trap(self) -> None:
        # Same box as TRAP_BOXED, but the black knight d4 simply takes the
        # attacking knight: a mechanical defense, so no trap flag.
        board = chess.Board(DEFENSE_CAPTURE)
        self.assertEqual(queen_traps_after(board, _move("e7e6"), MIN_LOSS), [])

    def test_safe_interposition_vetoes_trap(self) -> None:
        board = chess.Board(DEFENSE_INTERPOSE)
        self.assertTrue(
            _safe_defense_exists(board, chess.BLACK, chess.A1,
                                 board.attackers(chess.WHITE, chess.A1), MIN_LOSS)
        )


if __name__ == "__main__":
    unittest.main()
