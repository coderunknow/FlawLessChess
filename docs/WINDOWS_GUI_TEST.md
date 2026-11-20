# Windows GUI test guide — FlawLessChess v0.1.0 (pre-V1 release candidate)

Status of this guide: **prepared, not yet executed.** No GUI test has been run by the project.
Use it to test the Windows x64 engine in a UCI chess GUI and report results.

## 1. Get the exact binary

1. Open the GitHub Actions run for the release-candidate commit (the PR #3 head). The run is listed
   in `docs/audit/2026-11-19-v0.1.0-release-candidate.md`.
2. Download the artifact named `flawless-windows-x64-<commit-sha>`. It contains:
   - `flawless.exe` — the engine (UCI, x86-64 Windows).
   - `SHA256SUMS.txt` — the expected SHA-256 of `flawless.exe`.
   - `BUILD-MANIFEST.txt` — commit, target, toolchain, package version, PE machine type.
3. Verify the file (PowerShell, in the folder you unzipped it to):

   ```powershell
   Get-FileHash .\flawless.exe -Algorithm SHA256
   Get-Content .\SHA256SUMS.txt
   ```

   The two hashes must match (case-insensitive). If not, do not use the file; report it.
4. Check the version from the extracted folder, not from PATH: run `.\flawless.exe version` (in that folder) and confirm it prints `Flawless 0.1.0`.

## 2. Install in a GUI

Use any UCI-capable GUI. Tested-by-user targets: **Arena** and **Cute Chess** (both on Windows).

### Arena
1. `Engines → Install New Engine…` → select `flawless.exe`.
2. Protocol: `UCI`. Confirm the engine name shows `Flawless`.
3. Optional: `Engines → Manage` → set `Hash` (default 64 MB).

### Cute Chess
1. `Tools → Settings → Engines → Add…`.
2. Command: full path to `flawless.exe`. Protocol: `UCI`. Name: `Flawless`.
3. Working directory: the folder containing the exe.

Launching without arguments (`flawless.exe`) starts UCI mode; GUIs that pass no arguments are
supported.

## 3. Test checklist

Mark each item PASS, FAIL, or NOT TESTED, and note the GUI and its version.

| # | Test | Expected | Result |
|---|---|---|---|
| 1 | Engine is recognised and initialises | Name `Flawless`, no error dialog | |
| 2 | New game, engine plays White from startpos (3+2 clock) | Legal move within the clock; game continues | |
| 3 | New game, engine plays Black (3+2 clock) | Same as 2 | |
| 4 | Play a full game (≥ 40 plies) to checkmate or draw | No illegal move, no crash, no hang | |
| 5 | Fixed time per move: set 1 s/move, play 10 moves | Each move returns in about 1 s | |
| 6 | Analysis mode (infinite analysis, then stop) | Analysis shows lines; Stop returns promptly | |
| 7 | Promotion: play a pawn to the 8th rank as the engine or as the user | Promotion is legal and the game continues | |
| 8 | Checkmate / stalemate: reach one in a game | GUI reports the result; engine does not invent a move | |
| 9 | Three games in a row without restarting the GUI | No degradation, no crash | |
| 10 | Close the GUI with the engine running | GUI closes; no `flawless.exe` left in Task Manager | |

## 4. What to report

For each FAIL or unexpected behaviour, send:

- GUI name and version; Windows version.
- Exact steps (from the table) and the position (FEN, if the GUI shows it).
- The GUI's engine log, if it has one (Arena: `Engines → Engine Log` / Cute Chess: `View → Engine Output`).
- Screenshot or the move list.
- `SHA256` of the `flawless.exe` you tested.

Results from this guide are the only evidence that GUI playability has been tested. Until they are
reported, GUI playability remains **UNVERIFIED**.
