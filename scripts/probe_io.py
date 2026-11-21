"""Shared engine I/O for the probe scripts (audit finding F-37, CodeRabbit review on 2fe1118).

A reader thread feeds stdout lines into a queue, so every wait has a deadline. A blocking
`for line in p.stdout` never returns if the engine keeps stdout open and stops answering. `close()`
always sends `quit`, then kills and reaps the process, on success, timeout, and error paths.
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
        threading.Thread(target=self._pump, daemon=True).start()
        self._errthread = threading.Thread(target=lambda: self._err.append(self.p.stderr.read()), daemon=True)
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

    def close(self):
        """Quit the engine if it still runs, kill it after 10 s, and return its exit code."""
        try:
            if self.p.poll() is None:
                try:
                    self.send("quit")
                except (BrokenPipeError, OSError):
                    pass
                try:
                    self.p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.p.kill()
                    try:
                        self.p.wait(timeout=10)  # bounded reap after SIGKILL (F-43)
                    except subprocess.TimeoutExpired:
                        pass
        finally:
            if self.p.poll() is None:
                self.p.kill()
                try:
                    self.p.wait(timeout=10)  # bounded reap (F-43)
                except subprocess.TimeoutExpired:
                    pass
            self._errthread.join(timeout=5)  # stderr is complete once the process has exited
        return self.p.returncode


def search_lines(exe, commands, prefix="bestmove", timeout=60.0):
    """One fresh engine: send `commands` in order, return the lines up to the first line starting
    with `prefix`. A missing reply raises TimeoutError, and a nonzero exit status after the reply
    raises RuntimeError (F-43). The engine is always closed."""
    eng = Engine(exe)
    try:
        for c in commands:
            eng.send(c)
        lines = eng.read_until(prefix, timeout)
    except BaseException:
        eng.close()
        raise
    rc = eng.close()
    if rc != 0:
        raise RuntimeError(f"engine exited with status {rc} after '{prefix}'; stderr: {eng.stderr_text()[:200]}")
    return lines
