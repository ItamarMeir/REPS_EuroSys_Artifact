#!/usr/bin/env python3
"""T2 runner with slack configs: T2's run_cell with extra configs derived from T2 `a_r005` / `b_r005` (rate_gbps lowered, degrade file unchanged).
Run in the container next to run_t2.py, run_m4.py, configs.json: python3 run_knee_t2.py --out /kneeout_t2 --cfgs a_r005_slack160 ... --seeds 42 43 44 45 46 --bs 2 3 4 5 6 8 12 128"""
import argparse, copy, json, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_t2 as r
for base in ("a_r005", "b_r005"):
    for R in (160, 140):
        c = copy.deepcopy(r.CFGS[base]); c["name"] = f"{base}_slack{R}"; c["rate_gbps"] = float(R); r.CFGS[c["name"]] = c
c = copy.deepcopy(r.CFGS["a_r005"]); c["name"] = "a_r005_rep"; c["tm"] = "connection_matrices/knee/msg_n128_k2_s16M_p900.cm"; r.CFGS[c["name"]] = c
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/kneeout_t2"); ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seeds", type=int, nargs="*", default=[42]); ap.add_argument("--cfgs", nargs="*", required=True)
    ap.add_argument("--bs", type=int, nargs="*", required=True)
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    resf = out / "results.jsonl"
    done = {(d["cfg"], d["B"], d["seed"]) for d in map(json.loads, resf.read_text().splitlines())} if resf.exists() else set()
    jobs = [(c, B, s) for s in a.seeds for c in a.cfgs for B in a.bs if (c, B, s) not in done]
    print(f"{len(jobs)} cells to run", flush=True)
    def work(c):
        try: return c, r.run_cell(c, out, "./htsim_uec"), None
        except Exception as e: return c, None, str(e)
    with ThreadPoolExecutor(a.workers) as ex:
        for c, row, err in ex.map(work, jobs):
            if err: print("FAIL", c, err, flush=True); continue
            with open(resf, "a") as fh: fh.write(json.dumps(row) + "\n")
            print("ok", c, row["fct_max"], row["pct_random"], "rtos", row["rtos"], "frz", row["freeze_entries"], row["secs"], flush=True)
