#!/usr/bin/env python3
"""uci_probe.py — fixed-depth probe of the frozen engine on curated positions.

Drives a UCI engine binary over the trap-case positions (or any case JSON with
``fen``/``played_move`` fields) at each requested depth and records the best
move, score and PV. Used to root-cause search defects WITHOUT any hand-waving:
the engine is asked directly what it plays at a controlled depth, so
time-pressure artifacts are separated from genuine search blindness.

Usage:
  python3 benches/diagnostics/uci_probe.py ./target/release/flawless \
      benches/diagnostics/trap_cases.json --depths 8,10,12 --out /tmp/probe.json

Diagnostic only — never strength evidence.
"""
import argparse
import json
import sys
import time

import chess
import chess.engine


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("engine")
    ap.add_argument("cases_json")
    ap.add_argument("--depths", default="8,10,12")
    ap.add_argument("--time-per-probe", type=float, default=180.0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    depths = [int(x) for x in a.depths.split(",") if x.strip()]

    payload = json.load(open(a.cases_json))
    cases = payload["cases"] if isinstance(payload, dict) else payload

    cmd = a.engine if " " in a.engine else [a.engine]
    engine = chess.engine.SimpleEngine.popen_uci(cmd, debug=False)
    try:
        results = []
        for case in cases:
            board = chess.Board(case["fen"])
            entry = {"id": case.get("id"), "fen": case["fen"],
                     "played_move": case.get("played_move"),
                     "trap_reply": case.get("trap_reply"), "depths": {}}
            for d in depths:
                t0 = time.time()
                try:
                    with engine.analysis(board, chess.engine.Limit(
                            depth=d, time=a.time_per_probe)) as analysis:
                        info = {}
                        for upd in analysis:
                            info.update(upd)
                    move = info.get("pv", [None])[0] if info.get("pv") else None
                    score = info.get("score")
                    entry["depths"][str(d)] = {
                        "best_move": move.uci() if move else None,
                        "score_cp": score.white().score() if score else None,
                        "score_mate": score.white().mate() if score else None,
                        "reached_depth": info.get("depth"),
                        "nodes": info.get("nodes"),
                        "seconds": round(time.time() - t0, 1),
                        "pv": [m.uci() for m in (info.get("pv") or [])][:8],
                        "is_played_move": bool(move and case.get("played_move")
                                               and move.uci() == case["played_move"]),
                    }
                except Exception as exc:  # noqa: BLE001 — record and continue
                    entry["depths"][str(d)] = {"error": repr(exc)}
                print(f"{case.get('id')} depth {d}: "
                      f"{entry['depths'][str(d)].get('best_move')} "
                      f"score {entry['depths'][str(d)].get('score_cp')} "
                      f"(played={entry['depths'][str(d)].get('is_played_move')})",
                      flush=True)
            results.append(entry)
        json.dump({"engine": a.engine, "depths": depths, "results": results},
                  open(a.out, "w"), indent=1)
    finally:
        engine.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
