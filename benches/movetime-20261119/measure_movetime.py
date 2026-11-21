import subprocess,time,queue,threading
fens={"startpos":"rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1","kiwipete":"r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1","pos3":"8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1"}
def run(fen, cmd_go, wait=30):
    p=subprocess.Popen(["target/release/flawless"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,bufsize=1)
    try:
        q=queue.Queue(); threading.Thread(target=lambda:[q.put(l.rstrip()) for l in p.stdout],daemon=True).start()
        p.stdin.write(f"uci\nisready\nposition fen {fen}\n"); p.stdin.flush()
        got=[]
        while True:
            l=q.get(timeout=10); got.append(l)
            if l=="readyok": break
        t=time.monotonic(); p.stdin.write(cmd_go+"\n"); p.stdin.flush()
        lines=[]
        while True:
            l=q.get(timeout=wait); lines.append(l)
            if l.startswith("bestmove"): break
        dt=time.monotonic()-t
        p.stdin.write("quit\n"); p.stdin.flush(); p.wait(timeout=10)
        deps=[l for l in lines if l.startswith("info depth")]
        return dt, deps[-1][:60] if deps else "NO INFO", lines[-1]
    finally:
        # A failed or timed-out measurement must not leave an engine running.
        if p.poll() is None:
            p.kill(); p.wait()
        for f in (p.stdin, p.stdout):
            try: f.close()
            except Exception: pass
for name,fen in fens.items():
    for mt in [300,1000,3000]:
        dt,last,bm=run(fen,f"go movetime {mt}")
        print(f"{name:9s} movetime {mt:4d}: {dt*1000:6.0f} ms ({dt*1000/mt*100:3.0f}%) last-info=[{last}] {bm}")
