//! Process-level regression tests for UCI input handling (FINAL_AUDIT findings).
//!
//! Each test drives the real `flawless` executable over stdin/stdout, the way a GUI does, and
//! asserts on protocol output. Every child is bounded by a timeout and is killed on failure so a
//! hung engine fails the test instead of hanging the suite.

use std::io::Write;
use std::process::{Child, Command, Stdio};
use std::sync::mpsc::{channel, Receiver, RecvTimeoutError, Sender};
use std::thread;
use std::time::{Duration, Instant};

struct Engine {
    child: Child,
    /// Input goes through a writer thread, so a stalled engine cannot block the test thread
    /// before its reply deadline starts (a full pipe would otherwise block `write_all` forever).
    writer: Option<Sender<Vec<u8>>>,
    lines: Receiver<String>,
}

impl Engine {
    fn start() -> Engine {
        let mut child = Command::new(env!("CARGO_BIN_EXE_flawless"))
            .arg("uci")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .expect("spawn flawless");
        let stdout = child.stdout.take().expect("stdout piped");
        let mut stdin = child.stdin.take().expect("stdin piped");
        let (wtx, wrx) = channel::<Vec<u8>>();
        thread::spawn(move || {
            for buf in wrx {
                // A write error means the engine is gone; the reader side reports that.
                if stdin.write_all(&buf).is_err() || stdin.flush().is_err() {
                    break;
                }
            }
            // Dropping `stdin` here closes the pipe (EOF for the engine).
        });
        let (tx, rx) = channel();
        thread::spawn(move || {
            use std::io::BufRead;
            for line in std::io::BufReader::new(stdout).lines() {
                match line {
                    Ok(l) => {
                        if tx.send(l).is_err() {
                            break;
                        }
                    }
                    Err(_) => break,
                }
            }
        });
        Engine {
            child,
            writer: Some(wtx),
            lines: rx,
        }
    }

    fn send_raw(&mut self, bytes: &[u8]) {
        if let Some(tx) = self.writer.as_ref() {
            // Ignored on failure: if the engine died, reading its output reports the failure.
            let _ = tx.send(bytes.to_vec());
        }
    }

    fn send(&mut self, line: &str) {
        self.send_raw(format!("{line}\n").as_bytes());
    }

    /// Read lines until one starts with `token`, failing (and killing the child) on timeout.
    fn read_until(&mut self, token: &str, timeout: Duration) -> Vec<String> {
        let start = Instant::now();
        let mut seen = Vec::new();
        loop {
            let remaining = timeout.saturating_sub(start.elapsed());
            if remaining.is_zero() {
                self.kill();
                panic!("timed out waiting for {token:?}; output so far: {seen:?}");
            }
            match self.lines.recv_timeout(remaining) {
                Ok(line) => {
                    let done = line.starts_with(token);
                    seen.push(line);
                    if done {
                        return seen;
                    }
                }
                Err(RecvTimeoutError::Timeout) => {
                    self.kill();
                    panic!("timed out waiting for {token:?}; output so far: {seen:?}");
                }
                Err(RecvTimeoutError::Disconnected) => {
                    self.kill();
                    panic!("engine exited while waiting for {token:?}; output: {seen:?}");
                }
            }
        }
    }

    fn kill(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }

    /// Ask for `quit` and require the process to exit on its own within `timeout`.
    fn quit_and_expect_exit(mut self, timeout: Duration) {
        self.send("quit");
        self.writer = None; // closes the channel; the writer thread drains and exits
        let start = Instant::now();
        loop {
            match self.child.try_wait() {
                Ok(Some(status)) => {
                    assert!(status.success(), "engine exited with {status}");
                    return;
                }
                Ok(None) => {
                    if start.elapsed() > timeout {
                        self.kill();
                        panic!("engine did not exit after quit within {timeout:?}");
                    }
                    thread::sleep(Duration::from_millis(5));
                }
                Err(e) => panic!("try_wait failed: {e}"),
            }
        }
    }
}

impl Drop for Engine {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

fn bestmove_line(lines: &[String]) -> &str {
    lines
        .iter()
        .rev()
        .find(|l| l.starts_with("bestmove "))
        .map(|s| s.as_str())
        .unwrap_or_else(|| panic!("no bestmove in {lines:?}"))
}

/// Regression (AUDIT-UCI-01): a non-UTF-8 line used to end the UCI loop, so the engine exited
/// silently and every later command went unanswered. The line must be ignored instead.
#[test]
fn non_utf8_input_line_does_not_end_the_session() {
    let mut e = Engine::start();
    e.send("uci");
    e.read_until("uciok", Duration::from_secs(10));
    e.send_raw(b"\xff\xfe position startpos\n");
    e.send("isready");
    e.read_until("readyok", Duration::from_secs(10));
    e.send("go depth 1");
    let lines = e.read_until("bestmove", Duration::from_secs(20));
    assert!(bestmove_line(&lines).starts_with("bestmove "));
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// Regression (AUDIT-UCI-02): an oversized line is discarded whole; the next command still works.
#[test]
fn oversized_input_line_is_dropped_and_session_continues() {
    let mut e = Engine::start();
    e.send("uci");
    e.read_until("uciok", Duration::from_secs(10));
    let mut big = String::from("position startpos moves");
    while big.len() < 200 * 1024 {
        big.push_str(" e2e4");
    }
    big.push('\n');
    e.send_raw(big.as_bytes());
    e.send("isready");
    let lines = e.read_until("readyok", Duration::from_secs(10));
    assert!(
        lines.iter().any(|l| l.contains("exceeds")),
        "oversized line was not reported: {lines:?}"
    );
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// Regression (AUDIT-SEARCH-01): with only `wtime` present, the search had no limit and ran to
/// depth 64 (until a stop). The side to move's clock must bound the search.
#[test]
fn single_side_clock_bounds_the_search() {
    let mut e = Engine::start();
    e.send("uci");
    e.read_until("uciok", Duration::from_secs(10));
    e.send("position startpos");
    let started = Instant::now();
    e.send("go wtime 1000");
    let lines = e.read_until("bestmove", Duration::from_secs(10));
    let elapsed = started.elapsed();
    assert!(
        elapsed < Duration::from_secs(5),
        "wtime-only search took {elapsed:?}"
    );
    assert!(bestmove_line(&lines).starts_with("bestmove "));
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// Regression (AUDIT-UCI-03): Hash values above the real 1 GiB table ceiling must be rejected and
/// the advertised maximum must match what is accepted.
#[test]
fn hash_limit_is_advertised_and_enforced() {
    let mut e = Engine::start();
    e.send("uci");
    let uci = e.read_until("uciok", Duration::from_secs(10));
    assert!(
        uci.iter()
            .any(|l| l == "option name Hash type spin default 64 min 1 max 1024"),
        "Hash maximum not advertised as 1024: {uci:?}"
    );
    e.send("setoption name Hash value 4096");
    e.send("isready");
    let lines = e.read_until("readyok", Duration::from_secs(10));
    assert!(
        lines.iter().any(|l| l.contains("expects 1..1024")),
        "Hash 4096 was not rejected: {lines:?}"
    );
    e.send("setoption name Hash value 1024");
    e.send("isready");
    e.read_until("readyok", Duration::from_secs(10));
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// Regression (F-45): a Hash value that is not a power of two is rounded down, and the engine
/// must say what it allocated. Before the fix `Hash 100` silently allocated 64 MiB.
#[test]
fn hash_rounding_is_reported_on_stdout() {
    let mut e = Engine::start();
    e.send("uci");
    e.read_until("uciok", Duration::from_secs(10));
    e.send("setoption name Hash value 100");
    e.send("isready");
    let lines = e.read_until("readyok", Duration::from_secs(10));
    assert!(
        lines
            .iter()
            .any(|l| l.contains("Hash 100 MiB allocates 64 MiB")),
        "Hash 100 was not reported as 64 MiB: {lines:?}"
    );
    e.send("setoption name Hash value 64");
    e.send("isready");
    let lines = e.read_until("readyok", Duration::from_secs(10));
    assert!(
        !lines.iter().any(|l| l.contains("allocates")),
        "exact power of two reported as rounded: {lines:?}"
    );
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// Regression (AUDIT-FEN-01): a FEN with more pieces than any real game can reach generated more
/// moves than the fixed move list held, and `go` then crashed the engine (exit 101). The FEN must
/// be rejected, after which the engine answers the next `go` with `bestmove 0000` and stays alive.
#[test]
fn impossible_material_fen_is_rejected_without_crashing() {
    let mut e = Engine::start();
    e.send("uci");
    e.read_until("uciok", Duration::from_secs(10));
    e.send("position fen KQQQQQBk/Q5RB/Q6Q/Q6Q/Q6Q/Q6Q/Q1QQ3Q/QR3QQQ w - - 0 1");
    e.send("go depth 2");
    let lines = e.read_until("bestmove", Duration::from_secs(10));
    assert!(
        lines.iter().any(|l| l.contains("impossible material")),
        "rejection not reported: {lines:?}"
    );
    assert_eq!(bestmove_line(&lines), "bestmove 0000");
    e.send("isready");
    e.read_until("readyok", Duration::from_secs(10));
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// Strict `searchmoves` (owner decision, 2026-11-22): a list that names only illegal moves has an
/// empty intersection with the legal moves. The engine must not search unrestricted legal moves. It
/// answers `bestmove 0000`, says so on stdout, and prints no `info depth` line (no search ran).
#[test]
fn illegal_only_searchmoves_returns_null_without_searching() {
    let mut e = Engine::start();
    e.send("uci");
    e.read_until("uciok", Duration::from_secs(10));
    e.send("position startpos");
    e.send("go depth 2 searchmoves e2e5 d2d9");
    let lines = e.read_until("bestmove", Duration::from_secs(20));
    assert_eq!(bestmove_line(&lines), "bestmove 0000", "{lines:?}");
    assert!(
        lines
            .iter()
            .any(|l| l.starts_with("info string searchmoves names no legal move")),
        "empty intersection not announced: {lines:?}"
    );
    assert!(
        !lines.iter().any(|l| l.starts_with("info depth")),
        "a search ran outside the requested set: {lines:?}"
    );
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// Strict `searchmoves`: the returned move is always inside the requested set. Covers duplicate
/// names, a mix of legal and illegal names, malformed tokens, and an ordinary valid request.
#[test]
fn searchmoves_never_returns_a_move_outside_the_requested_set() {
    let cases: [(&str, &[&str]); 4] = [
        ("e2e4 e2e4 e2e4", &["e2e4"]),
        ("e2e5 e2e4 zzzz d2d9", &["e2e4"]),
        ("g1f3 b1c3", &["g1f3", "b1c3"]),
        ("a2a3", &["a2a3"]),
    ];
    for (named, allowed) in cases {
        let mut e = Engine::start();
        e.send("uci");
        e.read_until("uciok", Duration::from_secs(10));
        e.send("position startpos");
        e.send(&format!("go depth 3 searchmoves {named}"));
        let lines = e.read_until("bestmove", Duration::from_secs(20));
        let bm = bestmove_line(&lines)
            .split_whitespace()
            .nth(1)
            .unwrap_or("")
            .to_string();
        assert!(
            allowed.contains(&bm.as_str()),
            "searchmoves {named:?} returned {bm}, which is outside {allowed:?}: {lines:?}"
        );
        e.quit_and_expect_exit(Duration::from_secs(10));
    }
}

/// Strict `searchmoves`: a list that is only malformed tokens names no legal move, so the answer is
/// `bestmove 0000`, and the malformed token is reported on stdout.
#[test]
fn malformed_only_searchmoves_returns_null_and_reports_the_token() {
    let mut e = Engine::start();
    e.send("uci");
    e.read_until("uciok", Duration::from_secs(10));
    e.send("position startpos");
    e.send("go depth 2 searchmoves zzzz");
    let lines = e.read_until("bestmove", Duration::from_secs(20));
    assert_eq!(bestmove_line(&lines), "bestmove 0000", "{lines:?}");
    assert!(
        lines.iter().any(|l| l.contains("malformed move \"zzzz\"")),
        "malformed searchmoves token not reported: {lines:?}"
    );
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// Strict `searchmoves`: the list ends at the next `go` keyword, so `depth` after the list still
/// limits the search (the list is not swallowed and the depth is not lost).
#[test]
fn searchmoves_list_ends_at_the_next_go_keyword() {
    let mut e = Engine::start();
    e.send("uci");
    e.read_until("uciok", Duration::from_secs(10));
    e.send("position startpos");
    e.send("go searchmoves e2e4 g1f3 depth 2");
    let lines = e.read_until("bestmove", Duration::from_secs(20));
    assert!(
        lines.iter().any(|l| l.starts_with("info depth 2 ")),
        "depth after searchmoves was not honoured: {lines:?}"
    );
    assert!(
        !lines.iter().any(|l| l.starts_with("info depth 3 ")),
        "search ran past depth 2: {lines:?}"
    );
    let mv = bestmove_line(&lines)
        .split_whitespace()
        .nth(1)
        .unwrap_or("");
    assert!(
        mv == "e2e4" || mv == "g1f3",
        "bestmove {mv} is outside searchmoves: {lines:?}"
    );
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// Control for the searchmoves notice: when a named move is legal, no widening notice is printed
/// and the result is restricted to the named moves.
#[test]
fn legal_searchmoves_are_respected_without_widening_notice() {
    let mut e = Engine::start();
    e.send("uci");
    e.read_until("uciok", Duration::from_secs(10));
    e.send("position startpos");
    e.send("go depth 2 searchmoves e2e4 d2d4");
    let lines = e.read_until("bestmove", Duration::from_secs(20));
    assert!(
        !lines
            .iter()
            .any(|l| l.starts_with("info string searchmoves")),
        "legal searchmoves printed a widening notice: {lines:?}"
    );
    let bm = bestmove_line(&lines);
    let mv = bm
        .trim_start_matches("bestmove ")
        .split(' ')
        .next()
        .unwrap();
    assert!(
        mv == "e2e4" || mv == "d2d4",
        "searchmoves e2e4 d2d4 returned {bm}"
    );
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// Regression (F-52): the node cap of `go ponder nodes N` counts from `ponderhit` (S-07), even when
/// the ponder search already ran past N before the hit. The old code kept the cap spent during
/// pondering, so the search returned at once after the hit. The hit comes only after the search
/// has passed CAP, so the old code returns at once and the fixed code must spend about CAP more
/// nodes. The lower time bound is far above the old return time and far below the fixed run time.
#[test]
fn ponder_node_cap_counts_from_ponderhit_when_pondering_passed_it() {
    const CAP: u64 = 100_000;
    let mut e = Engine::start();
    e.send("uci");
    e.read_until("uciok", Duration::from_secs(10));
    e.send("isready");
    e.read_until("readyok", Duration::from_secs(10));
    e.send("position startpos");
    e.send(&format!("go ponder nodes {CAP}"));
    let mut nodes_before_hit = 0;
    while nodes_before_hit <= CAP {
        let lines = e.read_until("info depth", Duration::from_secs(120));
        if let Some(n) = lines
            .iter()
            .rev()
            .find(|l| l.starts_with("info depth"))
            .and_then(|l| info_nodes(l))
        {
            nodes_before_hit = n;
        }
    }
    let hit = std::time::Instant::now();
    e.send("ponderhit");
    e.read_until("bestmove", Duration::from_secs(60));
    let spent = hit.elapsed();
    assert!(
        spent >= Duration::from_millis(50),
        "node cap was already spent before ponderhit (pondering ran to {nodes_before_hit} nodes): \
         bestmove came {spent:?} after the hit"
    );
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// Regression (AUDIT-SEARCH-03, prior report S-07): after `ponderhit`, `go ponder nodes N` must
/// end the search (the cap applies from the hit on). The ponder search is unlimited until the
/// hit, and the hit is processed only after the first `info depth` line, so the search may have
/// passed CAP by then. The exact count is therefore not asserted here: the exact cap is covered
/// by `go_nodes_limit_is_spent_exactly_and_reported` and `correctness::node_cap_is_spent_exactly`.
#[test]
fn ponder_node_cap_is_enforced_after_ponderhit() {
    const CAP: u64 = 20_000;
    let mut e = Engine::start();
    e.send("uci");
    e.read_until("uciok", Duration::from_secs(10));
    e.send("isready");
    e.read_until("readyok", Duration::from_secs(10));
    e.send("position startpos moves e2e4 e7e5");
    e.send(&format!("go ponder nodes {CAP}"));
    let before_hit = e.read_until("info depth", Duration::from_secs(20));
    let first = before_hit.last().expect("first info line");
    let nodes_at_hit = info_nodes(first).expect("nodes on first info line");
    assert!(
        nodes_at_hit < CAP,
        "precondition: hit must arrive below the cap ({nodes_at_hit} >= {CAP})"
    );
    e.send("ponderhit");
    let lines = e.read_until("bestmove", Duration::from_secs(20));
    let final_nodes = lines
        .iter()
        .filter_map(|l| l.strip_prefix("info nodes "))
        .filter_map(|n| n.trim().parse::<u64>().ok())
        .next_back()
        .expect("final `info nodes` line before bestmove");
    assert!(
        final_nodes >= nodes_at_hit,
        "node count went backwards: {final_nodes} < {nodes_at_hit} at the hit"
    );
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// Returns the `nodes` value of an `info ... nodes N ...` line.
fn info_nodes(line: &str) -> Option<u64> {
    let mut it = line.split_whitespace();
    while let Some(tok) = it.next() {
        if tok == "nodes" {
            return it.next().and_then(|n| n.parse().ok());
        }
    }
    None
}

/// Regression (S-08): `go nodes N` spends exactly N nodes, reported on the final `info nodes` line
/// before `bestmove`. N = 1 is below the cost of depth 1: no iteration completes, so the bestmove
/// is the first legal move (unsearched), and the count is still exact.
#[test]
fn go_nodes_limit_is_spent_exactly_and_reported() {
    const START_LEGAL: [&str; 20] = [
        "a2a3", "a2a4", "b2b3", "b2b4", "c2c3", "c2c4", "d2d3", "d2d4", "e2e3", "e2e4", "f2f3",
        "f2f4", "g2g3", "g2g4", "h2h3", "h2h4", "b1a3", "b1c3", "g1f3", "g1h3",
    ];
    let mut e = Engine::start();
    e.send("uci");
    e.read_until("uciok", Duration::from_secs(10));
    for &n in &[1u64, 1000, 5000, 20000] {
        e.send("ucinewgame");
        e.send("isready");
        e.read_until("readyok", Duration::from_secs(10));
        e.send("position startpos");
        e.send(&format!("go nodes {n}"));
        let lines = e.read_until("bestmove", Duration::from_secs(30));
        let reported = lines
            .iter()
            .filter_map(|l| l.strip_prefix("info nodes "))
            .filter_map(|v| v.trim().parse::<u64>().ok())
            .next_back()
            .unwrap_or_else(|| panic!("no final `info nodes` for go nodes {n}: {lines:?}"));
        assert_eq!(reported, n, "go nodes {n} reported {reported} nodes");
        let mv = bestmove_line(&lines)
            .trim_start_matches("bestmove ")
            .split(' ')
            .next()
            .unwrap();
        assert!(
            START_LEGAL.contains(&mv),
            "go nodes {n}: bestmove {mv} is not legal"
        );
    }
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// Regression (F-09 revalidation): with `searchmoves` naming a legal move and an illegal one, the
/// restriction applies to the legal move only. The illegal name is ignored silently, and the
/// result must be the named legal move.
#[test]
fn mixed_searchmoves_restricts_to_the_legal_named_move() {
    let mut e = Engine::start();
    e.send("uci");
    e.read_until("uciok", Duration::from_secs(10));
    e.send("position startpos");
    e.send("go depth 2 searchmoves e2e5 d2d4");
    let lines = e.read_until("bestmove", Duration::from_secs(20));
    assert!(
        !lines
            .iter()
            .any(|l| l.starts_with("info string searchmoves names no legal move")),
        "mixed searchmoves with a legal move must not widen: {lines:?}"
    );
    let bm = bestmove_line(&lines);
    assert_eq!(
        bm.split(' ').nth(1),
        Some("d2d4"),
        "searchmoves e2e5 d2d4 must return d2d4, got {bm}"
    );
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// Regression (AUDIT-UCI-04): the build is single-threaded. A `Threads` value other than 1 must be
/// reported to the GUI on stdout (an `info string`), not only on stderr, and must not change
/// the search (the engine still answers with a legal move).
#[test]
fn threads_other_than_one_is_reported_on_stdout() {
    let mut e = Engine::start();
    e.send("uci");
    let uci = e.read_until("uciok", Duration::from_secs(10));
    assert!(
        uci.iter()
            .any(|l| l == "option name Threads type spin default 1 min 1 max 1"),
        "Threads option is not advertised as 1..1: {uci:?}"
    );
    e.send("setoption name Threads value 4");
    e.send("isready");
    let lines = e.read_until("readyok", Duration::from_secs(10));
    assert!(
        lines
            .iter()
            .any(|l| l.starts_with("info string") && l.contains("Threads")),
        "Threads 4 was not reported on stdout: {lines:?}"
    );
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// Regression (F-10): when the reader closes stdout, the engine must end quietly with status 0.
/// Before the `out_line!` macro, the next `println!` panicked on `Broken pipe` (exit 101).
/// The handshake and every wait go through the bounded `read_until`; `Engine` kills the child
/// on any failed assertion (its `Drop` impl), so no test failure leaves a process running.
#[test]
fn closed_stdout_ends_the_process_quietly() {
    let mut e = Engine::start();
    e.send("uci");
    e.read_until("uciok", Duration::from_secs(10));
    // Dropping the line receiver ends the reader thread on its next line. That closes the
    // engine's stdout read end, so the engine's next writes hit a broken pipe.
    //
    // The reader may drain several `readyok` lines in one read, close stdout, and leave the engine
    // with no further output to write. So keep asking for output until the engine exits: the
    // first write after the close fails with a broken pipe.
    e.lines = channel().1;
    let deadline = Instant::now() + Duration::from_secs(10);
    let status = loop {
        if let Some(st) = e.child.try_wait().expect("try_wait") {
            break st;
        }
        assert!(
            Instant::now() < deadline,
            "engine did not exit after its stdout was closed"
        );
        e.send("isready");
        thread::sleep(Duration::from_millis(20));
    };
    assert_eq!(status.code(), Some(0), "exit status after closed stdout");
}

/// Regression: an oversized line is dropped whole. The reader cannot tell whether it was a
/// `position` command, so the position must be marked invalid: `go` must not search the old
/// position. A later valid `position` clears the mark.
#[test]
fn oversized_position_line_does_not_leave_the_old_position_in_use() {
    let mut e = Engine::start();
    e.send("uci");
    e.read_until("uciok", Duration::from_secs(10));
    e.send("position startpos");
    let mut big = String::from("position startpos moves e2e4");
    while big.len() < 200 * 1024 {
        big.push_str(" e2e4");
    }
    big.push('\n');
    e.send_raw(big.as_bytes());
    e.send("go depth 1");
    let lines = e.read_until("bestmove", Duration::from_secs(10));
    assert_eq!(
        bestmove_line(&lines),
        "bestmove 0000",
        "go after a dropped oversized position must not search the old position"
    );
    e.send("position startpos");
    e.send("go depth 1");
    let lines = e.read_until("bestmove", Duration::from_secs(20));
    assert!(
        !bestmove_line(&lines).starts_with("bestmove 0000"),
        "a valid position command must clear the invalid mark: {lines:?}"
    );
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// Regression (F-13): a failed write to stderr used to panic (`eprintln!`), exiting 101 before
/// `readyok`. Here stderr is a pipe whose read end is already closed, so every write fails with
/// EPIPE. Status messages now go through a write that ignores errors, so the session keeps
/// answering. (A closed fd 2 cannot be produced on every platform: some runtimes reopen fds 0-2.)
#[cfg(unix)]
#[test]
fn stderr_write_failure_does_not_stop_the_session_on_an_oversized_line() {
    use std::io::Read;
    use std::os::fd::OwnedFd;
    use std::os::unix::net::UnixStream;
    // A socket pair with no reader left: every write to `writer` fails with EPIPE. This uses
    // only std (no FFI, no `unsafe`).
    let (reader, writer) = UnixStream::pair().expect("socketpair");
    drop(reader);
    let writer: OwnedFd = writer.into();
    let mut child = Command::new(env!("CARGO_BIN_EXE_flawless"))
        .arg("uci")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::from(writer))
        .spawn()
        .expect("spawn flawless");
    let mut stdin = child.stdin.take().expect("stdin piped");
    let stdout = child.stdout.take().expect("stdout piped");
    let mut big = String::from("position startpos moves e2e4");
    while big.len() < 200 * 1024 {
        big.push_str(" e2e4");
    }
    big.push('\n');
    // Written before reading: the engine answers in order and the output is small.
    stdin.write_all(b"uci\ndebug on\n").expect("write uci");
    stdin
        .write_all(big.as_bytes())
        .expect("write oversized line");
    stdin.write_all(b"isready\nquit\n").expect("write isready");
    drop(stdin);
    let mut out = String::new();
    std::io::BufReader::new(stdout)
        .read_to_string(&mut out)
        .unwrap_or_default();
    let status = child.wait().expect("wait");
    assert!(
        out.lines().any(|l| l == "readyok"),
        "no readyok after an oversized line with stderr unwritable"
    );
    assert_eq!(status.code(), Some(0), "exit status with stderr unwritable");
}

/// Regression (F-14): in single-PV mode, a root position with insufficient material returned at
/// once, after one node, with an empty PV, so `bestmove` was the first root move in move order
/// rather than a move from the search. The root must be searched like any other position: the
/// last `info depth` line must carry a non-empty PV whose first move is the `bestmove`.
#[test]
fn insufficient_material_root_is_searched_and_yields_a_pv() {
    for fen in [
        "8/8/8/4k3/8/8/8/4K3 w - - 0 1",   // K v K
        "8/8/8/4k3/8/8/3B4/4K3 w - - 0 1", // K+B v K
        "8/8/8/4k3/8/8/8/3NK3 b - - 0 1",  // K v K+N, black to move
    ] {
        let mut e = Engine::start();
        e.send("uci");
        e.read_until("uciok", Duration::from_secs(10));
        e.send(&format!("position fen {fen}"));
        e.send("go depth 3");
        let lines = e.read_until("bestmove", Duration::from_secs(30));
        let info = lines
            .iter()
            .rev()
            .find(|l| l.starts_with("info depth "))
            .unwrap_or_else(|| panic!("{fen}: no `info depth` line: {lines:?}"));
        let pv: Vec<&str> = info
            .split(" pv ")
            .nth(1)
            .unwrap_or_else(|| panic!("{fen}: no pv in {info}"))
            .split_whitespace()
            .collect();
        assert!(!pv.is_empty(), "{fen}: empty PV: {info}");
        let best = bestmove_line(&lines)
            .trim_start_matches("bestmove ")
            .split(' ')
            .next()
            .unwrap()
            .to_string();
        assert_eq!(pv[0], best, "{fen}: bestmove is not the PV's first move");
        e.quit_and_expect_exit(Duration::from_secs(10));
    }
}

/// Regression (time management): a negative `wtime`/`btime`/`movetime` value used to fail to parse,
/// so the token was dropped and `go` ran with no time limit (it never answered without `stop`).
/// A negative value means the time is already gone, so the engine must answer at once. A
/// positive value above `u64::MAX` must still be accepted as a (huge) limit, not dropped.
#[test]
fn negative_time_values_answer_at_once() {
    for cmd in [
        "go wtime -1000 btime -1000",
        "go movetime -5",
        "go wtime 0 btime -1 winc -3 binc 18446744073709551616",
    ] {
        let mut e = Engine::start();
        e.send("uci");
        e.read_until("uciok", Duration::from_secs(10));
        e.send("position startpos");
        e.send(cmd);
        let lines = e.read_until("bestmove", Duration::from_secs(5));
        let mv = bestmove_line(&lines);
        assert!(mv.starts_with("bestmove "), "{cmd}: no move: {lines:?}");
        e.quit_and_expect_exit(Duration::from_secs(10));
    }
}

/// Runs the engine with its address space limited to `limit_kb` (through `sh`'s `ulimit -v`),
/// feeds `input`, and returns stdout and the exit status. Kills the child after 30 s.
#[cfg(target_os = "linux")]
fn run_under_address_limit(limit_kb: u64, input: &str) -> (String, Option<i32>) {
    use std::io::Read;
    let script = format!("ulimit -v {limit_kb} && exec \"$0\" uci");
    let mut child = Command::new("sh")
        .arg("-c")
        .arg(script)
        .arg(env!("CARGO_BIN_EXE_flawless"))
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .expect("spawn sh");
    let mut stdin = child.stdin.take().expect("stdin piped");
    let mut stdout = child.stdout.take().expect("stdout piped");
    let (tx, rx) = channel::<String>();
    thread::spawn(move || {
        let mut s = String::new();
        let _ = stdout.read_to_string(&mut s);
        let _ = tx.send(s);
    });
    stdin.write_all(input.as_bytes()).expect("write input");
    drop(stdin);
    let out = match rx.recv_timeout(Duration::from_secs(30)) {
        Ok(s) => s,
        Err(_) => {
            let _ = child.kill();
            panic!("engine did not finish under a {limit_kb} KB address limit");
        }
    };
    let status = child.wait().expect("wait");
    (out, status.code())
}

/// Regression (memory): `setoption name Hash value 1024` under a 400 MB address limit made the
/// allocator abort the process (SIGABRT, no `readyok`). The refusal must be reported, the previous
/// table kept, and the engine must keep answering. Start-up with a 50 MB limit must halve the
/// default table instead of aborting, and `go` must still answer with a legal move even when the
/// search thread cannot be created.
#[cfg(target_os = "linux")]
#[test]
fn hash_allocation_refusal_does_not_abort_the_engine() {
    let (out, code) = run_under_address_limit(
        400_000,
        "uci\nsetoption name Hash value 1024\nisready\nposition startpos\ngo depth 3\nquit\n",
    );
    assert_eq!(
        code,
        Some(0),
        "exit status after a refused Hash 1024:\n{out}"
    );
    assert!(
        out.contains("info string option Hash 1024 MiB could not be allocated; keeping 64 MiB"),
        "refusal not reported:\n{out}"
    );
    assert!(out.lines().any(|l| l == "readyok"), "no readyok:\n{out}");
    assert!(
        out.lines().any(|l| l.starts_with("bestmove ")),
        "no bestmove:\n{out}"
    );

    let (out, code) = run_under_address_limit(
        50_000,
        "uci\nisready\nposition startpos\ngo depth 3\nquit\n",
    );
    assert_eq!(
        code,
        Some(0),
        "exit status at start-up under a 50 MB limit:\n{out}"
    );
    assert!(out.lines().any(|l| l == "readyok"), "no readyok:\n{out}");
    let mv = out
        .lines()
        .find_map(|l| l.strip_prefix("bestmove "))
        .unwrap_or_else(|| panic!("no bestmove:\n{out}"));
    let legal = [
        "a2a3", "a2a4", "b2b3", "b2b4", "c2c3", "c2c4", "d2d3", "d2d4", "e2e3", "e2e4", "f2f3",
        "f2f4", "g2g3", "g2g4", "h2h3", "h2h4", "b1a3", "b1c3", "g1f3", "g1h3",
    ];
    assert!(
        legal.iter().any(|m| mv.starts_with(m)),
        "bestmove {mv} is not a legal start move"
    );
}

/// Regression (F-21): when the OS refuses the search thread, the fallback move must respect
/// `go searchmoves`. Reproduced on the code before this fix under `ulimit -v 50000`: the fallback
/// was the first legal move in generation order (`bestmove a2a3`), which `searchmoves d2d4` excludes.
#[cfg(target_os = "linux")]
#[test]
fn spawn_fallback_respects_searchmoves() {
    let (out, code) = run_under_address_limit(
        50_000,
        "uci\nisready\nposition startpos\ngo searchmoves d2d4\nquit\n",
    );
    assert_eq!(code, Some(0), "exit status under the limit:\n{out}");
    assert!(
        out.lines().any(|l| l == "bestmove d2d4"),
        "fallback ignored searchmoves (expected bestmove d2d4):\n{out}"
    );
    assert!(
        out.lines()
            .any(|l| l.starts_with("info string search thread unavailable")),
        "refused thread was not announced on stdout:\n{out}"
    );
}

/// Kills and reaps the child when it goes out of scope, so a failing assertion cannot leave an engine
/// running (the `Engine` harness does the same for the other tests).
#[cfg(target_os = "linux")]
struct KillOnDrop(std::process::Child);

#[cfg(target_os = "linux")]
impl Drop for KillOnDrop {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

/// Regression (F-22): when the OS refuses the search thread, `go infinite` must hold its bestmove
/// until `stop`, as the normal search does. The fallback used to print `bestmove` at once.
#[cfg(target_os = "linux")]
#[test]
fn refused_thread_holds_bestmove_for_go_infinite_until_stop() {
    use std::io::{BufRead, BufReader, Write};
    use std::sync::mpsc::RecvTimeoutError;

    let child = Command::new("sh")
        .arg("-c")
        .arg("ulimit -v 50000 && exec \"$0\" uci")
        .arg(env!("CARGO_BIN_EXE_flawless"))
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .expect("spawn flawless under a 50 MB address limit");
    let mut child = KillOnDrop(child);
    let mut stdin = child.0.stdin.take().expect("stdin piped");
    let stdout = child.0.stdout.take().expect("stdout piped");
    let (tx, rx) = channel::<String>();
    thread::spawn(move || {
        for line in BufReader::new(stdout).lines() {
            match line {
                Ok(l) => {
                    if tx.send(l).is_err() {
                        break;
                    }
                }
                Err(_) => break,
            }
        }
    });
    let wait_for = |prefix: &str, limit: Duration| -> Option<String> {
        let end = Instant::now() + limit;
        loop {
            let left = end.saturating_duration_since(Instant::now());
            match rx.recv_timeout(left) {
                Ok(l) if l.starts_with(prefix) => return Some(l),
                Ok(_) => {}
                Err(RecvTimeoutError::Timeout) | Err(RecvTimeoutError::Disconnected) => {
                    return None
                }
            }
        }
    };
    stdin
        .write_all(b"uci\nisready\nposition startpos\ngo infinite\n")
        .expect("write");
    stdin.flush().expect("flush");
    assert!(
        wait_for("readyok", Duration::from_secs(10)).is_some(),
        "no readyok under the limit"
    );
    assert!(
        wait_for(
            "info string search thread unavailable",
            Duration::from_secs(10)
        )
        .is_some(),
        "refused thread was not announced on stdout after go infinite"
    );
    // Nothing may answer before `stop`: a `bestmove` here would come before the GUI asked for one.
    let early = wait_for("bestmove", Duration::from_secs(1));
    assert!(
        early.is_none(),
        "bestmove printed before stop during go infinite: {early:?}"
    );
    stdin.write_all(b"stop\n").expect("write stop");
    stdin.flush().expect("flush");
    let answer = wait_for("bestmove", Duration::from_secs(10));
    assert!(
        answer.is_some(),
        "no bestmove after stop with the search thread refused"
    );
    stdin.write_all(b"quit\n").expect("write quit");
    stdin.flush().expect("flush");
}

/// Regression (F-50 follow-up, 2026-11-21): when the OS refuses the search thread, a clock-limited
/// `go ponder` has no search to wait for. Its fallback answer must come at `ponderhit`, not at
/// `stop`: the GUI sends `ponderhit` and then waits for a `bestmove`. A bare `go ponder` (no limit)
/// keeps holding until `stop`, as the normal search does.
#[cfg(target_os = "linux")]
#[test]
fn refused_thread_answers_go_ponder_with_clock_at_ponderhit() {
    use std::io::{BufRead, BufReader, Write};
    use std::sync::mpsc::RecvTimeoutError;

    let child = Command::new("sh")
        .arg("-c")
        .arg("ulimit -v 50000 && exec \"$0\" uci")
        .arg(env!("CARGO_BIN_EXE_flawless"))
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .expect("spawn flawless under a 50 MB address limit");
    let mut child = KillOnDrop(child);
    let mut stdin = child.0.stdin.take().expect("stdin piped");
    let stdout = child.0.stdout.take().expect("stdout piped");
    let (tx, rx) = channel::<String>();
    thread::spawn(move || {
        for line in BufReader::new(stdout).lines() {
            match line {
                Ok(l) => {
                    if tx.send(l).is_err() {
                        break;
                    }
                }
                Err(_) => break,
            }
        }
    });
    let wait_for = |prefix: &str, limit: Duration| -> Option<String> {
        let end = Instant::now() + limit;
        loop {
            let left = end.saturating_duration_since(Instant::now());
            match rx.recv_timeout(left) {
                Ok(l) if l.starts_with(prefix) => return Some(l),
                Ok(_) => {}
                Err(RecvTimeoutError::Timeout) | Err(RecvTimeoutError::Disconnected) => {
                    return None
                }
            }
        }
    };
    let send = |stdin: &mut std::process::ChildStdin, text: &str| {
        stdin.write_all(text.as_bytes()).expect("write");
        stdin.flush().expect("flush");
    };
    send(
        &mut stdin,
        "uci\nisready\nposition startpos\ngo ponder wtime 60000 btime 60000\n",
    );
    assert!(
        wait_for("readyok", Duration::from_secs(10)).is_some(),
        "no readyok under the limit"
    );
    assert!(
        wait_for(
            "info string search thread unavailable",
            Duration::from_secs(10)
        )
        .is_some(),
        "refused thread was not announced on stdout after go ponder"
    );
    let early = wait_for("bestmove", Duration::from_millis(500));
    assert!(
        early.is_none(),
        "bestmove printed before ponderhit during go ponder: {early:?}"
    );
    send(&mut stdin, "ponderhit\n");
    let answer = wait_for("bestmove", Duration::from_secs(10));
    assert!(
        answer.is_some(),
        "no bestmove after ponderhit with the search thread refused (clock-limited ponder)"
    );
    send(&mut stdin, "quit\n");
}

/// Regression (F-26): `position startpos e2e4` (a missing `moves`) used to search the start
/// position and drop `e2e4` without a notice. It is refused like any other bad `position`: a
/// visible `info string position error`, and `go` answers `bestmove 0000` until a valid position.
#[test]
fn startpos_with_tokens_before_moves_is_refused_visibly() {
    let mut e = Engine::start();
    e.send("uci");
    e.read_until("uciok", Duration::from_secs(10));
    e.send("position startpos e2e4");
    e.send("go depth 1");
    let lines = e.read_until("bestmove", Duration::from_secs(10));
    assert!(
        lines
            .iter()
            .any(|l| l.starts_with("info string position error")),
        "no visible notice for `position startpos e2e4`: {lines:?}"
    );
    assert_eq!(bestmove_line(&lines), "bestmove 0000", "{lines:?}");
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// Regression (F-26): an unknown option was reported only on stderr (and only when stderr logging
/// was on). It now gets a UCI-visible notice on stdout, as the other rejected input does.
#[test]
fn unknown_option_is_reported_on_stdout() {
    let mut e = Engine::start();
    e.send("uci");
    e.read_until("uciok", Duration::from_secs(10));
    e.send("setoption name Clear Hash");
    e.send("isready");
    let lines = e.read_until("readyok", Duration::from_secs(10));
    assert!(
        lines
            .iter()
            .any(|l| l.starts_with("info string unknown option")),
        "no notice for an unknown option: {lines:?}"
    );
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// Regression (F-26): `go depth movetime 100` (a missing depth value) consumed `movetime` as the
/// value, so `100` was then skipped and the search had no limit until `stop`; nothing was reported.
/// Now the missing value is reported on stdout and the keyword is kept: the search ends at 100 ms.
#[test]
fn go_bad_value_is_reported_and_the_next_keyword_survives() {
    let mut e = Engine::start();
    e.send("uci");
    e.read_until("uciok", Duration::from_secs(10));
    e.send("position startpos");
    let start = std::time::Instant::now();
    e.send("go depth movetime 100");
    let lines = e.read_until("bestmove", Duration::from_secs(10));
    let ms = start.elapsed().as_millis() as u64;
    assert!(
        lines.iter().any(|l| l.starts_with("info string go depth")),
        "missing depth value not reported: {lines:?}"
    );
    assert!(
        ms < 5_000,
        "movetime was lost: bestmove after {ms} ms (expected about 100 ms)"
    );
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// Regression (F-26): `go mate N` is a standard UCI option this engine does not implement. It was
/// skipped on stderr only, so the GUI saw an unexplained unbounded search. The ignored token is now
/// reported on stdout, and the rest of the command (here `movetime`) still applies.
#[test]
fn unsupported_go_mate_is_reported_on_stdout() {
    let mut e = Engine::start();
    e.send("uci");
    e.read_until("uciok", Duration::from_secs(10));
    e.send("position startpos");
    e.send("go mate 3 movetime 100");
    let lines = e.read_until("bestmove", Duration::from_secs(10));
    assert!(
        lines
            .iter()
            .any(|l| l.starts_with("info string go token ignored: mate")),
        "`go mate` was not reported: {lines:?}"
    );
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// Regression (audit 2026-11-21, "one node" report): a fixed-depth search from a mate-in-one
/// position must run (more than one node, depth lines up to the requested depth), report the mate,
/// and answer with the mating move. The earlier report came from a harness that sent `quit` right
/// after `go`; this test waits for `bestmove` as a GUI does.
#[test]
fn fixed_depth_search_finds_mate_in_one_and_reports_depth_lines() {
    let mut e = Engine::start();
    e.send("uci");
    e.read_until("uciok", Duration::from_secs(10));
    e.send("position fen 6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1");
    e.send("go depth 4");
    let lines = e.read_until("bestmove", Duration::from_secs(30));
    assert_eq!(bestmove_line(&lines), "bestmove a1a8", "{lines:?}");
    let completed = lines
        .iter()
        .rev()
        .find(|l| l.starts_with("info depth "))
        .unwrap_or_else(|| panic!("no completed depth line: {lines:?}"));
    assert!(
        reports_mate_in(completed, 1),
        "the completed iteration did not report the mate: {completed}"
    );
    assert!(
        info_nodes(completed).is_some_and(|n| n > 1),
        "the mate search did not visit multiple nodes: {completed}"
    );
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// Regression (audit 2026-11-21, F-26 class): a malformed `setoption` (no `name`, or no option
/// name) was dropped without a word. It now gets a UCI-visible notice on stdout.
#[test]
fn malformed_setoption_is_reported_on_stdout() {
    let mut e = Engine::start();
    e.send("uci");
    e.read_until("uciok", Duration::from_secs(10));
    e.send("setoption");
    e.send("setoption value 1");
    e.send("setoption name");
    e.send("isready");
    let lines = e.read_until("readyok", Duration::from_secs(10));
    assert!(
        lines
            .iter()
            .any(|l| l.starts_with("info string setoption expects")),
        "no notice for a setoption without `name`: {lines:?}"
    );
    assert!(
        lines
            .iter()
            .any(|l| l.starts_with("info string setoption names no option")),
        "no notice for a setoption with an empty name: {lines:?}"
    );
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// Regression (audit 2026-11-21, F-26 class): `go searchmoves` with no move after it was silently a
/// full-width search. The search still runs (all legal moves), and the choice is announced.
#[test]
fn bare_searchmoves_is_announced_and_searches_all_moves() {
    let mut e = Engine::start();
    e.send("uci");
    e.read_until("uciok", Duration::from_secs(10));
    e.send("position startpos");
    e.send("go searchmoves depth 2");
    let lines = e.read_until("bestmove", Duration::from_secs(20));
    assert!(
        lines
            .iter()
            .any(|l| l.starts_with("info string searchmoves names no move")),
        "bare searchmoves was not announced: {lines:?}"
    );
    let best = bestmove_line(&lines);
    assert!(
        best.len() >= 13 && best != "bestmove 0000",
        "bare searchmoves should search all legal moves: {best}"
    );
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// Regression (audit 2026-11-21, F-26 class): a bare `position`, or `position moves ...` with no
/// `startpos` or `fen`, was silent (the bare form kept the old position; the other searched the start
/// position). Both are now refused with a visible notice, and `go` answers `bestmove 0000`.
#[test]
fn position_without_startpos_or_fen_is_refused_visibly() {
    let mut e = Engine::start();
    e.send("uci");
    e.read_until("uciok", Duration::from_secs(10));
    e.send("position");
    e.send("position moves e2e4");
    e.send("go depth 1");
    let lines = e.read_until("bestmove", Duration::from_secs(10));
    let notices = lines
        .iter()
        .filter(|l| l.starts_with("info string position error"))
        .count();
    assert_eq!(
        notices, 2,
        "expected a notice for each refused position: {lines:?}"
    );
    assert_eq!(bestmove_line(&lines), "bestmove 0000", "{lines:?}");
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// Regression (audit 2026-11-21): `ucinewgame` replaces the board with the valid start position but
/// kept the stale "position invalid" flag, so the next `go` answered `bestmove 0000` with a valid
/// board. The new game must clear the flag.
#[test]
fn ucinewgame_clears_a_rejected_position() {
    let mut e = Engine::start();
    e.send("uci");
    e.read_until("uciok", Duration::from_secs(10));
    e.send("position fen not/a/fen");
    e.send("ucinewgame");
    e.send("go depth 1");
    let lines = e.read_until("bestmove", Duration::from_secs(20));
    let best = bestmove_line(&lines);
    assert!(
        best != "bestmove 0000" && best.len() >= 13,
        "ucinewgame kept the rejected-position flag: {best}"
    );
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// Regression (F-30): every refused `position` was also written to stderr, unconditionally. A GUI
/// that does not read the engine's stderr fills that pipe after a few hundred refusals; the engine
/// then blocks on the write and stops answering (reproduced at 1,000 refusals on f4b2a9e). The
/// engine now writes stderr only after `debug on`; the notice is always on stdout. This test keeps
/// stderr piped and never reads it.
#[test]
fn refused_positions_do_not_block_when_stderr_is_not_drained() {
    use std::io::{BufRead, BufReader, Write};
    use std::sync::mpsc::RecvTimeoutError;

    // An en passant square that no double pawn push could create: refused on every `position`.
    const REFUSED: &str = "6q1/p2r3R/4B3/2nN1K2/8/q7/4k3/1n6 w kq a1 -1 1";
    let mut child = Command::new(env!("CARGO_BIN_EXE_flawless"))
        .arg("uci")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped()) // deliberately never read
        .spawn()
        .expect("spawn flawless");
    let mut stdin = child.stdin.take().expect("stdin piped");
    let stdout = child.stdout.take().expect("stdout piped");
    let (tx, rx) = channel::<String>();
    thread::spawn(move || {
        for line in BufReader::new(stdout).lines() {
            match line {
                Ok(l) => {
                    if tx.send(l).is_err() {
                        break;
                    }
                }
                Err(_) => break,
            }
        }
    });
    let wait_for = |prefix: &str| -> String {
        loop {
            match rx.recv_timeout(Duration::from_secs(10)) {
                Ok(l) if l.starts_with(prefix) => return l,
                Ok(_) => {}
                Err(RecvTimeoutError::Timeout) => {
                    panic!("no `{prefix}` within 10 s (engine blocked on stderr?)")
                }
                Err(RecvTimeoutError::Disconnected) => panic!("engine closed stdout"),
            }
        }
    };
    stdin.write_all(b"uci\n").expect("write uci");
    stdin.flush().expect("flush");
    wait_for("uciok");
    for i in 0..1500 {
        stdin
            .write_all(format!("position fen {REFUSED}\ngo depth 1\n").as_bytes())
            .expect("write");
        stdin.flush().expect("flush");
        let answer = wait_for("bestmove");
        assert_eq!(answer, "bestmove 0000", "refusal #{i} must answer 0000");
    }
    stdin.write_all(b"quit\n").expect("write quit");
    stdin.flush().expect("flush");
    drop(stdin);
    let status = child.wait().expect("wait");
    assert_eq!(status.code(), Some(0), "exit status after 1500 refusals");
}

/// Regression (F-39): an out-of-range `go depth` or `go nodes` value was ignored with a notice,
/// which left the search unlimited (`go` alone), so `go depth 4294967296` ran until `stop`.
/// Digit-only overflow now saturates like the time values do: depth to 64, nodes to `u64::MAX`.
/// The search is not stopped here: a depth- or node-limited search must end by itself. K v K
/// from `k7/8/8/8/8/8/8/K7 w` ends at depth 64 in well under a second.
#[test]
fn out_of_range_go_depth_and_nodes_saturate_instead_of_being_ignored() {
    for cmd in [
        "go depth 4294967296",
        "go depth 99999999999999999999",
        "go nodes 18446744073709551616",
    ] {
        let mut e = Engine::start();
        e.send("isready");
        e.read_until("readyok", Duration::from_secs(10));
        e.send("position fen k7/8/8/8/8/8/8/K7 w - - 0 1");
        e.send(cmd);
        // No `stop` is sent: a limited search answers by itself, an unlimited one would time out.
        let lines = e.read_until("bestmove", Duration::from_secs(20));
        assert!(
            !lines.iter().any(|l| l.starts_with("info string go")),
            "{cmd}: the value must be accepted, not reported as ignored: {lines:?}"
        );
        assert!(
            lines.iter().any(|l| l.starts_with("info depth 64 ")),
            "{cmd}: the search must reach depth 64 (the clamp): {lines:?}"
        );
        e.quit_and_expect_exit(Duration::from_secs(10));
    }
}

/// Regression (F-39): a negative `go depth` or `go nodes` value used to be ignored and left the
/// search unlimited. It now means the smallest limit: depth clamps to 1, nodes saturate to 0 (the
/// same rule as a negative time), so the search answers at once without a `stop`.
#[test]
fn negative_go_depth_and_nodes_answer_at_once() {
    for cmd in ["go depth -4294967296", "go depth -1", "go nodes -1"] {
        let mut e = Engine::start();
        e.send("isready");
        e.read_until("readyok", Duration::from_secs(10));
        e.send("position startpos");
        e.send(cmd);
        let lines = e.read_until("bestmove", Duration::from_secs(20));
        assert!(
            !lines.iter().any(|l| l.starts_with("info string go")),
            "{cmd}: the value must be accepted, not reported as ignored: {lines:?}"
        );
        assert!(
            !bestmove_line(&lines).starts_with("bestmove 0000"),
            "{cmd}: the start position has legal moves: {lines:?}"
        );
        e.quit_and_expect_exit(Duration::from_secs(10));
    }
}

/// Regression (F-41): futility pruning at depth <= 2 ignored a mate-score alpha. With alpha at a
/// mate-in-3 value, every quiet line looked futile, so the quiet mate in two `c5g5` (1. Rg5 Kh3
/// 2. Rh1#) was pruned and the engine reported `mate 3` through `c5c3`. Now the search reports
/// the shorter mate: `score mate 2` and `bestmove c5g5` at depth 6.
#[test]
fn quiet_mate_in_two_is_not_pruned_by_a_mate_alpha() {
    let mut e = Engine::start();
    e.send("isready");
    e.read_until("readyok", Duration::from_secs(10));
    e.send("position fen 8/3K4/8/2R5/8/8/7k/1R6 w - - 0 1");
    e.send("go depth 6");
    let lines = e.read_until("bestmove", Duration::from_secs(60));
    let last = lines
        .iter()
        .rev()
        .find(|l| l.starts_with("info depth 6 "))
        .unwrap_or_else(|| panic!("no depth-6 line: {lines:?}"));
    assert!(
        reports_mate_in(last, 2),
        "the shortest mate is mate in 2 (1. Rg5 Kh3 2. Rh1#): {last}"
    );
    assert!(
        bestmove_line(&lines).starts_with("bestmove c5g5"),
        "the mate in two is c5g5: {lines:?}"
    );
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// F-56: LMR used to reduce this late quiet checking move and miss a proven mate in two in a
/// legal middlegame. The independent python-chess proof is 1. Qc6+ Ka5 2. Ra1#; the reduced
/// search reported only a centipawn score at depth 6. Checking moves are now searched unreduced.
#[test]
fn late_quiet_checking_move_is_not_reduced_past_a_forced_mate() {
    let fen = "r4b2/p3p3/n2pP3/4Pp1q/k4P1P/2P1KQp1/1BP1NR2/5R2 w - - 0 51";
    let mut e = Engine::start();
    e.send("isready");
    e.read_until("readyok", Duration::from_secs(10));
    e.send(&format!("position fen {fen}"));
    e.send("go depth 6");
    let lines = e.read_until("bestmove", Duration::from_secs(60));
    let last = lines
        .iter()
        .rev()
        .find(|l| l.starts_with("info depth 6 "))
        .unwrap_or_else(|| panic!("no depth-6 line: {lines:?}"));
    assert!(
        reports_mate_in(last, 2),
        "the proven mate in two must be found at depth 6: {last}"
    );
    assert!(
        bestmove_line(&lines).starts_with("bestmove f3c6"),
        "Qc6+ is the proven mating move: {lines:?}"
    );
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// F-59: in a sparse endgame, a late quiet move that leaves at most two legal replies can be a
/// forcing threat even without check. Preserve it from LMR so a concrete mate in two is not
/// hidden at depth 6. The expected line was independently verified with python-chess.
#[test]
fn sparse_forcing_quiet_move_is_not_reduced() {
    let fen = "8/8/3K4/1k5p/5p2/1pr4b/6r1/8 b - - 7 68";
    let mut e = Engine::start();
    e.send("isready");
    e.read_until("readyok", Duration::from_secs(10));
    e.send(&format!("position fen {fen}"));
    e.send("go depth 6");
    let lines = e.read_until("bestmove", Duration::from_secs(60));
    let last = lines
        .iter()
        .rev()
        .find(|l| l.starts_with("info depth 6 "))
        .unwrap_or_else(|| panic!("no depth-6 line: {lines:?}"));
    assert!(
        reports_mate_in(last, 2),
        "mate in two must be found: {last}"
    );
    assert!(
        bestmove_line(&lines).starts_with("bestmove g2e2"),
        "Re2 is the proven mating move: {lines:?}"
    );
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// F-60: low-material quiet root moves leaving at most four legal replies can be mating threats.
/// These two legal-game positions have independent python-chess mate-in-two proofs; root LMR
/// misses them at depth 6, while the root-only low-reply safeguard recovers the forced mates.
#[test]
fn low_reply_quiet_mate_threats_are_not_reduced() {
    let cases = [
        ("8/4k3/6p1/1p2p2r/n6p/7P/r7/3K4 b - - 9 107", "h5g5"),
        ("8/2p2r2/6k1/3p4/1p4Kp/1P4nP/8/1N6 b - - 7 36", "g3h5"),
    ];
    let mut e = Engine::start();
    e.send("isready");
    e.read_until("readyok", Duration::from_secs(10));
    for (fen, mating_move) in cases {
        e.send("ucinewgame");
        e.send(&format!("position fen {fen}"));
        e.send("go depth 6");
        let lines = e.read_until("bestmove", Duration::from_secs(60));
        let last = lines
            .iter()
            .rev()
            .find(|l| l.starts_with("info depth 6 "))
            .unwrap_or_else(|| panic!("no depth-6 line for {fen}: {lines:?}"));
        assert!(
            reports_mate_in(last, 2),
            "independent mate-in-two proof must be found for {fen}: {last}"
        );
        assert!(
            bestmove_line(&lines).starts_with(&format!("bestmove {mating_move}")),
            "wrong mating move for {fen}: {lines:?}"
        );
    }
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// F-61: this legal 13-piece position has a quiet pawn push that threatens Qe2# against each of
/// White's ten legal replies. Root LMR missed the mate at depth 6 (but found it at depth 7); the
/// root low-material reply guard now preserves the depth-6 proof. Python-chess exhaustively
/// verified every reply and the final checkmate.
#[test]
fn root_quiet_mate_threat_with_ten_replies_is_not_reduced() {
    let fen = "r3k3/pb1p4/6p1/2P5/2Pp2P1/5q2/3B4/4K3 b - - 1 23";
    let mut e = Engine::start();
    e.send("isready");
    e.read_until("readyok", Duration::from_secs(10));
    e.send(&format!("position fen {fen}"));
    e.send("go depth 6");
    let lines = e.read_until("bestmove", Duration::from_secs(60));
    let last = lines
        .iter()
        .rev()
        .find(|l| l.starts_with("info depth 6 "))
        .unwrap_or_else(|| panic!("no depth-6 line: {lines:?}"));
    assert!(
        reports_mate_in(last, 2),
        "the proven mate in two must be found at depth 6: {last}"
    );
    assert!(
        bestmove_line(&lines).starts_with("bestmove d4d3"),
        "the quiet d3 push is the proven mating threat: {lines:?}"
    );
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// F-62: a quiet bishop move in this legal 14-piece position leaves only Kh1, after which Qg2#
/// is forced. Root LMR reduced the late move at depth 6 and reported mate in three, although the
/// same engine proved mate in two at depth 7. The <=14-piece root reply safeguard restores the
/// depth-6 proof; python-chess exhaustively verifies the one-reply mate tree.
#[test]
fn root_quiet_mate_threat_with_one_reply_is_not_reduced() {
    let fen = "2n2b2/1p6/3p1k1r/1n3P1p/1p5P/8/2q3b1/6K1 b - - 2 30";
    let mut e = Engine::start();
    e.send("isready");
    e.read_until("readyok", Duration::from_secs(10));
    e.send(&format!("position fen {fen}"));
    e.send("go depth 6");
    let lines = e.read_until("bestmove", Duration::from_secs(60));
    let last = lines
        .iter()
        .rev()
        .find(|l| l.starts_with("info depth 6 "))
        .unwrap_or_else(|| panic!("no depth-6 line: {lines:?}"));
    assert!(
        reports_mate_in(last, 2),
        "the proven mate in two must be found at depth 6: {last}"
    );
    assert!(
        bestmove_line(&lines).starts_with("bestmove g2h3"),
        "Bh3 is the proven mating threat: {lines:?}"
    );
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// F-63: null-move pruning gave a false fail-high in this eight-piece endgame and hid a forced
/// mate in two at depth 6. The low-material NMP exclusion (now through 13 pieces after F-65)
/// restores the exact proof; python-chess independently verifies the forced line and all seven
/// legal replies.
#[test]
fn null_move_pruning_does_not_hide_sparse_mate_in_two() {
    let fen = "4kr2/7p/1p5K/8/8/4P3/1N4r1/8 b - - 1 28";
    let mut e = Engine::start();
    e.send("isready");
    e.read_until("readyok", Duration::from_secs(10));
    e.send(&format!("position fen {fen}"));
    e.send("go depth 6");
    let lines = e.read_until("bestmove", Duration::from_secs(60));
    let last = lines
        .iter()
        .rev()
        .find(|l| l.starts_with("info depth 6 "))
        .unwrap_or_else(|| panic!("no depth-6 line: {lines:?}"));
    assert!(
        reports_mate_in(last, 2),
        "the proven mate in two must be found at depth 6: {last}"
    );
    assert!(
        bestmove_line(&lines).starts_with("bestmove f8f3"),
        "the rook move is the proven mate-in-two threat: {lines:?}"
    );
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// F-64: this legal 14-piece position has a quiet queen move that leaves eleven legal replies;
/// every reply permits mate on the next move. The previous <=10-reply root safeguard reduced it,
/// so depth 6 reported mate in four instead of the oracle-proven mate in two. Extending that
/// narrowly scoped threshold restores the proof; python-chess independently verifies all eleven
/// replies and their mating continuations.
#[test]
fn root_quiet_mate_threat_with_eleven_replies_is_not_reduced() {
    let fen = "6k1/r7/2p2p2/1p2r3/3q4/N4PP1/2P4P/5K1R b - - 2 20";
    let mut e = Engine::start();
    e.send("isready");
    e.read_until("readyok", Duration::from_secs(10));
    e.send(&format!("position fen {fen}"));
    e.send("go depth 6");
    let lines = e.read_until("bestmove", Duration::from_secs(60));
    let last = lines
        .iter()
        .rev()
        .find(|l| l.starts_with("info depth 6 "))
        .unwrap_or_else(|| panic!("no depth-6 line: {lines:?}"));
    assert!(
        reports_mate_in(last, 2),
        "the proven mate in two must be found at depth 6: {last}"
    );
    assert!(
        bestmove_line(&lines).starts_with("bestmove d4d2"),
        "Qd2 is the proven mating threat: {lines:?}"
    );
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// F-65: a null-move fail-high in this 13-piece legal endgame masked a forced mate in two.
/// Disabling NMP through 13 pieces restores `...Rh2` and the oracle-proven mate at depth 6;
/// python-chess verifies the move against all fifteen legal replies.
#[test]
fn null_move_pruning_does_not_hide_thirteen_piece_mate_in_two() {
    let fen = "1n5r/3kp3/3Np3/8/6P1/1P1P4/2P5/rN2K3 b - - 0 21";
    let mut e = Engine::start();
    e.send("isready");
    e.read_until("readyok", Duration::from_secs(10));
    e.send(&format!("position fen {fen}"));
    e.send("go depth 6");
    let lines = e.read_until("bestmove", Duration::from_secs(60));
    let last = lines
        .iter()
        .rev()
        .find(|l| l.starts_with("info depth 6 "))
        .unwrap_or_else(|| panic!("no depth-6 line: {lines:?}"));
    assert!(
        reports_mate_in(last, 2),
        "the proven mate in two must be found at depth 6: {last}"
    );
    assert!(
        bestmove_line(&lines).starts_with("bestmove h8h2"),
        "Rh2 is the proven mating move: {lines:?}"
    );
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// F-57: once a single-PV iteration proves a mate in one, deeper iterations cannot improve on
/// that maximum root score. This legal position has 1. Qbe5#; `go depth 6` must stop after the
/// proof instead of needlessly searching several more plies.
#[test]
fn proven_mate_in_one_stops_deeper_single_pv_iterations() {
    let fen = "1Q4n1/6Qr/4k3/7p/2N2B1p/1K3N2/nR6/8 w - - 2 61";
    let mut e = Engine::start();
    e.send("isready");
    e.read_until("readyok", Duration::from_secs(10));
    e.send(&format!("position fen {fen}"));
    e.send("go depth 6");
    let lines = e.read_until("bestmove", Duration::from_secs(15));
    let mate = lines.iter().find(|l| l.starts_with("info depth 1 "));
    assert!(
        mate.is_some_and(|line| reports_mate_in(line, 1)),
        "the independent legal-move proof is mate in one: {lines:?}"
    );
    assert!(
        bestmove_line(&lines).starts_with("bestmove b8e5"),
        "Qbe5# is the proven mate: {lines:?}"
    );
    let deeper_iterations: Vec<_> = lines
        .iter()
        .filter_map(|line| {
            line.strip_prefix("info depth ")?
                .split_whitespace()
                .next()?
                .parse::<u32>()
                .ok()
        })
        .filter(|&depth| depth > 1)
        .collect();
    assert!(
        deeper_iterations.is_empty(),
        "finite single-PV search continued after proving mate in one: {lines:?}"
    );
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// `go infinite` must keep searching until `stop`, even after proving a mate in one. The exact
/// mate is already a bestmove proof, but infinite mode is an explicit request for continued
/// analysis; an early single-PV completion must not silently turn it into a finite search.
#[test]
fn go_infinite_continues_after_proving_mate_in_one() {
    let fen = "1Q4n1/6Qr/4k3/7p/2N2B1p/1K3N2/nR6/8 w - - 2 61";
    let mut e = Engine::start();
    e.send("isready");
    e.read_until("readyok", Duration::from_secs(10));
    e.send(&format!("position fen {fen}"));
    e.send("go infinite");
    let depth_two = e.read_until("info depth 2 ", Duration::from_secs(15));
    assert!(
        depth_two
            .iter()
            .any(|line| line.starts_with("info depth 2 ")),
        "infinite search should continue beyond the mate-in-one proof: {depth_two:?}"
    );
    e.send("stop");
    let stopped = e.read_until("bestmove", Duration::from_secs(10));
    assert!(
        bestmove_line(&stopped).starts_with("bestmove b8e5"),
        "bestmove should still be the proven mate: {stopped:?}"
    );
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// Pondering remains an unbounded search until `ponderhit` or `stop`; a proven mate-in-one
/// must not make the engine silently stop pondering before the GUI reports the opponent's move.
#[test]
fn go_ponder_continues_after_proving_mate_in_one() {
    let fen = "1Q4n1/6Qr/4k3/7p/2N2B1p/1K3N2/nR6/8 w - - 2 61";
    let mut e = Engine::start();
    e.send("isready");
    e.read_until("readyok", Duration::from_secs(10));
    e.send(&format!("position fen {fen}"));
    e.send("go ponder");
    let depth_two = e.read_until("info depth 2 ", Duration::from_secs(15));
    assert!(
        depth_two
            .iter()
            .any(|line| line.starts_with("info depth 2 ")),
        "ponder search should continue beyond the mate-in-one proof: {depth_two:?}"
    );
    e.send("stop");
    let stopped = e.read_until("bestmove", Duration::from_secs(10));
    assert!(
        bestmove_line(&stopped).starts_with("bestmove b8e5"),
        "bestmove should still be the proven mate: {stopped:?}"
    );
    e.quit_and_expect_exit(Duration::from_secs(10));
}

/// True when an `info` line reports exactly `score mate <n>`. A substring test is not enough:
/// `score mate 30` contains `score mate 3`.
fn reports_mate_in(line: &str, n: i32) -> bool {
    let mut tokens = line.split_whitespace();
    while let Some(t) = tokens.next() {
        if t == "score" {
            return tokens.next() == Some("mate")
                && tokens.next().and_then(|v| v.parse::<i32>().ok()) == Some(n);
        }
    }
    false
}

#[test]
fn mate_score_is_compared_as_a_whole_token() {
    assert!(reports_mate_in("info depth 6 score mate 3 pv a1a2", 3));
    assert!(!reports_mate_in("info depth 6 score mate 30 pv a1a2", 3));
    assert!(!reports_mate_in("info depth 6 score mate -3 pv a1a2", 3));
    assert!(!reports_mate_in("info depth 6 score cp 300 pv a1a2", 3));
    assert!(reports_mate_in("info depth 6 score mate 1", 1));
    assert!(!reports_mate_in("info depth 6 score mate 10", 1));
}

/// F-44: in sparse positions the depth-6 search missed quiet mates in three. Every position below
/// has a forced mate in three (checked by an independent proof verifier with python-chess); before
/// the fix the engine reported `cp ~1300` or `mate 4`. The first one is 1. Kd6 Kxa7 2. Kc7 Ka8
/// 3. Ra1#. Both must report `score mate 3` (the exact distance) at depth 6.
#[test]
fn sparse_quiet_mate_in_three_is_found_at_depth_six() {
    let cases = [
        "k1B5/B7/8/2K5/8/8/8/2R5 w - - 0 1",
        "8/7k/8/r7/6K1/q7/8/8 b - - 0 1",
    ];
    for fen in cases {
        let mut e = Engine::start();
        e.send("isready");
        e.read_until("readyok", Duration::from_secs(10));
        e.send(&format!("position fen {fen}"));
        e.send("go depth 6");
        let lines = e.read_until("bestmove", Duration::from_secs(60));
        let last = lines
            .iter()
            .rev()
            .find(|l| l.starts_with("info depth 6 "))
            .unwrap_or_else(|| panic!("no depth-6 line for {fen}: {lines:?}"));
        assert!(
            reports_mate_in(last, 3),
            "{fen}: a forced mate in three exists, the engine must report `score mate 3`: {last}"
        );
        e.quit_and_expect_exit(Duration::from_secs(10));
    }
}
