//! Process-level tests for `flawless divide`. Regression for F-36: `divide 0` printed one line per
//! root move with count 1 and a total of 20, while `perft 0` is 1. Depth 0 is now refused with a
//! usage message and exit status 2. Depths 1 and 2 must still total the perft counts.

use std::process::Command;

const START: &str = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

fn divide(args: &[&str]) -> (i32, String) {
    let out = Command::new(env!("CARGO_BIN_EXE_flawless"))
        .arg("divide")
        .args(args)
        .stdin(std::process::Stdio::null())
        .output()
        .expect("spawn flawless");
    (
        out.status.code().unwrap_or(-1),
        String::from_utf8_lossy(&out.stdout).into_owned(),
    )
}

fn total(stdout: &str) -> u64 {
    let line = stdout
        .lines()
        .find(|l| l.starts_with("total = "))
        .expect("total line");
    line.trim_start_matches("total = ")
        .split_whitespace()
        .next()
        .expect("total value")
        .parse()
        .expect("total is a number")
}

#[test]
fn divide_depth_zero_is_refused_with_usage() {
    let (code, stdout) = divide(&["0"]);
    assert_eq!(code, 2, "divide 0 must exit with usage status 2");
    assert!(
        !stdout.contains("total = "),
        "divide 0 must not print a total: {stdout}"
    );
    assert!(
        !stdout.lines().any(|l| l.contains(": 1")),
        "divide 0 must not print per-move counts: {stdout}"
    );
}

#[test]
fn divide_depth_one_totals_the_root_move_count() {
    let (code, stdout) = divide(&["1", START]);
    assert_eq!(code, 0);
    assert_eq!(total(&stdout), 20, "perft(1) of the start position");
}

#[test]
fn divide_depth_two_totals_perft_two() {
    let (code, stdout) = divide(&["2", START]);
    assert_eq!(code, 0);
    assert_eq!(total(&stdout), 400, "perft(2) of the start position");
}
