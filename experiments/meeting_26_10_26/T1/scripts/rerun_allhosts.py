#!/usr/bin/env python3
"""Re-run T1 cells with ALL 32 ToR0 hosts traced (-log_reps_events_src 0..31), so the host that set the max FCT of each run can be analysed
(the original traces cover hosts 0-7; the slowest flow is a ToR0 host but is in 0-7 in only 7-30% of cells). Same flags and seeds as run_t1.py
(logging does not change the simulation: checked below by comparing the flow-finish lines with the stored stdout of the original cell).
Run in the container next to run_t1.py/run_m4.py:  python3 rerun_allhosts.py --out /t1out_allhosts [--workers 3] [--cells fail:B ...] [--check-dir DIR]"""
import argparse, json, re, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_t1 as r
r.m4.TRACE_SRCS = list(range(32))

def finish_lines(text):
    return [l for l in text.splitlines() if " finished at " in l and l.startswith("Flow")]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/t1out_allhosts"); ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--seeds", type=int, nargs="*", default=r.SEEDS); ap.add_argument("--cells", nargs="*"); ap.add_argument("--check-dir", default="/t1out/traces")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    grid = a.cells or [f"{f}:{b}" for f in ("nonuniform", "r010", "r005", "uniform50") for b in (1, 2, 4, 5, 6, 7, 8, 16, 128)]
    resf = out / "results.jsonl"
    done = {(d["fail"], d["B"], d["seed"]) for d in map(json.loads, resf.read_text().splitlines())} if resf.exists() else set()
    jobs = [(c.split(":")[0], int(c.split(":")[1]), s) for c in grid for s in a.seeds if (c.split(":")[0], int(c.split(":")[1]), s) not in done]
    print(f"{len(jobs)} cells to run", flush=True)
    def work(c):
        try: return c, r.run_cell(c, out), None
        except Exception as e: return c, None, str(e)
    with ThreadPoolExecutor(a.workers) as ex:
        for c, row, err in ex.map(work, jobs):
            if err: print("FAIL", c, err, flush=True); continue
            fail, B, seed = c
            new = (out / "traces" / f"matched_{fail}_B{B}_s{seed}.stdout.txt").read_text()
            old_p = Path(a.check_dir) / f"matched_{fail}_B{B}_s{seed}.stdout.txt"
            same = "no-original" if not old_p.exists() else ("identical" if sorted(finish_lines(old_p.read_text())) == sorted(finish_lines(new)) else "DIFFERENT")
            row["flow_lines_vs_original"] = same
            with open(resf, "a") as fh: fh.write(json.dumps(row) + "\n")
            print("ok", c, row["fct_max"], "rtos", row["rtos"], "frz", row["freeze_entries"], same, row["secs"], flush=True)
