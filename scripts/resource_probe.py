#!/usr/bin/env python3
"""Interactive resource probe (Linux /proc): wall time, CPU time, and peak RSS of a
`go movetime N` search, for several hash sizes. Waits for every reply; never batches `go`+`quit`.
Usage: python3 scripts/resource_probe.py <exe> [movetime_ms] [hash_mb ...]
"""
import os, queue, subprocess, sys, threading, time

exe = sys.argv[1]
mt = int(sys.argv[2]) if len(sys.argv) > 2 else 3000
hashes = [int(x) for x in sys.argv[3:]] or [16, 64, 256]
CLK = os.sysconf("SC_CLK_TCK")

def proc_cpu_s(pid):
    f = open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()
    return (int(f[11]) + int(f[12])) / CLK  # utime + stime

def rss_kib(pid):
    for l in open(f"/proc/{pid}/status"):
        if l.startswith("VmRSS"):
            return int(l.split()[1])

def until_line(q, pred, timeout, what):
    end = time.monotonic() + timeout
    while True:
        r = end - time.monotonic()
        if r <= 0:
            raise RuntimeError(f"timeout waiting for {what}")
        try:
            l = q.get(timeout=min(r, 0.2))
        except queue.Empty:
            continue
        if l is None:
            raise RuntimeError(f"EOF waiting for {what}")
        if pred(l):
            return l

for h in hashes:
    p = subprocess.Popen([exe], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
    q = queue.Queue()
    def pump(stream=p.stdout, out=q):
        for raw in stream:
            out.put(raw.rstrip("\r\n"))
        out.put(None)  # EOF sentinel
    threading.Thread(target=pump, daemon=True).start()
    try:
        p.stdin.write(f"uci\nsetoption name Hash value {h}\nisready\nposition startpos\n"); p.stdin.flush()
        until_line(q, lambda l: l == "readyok", 10, "readyok")
        idle_rss = rss_kib(p.pid) or 0
        cpu0 = proc_cpu_s(p.pid)
        p.stdin.write(f"go movetime {mt}\n"); p.stdin.flush()
        t0 = time.monotonic()
        deadline = t0 + mt / 1000.0 + 10.0          # grace beyond the movetime
        peak = idle_rss                              # baseline counts as a sample
        depth = 0; nodes = 0; bestmove = None
        while bestmove is None:
            cur = rss_kib(p.pid)
            if cur is not None:
                peak = max(peak, cur)                # sampled on every iteration, not only on idle
            if time.monotonic() > deadline:
                raise RuntimeError(f"no bestmove within movetime + 10 s (hash={h})")
            try:
                l = q.get(timeout=0.02)
            except queue.Empty:
                continue
            if l is None:
                raise RuntimeError(f"EOF before bestmove (hash={h})")
            if l.startswith("info depth"):
                parts = l.split(); depth = int(parts[2])
                nodes = int(parts[parts.index("nodes") + 1]) if "nodes" in parts else nodes
            if l.startswith("bestmove"):
                bestmove = l
        wall = time.monotonic() - t0
        cpu = proc_cpu_s(p.pid) - cpu0
        p.stdin.write("quit\n"); p.stdin.flush()
        code = p.wait(timeout=10)
        if code != 0:
            raise RuntimeError(f"exit status {code} after quit (hash={h})")
        print(f"hash={h:4d} MB  movetime={mt} ms  wall={wall*1000:6.0f} ms ({wall*1000/mt*100:4.0f}%)  "
              f"cpu={cpu:5.2f} s ({cpu/wall*100:4.0f}% of one core)  idle_rss={idle_rss/1024:6.1f} MiB  "
              f"peak_rss={peak/1024:6.1f} MiB  depth={depth} nodes={nodes} exit={code}", flush=True)
    finally:
        if p.poll() is None:
            p.kill()
        p.wait(timeout=10)
        for f in (p.stdin, p.stdout):
            try:
                f.close()
            except Exception:
                pass
