"""Shared engine I/O for the probe scripts (audit finding F-37, CodeRabbit review on 2fe1118).

A reader thread feeds stdout lines into a queue, so every wait has a deadline. A blocking
`for line in p.stdout` never returns if the engine keeps stdout open and stops answering. `close()`
sends `quit`, uses bounded terminate/kill escalation, reaps the child, closes its pipes, and verifies
that the reader threads finish. Incomplete cleanup is an error, never a successful probe result.
"""
import queue
import subprocess
import threading
import time


class Engine:
    def __init__(self, exe):
        self.p = subprocess.Popen(
            [exe], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )
        self.q = queue.Queue()
        self._err = []
        self._outthread = threading.Thread(target=self._pump, name="engine-stdout", daemon=True)
        self._errthread = threading.Thread(
            target=lambda: self._err.append(self.p.stderr.read()),
            name="engine-stderr", daemon=True,
        )
        self._closed = False
        self._cleanup_error = None
        self._outthread.start()
        self._errthread.start()

    def _pump(self):
        for line in self.p.stdout:
            self.q.put(line.rstrip("\n"))
        self.q.put(None)

    def send(self, line):
        self.p.stdin.write(line + "\n")
        self.p.stdin.flush()

    def read_until(self, prefix, timeout):
        """Lines up to and including the first line starting with `prefix`.

        Raises TimeoutError when no such line arrives within `timeout` seconds, and RuntimeError
        when stdout closes first."""
        lines = []
        end = time.monotonic() + timeout
        while True:
            left = end - time.monotonic()
            if left <= 0:
                raise TimeoutError(f"no '{prefix}' within {timeout:.0f} s; last lines: {lines[-3:]}")
            try:
                line = self.q.get(timeout=left)
            except queue.Empty:
                continue
            if line is None:
                raise RuntimeError(f"engine closed stdout before '{prefix}'")
            lines.append(line)
            if line.startswith(prefix):
                return lines

    def stderr_text(self):
        return self._err[0] if self._err else ""

    def _close_pipes_and_join_readers(self):
        errors = []
        threads = (self._outthread, self._errthread)
        if self.p.poll() is not None:
            # Let both readers consume EOF and trailing output before closing their pipes.
            for thread in threads:
                thread.join(timeout=5)
        for pipe in (self.p.stdin, self.p.stdout, self.p.stderr):
            try:
                pipe.close()
            except (OSError, ValueError):
                pass
        for thread in threads:
            if thread.is_alive():
                thread.join(timeout=5)
            if thread.is_alive():
                errors.append(f"{thread.name} reader did not finish within 5 seconds")
        return errors

    def close(self):
        """Quit, escalate with bounded waits, reap, close pipes, and return the exit code.

        Raises RuntimeError if the child cannot be reaped or either output reader remains stuck.
        It is safe to call more than once; the real exit code is retained.
        """
        if self._closed:
            if self._cleanup_error:
                raise RuntimeError("engine cleanup previously failed: " + self._cleanup_error)
            if self.p.returncode is None:
                raise RuntimeError("engine cleanup previously failed; process is still running")
            return self.p.returncode

        cleanup_errors = []
        if self.p.poll() is None:
            try:
                self.send("quit")
            except (BrokenPipeError, OSError, ValueError):
                pass
            try:
                self.p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    self.p.terminate()
                except OSError as exc:
                    cleanup_errors.append(f"terminate failed: {exc}")
                try:
                    self.p.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    try:
                        self.p.kill()
                    except OSError as exc:
                        cleanup_errors.append(f"kill failed: {exc}")
                    try:
                        self.p.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        cleanup_errors.append("engine did not exit after bounded SIGKILL reap")

        cleanup_errors.extend(self._close_pipes_and_join_readers())
        self._closed = True
        if self.p.poll() is None:
            cleanup_errors.append("engine is still running after cleanup")
        if cleanup_errors:
            self._cleanup_error = "; ".join(cleanup_errors)
            raise RuntimeError("incomplete engine cleanup: " + self._cleanup_error)
        return self.p.returncode


def search_lines(exe, commands, prefix="bestmove", timeout=60.0):
    """One fresh engine: send `commands` in order, return lines up to the first line starting
    with `prefix`. A missing reply raises TimeoutError, and a nonzero exit status after the reply
    raises RuntimeError (F-43). The engine is always closed."""
    eng = Engine(exe)
    try:
        for c in commands:
            eng.send(c)
        lines = eng.read_until(prefix, timeout)
    except BaseException as original:
        try:
            eng.close()
        except Exception as cleanup_error:
            raise RuntimeError(f"probe failed ({original!r}); cleanup also failed ({cleanup_error})") from original
        raise
    rc = eng.close()
    if rc != 0:
        raise RuntimeError(f"engine exited with status {rc} after '{prefix}'; stderr: {eng.stderr_text()[:200]}")
    return lines
