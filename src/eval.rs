//! Classical (handcrafted) evaluation.
//!
//! Design goals: reasonable strength, deterministic, fast, zero allocation, tapered
//! midgame/endgame interpolation, side-to-move relative centipawn output.
//!
//! The `Evaluator` trait is the seam for a future NNUE evaluator (intentionally NOT
//! the default and not implemented in v1).

use crate::attack;
use crate::position::Position;
use crate::types::*;

pub const MATE_SCORE: i32 = 30_000;
pub const INF_SCORE: i32 = 31_000;
pub const DRAW_SCORE: i32 = 0;

pub const PIECE_VALUE_MG: [i32; 6] = [100, 320, 330, 500, 900, 0];
pub const PIECE_VALUE_EG: [i32; 6] = [100, 300, 340, 500, 900, 0];
const PHASE_WEIGHT: [i32; 6] = [0, 1, 1, 2, 4, 0];
const TOTAL_PHASE: i32 = 24;
const TEMPO: i32 = 12;

// Piece-square tables, White's perspective, a1 = 0. Handcrafted for this project.
#[rustfmt::skip]
const PST_PAWN_MG: [i32; 64] = [
     0,  0,  0,  0,  0,  0,  0,  0,
     5, 10, 10,-15,-15, 10, 10,  5,
     5,  5, 10, 20, 20, 10,  5,  5,
     0,  0,  0, 25, 25,  0,  0,  0,
     5, 10, 15, 25, 25, 15, 10,  5,
    15, 20, 25, 30, 30, 25, 20, 15,
    40, 45, 50, 55, 55, 50, 45, 40,
     0,  0,  0,  0,  0,  0,  0,  0,
];
#[rustfmt::skip]
const PST_PAWN_EG: [i32; 64] = [
     0,  0,  0,  0,  0,  0,  0,  0,
    90, 90, 90, 90, 90, 90, 90, 90,
    55, 55, 55, 55, 55, 55, 55, 55,
    35, 35, 35, 35, 35, 35, 35, 35,
    20, 20, 20, 20, 20, 20, 20, 20,
    10, 10, 10, 10, 10, 10, 10, 10,
     5,  5,  5,  5,  5,  5,  5,  5,
     0,  0,  0,  0,  0,  0,  0,  0,
];
#[rustfmt::skip]
const PST_KNIGHT_MG: [i32; 64] = [
   -40,-25,-15,-10,-10,-15,-25,-40,
   -30,-15,  0,  5,  5,  0,-15,-30,
   -20,  0, 10, 15, 15, 10,  0,-20,
   -15,  5, 15, 20, 20, 15,  5,-15,
   -10, 10, 20, 22, 22, 20, 10,-10,
   -15,  5, 15, 20, 20, 15,  5,-15,
   -20,  0, 10, 15, 15, 10,  0,-20,
   -30,-15,-10, -5, -5,-10,-15,-30,
];
#[rustfmt::skip]
const PST_KNIGHT_EG: [i32; 64] = [
   -30,-15,-10,-10,-10,-10,-15,-30,
   -20,-10,  0,  0,  0,  0,-10,-20,
   -10,  0,  5, 10, 10,  5,  0,-10,
   -10,  0, 10, 12, 12, 10,  0,-10,
   -10,  0, 10, 12, 12, 10,  0,-10,
   -10,  0,  5, 10, 10,  5,  0,-10,
   -20,-10,  0,  0,  0,  0,-10,-20,
   -30,-15,-10,-10,-10,-10,-15,-30,
];
#[rustfmt::skip]
const PST_BISHOP_MG: [i32; 64] = [
   -15,-10,-10,-10,-10,-10,-10,-15,
   -10,  0,  0,  0,  0,  0,  0,-10,
   -10,  0,  5, 10, 10,  5,  0,-10,
   -10,  5, 10, 10, 10, 10,  5,-10,
   -10,  0, 10, 10, 10, 10,  0,-10,
   -10, 10, 10, 10, 10, 10, 10,-10,
   -10,  5,  0,  0,  0,  0,  5,-10,
   -15,-10,-10,-10,-10,-10,-10,-15,
];
#[rustfmt::skip]
const PST_BISHOP_EG: [i32; 64] = [
   -15,-10,-10,-10,-10,-10,-10,-15,
   -10,  0,  0,  0,  0,  0,  0,-10,
   -10,  5, 10, 10, 10, 10,  5,-10,
   -10,  5, 15, 15, 15, 15,  5,-10,
   -10,  5, 15, 15, 15, 15,  5,-10,
   -10,  0, 10, 10, 10, 10,  0,-10,
   -10,  5,  0,  0,  0,  0,  5,-10,
   -15,-10,-10,-10,-10,-10,-10,-15,
];
#[rustfmt::skip]
const PST_ROOK_MG: [i32; 64] = [
     0,  0,  2,  5,  5,  2,  0,  0,
     2,  5,  8, 10, 10,  8,  5,  2,
     5,  8, 10, 12, 12, 10,  8,  5,
     5,  8, 10, 12, 12, 10,  8,  5,
     5,  8, 10, 12, 12, 10,  8,  5,
     5,  8, 10, 12, 12, 10,  8,  5,
     8, 12, 15, 18, 18, 15, 12,  8,
    25, 25, 25, 25, 25, 25, 25, 25,
];
#[rustfmt::skip]
const PST_ROOK_EG: [i32; 64] = [
     5,  5,  5,  5,  5,  5,  5,  5,
     5,  8, 10, 10, 10, 10,  8,  5,
     0,  2,  5,  5,  5,  5,  2,  0,
     0,  2,  5,  5,  5,  5,  2,  0,
     0,  2,  5,  5,  5,  5,  2,  0,
     0,  2,  5,  5,  5,  5,  2,  0,
     5,  8, 12, 12, 12, 12,  8,  5,
    10, 12, 15, 15, 15, 15, 12, 10,
];
#[rustfmt::skip]
const PST_QUEEN_MG: [i32; 64] = [
   -10, -5, -2,  0,  0, -2, -5,-10,
    -5,  0,  2,  2,  2,  2,  0, -5,
    -2,  2,  5,  5,  5,  5,  2, -2,
     0,  2,  5,  5,  5,  5,  2,  0,
     0,  2,  5,  5,  5,  5,  2,  0,
    -2,  2,  5,  5,  5,  5,  2, -2,
    -5,  0,  2,  2,  2,  2,  0, -5,
   -10, -5, -2,  0,  0, -2, -5,-10,
];
#[rustfmt::skip]
const PST_QUEEN_EG: [i32; 64] = [
   -10, -5, -2,  0,  0, -2, -5,-10,
    -5,  0,  5,  5,  5,  5,  0, -5,
    -2,  5, 10, 10, 10, 10,  5, -2,
     0,  5, 10, 12, 12, 10,  5,  0,
     0,  5, 10, 12, 12, 10,  5,  0,
    -2,  5, 10, 10, 10, 10,  5, -2,
    -5,  0,  5,  5,  5,  5,  0, -5,
   -10, -5, -2,  0,  0, -2, -5,-10,
];
#[rustfmt::skip]
const PST_KING_MG: [i32; 64] = [
    25, 35, 25,  0, -5,  5, 40, 25,
    20, 25,  5,-15,-20,-10, 15, 15,
    -5, 10,-10,-25,-30,-25, -5, -5,
   -15,-10,-20,-30,-35,-30,-15,-15,
   -25,-20,-30,-35,-40,-35,-25,-25,
   -25,-20,-30,-35,-35,-30,-25,-25,
   -20,-15,-25,-30,-30,-25,-15,-20,
   -10, -5,-15,-20,-15,-20, -5,-10,
];
#[rustfmt::skip]
const PST_KING_EG: [i32; 64] = [
   -55,-35,-25,-15,-15,-25,-35,-55,
   -30,-20,-10,  0,  0,-10,-20,-30,
   -20,-10,  5, 10, 10,  5,-10,-20,
   -10,  0, 10, 15, 15, 10,  0,-10,
    -5,  5, 12, 18, 18, 12,  5, -5,
    -5,  5, 12, 18, 18, 12,  5, -5,
    -10,  0, 10, 15, 15, 10,  0,-10,
   -20,-10,  5, 10, 10,  5,-10,-20,
];

const PST_MG: [&[i32; 64]; 6] = [
    &PST_PAWN_MG,
    &PST_KNIGHT_MG,
    &PST_BISHOP_MG,
    &PST_ROOK_MG,
    &PST_QUEEN_MG,
    &PST_KING_MG,
];
const PST_EG: [&[i32; 64]; 6] = [
    &PST_PAWN_EG,
    &PST_KNIGHT_EG,
    &PST_BISHOP_EG,
    &PST_ROOK_EG,
    &PST_QUEEN_EG,
    &PST_KING_EG,
];

#[inline]
fn mirror_sq(sq: Square) -> Square {
    sq ^ 56
}
const PASSED_MG: [i32; 6] = [0, 10, 20, 38, 65, 100];
const PASSED_EG: [i32; 6] = [0, 25, 45, 80, 140, 220];

fn file_mask(file: i32) -> u64 {
    FILE_A << (file as u64)
}

fn ahead_ranks_mask(us_white: bool, rank: u8) -> u64 {
    let mut m = 0u64;
    if us_white {
        for rr in (rank + 1)..8 {
            m |= RANK_1 << (rr * 8);
        }
    } else {
        for rr in 0..rank {
            m |= RANK_1 << (rr * 8);
        }
    }
    m
}

/// Bitboard of pawns on `pawns` that are passed against `enemy_pawns`.
fn passed_pawn_bits(pawns: u64, enemy_pawns: u64, us_white: bool) -> u64 {
    let mut out = 0u64;
    let mut p = pawns;
    while p != 0 {
        let sq = lsb(p);
        p &= p - 1;
        let f = file_of(sq) as i32;
        let r = rank_of(sq);
        let ahead = ahead_ranks_mask(us_white, r);
        let mut files = file_mask(f);
        if f > 0 {
            files |= file_mask(f - 1);
        }
        if f < 7 {
            files |= file_mask(f + 1);
        }
        if enemy_pawns & files & ahead == 0 {
            out |= 1u64 << sq;
        }
    }
    out
}

#[derive(Default, Clone, Copy)]
pub struct EvalBreakdown {
    pub material: i32,
    pub pst: i32,
    pub mobility: i32,
    pub pawns: i32,
    pub king_safety: i32,
    pub bishop_pair: i32,
    pub rook_file: i32,
    pub space: i32,
    pub tempo: i32,
    pub total: i32,
}

pub trait Evaluator {
    fn evaluate(&mut self, pos: &Position) -> i32;
    fn breakdown(&mut self, pos: &Position) -> EvalBreakdown;
}

#[derive(Default)]
pub struct ClassicalEvaluator;

impl Evaluator for ClassicalEvaluator {
    fn evaluate(&mut self, pos: &Position) -> i32 {
        self.breakdown(pos).total
    }
    fn breakdown(&mut self, pos: &Position) -> EvalBreakdown {
        breakdown(pos)
    }
}

/// Square weights for space evaluation. Higher for central squares, symmetric
/// both horizontally and vertically so that colour mirroring preserves value.
const SPACE_WEIGHT: [i32; 64] = [
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 1, 2, 2, 2, 2, 1, 0, 1, 2, 3, 4, 4, 3, 2, 1,
    1, 2, 3, 4, 4, 3, 2, 1, 0, 1, 2, 2, 2, 2, 1, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
];

struct ColorEval {
    mg: i32,
    eg: i32,
    material: i32,
    pst: i32,
    mobility: i32,
    pawns: i32,
    king_safety: i32,
    bishop_pair: i32,
    rook_file: i32,
    space: i32,
}

fn eval_color(pos: &Position, color: usize, is_white: bool) -> ColorEval {
    let base = color * 6;
    let them = 1 - color;
    let mut out = ColorEval {
        mg: 0,
        eg: 0,
        material: 0,
        pst: 0,
        mobility: 0,
        pawns: 0,
        king_safety: 0,
        bishop_pair: 0,
        rook_file: 0,
        space: 0,
    };
    let mut king_sq: Square = 0;
    let mut bishops = 0u32;

    // material + PST
    for piece in 0..6 {
        let mut bits = pos.pieces[base + piece];
        while bits != 0 {
            let sq = lsb(bits);
            bits &= bits - 1;
            let tsq = if is_white { sq } else { mirror_sq(sq) } as usize;
            out.material += PIECE_VALUE_MG[piece];
            out.pst += PST_MG[piece][tsq];
            out.mg += PIECE_VALUE_MG[piece] + PST_MG[piece][tsq];
            out.eg += PIECE_VALUE_EG[piece] + PST_EG[piece][tsq];
            if piece == BISHOP {
                bishops += 1;
            } else if piece == KING {
                king_sq = sq;
            }
        }
    }

    // mobility
    let own_occ = pos.occ[color];
    let occ = pos.occ_all;
    let mut mob_mg = 0i32;
    let mut mob_eg = 0i32;
    let mut mobility_piece = |_sq: Square, att: u64, per: i32, baseline: i32| {
        let n = popcount(att & !own_occ) as i32 - baseline;
        mob_mg += n * per;
        mob_eg += n * per;
    };
    let mut knights = pos.pieces[base + KNIGHT];
    while knights != 0 {
        let sq = lsb(knights);
        knights &= knights - 1;
        mobility_piece(sq, attack::KNIGHT_ATTACKS[sq as usize], 4, 4);
    }
    let mut bishops_b = pos.pieces[base + BISHOP];
    while bishops_b != 0 {
        let sq = lsb(bishops_b);
        bishops_b &= bishops_b - 1;
        mobility_piece(sq, attack::bishop_attacks(sq, occ), 3, 3);
    }
    let mut rooks_b = pos.pieces[base + ROOK];
    while rooks_b != 0 {
        let sq = lsb(rooks_b);
        rooks_b &= rooks_b - 1;
        mobility_piece(sq, attack::rook_attacks(sq, occ), 2, 5);
    }
    let mut queens_b = pos.pieces[base + QUEEN];
    while queens_b != 0 {
        let sq = lsb(queens_b);
        queens_b &= queens_b - 1;
        mobility_piece(sq, attack::queen_attacks(sq, occ), 1, 9);
    }
    out.mobility = mob_mg;
    out.mg += mob_mg;
    out.eg += mob_eg;

    // pawn structure
    let pawns = pos.pieces[base + PAWN];
    let enemy_pawns = pos.pieces[them * 6 + PAWN];
    let mut pscore_mg = 0i32;
    let mut pscore_eg = 0i32;
    let mut p = pawns;
    while p != 0 {
        let sq = lsb(p);
        p &= p - 1;
        let f = file_of(sq) as i32;
        let mut neighbors = 0u64;
        if f > 0 {
            neighbors |= file_mask(f - 1);
        }
        if f < 7 {
            neighbors |= file_mask(f + 1);
        }
        if pawns & neighbors == 0 {
            pscore_mg -= 12;
            pscore_eg -= 16;
        }
        let ahead = ahead_ranks_mask(is_white, rank_of(sq));
        if pawns & file_mask(f) & ahead != 0 {
            pscore_mg -= 10;
            pscore_eg -= 14;
        }
    }
    let passers = passed_pawn_bits(pawns, enemy_pawns, is_white);
    let mut pp = passers;
    while pp != 0 {
        let sq = lsb(pp);
        pp &= pp - 1;
        let r_idx = (if is_white {
            rank_of(sq)
        } else {
            7 - rank_of(sq)
        }) as usize;
        if r_idx >= 2 {
            pscore_mg += PASSED_MG[r_idx - 1];
            pscore_eg += PASSED_EG[r_idx - 1];
        }
    }
    out.pawns = pscore_mg;
    out.mg += pscore_mg;
    out.eg += pscore_eg;

    // rooks: open/semi-open files, 7th rank
    let mut rfile_mg = 0i32;
    let mut rfile_eg = 0i32;
    let mut rr = pos.pieces[base + ROOK];
    while rr != 0 {
        let sq = lsb(rr);
        rr &= rr - 1;
        let f = file_of(sq) as i32;
        let own_pawn = pawns & file_mask(f) != 0;
        let enemy_pawn = enemy_pawns & file_mask(f) != 0;
        if !own_pawn && !enemy_pawn {
            rfile_mg += 16;
            rfile_eg += 12;
        } else if !own_pawn {
            rfile_mg += 8;
            rfile_eg += 6;
        }
        let on_seventh = if is_white {
            rank_of(sq) == 6
        } else {
            rank_of(sq) == 1
        };
        if on_seventh {
            rfile_mg += 12;
            rfile_eg += 22;
        }
    }
    out.rook_file = rfile_mg;
    out.mg += rfile_mg;
    out.eg += rfile_eg;

    // space: reward control of important squares, especially in the centre.
    // Squares are mirrored for black so the score is colour-symmetric.
    // Space matters more in the middlegame (full weight) than the endgame (half weight).
    let mut space_mg = 0i32;
    let mut space_eg = 0i32;
    let mut add_space = |att: u64| {
        let mut a = att;
        while a != 0 {
            let asq = lsb(a);
            a &= a - 1;
            let w = if is_white {
                SPACE_WEIGHT[asq as usize]
            } else {
                SPACE_WEIGHT[(asq ^ 56) as usize]
            };
            space_mg += w;
            space_eg += w / 2;
        }
    };
    // Pawns
    let mut p = pos.pieces[base + PAWN];
    while p != 0 {
        add_space(attack::pawn_attacks_lookup(color, lsb(p)));
        p &= p - 1;
    }
    // Knights
    let mut n = pos.pieces[base + KNIGHT];
    while n != 0 {
        add_space(attack::KNIGHT_ATTACKS[lsb(n) as usize]);
        n &= n - 1;
    }
    // Bishops
    let mut b = pos.pieces[base + BISHOP];
    while b != 0 {
        add_space(attack::bishop_attacks(lsb(b), occ));
        b &= b - 1;
    }
    // Rooks
    let mut r = pos.pieces[base + ROOK];
    while r != 0 {
        add_space(attack::rook_attacks(lsb(r), occ));
        r &= r - 1;
    }
    // Queens
    let mut q = pos.pieces[base + QUEEN];
    while q != 0 {
        add_space(attack::queen_attacks(lsb(q), occ));
        q &= q - 1;
    }
    // King
    if king_sq != 0 {
        add_space(attack::KING_ATTACKS[king_sq as usize]);
    }
    out.space = space_mg;
    out.mg += space_mg;
    out.eg += space_eg;

    // bishop pair
    if bishops >= 2 {
        out.bishop_pair = 22;
        out.mg += 22;
        out.eg += 44;
    }

    // king safety (midgame only, castled-side kings)
    let kf = file_of(king_sq) as i32;
    let kr = rank_of(king_sq) as i32;
    let home_rank = if is_white { kr <= 2 } else { kr >= 5 };
    if home_rank {
        let mut kscore = 0i32;
        let shield_rank = if is_white { kr + 1 } else { kr - 1 };
        if (0..8).contains(&shield_rank) {
            for df in [-1, 0, 1] {
                let nf = kf + df;
                if !(0..8).contains(&nf) {
                    continue;
                }
                let sq = make_square(nf as u8, shield_rank as u8);
                if pawns & (1u64 << sq) != 0 {
                    kscore += 12;
                } else {
                    kscore -= 18;
                }
            }
        }
        // enemy attack units near our king
        let mut zone = 0u64;
        for df in [-1, 0, 1] {
            for dr in [-1, 0, 1] {
                let nf = kf + df;
                let nr = kr + dr;
                if (0..8).contains(&nf) && (0..8).contains(&nr) {
                    zone |= 1u64 << make_square(nf as u8, nr as u8);
                }
            }
        }
        let ebase = them * 6;
        let mut units = 0i32;
        let mut e = pos.pieces[ebase + KNIGHT];
        while e != 0 {
            let sq = lsb(e);
            e &= e - 1;
            if attack::KNIGHT_ATTACKS[sq as usize] & zone != 0 {
                units += 2;
            }
        }
        let mut e = pos.pieces[ebase + BISHOP] | pos.pieces[ebase + QUEEN];
        while e != 0 {
            let sq = lsb(e);
            e &= e - 1;
            if attack::bishop_attacks(sq, occ) & zone != 0 {
                units += 2;
            }
        }
        let mut e = pos.pieces[ebase + ROOK] | pos.pieces[ebase + QUEEN];
        while e != 0 {
            let sq = lsb(e);
            e &= e - 1;
            if attack::rook_attacks(sq, occ) & zone != 0 {
                units += 3;
            }
        }
        kscore -= units * units / 14 + units * 2;
        out.king_safety = kscore;
        out.mg += kscore;
        out.eg += kscore / 4;
    }

    out
}

pub fn breakdown(pos: &Position) -> EvalBreakdown {
    let mut phase = 0i32;
    for color in 0..2 {
        for (piece, &pw) in PHASE_WEIGHT.iter().enumerate() {
            phase += pw * popcount(pos.pieces[color * 6 + piece]) as i32;
        }
    }
    phase = phase.min(TOTAL_PHASE);

    let w = eval_color(pos, WHITE, true);
    let b = eval_color(pos, BLACK, false);

    let mg = w.mg - b.mg;
    let eg = w.eg - b.eg;
    let tapered = (mg * phase + eg * (TOTAL_PHASE - phase)) / TOTAL_PHASE;
    let total = if pos.side == WHITE { tapered } else { -tapered } + TEMPO;

    EvalBreakdown {
        material: w.material - b.material,
        pst: w.pst - b.pst,
        mobility: w.mobility - b.mobility,
        pawns: w.pawns - b.pawns,
        king_safety: w.king_safety - b.king_safety,
        bishop_pair: w.bishop_pair - b.bishop_pair,
        rook_file: w.rook_file - b.rook_file,
        space: w.space - b.space,
        tempo: TEMPO,
        total,
    }
}
