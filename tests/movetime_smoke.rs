//! Real-process `go movetime` / stop / quit timing tests.
//!
//! Each test runs the actual binary (CARGO_BIN_EXE_flawless) and waits for every reply before
//! sending the next command. `go` and `quit` are never sent in one burst: a quit that arrives
//! during a search stops it, which would make a timing measurement meaningless.
//!
//! Tolerances are deliberately loose so CI scheduling noise (Windows timer granularity, shared
//! runners) does not cause flakes, while still catching the earlier defect where a 1 s movetime
//! returned after 0.4 s or less.

use std::io::{BufRead, BufReader, Write};
use std::process::{Child, Command, Stdio};
use std::sync::mpsc::{channel, Receiver, RecvTimeoutError};
use std::sync::{Mutex, MutexGuard};
use std::thread;
use std::time::{Duration, Instant};

/// Timing tests run one at a time: cargo runs test functions in parallel, and several engines
/// competing for a 2-vCPU runner would skew the measured search times.
static TIMING: Mutex<()> = Mutex::new(());

fn timing_lock() -> MutexGuard<'static, ()> {
    TIMING.lock().unwrap_or_else(|e| e.into_inner())
}

const START_FEN: &str = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

struct Engine {
    child: Child,
    rx: Receiver<String>,
    seen: Vec<String>,
}

impl Engine {
    fn spawn() -> Self {
        let mut child = Command::new(env!("CARGO_BIN_EXE_flawless"))
            .arg("uci")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .expect("spawn flawless");
        let stdout = child.stdout.take().expect("stdout piped");
        let (tx, rx) = channel();
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
        Engine {
            child,
            rx,
            seen: Vec::new(),
        }
    }

    fn send(&mut self, cmd: &str) {
        let stdin = self.child.stdin.as_mut().expect("stdin piped");
        stdin
            .write_all(format!("{cmd}\n").as_bytes())
            .expect("write");
        stdin.flush().expect("flush");
    }

    /// Read lines until one satisfies `pred`, or fail after `timeout`.
    fn until(&mut self, timeout: Duration, what: &str, pred: impl Fn(&str) -> bool) -> Duration {
        let start = Instant::now();
        loop {
            let remaining = timeout.checked_sub(start.elapsed()).unwrap_or_else(|| {
                panic!(
                    "timed out after {timeout:?} waiting for {what}; stdout: {:?}",
                    self.tail()
                )
            });
            match self.rx.recv_timeout(remaining) {
                Ok(line) => {
                    assert!(!line.contains("panicked"), "panic marker on stdout: {line}");
                    let hit = pred(&line);
                    self.seen.push(line);
                    if hit {
                        return start.elapsed();
                    }
                }
                Err(RecvTimeoutError::Timeout) => {}
                Err(RecvTimeoutError::Disconnected) => {
                    panic!(
                        "engine closed stdout while waiting for {what}; stdout: {:?}",
                        self.tail()
                    )
                }
            }
        }
    }

    fn tail(&self) -> Vec<String> {
        self.seen.iter().rev().take(5).rev().cloned().collect()
    }

    /// Moves every line already received (without blocking) into `seen`, so pre-stop checks see
    /// output that arrived during a sleep.
    fn drain(&mut self) {
        while let Ok(line) = self.rx.try_recv() {
            assert!(!line.contains("panicked"), "panic marker on stdout: {line}");
            self.seen.push(line);
        }
    }

    fn handshake(&mut self) {
        self.send("uci");
        self.until(Duration::from_secs(10), "uciok", |l| l == "uciok");
        self.send("isready");
        self.until(Duration::from_secs(10), "readyok", |l| l == "readyok");
    }

    fn position(&mut self, fen: &str) {
        self.send(&format!("position fen {fen}"));
        self.send("isready");
        self.until(Duration::from_secs(10), "readyok after position", |l| {
            l == "readyok"
        });
    }

    /// Start a search and return (elapsed until bestmove, bestmove token).
    fn go_until_bestmove(&mut self, go: &str, timeout: Duration) -> (Duration, String) {
        self.send(go);
        let start = Instant::now();
        self.until(timeout, "bestmove", |l| l.starts_with("bestmove"));
        let dt = start.elapsed();
        let mv = self
            .seen
            .iter()
            .rev()
            .find(|l| l.starts_with("bestmove"))
            .and_then(|l| l.split_whitespace().nth(1))
            .unwrap_or_default()
            .to_string();
        (dt, mv)
    }

    fn quit_and_expect_exit(&mut self, timeout: Duration) {
        self.send("quit");
        let start = Instant::now();
        loop {
            if let Some(status) = self.child.try_wait().expect("try_wait") {
                assert!(status.success(), "engine exit status {status:?} after quit");
                return;
            }
            if start.elapsed() > timeout {
                let _ = self.child.kill();
                panic!("engine did not exit within {timeout:?} after quit");
            }
            thread::sleep(Duration::from_millis(5));
        }
    }
}

impl Drop for Engine {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

/// Startpos legal moves via the engine's own CLI (`moves`), so the check does not depend on
/// a hand-written list.
fn legal_startpos_moves() -> Vec<String> {
    use std::io::Write as _;
    let mut child = Command::new(env!("CARGO_BIN_EXE_flawless"))
        .arg("moves")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .expect("spawn moves");
    child
        .stdin
        .as_mut()
        .unwrap()
        .write_all(format!("{START_FEN}\n").as_bytes())
        .unwrap();
    drop(child.stdin.take());
    let out = child.wait_with_output().expect("moves output");
    let text = String::from_utf8_lossy(&out.stdout).to_string();
    let mut it = text.split_whitespace();
    assert_eq!(it.next(), Some("ok"), "moves CLI output: {text:?}");
    it.next(); // move count
    it.map(|s| s.to_string()).collect()
}

fn assert_legal_startpos(mv: &str) {
    let legal = legal_startpos_moves();
    assert!(
        legal.iter().any(|m| m == mv),
        "bestmove {mv} not legal from startpos: {legal:?}"
    );
}

#[test]
fn movetime_uses_its_budget_within_tolerance() {
    let _serial = timing_lock();
    // Before the fix, a 1000 ms movetime often returned after 400-600 ms. Require the search to
    // run for at least 80% of the budget and to finish within 300 ms of it.
    for mt in [200u64, 500, 1000] {
        let mut e = Engine::spawn();
        e.handshake();
        e.position(START_FEN);
        let (dt, mv) = e.go_until_bestmove(&format!("go movetime {mt}"), Duration::from_secs(10));
        let ms = dt.as_millis() as u64;
        assert!(
            ms * 10 >= mt * 8,
            "movetime {mt}: returned after only {ms} ms (< 80%)"
        );
        assert!(
            ms <= mt + 300,
            "movetime {mt}: returned after {ms} ms (overrun)"
        );
        assert_legal_startpos(&mv);
        e.quit_and_expect_exit(Duration::from_secs(5));
    }
}

#[test]
fn movetime_bestmove_reports_a_completed_iteration() {
    let _serial = timing_lock();
    let mut e = Engine::spawn();
    e.handshake();
    e.position(START_FEN);
    let (_dt, mv) = e.go_until_bestmove("go movetime 300", Duration::from_secs(10));
    assert_legal_startpos(&mv);
    assert!(
        e.seen
            .iter()
            .any(|l| l.starts_with("info depth ") && l.contains(" score ")),
        "no completed iteration info before bestmove: {:?}",
        e.tail()
    );
    e.quit_and_expect_exit(Duration::from_secs(5));
}

#[test]
fn very_short_movetime_still_returns_a_legal_move() {
    let _serial = timing_lock();
    for mt in [1u64, 10] {
        let mut e = Engine::spawn();
        e.handshake();
        e.position(START_FEN);
        let (dt, mv) = e.go_until_bestmove(&format!("go movetime {mt}"), Duration::from_secs(5));
        assert!(dt < Duration::from_secs(2), "movetime {mt} took {dt:?}");
        assert_legal_startpos(&mv);
        e.quit_and_expect_exit(Duration::from_secs(5));
    }
}

#[test]
fn explicit_stop_ends_a_long_movetime_promptly() {
    let _serial = timing_lock();
    let mut e = Engine::spawn();
    e.handshake();
    e.position(START_FEN);
    e.send("go movetime 10000");
    thread::sleep(Duration::from_millis(300));
    let start = Instant::now();
    e.send("stop");
    e.until(Duration::from_secs(2), "bestmove after stop", |l| {
        l.starts_with("bestmove")
    });
    assert!(
        start.elapsed() < Duration::from_secs(1),
        "stop latency {:?}",
        start.elapsed()
    );
    e.quit_and_expect_exit(Duration::from_secs(5));
}

#[test]
fn quit_during_movetime_exits_cleanly_and_promptly() {
    let _serial = timing_lock();
    let mut e = Engine::spawn();
    e.handshake();
    e.position(START_FEN);
    e.send("go movetime 10000");
    thread::sleep(Duration::from_millis(300));
    let start = Instant::now();
    e.quit_and_expect_exit(Duration::from_secs(3));
    assert!(start.elapsed() < Duration::from_secs(3));
}

#[test]
fn infinite_then_stop_returns_one_legal_bestmove() {
    let _serial = timing_lock();
    let mut e = Engine::spawn();
    e.handshake();
    e.position(START_FEN);
    e.send("go infinite");
    thread::sleep(Duration::from_millis(400));
    e.drain();
    assert!(
        !e.seen.iter().any(|l| l.starts_with("bestmove")),
        "premature bestmove on infinite"
    );
    let start = Instant::now();
    e.send("stop");
    e.until(Duration::from_secs(2), "bestmove after stop", |l| {
        l.starts_with("bestmove")
    });
    assert!(start.elapsed() < Duration::from_secs(1));
    // readyok is sent after any bestmove the engine still owes, so counting only after it
    // detects a duplicate bestmove.
    e.send("isready");
    e.until(Duration::from_secs(2), "readyok after stop", |l| {
        l == "readyok"
    });
    let bms = e.seen.iter().filter(|l| l.starts_with("bestmove")).count();
    assert_eq!(bms, 1, "expected exactly one bestmove");
    e.quit_and_expect_exit(Duration::from_secs(5));
}

#[test]
fn repeated_movetime_searches_in_one_process() {
    let _serial = timing_lock();
    let mut e = Engine::spawn();
    e.handshake();
    let mut moves = vec![];
    for fen in [START_FEN, "r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", START_FEN] {
        e.position(fen);
        let (dt, mv) = e.go_until_bestmove("go movetime 250", Duration::from_secs(10));
        assert!(
            dt.as_millis() >= 200 && dt.as_millis() <= 600,
            "repeat search took {dt:?}"
        );
        assert!(!mv.is_empty() && mv != "0000", "no move in repeated search");
        moves.push(mv);
    }
    assert_legal_startpos(&moves[0]);
    e.quit_and_expect_exit(Duration::from_secs(5));
}

#[test]
fn terminal_positions_return_null_move_promptly() {
    let _serial = timing_lock();
    // Checkmated and stalemated sides have no legal move: UCI answers `bestmove 0000`.
    for fen in [
        "R5k1/5ppp/8/8/8/8/8/6K1 b - - 0 1",
        "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1",
    ] {
        let mut e = Engine::spawn();
        e.handshake();
        e.position(fen);
        let (dt, mv) = e.go_until_bestmove("go movetime 500", Duration::from_secs(5));
        assert_eq!(mv, "0000", "terminal position {fen}");
        assert!(dt < Duration::from_secs(1), "terminal position took {dt:?}");
        e.quit_and_expect_exit(Duration::from_secs(5));
    }
}

#[test]
fn ponderhit_starts_the_clock_slice_at_the_hit() {
    // Regression (F-24): the clock slice granted at `ponderhit` was measured from `go`, so the
    // time spent pondering on the opponent's clock used it up, and the answer came in a few ms.
    // Our clock only runs during our turn, so with 20 s on the clock (soft budget about 470 ms)
    // the answer after a 3 s ponder must still take a real search after the hit.
    let _serial = timing_lock();
    let mut e = Engine::spawn();
    e.handshake();
    e.position(START_FEN);
    e.send("go ponder wtime 20000 btime 20000 winc 0 binc 0");
    thread::sleep(Duration::from_millis(3000));
    e.drain();
    assert!(
        !e.seen.iter().any(|l| l.starts_with("bestmove")),
        "bestmove before ponderhit"
    );
    let start = Instant::now();
    e.send("ponderhit");
    e.until(Duration::from_secs(10), "bestmove after ponderhit", |l| {
        l.starts_with("bestmove")
    });
    let ms = start.elapsed().as_millis() as u64;
    assert!(
        ms >= 150,
        "ponderhit answered after only {ms} ms: the slice was spent while pondering (F-24)"
    );
    assert!(
        ms <= 2500,
        "ponderhit answered after {ms} ms: the 20 s clock slice was overrun"
    );
    e.quit_and_expect_exit(Duration::from_secs(5));
}

#[test]
fn ponder_movetime_ponderhit_keeps_the_movetime_deadline() {
    // Regression: `ponderhit` used to recalculate the budget from zero clocks (~20 ms), so the
    // search stopped at once. The movetime deadline counts from the start of the search, so a
    // `ponderhit` at ~300 ms of a 1000 ms movetime must answer about 700 ms later.
    let _serial = timing_lock();
    let mut e = Engine::spawn();
    e.handshake();
    e.position(START_FEN);
    e.send("go ponder movetime 1000");
    thread::sleep(Duration::from_millis(300));
    e.drain();
    assert!(
        !e.seen.iter().any(|l| l.starts_with("bestmove")),
        "bestmove before ponderhit"
    );
    let start = Instant::now();
    e.send("ponderhit");
    e.until(Duration::from_secs(5), "bestmove after ponderhit", |l| {
        l.starts_with("bestmove")
    });
    let ms = start.elapsed().as_millis() as u64;
    assert!(
        ms >= 300,
        "ponderhit answered after only {ms} ms (budget collapsed)"
    );
    assert!(
        ms <= 1100,
        "ponderhit answered after {ms} ms (deadline overrun)"
    );
    e.quit_and_expect_exit(Duration::from_secs(5));
}

#[test]
fn bare_go_ponder_keeps_searching_until_stop() {
    // A bare `go ponder` has no time limit: it must not answer on its own, and `ponderhit`
    // must not give it one either (no clock was sent, so the fallback must not install a
    // zero-clock deadline). Only `stop` ends it.
    let _serial = timing_lock();
    let mut e = Engine::spawn();
    e.handshake();
    e.position(START_FEN);
    e.send("go ponder");
    thread::sleep(Duration::from_millis(400));
    e.drain();
    assert!(
        !e.seen.iter().any(|l| l.starts_with("bestmove")),
        "bare go ponder answered before ponderhit"
    );
    e.send("ponderhit");
    thread::sleep(Duration::from_millis(800));
    e.drain();
    assert!(
        !e.seen.iter().any(|l| l.starts_with("bestmove")),
        "bare go ponder answered after ponderhit without stop"
    );
    e.send("stop");
    e.until(Duration::from_secs(2), "bestmove after stop", |l| {
        l.starts_with("bestmove")
    });
    // readyok is sent after any bestmove still owed, so counting after it detects duplicates.
    e.send("isready");
    e.until(Duration::from_secs(2), "readyok after stop", |l| {
        l == "readyok"
    });
    let bms = e.seen.iter().filter(|l| l.starts_with("bestmove")).count();
    assert_eq!(bms, 1, "expected exactly one bestmove");
    e.quit_and_expect_exit(Duration::from_secs(5));
}

#[test]
fn ponder_node_cap_is_enforced_after_ponderhit() {
    // Regression: `go ponder nodes N` keeps `infinite` set while pondering. The ponderhit
    // fallback arm used to leave it set, so the node cap was never checked and the search ran
    // until `stop`. After ponderhit the cap must end the search on its own.
    let _serial = timing_lock();
    let mut e = Engine::spawn();
    e.handshake();
    e.position(START_FEN);
    e.send("go ponder nodes 20000");
    thread::sleep(Duration::from_millis(200));
    e.drain();
    assert!(
        !e.seen.iter().any(|l| l.starts_with("bestmove")),
        "bestmove before ponderhit"
    );
    let start = Instant::now();
    e.send("ponderhit");
    e.until(Duration::from_secs(5), "bestmove from node cap", |l| {
        l.starts_with("bestmove")
    });
    assert!(
        start.elapsed() < Duration::from_secs(4),
        "node cap not enforced after ponderhit: {:?}",
        start.elapsed()
    );
    e.quit_and_expect_exit(Duration::from_secs(5));
}
