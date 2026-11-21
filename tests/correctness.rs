//! Integration tests: correctness gates for board, hashing, legality, and draws.
//! Run: `cargo test --release` (perft cases) / `cargo test` (logic cases).

use flawless::attack;
use flawless::movegen;
use flawless::position::Position;
use flawless::types::*;

fn rng(seed: &mut u64) -> u64 {
    *seed = seed.wrapping_add(0x9E37_79B9_7F4A_7C15);
    let mut z = *seed;
    z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
    z ^ (z >> 31)
}

#[test]
fn magic_vs_walk_exhaustive() {
    attack::init_attacks();
    if !attack::magic_ready() {
        eprintln!("magic tables unavailable; walker fallback in use");
        return;
    }
    for sq in 0..64 {
        let rm = attack::rook_attacks_walk(sq as Square, 0); // not used; we want masks via public API
        let _ = rm;
    }
    // Recompute masks independently: enumerate every subset of the relevant-ray mask.
    // rook masks: replicate via ray walk differences.
    // We can't access private masks; instead, test magic against walk on EVERY occupancy of the rays
    // by enumerating 2^12 subsets of the full 12-bit relevant zone built from ray squares.
    for sq in 0..64u8 {
        // Build relevant mask by walking rays and excluding the board-edge square.
        let mut mask = 0u64;
        let f = (sq % 8) as i32;
        let r = (sq / 8) as i32;
        for &(df, dr) in &[
            (0i32, 1i32),
            (1, 0),
            (0, -1),
            (-1, 0),
            (1, 1),
            (1, -1),
            (-1, 1),
            (-1, -1),
        ] {
            let mut nf = f + df;
            let mut nr = r + dr;
            while (0..8).contains(&nf) && (0..8).contains(&nr) {
                let next_nf = nf + df;
                let next_nr = nr + dr;
                if (0..8).contains(&next_nf) && (0..8).contains(&next_nr) {
                    mask |= 1u64 << (nr * 8 + nf);
                }
                nf = next_nf;
                nr = next_nr;
            }
        }
        // rook-relevant bits and bishop-relevant bits are disjoint subsets; testing all subsets of
        // the union covers both (walk ignores occ bits off its rays).
        let n = 1usize << mask.count_ones();
        let mut subset: u64 = 0;
        for _ in 0..n {
            let m_rook = attack::rook_attacks(sq, subset);
            let w_rook = attack::rook_attacks_walk(sq, subset);
            assert_eq!(m_rook, w_rook, "rook mismatch sq={sq} occ={subset:#x}");
            let m_bishop = attack::bishop_attacks(sq, subset);
            let w_bishop = attack::bishop_attacks_walk(sq, subset);
            assert_eq!(
                m_bishop, w_bishop,
                "bishop mismatch sq={sq} occ={subset:#x}"
            );
            subset = subset.wrapping_sub(mask) & mask;
        }
    }
}

#[test]
fn fen_roundtrip_canonical() {
    let fens = [
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
        "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
        "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1",
        "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8",
        "8/8/8/8/8/8/8/K6k w - - 0 1",
        "4k3/8/8/8/8/8/8/R3K2R w KQ - 9 17",
    ];
    for f in fens {
        let pos = Position::from_fen(f).unwrap_or_else(|e| panic!("fen {f}: {e}"));
        assert_eq!(pos.to_fen(), f, "roundtrip failed for {f}");
    }
}

#[test]
fn invalid_fens_rejected() {
    for f in [
        "8/8/8/8/8/8/8/K6k w - - x 1", // bad halfmove clock
        "8/8/8/8/8/8/8/K6K w - - 0 1", // two white kings
        "8/8/8/8/8/8/8/k6k w - - 0 1", // two black kings
        "8/8/8/8/8/8/8/8 w - - 0 1",   // no kings
        "8/8/8/8/8/8/8/P7 w - - 0 1",  // pawn on back rank
        "8/8/8/8/8/8/8/K6q x - - 0 1", // bad side
        "8/8/8/8/8/8/8/K6k w X - 0 1", // bad castling char
    ] {
        assert!(Position::from_fen(f).is_err(), "expected rejection: {f}");
    }
}

fn play_and_check_roundtrip(seed: u64, plies: usize) {
    let mut pos = Position::startpos();
    let mut seed = seed;
    for ply in 0..plies {
        let legal = movegen::generate_legal(&mut pos);
        if legal.len == 0 {
            return;
        }
        let snapshot_fen = pos.to_fen();
        let snapshot_hash = pos.hash;
        pos.debug_check_invariants();
        let m = legal.moves[(rng(&mut seed) as usize) % legal.len];
        let undo = pos.make_move(m);
        assert_eq!(
            pos.hash,
            pos.zobrist_full(),
            "hash drift after move {m:?} at ply {ply}"
        );
        pos.debug_check_invariants();
        pos.unmake_move(m, &undo);
        assert_eq!(pos.to_fen(), snapshot_fen, "fen not restored at ply {ply}");
        assert_eq!(pos.hash, snapshot_hash, "hash not restored at ply {ply}");
        pos.debug_check_invariants();
        // now actually make the move to advance the game
        pos.make_move(m);
    }
}

#[test]
fn make_unmake_roundtrip_random() {
    for seed in [1u64, 2, 42, 1337, 99991] {
        play_and_check_roundtrip(seed, 120);
    }
}

#[test]
fn make_unmake_full_game_fens() {
    let mut pos = Position::startpos();
    let moves = [
        "e2e4", "e7e5", "g1f3", "b8c6", "f1b5", "a7a6", "b5a4", "g8f6", "e1g1", "f6e4",
    ];
    for (i, uci) in moves.iter().enumerate() {
        let legal = movegen::generate_legal(&mut pos);
        let m = legal
            .iter()
            .copied()
            .find(|m| m.to_uci() == *uci)
            .unwrap_or_else(|| panic!("move {uci} not legal at ply {i}"));
        let snapshot_fen = pos.to_fen();
        let snapshot_hash = pos.hash;
        let undo = pos.make_move(m);
        pos.unmake_move(m, &undo);
        assert_eq!(pos.to_fen(), snapshot_fen);
        assert_eq!(pos.hash, snapshot_hash);
        pos.make_move(m);
    }
}

#[test]
fn ep_capture_legality_pin() {
    // pinned ep capture must be rejected; unpinned must be allowed
    let mut pos = Position::from_fen("8/8/8/K3Pp1r/8/8/8/4k3 w - f6 0 1").unwrap();
    let legal = movegen::generate_legal(&mut pos);
    assert!(
        !legal.iter().any(|m| m.to_uci() == "e5f6"),
        "pinned ep must be illegal"
    );

    let mut pos = Position::from_fen("8/8/8/K3Pp2/7r/8/8/4k3 w - f6 0 1").unwrap();
    let legal = movegen::generate_legal(&mut pos);
    assert!(
        legal.iter().any(|m| m.to_uci() == "e5f6"),
        "unpinned ep must be legal"
    );
}

#[test]
fn castling_through_check_illegal() {
    // f1 attacked by black rook on f2 -> kingside illegal, queenside legal
    let mut pos = Position::from_fen("4k3/8/8/8/8/8/5r2/R3K2R w KQ - 0 1").unwrap();
    let legal = movegen::generate_legal(&mut pos);
    assert!(
        !legal.iter().any(|m| m.to_uci() == "e1g1"),
        "castling through check must be illegal"
    );
    assert!(
        legal.iter().any(|m| m.to_uci() == "e1c1"),
        "queenside castle must be legal here"
    );
    // rook e2 attacks e1 -> no castling at all
    let mut pos = Position::from_fen("4k3/8/8/8/8/8/4r3/R3K2R w KQ - 0 1").unwrap();
    let legal = movegen::generate_legal(&mut pos);
    assert!(!legal
        .iter()
        .any(|m| m.to_uci() == "e1g1" || m.to_uci() == "e1c1"));
}

#[test]
fn promotion_generation() {
    // white pawn d7 must produce four promotions plus quiet push? d8 empty: d7d8 4 promos + capture on c8? nothing there.
    let mut pos = Position::from_fen("k1r1r3/3P4/8/8/8/8/8/7K w - - 0 1").unwrap();
    let legal = movegen::generate_legal(&mut pos);
    let promos: Vec<String> = legal
        .iter()
        .map(|m| m.to_uci())
        .filter(|s| s.starts_with("d7"))
        .map(|s| s.to_string())
        .collect();
    for want in [
        "d7d8n", "d7d8b", "d7d8r", "d7d8q", "d7c8n", "d7c8b", "d7c8r", "d7c8q", "d7e8n", "d7e8b",
        "d7e8r", "d7e8q",
    ] {
        assert!(
            promos.iter().any(|p| p == want),
            "missing promotion {want}; got {promos:?}"
        );
    }
}

#[test]
fn insufficient_material_table() {
    let cases = [
        ("8/8/8/8/8/8/8/K6k w - - 0 1", true),      // KvK
        ("8/8/8/8/8/8/4B3/K6k w - - 0 1", true),    // K+B v K
        ("8/8/8/8/8/8/4N3/K6k w - - 0 1", true),    // K+N v K
        ("8/8/8/8/8/8/4B3/K6k b - - 0 1", true),    // same
        ("8/8/8/8/8/5b2/4B3/K6k w - - 0 1", true), // K+B v K+B, all bishops same square color => dead
        ("8/8/8/8/8/8/4PP2/K6k w - - 0 1", false), // pawns present
        ("8/8/8/8/8/8/R7/K6k w - - 0 1", false),   // rook present
        ("8/8/8/8/8/8/4N3/K3n2k w - - 0 1", false), // K+N v K+N => helpmate exists => not dead
        ("8/8/8/8/8/6b1/4B3/K6k w - - 0 1", false), // opposite-colored bishops => mate possible
        ("8/8/8/8/8/8/4N3/K3N2k w - - 0 1", false), // K+2N v K => helpmate exists => not dead
    ];
    for (fen, want) in cases {
        let pos = Position::from_fen(fen).unwrap();
        assert_eq!(pos.insufficient_material(), want, "case {fen}");
    }
}

#[test]
fn fifty_move_rule() {
    let pos = Position::from_fen("8/8/8/8/8/8/8/K6k w - - 100 60").unwrap();
    assert!(pos.is_fifty_move());
    let pos = Position::from_fen("8/8/8/8/8/8/8/K6k w - - 99 60").unwrap();
    assert!(!pos.is_fifty_move());
}

#[test]
fn repetition_detection() {
    // 1. Nf3 Nf6 2. Ng1 Ng8 3. Nf3 Nf6 4. Ng1 Ng8 -> position repeated; white to move at move 4 start? after 3...Ng8 it's same as after 1...Nf6? Let's construct from startpos with four knight moves.
    let mut pos = Position::startpos();
    let seq = ["g1f3", "g8f6", "f3g1", "f6g8", "g1f3", "g8f6"];
    for uci in seq {
        let legal = movegen::generate_legal(&mut pos);
        let m = legal.iter().copied().find(|m| m.to_uci() == uci).unwrap();
        pos.make_move(m);
    }
    // startpos has occurred 3 times (at ply 0, after 2...Ng8, and after 4...Ng8? actually after the 6th move we are at move 4 position identical to after move 2)
    assert!(
        pos.repetition_count() >= 1,
        "repetition not detected; count={}",
        pos.repetition_count()
    );
}

#[test]
fn checkmate_and_stalemate_detection() {
    // Fool's mate: after 1. f3 e5 2. g4 Qh4#
    let mut pos = Position::startpos();
    for uci in ["f2f3", "e7e5", "g2g4", "d8h4"] {
        let legal = movegen::generate_legal(&mut pos);
        let m = legal.iter().copied().find(|m| m.to_uci() == uci).unwrap();
        pos.make_move(m);
    }
    assert!(movegen::in_check(&pos));
    assert_eq!(
        movegen::generate_legal(&mut pos).len,
        0,
        "checkmate position must have no legal moves"
    );

    // stalemate: black king h8, white queen g6(?) Actually: 7k/5Q2/6K1/8/8/8/8/8 b - - 0 1 is stalemate
    let mut pos = Position::from_fen("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1").unwrap();
    assert!(!movegen::in_check(&pos));
    assert_eq!(
        movegen::generate_legal(&mut pos).len,
        0,
        "stalemate must have no legal moves"
    );
}

#[test]
fn hash_seed_determinism() {
    // Same FEN -> same hash across processes
    let a =
        Position::from_fen("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1")
            .unwrap();
    let b =
        Position::from_fen("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1")
            .unwrap();
    assert_eq!(a.hash, b.hash);
}

#[test]
fn perft_small_fast() {
    // debug-mode friendly shallow gates; release suite covers the rest
    let mut pos = Position::startpos();
    assert_eq!(movegen::perft(&mut pos, 3), 8902);
}

// ---------- Audit regressions: draw-rule vs checkmate precedence ----------

fn search_score(
    fen: &str,
    depth: i32,
    searchmoves: Option<Vec<&str>>,
) -> flawless::search::SearchResult {
    use flawless::search::{SearchLimits, Searcher};
    use flawless::tt::TranspositionTable;
    use std::sync::atomic::AtomicBool;
    use std::sync::Arc;

    let mut pos = Position::from_fen(fen).unwrap();
    let stop = Arc::new(AtomicBool::new(false));
    let limits = Arc::new(std::sync::Mutex::new(SearchLimits {
        max_depth: depth,
        max_nodes: u64::MAX,
        soft_ms: u64::MAX,
        hard_ms: u64::MAX,
        infinite: false,
        ponder: false,
        fixed_time: false,
        clock_origin: None,
    }));
    let mut tt = TranspositionTable::new(4);
    let moves = searchmoves.map(|v| {
        v.iter()
            .map(|s| flawless::types::Move::from_uci(s).unwrap())
            .collect::<Vec<_>>()
    });
    Searcher::new(&mut tt, &stop, limits).search_root(&mut pos, moves, 1, &mut |_| {})
}

// FIDE: checkmate ends the game immediately — it takes precedence over the
// fifty-move draw (FIDE 9.6.2 makes the 75-move draw non-terminal when the
// last move produced checkmate; mate always stands).
#[test]
fn mate_beats_fifty_move_rule() {
    // Fool's mate final position, white to move, checkmated, halfmove clock 100.
    let result = search_score(
        "rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 100 75",
        1,
        None,
    );
    assert_eq!(
        result.score_cp, -30_000,
        "checkmate must outrank the fifty-move draw"
    );
}

#[test]
fn mate_beats_repetition_rule() {
    let mut pos =
        Position::from_fen("rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 10 10")
            .unwrap();
    pos.history.push(pos.hash); // simulate one earlier occurrence of this exact position
    assert!(pos.is_repetition());
    let stop = std::sync::Arc::new(std::sync::atomic::AtomicBool::new(false));
    let limits = std::sync::Arc::new(std::sync::Mutex::new(flawless::search::SearchLimits {
        max_depth: 1,
        max_nodes: u64::MAX,
        soft_ms: u64::MAX,
        hard_ms: u64::MAX,
        infinite: false,
        ponder: false,
        fixed_time: false,
        clock_origin: None,
    }));
    let mut tt = flawless::tt::TranspositionTable::new(4);
    let result = flawless::search::Searcher::new(&mut tt, &stop, limits).search_root(
        &mut pos,
        None,
        1,
        &mut |_| {},
    );
    assert_eq!(
        result.score_cp, -30_000,
        "checkmate must outrank a repetition draw"
    );
}

// The claimable draw still applies away from mate: non-check, winning material does
// not save the game at 100 halfmoves.
#[test]
fn fifty_move_draw_still_applies_without_mate() {
    let result = search_score("r7/8/8/8/8/5k2/8/6K1 w - - 100 75", 2, None);
    assert_eq!(
        result.score_cp, 0,
        "non-mated position at halfmove 100 scores as a draw"
    );
}

// Stalemate is a draw — never a fail-high of an enclosing search node.
#[test]
fn stalemate_root_scores_draw() {
    // Black to move: Kh8 stalemated by Kf7 and Qg6 (not in check).
    let result = search_score("7k/5K2/6Q1/8/8/8/8/8 b - - 0 1", 4, None);
    assert_eq!(
        result.score_cp, 0,
        "stalemate must score 0, not a mate or a fail-high cp"
    );
}

// go searchmoves must restrict the MultiPV=1 root search as well.
#[test]
fn searchmoves_restricts_root_search() {
    let a = search_score(
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        5,
        Some(vec!["h2h3"]),
    );
    assert_eq!(
        a.best_move.to_uci(),
        "h2h3",
        "search must honor the restricted root move set"
    );
    // sanity: unrestricted search does not pick h2h3 at depth 5 on this engine build
    let b = search_score(
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        5,
        None,
    );
    assert_ne!(
        b.best_move.to_uci(),
        "h2h3",
        "sanity anchor for the searchmoves restriction test"
    );
}

#[test]
fn searchmoves_empty_falls_back_to_all_legal() {
    // Some(empty) is normalized by the UCI layer; the API's None means "all legal moves".
    let result = search_score(
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        1,
        None,
    );
    assert_ne!(result.best_move.to_uci(), "0000");
}

// ---------- Audit regressions: clock handling ----------

#[test]
fn clock_limits_never_panics_at_zero_time() {
    use flawless::uci::clock_limits;
    // t = 0 (flagged on time) must not hit u64::clamp(min > max) and must keep soft <= hard.
    let (soft, hard) = clock_limits(WHITE, 0, 0, 0, 0, None);
    assert!(soft <= hard);
    let (soft, hard) = clock_limits(BLACK, 0, 0, 0, 0, Some(0));
    assert!(soft <= hard);
    let (soft, hard) = clock_limits(WHITE, 10, 10, 0, 0, Some(1));
    assert!(soft <= hard);
    // normal case: soft < hard and hard within the budget
    let (soft, hard) = clock_limits(WHITE, 60_000, 60_000, 1_000, 1_000, None);
    assert!(soft <= hard && hard <= 60_000 - 30 + 1);
}

// ---------- Perft reference matrix (Chess Programming Wiki "Perft Results") ----------
// Node counts are the published CPW values. Release-mode gates (perft is slow in debug builds).

fn perft_of(fen: Option<&str>, depth: u32) -> u64 {
    let mut pos = match fen {
        Some(f) => Position::from_fen(f).expect("reference FEN"),
        None => Position::startpos(),
    };
    movegen::perft(&mut pos, depth)
}

#[test]
#[cfg_attr(debug_assertions, ignore = "perft gate: run with --release")]
fn perft_startpos_reference() {
    assert_eq!(perft_of(None, 1), 20);
    assert_eq!(perft_of(None, 2), 400);
    assert_eq!(perft_of(None, 3), 8_902);
    assert_eq!(perft_of(None, 4), 197_281);
}

#[test]
#[cfg_attr(debug_assertions, ignore = "perft gate: run with --release")]
fn perft_kiwipete_reference() {
    let f = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1";
    assert_eq!(perft_of(Some(f), 1), 48);
    assert_eq!(perft_of(Some(f), 2), 2_039);
    assert_eq!(perft_of(Some(f), 3), 97_862);
}

#[test]
#[cfg_attr(debug_assertions, ignore = "perft gate: run with --release")]
fn perft_cpw_position_3_reference() {
    // Pawn/en-passant/discovered-check heavy endgame.
    let f = "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1";
    assert_eq!(perft_of(Some(f), 1), 14);
    assert_eq!(perft_of(Some(f), 2), 191);
    assert_eq!(perft_of(Some(f), 3), 2_812);
    assert_eq!(perft_of(Some(f), 4), 43_238);
}

#[test]
#[cfg_attr(debug_assertions, ignore = "perft gate: run with --release")]
fn perft_cpw_position_4_reference() {
    // Promotions, castling through/into check, and pins.
    let f = "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1";
    assert_eq!(perft_of(Some(f), 1), 6);
    assert_eq!(perft_of(Some(f), 2), 264);
    assert_eq!(perft_of(Some(f), 3), 9_467);
}

#[test]
#[cfg_attr(debug_assertions, ignore = "perft gate: run with --release")]
fn perft_cpw_position_5_reference() {
    let f = "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8";
    assert_eq!(perft_of(Some(f), 1), 44);
    assert_eq!(perft_of(Some(f), 2), 1_486);
    assert_eq!(perft_of(Some(f), 3), 62_379);
}

#[test]
#[cfg_attr(debug_assertions, ignore = "perft gate: run with --release")]
fn perft_cpw_position_6_reference() {
    let f = "r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10";
    assert_eq!(perft_of(Some(f), 1), 46);
    assert_eq!(perft_of(Some(f), 2), 2_079);
    assert_eq!(perft_of(Some(f), 3), 89_890);
}

// ---------- Material limits (AUDIT-FEN-01) ----------

#[test]
fn fen_rejects_material_that_no_game_can_reach() {
    // 22 queens + 2 rooks + 2 bishops + king: 27 white pieces, far above the 16-piece limit.
    let too_many = "KQQQQQBk/Q5RB/Q6Q/Q6Q/Q6Q/Q6Q/Q1QQ3Q/QR3QQQ w - - 0 1";
    let err = Position::from_fen(too_many)
        .err()
        .expect("27 white pieces were not rejected");
    assert!(err.contains("impossible material"), "{err}");
    // 9 white pawns.
    let err = Position::from_fen("4k3/PPPPPPPP/P7/8/8/8/8/4K3 w - - 0 1")
        .err()
        .expect("9 pawns");
    assert!(err.contains("impossible material"), "{err}");
    // 9 queens with one pawn: eight promotions are needed but only seven pawns are missing.
    let err = Position::from_fen("4k3/8/8/QQQQQQQQ/Q7/8/P7/K7 w - - 0 1")
        .err()
        .expect("nine queens with one pawn accepted");
    assert!(err.contains("impossible material"), "{err}");
}

#[test]
fn fen_accepts_promoted_piece_counts_that_are_reachable() {
    // Three extra queens with seven missing pawns: reachable.
    assert!(Position::from_fen("4k3/8/8/8/8/8/P7/QQQQ1K2 w - - 0 1").is_ok());
    // Nine queens and no pawns: all eight pawns promoted.
    let nine = "k7/8/8/8/8/8/QQQQQQQQ/K6Q b - - 0 1";
    let pos = Position::from_fen(nine).expect("nine queens reachable by promotion");
    assert_eq!(pos.pieces[WHITE * 6 + QUEEN].count_ones(), 9);
    assert_eq!(pos.pieces[WHITE * 6 + PAWN], 0);
}

#[test]
fn move_list_capacity_covers_maximum_mobility_of_accepted_positions() {
    // A high-mobility position accepted by the material rules: 211 pseudo-legal moves for White.
    let fen = "rR5Q/k1N1Q3/b1Q3Q1/3Q4/5Q2/R6Q/4Q3/BQ1NB1K1 w - - 0 1";
    let pos = Position::from_fen(fen).expect("accepted high-mobility position");
    let n = movegen::generate_pseudo_legal(&pos).len;
    assert!(n > 200, "test position lost its mobility: {n}");
    assert!(n < MOVE_LIST_CAPACITY, "{n} pseudo-legal moves");
    let mut p = pos.clone();
    assert!(movegen::generate_legal(&mut p).len <= n);
}

// ---------- Castling rights vs. placement (AUDIT-FEN-02) ----------
// The FEN castling field is not cross-checked against the placement. These tests pin the
// observable contract: stale rights never produce a castling move, and correct rights do.

fn castle_moves_for(fen: &str) -> Vec<String> {
    let mut pos = Position::from_fen(fen).expect("fen accepted");
    movegen::generate_legal(&mut pos)
        .iter()
        .map(|m| m.to_uci())
        .filter(|u| u == "e1g1" || u == "e1c1" || u == "e8g8" || u == "e8c8")
        .collect()
}

#[test]
fn stale_castling_rights_without_rooks_generate_no_castling() {
    assert!(castle_moves_for("4k3/8/8/8/8/8/8/4K3 w KQkq - 0 1").is_empty());
    assert!(castle_moves_for("4k3/8/8/8/8/8/8/R3K3 w KQ - 0 1")
        .iter()
        .all(|m| m != "e1g1"));
    assert!(castle_moves_for("4k3/8/8/8/8/8/8/R3K3 w Q - 0 1").contains(&"e1c1".to_string()));
}

#[test]
fn castling_rights_with_rooks_generate_exactly_the_castles() {
    let both = castle_moves_for("4k3/8/8/8/8/8/8/R3K2R w KQ - 0 1");
    assert!(both.contains(&"e1g1".to_string()) && both.contains(&"e1c1".to_string()));
    assert_eq!(
        castle_moves_for("4k3/8/8/8/8/8/8/R3K2R w K - 0 1"),
        vec!["e1g1".to_string()]
    );
    assert_eq!(
        castle_moves_for("4k3/8/8/8/8/8/8/R3K2R w Q - 0 1"),
        vec!["e1c1".to_string()]
    );
    assert!(castle_moves_for("4k3/8/8/8/8/8/8/R3K2R w - - 0 1").is_empty());
}

#[test]
fn castling_right_is_ignored_when_king_is_off_its_home_square() {
    // King on f1 with a K right: no castling move may be generated from f1.
    let moves = castle_moves_for("4k3/8/8/8/8/8/8/R4K1R w K - 0 1");
    assert!(moves.is_empty(), "{moves:?}");
}

// ---------- Checkers against the side to move (AUDIT-FEN-03) ----------
// Found by differential fuzzing against python-chess: the engine accepted positions in which the
// side to move was in check from two sliders on one line with its king between them, and from
// three pieces. Neither can occur in a legal game.

#[test]
fn fen_rejects_two_checkers_on_one_line_through_the_king() {
    // Black queens on d5 and h1 both check Kf3 along the d5-h1 diagonal.
    let err = Position::from_fen("1b4NQ/8/7R/3q4/3P1bn1/3k1K1P/3p4/2B1bN1q w - - 0 1")
        .err()
        .expect("aligned double check accepted");
    assert!(err.contains("two checkers on one line"), "{err}");
}

#[test]
fn fen_rejects_more_than_two_checkers() {
    let err = Position::from_fen("3Q1N1R/NK5q/p7/nq6/R4rQ1/6Q1/1N4Qr/1k6 w - - 0 1")
        .err()
        .expect("three checkers accepted");
    assert!(err.contains("more than two checkers"), "{err}");
}

#[test]
fn fen_accepts_a_legal_double_check_from_knight_and_queen() {
    // Queen d2 and knight g2 both check Ke1 (checkers d2 and g2, not on one line through the king).
    let mut pos =
        Position::from_fen("4k3/8/8/8/8/8/3q2n1/4K3 w - - 0 1").expect("legal double check");
    let legal = movegen::generate_legal(&mut pos);
    let mut moves: Vec<String> = legal.iter().map(|m| m.to_uci()).collect();
    moves.sort();
    assert_eq!(moves, vec!["e1d2", "e1f1"]);
}

// ---------- Evaluation colour symmetry (AUDIT-EVAL-01) ----------
// The static evaluation, seen from the side to move, must be identical for a position and its
// colour mirror (ranks flipped, colours and side swapped). tests/data/eval_symmetry_fens.tsv holds
// 303 such pairs generated with python-chess `Board.mirror()`; the last two are positions where a
// depth-4 search scored a mirror pair differently (the search is not symmetric by design: null
// move, LMR and move-order ties; the static evaluation must still be).

#[test]
fn static_evaluation_is_colour_symmetric() {
    use flawless::eval::{ClassicalEvaluator, Evaluator};
    let data = include_str!("data/eval_symmetry_fens.tsv");
    let mut ev = ClassicalEvaluator;
    let mut pairs = 0;
    for line in data
        .lines()
        .filter(|l| !l.starts_with('#') && !l.trim().is_empty())
    {
        let (fen, mirror) = line.split_once('\t').expect("tab-separated pair");
        let a = Position::from_fen(fen).expect("fen");
        let b = Position::from_fen(mirror).expect("mirror fen");
        let (ea, eb) = (ev.evaluate(&a), ev.evaluate(&b));
        assert_eq!(
            ea, eb,
            "eval asymmetry: {fen} -> {ea}, mirror {mirror} -> {eb}"
        );
        pairs += 1;
    }
    assert!(pairs >= 300, "only {pairs} pairs checked");
}

// ---------------------------------------------------------------------------------------------
// Search regressions (S-08 node cap, S-14 colour symmetry). Library-level, deterministic.
// ---------------------------------------------------------------------------------------------

/// Runs one fresh search (new table, new searcher) and returns (score, nodes spent).
fn fresh_search(fen: &str, max_depth: i32, max_nodes: u64) -> (i32, u64, Move) {
    use flawless::search::{SearchLimits, Searcher};
    use flawless::tt::TranspositionTable;
    use std::sync::atomic::AtomicBool;
    use std::sync::{Arc, Mutex};
    attack::init_attacks();
    let mut pos = Position::from_fen(fen).expect("fen");
    let mut tt = TranspositionTable::new(16);
    let stop = AtomicBool::new(false);
    let limits = SearchLimits {
        max_depth,
        max_nodes,
        ..SearchLimits::default()
    };
    let mut s = Searcher::new(&mut tt, &stop, Arc::new(Mutex::new(limits)));
    let r = s.search_root(&mut pos, None, 1, &mut |_| {});
    (r.score_cp, s.nodes(), r.best_move)
}

/// Regression (S-14): a position and its colour mirror must search to the same score. Before the
/// colour-relative move ordering, these 11 recorded pairs differed (6 of 120 positions at depth 4
/// with seed 2026; 5 of 60 at depth 5 with seed 2027). Each mirror was checked with python-chess.
#[test]
fn search_scores_are_colour_symmetric_on_recorded_pairs() {
    let data = include_str!("data/search_symmetry_pairs.tsv");
    let mut pairs = 0;
    for line in data
        .lines()
        .filter(|l| !l.starts_with('#') && !l.trim().is_empty())
    {
        let cols: Vec<&str> = line.split('\t').collect();
        assert_eq!(cols.len(), 3, "malformed fixture row: {line}");
        let depth: i32 = cols[0].parse().expect("depth");
        let (a, _, _) = fresh_search(cols[1], depth, u64::MAX);
        let (b, _, _) = fresh_search(cols[2], depth, u64::MAX);
        assert_eq!(
            a, b,
            "search asymmetry at depth {depth}: {} -> {a}, mirror {} -> {b}",
            cols[1], cols[2]
        );
        pairs += 1;
    }
    assert_eq!(pairs, 11, "fixture must hold the 11 recorded pairs");
}

/// Regression (S-08): the node cap is spent exactly. The cap used to be checked every 1024
/// nodes, so `go nodes 1` searched 1024 nodes and small caps overshot. The count returned
/// by the searcher must equal the cap for every cap that the search can reach.
#[test]
fn node_cap_is_spent_exactly() {
    for &cap in &[1u64, 2, 100, 1000, 5000, 20000] {
        for fen in [
            "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
        ] {
            let (_, nodes, best) = fresh_search(fen, 64, cap);
            assert_eq!(nodes, cap, "cap {cap} on {fen}: searched {nodes} nodes");
            assert_ne!(best, Move::NULL, "cap {cap}: no move returned on {fen}");
        }
    }
}

/// Invariant sweep for the piece bitboards. `Position::piece_on` ends in `unreachable!` if the
/// occupancy bitboards and the per-piece bitboards disagree, so this walks random legal games
/// (make and unmake) and checks, on every ply, that each occupied square has exactly one piece,
/// that `occ` and `occ_all` agree with `pieces`, and that `piece_on` answers for every square.
#[test]
fn piece_bitboards_stay_in_sync_over_random_games() {
    fn check(pos: &Position) {
        let mut union = 0u64;
        for c in 0..2 {
            let mut side = 0u64;
            for p in 0..6 {
                let bb = pos.pieces[c * 6 + p];
                assert_eq!(side & bb, 0, "two pieces of one colour share a square");
                side |= bb;
            }
            assert_eq!(side, pos.occ[c], "occ[{c}] differs from its piece boards");
            assert_eq!(union & side, 0, "both colours occupy one square");
            union |= side;
        }
        assert_eq!(
            union, pos.occ_all,
            "occ_all differs from occ[WHITE] | occ[BLACK]"
        );
        for sq in 0..64u8 {
            let b = 1u64 << sq;
            let found = pos.piece_on(sq);
            match found {
                None => assert_eq!(pos.occ_all & b, 0, "empty answer on occupied square {sq}"),
                Some((c, p)) => assert_ne!(pos.pieces[c * 6 + p] & b, 0, "piece_on lies at {sq}"),
            }
        }
    }

    let starts = [
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
        "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
        "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1",
    ];
    let mut seed = 0x5EED_1234_u64;
    let mut plies = 0usize;
    for fen in starts {
        for _ in 0..40 {
            let mut pos = Position::from_fen(fen).expect("fixture FEN");
            let mut history = Vec::new();
            for _ in 0..120 {
                check(&pos);
                let legal = movegen::generate_legal(&mut pos);
                if legal.as_slice().is_empty() {
                    break;
                }
                let m = legal.as_slice()[(rng(&mut seed) % legal.as_slice().len() as u64) as usize];
                let undo = pos.make_move(m);
                check(&pos);
                history.push((m, undo));
                plies += 1;
            }
            while let Some((m, undo)) = history.pop() {
                pos.unmake_move(m, &undo);
                check(&pos);
            }
            assert_eq!(
                pos.to_fen(),
                fen,
                "unmake did not restore the start position"
            );
        }
    }
    assert!(
        plies > 5_000,
        "sweep too short to mean anything: {plies} plies"
    );
}
