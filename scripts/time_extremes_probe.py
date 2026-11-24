# Probe for go movetime / movestogo / wtime extremes. Each case: send go, expect no bestmove within 1.5 s
# unless the limit is short, then send stop and measure the reply. Env: FLAWLESS_ENGINE. Needs only python3 (std lib).
import subprocess, threading, queue, time
import os
EXE = os.environ.get("FLAWLESS_ENGINE", "/home/user/FlawLessChess/target/release/flawless")
cases = [
 ("movetime 2^63-1", "go movetime 9223372036854775807"),
 ("movetime 2^64-1", "go movetime 18446744073709551615"),
 ("movetime 2^64 (overflow)", "go movetime 18446744073709551616"),
 ("movetime -1", "go movetime -1"),
 ("movestogo 2^64-1", "go wtime 1000 btime 1000 movestogo 18446744073709551615"),
 ("movestogo 0", "go wtime 1000 btime 1000 movestogo 0"),
 ("movestogo 2^63", "go wtime 3000 btime 3000 movestogo 9223372036854775808"),
 ("all fields 2^63-1 + movestogo 1", "go wtime 9223372036854775807 btime 9223372036854775807 winc 9223372036854775807 binc 9223372036854775807 movestogo 1"),
]
def run(name, go):
    p = subprocess.Popen([EXE], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    q = queue.Queue()
    def rd(): 
        for line in p.stdout: q.put((time.time(), line.rstrip("\n")))
        q.put((time.time(), None))
    threading.Thread(target=rd, daemon=True).start()
    errs=[]
    threading.Thread(target=lambda: errs.append(p.stderr.read()), daemon=True).start()
    def wait_for(prefix, timeout):
        end=time.time()+timeout; lines=[]
        while time.time()<end:
            try: t,l=q.get(timeout=0.1)
            except queue.Empty: continue
            if l is None: return None, lines
            lines.append(l)
            if l.startswith(prefix): return t, lines
        return None, lines
    p.stdin.write("uci\nisready\nposition startpos\n"); p.stdin.flush()
    wait_for("readyok", 10)
    t0=time.time(); p.stdin.write(go+"\n"); p.stdin.flush()
    early, _ = wait_for("bestmove", 1.5)
    result = "bestmove EARLY (time-limited finish within 1.5s)" if early else "no bestmove in 1.5s (search running)"
    if not early:
        t1=time.time(); p.stdin.write("stop\n"); p.stdin.flush()
        t, lines = wait_for("bestmove", 5)
        result += f"; after stop: {'bestmove '+ (lines[-1] if t else '') if t else 'NO BESTMOVE in 5s'} latency={(t-t1)*1000:.1f}ms" if t else "; after stop: NO BESTMOVE in 5s"
    p.stdin.write("quit\n"); p.stdin.flush()
    try: p.wait(timeout=5)
    except subprocess.TimeoutExpired: p.kill(); result+=" QUIT-HANG"
    time.sleep(0.05)
    print(f"{name}: rc={p.returncode} {result} stderr={(errs[0] if errs else '').strip()[:100]!r}", flush=True)
for n,g in cases: run(n,g)
