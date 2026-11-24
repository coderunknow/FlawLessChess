//! Core types shared across the engine. Zero dependencies.
//!
//! Square numbering: a1 = 0, b1 = 1, ..., h1 = 7, ..., h8 = 63.

pub type Square = u8;
pub const A1: Square = 0;
pub const B1: Square = 1;
pub const C1: Square = 2;
pub const D1: Square = 3;
pub const E1: Square = 4;
pub const F1: Square = 5;
pub const G1: Square = 6;
pub const H1: Square = 7;
pub const A8: Square = 56;
pub const H8: Square = 63;
pub const INVALID_SQUARE: Square = 255;

pub const WHITE: usize = 0;
pub const BLACK: usize = 1;

pub const PAWN: usize = 0;
pub const KNIGHT: usize = 1;
pub const BISHOP: usize = 2;
pub const ROOK: usize = 3;
pub const QUEEN: usize = 4;
pub const KING: usize = 5;

pub const PIECE_CHARS: [char; 6] = ['p', 'n', 'b', 'r', 'q', 'k'];
pub const PIECE_NAMES: [&str; 6] = ["pawn", "knight", "bishop", "rook", "queen", "king"];

pub const fn file_of(sq: Square) -> u8 {
    sq & 7
}
pub const fn rank_of(sq: Square) -> u8 {
    sq >> 3
}
pub const fn make_square(file: u8, rank: u8) -> Square {
    rank * 8 + file
}
pub const fn is_valid_square(sq: Square) -> bool {
    sq < 64
}

/// Castling rights bit mask.
pub const CASTLE_WK: u8 = 0b0001;
pub const CASTLE_WQ: u8 = 0b0010;
pub const CASTLE_BK: u8 = 0b0100;
pub const CASTLE_BQ: u8 = 0b1000;

/// Promotion piece kinds (also used as small indices).
pub const PROMO_NONE: u8 = 0;
pub const PROMO_KNIGHT: u8 = 1;
pub const PROMO_BISHOP: u8 = 2;
pub const PROMO_ROOK: u8 = 3;
pub const PROMO_QUEEN: u8 = 4;

pub const fn promo_piece_type(promo: u8) -> usize {
    match promo {
        PROMO_KNIGHT => KNIGHT,
        PROMO_BISHOP => BISHOP,
        PROMO_ROOK => ROOK,
        PROMO_QUEEN => QUEEN,
        _ => PAWN,
    }
}

pub const fn promo_char(promo: u8) -> char {
    match promo {
        PROMO_KNIGHT => 'n',
        PROMO_BISHOP => 'b',
        PROMO_ROOK => 'r',
        PROMO_QUEEN => 'q',
        _ => '?',
    }
}

pub const fn promo_from_char(c: char) -> u8 {
    match c {
        'n' | 'N' => PROMO_KNIGHT,
        'b' | 'B' => PROMO_BISHOP,
        'r' | 'R' => PROMO_ROOK,
        'q' | 'Q' => PROMO_QUEEN,
        _ => PROMO_NONE,
    }
}

/// A pseudo-legal or legal move. Encoded explicitly (no bit packing) for clarity:
/// 4 bytes. Promotion is `PROMO_NONE` for non-promotions.
///
/// Special moves are detected positionally on make/unmake:
/// - pawn double push  : pawn moved |from-to| == 16
/// - en passant capture: pawn moved onto the ep square with empty target
/// - castle            : king moved |from-to| == 2 files
#[derive(Clone, Copy, PartialEq, Eq, Default)]
pub struct Move {
    pub from: Square,
    pub to: Square,
    pub promo: u8,
}

impl Move {
    pub const NULL: Move = Move {
        from: 0,
        to: 0,
        promo: PROMO_NONE,
    };

    pub const fn new(from: Square, to: Square) -> Move {
        Move {
            from,
            to,
            promo: PROMO_NONE,
        }
    }
    pub const fn with_promo(from: Square, to: Square, promo: u8) -> Move {
        Move { from, to, promo }
    }
    /// Pack into u16 for compact TT storage: from(6) | to(6) | promo(3) | spare(1).
    pub const fn to_u16(self) -> u16 {
        (self.from as u16) | ((self.to as u16) << 6) | ((self.promo as u16) << 12)
    }
    pub const fn from_u16(v: u16) -> Move {
        Move {
            from: (v & 0x3f) as Square,
            to: ((v >> 6) & 0x3f) as Square,
            promo: ((v >> 12) & 0x7) as u8,
        }
    }
    /// UCI long algebraic notation, e.g. "e2e4", "e7e8q". `Move::NULL` maps to `0000`.
    pub fn to_uci(self) -> String {
        if self == Move::NULL {
            return "0000".to_string();
        }
        let mut s = String::with_capacity(5);
        s.push((b'a' + file_of(self.from)) as char);
        s.push((b'1' + rank_of(self.from)) as char);
        s.push((b'a' + file_of(self.to)) as char);
        s.push((b'1' + rank_of(self.to)) as char);
        if self.promo != PROMO_NONE {
            s.push(promo_char(self.promo));
        }
        s
    }
    /// Parse a UCI move string; returns None if malformed.
    pub fn from_uci(s: &str) -> Option<Move> {
        let b = s.as_bytes();
        if b.len() < 4 || b.len() > 5 {
            return None;
        }
        let from = make_square(file_char_to_idx(b[0])?, rank_char_to_idx(b[1])?);
        let to = make_square(file_char_to_idx(b[2])?, rank_char_to_idx(b[3])?);
        let promo = if b.len() == 5 {
            promo_from_char(b[4] as char)
        } else {
            PROMO_NONE
        };
        if b.len() == 5 && promo == PROMO_NONE {
            return None;
        }
        Some(Move { from, to, promo })
    }
}

fn file_char_to_idx(c: u8) -> Option<u8> {
    match c {
        b'a'..=b'h' => Some(c - b'a'),
        _ => None,
    }
}
fn rank_char_to_idx(c: u8) -> Option<u8> {
    match c {
        b'1'..=b'8' => Some(c - b'1'),
        _ => None,
    }
}

impl core::fmt::Debug for Move {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        write!(f, "{}", self.to_uci())
    }
}
impl core::fmt::Display for Move {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        write!(f, "{}", self.to_uci())
    }
}
impl PartialOrd for Move {
    fn partial_cmp(&self, other: &Self) -> Option<core::cmp::Ordering> {
        Some(self.cmp(other))
    }
}
impl Ord for Move {
    fn cmp(&self, other: &Self) -> core::cmp::Ordering {
        self.to_u16().cmp(&other.to_u16())
    }
}

/// Capacity of a [`MoveList`].
///
/// Positions are only accepted by `Position::from_fen` when they respect the material limits of a
/// real game (at most 16 pieces per side, at most 8 pawns, and no more promoted pieces than missing
/// pawns; see `position.rs`). Under those limits a side has at most 9 queens and 15 non-king pieces,
/// so the pseudo-legal move count is bounded by 9*27 + 6*14 + 8 = 335 < 512 (queen, rook and king
/// maximum mobility on an empty board). 512 therefore holds every move list the generator can
/// produce for an accepted position.
pub const MOVE_LIST_CAPACITY: usize = 512;

/// Fixed-capacity move list (see [`MOVE_LIST_CAPACITY`] for the sizing argument).
pub struct MoveList {
    pub moves: [Move; MOVE_LIST_CAPACITY],
    pub scores: [i32; MOVE_LIST_CAPACITY],
    pub len: usize,
}

impl Default for MoveList {
    fn default() -> Self {
        Self::new()
    }
}
impl core::fmt::Debug for MoveList {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        f.debug_list()
            .entries(self.moves[..self.len].iter())
            .finish()
    }
}
impl MoveList {
    pub const fn new() -> Self {
        MoveList {
            moves: [Move::NULL; MOVE_LIST_CAPACITY],
            scores: [0; MOVE_LIST_CAPACITY],
            len: 0,
        }
    }
    #[inline]
    pub fn push(&mut self, m: Move) {
        // A hard check (not debug-only): an overflow here would otherwise be a release-mode
        // index panic on the main thread. Unreachable for FENs accepted by `Position::from_fen`.
        assert!(self.len < MOVE_LIST_CAPACITY, "move list overflow");
        self.moves[self.len] = m;
        self.len += 1;
    }
    #[inline]
    pub fn as_slice(&self) -> &[Move] {
        &self.moves[..self.len]
    }
    #[inline]
    pub fn as_mut_slice(&mut self) -> &mut [Move] {
        &mut self.moves[..self.len]
    }
    #[inline]
    pub fn iter(&self) -> core::slice::Iter<'_, Move> {
        self.moves[..self.len].iter()
    }
}

/// Bitboard helpers.
#[inline]
pub const fn bb(sq: Square) -> u64 {
    1u64 << sq
}
#[inline]
pub const fn popcount(b: u64) -> u32 {
    b.count_ones()
}
#[inline]
pub const fn lsb(b: u64) -> Square {
    b.trailing_zeros() as Square
}
#[inline]
pub const fn more_than_one(b: u64) -> bool {
    b & b.wrapping_sub(1) != 0
}

/// File/rank masks
pub const FILE_A: u64 = 0x0101010101010101;
pub const FILE_H: u64 = 0x8080808080808080;
pub const FILE_B: u64 = 0x0202020202020202;
pub const FILE_G: u64 = 0x4040404040404040;
pub const NOT_FILE_A: u64 = !FILE_A;
pub const NOT_FILE_H: u64 = !FILE_H;
pub const RANK_1: u64 = 0x00000000000000ff;
pub const RANK_2: u64 = 0x000000000000ff00;
pub const RANK_7: u64 = 0x00ff000000000000;
pub const RANK_8: u64 = 0xff00000000000000;
pub const LIGHT_SQUARES: u64 = 0x55aa55aa55aa55aa;
pub const DARK_SQUARES: u64 = !LIGHT_SQUARES;
