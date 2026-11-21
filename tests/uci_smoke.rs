//! UCI integration smoke: handshake, unknown-command tolerance, deterministic seeded
//! fuzz over a small command grammar, and graceful `quit`.
//!
//! Runs the actual binary via CARGO_BIN_EXE_flawless. Not a comprehensive fuzzer —
//! a regression tripwire so protocol handling cannot silently start crashing.

use std::io::{BufRead, BufReader, Write};
use std::process::{Child, Command, Stdio};
use std::sync::mpsc::{channel, Receiver};
use std::thread;
use std::time::{Duration, Instant};

/// Spawn the engine in explicit `uci` mode (the historical harness default).
fn start() -> (Child, Receiver<String>) {
    start_with_args(&["uci"])
}

/// Spawn the engine with the given command-line arguments and a reader thread;
/// lines arrive on an mpsc channel. `read_line` on the raw stdout would block
/// forever when the child stalls (or to its EOF), so the test side never reads
/// it directly.
fn start_with_args(args: &[&str]) -> (Child, Receiver<String>) {
    let bin = env!("CARGO_BIN_EXE_flawless");
    let mut child = Command::new(bin)
        .args(args)
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

fn kill_and_reap(child: &mut Child) {
    let _ = child.kill();
    let _ = child.wait();
}

/// Bounded reap: `wait()` on a hung child would block forever, so poll try_wait.
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
                std::thread::sleep(Duration::from_millis(5));
            }
            Err(e) => panic!("failed to wait for child: {e}"),
        }
    }
}

fn wait_for(
    child: &mut Child,
    rx: &Receiver<String>,
    token: &str,
    timeout: Duration,
) -> Vec<String> {
    let start = Instant::now();
    let mut lines = Vec::new();
    loop {
        let remaining = timeout.saturating_sub(start.elapsed());
        if remaining.is_zero() {
            eprintln!("timed out waiting for {token}; lines so far: {lines:?}");
            kill_and_reap(child);
            panic!("timed out waiting for {token}");
        }
        match rx.recv_timeout(remaining) {
            Ok(line) => {
                let line = line.trim_end().to_string();
                if line.starts_with(token) {
                    lines.push(line);
                    return lines;
                }
                lines.push(line);
            }
            Err(std::sync::mpsc::RecvTimeoutError::Timeout) => {
                eprintln!("timed out waiting for {token}; lines so far: {lines:?}");
                kill_and_reap(child);
                panic!("timed out waiting for {token}");
            }
            Err(std::sync::mpsc::RecvTimeoutError::Disconnected) => {
                kill_and_reap(child);
                panic!("engine exited early waiting for {token}; lines so far: {lines:?}");
            }
        }
    }
}

/// After the bounded child has exited, the reader thread reaches EOF and the channel
/// disconnects. Drain everything the engine printed (not just up to the first token)
/// so panic markers late in the session are not silently missed.
fn drain_reader(rx: &Receiver<String>, timeout: Duration) -> Vec<String> {
    let mut lines = Vec::new();
    loop {
        match rx.recv_timeout(timeout) {
            Ok(line) => lines.push(line.trim_end().to_string()),
            Err(_) => return lines,
        }
    }
}

/// Any line we are willing to discard must at least not contain the engine's
/// explicit panic marker, or we would silently swallow a broken search.
fn assert_no_panic_markers(lines: &[String]) {
    for l in lines {
        assert!(
            !l.contains("search thread panicked"),
            "engine reported a panicked search thread: {l}"
        );
    }
}

#[test]
fn handshake_isready_quit() {
    let (mut child, reader) = start();
    let stdin = child.stdin.as_mut().unwrap();
    writeln!(stdin, "uci").unwrap();
    writeln!(stdin, "isready").unwrap();
    writeln!(stdin, "quit").unwrap();
    stdin.flush().unwrap();
    let lines = wait_for(&mut child, &reader, "readyok", Duration::from_secs(10));
    assert!(
        lines.iter().any(|l| l == "uciok"),
        "expected uciok before readyok"
    );
    assert_no_panic_markers(&lines);
    let status = wait_child(child, Duration::from_secs(10));
    assert!(status.success());
}

#[test]
fn unknown_commands_do_not_crash() {
    let (mut child, reader) = start();
    let stdin = child.stdin.as_mut().unwrap();
    writeln!(stdin, "uci").unwrap();
    writeln!(stdin, "isready").unwrap();
    for junk in [
        "definitely-not-a-command",
        "setoption name Nope value 1",
        "go depth notanumber",
        "go nodes -1",
        "position fen not-a-fen",
        "position startpos moves e2e5xx",
        "register later",
        "ponderhit", // ponderhit with no active search must be tolerated
        "stop",      // stop with no active search must be tolerated
        "",
    ] {
        writeln!(stdin, "{junk}").unwrap();
    }
    writeln!(stdin, "isready").unwrap();
    writeln!(stdin, "quit").unwrap();
    stdin.flush().unwrap();
    let mut lines = wait_for(&mut child, &reader, "readyok", Duration::from_secs(10));
    let status = wait_child(child, Duration::from_secs(10));
    lines.extend(drain_reader(&reader, Duration::from_secs(5)));
    assert_no_panic_markers(&lines);
    assert!(status.success());
}

#[test]
fn seeded_fuzz_command_sequences() {
    // Deterministic PRNG (splitmix64); same sequences on every platform.
    let grammar: &[&str] = &[
        "uci",
        "isready",
        "ucinewgame",
        "stop",
        "ponderhit",
        "position startpos",
        "position startpos moves e2e4 e7e5 g1f3",
        "position fen rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "go depth 1",
        "go movetime 50",
        "go nodes 10",
        "go wtime 10000 btime 10000",
        "setoption name Hash value 16",
        "setoption name MultiPV value 2",
        "debug on",
        "debug off",
        "register",
        "go searchmoves e2e4 d2d4 depth 1",
        "garbage token storm !!",
        "go depth 99999999999999999999",
    ];
    let mut seed: u64 = 0xA341_5EED_5EED_0001;
    let mut next = move || {
        seed = seed.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = seed;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    };
    for trial in 0..6 {
        let (mut child, reader) = start();
        let stdin = child.stdin.as_mut().unwrap();
        writeln!(stdin, "uci").unwrap();
        for _ in 0..25 {
            let idx = (next() % grammar.len() as u64) as usize;
            writeln!(stdin, "{}", grammar[idx]).unwrap();
        }
        // always finish with a liveness probe and a clean quit
        writeln!(stdin, "isready").unwrap();
        writeln!(stdin, "quit").unwrap();
        stdin.flush().unwrap();
        let mut lines = wait_for(&mut child, &reader, "readyok", Duration::from_secs(30));
        let status = wait_child(child, Duration::from_secs(10));
        lines.extend(drain_reader(&reader, Duration::from_secs(5)));
        assert_no_panic_markers(&lines);
        assert!(status.success(), "trial {trial}: nonzero exit");
    }
}

/// Regression for the hold/ponderhit bestmove handoff (PR #1 review thread
/// PRRT_..D-, src/uci.rs:433): after `go ponder`, exactly one `bestmove` must be
/// emitted as soon as the search ends or `ponderhit`/`stop` arrives — never
/// deferred until a later GUI command, never duplicated. The trials race the
/// worker's end-of-search section against the main thread's command handling
/// with sub-millisecond jitter and tiny movetimes, hammering both orderings.
#[test]
fn ponderhit_or_stop_racing_search_end_emits_exactly_one_bestmove() {
    for trial in 0..30u32 {
        let (mut child, reader) = start();
        {
            let stdin = child.stdin.as_mut().unwrap();
            writeln!(stdin, "uci").unwrap();
            writeln!(stdin, "isready").unwrap();
        }
        wait_for(&mut child, &reader, "readyok", Duration::from_secs(10));
        let mt = 2 + (trial % 7); // 2..8 ms: search ends almost immediately
        {
            let stdin = child.stdin.as_mut().unwrap();
            writeln!(stdin, "position startpos").unwrap();
            writeln!(stdin, "go ponder movetime {mt}").unwrap();
            // Jittered arrival: sometimes the command lands before the search ends,
            // sometimes after the worker already held back bestmove.
            std::thread::sleep(Duration::from_micros(50 * u64::from(trial % 41)));
            if trial % 2 == 0 {
                writeln!(stdin, "ponderhit").unwrap();
            } else {
                writeln!(stdin, "stop").unwrap();
            }
            stdin.flush().unwrap();
        }
        // Exactly one bestmove must arrive WITHOUT any further command.
        let mut lines = Vec::new();
        let mut bestmoves = 0u32;
        let deadline = Instant::now() + Duration::from_secs(10);
        while Instant::now() < deadline && bestmoves == 0 {
            for line in drain_reader(&reader, Duration::from_millis(150)) {
                if line.starts_with("bestmove") {
                    bestmoves += 1;
                }
                assert!(!line.contains("panicked"), "trial {trial}: {line}");
                lines.push(line);
            }
        }
        // Grace window: catch a duplicated bestmove if the handoff were broken.
        for line in drain_reader(&reader, Duration::from_millis(300)) {
            if line.starts_with("bestmove") {
                bestmoves += 1;
            }
            assert!(!line.contains("panicked"), "trial {trial}: {line}");
            lines.push(line);
        }
        assert_eq!(
            bestmoves, 1,
            "trial {trial} (mt={mt}, cmd={}): expected exactly one bestmove without further input; saw lines: {lines:?}",
            if trial % 2 == 0 { "ponderhit" } else { "stop" }
        );
        writeln!(child.stdin.as_mut().unwrap(), "quit").unwrap();
        let _ = child.stdin.as_mut().unwrap().flush();
        let status = wait_child(child, Duration::from_secs(10));
        assert!(status.success(), "trial {trial}: nonzero exit");
    }
}

/// R-07: a rejected `position` command must not be searched silently. The next `go`
/// answers `bestmove 0000`; a later valid `position` restores normal search.
#[test]
fn rejected_position_yields_null_bestmove_until_fixed() {
    let (mut child, rx) = start();
    let mut stdin = child.stdin.take().expect("stdin piped");
    writeln!(stdin, "uci").unwrap();
    writeln!(stdin, "position startpos moves e2e4 e2e5").unwrap();
    writeln!(stdin, "go depth 3").unwrap();
    let mut bad = None;
    let deadline = Instant::now() + Duration::from_secs(20);
    while Instant::now() < deadline {
        if let Ok(line) = rx.recv_timeout(Duration::from_millis(50)) {
            if line.starts_with("bestmove") {
                bad = Some(line);
                break;
            }
        }
    }
    assert_eq!(bad.as_deref(), Some("bestmove 0000"));
    writeln!(stdin, "position startpos moves e2e4 e7e5").unwrap();
    writeln!(stdin, "go depth 3").unwrap();
    let mut good = None;
    while Instant::now() < deadline {
        if let Ok(line) = rx.recv_timeout(Duration::from_millis(50)) {
            if line.starts_with("bestmove") {
                good = Some(line);
                break;
            }
        }
    }
    let good = good.expect("bestmove after valid position");
    assert_ne!(good, "bestmove 0000");
    writeln!(stdin, "quit").unwrap();
    drop(stdin);
    wait_child(child, Duration::from_secs(10));
}

// ---------------------------------------------------------------------------
// Launch-mode compatibility (no-argument UCI startup) and CLI regression tests.
//
// Conventional UCI GUIs start a custom engine with `Process.start(path, [])` and
// then write `uci` to stdin. These tests run the real compiled executable in
// exactly that way, plus the explicit `uci` form, so neither mode can regress.
// ---------------------------------------------------------------------------

const T: Duration = Duration::from_secs(20);

/// A spawned engine plus its stdout reader channel. Dropping it kills and reaps
/// the child, so a failing assertion never leaves a process running.
struct Engine {
    child: Child,
    rx: Receiver<String>,
}

impl Engine {
    fn spawn(args: &[&str]) -> Self {
        let (child, rx) = start_with_args(args);
        Engine { child, rx }
    }

    fn send(&mut self, cmd: &str) {
        let stdin = self.child.stdin.as_mut().expect("stdin piped");
        writeln!(stdin, "{cmd}").expect("write to engine stdin");
        stdin.flush().expect("flush engine stdin");
    }

    /// Bounded wait for the process to exit; kills it and panics on timeout.
    fn wait_exit(&mut self, timeout: Duration) -> std::process::ExitStatus {
        let start = Instant::now();
        loop {
            match self.child.try_wait() {
                Ok(Some(status)) => return status,
                Ok(None) => {
                    if start.elapsed() > timeout {
                        let _ = self.child.kill();
                        let _ = self.child.wait();
                        panic!("engine did not exit within {timeout:?}");
                    }
                    thread::sleep(Duration::from_millis(5));
                }
                Err(e) => panic!("failed to poll engine: {e}"),
            }
        }
    }
}

impl Drop for Engine {
    fn drop(&mut self) {
        if let Ok(None) = self.child.try_wait() {
            let _ = self.child.kill();
        }
        let _ = self.child.wait();
    }
}

/// Read stdout lines until one equals `token` exactly. Returns every line read,
/// including the token. Panics (with the lines seen so far) on timeout.
fn read_until(rx: &Receiver<String>, token: &str, timeout: Duration) -> Vec<String> {
    let deadline = Instant::now() + timeout;
    let mut lines = Vec::new();
    while Instant::now() < deadline {
        if let Ok(line) = rx.recv_timeout(Duration::from_millis(50)) {
            let line = line.trim_end().to_string();
            let done = line == token;
            lines.push(line);
            if done {
                return lines;
            }
        }
    }
    panic!("timed out after {timeout:?} waiting for {token:?}; stdout so far: {lines:?}");
}

/// Read stdout lines until one starts with `prefix`. Returns every line read.
fn read_until_prefix(rx: &Receiver<String>, prefix: &str, timeout: Duration) -> Vec<String> {
    let deadline = Instant::now() + timeout;
    let mut lines = Vec::new();
    while Instant::now() < deadline {
        if let Ok(line) = rx.recv_timeout(Duration::from_millis(50)) {
            let line = line.trim_end().to_string();
            let done = line.starts_with(prefix);
            lines.push(line);
            if done {
                return lines;
            }
        }
    }
    panic!("timed out after {timeout:?} waiting for prefix {prefix:?}; stdout so far: {lines:?}");
}

/// Every stdout line in UCI mode must be a protocol line. A banner or usage text
/// on stdout would confuse a GUI, so this is a strict allow-list.
fn assert_only_uci_lines(lines: &[String]) {
    for l in lines {
        let ok = l == "uciok"
            || l == "readyok"
            || l.starts_with("id ")
            || l.starts_with("option name ")
            || l.starts_with("info ")
            || l.starts_with("bestmove ");
        assert!(ok, "non-UCI text on stdout: {l:?} (all lines: {lines:?})");
        assert!(!l.contains("usage"), "usage banner leaked to stdout: {l:?}");
    }
}

/// The set of legal moves from the start position, in UCI notation.
fn legal_uci_moves_from_startpos() -> Vec<String> {
    use flawless::position::Position;
    flawless::attack::init_attacks();
    let mut pos = Position::startpos();
    flawless::movegen::generate_legal(&mut pos)
        .iter()
        .map(|m| m.to_uci())
        .collect()
}

/// Full lifecycle with ZERO command-line arguments: the exact launch shape used by
/// the CrispChess Extended generic UCI launcher (`Process.start(path, [])`).
#[test]
fn no_arguments_starts_uci_mode_and_completes_lifecycle() {
    let mut eng = Engine::spawn(&[]);

    // The process must not exit (or print anything) before the first UCI command.
    thread::sleep(Duration::from_millis(300));
    assert!(
        eng.child.try_wait().expect("poll engine").is_none(),
        "engine exited before receiving any command (no-argument launch)"
    );
    assert!(
        eng.rx.recv_timeout(Duration::from_millis(100)).is_err(),
        "engine wrote to stdout before receiving any command"
    );

    // uci -> identification + options + uciok, nothing else.
    eng.send("uci");
    let hs = read_until(&eng.rx, "uciok", T);
    assert_only_uci_lines(&hs);
    assert!(hs.iter().any(|l| l == "id name Flawless"), "{hs:?}");
    assert!(hs.iter().any(|l| l.starts_with("id author ")), "{hs:?}");

    // isready -> readyok.
    eng.send("isready");
    let ready = read_until(&eng.rx, "readyok", T);
    assert_only_uci_lines(&ready);

    // position startpos is accepted: no error report, and the engine stays in sync.
    eng.send("position startpos");
    eng.send("isready");
    let after_pos = read_until(&eng.rx, "readyok", T);
    assert_only_uci_lines(&after_pos);
    assert!(
        !after_pos.iter().any(|l| l.contains("error")),
        "position startpos was rejected: {after_pos:?}"
    );

    // go depth 2 -> a legal bestmove from the start position.
    eng.send("go depth 2");
    let search = read_until_prefix(&eng.rx, "bestmove", T);
    assert_only_uci_lines(&search);
    let bm_line = search.last().expect("bestmove line");
    let mv = bm_line
        .strip_prefix("bestmove ")
        .and_then(|rest| rest.split_whitespace().next())
        .expect("bestmove has a move token");
    let legal = legal_uci_moves_from_startpos();
    assert!(
        legal.iter().any(|m| m == mv),
        "bestmove {mv} is not legal from startpos; legal = {legal:?}"
    );

    // quit -> clean exit with status 0.
    eng.send("quit");
    let status = eng.wait_exit(Duration::from_secs(10));
    assert!(status.success(), "quit: nonzero exit status {status:?}");
    assert_eq!(status.code(), Some(0), "quit: exit code must be 0");
}

/// Zero-argument and explicit `uci` launches must produce byte-identical handshakes.
#[test]
fn no_arguments_and_explicit_uci_produce_identical_handshake() {
    let mut no_args = Engine::spawn(&[]);
    let mut explicit = Engine::spawn(&["uci"]);
    no_args.send("uci");
    explicit.send("uci");
    let a = read_until(&no_args.rx, "uciok", T);
    let b = read_until(&explicit.rx, "uciok", T);
    assert_eq!(
        a, b,
        "handshake differs between no-argument and `uci` launch"
    );
    no_args.send("quit");
    explicit.send("quit");
    assert!(no_args.wait_exit(Duration::from_secs(10)).success());
    assert!(explicit.wait_exit(Duration::from_secs(10)).success());
}

/// With no arguments, closing stdin is a clean shutdown: exit 0, no hang.
#[test]
fn no_arguments_exits_cleanly_on_stdin_eof() {
    let mut eng = Engine::spawn(&[]);
    eng.send("uci");
    let _ = read_until(&eng.rx, "uciok", T);
    // Drop our write end of stdin to deliver EOF.
    drop(eng.child.stdin.take());
    let status = eng.wait_exit(Duration::from_secs(10));
    assert_eq!(status.code(), Some(0), "EOF on stdin: exit code {status:?}");
}

/// Run a CLI invocation with stdin closed (so nothing can block on input), drain
/// both pipes on threads (so a chatty child cannot deadlock), and bound the wait.
/// Returns (exit code, stdout, stderr).
fn run_cli(args: &[&str]) -> (Option<i32>, String, String) {
    use std::io::Read;
    let bin = env!("CARGO_BIN_EXE_flawless");
    let mut child = Command::new(bin)
        .args(args)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("spawn flawless");
    let mut out_pipe = child.stdout.take().expect("stdout piped");
    let mut err_pipe = child.stderr.take().expect("stderr piped");
    let out_thread = thread::spawn(move || {
        let mut s = String::new();
        let _ = out_pipe.read_to_string(&mut s);
        s
    });
    let err_thread = thread::spawn(move || {
        let mut s = String::new();
        let _ = err_pipe.read_to_string(&mut s);
        s
    });
    let start = Instant::now();
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break status,
            Ok(None) => {
                if start.elapsed() > Duration::from_secs(60) {
                    let _ = child.kill();
                    let _ = child.wait();
                    panic!("`flawless {args:?}` did not finish within 60s");
                }
                thread::sleep(Duration::from_millis(5));
            }
            Err(e) => panic!("failed to poll flawless: {e}"),
        }
    };
    let stdout = out_thread.join().expect("stdout reader");
    let stderr = err_thread.join().expect("stderr reader");
    (status.code(), stdout, stderr)
}

/// `--version` / `--help` / `-h` are explicit requests: stdout, exit 0.
#[test]
fn cli_version_and_help_are_explicit_and_exit_zero() {
    let (code, out, err) = run_cli(&["--version"]);
    assert_eq!(code, Some(0));
    assert_eq!(
        out.trim(),
        format!("Flawless {}", env!("CARGO_PKG_VERSION"))
    );
    assert!(err.is_empty(), "--version wrote to stderr: {err:?}");

    for flag in ["--help", "-h"] {
        let (code, out, err) = run_cli(&[flag]);
        assert_eq!(code, Some(0), "{flag} exit code");
        assert!(out.contains("usage:"), "{flag} stdout: {out:?}");
        assert!(out.contains("UCI mode"), "{flag} stdout: {out:?}");
        assert!(err.is_empty(), "{flag} wrote to stderr: {err:?}");
    }
}

/// Existing subcommands keep their behaviour and output.
#[test]
fn cli_existing_subcommands_still_work() {
    let (code, out, _) = run_cli(&["perft", "3"]);
    assert_eq!(code, Some(0));
    assert!(out.contains("perft(3) = 8902"), "perft 3: {out:?}");

    let (code, out, _) = run_cli(&["divide", "1"]);
    assert_eq!(code, Some(0));
    assert!(out.contains("total = 20"), "divide 1: {out:?}");

    let (code, out, _) = run_cli(&["eval"]);
    assert_eq!(code, Some(0));
    assert!(out.contains("total"), "eval: {out:?}");

    let (code, out, _) = run_cli(&["hash"]);
    assert_eq!(code, Some(0), "hash with empty stdin should exit 0");
    assert!(out.is_empty(), "hash with no input printed: {out:?}");
}

/// An unknown command is a user error: exit 2, message on stderr, nothing on stdout.
#[test]
fn cli_unknown_command_is_an_error_on_stderr() {
    let (code, out, err) = run_cli(&["definitely-not-a-command"]);
    assert_eq!(code, Some(2));
    assert!(out.is_empty(), "unknown command wrote to stdout: {out:?}");
    assert!(
        err.contains("unknown command: definitely-not-a-command"),
        "stderr: {err:?}"
    );
}
