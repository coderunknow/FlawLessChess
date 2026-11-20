# Audit: UCI no-argument startup compatibility (2026-11-19)

Scope: make `flawless` enter UCI mode when launched with no command-line arguments, and produce a
Windows x64 executable as a CI artifact. No search, evaluation, rating, or V1-gate work.

## Reproduction (VERIFIED)

Source: user diagnostic bundle `diagnostic-report.zip` (Google Drive; `application.log`,
`errors.json`, `lifecycle.json`). Key record:
`Engine "flawlessv1 patch2.exe" exited while searching (exit code 2)`, stderr
`Flawless 0.1.0-dev.1 — UCI chess engine` / `usage: Flawless [uci|perft …]`. The process
started and was lost about 40 ms later, before any UCI command.

Local reproduction on the pre-change commit `5e36b06` (Linux, Rust 1.99.0, release build):

```
$ flawless < <(printf 'uci\nisready\nquit\n');  echo $?   -> usage on stderr, exit 2
$ flawless uci < <(printf 'uci\nisready\nquit\n');         -> id name Flawless … uciok readyok, exit 0
```

The user's binary's commit is not recorded in the bundle. The startup code is the same on `main`.

## Root cause (VERIFIED from source)

`src/main.rs`, `fn main`, the `None =>` arm of the argument match: it printed usage to stderr and
called `std::process::exit(2)`. Conventional UCI launchers (for example CrispChess Extended's
generic launcher, `Process.start(profile.path, [])`) start the engine with no arguments and then
send `uci`. The engine exited before reading stdin. The existing integration test always passed
`uci`, so it could not detect this.

## Implemented fix (commit `a75aa7e` + `3a47185`)

- `src/main.rs`: `None` and `Some("uci")` both call `flawless::uci::run_uci()`. `-h`/`--help`
  print help to stdout (exit 0). Unknown commands still exit 2 with the message on stderr, plus a
  pointer to `--help`. `perft`, `divide`, `bench`, `eval`, `bench_eval`, `moves`, `hash`, and
  `version`/`--version` are unchanged. No text is written to stdout in UCI mode.
- Why this is correct: the UCI loop reads stdin and writes only protocol lines, and it was already
  verified in `uci` mode. A missing argument is now a valid UCI launch, which is the convention GUIs
  follow. The fix is in the engine's startup contract, not tied to the executable's file name.
- Zero dependencies. No search code changed.

## Regression tests (VERIFIED locally on Linux; Windows via CI)

`tests/uci_smoke.rs` runs the real compiled binary through `CARGO_BIN_EXE_flawless`:

- `no_arguments_starts_uci_mode_and_completes_lifecycle`: no output and no exit before the first
  command; `uci` → `uciok` with identification; `isready` → `readyok`; `position startpos` accepted;
  `go depth 2` → a bestmove that is legal from startpos (checked with `generate_legal`); `quit` →
  exit code 0. Stdout is restricted to protocol lines, and "usage" is rejected.
- `no_arguments_and_explicit_uci_produce_identical_handshake`: byte-identical handshake in both modes.
- `no_arguments_exits_cleanly_on_stdin_eof`: EOF → exit code 0.
- `cli_version_and_help_are_explicit_and_exit_zero`, `cli_existing_subcommands_still_work`,
  `cli_unknown_command_is_an_error_on_stderr`.

A `Engine` guard kills and reaps children on drop, and every wait is bounded.

Negative control (VERIFIED): with the pre-change `src/main.rs`, the three no-argument tests fail
(`engine exited before receiving any command (no-argument launch)`). With the fix, all pass.

## Gates (local, VERIFIED)

| Gate | Result |
|---|---|
| `cargo fmt --all -- --check` | pass |
| `cargo clippy --release --all-targets -- -D warnings` | pass |
| `cargo test --release --locked` | pass (18 + 3 + 21 + 11 + 5 integration/unit; 0 failed) |
| `cargo build --release --locked` | pass |
| perft startpos depth 3 | 8902 (pass) |
| Rust 1.80 MSRV | CI job `msrv (rust 1.80)` **success** on `3a47185`; not compiled locally (no 1.80 toolchain obtainable here) |

## Benchmark signature (VERIFIED, unchanged)

| | depth-10 signature | per-position lines |
|---|---|---|
| before (`5e36b06`) | `141943aa23b3fc68` | baseline |
| after (`a75aa7e`) | `141943aa23b3fc68` | identical |

Expected: no search change. The signature matches the value already recorded in the project logs.

## CI (exact heads)

- Draft PR #3 `arena/2d2d30b4-flawlesschess` → `main` (not merged). PR #2 belongs to another branch and was not touched.
- Head `a75aa7e`: run `44650123000`, CI success. Its artifact was labelled with the merge SHA
  (`aeb6435…`), which exposed the defect fixed below.
- **Final verified head `3a47185ea…` `3a4718561b7abb7f268fe5608eed8ccfeaecd0cd`:** run
  https://github.com/coderunknow/FlawLessChess/actions/runs/44650377260 (CI, success)
  - ubuntu-latest: success (fmt, clippy, all tests, Python harness, release, UCI smoke, perft)
  - windows-latest: success (all steps, including the new UCI and CLI tests on Windows)
  - msrv (rust 1.80): success
  - windows x64 release artifact: success. Steps: rustc host check, release build, PE check and
    smoke tests (script), artifact upload, all successful.
  - anchor-verify run `44650377210`: success.

Defect found and fixed in CI: for `pull_request` events, `GITHUB_SHA` is GitHub's synthetic merge
commit. The artifact is now checked out and labelled with `github.event.pull_request.head.sha`.

## Windows x64 artifact

- Artifact: `flawless-windows-x64-3a4718561b7abb7f268fe5608eed8ccfeaecd0cd`, workflow artifact id
  `14590461654` (186,688 bytes), run 44650377260. Download:
  https://github.com/coderunknow/FlawLessChess/actions/runs/44650377260 (Artifacts section).
- Contents set by the job: `flawless.exe`, `SHA256SUMS.txt`, `BUILD-MANIFEST.txt`.
- Build target: `rustc` host `x86_64-pc-windows-msvc`, checked by the job.
- PE architecture: the job checked COFF machine `0x8664` (x86-64) and the job succeeded. This
  check, the smoke tests and the checksum write are in the step logs.
- **NOT VERIFIED by this session:** the executable SHA-256, the manifest contents, and an
  independent PE check of the downloaded bytes. The sandbox cannot reach the Actions artifact
  storage host (`productionresultssa*.blob.core.windows.net` returned EOF), and the step logs are
  unavailable from the sandbox too. The job reported success, but the checksum value must be read
  from the artifact or `SHA256SUMS.txt` by a human with access to the run page.

## Compatibility impact

The release binary changes, so ENGINE-2 binary hashes registered in the rating documents
(`168dc0ab…`) no longer identify this build. No rating evidence was reused or re-authorized.
RATING-100 remains BLOCKED and V1 remains NOT complete.

## Acceptance checklist

- [x] Root cause reproduced and confirmed from source and executable behaviour
- [x] Zero-argument UCI startup fixed
- [x] Explicit `uci` startup preserved (handshake identical)
- [x] Full no-argument UCI lifecycle verified (local test and Linux/Windows CI test run)
- [x] Existing CLI commands preserved (regression tests)
- [x] Regression tests passed on Linux (local and CI)
- [x] Regression tests passed on Windows x64 (CI windows-latest job)
- [x] Formatting and Clippy passed
- [x] Full test suite passed
- [ ] Rust 1.80 compatibility verified — CI `msrv` success on the head; not compiled locally
- [x] Existing perft gates passed (startpos d3 = 8902; local)
- [x] Benchmark signature unchanged (`141943aa23b3fc68`)
- [x] Documentation and append-only logs updated
- [x] Final code committed and pushed (`arena/2d2d30b4-flawlesschess`)
- [x] Exact pushed SHA verified remotely (`git ls-remote`)
- [x] Exact-head CI passed (run 44650377260)
- [~] Windows x64 executable produced — job reported success; the artifact bytes were not retrievable from the sandbox
- [~] PE architecture verified as x86-64 — checked by the CI job; independent check NOT VERIFIED here
- [ ] SHA-256 and build manifest verified — NOT VERIFIED here (see above)
- [~] Actual executable artifact uploaded and accessible — upload step succeeded; accessibility from the sandbox NOT VERIFIED
- [ ] Actual executable delivered to the user — NOT done (bytes not retrievable here)

## Next experiment

Run the artifact's `flawless.exe` under CrispChess Extended to confirm the engine is added without the
exit-2 error. Not done: no GUI is available in this environment.

## Review round 2 (CodeRabbit on PR #3, head `df0097e`)

CodeRabbit was triggered manually (comment on PR #3). Its review found four items; each was checked against the code:

| Finding | Verdict | Action |
|---|---|---|
| bestmove regex rejects `bestmove X ponder Y` | valid | regex accepts the optional ponder suffix; unit-tested |
| bench timeout blocks staging | valid | bench is informational; a timeout records `unavailable (…)` and staging continues; unit-tested |
| `quit` sent with `go depth 2` can stop the search at depth 0 | valid, confirmed (see FAILURE_LEDGER entry) | smoke test is interactive: `quit` only after `bestmove`, with bounded waits |
| checkout keeps credentials during PR-code build | valid hardening | `persist-credentials: false` on the windows artifact checkout |

Also fixed: a missing `--rustc-version-file` produced a traceback instead of a clean failure.

Known gap, not changed: the pre-existing ci.yml step "UCI bestmove smoke test (search depth 2)" uses a pipe with `quit` in the same input and therefore can pass at depth 0 (see FAILURE_LEDGER). The Rust lifecycle test covers the synchronised path.

## Review round 3 (final head, this section supersedes earlier head references)

- Full-review request sent to CodeRabbit on `8693045` (the incremental re-review request on `8693045` had no review posted after about 25 minutes).
- Engine probes, no bug found: CRLF input, `go infinite` + `stop`, `go movetime`, `go` without `position`, `setoption` (Threads>1 is reported on stderr and ignored).
- Bugs found and fixed in the test tooling:
  - The pipe-based CI bestmove step could pass on a depth-0 fallback move (see FAILURE_LEDGER). It is replaced by `scripts/uci_bestmove_smoke.py`, which requires a completed `info depth 2` line.
  - The artifact smoke test now applies the same depth-2 requirement.
  - The CI step used bare `python`; it now resolves `python3`/`python` like the other steps.
- Documentation: AGENTS_LOG push-policy claim corrected (the `gh workflow run` dispatch was refused with 403).

## Review round 4 (head a7b7eda, CodeRabbit findings fixed in the harness)

- CI on `a7b7eda` (run `44668848037`): ubuntu-latest, windows-latest, msrv (rust 1.80), windows x64 artifact job, anchor-verify `44668848066` all success. The new depth-2 step (`scripts/uci_bestmove_smoke.py`) passed on both OSes.
- Artifact `flawless-windows-x64-a7b7eda99ba466ee5ca35f3e273d8347d3230206` (186746 bytes) is listed. Download fails from this sandbox (blob-storage EOF), so its SHA-256, manifest, and PE machine check are NOT VERIFIED here.
- CodeRabbit on `a7b7eda`: 3 actionable findings (all in `scripts/windows_artifact.py`), all valid and fixed in the harness. Regression tests added (15/15 pass).
- No Rust code changed in round 4, so the round-3 Rust gate results still apply. Engine behaviour is unchanged.


## Current head status (07b68a8, supersedes the a7b7eda CI references above)

- CI run `44673016254` on `07b68a8` (harness hardening only; no Rust change): success on ubuntu-latest, windows-latest, msrv (rust 1.80), windows x64 artifact job; anchor-verify `44673016389` success.
- Artifact `flawless-windows-x64-07b68a8001a3405b21d3cdfcb5f013d89e6eb469` (186691 bytes) is listed; download fails from this sandbox (blob-storage EOF). NOT VERIFIED: SHA-256, manifest, PE 0x8664 on the downloaded file.
- CodeRabbit on `07b68a8`: review requested; rate-limited by CodeRabbit ("Your next included review will be available in 16 minutes" earlier; the later request was also rate-limited). NOT VERIFIED.
- Merge criteria (CI and CodeRabbit both green on the final head) are NOT met for CodeRabbit on `07b68a8`.
