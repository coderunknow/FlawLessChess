//! CLI entry point for Flawless.

use flawless::eval::{ClassicalEvaluator, Evaluator};
use flawless::movegen;
use flawless::position::Position;
use std::time::Instant;

const ENGINE_NAME: &str = "Flawless";
const ENGINE_VERSION: &str = env!("CARGO_PKG_VERSION");

fn main() {
    let args: Vec<String> = std::env::args().collect();
    match args.get(1).map(|s| s.as_str()) {
        // Conventional UCI GUIs (e.g. CrispChess Extended) start a custom engine with
        // no command-line arguments and then speak UCI over stdin/stdout. A missing
        // argument therefore means "UCI mode", not "print usage and exit".
        None => flawless::uci::run_uci(),
        Some("uci") => flawless::uci::run_uci(),
        Some("-h") | Some("--help") => print_help(),
        Some("perft") => cmd_perft(&args[2..]),
        Some("divide") => cmd_divide(&args[2..]),
        Some("bench") => cmd_bench(),
        Some("eval") => cmd_eval(&args[2..]),
        Some("bench_eval") => cmd_bench_eval(),
        Some("moves") => cmd_moves(&args[2..]),
        Some("hash") => cmd_hash(&args[2..]),
        Some("--version") | Some("version") => println!("{ENGINE_NAME} {ENGINE_VERSION}"),
        Some(other) => {
            eprintln!("unknown command: {other}");
            eprintln!("run `{ENGINE_NAME} --help` for the list of commands");
            std::process::exit(2);
        }
    }
}

/// Explicit help (requested with `-h` / `--help`) goes to stdout, exit 0.
fn print_help() {
    println!("{ENGINE_NAME} {ENGINE_VERSION} — UCI chess engine");
    println!();
    println!("With no arguments, {ENGINE_NAME} starts the UCI protocol loop on stdin/stdout.");
    println!();
    println!("usage: {ENGINE_NAME} [command]");
    println!("  (no command)              UCI mode (same as `uci`)");
    println!("  uci                       UCI mode");
    println!("  perft <depth> [fen]       count leaf nodes of the legal-move tree");
    println!("  divide <depth> [fen]      perft split by root move");
    println!("  bench                     fixed-depth search benchmark + signature");
    println!("  eval [fen]                static evaluation breakdown");
    println!("  bench_eval                evaluation timing benchmark");
    println!("  moves                     read FENs on stdin, print legal moves");
    println!("  hash [fen]                print Zobrist hash (FEN arg or stdin)");
    println!("  version | --version       print the engine version");
    println!("  -h | --help               print this help");
}

fn cmd_perft(args: &[String]) {
    let depth: u32 = args
        .first()
        .and_then(|s| s.parse().ok())
        .unwrap_or_else(|| {
            eprintln!("usage: perft <depth> [fen]");
            std::process::exit(2);
        });
    let fen = args.get(1).map(|s| s.as_str());
    let mut pos = match fen {
        Some(f) => match Position::from_fen(f) {
            Ok(p) => p,
            Err(e) => {
                eprintln!("error: {e}");
                std::process::exit(1);
            }
        },
        None => Position::startpos(),
    };
    flawless::attack::init_attacks();
    eprintln!("magic sliders active: {}", flawless::attack::magic_ready());
    let t = Instant::now();
    let nodes = movegen::perft(&mut pos, depth);
    let dt = t.elapsed();
    println!(
        "perft({depth}) = {nodes}  ({:.3}s, {:.2}M nodes/s)",
        dt.as_secs_f64(),
        nodes as f64 / dt.as_secs_f64() / 1e6
    );
}

fn cmd_divide(args: &[String]) {
    let depth: u32 = args
        .first()
        .and_then(|s| s.parse().ok())
        .unwrap_or_else(|| {
            eprintln!("usage: divide <depth> [fen]");
            std::process::exit(2);
        });
    let fen = args.get(1).map(|s| s.as_str());
    let mut pos = match fen {
        Some(f) => Position::from_fen(f).unwrap_or_else(|e| {
            eprintln!("error: {e}");
            std::process::exit(1);
        }),
        None => Position::startpos(),
    };
    flawless::attack::init_attacks();
    let t = Instant::now();
    let total: u64 = movegen::perft_divide(&mut pos, depth)
        .iter()
        .map(|(m, n)| {
            println!("{m}: {n}");
            n
        })
        .sum();
    let dt = t.elapsed();
    println!("total = {total}  ({:.3}s)", dt.as_secs_f64());
}

/// Fixed-depth search benchmark over a fixed set of positions.
///
/// Prints per-position depth/score/nodes, then a total: nodes + an FNV-1a
/// signature over (fen, depth, bestmove) — a deterministic regression signature
/// for the search implementation on this machine. Timing varies by machine;
/// node counts and the signature should not change for identical engine code.
fn cmd_bench() {
    use flawless::search::{SearchLimits, Searcher};
    use flawless::tt::TranspositionTable;
    use std::sync::atomic::AtomicBool;
    use std::sync::{Arc, Mutex};

    const DEPTH: i32 = 10;
    let positions = [
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
        "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
        "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1",
        "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8",
        "rn1q1rk1/pb4pp/1p2pn2/3p2b1/2PP3B/2N2N2/PP2QPPP/R2R1K2 w - - 2 16",
        "2rr3k/pp3pp1/1nnqbN1p/3pN3/2pP4/2P3Q1/PPB4P/R4RK1 w - - 0 1",
        "r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10",
        "3r2k1/ppq2pp1/2n1pn1p/3p2P1/2PP2P1/P1N2N2/1PQ1R2P/2R3K1 w - - 7 22",
        "8/8/8/8/8/8/8/K6k w - - 0 1",
        "6k1/8/6K1/8/8/8/8/1Q6 w - - 0 1",
        "r1b1kb1r/pp1p1ppp/2n2n2/q1pp4/3P4/2PB1N2/PP3PPP/RNBQ1RK1 w kq - 0 1",
    ];

    flawless::attack::init_attacks();
    let t = Instant::now();
    let mut total_nodes = 0u64;
    let mut signature: u64 = 0xcbf29ce484222325;
    let mut fnv = |bytes: &[u8]| {
        for &b in bytes {
            signature ^= b as u64;
            signature = signature.wrapping_mul(0x100000001b3);
        }
    };

    for (i, fen) in positions.iter().enumerate() {
        let mut pos = Position::from_fen(fen).unwrap_or_else(|e| {
            eprintln!("bench FEN {i} invalid: {e}");
            std::process::exit(1);
        });
        let stop = Arc::new(AtomicBool::new(false));
        let limits = Arc::new(Mutex::new(SearchLimits {
            max_depth: DEPTH,
            max_nodes: u64::MAX,
            soft_ms: u64::MAX,
            hard_ms: u64::MAX,
            infinite: false,
            ponder: false,
            fixed_time: false,
        }));
        let mut tt = TranspositionTable::new(16);
        let result =
            Searcher::new(&mut tt, &stop, limits).search_root(&mut pos, None, 1, &mut |_| {});
        total_nodes += result.nodes;
        let bm = result.best_move.to_uci();
        fnv(fen.as_bytes());
        fnv(b"|");
        fnv(&DEPTH.to_le_bytes());
        fnv(bm.as_bytes());
        fnv(b"\n");
        println!(
            "bench [{i:2}]: depth {} score {:6} nodes {} pv {}",
            result.depth,
            result.score_cp,
            result.nodes,
            result
                .pv
                .iter()
                .map(|m| m.to_uci())
                .collect::<Vec<_>>()
                .join(" ")
        );
    }

    let dt = t.elapsed().as_secs_f64();
    println!("bench signature: {signature:016x}");
    println!(
        "bench: {} positions at depth {} — {} nodes in {:.2}s ({} nps)",
        positions.len(),
        DEPTH,
        total_nodes,
        dt,
        (total_nodes as f64 / dt.max(1e-9)) as u64
    );
}

/// Batch mode: read FENs (one per line) from stdin; print the engine's legal moves for each.
fn cmd_moves(_args: &[String]) {
    use std::io::{BufRead, Write};
    let stdin = std::io::stdin();
    let stdout = std::io::stdout();
    let mut out = stdout.lock();
    flawless::attack::init_attacks();
    for line in stdin.lock().lines() {
        let line = match line {
            Ok(l) => l,
            Err(_) => break,
        };
        let fen = line.trim();
        if fen.is_empty() || fen.starts_with('#') {
            continue;
        }
        match Position::from_fen(fen) {
            Ok(mut pos) => {
                let moves = movegen::generate_legal(&mut pos);
                let mut list: Vec<String> = moves.iter().map(|m| m.to_uci()).collect();
                list.sort();
                let _ = writeln!(out, "ok {} {}", moves.len, list.join(" "));
            }
            Err(e) => {
                let _ = writeln!(out, "error {e}");
            }
        }
    }
}

/// Print the Zobrist hash of the given FEN (or stdin FENs, one per line).
fn cmd_hash(args: &[String]) {
    use std::io::{BufRead, Write};
    flawless::attack::init_attacks();
    let stdout = std::io::stdout();
    let mut out = stdout.lock();
    if let Some(fen) = args.first() {
        match Position::from_fen(fen) {
            Ok(pos) => println!("{:016x}", pos.hash),
            Err(e) => {
                eprintln!("error: {e}");
                std::process::exit(1);
            }
        }
        return;
    }
    let stdin = std::io::stdin();
    for line in stdin.lock().lines() {
        let line = match line {
            Ok(l) => l,
            Err(_) => break,
        };
        let fen = line.trim();
        if fen.is_empty() {
            continue;
        }
        match Position::from_fen(fen) {
            Ok(pos) => {
                let _ = writeln!(out, "{:016x} {fen}", pos.hash);
            }
            Err(_) => {
                let _ = writeln!(out, "error {fen}");
            }
        }
    }
}

fn cmd_eval(args: &[String]) {
    let fen = args.first().map(|s| s.as_str());
    let pos = match fen {
        Some(f) => Position::from_fen(f).unwrap_or_else(|e| {
            eprintln!("error: {e}");
            std::process::exit(1);
        }),
        None => Position::startpos(),
    };
    flawless::attack::init_attacks();
    let mut eval = ClassicalEvaluator;
    let b = eval.breakdown(&pos);
    println!("total      {:>6} cp", b.total);
    println!("material   {:>6}", b.material);
    println!("pst        {:>6}", b.pst);
    println!("mobility   {:>6}", b.mobility);
    println!("pawns      {:>6}", b.pawns);
    println!("king_safety{:>6}", b.king_safety);
    println!("bishop_pair{:>6}", b.bishop_pair);
    println!("rook_file  {:>6}", b.rook_file);
    println!("tempo      {:>6}", b.tempo);
}

fn cmd_bench_eval() {
    flawless::attack::init_attacks();
    let fens = [
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
        "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
        "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1",
    ];
    let mut eval = ClassicalEvaluator;
    for fen in fens {
        let pos = Position::from_fen(fen).unwrap();
        let t = Instant::now();
        let mut acc = 0i32;
        let n = 1000;
        for _ in 0..n {
            acc = acc.saturating_add(eval.evaluate(&pos));
        }
        println!(
            "{:>6} cp  avg over {} evals in {:.3}s ({} ns/eval, checksum {})",
            acc / n,
            n,
            t.elapsed().as_secs_f64(),
            t.elapsed().as_nanos() / n as u128,
            acc
        );
    }
}
