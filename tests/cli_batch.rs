//! Process-level tests for the batch modes `flawless moves` and `flawless hash`, which read one
//! FEN per stdin line. Regression for audit finding F-12: a line that was not valid UTF-8 (or
//! too long) ended the batch, so later FENs got no reply. Each input line must get exactly one
//! output line, and a bad line must not stop the rest of the batch.

use std::io::Write;
use std::process::{Command, Stdio};

const START: &str = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

/// Runs `flawless <mode>` with `input` on stdin and returns its stdout lines.
fn run_batch(mode: &str, input: &[u8]) -> Vec<String> {
    let mut child = Command::new(env!("CARGO_BIN_EXE_flawless"))
        .arg(mode)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .expect("spawn flawless");
    {
        let mut stdin = child.stdin.take().expect("stdin");
        stdin.write_all(input).expect("write batch input");
    }
    let out = child.wait_with_output().expect("wait");
    assert!(out.status.success(), "{mode} exited with {}", out.status);
    String::from_utf8(out.stdout)
        .expect("utf-8 output")
        .lines()
        .map(str::to_string)
        .collect()
}

#[test]
fn moves_answers_every_line_when_one_is_not_utf8() {
    let mut bytes = format!("{START}\n").into_bytes();
    bytes.extend_from_slice(&[0xFF, b'\n']);
    bytes.extend_from_slice(format!("{START}\n").as_bytes());
    let lines = run_batch("moves", &bytes);
    assert_eq!(lines.len(), 3, "one reply per input line: {lines:?}");
    assert!(lines[0].starts_with("ok 20 "), "first line: {lines:?}");
    assert!(
        lines[1].starts_with("error "),
        "bad line must be answered: {lines:?}"
    );
    assert!(
        lines[2].starts_with("ok 20 "),
        "batch must continue: {lines:?}"
    );
}

#[test]
fn hash_answers_every_line_when_one_is_not_utf8() {
    let mut bytes = format!("{START}\n").into_bytes();
    bytes.extend_from_slice(&[0xFF, b'\n']);
    bytes.extend_from_slice(format!("{START}\n").as_bytes());
    let lines = run_batch("hash", &bytes);
    assert_eq!(lines.len(), 3, "one reply per input line: {lines:?}");
    assert!(
        lines[0].starts_with("d9e3a1d48a48bfe3 "),
        "first line: {lines:?}"
    );
    assert!(
        lines[1].starts_with("error "),
        "bad line must be answered: {lines:?}"
    );
    assert!(
        lines[2].starts_with("d9e3a1d48a48bfe3 "),
        "batch must continue: {lines:?}"
    );
}

#[test]
fn moves_answers_an_overlong_line_and_continues() {
    let mut bytes = format!("{START}\n").into_bytes();
    bytes.extend(std::iter::repeat(b'a').take(70_000));
    bytes.push(b'\n');
    bytes.extend_from_slice(format!("{START}\n").as_bytes());
    let lines = run_batch("moves", &bytes);
    assert_eq!(lines.len(), 3, "one reply per input line: {lines:?}");
    assert!(
        lines[1].starts_with("error "),
        "overlong line must be answered: {lines:?}"
    );
    assert!(
        lines[2].starts_with("ok 20 "),
        "batch must continue: {lines:?}"
    );
}
