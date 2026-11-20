#!/usr/bin/env python3
"""Unit tests for scripts/windows_artifact.py (no engine or Windows needed).

Covers the bestmove grammar (including the optional ponder suffix), PE machine
parsing on synthetic headers, and the informational-only bench behaviour.
"""

import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import windows_artifact as wa  # noqa: E402


def synthetic_pe(machine):
    """Minimal PE header: MZ, e_lfanew = 0x80, PE\\0\\0, COFF machine field."""
    buf = bytearray(0x100)
    buf[0:2] = b"MZ"
    struct.pack_into("<I", buf, 0x3C, 0x80)
    buf[0x80:0x84] = b"PE\x00\x00"
    struct.pack_into("<H", buf, 0x84, machine)
    return bytes(buf)


class BestmoveGrammar(unittest.TestCase):
    def match(self, line):
        m = wa.BESTMOVE_RE.match(line)
        return m.group(1) if m else None

    def test_bare_bestmove(self):
        self.assertEqual(self.match("bestmove e2e4"), "e2e4")

    def test_promotion(self):
        self.assertEqual(self.match("bestmove a7a8q"), "a7a8q")

    def test_ponder_suffix_keeps_selected_move(self):
        self.assertEqual(self.match("bestmove e2e4 ponder e7e5"), "e2e4")

    def test_rejects_null_and_garbage(self):
        self.assertIsNone(self.match("bestmove 0000"))
        self.assertIsNone(self.match("bestmove e2e4 extra"))
        self.assertIsNone(self.match("bestmove e2e4 ponder"))
        self.assertIsNone(self.match("info bestmove e2e4"))


class PeMachine(unittest.TestCase):
    def write(self, data):
        f = tempfile.NamedTemporaryFile(delete=False)
        f.write(data)
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_x86_64(self):
        self.assertEqual(wa.pe_machine(self.write(synthetic_pe(0x8664))), 0x8664)

    def test_i386_is_reported_not_accepted_silently(self):
        self.assertEqual(wa.pe_machine(self.write(synthetic_pe(0x014C))), 0x014C)

    def test_elf_rejected(self):
        elf = b"\x7fELF" + b"\x00" * 200
        with self.assertRaises(wa.CheckError):
            wa.pe_machine(self.write(elf))

    def test_missing_pe_signature_rejected(self):
        data = bytearray(synthetic_pe(0x8664))
        data[0x80:0x84] = b"XX\x00\x00"
        with self.assertRaises(wa.CheckError):
            wa.pe_machine(self.write(bytes(data)))


class BenchIsInformational(unittest.TestCase):
    def test_bench_timeout_does_not_raise(self):
        orig = wa.run_engine

        def boom(*a, **k):
            raise wa.CheckError("did not exit within 120s")

        wa.run_engine = boom
        try:
            result = wa.bench_signature("flawless.exe")
        finally:
            wa.run_engine = orig
        self.assertTrue(result.startswith("unavailable"), result)

    def test_signature_parsed(self):
        orig = wa.run_engine
        wa.run_engine = lambda *a, **k: (0, "bench signature: 141943aa23b3fc68\n", "")
        try:
            self.assertEqual(wa.bench_signature("flawless.exe"), "141943aa23b3fc68")
        finally:
            wa.run_engine = orig


class DepthEvidence(unittest.TestCase):
    """uci_session_bestmove must reject a bestmove with no completed depth-2 info line."""

    def run_with_lines(self, emitted):
        orig = wa.Session

        class Fake:
            def __init__(self, exe, args):
                self.lines = []
                self.feed = list(emitted)
                self.stderr_chunks = []

            def send(self, cmd):
                pass

            def read_until(self, pred, what):
                while self.feed:
                    line = self.feed.pop(0)
                    self.lines.append(line)
                    if pred(line):
                        return self.lines
                raise wa.CheckError(f"no line for {what}")

            def finish(self, eof=True):
                return 0

            def kill(self):
                pass

        wa.Session = Fake
        try:
            return wa.uci_session_bestmove("flawless", [], "t")
        finally:
            wa.Session = orig

    base = ["id name Flawless", "uciok", "readyok", "readyok"]

    def test_depth2_accepted(self):
        lines = self.base + ["info depth 1 seldepth 1 multipv 1 score cp 37 nodes 53", "info depth 2 seldepth 4 multipv 1 score cp 12", "bestmove b1c3 ponder b8c6"]
        _, bm, code, _ = self.run_with_lines(lines)
        self.assertEqual((bm, code), ("b1c3", 0))

    def test_depth0_fallback_rejected(self):
        lines = self.base + ["bestmove a2a3"]
        with self.assertRaises(wa.CheckError):
            self.run_with_lines(lines)




class CargoMetadata(unittest.TestCase):
    def test_package_version_read_from_package_table_only(self):
        text = '[package]\nname = "x"\nversion = "9.8.7"\n\n[dependencies]\nversion = "1.0"\n'
        orig = wa.cargo_toml_text
        try:
            wa.cargo_toml_text = lambda: text
            self.assertEqual(wa.cargo_package_version(), "9.8.7")
            wa.cargo_toml_text = lambda: '[package]\nname = "x"\n\n[dependencies]\nversion = "1.0"\n'
            with self.assertRaises(wa.CheckError):
                wa.cargo_package_version()
        finally:
            wa.cargo_toml_text = orig

    def test_release_profile_is_read_not_hard_coded(self):
        text = '[profile.release]\nlto = "fat"\ncodegen-units = 1\npanic = "unwind"  # keep unwind\n'
        orig = wa.cargo_toml_text
        try:
            wa.cargo_toml_text = lambda: text
            line = wa.release_profile_manifest_line()
            self.assertIn("lto=fat", line)
            self.assertIn("codegen-units=1", line)
            self.assertIn("panic=unwind", line)
            self.assertNotIn("debug=", line)  # absent from the table, so not claimed
        finally:
            wa.cargo_toml_text = orig

    def test_real_repository_values(self):
        self.assertRegex(wa.cargo_package_version(), r"^\d+\.\d+\.\d+")
        self.assertIn("lto=fat", wa.release_profile_manifest_line())

FAKE_ENGINE = r'''
import os, sys
mode = os.environ.get("FAKE_MODE", "")
if mode == "banner":
    print("usage: flawless <command>", flush=True)
for raw in sys.stdin:
    cmd = raw.strip()
    if cmd == "uci":
        print("id name Flawless", flush=True)
        print("uciok", flush=True)
    elif cmd == "isready":
        print("readyok", flush=True)
    elif cmd.startswith("go"):
        # Search output differs from the handshake; the handshake snapshot must not change.
        print("info depth 2 score cp 10 pv e2e4", flush=True)
        print("bestmove e2e4", flush=True)
    elif cmd == "quit":
        if mode == "noquit":
            continue  # ignores quit: only EOF would end it
        if mode == "trailing":
            print("Thinking about the position", flush=True)
        sys.exit(0)
'''


class StdoutCapture(unittest.TestCase):
    def setUp(self):
        fd, self.script = tempfile.mkstemp(suffix=".py")
        with os.fdopen(fd, "w") as f:
            f.write(FAKE_ENGINE)
        self._old_mode = os.environ.get("FAKE_MODE")

    def tearDown(self):
        os.unlink(self.script)
        if self._old_mode is None:
            os.environ.pop("FAKE_MODE", None)
        else:
            os.environ["FAKE_MODE"] = self._old_mode

    def session(self, mode):
        os.environ["FAKE_MODE"] = mode
        return wa.Session(sys.executable, [self.script])

    def test_handshake_snapshot_unaffected_by_search_output(self):
        hs, bestmove, code, lines = wa.uci_session_bestmove(sys.executable, [self.script], "fake")
        self.assertEqual(hs, ["id name Flawless", "uciok"])
        self.assertEqual(bestmove, "e2e4")
        self.assertEqual(code, 0)
        self.assertTrue(any(l.startswith("info depth 2") for l in lines))

    def test_stdout_after_quit_is_checked(self):
        os.environ["FAKE_MODE"] = "trailing"
        with self.assertRaises(wa.CheckError):
            wa.uci_session_bestmove(sys.executable, [self.script], "trailing")

    def test_engine_ignoring_quit_is_not_passed_by_eof(self):
        # Regression: finish() used to close stdin before waiting, so EOF let an engine that
        # ignores `quit` exit "cleanly". Now quit must make it exit by itself.
        os.environ["FAKE_MODE"] = "noquit"
        old_timeout = wa.SMOKE_TIMEOUT
        wa.SMOKE_TIMEOUT = 3  # the engine never exits on its own; keep the test short
        try:
            with self.assertRaises(wa.CheckError):
                wa.uci_session_bestmove(sys.executable, [self.script], "noquit")
        finally:
            wa.SMOKE_TIMEOUT = old_timeout

    def test_banner_before_any_command_is_captured(self):
        s = self.session("banner")
        try:
            code = s.finish()  # EOF straight away; finish must drain the banner
        finally:
            s.kill()
        self.assertEqual(code, 0)
        self.assertEqual(s.lines, ["usage: flawless <command>"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
