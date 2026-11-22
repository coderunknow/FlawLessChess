//! Transposition table.
//!
//! - Zobrist-keyed, depth-preferred replacement with generation aging.
//! - 8-byte entries; power-of-two entry count; aligned u64 access.
//! - Mate scores are stored ply-relative (added on store, subtracted on load).
//! - Scores from subtrees that can reach the fifty-move horizon are flagged CLOCK-UNSAFE
//!   at store time and never reused as bounds. Probe-time halfmove + stored-depth checks also
//!   prevent a low-clock entry from being reused near the horizon; moves remain usable for ordering.

use crate::types::Move;

pub const BOUND_NONE: u8 = 0;
pub const BOUND_EXACT: u8 = 1;
pub const BOUND_LOWER: u8 = 2; // fail-high: true score >= stored score
pub const BOUND_UPPER: u8 = 3; // fail-low:  true score <= stored score

#[derive(Clone, Copy, Default)]
struct Entry {
    key16: u16,
    move16: u16,
    score: i16,
    /// Search depth 0..=127 in bits 0..=6. Bit 7 is the CLOCK-UNSAFE flag: set when the
    /// subtree at store time could reach the fifty-move horizon (store-time halfmove +
    /// remaining depth >= 100). Such scores are halfmove-clock-context-dependent and must
    /// never be reused as a bound — the cached move stays valid for ordering.
    depth: i8,
    bound_gen: u8, // bound(2 bits) | gen(6 bits)
}

const FIFTY_MOVE_HORIZON: i32 = 100;
const DEPTH_VALUE_MASK: u8 = 0x7F;
const CLOCK_UNSAFE_FLAG: u8 = 0x80;

impl Entry {
    fn bound(&self) -> u8 {
        self.bound_gen & 0b11
    }
    fn generation(&self) -> u8 {
        self.bound_gen >> 2
    }
    fn depth_val(&self) -> i32 {
        (self.depth as u8 & DEPTH_VALUE_MASK) as i32
    }
    fn clock_unsafe(&self) -> bool {
        self.depth as u8 & CLOCK_UNSAFE_FLAG != 0
    }
}

/// Parameters for one TT store, bundled to keep the API under clippy's argument budget.
#[derive(Clone, Copy)]
pub struct StoreRequest {
    pub key: u64,
    pub best_move: Option<Move>,
    pub score: i32,
    pub depth: i32,
    pub bound: u8,
    pub ply: i32,
    /// Halfmove clock at store time; decides the CLOCK-UNSAFE flag (fifty-move horizon).
    pub halfmove: u16,
}

#[derive(Clone, Copy)]
pub struct ProbeResult {
    pub best_move: Option<Move>,
    pub score: Option<i32>,
    pub depth: i32,
    pub bound: u8,
}

pub struct TranspositionTable {
    entries: Box<[u64]>,
    len_mask: usize,
    generation: u8,
    pub stores: u64,
    pub probes: u64,
    pub hits: u64,
}

/// The allocator refused a transposition table of `bytes` bytes.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TableAllocError {
    pub bytes: usize,
}

impl std::fmt::Display for TableAllocError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "could not reserve {} bytes", self.bytes)
    }
}

const MATE_BOUND: i32 = crate::eval::MATE_SCORE - 100;

/// Largest power of two that is at most `n` (`n` must be at least 1).
fn prev_power_of_two(n: usize) -> usize {
    1usize << (usize::BITS - 1 - n.leading_zeros())
}

/// Entry count for a requested size in MiB. The count is a power of two (the index is masked),
/// rounded DOWN so the table never holds more than the request (F-40: rounding up made `Hash 65`
/// allocate 128 MiB and `Hash 513` allocate 1 GiB), and clamped to 2^27 entries (1 GiB).
fn table_entries(size_mb: usize) -> usize {
    // Clamp the MiB count BEFORE multiplying: 1 MiB is 2^17 eight-byte entries, and the 1 GiB cap is
    // 2^27 entries = 1024 MiB. On a 32-bit `usize`, `size_mb * 1024 * 1024` overflowed for requests of
    // 4096 MiB and above; the clamped product (at most 2^27) always fits. Requests of 0 MiB count as 1.
    const MAX_MIB: usize = 1024;
    let mib = size_mb.clamp(1, MAX_MIB);
    prev_power_of_two(mib << 17)
}

/// The table size, in MiB, that a requested `Hash` value really allocates. `Hash 100` allocates
/// 64 MiB (F-45): the engine reports this on stdout, so the GUI user sees what was allocated.
pub fn effective_table_mib(size_mb: usize) -> usize {
    table_entries(size_mb) * 8 / (1024 * 1024)
}

/// Allocates `n` zeroed table entries, or reports a refused allocation.
///
/// This is the only `unsafe` in `src/` (test code has one FFI block, see F-18). Its purpose:
/// `std::alloc::alloc_zeroed` returns a null pointer on refusal instead of aborting, and it
/// returns zeroed pages that the OS commits lazily.
///
/// Invariants:
///
/// - `layout` is `Layout::array::<u64>(n)`, so it is valid for `n` entries; `n == 0` never reaches
///   the allocator.
/// - A non-null result points to `layout.size()` bytes, aligned to `align_of::<u64>()`, allocated
///   by the global allocator and zeroed. An all-zero bit pattern is a valid `u64`, so the `n`
///   elements are initialized.
/// - `Box<[u64]>` frees its memory with `Layout::array::<u64>(len)` for the same `len`, which is
///   the layout used here, so the allocation is released with the matching layout.
/// - A null result is checked before the pointer is used. The error path allocates nothing.
///
/// Fallback: on `Err` the caller keeps its current table (see `try_resize`), and `setoption Hash`
/// and start-up halve the size (see `src/uci.rs`).
///
/// Tests: `zeroed_entries_are_zero_and_sized`, `zeroed_entries_reject_impossible_sizes`, and the
/// process test `hash_allocation_refusal_does_not_abort_the_engine`.
///
/// Benchmark: BENCHMARKING.md (first-`go` time and resident memory, before and after this change).
fn zeroed_entries(n: usize) -> Result<Box<[u64]>, TableAllocError> {
    if n == 0 {
        // A zero-size allocation is not valid for `alloc_zeroed` (invariant 1), so no allocation.
        return Ok(Vec::new().into_boxed_slice());
    }
    let bytes = n.saturating_mul(8);
    let layout = std::alloc::Layout::array::<u64>(n).map_err(|_| TableAllocError { bytes })?;
    // SAFETY: see the invariants above. `n >= 1` here, so `layout` has nonzero size. The null
    // check runs before the pointer is used.
    unsafe {
        let ptr = std::alloc::alloc_zeroed(layout) as *mut u64;
        if ptr.is_null() {
            return Err(TableAllocError { bytes });
        }
        Ok(Box::from_raw(std::ptr::slice_from_raw_parts_mut(ptr, n)))
    }
}

impl TranspositionTable {
    pub fn new(size_mb: usize) -> Self {
        let mut tt = TranspositionTable {
            entries: Box::new([]),
            len_mask: 0,
            generation: 1,
            stores: 0,
            probes: 0,
            hits: 0,
        };
        tt.resize(size_mb);
        tt
    }

    pub fn resize(&mut self, size_mb: usize) {
        if let Err(e) = self.try_resize(size_mb) {
            panic!("transposition table allocation failed: {e}");
        }
    }

    /// Like [`TranspositionTable::new`], but reports a refused allocation instead of aborting.
    pub fn try_new(size_mb: usize) -> Result<Self, TableAllocError> {
        let mut tt = TranspositionTable {
            entries: Box::new([]),
            len_mask: 0,
            generation: 1,
            stores: 0,
            probes: 0,
            hits: 0,
        };
        tt.try_resize(size_mb)?;
        Ok(tt)
    }

    /// Resizes the table to `size_mb` MiB. On a refused allocation the table is left unchanged.
    ///
    /// The new table is one fallible zeroed allocation (see `zeroed_entries`). Rust aborts the
    /// process when an allocation fails, so a probe-then-allocate pair would leave a window in
    /// which the second allocation can still abort (F-20). The zeroed allocation keeps the table
    /// lazily zeroed: pages are committed when first written, not at resize.
    pub fn try_resize(&mut self, size_mb: usize) -> Result<(), TableAllocError> {
        let entries = table_entries(size_mb);
        self.entries = zeroed_entries(entries)?;
        self.len_mask = entries - 1;
        // The entries are already zero; only the counters and the generation need resetting.
        // (`clear()` would write every entry and commit every page.)
        self.generation = 1;
        self.stores = 0;
        self.probes = 0;
        self.hits = 0;
        Ok(())
    }

    pub fn clear(&mut self) {
        self.entries.fill(0);
        self.generation = 1;
        self.stores = 0;
        self.probes = 0;
        self.hits = 0;
    }

    /// Called at the start of a new search: age entries into the next generation.
    pub fn new_search(&mut self) {
        self.generation = (self.generation + 1) & 0b111111;
        if self.generation == 0 {
            self.clear();
        }
    }

    #[inline]
    fn pack(e: &Entry) -> u64 {
        (e.key16 as u64)
            | ((e.move16 as u64) << 16)
            | (((e.score as u16) as u64) << 32)
            | (((e.depth as u8) as u64) << 48)
            | ((e.bound_gen as u64) << 56)
    }

    #[inline]
    fn unpack(v: u64) -> Entry {
        Entry {
            key16: (v & 0xFFFF) as u16,
            move16: ((v >> 16) & 0xFFFF) as u16,
            score: ((v >> 32) & 0xFFFF) as u16 as i16,
            depth: ((v >> 48) & 0xFF) as u8 as i8,
            bound_gen: ((v >> 56) & 0xFF) as u8,
        }
    }

    #[inline]
    fn index(&self, key: u64) -> usize {
        (key as usize) & self.len_mask
    }

    #[inline]
    fn adjust_score_to_tt(score: i32, ply: i32) -> i16 {
        let s = if score > MATE_BOUND {
            score + ply
        } else if score < -MATE_BOUND {
            score - ply
        } else {
            score
        };
        s.clamp(i16::MIN as i32, i16::MAX as i32) as i16
    }

    #[inline]
    fn adjust_score_from_tt(score: i16, ply: i32) -> i32 {
        let s = score as i32;
        if s > MATE_BOUND {
            s - ply
        } else if s < -MATE_BOUND {
            s + ply
        } else {
            s
        }
    }

    /// Probe a position at `halfmove`. The clock is not in the Zobrist key, so the score bound
    /// is suppressed if either store-time or probe-time depth can reach the fifty-move horizon.
    /// The best move remains available for ordering when the score is suppressed.
    pub fn probe(&mut self, key: u64, ply: i32, halfmove: u16) -> ProbeResult {
        self.probes += 1;
        let e = Self::unpack(self.entries[self.index(key)]);
        if e.bound() == BOUND_NONE || e.key16 != (key >> 48) as u16 {
            return ProbeResult {
                best_move: None,
                score: None,
                depth: 0,
                bound: BOUND_NONE,
            };
        }
        self.hits += 1;
        let best_move = if e.move16 != 0 {
            Some(Move::from_u16(e.move16))
        } else {
            None
        };
        ProbeResult {
            best_move,
            // A score is reusable only when it was clock-safe where stored AND the probe's
            // own halfmove clock plus the stored depth cannot reach the fifty-move horizon.
            // The Zobrist key excludes the clock, so both contexts must be checked.
            score: if e.clock_unsafe() || halfmove as i32 + e.depth_val() >= FIFTY_MOVE_HORIZON {
                None
            } else {
                Some(Self::adjust_score_from_tt(e.score, ply))
            },
            depth: e.depth_val(),
            bound: e.bound(),
        }
    }

    /// Cheap best-move probe (no stats, for move ordering / PV extraction).
    pub fn probe_move(&self, key: u64) -> Option<Move> {
        let e = Self::unpack(self.entries[self.index(key)]);
        if e.bound() == BOUND_NONE || e.key16 != (key >> 48) as u16 || e.move16 == 0 {
            None
        } else {
            Some(Move::from_u16(e.move16))
        }
    }

    pub fn store(&mut self, req: StoreRequest) {
        let StoreRequest {
            key,
            best_move,
            score,
            depth,
            bound,
            ply,
            halfmove,
        } = req;
        let depth_v = depth.clamp(0, DEPTH_VALUE_MASK as i32);
        // Mark scores whose searched subtree may reach the fifty-move horizon in the store
        // context. Such scores are never reused as bounds. For entries safe at store time,
        // `probe` also checks the probing halfmove clock + stored depth because the clock is
        // excluded from the Zobrist key; a score safe at halfmove 0 can still be unsafe at 98.
        // The best move remains available for ordering in either case.
        let clock_safe = (halfmove as i32 + depth_v) < FIFTY_MOVE_HORIZON;
        let depth_field = (depth_v as u8) | if clock_safe { 0 } else { CLOCK_UNSAFE_FLAG };
        let idx = self.index(key);
        let old = Self::unpack(self.entries[idx]);
        let replace = old.bound() == BOUND_NONE
            || depth_v >= old.depth_val()
            || old.generation() != self.generation;
        if !replace {
            return;
        }
        let entry = Entry {
            key16: (key >> 48) as u16,
            move16: best_move.map(|m| m.to_u16()).unwrap_or(0),
            score: Self::adjust_score_to_tt(score, ply),
            depth: depth_field as i8,
            bound_gen: (bound & 0b11) | ((self.generation & 0b111111) << 2),
        };
        self.entries[idx] = Self::pack(&entry);
        self.stores += 1;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn store_and_probe_roundtrip() {
        let mut tt = TranspositionTable::new(1);
        let key = 0xDEADBEEFCAFEBABEu64;
        tt.store(StoreRequest {
            key,
            best_move: Some(Move::new(12, 28)),
            score: 150,
            depth: 7,
            bound: BOUND_EXACT,
            ply: 0,
            halfmove: 0,
        });
        let p = tt.probe(key, 0, 0);
        assert_eq!(p.score, Some(150));
        assert_eq!(p.depth, 7);
        assert_eq!(p.best_move, Some(Move::new(12, 28)));
    }

    #[test]
    fn mate_scores_are_ply_relative() {
        let mut tt = TranspositionTable::new(1);
        let key = 0x1122334455667788u64;
        tt.store(StoreRequest {
            key,
            best_move: None,
            score: MATE_BOUND + 5,
            depth: 10,
            bound: BOUND_EXACT,
            ply: 10,
            halfmove: 0,
        });
        let p = tt.probe(key, 10, 0);
        assert_eq!(p.score, Some(MATE_BOUND + 5));
        let p_other = tt.probe(key, 3, 0);
        assert_eq!(p_other.score, Some(MATE_BOUND + 5 + 7));
    }

    #[test]
    fn wrong_key_misses() {
        let mut tt = TranspositionTable::new(1);
        tt.store(StoreRequest {
            key: 0xAAAABBBBCCCCDDDDu64,
            best_move: None,
            score: 42,
            depth: 3,
            bound: BOUND_LOWER,
            ply: 0,
            halfmove: 0,
        });
        let p = tt.probe(0xBBBBCCCCDDDDEEEEu64, 0, 0);
        assert_eq!(p.score, None);
    }

    #[test]
    fn clock_unsafe_entries_suppress_score_but_keep_move() {
        let mut tt = TranspositionTable::new(1);
        let key = 0x0102030405060708u64;
        let mv = Move::new(12, 28);
        // halfmove 96 + depth 4 = 100 -> clock-unsafe; score must not be reusable.
        tt.store(StoreRequest {
            key,
            best_move: Some(mv),
            score: 300,
            depth: 4,
            bound: BOUND_EXACT,
            ply: 0,
            halfmove: 96,
        });
        let p = tt.probe(key, 0, 0);
        assert_eq!(p.score, None);
        assert_eq!(p.best_move, Some(mv));
        assert_eq!(p.depth, 4);
        // halfmove 94 + depth 4 = 98 < 100 -> clock-safe; score reusable in any context.
        let mut tt2 = TranspositionTable::new(1);
        tt2.store(StoreRequest {
            key,
            best_move: Some(mv),
            score: 300,
            depth: 4,
            bound: BOUND_EXACT,
            ply: 0,
            halfmove: 94,
        });
        assert_eq!(tt2.probe(key, 0, 0).score, Some(300));
        // Boundary: halfmove 99 + depth 1 = 100 -> unsafe.
        let mut tt3 = TranspositionTable::new(1);
        tt3.store(StoreRequest {
            key,
            best_move: Some(mv),
            score: 300,
            depth: 1,
            bound: BOUND_EXACT,
            ply: 0,
            halfmove: 99,
        });
        assert_eq!(tt3.probe(key, 0, 0).score, None);
    }

    /// A bound stored early in the fifty-move clock is not portable to a probe near the
    /// horizon, even when that entry was safe in its original context (F-54).
    #[test]
    fn clock_safe_store_is_suppressed_when_probe_clock_can_reach_horizon() {
        let mut tt = TranspositionTable::new(1);
        let key = 0xA1B2_C3D4_E5F6_0708u64;
        let mv = Move::new(12, 28);
        tt.store(StoreRequest {
            key,
            best_move: Some(mv),
            score: 275,
            depth: 5,
            bound: BOUND_EXACT,
            ply: 0,
            halfmove: 0,
        });

        // The entry's stored depth cannot reach 100 from 94, but it can from 95.
        assert_eq!(tt.probe(key, 0, 94).score, Some(275));
        for halfmove in [95, 98, 99] {
            let probe = tt.probe(key, 0, halfmove);
            assert_eq!(probe.score, None, "unsafe probe clock {halfmove}");
            assert_eq!(probe.best_move, Some(mv), "move ordering at {halfmove}");
            assert_eq!(probe.depth, 5);
        }
    }

    #[test]
    fn depth_preferred_replacement() {
        let mut tt = TranspositionTable::new(1);
        let key = 0x123456789ABCDEF0u64;
        tt.store(StoreRequest {
            key,
            best_move: None,
            score: 100,
            depth: 5,
            bound: BOUND_EXACT,
            ply: 0,
            halfmove: 0,
        });
        tt.store(StoreRequest {
            key,
            best_move: None,
            score: 200,
            depth: 3,
            bound: BOUND_EXACT,
            ply: 0,
            halfmove: 0,
        }); // shallower, must not replace
        let p = tt.probe(key, 0, 0);
        assert_eq!(p.score, Some(100));
        tt.store(StoreRequest {
            key,
            best_move: None,
            score: 200,
            depth: 6,
            bound: BOUND_EXACT,
            ply: 0,
            halfmove: 0,
        }); // deeper, replaces
        let p = tt.probe(key, 0, 0);
        assert_eq!(p.score, Some(200));
    }
}

#[cfg(test)]
mod mate_score_range_tests {
    use super::*;
    use crate::eval::MATE_SCORE;

    /// R-05: mate scores stored ply-relative must round-trip exactly at the deepest ply
    /// (MAX_PLY = 128). The largest stored magnitude is MATE_SCORE + 128 = 30_128, which
    /// fits in i16; this test pins that invariant so a future constant change cannot clamp
    /// mate scores silently.
    #[test]
    fn mate_scores_round_trip_at_max_ply() {
        const MAX_PLY: i32 = 128;
        assert!(MATE_SCORE + MAX_PLY <= i16::MAX as i32);
        for ply in [0, 1, 64, MAX_PLY - 1] {
            for score in [MATE_SCORE - 1, MATE_SCORE - ply, -(MATE_SCORE - ply)] {
                let stored = TranspositionTable::adjust_score_to_tt(score, ply);
                let back = TranspositionTable::adjust_score_from_tt(stored, ply);
                assert_eq!(back, score, "round trip failed at ply {ply}, score {score}");
            }
        }
    }

    #[test]
    fn stored_mate_probe_returns_exact_score_at_high_ply() {
        let mut tt = TranspositionTable::new(1);
        let key = 0x9E37_79B9_7F4A_7C15u64;
        tt.store(StoreRequest {
            key,
            best_move: None,
            score: MATE_SCORE - 1,
            depth: 5,
            bound: BOUND_EXACT,
            ply: 127,
            halfmove: 0,
        });
        assert_eq!(tt.probe(key, 127, 0).score, Some(MATE_SCORE - 1));
    }

    #[test]
    fn zeroed_entries_are_zero_and_sized() {
        let t = zeroed_entries(4096).expect("4096 entries");
        assert_eq!(t.len(), 4096);
        assert!(t.iter().all(|&v| v == 0));
        assert_eq!(zeroed_entries(0).expect("empty table").len(), 0);
    }

    #[test]
    fn zeroed_entries_reject_impossible_sizes() {
        // 2^61 u64 entries are 2^64 bytes: no Layout exists, so the allocator is never asked.
        assert!(zeroed_entries(1usize << 61).is_err());
    }

    #[test]
    fn try_resize_sets_the_entry_count_and_resets_counters() {
        let mut tt = TranspositionTable::try_new(1).expect("1 MiB");
        assert_eq!(tt.entries.len(), 1024 * 1024 / 8);
        tt.stores = 5;
        tt.hits = 3;
        tt.try_resize(2).expect("2 MiB");
        assert_eq!(tt.entries.len(), 2 * 1024 * 1024 / 8);
        assert_eq!((tt.stores, tt.hits), (0, 0));
        assert!(tt.entries.iter().all(|&v| v == 0));
    }
}

#[cfg(test)]
mod size_tests_f40 {
    use super::*;

    /// F-40: the allocated table never exceeds the requested size, and is at least half of it
    /// (up to the 1 GiB cap). Before the fix, 65 MiB allocated 128 MiB and 513 MiB allocated 1 GiB.
    #[test]
    fn allocated_table_never_exceeds_the_requested_size() {
        for mb in [
            1usize, 2, 3, 16, 33, 64, 65, 100, 129, 500, 513, 1000, 1023, 1024, 4096,
        ] {
            let mut tt = TranspositionTable::try_new(1).expect("1 MiB table");
            tt.try_resize(mb).expect("resize");
            let bytes = tt.entries.len() * 8;
            let want = mb.min(1024) * 1024 * 1024 / 1024 * 1024; // MiB → bytes, capped at 1 GiB
            assert!(bytes <= want, "{mb} MiB requested, {bytes} bytes allocated");
            assert!(
                bytes * 2 > want.min(1 << 30),
                "{mb} MiB requested, only {bytes} bytes allocated"
            );
        }
    }

    #[test]
    fn power_of_two_sizes_are_unchanged() {
        for mb in [1usize, 16, 64, 1024] {
            let mut tt = TranspositionTable::try_new(1).expect("1 MiB table");
            tt.try_resize(mb).expect("resize");
            assert_eq!(tt.entries.len() * 8, mb * 1024 * 1024, "{mb} MiB");
        }
    }

    /// Arithmetic bounds (review, 2026-11-22): extreme requests must not overflow before the cap.
    /// `usize::MAX` MiB is far beyond any `usize` byte count, so an unclamped product would panic in
    /// debug builds on every platform; the clamped count is the 1 GiB cap.
    #[test]
    fn table_entries_clamp_before_multiplying() {
        assert_eq!(table_entries(usize::MAX), 1 << 27);
        assert_eq!(table_entries(4096), 1 << 27);
        assert_eq!(table_entries(1024), 1 << 27);
        assert_eq!(table_entries(0), 1 << 17);
        assert_eq!(effective_table_mib(usize::MAX), 1024);
        // Boundary values around the largest power of two that is at most the request.
        // 3 MiB = 3 * 2^17 entries; the largest power of two below it is 2^18 (2 MiB).
        assert_eq!(table_entries(3), 1 << 18);
        // 1023 MiB rounds down to 512 MiB.
        assert_eq!(table_entries(1023), 1 << 26);
    }

    /// F-45: the size the engine reports is the size it allocates. `Hash 100` is 64 MiB, and the
    /// reported value must agree with the real entry count for every requested size.
    #[test]
    fn effective_table_mib_matches_the_allocation() {
        for (requested, effective) in [
            (1usize, 1usize),
            (2, 2),
            (64, 64),
            (65, 64),
            (100, 64),
            (513, 512),
            (1024, 1024),
        ] {
            assert_eq!(
                effective_table_mib(requested),
                effective,
                "reported size for {requested} MiB"
            );
            if effective <= 128 {
                let mut tt = TranspositionTable::try_new(1).expect("1 MiB table");
                tt.try_resize(requested).expect("resize");
                assert_eq!(
                    tt.entries.len() * 8,
                    effective * 1024 * 1024,
                    "allocation for {requested} MiB"
                );
            }
        }
    }
}
