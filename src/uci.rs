//! UCI (Universal Chess Interface) protocol implementation — hand-rolled, no dependencies.
//!
//! Implemented commands: uci, isready, ucinewgame, position, go (depth/nodes/movetime/
//! wtime..btime, winc/binc, movestogo, searchmoves, infinite, ponder), stop, ponderhit,
//! quit, register, setoption (Hash, Threads, MultiPV), debug.
//!
//! Search runs on a worker thread; `go` returns immediately. `bestmove` is printed exactly
//! once per `go`. `stop` / `ponderhit` act on the running search through shared, cheap
//! primitives (AtomicBool + Arc<Mutex<SearchLimits>>).

use crate::eval::MATE_SCORE;
use crate::movegen::generate_legal;
use crate::position::Position;
use crate::search::{SearchLimits, SearchProgress, SearchResult, Searcher};
use crate::tt::TranspositionTable;
use crate::types::Move;
use std::io::{BufRead, Write};
use std::sync::mpsc::{channel, Receiver};
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc, Mutex,
};
use std::thread;
use std::time::Instant;

const WHITE: usize = crate::types::WHITE;
const ENGINE_NAME: &str = "Flawless";

impl Default for UciEngine {
    fn default() -> Self {
        Self::new()
    }
}

pub struct UciEngine {
    pos: Position,
    /// Set when the last `position` command was rejected (R-07). While set, `go` answers
    /// `bestmove 0000` instead of searching a silently truncated position.
    position_invalid: bool,
    tt: Option<TranspositionTable>,
    hash_mb: usize,
    multi_pv: usize,
    worker: Option<WorkerHandle>,
    last_clocks: Option<(u64, u64, u64, u64, Option<u64>)>, // wtime btime winc binc movestogo
    stderr_log: bool,
}

fn print_bestmove(result: &SearchResult) {
    match result.ponder_move {
        Some(p) => println!("bestmove {} ponder {}", result.best_move, p),
        None => println!("bestmove {}", result.best_move),
    }
}

struct WorkerHandle {
    join: thread::JoinHandle<()>,
    done: Receiver<(SearchResult, TranspositionTable)>,
    stop: Arc<AtomicBool>,
    limits: Arc<Mutex<SearchLimits>>,
    /// True while `go infinite` / `go ponder` / a bare `go` is waiting for an external
    /// signal: bestmove must NOT be printed until `stop`/`ponderhit` (UCI).
    hold: Arc<AtomicBool>,
    /// Exactly-once guard for printing bestmove (worker or main thread prints it).
    printed: Arc<AtomicBool>,
    /// Legal move used if the search thread panics before producing one.
    fallback: Option<Move>,
    /// Result was already received (via ponderhit's try_recv); stop_and_join should not
    /// treat a later channel disconnect as an error.
    consumed: Arc<AtomicBool>,
    /// Serializes "release the hold" with "publish the result" between the worker thread
    /// and `ponderhit`, so exactly one of them prints the bestmove regardless of order.
    flush: Arc<Mutex<()>>,
}

impl UciEngine {
    pub fn new() -> Self {
        UciEngine {
            pos: Position::startpos(),
            position_invalid: false,
            tt: Some(TranspositionTable::new(64)),
            hash_mb: 64,
            multi_pv: 1,
            worker: None,
            last_clocks: None,
            stderr_log: false,
        }
    }

    pub fn run(&mut self) {
        let stdin = std::io::stdin();
        let mut lines = stdin.lock().lines();
        while let Some(Ok(line)) = lines.next() {
            let line = line.trim().to_string();
            if line.is_empty() {
                continue;
            }
            if !self.handle_line(&line) {
                break;
            }
        }
        self.stop_and_join();
    }

    /// Returns false to quit.
    fn handle_line(&mut self, line: &str) -> bool {
        let tokens: Vec<&str> = line.split_whitespace().collect();
        let Some(&cmd) = tokens.first() else {
            return true;
        };
        match cmd {
            "uci" => {
                println!("id name {ENGINE_NAME}");
                println!("id author coderunknow (Apache-2.0)");
                println!("option name Hash type spin default 64 min 1 max 4096");
                println!("option name Threads type spin default 1 min 1 max 1");
                println!("option name MultiPV type spin default 1 min 1 max 256");
                println!("uciok");
                let _ = std::io::stdout().flush();
            }
            "isready" => {
                println!("readyok");
                let _ = std::io::stdout().flush();
            }
            "ucinewgame" => {
                self.stop_and_join();
                if let Some(tt) = self.tt.as_mut() {
                    tt.clear();
                }
                self.pos = Position::startpos();
            }
            "position" => self.cmd_position(&tokens[1..]),
            "go" => self.cmd_go(&tokens[1..]),
            "stop" => self.stop_and_join(),
            "ponderhit" => self.cmd_ponderhit(),
            "setoption" => self.cmd_setoption(&tokens[1..]),
            "register" => println!("registration ok"),
            "debug" => {
                self.stderr_log = tokens.get(1).map(|&s| s == "on").unwrap_or(false);
            }
            "quit" => {
                self.stop_and_join();
                return false;
            }
            other => {
                if self.stderr_log {
                    eprintln!("info string unknown command: {other}");
                }
            }
        }
        true
    }

    fn cmd_position(&mut self, args: &[&str]) {
        self.stop_and_join();
        if args.is_empty() {
            return;
        }
        let moves_idx = args.iter().position(|&t| t == "moves");
        let (fen_tokens, move_tokens): (&[&str], &[&str]) = match moves_idx {
            Some(i) => (&args[..i], &args[i + 1..]),
            None => (args, &[]),
        };
        // All-or-nothing (R-07): a rejected command keeps the previous position out of the
        // search and makes the next `go` answer `bestmove 0000`, so a GUI or runner error
        // is visible instead of silently searching a different position.
        let rejected = |why: String, flag: &mut bool| {
            eprintln!("info string position error: {why}");
            println!("info string position error: {why}");
            *flag = true;
        };
        let base = if fen_tokens.is_empty() || fen_tokens[0] == "startpos" {
            Some(Position::startpos())
        } else {
            let fen = if fen_tokens[0] == "fen" {
                fen_tokens[1..].join(" ")
            } else {
                fen_tokens.join(" ")
            };
            match Position::from_fen(&fen) {
                Ok(p) => Some(p),
                Err(e) => {
                    rejected(e, &mut self.position_invalid);
                    None
                }
            }
        };
        let Some(mut pos) = base else { return };
        for mv in move_tokens {
            let Some(m) = Move::from_uci(mv) else {
                rejected(format!("malformed move {mv}"), &mut self.position_invalid);
                return;
            };
            let legal = generate_legal(&mut pos);
            match legal.iter().find(|&&x| x == m) {
                Some(&legal_m) => {
                    pos.make_move(legal_m);
                }
                None => {
                    rejected(format!("illegal move {mv}"), &mut self.position_invalid);
                    return;
                }
            }
        }
        self.pos = pos;
        self.position_invalid = false;
    }

    fn cmd_go(&mut self, args: &[&str]) {
        self.stop_and_join();
        if self.position_invalid {
            println!("bestmove 0000");
            return;
        }
        let mut movetime: Option<u64> = None;
        let mut depth: Option<i32> = None;
        let mut nodes: Option<u64> = None;
        let mut wtime: Option<u64> = None;
        let mut btime: Option<u64> = None;
        let mut winc: u64 = 0;
        let mut binc: u64 = 0;
        let mut movestogo: Option<u64> = None;
        let mut search_moves: Option<Vec<Move>> = None;
        let mut ponder = false;
        let mut infinite = false;

        let mut i = 0;
        while i < args.len() {
            match args[i] {
                "searchmoves" => {
                    let mut list = Vec::new();
                    i += 1;
                    while i < args.len() && Move::from_uci(args[i]).is_some() {
                        list.push(Move::from_uci(args[i]).unwrap());
                        i += 1;
                    }
                    search_moves = if list.is_empty() { None } else { Some(list) };
                    continue;
                }
                "ponder" => {
                    ponder = true;
                    i += 1;
                }
                "infinite" => {
                    infinite = true;
                    i += 1;
                }
                "wtime" => {
                    wtime = args.get(i + 1).and_then(|s| s.parse().ok());
                    i += 2;
                }
                "btime" => {
                    btime = args.get(i + 1).and_then(|s| s.parse().ok());
                    i += 2;
                }
                "winc" => {
                    winc = args.get(i + 1).and_then(|s| s.parse().ok()).unwrap_or(0);
                    i += 2;
                }
                "binc" => {
                    binc = args.get(i + 1).and_then(|s| s.parse().ok()).unwrap_or(0);
                    i += 2;
                }
                "movestogo" => {
                    movestogo = args.get(i + 1).and_then(|s| s.parse().ok());
                    i += 2;
                }
                "depth" => {
                    depth = args.get(i + 1).and_then(|s| s.parse().ok());
                    i += 2;
                }
                "nodes" => {
                    nodes = args.get(i + 1).and_then(|s| s.parse().ok());
                    i += 2;
                }
                "movetime" => {
                    movetime = args.get(i + 1).and_then(|s| s.parse().ok());
                    i += 2;
                }
                other => {
                    if self.stderr_log {
                        eprintln!("info string skipping unknown go token: {other}");
                    }
                    i += 1;
                }
            }
        }

        // Remember clock fields only when the GUI sent a clock. `ponderhit` recalculates the
        // budget from these; a movetime-only or bare `go ponder` must not recalculate from zeros
        // (that gave a ~20 ms budget and an immediate bestmove).
        self.last_clocks = if wtime.is_some() || btime.is_some() {
            Some((
                wtime.unwrap_or(0),
                btime.unwrap_or(0),
                winc,
                binc,
                movestogo,
            ))
        } else {
            None
        };

        let (soft_ms, hard_ms) = if let Some(mt) = movetime {
            (mt, mt)
        } else if let (Some(wt), Some(bt)) = (wtime, btime) {
            clock_limits(self.pos.side, wt, bt, winc, binc, movestogo)
        } else {
            (u64::MAX, u64::MAX)
        };
        let max_depth = depth.unwrap_or(64).clamp(1, 64);
        let max_nodes = nodes.unwrap_or(u64::MAX);

        let limits = SearchLimits {
            max_depth,
            max_nodes,
            soft_ms,
            hard_ms,
            fixed_time: movetime.is_some(),
            infinite: infinite
                || ponder
                || (wtime.is_none()
                    && btime.is_none()
                    && movetime.is_none()
                    && depth.is_none()
                    && nodes.is_none()),
            ponder,
        };
        let shared_limits = Arc::new(Mutex::new(SearchLimits {
            max_depth: limits.max_depth,
            max_nodes: limits.max_nodes,
            soft_ms: limits.soft_ms,
            hard_ms: limits.hard_ms,
            infinite: limits.infinite,
            ponder: limits.ponder,
            fixed_time: limits.fixed_time,
        }));

        // Fallback legal move in case the search thread dies unexpectedly —
        // the GUI must always receive a bestmove.
        let fallback_move = generate_legal(&mut self.pos).iter().next().copied();
        // go infinite / go ponder / bare go: bestmove is held until stop/ponderhit.
        let hold = Arc::new(AtomicBool::new(limits.infinite));
        let printed = Arc::new(AtomicBool::new(false));
        let flush = Arc::new(Mutex::new(()));
        let stop = Arc::new(AtomicBool::new(false));
        let consumed = Arc::new(AtomicBool::new(false));
        let tt = self
            .tt
            .take()
            .unwrap_or_else(|| TranspositionTable::new(self.hash_mb));
        let mut pos = self.pos.clone();
        let stop_for_search = stop.clone();
        let multi_pv = self.multi_pv;
        let start_instant = Instant::now();
        let (tx, rx) = channel();

        let limits_for_thread = shared_limits.clone();
        let hold_for_thread = hold.clone();
        let printed_for_thread = printed.clone();
        let flush_for_thread = flush.clone();
        let handle = thread::spawn(move || {
            let mut tt = tt;
            let searched = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                let mut searcher =
                    Searcher::new(&mut tt, &stop_for_search, limits_for_thread.clone());
                searcher.search_root(&mut pos, search_moves, multi_pv, &mut |progress: &SearchProgress| {
                    let elapsed = start_instant.elapsed().as_millis() as u64;
                    let nps = progress.nodes.saturating_mul(1000).checked_div(elapsed).unwrap_or(progress.nodes);
                    println!(
                        "info depth {} seldepth {} multipv {} score {} nodes {} nps {} time {} pv {}",
                        progress.depth,
                        progress.seldepth,
                        progress.multipv,
                        format_score(progress.score_cp),
                        progress.nodes,
                        nps,
                        elapsed,
                        progress.pv.iter().map(|m| m.to_uci()).collect::<Vec<_>>().join(" ")
                    );
                    let _ = std::io::stdout().flush();
                })
            }));
            // Print bestmove directly from the worker so it appears as soon as the
            // search ends, even if the GUI sends no further commands (UCI protocol).
            match searched {
                Ok(result) => {
                    // One critical section covers the hold-check/print AND the channel
                    // publish, so a concurrent ponderhit can never see "not printed yet"
                    // and "no message yet" at the same time: exactly one side prints.
                    let _g = flush_for_thread.lock().unwrap();
                    // For infinite/ponder searches the main thread prints bestmove
                    // after stop/ponderhit; otherwise we print as soon as we're done.
                    if !hold_for_thread.load(Ordering::Acquire)
                        && !printed_for_thread.swap(true, Ordering::AcqRel)
                    {
                        print_bestmove(&result);
                        let _ = std::io::stdout().flush();
                    }
                    let _ = tx.send((result, tt));
                }
                Err(_) => {
                    // Search thread panicked; unblock the GUI with a legal fallback.
                    // The marker goes to stdout so GUIs and the match runner can see it.
                    println!("info string search thread panicked; emitting fallback bestmove");
                    eprintln!("info string search thread panicked; emitting fallback bestmove");
                    let _g = flush_for_thread.lock().unwrap();
                    if !hold_for_thread.load(Ordering::Acquire)
                        && !printed_for_thread.swap(true, Ordering::AcqRel)
                    {
                        match fallback_move {
                            Some(m) => println!("bestmove {m}"),
                            None => println!("bestmove 0000"),
                        }
                        let _ = std::io::stdout().flush();
                    }
                    // TT is lost; the main thread recreates it on join failure.
                }
            }
        });

        self.worker = Some(WorkerHandle {
            join: handle,
            done: rx,
            stop,
            limits: shared_limits,
            hold,
            printed,
            fallback: fallback_move,
            consumed,
            flush,
        });
    }

    fn cmd_ponderhit(&mut self) {
        if let Some(worker) = self.worker.as_ref() {
            if let Ok(mut lim) = worker.limits.lock() {
                if lim.ponder {
                    match self.last_clocks {
                        // Clock-based ponder: the budget becomes a clock slice now, so the
                        // growth-prediction stop applies again.
                        Some((wt, bt, winc, binc, movestogo)) if !lim.fixed_time => {
                            let (soft, hard) =
                                clock_limits(self.pos.side, wt, bt, winc, binc, movestogo);
                            lim.soft_ms = soft;
                            lim.hard_ms = hard;
                            lim.infinite = false;
                        }
                        // Fixed movetime ponder: keep the movetime deadline (counted from the
                        // start of the search) and stop there.
                        _ if lim.fixed_time => {
                            lim.infinite = false;
                        }
                        // Bare `go ponder`: keep searching until an explicit `stop`. A node cap
                        // (`go ponder nodes N`) is still a limit, so it must be enforced after
                        // ponderhit; clearing `infinite` is what lets should_stop_now check it.
                        _ => {
                            if lim.max_nodes != u64::MAX {
                                lim.infinite = false;
                            }
                        }
                    }
                    lim.ponder = false;
                }
            }
            // Synchronize with the worker's end-of-search flush: whichever side gets the
            // mutex first decides, so the bestmove is printed exactly once regardless of
            // ordering. `hold` is cleared inside the critical section.
            let _g = worker.flush.lock().unwrap();
            worker.hold.store(false, Ordering::Release);
            // If the search already ended while bestmove was held (rare, e.g. hit max_depth
            // territory before the GUI reacted), flush the suppressed result now.
            match worker.done.try_recv() {
                Ok((result, tt)) => {
                    worker.consumed.store(true, Ordering::Relaxed);
                    self.tt = Some(tt);
                    if !worker.printed.swap(true, Ordering::AcqRel) {
                        print_bestmove(&result);
                        let _ = std::io::stdout().flush();
                    }
                }
                Err(std::sync::mpsc::TryRecvError::Empty) => {}
                Err(std::sync::mpsc::TryRecvError::Disconnected) => {
                    worker.consumed.store(true, Ordering::Relaxed);
                    if !worker.printed.swap(true, Ordering::AcqRel) {
                        match worker.fallback {
                            Some(m) => println!("bestmove {m}"),
                            None => println!("bestmove 0000"),
                        }
                        let _ = std::io::stdout().flush();
                    }
                }
            }
        }
    }

    fn cmd_setoption(&mut self, args: &[&str]) {
        if args.is_empty() || args[0] != "name" {
            return;
        }
        let value_idx = args.iter().position(|&t| t == "value");
        let (name_tokens, value_tokens): (&[&str], &[&str]) = match value_idx {
            Some(i) => (&args[1..i], &args[i + 1..]),
            None => (&args[1..], &[]),
        };
        let name = name_tokens.join(" ").to_ascii_lowercase();
        let value = value_tokens.join(" ");
        match name.as_str() {
            "hash" => match value
                .parse::<usize>()
                .ok()
                .filter(|&v| (1..=4096).contains(&v))
            {
                Some(mb) => {
                    self.stop_and_join();
                    self.hash_mb = mb;
                    self.tt = Some(TranspositionTable::new(mb));
                }
                None => eprintln!("info string option Hash expects 1..4096 MiB, got {value:?}"),
            },
            "threads" => {
                if value != "1" {
                    eprintln!("info string option Threads: this build is single-threaded; value {value:?} ignored (1 thread used)");
                }
            }
            "multipv" => match value
                .parse::<usize>()
                .ok()
                .filter(|&v| (1..=256).contains(&v))
            {
                Some(n) => self.multi_pv = n,
                None => eprintln!("info string option MultiPV expects 1..256, got {value:?}"),
            },
            other => {
                if self.stderr_log {
                    eprintln!("info string unknown option: {other}");
                }
            }
        }
    }

    fn stop_and_join(&mut self) {
        if self.worker.is_none() {
            return;
        }
        self.worker
            .as_ref()
            .unwrap()
            .stop
            .store(true, Ordering::Relaxed);
        let worker = self.worker.take().unwrap();
        let _ = worker.join.join();
        match worker.done.recv() {
            Ok((result, tt)) => {
                self.tt = Some(tt);
                if !worker.printed.swap(true, Ordering::AcqRel) {
                    print_bestmove(&result);
                }
            }
            Err(_) => {
                if !worker.consumed.load(Ordering::Relaxed) {
                    eprintln!("info string search thread ended without result");
                }
                if self.tt.is_none() {
                    self.tt = Some(TranspositionTable::new(self.hash_mb));
                }
                if !worker.printed.swap(true, Ordering::AcqRel) {
                    match worker.fallback {
                        Some(m) => println!("bestmove {m}"),
                        None => println!("bestmove 0000"),
                    }
                }
            }
        }
        let _ = std::io::stdout().flush();
    }
}

pub fn clock_limits(
    side: usize,
    wtime: u64,
    btime: u64,
    winc: u64,
    binc: u64,
    movestogo: Option<u64>,
) -> (u64, u64) {
    let (t, inc) = if side == WHITE {
        (wtime, winc)
    } else {
        (btime, binc)
    };
    let mtg = movestogo.unwrap_or(40).max(1);
    // ENGINE-1 reserve-bearing budget (registered 2026-11-15 in PREREGISTRATION.md
    // before implementation; supersedes the soft-clamp(20, 30_000)/hard=6*soft formula
    // whose late-period overspend produced ~95% flag falls at 40/15 — see
    // FAILURE_LEDGER 2026-11-15):
    //   reserve = clamp(t/16, 300 ms, 8 s)   — safety margin for per-move overhead,
    //   soft    = max(20 ms, (t - reserve)/mtg)  — full-period utilization is correct
    //              for repeating 'add' schedules, but planned spend never passes the
    //              period budget, and there is no upper clamp (the old 30 s cap made
    //              soft exceed the remaining plan and starved the period end),
    //   hard    = min(4*soft, (t - reserve)/2, t - reserve/2), floored at soft —
    //              a single move can never consume the whole usable clock.
    // Invariants (regression-tested): planned period spend <= t - reserve; after any
    // hard-limited move at least reserve/2 of the clock survives; hard >= soft; the
    // engine never plans past the remaining clock.
    let reserve = (t / 16).clamp(300, 8_000);
    let usable = t.saturating_sub(reserve);
    let soft = (usable / mtg + inc / 2).max(20).min(t);
    let cap = t.saturating_sub(reserve / 2).max(soft);
    let hard = soft
        .saturating_mul(4)
        .min(usable / 2)
        .min(cap)
        .max(soft)
        .min(t);
    (soft, hard)
}

fn format_score(score: i32) -> String {
    // Scores at/above MATE_SCORE are forced-mate scores; anything beyond MATE_SCORE
    // (or far below) is clamped — it cannot represent a real position evaluation.
    if score >= MATE_SCORE - 100 {
        let d = ((MATE_SCORE - score + 1) / 2).max(0);
        format!("mate {d}")
    } else if score <= -(MATE_SCORE - 100) {
        let d = ((MATE_SCORE + score + 1) / 2).max(0);
        format!("mate -{d}")
    } else {
        format!("cp {score}")
    }
}

/// Entry point: run the UCI loop on stdin/stdout.
pub fn run_uci() {
    let mut engine = UciEngine::new();
    engine.run();
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn clock_limits_respect_remaining_time() {
        // 40 moves in 15 minutes (the rating-schedule shape): reserve = 8 s,
        // usable = 892 s, soft = 22.3 s/move, hard = 4*soft = 89.2 s.
        let (soft, hard) = clock_limits(WHITE, 900_000, 900_000, 0, 0, Some(40));
        assert_eq!(soft, 22_300);
        assert_eq!(hard, 89_200);
        // Never exceed the remaining clock; hard >= soft; hard keeps reserve/2 alive.
        for &(t, inc, mtg) in &[
            (0u64, 0u64, Some(40u64)),
            (1, 0, Some(40)),
            (250, 0, Some(40)),
            (3_000, 0, Some(40)),
            (900_000, 0, Some(40)),
            (900_000, 0, Some(1)),
            (900_000, 100, Some(10)),
            (5_000, 0, None),
            (900_000, 0, Some(0)), // movestogo 0 must not panic; treated as >= 1
        ] {
            let (s, h) = clock_limits(WHITE, t, t, inc, inc, mtg);
            assert!(s <= t, "soft {s} exceeds remaining {t}");
            assert!(h >= s, "hard {h} below soft {s}");
            assert!(h <= t, "hard {h} exceeds remaining {t}");
        }
        // Side symmetry: black gets the same limits from its own clock.
        let (sw, hw) = clock_limits(WHITE, 3_000, 250, 0, 0, Some(40));
        let (sb, hb) = clock_limits(WHITE + 1, 3_000, 250, 0, 0, Some(40));
        // t=3000: reserve clamps to 300 ms -> usable 2700 -> soft 67, hard 4*soft=268.
        assert_eq!((sw, hw), (67, 268));
        // t=250: reserve floor 300 > t -> usable 0 -> 20 ms floor moves.
        assert_eq!((sb, hb), (20, 20));
    }

    #[test]
    fn clock_limits_engine1_no_flag_death_march() {
        // ENGINE-1 regression (FAILURE_LEDGER 2026-11-15): the old clamp(20, 30_000)
        // soft cap pinned soft at 30 s while the remaining clock shrank below the
        // plan, and hard = 6*soft allowed spending down to a ~30 ms clock — ~95% of
        // rating games ended in flag falls. The reserve-bearing budget must complete
        // a full 40-move period with a positive reserve, and no single move may be
        // able to consume the whole usable clock.
        let reserve_of = |t: u64| (t / 16).clamp(300, 8_000);
        // (1) Simulate a full period: spend exactly soft per move (the plan), charge
        //     60 ms of per-move overhead on top (engine elapsed = search + IO).
        let mut t: u64 = 900_000;
        for mtg in (1..=40).rev() {
            let (s, _) = clock_limits(WHITE, t, t, 0, 0, Some(mtg));
            let spent = s + 60; // overhead beyond the planned search time
            assert!(spent < t, "move with mtg={mtg} plans {spent} ms of {t} ms");
            t -= spent;
        }
        assert!(
            t >= 300,
            "period plan spent past the 300 ms reserve floor: {t} ms left"
        );
        // (2) A hard-limited move can never drop the clock below reserve/2.
        for &(tt, mtg) in &[
            (900_000u64, 40u64),
            (900_000, 1),
            (120_000, 7),
            (20_000, 40),
            (1_000, 3),
            (250, 40),
        ] {
            let (s, h) = clock_limits(WHITE, tt, tt, 0, 0, Some(mtg));
            let floor = (reserve_of(tt) / 2).min(tt.saturating_sub(1)).max(1);
            assert!(
                tt.saturating_sub(h) >= floor || h == tt.saturating_sub(1) || h >= tt,
                "hard {h} of {tt} (mtg={mtg}) can flag: survives only {} ms",
                tt - h
            );
            assert!(h >= s, "hard below soft at t={tt} mtg={mtg}");
        }
        // (3) Sudden-death shape (no movestogo, mtg defaults to 40) stays safe as
        //     the clock drains: plan sums stay within the remaining time.
        let mut t: u64 = 60_000;
        for _ in 0..30 {
            let (s, _) = clock_limits(WHITE, t, t, 0, 0, None);
            let spent = s + 20;
            assert!(spent < t, "sudden-death move plans {spent} of {t} ms");
            t -= spent;
        }
        assert!(t > 0);
        // (4) The old death-march trigger: late-period small clock with large mtg
        //     (movestogo lost) must NOT pin soft above the remaining budget.
        let (s, h) = clock_limits(WHITE, 45_000, 45_000, 0, 0, Some(40));
        assert!(s <= 45_000 / 8 + 1, "soft {s} overspends a starved period");
        assert!(
            h <= 45_000u64.saturating_sub(300),
            "hard {h} unsafe at 45 s/40"
        );
    }
}
