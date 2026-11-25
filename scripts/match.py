#!/usr/bin/env python3
"""Match runner: play UCI games between two engines, record raw evidence.

Every game is stored as PGN + a JSONL record line with full config, so any batch
is reproducible and auditable. No ratings are computed here (see stats.py).

Usage examples:
  # Screening (fixed movetime) — never gate evidence:
  python3 scripts/match.py --white-cmd "./target/release/flawless uci" \
      --black-cmd "node /path/to/stockfish-19-lite-single.js" \
      --movetime 100 --openings openings.txt --out benches/<id> --games 20

  # Rating-grade (CCRL-style repeating clock, 40 moves in 15 minutes):
  python3 scripts/match.py --white-cmd "./target/release/flawless uci" \
      --black-cmd "./anchor-1.0" --tc 40/15 --repetitions 17 \
      --openings benches/rating-openings-batchA.txt --out benches/rating-A/anchor1 \
      --batch-id A --shard-id A-anchor1-00 --anchor-json anchors.json

Time control modes (exactly one of): --tc (UCI clock), --movetime, --depth.
--tc 40/15 = repeating 40-moves-in-15-minutes: movestogo is sent so the engine
sees the next time-control period; at each period boundary the policy (default
'add') adds a fresh period to the mover's remaining clock ('reset' sets it
instead). Actual elapsed wall time is charged to the mover; flag fall is a loss.

Game-error policy (docs/RATING_PROTOCOL.md §3): engine errors (exit/timeout/
illegal/unparseable move) are recorded as uncounted attempts and replayed
(--max-replays-per-game, default 1); the batch ABORTS as invalid once any side
accumulates --max-errors-per-side (default 2) errors. Move-cap termination is
recorded unadjudicated ('*') by default and never silently scored a draw
(--move-cap-policy draw is exploratory-only).

--white-artifact / --black-artifact: os.pathsep-separated extra files hashed into
the respective artifact record (e.g. the .wasm next to the stockfish .js launcher)
so swapping them invalidates the recorded batch identity.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import Counter
from dataclasses import dataclass

import chess
import chess.pgn


class EngineExited(RuntimeError):
    pass


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@dataclass
class EngineSpec:
    name: str
    cmd: list[str]


class UciEngine:
    def __init__(
        self,
        spec: EngineSpec,
        hash_mb: int | None = None,
        skill: int | None = None,
        threads: int | None = None,
    ):
        self.spec = spec
        self.proc = subprocess.Popen(
            spec.cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )
        self.engine_error_events: list[str] = []
        self._buf = b""
        self._buf_lock = threading.Lock()
        self._wake = threading.Event()
        self._eof = False
        # Stdout is drained by a dedicated reader thread; consumers take lines from the
        # shared buffer under a lock with a hard deadline. select() is NOT usable on
        # Windows pipes, so all waiting goes through the event.
        self._reader = threading.Thread(
            target=self._reader_loop, name=f"{spec.name}-stdout-reader", daemon=True
        )
        self._reader.start()
        self._send("uci")
        self._wait_for("uciok", timeout=60.0)
        if hash_mb is not None:
            self._send(f"setoption name Hash value {hash_mb}")
        if threads is not None:
            self._send(f"setoption name Threads value {threads}")
        if skill is not None:
            self._send(f"setoption name Skill Level value {skill}")
        # Rating protocol: pondering is disabled unless the preregistered protocol
        # explicitly requires it. Engines without a Ponder option ignore this harmlessly.
        self._send("setoption name Ponder value false")
        self._send("isready")
        self._wait_for("readyok", timeout=60.0)

    def _send(self, s: str) -> None:
        assert self.proc.stdin is not None
        try:
            self.proc.stdin.write((s + "\n").encode())
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            # Engine died (or its stdin closed) — surface as EngineExited so the game
            # loop records an engine-error loss instead of crashing the whole batch.
            raise EngineExited(f"engine {self.spec.name}: pipe broken while sending {s!r}: {e}") from e

    def _reader_loop(self) -> None:
        try:
            out = self.proc.stdout
            assert out is not None
            while True:
                chunk = out.read(65536)  # blocks until >=1 byte or EOF; Windows-safe
                if not chunk:
                    break
                with self._buf_lock:
                    self._buf += chunk
                self._wake.set()
        except Exception:
            pass
        finally:
            with self._buf_lock:
                self._eof = True
            self._wake.set()

    def _readline(self, timeout: float) -> bytes:
        deadline = time.time() + timeout
        while True:
            with self._buf_lock:
                idx = self._buf.find(b"\n")
                if idx != -1:
                    line, self._buf = self._buf[: idx + 1], self._buf[idx + 1 :]
                    return line
                eof = self._eof
            if eof:
                raise EngineExited(f"engine {self.spec.name} exited (stdout EOF, code {self.proc.poll()})")
            remaining = deadline - time.time()
            if remaining <= 0:
                raise TimeoutError(f"engine {self.spec.name}: no complete line for {timeout}s")
            self._wake.wait(remaining)
            self._wake.clear()

    def _wait_for(self, token: str, timeout: float) -> None:
        t0 = time.time()
        while time.time() - t0 < timeout:
            line = self._readline(max(0.1, timeout - (time.time() - t0))).decode(errors="replace")
            if line.strip().startswith(token):
                return
        raise TimeoutError(f"engine {self.spec.name}: expected {token}")

    def set_position(self, board: chess.Board) -> None:
        # Full move history from the initial position (openings included) so the engine's
        # repetition detection has the whole game context — FEN alone hides prior occurrences.
        moves = " ".join(m.uci() for m in board.move_stack)
        if moves:
            self._send(f"position startpos moves {moves}")
        else:
            self._send("position startpos")

    def go(
        self,
        movetime_ms: int | None = None,
        depth: int | None = None,
        clock: tuple[int, int, int, int, int] | None = None,
        timeout: float = 300.0,
    ) -> str:
        """Send `go` and return the bestmove token.

        clock = (wtime_ms, btime_ms, winc_ms, binc_ms, movestogo) for UCI clock mode.
        `timeout` is the runner-side crash net for a missing bestmove; in clock mode it
        should exceed the mover's remaining time so legitimate long thinks are not
        misread as engine errors (the engine stops itself via its own hard limit).
        """
        args = ["go"]
        if clock is not None:
            wtime, btime, winc, binc, mtg = clock
            args += ["wtime", str(wtime), "btime", str(btime), "winc", str(winc), "binc", str(binc)]
            if mtg > 0:
                args += ["movestogo", str(mtg)]
        elif movetime_ms is not None:
            args += ["movetime", str(movetime_ms)]
        elif depth is not None:
            args += ["depth", str(depth)]
        self._send(" ".join(args))
        while True:
            line = self._readline(timeout).decode(errors="replace").strip()
            if line.startswith("info string") and "panicked" in line:
                self.engine_error_events.append(line)
            if line.startswith("bestmove"):
                parts = line.split()
                return parts[1]

    def quit(self) -> None:
        try:
            self._send("quit")
            self.proc.wait(timeout=5.0)
        except Exception:
            self.proc.kill()


# ---------------------------------------------------------------------------
# Time control: repeating moves/minutes schedule on a real UCI clock.
# ---------------------------------------------------------------------------


@dataclass
class ClockTC:
    period_moves: int  # moves per time-control period (e.g. 40)
    period_seconds: float  # seconds granted per period (e.g. 15 minutes = 900)
    increment_seconds: float = 0.0
    policy: str = "add"  # 'add': carry over + grant a fresh period; 'reset': clock set to period

    def describe(self) -> dict:
        return {
            "mode": "clock",
            "period_moves": self.period_moves,
            "period_seconds": self.period_seconds,
            "increment_seconds": self.increment_seconds,
            "period_policy": self.policy,
            "schedule": f"{self.period_moves} moves in {self.period_seconds} seconds, repeating "
            f"({'fresh period added to remaining time' if self.policy == 'add' else 'clock reset to period at boundary'})",
            "ponder": False,
        }


def parse_tc(spec: str, inc_seconds: float, policy: str) -> ClockTC:
    """Parse '40/15' (moves/minutes) or '40/900s' (moves/seconds)."""
    m = re.fullmatch(r"(\d+)\s*/\s*([0-9.]+)\s*(m|s|)?", spec.strip())
    if not m:
        raise SystemExit(f"--tc: cannot parse {spec!r}; expected e.g. '40/15' (moves/minutes)")
    moves = int(m.group(1))
    value = float(m.group(2))
    unit = m.group(3) or "m"
    seconds = value * 60.0 if unit == "m" else value
    if moves < 1 or seconds <= 0:
        raise SystemExit(f"--tc: invalid values {spec!r}")
    if policy not in ("add", "reset"):
        raise SystemExit(f"--tc-policy: must be 'add' or 'reset', got {policy!r}")
    return ClockTC(moves, seconds, inc_seconds, policy)


class GameClock:
    """Per-game clock state for the repeating schedule. Times in integer milliseconds."""

    def __init__(self, tc: ClockTC):
        self.tc = tc
        period_ms = int(round(tc.period_seconds * 1000))
        self.left_ms = {"w": period_ms, "b": period_ms}
        self.moves_left = {"w": tc.period_moves, "b": tc.period_moves}
        self.inc_ms = int(round(tc.increment_seconds * 1000))

    def _key(self, turn: chess.Color) -> str:
        return "w" if turn == chess.WHITE else "b"

    def go_args(self, turn: chess.Color) -> tuple[int, int, int, int, int]:
        k = self._key(turn)
        return (self.left_ms["w"], self.left_ms["b"], self.inc_ms, self.inc_ms, self.moves_left[k])

    def response_timeout(self, turn: chess.Color) -> float:
        """Runner-side crash net: engine may use its whole remaining clock legitimately."""
        return self.left_ms[self._key(turn)] / 1000.0 + 60.0

    def charge(self, turn: chess.Color, elapsed_ms: int) -> bool:
        """Charge actual elapsed wall time to the mover. False => flag fall."""
        k = self._key(turn)
        self.left_ms[k] -= int(elapsed_ms)
        return self.left_ms[k] > 0

    def on_move_made(self, turn: chess.Color) -> None:
        """Apply increment and the period boundary of the repeating schedule."""
        k = self._key(turn)
        self.left_ms[k] += self.inc_ms
        self.moves_left[k] -= 1
        if self.moves_left[k] <= 0:
            period_ms = int(round(self.tc.period_seconds * 1000))
            if self.tc.policy == "add":
                self.left_ms[k] += period_ms
            else:  # 'reset'
                self.left_ms[k] = period_ms
            self.moves_left[k] = self.tc.period_moves


# ---------------------------------------------------------------------------
# Provenance helpers
# ---------------------------------------------------------------------------


def file_sha256(path: str) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def probe_artifact(cmd_line: str, extra_paths: str = "") -> dict:
    """Record which exact binaries/scripts produced a batch — probe archaeology.

    Hashes (a) the PATH-resolved launcher (first token) and (b) EVERY command token that
    resolves to an existing file (e.g. the Stockfish .js next to a `node` launcher), plus
    (c) any explicit artifacts passed via `extra_paths` (os.pathsep-separated, from
    --white-artifact / --black-artifact — e.g. `stockfish-19-lite-single.wasm`, which a
    wrapper loads dynamically and cannot be discovered from the command line alone).
    Replacing the launcher OR the engine script changes the recorded hashes.
    """
    parts = cmd_line.split() if cmd_line else []
    artifacts: list[dict] = []
    seen: set[str] = set()

    def add(path: str) -> None:
        real = os.path.realpath(path)
        if real in seen:
            return
        seen.add(real)
        artifacts.append({"path": path, "sha256": file_sha256(path)})

    for i, tok in enumerate(parts):
        if tok.startswith("-"):
            continue
        if os.path.isfile(tok):
            add(tok)
            continue
        cand = os.path.join(os.getcwd(), tok)
        if os.path.isfile(cand):
            add(cand)
            continue
        if i == 0:
            which = shutil.which(tok)
            if which:
                add(which)
    for extra in (extra_paths or "").split(os.pathsep):
        extra = extra.strip()
        if extra and os.path.isfile(extra):
            add(extra)
    first = artifacts[0] if artifacts else {"path": None, "sha256": None}
    return {
        "cmd": cmd_line,
        "artifacts": artifacts,
        # Back-compat convenience fields; auditors must use "artifacts" (full coverage).
        "binary_path": first["path"],
        "sha256": first["sha256"],
    }


def hardware_info() -> dict:
    """Hardware/OS fingerprint for the match manifest (audit requirement)."""
    info = {
        "platform": None,
        "os": None,
        "kernel": None,
        "cpu_model": None,
        "cpu_count": os.cpu_count(),
        "ram_bytes": None,
        "hostname": None,
        "python": sys.version.split()[0],
    }
    try:
        import platform as _pl

        info["platform"] = _pl.platform()
        info["os"] = f"{_pl.system()} {_pl.release()}"
        info["kernel"] = _pl.version()
        info["hostname"] = _pl.node()
        info["machine"] = _pl.machine()
    except Exception:
        pass
    try:
        with open("/proc/cpuinfo", "rb") as f:
            cpuinfo = f.read().decode(errors="replace")
        for line in cpuinfo.splitlines():
            if line.lower().startswith("model name"):
                info["cpu_model"] = line.split(":", 1)[1].strip()
                break
    except OSError:
        import platform as _pl

        info["cpu_model"] = _pl.processor() or None
    try:
        info["ram_bytes"] = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError, AttributeError):
        pass
    return info


def git_head() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True,
            text=True,
            timeout=5,
        )
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Openings and scheduling
# ---------------------------------------------------------------------------


def parse_opening_moves(text: str) -> list[str]:
    return text.split()


def load_openings(path: str) -> list[tuple[str, list[str]]]:
    """Each line: name|moves (space-separated UCI)."""
    out = []
    with open(path) as f:
        for raw in f:
            raw = raw.strip()
            if not raw or raw.startswith("#"):
                continue
            name, moves = raw.split("|", 1)
            out.append((name.strip(), parse_opening_moves(moves.strip())))
    return out


def apply_opening(board: chess.Board, moves: list[str]) -> None:
    for uci in moves:
        move = chess.Move.from_uci(uci)
        assert move in board.legal_moves, f"opening move illegal: {uci} in {board.fen()}"
        board.push(move)


def build_schedule(openings: list, repetitions: int) -> list[dict]:
    """Deterministic schedule: opening-major, repetition-minor, AB then BA.

    One paired repetition of an opening = 2 games with exact color reversal, so
    len(schedule) = len(openings) * repetitions * 2 (e.g. 60 * 17 * 2 = 2,040).
    """
    if repetitions < 1:
        raise SystemExit("--repetitions must be >= 1")
    sched = []
    for oi, (oname, _omoves) in enumerate(openings):
        for rep in range(repetitions):
            for pair in ("AB", "BA"):
                sched.append({"schedule_index": len(sched), "opening_index": oi,
                              "opening": oname, "repetition": rep, "color_pair": pair})
    return sched


def schedule_sha256(schedule: list[dict]) -> str:
    blob = json.dumps(schedule, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


# ---------------------------------------------------------------------------
# Adjudication
# ---------------------------------------------------------------------------


def adjudicate(board: chess.Board) -> tuple[str, str] | None:
    """Returns (result, reason) if the game is over, else None."""
    outcome = board.outcome(claim_draw=True)
    if outcome is not None:
        if outcome.winner is None:
            return "1/2-1/2", outcome.termination.name.lower()
        return ("1-0" if outcome.winner == chess.WHITE else "0-1"), outcome.termination.name.lower()
    return None


def harvest_engine_errors(mover: UciEngine, plies: int, turns: list[int]) -> None:
    """Move any buffered panic-fallback markers from the mover into the turns list."""
    if mover.engine_error_events:
        turns.append(plies)
        mover.engine_error_events = []


def play_game(
    white: UciEngine,
    black: UciEngine,
    opening: tuple[str, list[str]],
    movetime_ms: int | None,
    depth: int | None,
    white_name: str,
    black_name: str,
    max_moves: int = 300,
    clock_tc: ClockTC | None = None,
    move_cap_policy: str = "unadjudicated",
) -> dict:
    oname, omoves = opening
    board = chess.Board()
    apply_opening(board, omoves)
    engine_error_turns: list[int] = []
    clock = GameClock(clock_tc) if clock_tc is not None else None

    def err_result(reason: str, error_side: str) -> dict:
        loser = error_side
        return {
            "opening": oname,
            "white": white_name,
            "black": black_name,
            "result": "1-0" if loser == "black" else "0-1",
            "reason": reason,
            "moves": [m.uci() for m in board.move_stack],
            "fen": board.fen(),
            "move_count": len(board.move_stack),
            "engine_error": True,
            "error_side": error_side,
            "engine_error_turns": engine_error_turns,
            "clock_ms_at_end": dict(clock.left_ms) if clock else None,
        }

    while True:
        if board.is_game_over(claim_draw=True):
            break
        if board.fullmove_number > max_moves:
            break
        mover = white if board.turn == chess.WHITE else black
        mover_name = white_name if board.turn == chess.WHITE else black_name
        error_side = "white" if board.turn == chess.WHITE else "black"
        if clock is not None and clock.left_ms["w" if board.turn == chess.WHITE else "b"] <= 0:
            # Flag fall: a normal game result (loss on time), NOT an engine error.
            return {
                "opening": oname,
                "white": white_name,
                "black": black_name,
                "result": "0-1" if board.turn == chess.WHITE else "1-0",
                "reason": "flag",
                "moves": [m.uci() for m in board.move_stack],
                "fen": board.fen(),
                "move_count": len(board.move_stack),
                "engine_error": False,
                "error_side": None,
                "engine_error_turns": engine_error_turns,
                "clock_ms_at_end": dict(clock.left_ms),
            }
        t0 = time.time()
        try:
            mover.set_position(board)
            if clock is not None:
                move_uci = mover.go(clock=clock.go_args(board.turn),
                                    timeout=clock.response_timeout(board.turn))
            else:
                move_uci = mover.go(movetime_ms=movetime_ms, depth=depth)
        except EngineExited:
            harvest_engine_errors(mover, len(board.move_stack) + 1, engine_error_turns)
            return err_result("engine_exited", error_side)
        except TimeoutError:
            harvest_engine_errors(mover, len(board.move_stack) + 1, engine_error_turns)
            return err_result("timeout_forfeit", error_side)
        dt_ms = int((time.time() - t0) * 1000)
        if clock is not None:
            # Charge ACTUAL elapsed wall time to the mover (not a nominal movetime).
            if not clock.charge(board.turn, dt_ms):
                return {
                    "opening": oname,
                    "white": white_name,
                    "black": black_name,
                    "result": "0-1" if board.turn == chess.WHITE else "1-0",
                    "reason": "flag",
                    "moves": [m.uci() for m in board.move_stack],
                    "fen": board.fen(),
                    "move_count": len(board.move_stack),
                    "engine_error": False,
                    "error_side": None,
                    "engine_error_turns": engine_error_turns,
                    "clock_ms_at_end": dict(clock.left_ms),
                }
        try:
            move = chess.Move.from_uci(move_uci)
            if move not in board.legal_moves:
                harvest_engine_errors(mover, len(board.move_stack) + 1, engine_error_turns)
                return err_result("illegal_move", error_side)
        except ValueError:
            harvest_engine_errors(mover, len(board.move_stack) + 1, engine_error_turns)
            return err_result("unparseable_move", error_side)
        board.push(move)
        if clock is not None:
            clock.on_move_made(board.turn)
        harvest_engine_errors(mover, len(board.move_stack), engine_error_turns)
        if dt_ms > 30_000:
            sys.stderr.write(f"slow move {move_uci} ({dt_ms / 1000:.1f}s)\n")

    end = adjudicate(board)
    if end is None:
        # Move-cap termination is NOT a draw: record it unadjudicated unless an
        # explicitly preregistered policy says otherwise (exploratory only).
        if move_cap_policy == "draw":
            end = ("1/2-1/2", "move_cap_draw_policy")
        else:
            return {
                "opening": oname,
                "white": white_name,
                "black": black_name,
                "result": "*",
                "reason": "move_cap_unadjudicated",
                "moves": [m.uci() for m in board.move_stack],
                "fen": board.fen(),
                "move_count": len(board.move_stack),
                "engine_error": bool(engine_error_turns),
                "error_side": None,
                "engine_error_turns": engine_error_turns,
                "adjudicated": False,
                "clock_ms_at_end": dict(clock.left_ms) if clock else None,
            }
    return {
        "opening": oname,
        "white": white_name,
        "black": black_name,
        "result": end[0],
        "reason": end[1],
        "moves": [m.uci() for m in board.move_stack],
        "fen": board.fen(),
        "move_count": len(board.move_stack),
        "engine_error": bool(engine_error_turns),
        "error_side": None,
        "engine_error_turns": engine_error_turns,
        "adjudicated": True,
        "clock_ms_at_end": dict(clock.left_ms) if clock else None,
    }


# ---------------------------------------------------------------------------
# Anchor-pool validation (rating gate §2): fail closed on any placeholder.
# ---------------------------------------------------------------------------

PLACEHOLDER_RE = re.compile(r"tbd|tba|todo|placeholder|\bnull\b|\bnone\b|unknown|n/?a", re.I)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ERROR_CONVENTIONS = {"sd", "se", "ci95", "ci90", "ci99"}

REQUIRED_ANCHOR_KEYS = (
    "rating_source",      # e.g. "CCRL 40/15 list"
    "list_publication_date",
    "retrieval_date",
    "time_control",
    "engines",            # list of anchor engines
)
REQUIRED_ANCHOR_ENGINE_KEYS = (
    "name", "version", "sha256", "published_elo", "published_error",
    "error_convention", "license", "license_verified",
    "binary_source_url", "binary_downloaded", "binary_sha256_verified",
)


def _fail(msg: str) -> None:
    raise SystemExit(f"anchor-json: {msg}")


def _require_str(eng: dict, key: str, i: int, pattern: str | None = None) -> str:
    v = eng.get(key)
    if not isinstance(v, str) or not v.strip():
        _fail(f"engines[{i}].{key} must be a non-empty string")
    if PLACEHOLDER_RE.search(v):
        _fail(f"engines[{i}].{key} contains a placeholder value: {v!r}")
    if pattern and not re.search(pattern, v):
        _fail(f"engines[{i}].{key} does not match required pattern {pattern}")
    return v


def _require_anchor_schema(pool) -> None:
    """Fail fast unless the anchor descriptor is complete and verified (rating §2).

    Rejects: TBD/placeholder strings, null/missing ratings, malformed SHA-256,
    invalid dates, missing source information, unverified binaries, missing or
    ambiguous uncertainty conventions, unverified licenses.
    """
    if not isinstance(pool, dict):
        _fail("top level must be an object")
    missing = [k for k in REQUIRED_ANCHOR_KEYS if k not in pool]
    if missing:
        _fail(f"missing keys: {', '.join(missing)}")
    for key in ("rating_source", "time_control"):
        v = pool[key]
        if not isinstance(v, str) or not v.strip() or PLACEHOLDER_RE.search(v):
            _fail(f"{key} must be a non-empty, non-placeholder string")
    for key in ("list_publication_date", "retrieval_date"):
        v = pool[key]
        if not isinstance(v, str) or not DATE_RE.match(v):
            _fail(f"{key} must be an ISO date (YYYY-MM-DD), got {v!r}")
        try:
            time.strptime(v, "%Y-%m-%d")
        except ValueError:
            _fail(f"{key} is not a valid date: {v!r}")
    engines = pool["engines"]
    if not isinstance(engines, list) or not engines:
        _fail("'engines' must be a non-empty list")
    for i, eng in enumerate(engines):
        if not isinstance(eng, dict):
            _fail(f"engines[{i}] must be an object")
        miss = [k for k in REQUIRED_ANCHOR_ENGINE_KEYS if k not in eng]
        if miss:
            _fail(f"engines[{i}] missing keys: {', '.join(miss)}")
        _require_str(eng, "name", i)
        _require_str(eng, "version", i)
        sha = _require_str(eng, "sha256", i)
        if not SHA256_RE.match(sha.lower()):
            _fail(f"engines[{i}].sha256 is not a 64-hex SHA-256: {sha!r}")
        for key in ("published_elo", "published_error"):
            v = eng[key]
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                _fail(f"engines[{i}].{key} must be numeric, got {v!r}")
            if PLACEHOLDER_RE.search(str(v)):
                _fail(f"engines[{i}].{key} contains a placeholder value: {v!r}")
        if eng["published_error"] <= 0:
            _fail(f"engines[{i}].published_error must be > 0 (uncertainty cannot be zero)")
        conv = eng["error_convention"]
        if not isinstance(conv, str) or conv.lower() not in ERROR_CONVENTIONS:
            _fail(
                f"engines[{i}].error_convention must be one of {sorted(ERROR_CONVENTIONS)} "
                f"(explicit uncertainty convention), got {conv!r}"
            )
        lic = _require_str(eng, "license", i)
        if not isinstance(eng.get("license_verified"), bool) or eng["license_verified"] is not True:
            _fail(f"engines[{i}].license_verified must be true (license checked: {lic!r})")
        _require_str(eng, "binary_source_url", i, pattern=r"^https://")
        for key in ("binary_downloaded", "binary_sha256_verified"):
            if not isinstance(eng.get(key), bool) or eng[key] is not True:
                _fail(f"engines[{i}].{key} must be true (binary must be present and hash-verified)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--white-cmd", required=True)
    ap.add_argument("--black-cmd", required=True)
    ap.add_argument("--white-name", default="engine-white")
    ap.add_argument("--black-name", default="engine-black")
    ap.add_argument("--openings", required=True, help="file with 'name|moves' lines")
    ap.add_argument("--out", required=True, help="output directory (created)")
    ap.add_argument("--movetime", type=int, default=None, help="ms per move (fixed; screening only)")
    ap.add_argument("--depth", type=int, default=None, help="fixed search depth (overrides movetime)")
    ap.add_argument("--tc", default=None,
                    help="clock time control 'moves/minutes' (e.g. '40/15') or 'moves/seconds' "
                         "(e.g. '40/900s'); repeating schedule with movestogo")
    ap.add_argument("--tc-inc", type=float, default=0.0, help="increment seconds per move (clock mode)")
    ap.add_argument("--tc-policy", choices=("add", "reset"), default="add",
                    help="period boundary: 'add' a fresh period to remaining time (classic "
                         "repeating control) or 'reset' the clock to the period")
    ap.add_argument("--games", type=int, default=None, help="cap number of games (screening)")
    ap.add_argument("--repetitions", type=int, default=1,
                    help="paired repetitions per opening (1 repetition = 2 games, AB/BA); "
                         "e.g. --repetitions 17 with 60 openings = 2,040 games")
    ap.add_argument("--hash", type=int, default=None)
    ap.add_argument("--threads", type=int, default=None,
                    help="set each engine's UCI Threads option (e.g. 1 for single-thread benchmarks)")
    ap.add_argument("--skill-white", type=int, default=None)
    ap.add_argument("--skill-black", type=int, default=None)
    ap.add_argument("--max-moves", type=int, default=300)
    ap.add_argument("--move-cap-policy", choices=("unadjudicated", "draw"), default="unadjudicated",
                    help="'unadjudicated' (default; recorded as '*' and not scored) or 'draw' "
                         "(exploratory only — never gate evidence)")
    ap.add_argument("--max-errors-per-side", type=int, default=2,
                    help="abort the batch as invalid once a side accumulates this many engine "
                         "errors (protocol §3: 2 failures at the same anchor invalidate it)")
    ap.add_argument("--max-replays-per-game", type=int, default=1,
                    help="engine-error games are replayed up to this many times (attempt lines "
                         "are all recorded; only counted attempts are scored)")
    ap.add_argument("--batch-id", default=None, help="preregistered batch identity (e.g. 'A')")
    ap.add_argument("--shard-id", default=None, help="deterministic shard identity")
    ap.add_argument("--shard-index", type=int, default=None,
                    help="0-based shard index for deterministic sharding (with --shard-count): "
                         "plays a contiguous slice of the frozen schedule (opening range x "
                         "repetition range)")
    ap.add_argument("--shard-count", type=int, default=None, help="total number of shards")
    ap.add_argument("--schedule-indices", nargs="+", type=int, default=None,
                    help="run only these frozen schedule indices within this shard (recovery only)")
    ap.add_argument("--anchor-json", default=None,
                    help="path to JSON anchor-pool descriptor (rating source, published Elo±error + "
                         "convention, list publication/retrieval dates, TC, verified binaries); "
                         "embedded verbatim into meta.json")
    ap.add_argument("--white-artifact", default="",
                    help="os.pathsep-separated extra files hashed into the WHITE artifact "
                         "(e.g. WASM a wrapper loads dynamically)")
    ap.add_argument("--black-artifact", default="",
                    help="os.pathsep-separated extra files hashed into the BLACK artifact")
    args = ap.parse_args()

    if args.threads is not None and args.threads < 1:
        ap.error("--threads must be >= 1")

    tc_modes = [m for m in (args.movetime, args.depth, args.tc) if m is not None]
    if len(tc_modes) != 1:
        ap.error("exactly one time-control mode required: --tc (rating) | --movetime | --depth (screening)")

    anchor_pool = None
    if args.anchor_json:
        with open(args.anchor_json) as f:
            anchor_pool = json.load(f)
        _require_anchor_schema(anchor_pool)

    clock_tc = parse_tc(args.tc, args.tc_inc, args.tc_policy) if args.tc else None

    openings = load_openings(args.openings)
    schedule = build_schedule(openings, args.repetitions)
    shard_meta = None
    if (args.shard_index is None) != (args.shard_count is None):
        ap.error("--shard-index and --shard-count must be used together")
    if args.shard_count is not None:
        if not (0 <= args.shard_index < args.shard_count):
            ap.error("--shard-index must be in [0, --shard-count)")
        n = len(schedule)
        lo = args.shard_index * n // args.shard_count
        hi = (args.shard_index + 1) * n // args.shard_count
        shard_meta = {
            "shard_index": args.shard_index,
            "shard_count": args.shard_count,
            "schedule_lo": lo,
            "schedule_hi": hi,
        }
        schedule = schedule[lo:hi]
    if args.schedule_indices is not None:
        if args.shard_count is None:
            ap.error("--schedule-indices requires --shard-index and --shard-count")
        requested = args.schedule_indices
        if not requested or len(set(requested)) != len(requested) or requested != sorted(requested):
            ap.error("--schedule-indices must be a non-empty, unique, ascending list")
        available = {entry["schedule_index"] for entry in schedule}
        if not set(requested).issubset(available):
            ap.error("--schedule-indices contains an index outside this shard's frozen slice")
        requested_set = set(requested)
        schedule = [entry for entry in schedule if entry["schedule_index"] in requested_set]
        if len(schedule) != len(requested):
            ap.error("--schedule-indices could not be resolved exactly")
        shard_meta["selected_schedule_indices"] = requested
    if args.schedule_indices is not None and args.games is not None:
        ap.error("--games cannot be combined with exact --schedule-indices recovery")
    if args.games is not None:
        schedule = schedule[: args.games]

    os.makedirs(args.out, exist_ok=True)
    # Reserve the batch output atomically BEFORE starting any engine: exclusive creation
    # of the three artifacts. Two concurrent invocations in the same --out (or a rerun
    # over a partial batch) fail here instead of mixing or truncating each other's files.
    try:
        for name in ("games.pgn", "games.jsonl", "meta.json"):
            fd = os.open(os.path.join(args.out, name), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            os.close(fd)
    except FileExistsError as e:
        ap.error(
            f"batch output already reserved/exists: {e.filename} — choose a fresh --out directory "
            f"(never overwriting or mixing a batch; if it is an empty crash remnant, remove it explicitly)"
        )

    white = UciEngine(
        EngineSpec(args.white_name, args.white_cmd.split()),
        hash_mb=args.hash,
        skill=args.skill_white,
        threads=args.threads,
    )
    black = UciEngine(
        EngineSpec(args.black_name, args.black_cmd.split()),
        hash_mb=args.hash,
        skill=args.skill_black,
        threads=args.threads,
    )

    pgn_path = os.path.join(args.out, "games.pgn")
    jsonl_path = os.path.join(args.out, "games.jsonl")
    meta_path = os.path.join(args.out, "meta.json")

    tc_desc = clock_tc.describe() if clock_tc else {
        "mode": "depth" if args.depth else "movetime",
        "depth": args.depth, "movetime_ms": args.movetime,
        "note": "screening only — never gate evidence",
    }

    def write_meta() -> None:
        with open(meta_path, "w") as mf:
            json.dump(meta, mf, indent=2)

    meta = {
        "manifest_version": 2,
        "completion_status": "in_progress",
        "white_cmd": args.white_cmd,
        "black_cmd": args.black_cmd,
        "white_name": args.white_name,
        "black_name": args.black_name,
        "batch_id": args.batch_id,
        "shard_id": args.shard_id,
        "time_control": tc_desc,
        "hash_mb": args.hash,
        "threads": args.threads,
        "skill_white": args.skill_white,
        "skill_black": args.skill_black,
        "openings_file": os.path.abspath(args.openings),
        "openings_file_sha256": file_sha256(args.openings),
        "schedule": {
            "repetitions": args.repetitions,
            "colors": "AB/BA exact reversal per (opening, repetition)",
            "order": "opening-major, repetition-minor, AB then BA",
            "schedule_sha256": schedule_sha256(schedule),
            "n_scheduled": len(schedule),
            "shard": shard_meta,
        },
        "n_games_planned": len(schedule),
        "error_policy": {
            "max_errors_per_side": args.max_errors_per_side,
            "max_replays_per_game": args.max_replays_per_game,
            "move_cap_policy": args.move_cap_policy,
            "note": "engine-error attempts are recorded uncounted and replayed; "
                    "batch aborts as invalid at max_errors_per_side for any side",
        },
        # Probe archaeology: which exact binaries produced this batch, and which commit.
        "white_artifact": probe_artifact(args.white_cmd, args.white_artifact),
        "black_artifact": probe_artifact(args.black_cmd, args.black_artifact),
        "git_commit": git_head(),
        "hardware": hardware_info(),
        # The engine process inherits this variable, so it decides the evaluation the batch was
        # produced under. Recording the effective value (including the unset case) means a saved
        # record identifies its own ablation condition: without it, an ablated run and a full run
        # from the same commit and seed would produce indistinguishable manifests.
        "flawless_ablate": os.environ.get("FLAWLESS_ABLATE", ""),
        "anchor_pool": anchor_pool,
        "color_pairs": "AB/BA alternating per (opening, repetition) (exact color reversal)",
        "adjudication": "FIDE termination via python-chess outcome(claim_draw=True) (50-move/3-fold "
                        "claims enforced); flag-on-time => loss; illegal/exit/timeout => engine_error "
                        "attempt (recorded, replayed per policy); move_cap => unadjudicated '*' by default",
    }
    # Persist the manifest BEFORE any game runs and before the game streams open.
    # Provenance must survive a crash/interrupt mid-batch. Finalization after the match
    # adds counters + end timestamp + completion_status; an interrupted run stays
    # visibly 'in_progress' here.
    meta["match_utc_start"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    write_meta()

    errors_by_side: Counter = Counter()
    counts = {"attempts": 0, "counted": 0, "replays": 0, "engine_errors": 0, "unadjudicated": 0}
    completion_status = "completed"
    pending: list[tuple[dict, int]] = [(s, 0) for s in schedule]  # (schedule entry, replay depth)

    with open(jsonl_path, "w") as jf, open(pgn_path, "w") as pgn:
        game_no = 0
        while pending:
            entry, replay_depth = pending.pop(0)
            game_no += 1
            pair = entry["color_pair"]
            if pair == "AB":
                w_name, b_name = args.white_name, args.black_name
                w_cmd, b_cmd = args.white_cmd, args.black_cmd
                w_skill, b_skill = args.skill_white, args.skill_black
            else:
                w_name, b_name = args.black_name, args.white_name
                w_cmd, b_cmd = args.black_cmd, args.white_cmd
                w_skill, b_skill = args.skill_black, args.skill_white
            opening = (entry["opening"], openings[entry["opening_index"]][1])
            w = UciEngine(
                EngineSpec(w_name, w_cmd.split()),
                hash_mb=args.hash,
                skill=w_skill,
                threads=args.threads,
            )
            b = UciEngine(
                EngineSpec(b_name, b_cmd.split()),
                hash_mb=args.hash,
                skill=b_skill,
                threads=args.threads,
            )
            t0 = time.time()
            try:
                result = play_game(
                    w, b, opening,
                    args.movetime, args.depth, w_name, b_name, args.max_moves,
                    clock_tc=clock_tc, move_cap_policy=args.move_cap_policy,
                )
            finally:
                w.quit()
                b.quit()
            result["wall_seconds"] = round(time.time() - t0, 3)
            result["color_pair"] = pair
            result["game_index"] = game_no
            result["schedule_index"] = entry["schedule_index"]
            result["repetition"] = entry["repetition"]
            result["replay_of_schedule_index"] = entry["schedule_index"] if replay_depth else None
            result["replay_depth"] = replay_depth

            counts["attempts"] += 1
            if result.get("engine_error"):
                # Engine errors are NEVER ordinary results: recorded uncounted, replayed
                # per policy, and any side hitting the per-side limit aborts the batch.
                result["counted"] = False
                counts["engine_errors"] += 1
                culprit = result.get("error_side") or "unknown"
                errors_by_side[culprit] += 1
                if replay_depth < args.max_replays_per_game:
                    counts["replays"] += 1
                    # Replay IMMEDIATELY (depth-first): a second consecutive failure must
                    # abort the batch promptly, not after thousands of queued games.
                    pending.insert(0, (entry, replay_depth + 1))
                if errors_by_side[culprit] >= args.max_errors_per_side:
                    completion_status = "aborted_engine_errors"
            elif result.get("adjudicated") is False:
                result["counted"] = False
                counts["unadjudicated"] += 1
            else:
                result["counted"] = True
                counts["counted"] += 1

            jf.write(json.dumps(result) + "\n")
            jf.flush()

            game = chess.pgn.Game()
            game.headers["Event"] = f"benchmark match {args.batch_id or ''}".strip()
            game.headers["Site"] = "local"
            game.headers["Date"] = time.strftime("%Y.%m.%d", time.gmtime())
            game.headers["Round"] = str(game_no)
            game.headers["White"] = w_name
            game.headers["Black"] = b_name
            game.headers["Opening"] = entry["opening"]
            game.headers["Result"] = result["result"]
            node = game
            for uci in opening[1]:
                mv = chess.Move.from_uci(uci)
                node = node.add_variation(mv)
            for uci in result["moves"][len(opening[1]):]:
                mv = chess.Move.from_uci(uci)
                node = node.add_variation(mv)
            pgn.write(str(game) + "\n\n")
            pgn.flush()
            print(
                f"[game {game_no:4d}] sched#{entry['schedule_index']:4d} rep{entry['repetition']:2d} "
                f"{entry['opening'][:28]:<28} {w_name} vs {b_name} -> {result['result']} ({result['reason']})"
            )
            if completion_status != "completed":
                break

    white.quit()
    black.quit()

    # Finalize the manifest after execution. An interrupted run never reaches this
    # point and stays visibly 'in_progress'.
    meta["match_utc_end"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    meta["completion_status"] = completion_status
    meta["n_attempts"] = counts["attempts"]
    meta["n_games_counted"] = counts["counted"]
    meta["n_replays"] = counts["replays"]
    meta["n_engine_errors"] = counts["engine_errors"]
    meta["n_unadjudicated"] = counts["unadjudicated"]
    meta["engine_errors_by_side"] = dict(errors_by_side)
    write_meta()

    if completion_status != "completed":
        sys.stderr.write(f"BATCH ABORTED ({completion_status}) — invalid per protocol §3\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
