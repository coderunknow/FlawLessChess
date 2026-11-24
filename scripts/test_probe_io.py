#!/usr/bin/env python3
"""Failure-injection regressions for shared subprocess cleanup in probe_io.Engine."""
import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_io import Engine  # noqa: E402
import uci_extreme_args_probe  # noqa: E402


class FakeProcess:
    def __init__(self, returncode=None, never_exits=False):
        self.stdin = io.StringIO()
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        self.returncode = returncode
        self.never_exits = never_exits
        self.wait_timeouts = []
        self.terminated = False
        self.killed = False

    def poll(self):
        return None if self.never_exits else self.returncode

    def wait(self, timeout=None):
        self.wait_timeouts.append(timeout)
        if self.never_exits:
            raise __import__("subprocess").TimeoutExpired("fake-engine", timeout)
        return self.returncode

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


class FailingStdin:
    def __init__(self):
        self.closed = False

    def write(self, _text):
        raise OSError("injected write failure")

    def flush(self):
        return None

    def close(self):
        self.closed = True


class ExtremeProbeProcess:
    def __init__(self):
        self.stdin = FailingStdin()
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        self.returncode = None
        self.timeouts = []

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = -15

    def kill(self):
        self.returncode = -9

    def wait(self, timeout=None):
        self.timeouts.append(timeout)
        if self.returncode is None:
            raise __import__("subprocess").TimeoutExpired("fake-engine", timeout)
        return self.returncode


class ProbeIoCleanupTests(unittest.TestCase):
    def test_normal_exit_code_is_preserved_and_pipes_close(self):
        child = FakeProcess(returncode=17)
        with mock.patch("probe_io.subprocess.Popen", return_value=child):
            eng = Engine("fake-engine")
            self.assertEqual(eng.close(), 17)
            self.assertEqual(eng.close(), 17)
        self.assertTrue(child.stdin.closed)
        self.assertTrue(child.stdout.closed)
        self.assertTrue(child.stderr.closed)
        self.assertFalse(eng._outthread.is_alive())
        self.assertFalse(eng._errthread.is_alive())

    def test_extreme_probe_failure_still_terminates_reaps_and_closes(self):
        child = ExtremeProbeProcess()
        with mock.patch("uci_extreme_args_probe.subprocess.Popen", return_value=child):
            reply, _elapsed, rc, err, _out = uci_extreme_args_probe.run_session(
                ["go depth 2"], "bestmove", timeout=0.01,
            )
        self.assertEqual(reply, "ERROR")
        self.assertEqual(rc, -15)
        self.assertIn("injected write failure", err)
        self.assertEqual(child.timeouts, [2])
        self.assertTrue(child.stdin.closed)
        self.assertTrue(child.stdout.closed)
        self.assertTrue(child.stderr.closed)

    def test_unreaped_child_is_reported_after_bounded_escalation(self):
        child = FakeProcess(never_exits=True)
        with mock.patch("probe_io.subprocess.Popen", return_value=child):
            eng = Engine("fake-engine")
            with self.assertRaisesRegex(RuntimeError, "incomplete engine cleanup.*SIGKILL"):
                eng.close()
        self.assertTrue(child.terminated)
        self.assertTrue(child.killed)
        self.assertEqual(child.wait_timeouts, [10, 2, 2])
        self.assertTrue(all(timeout is not None for timeout in child.wait_timeouts))
        self.assertTrue(child.stdin.closed)
        self.assertTrue(child.stdout.closed)
        self.assertTrue(child.stderr.closed)
        self.assertFalse(eng._outthread.is_alive())
        self.assertFalse(eng._errthread.is_alive())
        with self.assertRaisesRegex(RuntimeError, "previously failed"):
            eng.close()


if __name__ == "__main__":
    unittest.main()
