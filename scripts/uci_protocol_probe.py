#!/usr/bin/env python3
"""Raw UCI protocol probes against the exact executable (stdlib only).

Each probe sends commands, waits for the expected reply with a bounded timeout, and
asserts: bestmove is legal (checked with python-chess when available), stdout is UCI-only,
and the process exits 0 on quit. Usage: python3 scripts/uci_protocol_probe.py <exe>
"""
import queue, subprocess, sys, threading, time
try:
    import chess
except ImportError:
    sys.exit("uci_protocol_probe.py requires python-chess (pip install chess==1.11.2)")

EXE = sys.argv[1]
results = []

ALLOWED_OUT = ("id ", "option ", "uciok", "readyok", "info ", "bestmove ")
ENGINES = []  # every engine started by the current check; killed and reaped by check() on exit

def unknown_lines(lines):
    return [l for l in lines if l and not l.startswith(ALLOWED_OUT)]

class Eng:
    def __init__(self):
        self.p = subprocess.Popen([EXE], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.q = queue.Queue(); self.all = []; self.err = []
        ENGINES.append(self)
        self.reader = threading.Thread(target=self._r, daemon=True); self.reader.start()
        # Drain stderr so a chatty engine can never block on a full pipe.
        threading.Thread(target=lambda: self.err.append(self.p.stderr.read()), daemon=True).start()
    def _r(self):
        for raw in iter(self.p.stdout.readline, b""):
            l = raw.decode("utf-8", "replace").rstrip("\r\n"); self.q.put(l); self.all.append(l)
        self.q.put(None)
    def send(self, s):
        self.p.stdin.write((s + "\n").encode()); self.p.stdin.flush()
    def until(self, pred, timeout, what):
        end = time.monotonic() + timeout; seen = []
        while True:
            r = end - time.monotonic()
            if r <= 0: raise AssertionError(f"timeout waiting for {what}; last={seen[-3:]}")
            try: l = self.q.get(timeout=min(r, 0.2))
            except queue.Empty: continue
            if l is None: raise AssertionError(f"EOF waiting for {what}; last={seen[-3:]}")
            seen.append(l)
            if pred(l): return seen
    def close(self):
        """Wait (bounded) for the engine to exit on its own after `quit`; only then close stdin.
        Closing stdin first would let EOF end an engine that ignores `quit`, hiding the failure.
        Then drain every stdout line and validate all of them."""
        try:
            code = self.p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.p.kill(); self.p.wait(); raise AssertionError("engine did not exit after quit")
        finally:
            try: self.p.stdin.close()
            except OSError: pass
        self.reader.join(5)
        if self.reader.is_alive():
            raise AssertionError("stdout not drained after exit")
        bad = unknown_lines(self.all)
        if bad:
            raise AssertionError(f"unexpected stdout lines (all output is checked, incl. before uciok): {bad[:3]}")
        return code

def check(name, fn):
    try:
        fn(); results.append((name, "PASS", ""))
    except AssertionError as e:
        results.append((name, "FAIL", str(e)))
    except Exception as e:
        results.append((name, "ERROR", repr(e)))
    finally:
        # Unconditional cleanup: kill, reap, and close pipes of every engine this check started.
        for e in ENGINES:
            if e.p.poll() is None:
                e.p.kill()
            e.p.wait()
            for f in (e.p.stdin, e.p.stdout, e.p.stderr):
                try: f.close()
                except Exception: pass
        ENGINES.clear()

def bestmove_of(lines):
    bm = [l for l in lines if l.startswith("bestmove")]
    assert len(bm) == 1, f"expected exactly one bestmove, got {bm}"
    return bm[0].split()[1]

def legal_check(fen_moves, mv):
    b = chess.Board()
    for m in fen_moves: b.push_uci(m)
    assert chess.Move.from_uci(mv) in b.legal_moves, f"illegal bestmove {mv}"

def t_handshake():
    e = Eng(); e.send("uci")
    lines = e.until(lambda l: l == "uciok", 10, "uciok")
    assert any(l.startswith("id name Flawless") for l in lines), "no id name"
    e.send("isready"); e.until(lambda l: l == "readyok", 10, "readyok")
    e.send("quit"); assert e.close() == 0

def t_no_banner_on_stdout():
    e = Eng(); time.sleep(0.3); assert e.p.poll() is None, "exited before commands"
    assert not e.all, f"stdout before commands: {e.all}"
    e.send("quit"); assert e.close() == 0

def t_depth_bestmove_after_moves():
    e = Eng(); e.send("uci"); e.until(lambda l: l == "uciok", 10, "uciok")
    e.send("ucinewgame"); e.send("isready"); e.until(lambda l: l == "readyok", 10, "readyok")
    e.send("position startpos moves e2e4 e7e5 g1f3")
    e.send("go depth 4")
    lines = e.until(lambda l: l.startswith("bestmove"), 60, "bestmove")
    assert any(l.startswith("info depth 4") for l in lines), "no completed depth-4 info"
    legal_check(["e2e4", "e7e5", "g1f3"], bestmove_of(lines))
    e.send("quit"); assert e.close() == 0

def t_tiny_clock_no_hang():
    # 10 ms clock with no increment: engine must answer promptly and never hang.
    e = Eng(); e.send("uci"); e.until(lambda l: l == "uciok", 10, "uciok")
    e.send("position startpos")
    t = time.monotonic(); e.send("go wtime 10 btime 10 winc 0 binc 0")
    lines = e.until(lambda l: l.startswith("bestmove"), 15, "bestmove under 10ms clock")
    dt = time.monotonic() - t
    assert dt < 5, f"took {dt:.2f}s on a 10ms clock"
    legal_check([], lines[-1].split()[1])
    e.send("quit"); assert e.close() == 0

def t_movetime():
    e = Eng(); e.send("uci"); e.until(lambda l: l == "uciok", 10, "uciok")
    e.send("position startpos"); t = time.monotonic(); e.send("go movetime 300")
    lines = e.until(lambda l: l.startswith("bestmove"), 15, "bestmove")
    dt = time.monotonic() - t
    # UCI requires no overrun. Since the fixed-time fix the engine uses ~100% of movetime, so
    # only the upper bound is asserted here (the tight tolerance lives in tests/movetime_smoke.rs).
    # Shared CI runners are noisy; the tight 80%-300ms tolerance lives in tests/movetime_smoke.rs.
    assert dt < 1.5, f"movetime 300ms returned after {dt:.3f}s (overrun)"
    legal_check([], bestmove_of(lines))  # the movetime result must be legal from the start position
    e.send("quit"); assert e.close() == 0

def t_infinite_stop():
    e = Eng(); e.send("uci"); e.until(lambda l: l == "uciok", 10, "uciok")
    e.send("position startpos"); e.send("go infinite")
    time.sleep(0.5)
    assert not any(l.startswith("bestmove") for l in e.all), "premature bestmove on infinite"
    t = time.monotonic(); e.send("stop")
    lines = e.until(lambda l: l.startswith("bestmove"), 10, "bestmove after stop")
    assert time.monotonic() - t < 2.0, "stop latency > 2s"
    legal_check([], lines[-1].split()[1])
    e.send("quit"); assert e.close() == 0

def t_quit_during_infinite():
    e = Eng(); e.send("uci"); e.until(lambda l: l == "uciok", 10, "uciok")
    e.send("position startpos"); e.send("go infinite"); time.sleep(0.3)
    e.send("quit"); code = e.close()
    assert code == 0, f"exit {code} after quit during search"

def t_setoption_and_unknown():
    e = Eng(); e.send("uci"); e.until(lambda l: l == "uciok", 10, "uciok")
    e.send("setoption name Hash value 16"); e.send("setoption name NoSuchOption value 1")
    e.send("bogus command here"); e.send("isready")
    e.until(lambda l: l == "readyok", 10, "readyok after junk")
    e.send("quit"); assert e.close() == 0

def t_fen_position():
    e = Eng(); e.send("uci"); e.until(lambda l: l == "uciok", 10, "uciok")
    fen = "4k3/1P6/8/8/8/8/6p1/4K3 w - - 0 1"
    e.send(f"position fen {fen}"); e.send("go depth 3")
    lines = e.until(lambda l: l.startswith("bestmove"), 30, "bestmove")
    mv = lines[-1].split()[1]
    assert chess.Move.from_uci(mv) in chess.Board(fen).legal_moves, f"illegal {mv}"
    e.send("quit"); assert e.close() == 0

def t_en_passant_capture():
    """En passant must be generated, accepted as a root move, and returned as bestmove.
    `go searchmoves` restricts the root to the single en passant capture, so the engine's
    answer is forced to be that capture; python-chess confirms it is en passant."""
    cases = [
        # 1.e4 a6 2.e5 d5: white e5xd6 en passant
        ("startpos moves e2e4 a7a6 e4e5 d7d5", None, "e5d6"),
        # position with ep square f6 after f7-f5 (white pawn on e5)
        (None, "rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3", "e5f6"),
    ]
    for pos_moves, fen, want in cases:
        e = Eng(); e.send("uci"); e.until(lambda l: l == "uciok", 10, "uciok")
        e.send(f"position {'fen ' + fen if fen else pos_moves}")
        e.send("isready"); e.until(lambda l: l == "readyok", 10, "readyok")
        board = chess.Board(fen) if fen else chess.Board()
        if not fen:
            for m in pos_moves.split()[2:]:
                board.push_uci(m)
        target = chess.Move.from_uci(want)
        assert target in board.legal_moves, f"{want} is not legal here (test setup)"
        assert board.is_en_passant(target), f"{want} is not an en passant capture (test setup)"
        e.send(f"go depth 2 searchmoves {want}")
        lines = e.until(lambda l: l.startswith("bestmove"), 20, "bestmove")
        mv = bestmove_of(lines)
        assert mv == want, f"expected en passant {want}, got {mv}"
        e.send("quit"); assert e.close() == 0

def t_searchmoves_only_illegal_moves():
    """`go searchmoves` naming only illegal moves must still answer with a legal move.
    Regression: the engine used to print `bestmove 0000` here."""
    e = Eng(); e.send("uci"); e.until(lambda l: l == "uciok", 10, "uciok")
    e.send("position startpos"); e.send("go depth 2 searchmoves e2e5")
    lines = e.until(lambda l: l.startswith("bestmove"), 20, "bestmove")
    mv = bestmove_of(lines)
    assert mv != "0000", "null bestmove although the start position has legal moves"
    legal_check([], mv)
    e.send("quit"); assert e.close() == 0

def t_stalemate_position_no_legal_move():
    # Black to move, stalemated: engine must not invent a move; it should report bestmove 0000 or none.
    e = Eng(); e.send("uci"); e.until(lambda l: l == "uciok", 10, "uciok")
    e.send("position fen 7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"); e.send("go depth 3")
    try:
        lines = e.until(lambda l: l.startswith("bestmove"), 15, "bestmove on stalemate")
        bm = lines[-1].split()[1]
        assert bm in ("0000", "(none)"), f"stalemate returned move {bm}"
    except AssertionError as ex:
        raise AssertionError(f"no bestmove reply on stalemate: {ex}")
    e.send("quit"); assert e.close() == 0

for name, fn in [("handshake", t_handshake), ("no banner", t_no_banner_on_stdout),
                 ("depth-4 after moves", t_depth_bestmove_after_moves),
                 ("10ms clock no hang", t_tiny_clock_no_hang), ("movetime 300", t_movetime),
                 ("infinite+stop", t_infinite_stop), ("quit during infinite", t_quit_during_infinite),
                 ("setoption/junk tolerant", t_setoption_and_unknown),
                 ("position fen promo", t_fen_position), ("stalemate", t_stalemate_position_no_legal_move),
                 ("en passant capture", t_en_passant_capture),
                 ("searchmoves illegal only", t_searchmoves_only_illegal_moves)]:
    check(name, fn)

for n, s, d in results:
    print(f"{s:6s} {n}" + (f"  -- {d}" if d else ""))
bad = [r for r in results if r[1] != "PASS"]
print(f"{len(results)-len(bad)}/{len(results)} passed")
sys.exit(1 if bad else 0)
