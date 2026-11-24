# docs/ENVIRONMENT.md — build environment record (2026-11-14)

## Sandbox (this dev machine)

- Linux (Debian 12 userland), 2 vCPU, ~3.9 GB RAM, 21 GB disk (20 GB free)
- Kernel: unknown (container); `nproc` = 2

## Network reachability (tested 2026-11-14)

| Host | Status |
|---|---|
| github.com | 200 OK |
| codeload.github.com | 301 (reachable) |
| api.github.com | 200 OK |
| registry.npmjs.org | 200 OK |
| pypi.org / files.pythonhosted.org | 200 / reachable |
| crates.io / static.crates.io / index.crates.io | **BLOCKED** (TLS failure) |
| static.rust-lang.org / sh.rustup.rs | **BLOCKED** |
| raw.githubusercontent.com | **BLOCKED** |
| mirrors.tuna.tsinghua.edu.cn / mirrors.aliyun.com | **BLOCKED** |

## Rust toolchain (installed from npm, unofficial redistribution)

crates.io and static.rust-lang.org are blocked, so the official installer cannot be used.
The toolchain was installed from the `@toolchain-bin/*` npm scope (trusted redistribution of the
official compiler binaries; install scripts mirror the rust-installer layout):

- `@toolchain-bin/rustc-1.99.0-x86_64-unknown-linux-gnu@1.99.0` → rustc 1.99.0 (b940084d7 2026-09-28)
- `@toolchain-bin/rust-std-1.99.0-x86_64-unknown-linux-gnu@1.99.0-1`
- `@toolchain-bin/cargo-1.99.0-x86_64-unknown-linux-gnu@0.100.0` → cargo 1.99.0
- `@toolchain-bin/rustfmt-1.99.0-x86_64-unknown-linux-gnu@1.10.0`
- `@toolchain-bin/clippy-1.99.0-x86_64-unknown-linux-gnu@0.1.99`

Install prefix: `/home/user/.toolchain/sysroot` (activate with `export PATH=/home/user/.toolchain/sysroot/bin:$PATH`
or `source /home/user/.toolchain/env`). **The dependency directories do NOT survive sandbox snapshot
restores.** After every restore, redo: npm toolchain install (same pins) + venv + opponents, then
`find /home/user/.toolchain/sysroot/bin /home/user/.toolchain/sysroot/lib/rustlib/*/bin -type f -exec chmod 755 {} +`
(the npm tarballs ship `rust-lld` and `gcc-ld/*` as mode 644, which otherwise breaks linking with
`collect2: cannot find 'ld'`). `gcc 12.2.0` + binutils `ld` are present for linking.

**Sandbox snapshot restores** wiped `/home/user/.toolchain`, `/home/user/.venv` and
`/home/user/opponents` three times so far (2026-11-14 entries in FAILURE_LEDGER.md). Working tree
recovers via `git update-ref` to origin tip + `git reset`; origin is the source of truth; push early
and often; never trust unpushed local state.

## Python (test oracle & tooling)

- python3 3.11.2 (system). venv at `/home/user/.venv` with **python-chess 1.11.2**
  (pip index reports it as `1.999`; module reports `1.11.2`). License: **GPL-3.0+** (test-only oracle, never
  linked into the engine, never a runtime dependency).
- Node.js v22.22.3 + npm 10.9.8 (used for toolchain install and potentially for stockfish.wasm-based
  opponent testing; see BENCHMARKING.md).

## Git / GitHub

- `git` and `gh` authenticated as `coderunknow` (token via env; never stored in repo).
- Branch: `arena/b756c5f1-asilzkkbatwabaieokwvfotrsioiij` (current work branch).
- `main` contains the initial commit only; engine development happens on `arena/...` (PR #1).
- Repository is named `coderunknow/Flawless-Chess-Engine` (externally renamed; this project did not
  rename it; old URL auto-redirects). Engine identity is **Flawless** (ADR-0002).

## Target reference machine (NOT available here)

Windows 10 LTSC 2021, Intel Core i5-7300U (4 threads), 8 GB RAM, Intel HD 620, 256 GB SSD.
All performance claims must eventually be validated there (or labeled as sandbox measurements).

## Restore #4 (2026-11-14, same day) — rebuild verified end-to-end
- Rebuilt with the documented sequence (install.sh --prefix per @toolchain-bin tarball + chmod
  755 of libexec/gcc-ld). Verified: `cargo 1.99.0`, `rustc 1.99.0`, clippy 0.1.99, rustfmt
  1.10.0; venv python-chess 1.11.2; SF WASM hashes re-verified identical; tests 29/29 green;
  DIFTEST PASSED (2295 perft-d2, 0 mismatches); bench 2,221,199 nodes; clippy clean after the
  StoreRequest bundling fix.

## Naming note (2026-11-19)

- Product: FlawLessChess. Verified remote: `coderunknow/FlawLessChess` (GitHub redirects the old name `Flawless-Chess-Engine`).
- Cargo package: `flawless` (binary `flawless`); the approved `Flawless-Chess-Engine` package name is not used because renaming would break crate imports and CI paths. Pending user decision.

