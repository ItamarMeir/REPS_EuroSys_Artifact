#!/usr/bin/env python3
"""Runner for knee configs: T3's run_cell with the config table swapped for configs_knee.json and each config's `extra` flags appended.
Run in the container next to run_t3.py/run_m4.py/configs_knee.json:
  python3 run_knee.py --out /kneeout --cfgs NAME... --seeds 42 43 44 --bs 2 4 8 --workers 6"""
import argparse, json, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_t3 as r

CFGS = {c["name"]: c for c in json.loads((HERE / "configs_knee.json").read_text())}
r.CFGS.clear(); r.CFGS.update(CFGS)
_flags = r.flags
r.flags = lambda cfg, B, seed: _flags(cfg, B, seed) + list(cfg.get("extra", []))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/kneeout"); ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seeds", type=int, nargs="*", default=[42]); ap.add_argument("--cfgs", nargs="*", default=list(CFGS))
    ap.add_argument("--bs", type=int, nargs="*", default=r.BS)
    ap.add_argument("--bsmap", default=None, help='JSON {cfg: [B, ...]} overriding --bs per cfg (N sweep: the B range scales with N)')
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    resf = out / "results.jsonl"
    done = {(d["cfg"], d["B"], d["seed"]) for d in map(json.loads, resf.read_text().splitlines())} if resf.exists() else set()
    bsmap = json.loads(Path(a.bsmap).read_text()) if a.bsmap else {}
    jobs = [(c, B, s) for s in a.seeds for c in a.cfgs for B in bsmap.get(c, a.bs) if (c, B, s) not in done]
    print(f"{len(jobs)} cells to run", flush=True)
    def work(c):
        try: return c, r.run_cell(c, out), None
        except Exception as e: return c, None, str(e)
    with ThreadPoolExecutor(a.workers) as ex:
        for c, row, err in ex.map(work, jobs):
            if err: print("FAIL", c, err, flush=True); continue
            with open(resf, "a") as fh: fh.write(json.dumps(row) + "\n")
            print("ok", c, row["fct_max"], row["pct_random"], "rtos", row["rtos"], "frz", row["freeze_entries"], row["secs"], flush=True)
