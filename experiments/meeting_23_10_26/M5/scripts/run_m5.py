#!/usr/bin/env python3
"""M5: OPS (oblivious spraying, no memory) on the exact M4 network. One pass per cell, resumable.
The command line is DERIVED from M4's flags() so the network cannot drift; only the load balancer changes:
  -load_balancing_algo freezing -reps_buffer_size B   ->   -load_balancing_algo <lb>   (oblivious | path_random)
Each cell logs -log_reps_events (ToR0 hosts 0..7; fresh/slots are -1 for OPS), -log_queue_stats and keeps gzip'd traces.
Run inside container m23-dev:  python3 run_m5.py --out /out_m5 [--lb oblivious] [--workers 7] [--seeds 42 43 44] [--cells rate:fail ...]
Also usable for REPS reruns: --lb freezing --B 4 (keeps M4's flags untouched, adds queue stats).
"""
import argparse, json, os, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/work")
import run_m4 as m4

def flags(rate, fail, lb, B, seed):
    f = m4.flags(rate, fail, B if B else 8, seed)
    if lb != "freezing":
        i = f.index("-load_balancing_algo"); f[i + 1] = lb
        j = f.index("-reps_buffer_size"); del f[j:j + 2]
    elif B:
        pass
    return f

def stdout_checks(so, rate, fail, lb, B):
    """Assertions that the network is the M4 network. Returns list of failures."""
    bad = []
    if f"Load balancing algorithm set to  {lb}" not in so: bad.append("lb line")
    if "enable on tor downlink 1" in so: bad.append("tor downlink ECN on")
    if "rate_const" not in so and "rate-const" not in so: bad.append("no rate-const line")
    nf = sum(1 for l in so.splitlines() if l.startswith("Flow") and " finished at " in l)
    if nf != 1024: bad.append(f"{nf} flows finished")
    return bad

def analyze(trace, queues, stdout, rate, fail, lb, B):
    import numpy as np, pandas as pd
    fcts, rtos, frz, ecn, t0f, rnd, nlast = [], 0, 0, 0, [], 0, 0
    for ln in stdout.splitlines():
        if ln.startswith("Flow") and " finished at " in ln:
            t = ln.split(" finished at ")[1].split(); fcts.append(float(t[0])); tk = ln.split()
            rtos += int(tk[tk.index("rtos") + 1]); frz += int(tk[tk.index("freeze_entries") + 1]); ecn += int(tk[tk.index("ecn_acks") + 1])
            if int(tk[tk.index("srcaddr") + 1]) < 32: t0f.append(float(t[0]))
    r = dict(flows=len(fcts), fct_p50=float(np.percentile(fcts, 50)), fct_p99=float(np.percentile(fcts, 99)), fct_max=float(max(fcts)),
             fct_tor0_mean=float(np.mean(t0f)), fct_tor0_max=float(max(t0f)), rtos=rtos, freeze_entries=frz, ecn_acks=ecn)
    q = pd.read_csv(queues, sep="\t")
    r["trims_total"] = int(q.trims.sum()); r["drops_total"] = int(q.drops.sum())
    for lay in ("E->A", "A->E", "E->H"):          # 2-tier fabric: no core layers
        x = q[q.layer == lay]; r["maxq_" + lay] = int(x.max_q_total_bytes.max()); r["trims_" + lay] = int(x.trims.sum())
    # ToR0 uplinks (E->A, i == 0, one per agg j): per-uplink max queue and trims, so degrade classes can be split (even/odd agg)
    e = q[(q.layer == "E->A") & (q.i == 0)].sort_values("j")
    r["tor0_up_maxq"] = [int(v) for v in e.max_q_total_bytes]; r["tor0_up_trims"] = [int(v) for v in e.trims]
    df = pd.read_csv(trace, usecols=["n", "src_id", "event", "ev", "ev_src"], dtype={"ev_src": str})
    d = df[df.event.isin(["SEND", "RTX", "RTS"])]
    r.update(sends_traced=int((df.event == "SEND").sum()), rtx_traced=int((df.event == "RTX").sum()), rts_traced=int((df.event == "RTS").sum()))
    # spray uniformity: share of each EV (mod 32 = path) among SENDs of the traced hosts
    ev = df[df.event == "SEND"].ev.astype(int) % 32
    h = np.bincount(ev, minlength=32)
    r["path_hist"] = [int(v) for v in h]; r["path_cv"] = float(h.std() / h.mean())
    return r

def run_cell(cell, out, lb, B):
    out = Path(out); rate, fail, seed = cell
    tag = f"{lb}{('_B%d' % B) if (lb == 'freezing') else ''}_{rate}_{fail}_s{seed}"
    tr = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, dir="/tmp").name
    qf = tempfile.NamedTemporaryFile(suffix=".tsv", delete=False, dir="/tmp").name
    cmd = ["./htsim_uec"] + flags(rate, fail, lb, B, seed) + ["-log_reps_events", tr, "-log_reps_events_max", "50000000", "-log_queue_stats", qf]
    for s in m4.TRACE_SRCS: cmd += ["-log_reps_events_src", str(s)]
    t0 = time.time()
    p = subprocess.run(cmd, cwd=m4.DC, capture_output=True, text=True, timeout=7200)
    td = out / "traces"; td.mkdir(parents=True, exist_ok=True)
    try:
        if p.returncode: raise RuntimeError(p.stderr[-300:])
        bad = stdout_checks(p.stdout, rate, fail, lb, B)
        if bad: raise RuntimeError("assertions: " + ",".join(bad))
        row = dict(lb=lb, B=B if lb == "freezing" else None, rate=rate, rate_gbps=m4.RATES[rate], fail=fail, seed=seed,
                   **analyze(tr, qf, p.stdout, rate, fail, lb, B), secs=round(time.time() - t0, 1))
    finally:
        if os.path.exists(tr):
            subprocess.run(["gzip", "-9", "-c", tr], stdout=open(td / (tag + ".csv.gz"), "wb"), check=True); os.unlink(tr)
        (td / (tag + ".stdout.txt")).write_text(p.stdout)
        if os.path.exists(qf): os.replace(qf, td / (tag + ".queues.tsv"))
    return row

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/out_m5"); ap.add_argument("--workers", type=int, default=7)
    ap.add_argument("--seeds", type=int, nargs="*", default=[42, 43, 44]); ap.add_argument("--lb", default="oblivious")
    ap.add_argument("--B", type=int, default=0); ap.add_argument("--cells", nargs="*", help="rate:fail")
    ap.add_argument("--results", default="results.jsonl")
    a = ap.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True); resf = out / a.results
    done = set()
    if resf.exists():
        for ln in resf.read_text().splitlines():
            d = json.loads(ln); done.add((d["rate"], d["fail"], d["seed"]))
    base = [tuple(c.split(":")) for c in a.cells] if a.cells else [(r, f) for r in m4.RATES for f in m4.FAILS]
    jobs = [(r, f, s) for s in a.seeds for (r, f) in base if (r, f, s) not in done]
    print(len(jobs), "cells", flush=True)
    def work(c):
        try: return c, run_cell(c, out, a.lb, a.B), None
        except Exception as e: return c, None, str(e)
    with ThreadPoolExecutor(a.workers) as ex:
        for c, row, err in ex.map(work, jobs):
            if err: print("FAIL", c, err, flush=True); continue
            open(resf, "a").write(json.dumps(row) + "\n")
            print("ok", c, row["fct_max"], row["trims_total"], row["ecn_acks"], row["path_cv"], row["secs"], flush=True)
