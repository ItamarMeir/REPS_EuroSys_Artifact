#!/usr/bin/env python3
"""T2 sweep: 3-tier k=8 fat tree (128 hosts, 16 paths), matched 200G constant-rate sender, REPS (freezing), pod0 degradation
(sub-experiment A: ToR->agg uplinks, B: agg->core uplinks; shapes from make_configs.py). Flags and per-cell analysis are
meeting_23_10_26/M4's (run_m4.flags / run_m4.analyze); each config only overrides -tm -topo -paths -rate_const_gbps -q -ecn and adds
-degrade_links_file, by key substitution on the M4 list. Per cell: -log_reps_events (the 16 pod0 hosts) + -log_queue_stats, both gzip'd
and kept in <out>/traces/. Run inside the build container with run_m4.py and configs.json next to this file:
  python3 run_t2.py --out /t2out [--binary ./htsim_uec] [--workers 6] [--seeds 42] [--cfgs name ...] [--bs 1 2 4 ...]
"""
import argparse, json, os, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_m4 as m4

ROW_CAP = 50_000_000
BS = [1, 2, 4, 8, 16, 32, 64, 128]
POD0_HOSTS = 16
CFGS = {c["name"]: c for c in json.loads((HERE / "configs.json").read_text())}


def set_flag(f, key, *vals):
    i = f.index(key)
    f[i + 1:i + 1 + len(vals)] = [str(v) for v in vals]


def flags(cfg, B, seed):
    f = m4.flags("matched", "healthy", B, seed)          # M4 flag list; healthy = no degrade file, added below
    set_flag(f, "-tm", cfg["tm"]); set_flag(f, "-topo", cfg["topo"]); set_flag(f, "-paths", cfg["P"])
    set_flag(f, "-rate_const_gbps", int(cfg["rate_gbps"])); set_flag(f, "-q", cfg["q"]); set_flag(f, "-ecn", *cfg["ecn"])
    set_flag(f, "-sack_threshold", cfg["sack"])
    return f + (["-degrade_links_file", cfg["degrade"]] if cfg["degrade"] else [])


def finish_lines(stdout):
    """(src, dst, fct_us, rtos, freeze_entries) per finished flow; flow name is Uec_<src>_<dst>."""
    out = []
    for ln in stdout.splitlines():
        if ln.startswith("Flow") and " finished at " in ln:
            tk = ln.split(); s, d = tk[1].split("_")[1:3]
            out.append((int(s), int(d), float(ln.split(" finished at ")[1].split()[0]), int(tk[tk.index("rtos") + 1]), int(tk[tk.index("freeze_entries") + 1])))
    return out


def queue_stats(path, cfg, sim_us):
    """Per-link rows for the degraded scope plus fleet totals. A (and the healthy reference): layer E->A of pod0 ToRs (i 0..3).
    B: layer A->C of pod0 aggs (i 0..3). Achieved Gbps = (data + header bytes) * 8 / sim time; the speed proof compares it with ratio * 400G."""
    import pandas as pd
    q = pd.read_csv(path, sep="\t")
    layer = "E->A" if cfg["sub"] in ("a", "ref") else "A->C"
    up = q[(q.layer == layer) & (q.i < 4)].sort_values(["i", "j"])
    return dict(scope_layer=layer, scope_rows=int(len(up)), scope_i=[int(v) for v in up.i], scope_j=[int(v) for v in up.j],
                scope_trims=[int(v) for v in up.trims], scope_data_pkts=[int(v) for v in up.data_pkts],
                scope_max_q=[int(v) for v in up.max_q_bytes],
                scope_gbps=[round(float(a + b) * 8 / (sim_us * 1e3), 3) for a, b in zip(up.data_bytes, up.hdr_bytes)],
                trims_total=int(q.trims.sum()), drops_total=int(q.drops.sum()),
                trims_outside_scope=int(q.trims.sum() - up.trims.sum()))


def extras(cfg, trace, stdout, qpath):
    import numpy as np, pandas as pd
    P = cfg["P"]
    df = pd.read_csv(trace, usecols=["n", "src_id", "event", "ev", "frozen_mode"])
    fm = df.frozen_mode.astype(int)
    prev = fm.groupby(df.src_id).shift(1).fillna(0).astype(int)
    new = df[df.event == "SEND"]
    per_path = np.bincount((new.ev % P).astype(int), minlength=P)       # SRv6: EV -> _paths[ev % P]
    lines = stdout.splitlines()
    speeds = sorted({ln.split("linkspeed set to")[1].strip() for ln in lines if ln.startswith("Failure:") and "linkspeed set to" in ln}, key=float)
    dp = sorted({int(ln.split("distinct_paths=")[1].split()[0]) for ln in lines if "distinct_paths=" in ln})
    fl = finish_lines(stdout)
    slow = max(fl, key=lambda x: x[2])
    sim_us = max(x[2] for x in fl)
    return dict(frozen_rows=int((fm > 0).sum()), n_freeze_events=int(((fm > 0) & (prev == 0)).sum()), trace_rows=int(len(df)),
                trace_capped=bool(len(df) >= ROW_CAP), failure_lines=sum(1 for ln in lines if ln.startswith("Failure:")),
                failure_speeds_gbps=speeds, distinct_paths=dp, tor_dl_ecn_on=("enable on tor downlink 1" in stdout),
                send_per_path=[int(v) for v in per_path], n_flow_lines=len(fl),
                fct_pod0_src_max=max(x[2] for x in fl if x[0] < POD0_HOSTS), fct_pod0_dst_max=max(x[2] for x in fl if x[1] < POD0_HOSTS),
                fct_other_max=max(x[2] for x in fl if x[0] >= POD0_HOSTS and x[1] >= POD0_HOSTS),
                slowest_src=slow[0], slowest_dst=slow[1], sim_us=sim_us, **queue_stats(qpath, cfg, sim_us))


def run_cell(cell, out, binary):
    out = Path(out); name, B, seed = cell; cfg = CFGS[name]
    tr = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, dir="/tmp").name
    qs = tempfile.NamedTemporaryFile(suffix=".tsv", delete=False, dir="/tmp").name
    cmd = [binary] + flags(cfg, B, seed) + ["-log_reps_events", tr, "-log_reps_events_max", str(ROW_CAP), "-log_queue_stats", qs]
    for s in range(POD0_HOSTS): cmd += ["-log_reps_events_src", str(s)]
    t0 = time.time()
    p = subprocess.run(cmd, cwd=m4.DC, capture_output=True, text=True, timeout=7200)
    cname = f"{name}_B{B}_s{seed}"
    try:
        if p.returncode: raise RuntimeError(p.stderr[-300:])
        row = dict(cfg=name, sub=cfg["sub"], shape=cfg["shape"], r=cfg["r"], H=cfg["H"], U=cfg["U"], paths=cfg["P"], rate_gbps=cfg["rate_gbps"], B=B, seed=seed,
                   n_links=cfg["n_links"], binary=binary,
                   **{k: v for k, v in m4.analyze(tr, p.stdout, B).items() if k not in ("fct_tor0_mean", "fct_tor0_max")},   # M4's ToR0 definition assumes H = 32
                   **extras(cfg, tr, p.stdout, qs), secs=round(time.time() - t0, 1))
    finally:
        td = out / "traces"; td.mkdir(parents=True, exist_ok=True)
        for src, suf in ((tr, ".csv"), (qs, ".queues.tsv")):
            if os.path.exists(src):
                subprocess.run(["gzip", "-9", "-c", src], stdout=open(td / (cname + suf + ".gz"), "wb"), check=True)
                os.unlink(src)
        (td / f"{cname}.stdout.txt").write_text(p.stdout)
    return row


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/t2out"); ap.add_argument("--workers", type=int, default=6); ap.add_argument("--binary", default="./htsim_uec")
    ap.add_argument("--seeds", type=int, nargs="*", default=[42]); ap.add_argument("--cfgs", nargs="*", default=list(CFGS))
    ap.add_argument("--bs", type=int, nargs="*", default=BS)
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    resf = out / "results.jsonl"
    done = {(d["cfg"], d["B"], d["seed"]) for d in map(json.loads, resf.read_text().splitlines())} if resf.exists() else set()
    jobs = [(c, B, s) for s in a.seeds for c in a.cfgs for B in a.bs if (c, B, s) not in done]
    print(f"{len(jobs)} cells to run", flush=True)
    def work(c):
        try: return c, run_cell(c, out, a.binary), None
        except Exception as e: return c, None, str(e)
    with ThreadPoolExecutor(a.workers) as ex:
        for c, row, err in ex.map(work, jobs):
            if err: print("FAIL", c, err, flush=True); continue
            with open(resf, "a") as fh: fh.write(json.dumps(row) + "\n")
            print("ok", c, row["fct_max"], row["pct_random"], "rtos", row["rtos"], "frz", row["freeze_entries"], row["secs"], flush=True)
