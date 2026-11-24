//! Flawless — an independent chess engine.
//!
//! Library root: exposes modules for the binary and for integration tests.
//! Zero external dependencies.

/// `println!` for protocol and CLI output. A closed stdout (the GUI or the pipe reader has gone)
/// ends the process with status 0 instead of panicking with exit status 101, as `println!` does
/// on `Broken pipe` (found by audit, see FAILURE_LEDGER F-10).
#[macro_export]
macro_rules! out_line {
    ($($arg:tt)*) => {{
        use std::io::Write as _;
        let mut handle = std::io::stdout().lock();
        if writeln!(handle, $($arg)*).is_err() {
            std::process::exit(0);
        }
    }};
}

/// `eprintln!` for diagnostics. A closed or broken stderr must not end the process, so write
/// errors are ignored (audit finding F-13: `eprintln!` panics on a broken pipe, which ended the
/// session with exit status 101 after an oversized input line).
#[macro_export]
macro_rules! err_line {
    ($($arg:tt)*) => {{
        use std::io::Write as _;
        let _ = writeln!(std::io::stderr().lock(), $($arg)*);
    }};
}

pub mod attack;
pub mod eval;
pub mod movegen;
pub mod position;
pub mod search;
pub mod tt;
pub mod types;
pub mod uci;
