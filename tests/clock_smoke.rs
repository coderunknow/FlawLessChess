//! Clock-management smoke: Flawless's own UCI time control handling.
//!
//! Rating games use `go wtime/btime/winc/binc/movestogo` (CCRL-style repeating
//! clock), so before any rating run the engine must (a) accept full clock
//! commands, (b) return a legal-looking bestmove, and (c) respect its time
//! budget — the runner-side bound here is a generous crash net, not a perf test
//! (soft/hard limits per `uci::clock_limits`: soft = t/movestogo + inc/2,
//! hard = min(6*soft, t-30ms)).
//!
//! Runs the actual binary via CARGO_BIN_EXE_flawless.

use std::io::{BufRead, BufReader, Write};
use std::process::{Child, Command, Stdio};
use std::sync::mpsc::{channel, Receiver};
use std::thread;
use std::time::{Duration, Instant};

fn start() -> (Child, Receiver<String>) {
    let bin = env!("CARGO_BIN_EXE_flawless");
    let mut child = Command::new(bin)
        .arg("uci")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .expect("spawn flawless");
    let stdout = child.stdout.take().expect("stdout piped");
    let (tx, rx) = channel();
    thread::spawn(move || {
        let reader = BufReader::new(stdout);
        for line in reader.lines() {
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
    (child, rx)
}

fn send(child: &mut Child, s: &str) {
    let stdin = child.stdin.as_mut().expect("stdin piped");
    stdin.write_all(s.as_bytes()).expect("write stdin");
    stdin.flush().expect("flush stdin");
}

fn wait_for_bestmove(rx: &Receiver<String>, timeout: Duration) -> (String, Duration) {
    let start = Instant::now();
    loop {
        let remaining = timeout
            .checked_sub(start.elapsed())
            .unwrap_or_else(|| panic!("no bestmove within {timeout:?}"));
        match rx.recv_timeout(remaining) {
            Ok(line) => {
                if line.starts_with("info string") && line.contains("panicked") {
                    panic!("panic marker: {line}");
                }
                if line.starts_with("bestmove") {
                    return (line, start.elapsed());
                }
            }
            Err(_) => panic!("no bestmove within {timeout:?}"),
        }
    }
}

fn assert_bestmove_format(line: &str) {
    let mut parts = line.split_whitespace();
    assert_eq!(parts.next(), Some("bestmove"));
    let mv = parts.next().expect("bestmove token");
    assert!(
        mv == "0000" || (mv.len() == 4 || mv.len() == 5),
        "unexpected bestmove token: {mv}"
    );
}

fn kill_and_reap(child: &mut Child) {
    let _ = child.kill();
    let _ = child.wait();
}

#[test]
fn clock_command_returns_bestmove_within_budget() {
    let (mut child, rx) = start();
    send(
        &mut child,
        "uci\nisready\nposition startpos\ngo wtime 3000 btime 3000 winc 0 binc 0 movestogo 40\n",
    );
    // clock_limits (ENGINE-1): reserve 300 ms, usable 2700, soft = 2700/40 = 67 ms, hard = 4*soft = 268 ms.
    let (best, elapsed) = wait_for_bestmove(&rx, Duration::from_secs(3));
    assert_bestmove_format(&best);
    assert!(
        elapsed < Duration::from_millis(2500),
        "engine blew its clock budget: {elapsed:?} for wtime 3000"
    );
    send(&mut child, "quit\n");
    let _ = child.wait();
}

#[test]
fn tight_clock_returns_quickly() {
    let (mut child, rx) = start();
    send(
        &mut child,
        "uci\nisready\nposition startpos\ngo wtime 250 btime 250 winc 0 binc 0 movestogo 40\n",
    );
    // clock_limits (CLOCK-1 floor): reserve 300 ms exceeds 250 ms, usable 0, soft = the 1 ms per-move floor, hard = 1 ms.
    let (best, elapsed) = wait_for_bestmove(&rx, Duration::from_secs(3));
    assert_bestmove_format(&best);
    assert!(
        elapsed < Duration::from_millis(2000),
        "engine ignored a tight clock: {elapsed:?} for wtime 250"
    );
    send(&mut child, "quit\n");
    let _ = child.wait();
}

#[test]
fn clock_with_increment_and_movestogo() {
    let (mut child, rx) = start();
    send(
        &mut child,
        "uci\nisready\nposition startpos moves e2e4 e7e5\ngo wtime 2000 btime 2000 winc 100 binc 100 movestogo 10\n",
    );
    // clock_limits (ENGINE-1): reserve 300 ms, usable 1700, soft = 1700/10 + 100/2 = 220 ms, hard = min(880, 850) = 850 ms.
    let (best, elapsed) = wait_for_bestmove(&rx, Duration::from_secs(5));
    assert_bestmove_format(&best);
    assert!(
        elapsed < Duration::from_millis(4000),
        "engine blew its budget with increment: {elapsed:?}"
    );
    // Continue the clock conversation: the engine must keep answering.
    send(
        &mut child,
        "go wtime 1900 btime 2000 winc 100 binc 100 movestogo 9\n",
    );
    let (best2, _) = wait_for_bestmove(&rx, Duration::from_secs(5));
    assert_bestmove_format(&best2);
    send(&mut child, "quit\n");
    let status = wait_child(child, Duration::from_secs(5));
    assert!(
        status.success(),
        "engine must exit cleanly after clock games"
    );
}

fn wait_child(mut child: Child, timeout: Duration) -> std::process::ExitStatus {
    let start = Instant::now();
    loop {
        match child.try_wait() {
            Ok(Some(status)) => return status,
            Ok(None) => {
                if start.elapsed() > timeout {
                    kill_and_reap(&mut child);
                    panic!("child did not exit within {timeout:?}");
                }
                thread::sleep(Duration::from_millis(5));
            }
            Err(_) => {
                kill_and_reap(&mut child);
                panic!("try_wait failed");
            }
        }
    }
}
