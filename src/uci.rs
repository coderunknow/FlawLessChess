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
/// Largest Hash the engine accepts. `TranspositionTable` caps its size at 2^27 eight-byte entries
/// (1 GiB), so larger requests would silently allocate 1 GiB; they are rejected instead.
pub const MAX_HASH_MB: usize = 1024;

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
    /// Answer owed for a search that could not start (the OS refused the thread) and that the
    /// protocol holds until `stop` (`go infinite`, `go ponder`, bare `go`). Printed by
    /// `stop_and_join`, so `stop`, `quit`, EOF, and the next `go` all deliver it exactly once.
    pending_answer: Option<Option<Move>>,
    last_clocks: Option<(u64, u64, u64, u64, Option<u64>)>, // wtime btime winc binc movestogo
    stderr_log: bool,
}

/// Longest accepted input line. Real GUIs send far shorter lines (a 500-move `position` command is
/// about 3 KB); longer lines are discarded without unbounded buffering.
const MAX_INPUT_LINE_BYTES: usize = 64 * 1024;

/// Result of [`read_bounded_line`].
pub enum LineRead {
    Line,
    TooLong,
    Eof,
}

/// Read one `\n`-terminated line as raw bytes, keeping at most `max` bytes. A longer line is
/// consumed completely and reported as `TooLong`. A final line without a newline is returned as a
/// line; end of input with nothing buffered is `Eof`.
pub fn read_bounded_line<R: BufRead>(
    reader: &mut R,
    buf: &mut Vec<u8>,
    max: usize,
) -> std::io::Result<LineRead> {
    buf.clear();
    let mut too_long = false;
    let mut saw_bytes = false;
    loop {
        let (finished, used) = {
            let avail = reader.fill_buf()?;
            if avail.is_empty() {
                return Ok(match (saw_bytes, too_long) {
                    (false, _) => LineRead::Eof,
                    (true, true) => LineRead::TooLong,
                    (true, false) => LineRead::Line,
                });
            }
            saw_bytes = true;
            let (chunk, newline) = match avail.iter().position(|&b| b == b'\n') {
                Some(i) => (&avail[..i], true),
                None => (avail, false),
            };
            if !too_long {
                if buf.len() + chunk.len() > max {
                    too_long = true;
                    buf.clear();
                } else {
                    buf.extend_from_slice(chunk);
                }
            }
            (
                newline,
                if newline {
                    chunk.len() + 1
                } else {
                    chunk.len()
                },
            )
        };
        reader.consume(used);
        if finished {
            return Ok(if too_long {
                LineRead::TooLong
            } else {
                LineRead::Line
            });
        }
    }
}

/// Takes the stdout ordering lock. The guarded value is `()`, so a poisoned lock (a panic while
/// another thread held it) carries no state to protect; recovering keeps the UCI loop alive.
fn lock_ignoring_poison(m: &Mutex<()>) -> std::sync::MutexGuard<'_, ()> {
    m.lock().unwrap_or_else(std::sync::PoisonError::into_inner)
}

/// Hash size at start-up, in MiB (the UCI default).
const DEFAULT_HASH_MB: usize = 64;

/// Allocates a transposition table of `mb` MiB, halving the size while the allocator refuses it.
/// Returns the table and the size actually allocated. A refusal at 1 MiB is fatal: there is no
/// memory for any search, and this is reported on the process's stderr before exiting.
fn allocate_tt(mb: usize) -> (TranspositionTable, usize) {
    let mut size = mb.clamp(1, MAX_HASH_MB);
    loop {
        match TranspositionTable::try_new(size) {
            Ok(tt) => {
                if size < mb {
                    crate::out_line!(
                        "info string hash table reduced from {mb} MiB to {size} MiB (memory limit)"
                    );
                }
                return (tt, size);
            }
            Err(e) if size > 1 => {
                crate::out_line!("info string table of {size} MiB refused ({e}); trying half");
                size /= 2;
            }
            Err(e) => {
                crate::out_line!("info string fatal: no memory for even a 1 MiB table ({e})");
                std::process::exit(1);
            }
        }
    }
}

/// Reads the value after a `go` keyword at `args[i]` (F-26). The value is consumed only if it
/// parses; a missing or bad value (or another keyword, as in `go depth wtime 1000`) is reported on
/// stdout and only the keyword is skipped, so the next keyword is not lost. Returns the value and
/// the number of tokens consumed (1 or 2).
fn take_go_value<T>(
    args: &[&str],
    i: usize,
    key: &str,
    parse: impl Fn(&str) -> Option<T>,
) -> (Option<T>, usize) {
    match args.get(i + 1).and_then(|s| parse(s)) {
        Some(v) => (Some(v), 2),
        None => {
            crate::out_line!(
                "info string go {key}: missing or invalid value {:?}; ignored",
                args.get(i + 1).copied().unwrap_or("")
            );
            (None, 1)
        }
    }
}

/// Parses a `go depth` value (F-39). A digit-only value beyond the `i32` range saturates like the
/// time and node values do (a positive one to `i32::MAX`, clamped to 64 by the caller); a negative one
/// saturates to `i32::MIN` (clamped to 1). Before this, `go depth 4294967296` and `go depth
/// -4294967296` were ignored, which made the search unlimited, while `go depth 100` stopped at 64.
fn parse_depth(text: &str) -> Option<i32> {
    if let Ok(v) = text.parse::<i32>() {
        return Some(v);
    }
    let (negative, digits) = match text.strip_prefix('-') {
        Some(d) => (true, d),
        None => (false, text),
    };
    if !digits.is_empty() && digits.bytes().all(|b| b.is_ascii_digit()) {
        Some(if negative { i32::MIN } else { i32::MAX })
    } else {
        None
    }
}

/// Parses a `go` time value in milliseconds (`wtime`, `btime`, `winc`, `binc`, `movetime`) and,
/// since F-39, a `go nodes` count.
///
/// A negative value means the time is already gone (a GUI reports a flagged clock this way), so
/// it is 0: the search answers at once. Before this, `-1000` failed to parse and the token was
/// dropped, so the search had no time limit at all and never answered. A value above `u64::MAX`
/// saturates. Anything else that is not a number is `None`, as before.
fn parse_time_ms(text: &str) -> Option<u64> {
    let digits = text.strip_prefix('-');
    match digits {
        Some(d) if !d.is_empty() && d.bytes().all(|b| b.is_ascii_digit()) => Some(0),
        Some(_) => None,
        None => match text.parse::<u64>() {
            Ok(v) => Some(v),
            Err(_) if !text.is_empty() && text.bytes().all(|b| b.is_ascii_digit()) => {
                Some(u64::MAX)
            }
            Err(_) => None,
        },
    }
}

fn print_bestmove(result: &SearchResult) {
    // The total spent on the search, including any iteration that was aborted by a limit. The
    // last `info depth` line reports only the last completed iteration (S-08).
    crate::out_line!("info nodes {}", result.nodes);
    match result.ponder_move {
        Some(p) => crate::out_line!("bestmove {} ponder {}", result.best_move, p),
        None => crate::out_line!("bestmove {}", result.best_move),
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
        let (tt, hash_mb) = allocate_tt(DEFAULT_HASH_MB);
        UciEngine {
            pos: Position::startpos(),
            position_invalid: false,
            tt: Some(tt),
            hash_mb,
            multi_pv: 1,
            worker: None,
            pending_answer: None,
            last_clocks: None,
            stderr_log: false,
        }
    }

    pub fn run(&mut self) {
        let stdin = std::io::stdin();
        let mut reader = stdin.lock();
        let mut buf: Vec<u8> = Vec::new();
        loop {
            match read_bounded_line(&mut reader, &mut buf, MAX_INPUT_LINE_BYTES) {
                Ok(LineRead::Eof) | Err(_) => break,
                Ok(LineRead::TooLong) => {
                    // Oversized input is dropped as a whole line; the session stays in sync.
                    // The reader cannot tell which command it was, so a dropped `position`
                    // would leave the old position in place. Mark the position invalid, as a
                    // rejected `position` does: `go` then answers `bestmove 0000` until a valid
                    // `position` command arrives (the next valid one clears the flag).
                    self.position_invalid = true;
                    if self.stderr_log {
                        crate::err_line!(
                            "info string input line exceeds {MAX_INPUT_LINE_BYTES} bytes; ignored"
                        );
                    }
                    crate::out_line!(
                        "info string input line exceeds {MAX_INPUT_LINE_BYTES} bytes; ignored"
                    );
                    let _ = std::io::stdout().flush();
                }
                Ok(LineRead::Line) => {
                    // Invalid UTF-8 is replaced rather than treated as end of input.
                    let text = String::from_utf8_lossy(&buf);
                    let line = text.trim();
                    if line.is_empty() {
                        continue;
                    }
                    if !self.handle_line(line) {
                        break;
                    }
                }
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
                crate::out_line!("id name {ENGINE_NAME}");
                crate::out_line!("id author coderunknow (Apache-2.0)");
                crate::out_line!("option name Hash type spin default 64 min 1 max 1024");
                crate::out_line!("option name Threads type spin default 1 min 1 max 1");
                crate::out_line!("option name MultiPV type spin default 1 min 1 max 256");
                crate::out_line!("uciok");
                let _ = std::io::stdout().flush();
            }
            "isready" => {
                crate::out_line!("readyok");
                let _ = std::io::stdout().flush();
            }
            "ucinewgame" => {
                self.stop_and_join();
                if let Some(tt) = self.tt.as_mut() {
                    tt.clear();
                }
                self.pos = Position::startpos();
                self.position_invalid = false;
            }
            "position" => self.cmd_position(&tokens[1..]),
            "go" => self.cmd_go(&tokens[1..]),
            "stop" => self.stop_and_join(),
            "ponderhit" => self.cmd_ponderhit(),
            "setoption" => self.cmd_setoption(&tokens[1..]),
            "register" => crate::out_line!("registration ok"),
            "debug" => {
                self.stderr_log = tokens.get(1).map(|&s| s == "on").unwrap_or(false);
            }
            "quit" => {
                self.stop_and_join();
                return false;
            }
            other => {
                if self.stderr_log {
                    crate::err_line!("info string unknown command: {other}");
                }
            }
        }
        true
    }

    fn cmd_position(&mut self, args: &[&str]) {
        self.stop_and_join();
        let moves_idx = args.iter().position(|&t| t == "moves");
        let (fen_tokens, move_tokens): (&[&str], &[&str]) = match moves_idx {
            Some(i) => (&args[..i], &args[i + 1..]),
            None => (args, &[]),
        };
        // All-or-nothing (R-07): a rejected command keeps the previous position out of the
        // search and makes the next `go` answer `bestmove 0000`, so a GUI or runner error
        // is visible instead of silently searching a different position.
        let stderr_log = self.stderr_log;
        let rejected = |why: String, flag: &mut bool| {
            // stderr only with `debug on`: an undrained stderr pipe must never stall the engine (F-30).
            if stderr_log {
                crate::err_line!("info string position error: {why}");
            }
            crate::out_line!("info string position error: {why}");
            *flag = true;
        };
        // `startpos` may be followed only by `moves`: `position startpos e2e4` is a missing `moves`,
        // which used to search the start position and drop e2e4 without a notice (F-26).
        let startpos_extra = fen_tokens.first() == Some(&"startpos") && fen_tokens.len() > 1;
        let base = if fen_tokens.is_empty() {
            // `position` alone, or `position moves ...`: no startpos or fen to start from. The old
            // code searched the start position silently (F-26 class).
            let why = if args.is_empty() {
                "position needs `startpos` or `fen`"
            } else {
                "moves given without `startpos` or `fen`"
            };
            rejected(why.to_string(), &mut self.position_invalid);
            None
        } else if startpos_extra {
            rejected(
                "startpos takes no tokens before `moves`".to_string(),
                &mut self.position_invalid,
            );
            None
        } else if fen_tokens[0] == "startpos" {
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
            crate::out_line!("bestmove 0000");
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
                    if list.is_empty() {
                        crate::out_line!(
                            "info string searchmoves names no move; searching all legal moves"
                        );
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
                    let (v, used) = take_go_value(args, i, "wtime", parse_time_ms);
                    wtime = v;
                    i += used;
                }
                "btime" => {
                    let (v, used) = take_go_value(args, i, "btime", parse_time_ms);
                    btime = v;
                    i += used;
                }
                "winc" => {
                    let (v, used) = take_go_value(args, i, "winc", parse_time_ms);
                    winc = v.unwrap_or(0);
                    i += used;
                }
                "binc" => {
                    let (v, used) = take_go_value(args, i, "binc", parse_time_ms);
                    binc = v.unwrap_or(0);
                    i += used;
                }
                "movestogo" => {
                    let (v, used) = take_go_value(args, i, "movestogo", |s| s.parse().ok());
                    movestogo = v;
                    i += used;
                }
                "depth" => {
                    let (v, used) = take_go_value(args, i, "depth", parse_depth);
                    depth = v;
                    i += used;
                }
                "nodes" => {
                    let (v, used) = take_go_value(args, i, "nodes", parse_time_ms);
                    nodes = v;
                    i += used;
                }
                "movetime" => {
                    let (v, used) = take_go_value(args, i, "movetime", parse_time_ms);
                    movetime = v;
                    i += used;
                }
                other => {
                    // F-26: visible on stdout. `go mate N` is a standard UCI option this engine does
                    // not implement (the search runs until `stop`, as a bare `go`); the notice says so.
                    crate::out_line!("info string go token ignored: {other}");
                    i += 1;
                }
            }
        }

        // Remember clock fields only when the GUI sent a clock. `ponderhit` recalculates the
        // budget from these; a movetime-only or bare `go ponder` must not recalculate from zeros
        // (that gave a ~20 ms budget and an immediate bestmove).
        // Only the side to move's clock limits the search. A GUI that sends a single clock, or that
        // omits the opponent's clock, must still get a bounded search; the missing opponent clock is
        // never read, so it takes the side-to-move value. Without the side-to-move clock the search
        // is unlimited (until stop/ponderhit), as for a bare `go`.
        let own_clock = if self.pos.side == WHITE { wtime } else { btime };
        let clock_pair = own_clock.map(|own| (wtime.unwrap_or(own), btime.unwrap_or(own)));
        self.last_clocks = clock_pair.map(|(wt, bt)| (wt, bt, winc, binc, movestogo));

        let (soft_ms, hard_ms) = if let Some(mt) = movetime {
            (mt, mt)
        } else if let Some((wt, bt)) = clock_pair {
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
                || (own_clock.is_none()
                    && movetime.is_none()
                    && depth.is_none()
                    && nodes.is_none()),
            ponder,
            clock_origin: None,
        };
        let shared_limits = Arc::new(Mutex::new(SearchLimits {
            max_depth: limits.max_depth,
            max_nodes: limits.max_nodes,
            soft_ms: limits.soft_ms,
            hard_ms: limits.hard_ms,
            infinite: limits.infinite,
            ponder: limits.ponder,
            fixed_time: limits.fixed_time,
            clock_origin: None,
        }));

        // Fallback legal move in case the search thread dies unexpectedly —
        // the GUI must always receive a bestmove.
        // Prefer a legal move from `searchmoves` (F-21): the search is restricted to it, so the
        // fallback must be too. If no named move is legal, the search widens to all legal moves
        // (see below), and so does the fallback.
        let legal_for_fallback = generate_legal(&mut self.pos);
        let fallback_move = search_moves
            .as_ref()
            .and_then(|named| {
                legal_for_fallback
                    .iter()
                    .copied()
                    .find(|m| named.contains(m))
            })
            .or_else(|| legal_for_fallback.iter().next().copied());
        // go infinite / go ponder / bare go: bestmove is held until stop/ponderhit.
        let hold = Arc::new(AtomicBool::new(limits.infinite));
        let printed = Arc::new(AtomicBool::new(false));
        let flush = Arc::new(Mutex::new(()));
        let stop = Arc::new(AtomicBool::new(false));
        let consumed = Arc::new(AtomicBool::new(false));
        let tt = match self.tt.take() {
            Some(tt) => tt,
            None => {
                let (tt, mb) = allocate_tt(self.hash_mb);
                self.hash_mb = mb;
                tt
            }
        };
        let mut pos = self.pos.clone();
        // `searchmoves` that names no legal move: the search widens to all legal moves (see
        // `Searcher::search_root`). That is a deliberate choice (a null move is never useful here),
        // so it is reported on stdout rather than done silently.
        if let Some(ref named) = search_moves {
            let mut probe = self.pos.clone();
            let legal = generate_legal(&mut probe);
            if legal.len > 0 && !legal.iter().any(|m| named.contains(m)) {
                crate::out_line!("info string searchmoves names no legal move in this position; searching all legal moves");
            }
        }
        let stop_for_search = stop.clone();
        let multi_pv = self.multi_pv;
        let start_instant = Instant::now();
        let (tx, rx) = channel();

        let limits_for_thread = shared_limits.clone();
        let hold_for_thread = hold.clone();
        let printed_for_thread = printed.clone();
        let flush_for_thread = flush.clone();
        let spawned = thread::Builder::new()
            .stack_size(SEARCH_STACK_BYTES)
            .spawn(move || {
            let mut tt = tt;
            let searched = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                let mut searcher =
                    Searcher::new(&mut tt, &stop_for_search, limits_for_thread.clone());
                searcher.search_root(&mut pos, search_moves, multi_pv, &mut |progress: &SearchProgress| {
                    let elapsed = start_instant.elapsed().as_millis() as u64;
                    let nps = nps_of(progress.nodes, elapsed);
                    crate::out_line!(
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
                    let _g = lock_ignoring_poison(&flush_for_thread);
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
                    crate::out_line!("info string search thread panicked; emitting fallback bestmove");
                    let _g = lock_ignoring_poison(&flush_for_thread);
                    if !hold_for_thread.load(Ordering::Acquire)
                        && !printed_for_thread.swap(true, Ordering::AcqRel)
                    {
                        match fallback_move {
                            Some(m) => crate::out_line!("bestmove {m}"),
                            None => crate::out_line!("bestmove 0000"),
                        }
                        let _ = std::io::stdout().flush();
                    }
                    // TT is lost; the main thread recreates it on join failure.
                }
            }
        })
            ;
        let handle = match spawned {
            Ok(handle) => handle,
            Err(e) => {
                // The OS refused the search thread (for example under a memory limit). Answer now
                // with the fallback move (the first legal move) and say so on stdout, instead of
                // panicking. The table was moved into the thread's closure and is dropped with it;
                // the next `go` allocates a new one.
                crate::out_line!(
                    "info string search thread unavailable ({e}); answering without a search"
                );
                if limits.infinite {
                    // `go infinite`, `go ponder`, and bare `go` hold bestmove until `stop` (UCI).
                    // Answering now would send a bestmove before the GUI asked for one (F-22).
                    self.pending_answer = Some(fallback_move);
                } else {
                    match fallback_move {
                        Some(m) => crate::out_line!("bestmove {m}"),
                        None => crate::out_line!("bestmove 0000"),
                    }
                }
                let _ = std::io::stdout().flush();
                return;
            }
        };

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
                            // The slice counts from the hit (F-24): time spent pondering on the
                            // opponent's clock is not ours to spend.
                            lim.clock_origin = Some(std::time::Instant::now());
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
            let _g = lock_ignoring_poison(&worker.flush);
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
                            Some(m) => crate::out_line!("bestmove {m}"),
                            None => crate::out_line!("bestmove 0000"),
                        }
                        let _ = std::io::stdout().flush();
                    }
                }
            }
        }
    }

    fn cmd_setoption(&mut self, args: &[&str]) {
        // A malformed `setoption` used to be dropped without a word (F-26 class): say so on stdout.
        if args.is_empty() || args[0] != "name" {
            crate::out_line!("info string setoption expects `name <option> [value <x>]`; ignored");
            return;
        }
        let value_idx = args.iter().position(|&t| t == "value");
        let (name_tokens, value_tokens): (&[&str], &[&str]) = match value_idx {
            Some(i) => (&args[1..i], &args[i + 1..]),
            None => (&args[1..], &[]),
        };
        if name_tokens.is_empty() {
            crate::out_line!("info string setoption names no option; ignored");
            return;
        }
        let name = name_tokens.join(" ").to_ascii_lowercase();
        let value = value_tokens.join(" ");
        match name.as_str() {
            "hash" => match value
                .parse::<usize>()
                .ok()
                .filter(|&v| (1..=MAX_HASH_MB).contains(&v))
            {
                Some(mb) => {
                    self.stop_and_join();
                    match self.tt.as_mut().map(|tt| tt.try_resize(mb)) {
                        Some(Ok(())) => self.hash_mb = mb,
                        _ => {
                            // Keep the previous table: the engine must stay usable.
                            let (tt, kept) = match self.tt.take() {
                                Some(tt) => (tt, self.hash_mb),
                                None => allocate_tt(self.hash_mb),
                            };
                            self.tt = Some(tt);
                            self.hash_mb = kept;
                            crate::out_line!(
                                "info string option Hash {mb} MiB could not be allocated; keeping {kept} MiB"
                            );
                        }
                    }
                }
                None => {
                    crate::out_line!(
                        "info string option Hash expects 1..{MAX_HASH_MB} MiB, got {value:?}"
                    )
                }
            },
            "threads" => {
                if value != "1" {
                    crate::out_line!("info string option Threads: this build is single-threaded; value {value:?} ignored (1 thread used)");
                }
            }
            "multipv" => match value
                .parse::<usize>()
                .ok()
                .filter(|&v| (1..=256).contains(&v))
            {
                Some(n) => self.multi_pv = n,
                None => {
                    crate::out_line!("info string option MultiPV expects 1..256, got {value:?}")
                }
            },
            other => {
                // F-26: a UCI-visible notice on stdout (as for other rejected input).
                crate::out_line!("info string unknown option: {other}");
            }
        }
    }

    fn stop_and_join(&mut self) {
        if let Some(answer) = self.pending_answer.take() {
            // A held answer for a search that never started (see `cmd_go`, F-22).
            match answer {
                Some(m) => crate::out_line!("bestmove {m}"),
                None => crate::out_line!("bestmove 0000"),
            }
            let _ = std::io::stdout().flush();
            return;
        }
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
                    crate::out_line!("info string search thread ended without result");
                }
                if self.tt.is_none() {
                    let (tt, mb) = allocate_tt(self.hash_mb);
                    self.hash_mb = mb;
                    self.tt = Some(tt);
                }
                if !worker.printed.swap(true, Ordering::AcqRel) {
                    match worker.fallback {
                        Some(m) => crate::out_line!("bestmove {m}"),
                        None => crate::out_line!("bestmove 0000"),
                    }
                }
            }
        }
        let _ = std::io::stdout().flush();
    }
}

/// Stack for the search worker: recursion reaches MAX_PLY plies, and each ply holds move lists.
const SEARCH_STACK_BYTES: usize = 16 * 1024 * 1024;

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
    //   soft    = max(min(20 ms, t/(4*mtg)), (t - reserve)/mtg)  (CLOCK-1 floor, F-32) — full-period utilization is correct
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
    // Per-move floor (CLOCK-1 amendment, F-32): a quarter of the clock per planned move, capped at
    // 20 ms and never below 1 ms. The former fixed 20 ms floor spent 20 ms per move on short clocks
    // and drained the reserve to a flag. The floor reaches 20 ms at t >= 80 ms * movestogo (3.2 s at
    // the default of 40), so it changes only the short-clock range.
    let floor = (t / mtg.saturating_mul(4)).clamp(1, 20);
    // The increment share is part of the plan only within the usable clock (F-23): an increment
    // larger than the clock must not make soft (or hard) the whole clock.
    let soft = usable
        .saturating_div(mtg)
        .saturating_add(inc / 2)
        .min(usable)
        .max(floor)
        .min(t);
    let cap = t.saturating_sub(reserve / 2).max(soft);
    let hard = soft
        .saturating_mul(4)
        .min(usable / 2)
        .min(cap)
        .max(soft)
        .min(t);
    (soft, hard)
}

/// Nodes per second for an `info nps` value. A search that has taken 0 ms is reported as if it took
/// 1 ms, so the value is always a rate. The old fallback printed the bare node count (F-35).
fn nps_of(nodes: u64, elapsed_ms: u64) -> u64 {
    nodes.saturating_mul(1000) / elapsed_ms.max(1)
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
    fn clock_limits_never_plan_past_the_usable_clock_with_large_increment() {
        // Regression (F-23): `inc/2` was added after the division and only clamped to the whole
        // clock, so with an increment larger than the clock, soft (and hard) equalled the whole
        // remaining time. A GUI adds the increment only after the move, so such a move could flag.
        // The planned spend must stay within `t - reserve` (the usable clock), for any increment.
        for &(t, inc, mtg) in &[
            (1_000u64, 2_000u64, Some(40u64)),
            (10_000, 20_000, Some(40)),
            (900, 5_000, Some(1)),
            (3_000, 60_000, None),
            (250, 10_000, Some(40)),
        ] {
            let reserve = (t / 16).clamp(300, 8_000);
            let usable = t.saturating_sub(reserve);
            for side in [WHITE, WHITE + 1] {
                let (s, h) = clock_limits(side, t, t, inc, inc, mtg);
                assert!(
                    s <= usable.max(20),
                    "soft {s} plans past usable {usable} (t={t} inc={inc})"
                );
                assert!(
                    h <= usable.max(20),
                    "hard {h} plans past usable {usable} (t={t} inc={inc})"
                );
                assert!(h >= s, "hard {h} below soft {s}");
            }
        }
    }

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
        // t=250: reserve floor 300 > t -> usable 0 -> per-move floor min(20, 250/(4*40)) = 1 ms.
        // (CLOCK-1 amendment F-32: this was (20, 20) under the fixed 20 ms floor, which drained
        // a 250 ms clock; the change is owner-approved and recorded in PREREGISTRATION.md.)
        assert_eq!((sb, hb), (1, 1));
    }

    #[test]
    fn clock_limits_saturate_instead_of_wrapping() {
        // AUDIT-SEARCH-02: `usable / movestogo + increment / 2` overflowed u64 with a huge clock.
        let (soft, hard) = clock_limits(WHITE, u64::MAX, u64::MAX, u64::MAX, u64::MAX, Some(1));
        assert!(hard >= soft);
        assert!(soft > 1_000_000_000, "soft budget wrapped to {soft}");
    }

    #[test]
    fn bounded_line_reader_splits_lines_and_survives_bad_bytes() {
        use std::io::Cursor;
        let mut input = Cursor::new(b"uci\n\xff\xfe x\r\nlast".to_vec());
        let mut buf = Vec::new();
        assert!(matches!(
            read_bounded_line(&mut input, &mut buf, 64),
            Ok(LineRead::Line)
        ));
        assert_eq!(buf, b"uci");
        assert!(matches!(
            read_bounded_line(&mut input, &mut buf, 64),
            Ok(LineRead::Line)
        ));
        assert_eq!(buf, b"\xff\xfe x\r");
        assert!(matches!(
            read_bounded_line(&mut input, &mut buf, 64),
            Ok(LineRead::Line)
        ));
        assert_eq!(buf, b"last", "unterminated final line is still delivered");
        assert!(matches!(
            read_bounded_line(&mut input, &mut buf, 64),
            Ok(LineRead::Eof)
        ));
    }

    #[test]
    fn bounded_line_reader_discards_oversized_line_and_resyncs() {
        use std::io::Cursor;
        let mut data = vec![b'a'; 200];
        data.extend_from_slice(b"\nok\n");
        let mut input = Cursor::new(data);
        let mut buf = Vec::new();
        assert!(matches!(
            read_bounded_line(&mut input, &mut buf, 50),
            Ok(LineRead::TooLong)
        ));
        assert!(buf.is_empty());
        assert!(matches!(
            read_bounded_line(&mut input, &mut buf, 50),
            Ok(LineRead::Line)
        ));
        assert_eq!(buf, b"ok", "the line after an oversized one is read intact");
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

    #[test]
    fn info_nps_is_a_rate_when_no_time_has_passed() {
        // F-35: `info ... nodes 43 nps 43 time 0` printed the node count as the rate.
        assert_eq!(nps_of(43, 0), 43_000);
        assert_eq!(nps_of(146, 1), 146_000);
        assert_eq!(nps_of(146, 2), 73_000);
        assert_eq!(nps_of(u64::MAX, 0), u64::MAX);
    }

    #[test]
    fn clock_floor_f32_short_clock_keeps_reserve_over_a_period() {
        // F-32 regression (FAILURE_LEDGER F-32; CLOCK-1 amendment). With the fixed 20 ms floor,
        // a 300 ms or 1000 ms sudden-death clock spent 20 ms per move (plus overhead) and flagged
        // in self-play (300 ms: 3 of 3 games; 1000 ms: 2 of 3). Over a 40-move period at 2 ms
        // overhead per move, the clock must keep at least half of its reserve.
        for &t0 in &[300u64, 500, 800, 1_000, 1_100] {
            let reserve = (t0 / 16).clamp(300, 8_000);
            let mut t = t0;
            for _ in 0..40 {
                let (s, _) = clock_limits(WHITE, t, t, 0, 0, None);
                let spent = s + 2;
                assert!(spent < t, "move plans {spent} ms of {t} ms (start {t0})");
                t -= spent;
            }
            assert!(
                t >= reserve / 2,
                "40 moves from {t0} ms left {t} ms, below half the {reserve} ms reserve"
            );
        }
    }

    #[test]
    fn clock_floor_f32_exact_values_below_the_old_floor_range() {
        // Values from the formula (reserve, usable, floor = clamp(t/(4*mtg), 1, 20)):
        //  300 ms: reserve 300, usable 0 -> floor 1 -> soft 1; hard 1.
        // 1000 ms: reserve 300, usable 700 -> soft 700/40 = 17 (floor 6 does not bind); hard 68.
        // 800 ms: reserve 300, usable 500 -> soft 12; hard 48.
        assert_eq!(clock_limits(WHITE, 300, 300, 0, 0, Some(40)), (1, 1));
        assert_eq!(clock_limits(WHITE, 1_000, 1_000, 0, 0, Some(40)), (17, 68));
        assert_eq!(clock_limits(WHITE, 800, 800, 0, 0, Some(40)), (12, 48));
        // The floor is capped at 20 ms and does not change clocks at or above 3.2 s (default 40).
        assert_eq!(clock_limits(WHITE, 3_000, 3_000, 0, 0, None), (67, 268));
    }

    #[test]
    fn clock_floor_f32_huge_movestogo_does_not_overflow() {
        // The floor computes 4 * movestogo; a huge movestogo must saturate, not overflow.
        let (s, h) = clock_limits(WHITE, 1_000, 1_000, 0, 0, Some(u64::MAX));
        assert!(s >= 1 && s <= h && h <= 1_000, "soft {s} hard {h}");
        let (s0, h0) = clock_limits(WHITE, 0, 0, 0, 0, Some(40));
        assert_eq!((s0, h0), (0, 0));
    }
}
