#!/usr/bin/env python3
"""T1 sweep: extreme non-uniform ToR0 uplink degradation (even agg r, odd agg 1-r), matched 200G constant-rate sender,
REPS(freezing), B in 1..128, one pass per cell. Flags, per-cell analysis and trace handling are meeting_23_10_26/M4's
(run_m4.flags / run_m4.analyze); this file only adds the failure files, the Freezing-Mode gate fields, the per-path
spray share, -log_queue_stats (kept, gzip'd) and a trace row-cap assertion.
Run inside the build container with run_m4.py next to this file:
  python3 run_t1.py --out /out [--workers 6] [--seeds 42 43 44] [--cells fail:B ...]
"""
import argparse, json, os, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_m4 as m4

ROW_CAP = 50_000_000
FAILS = {"uniform50": "uniform50", "nonuniform": "r025", "r010": "r010", "r005": "r005", "r001": "r001"}  # name -> tag (r025 = M4 25/75 file)
for name in ("r010", "r005", "r001"):
    m4.FAILS[name] = f"/work/degrade_{name}.txt"
BS = [1, 2, 4, 8, 16, 32, 64, 128]
SEEDS = [42, 43, 44]
RATE = "matched"

def extras(trace, stdout):
    """Gate fields and spray share from the same trace/stdout as the stats."""
    import numpy as np, pandas as pd
    df = pd.read_csv(trace, usecols=["n", "src_id", "event", "ev", "frozen_mode"])
    fm = df.frozen_mode.astype(int)
    prev = fm.groupby(df.src_id).shift(1).fillna(0).astype(int)
    new = df[df.event == "SEND"]
    per_path = np.bincount((new.ev % 32).astype(int), minlength=32)       # SRv6: EV -> _paths[ev % 32]
    fail_lines = sum(1 for ln in stdout.splitlines() if ln.startswith("Failure:"))
    return dict(frozen_rows=int((fm > 0).sum()), n_freeze_events=int(((fm > 0) & (prev == 0)).sum()),
                trace_rows=int(len(df)), trace_capped=bool(len(df) >= ROW_CAP), failure_lines=fail_lines,
                tor_dl_ecn_on=("enable on tor downlink 1" in stdout), send_per_path=[int(v) for v in per_path],
                n_flow_lines=sum(1 for ln in stdout.splitlines() if ln.startswith("Flow") and " finished at " in ln))

def run_cell(cell, out):
    out = Path(out); fail, B, seed = cell
    tr = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, dir="/tmp").name
    qs = tempfile.NamedTemporaryFile(suffix=".tsv", delete=False, dir="/tmp").name
    cmd = ["./htsim_uec"] + m4.flags(RATE, fail, B, seed) + ["-log_reps_events", tr, "-log_reps_events_max", str(ROW_CAP),
                                                          "-log_queue_stats", qs]
    for s in m4.TRACE_SRCS: cmd += ["-log_reps_events_src", str(s)]
    t0 = time.time()
    p = subprocess.run(cmd, cwd=m4.DC, capture_output=True, text=True, timeout=7200)
    name = f"{RATE}_{fail}_B{B}_s{seed}"
    try:
        if p.returncode: raise RuntimeError(p.stderr[-300:])
        row = dict(rate=RATE, rate_gbps=m4.RATES[RATE], fail=fail, B=B, seed=seed, **m4.analyze(tr, p.stdout, B),
                   **extras(tr, p.stdout), secs=round(time.time() - t0, 1))
    finally:
        td = out / "traces"; td.mkdir(parents=True, exist_ok=True)
        for src, suf in ((tr, ".csv"), (qs, ".queues.tsv")):
            if os.path.exists(src):
                subprocess.run(["gzip", "-9", "-c", src], stdout=open(td / (name + suf + ".gz"), "wb"), check=True)
                os.unlink(src)
        (td / f"{name}.stdout.txt").write_text(p.stdout)
    return row

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/out"); ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seeds", type=int, nargs="*", default=SEEDS)
    ap.add_argument("--cells", nargs="*", help="fail:B")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    resf = out / "results.jsonl"
    done = {(d["fail"], d["B"], d["seed"]) for d in map(json.loads, resf.read_text().splitlines())} if resf.exists() else set()
    base = [(c.split(":")[0], int(c.split(":")[1])) for c in a.cells] if a.cells else [(f, B) for f in ("r010", "r005", "r001") for B in BS]
    jobs = [(f, B, s) for s in a.seeds for (f, B) in base if (f, B, s) not in done]
    print(f"{len(jobs)} cells to run", flush=True)
    def work(c):
        try: return c, run_cell(c, out), None
        except Exception as e: return c, None, str(e)
    with ThreadPoolExecutor(a.workers) as ex:
        for c, row, err in ex.map(work, jobs):
            if err: print("FAIL", c, err, flush=True); continue
            with open(resf, "a") as fh: fh.write(json.dumps(row) + "\n")
            print("ok", c, row["fct_max"], row["pct_random"], "rtos", row["rtos"], "frz", row["freeze_entries"], row["secs"], flush=True)
