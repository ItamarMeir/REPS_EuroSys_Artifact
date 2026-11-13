#!/usr/bin/env python3
"""T3 sweep: where does the REPS buffer knee (B = 8) come from? Matched 200G constant-rate sender, ToR0 uplinks 5/95
(even agg 0.05, odd 0.95), REPS (freezing), one pass per cell. Flags and per-cell analysis are meeting_23_10_26/M4's
(run_m4.flags / run_m4.analyze); each config (data/configs/configs.json from make_configs.py) only overrides
-topo -tm -paths -rate_const_gbps -q -ecn -sack_threshold and adds -degrade_links_file, by key substitution on the M4 list.
Per cell: -log_reps_events (first min(8, H) hosts of ToR0) + -log_queue_stats, both gzip'd and kept in traces/.
Run inside the build container with run_m4.py and configs.json next to this file:
  python3 run_t3.py --out /t3out [--workers 6] [--seeds 42] [--cfgs name ...] [--bs 2 4 8 ...]
"""
import argparse, json, os, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_m4 as m4

ROW_CAP = 50_000_000
BS = [2, 4, 6, 8, 12, 16, 32, 128]
CFGS = {c["name"]: c for c in json.loads((HERE / "configs.json").read_text())}


def set_flag(f, key, *vals):
    i = f.index(key)
    f[i + 1:i + 1 + len(vals)] = [str(v) for v in vals]


def flags(cfg, B, seed):
    f = m4.flags("matched", "healthy", B, seed)          # M4 flag list; healthy = no degrade file, added below
    set_flag(f, "-tm", cfg["tm"]); set_flag(f, "-topo", cfg["topo"]); set_flag(f, "-paths", cfg["P"])
    set_flag(f, "-rate_const_gbps", int(cfg["rate_gbps"])); set_flag(f, "-q", cfg["q"]); set_flag(f, "-ecn", *cfg["ecn"])
    set_flag(f, "-sack_threshold", cfg["sack"])
    return f + ["-degrade_links_file", cfg["degrade"]]


def parse_queues(path, U):
    """ToR0 uplinks (layer E->A, i == 0): per agg j trims, data packets, max queue; fleet totals over all rows."""
    import pandas as pd
    q = pd.read_csv(path, sep="\t")
    up = q[(q.layer == "E->A") & (q.i == 0)].sort_values("j")
    return dict(uplink_trims=[int(v) for v in up.trims], uplink_data_pkts=[int(v) for v in up.data_pkts],
                uplink_max_q=[int(v) for v in up.max_q_bytes], uplink_rows=int(len(up)), trims_total=int(q.trims.sum()),
                drops_total=int(q.drops.sum()), uplink_expected=U)


def extras(cfg, trace, stdout, qpath):
    import numpy as np, pandas as pd
    H, P, U = cfg["H"], cfg["P"], cfg["U"]
    df = pd.read_csv(trace, usecols=["n", "src_id", "event", "ev", "frozen_mode"])
    fm = df.frozen_mode.astype(int)
    prev = fm.groupby(df.src_id).shift(1).fillna(0).astype(int)
    new = df[df.event == "SEND"]
    per_path = np.bincount((new.ev % P).astype(int), minlength=P)       # SRv6: EV -> _paths[ev % P]
    lines = stdout.splitlines()
    speeds = sorted({ln.split("linkspeed set to")[1].strip() for ln in lines if ln.startswith("Failure:") and "linkspeed set to" in ln}, key=float)
    dp = sorted({int(ln.split("distinct_paths=")[1].split()[0]) for ln in lines if "distinct_paths=" in ln})
    t0 = []
    for ln in lines:
        if ln.startswith("Flow") and " finished at " in ln:
            tk = ln.split()
            if int(tk[tk.index("srcaddr") + 1]) < H: t0.append(float(ln.split(" finished at ")[1].split()[0]))
    return dict(frozen_rows=int((fm > 0).sum()), n_freeze_events=int(((fm > 0) & (prev == 0)).sum()), trace_rows=int(len(df)),
                trace_capped=bool(len(df) >= ROW_CAP), failure_lines=sum(1 for ln in lines if ln.startswith("Failure:")),
                failure_speeds_mbps=speeds, distinct_paths=dp, tor_dl_ecn_on=("enable on tor downlink 1" in stdout),
                send_per_path=[int(v) for v in per_path], n_flow_lines=sum(1 for ln in lines if ln.startswith("Flow") and " finished at " in ln),
                fct_tor0_mean=float(np.mean(t0)), fct_tor0_max=float(max(t0)), **parse_queues(qpath, U))


def run_cell(cell, out):
    out = Path(out); name, B, seed = cell; cfg = CFGS[name]
    tr = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, dir="/tmp").name
    qs = tempfile.NamedTemporaryFile(suffix=".tsv", delete=False, dir="/tmp").name
    cmd = ["./htsim_uec"] + flags(cfg, B, seed) + ["-log_reps_events", tr, "-log_reps_events_max", str(ROW_CAP), "-log_queue_stats", qs]
    for s in range(min(8, cfg["H"])): cmd += ["-log_reps_events_src", str(s)]
    tq = None
    if os.environ.get("T3_TOR_QUEUES"):                    # existing -log_tor_queues sampler (1 us, all ToR uplinks); logging only
        tq = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, dir="/tmp").name; cmd += ["-log_tor_queues", tq]
        set_flag(cmd, "-end", 1500)                        # the sampler re-arms forever: stop after the flows (~700 us) so the file stays small
    t0 = time.time()
    p = subprocess.run(cmd, cwd=m4.DC, capture_output=True, text=True, timeout=7200)
    cname = f"{name}_B{B}_s{seed}"
    try:
        if p.returncode: raise RuntimeError(p.stderr[-300:])
        row = dict(cfg=name, axis=cfg["axis"], hosts=cfg["hosts"], tiers=cfg["tiers"], paths=cfg["P"], H=cfg["H"], U=cfg["U"],
                   latency_ns=cfg["latency_ns"], sack=cfg["sack"], rate_gbps=cfg["rate_gbps"], B=B, seed=seed,
                   **{k: v for k, v in m4.analyze(tr, p.stdout, B).items() if k not in ("fct_tor0_mean", "fct_tor0_max")},   # M4's assume H = 32
                   **extras(cfg, tr, p.stdout, qs), secs=round(time.time() - t0, 1))
    finally:
        td = out / "traces"; td.mkdir(parents=True, exist_ok=True)
        for src, suf in ((tr, ".csv"), (qs, ".queues.tsv")) + (((tq, ".torq.csv"),) if tq else ()):
            if os.path.exists(src):
                subprocess.run(["gzip", "-9", "-c", src], stdout=open(td / (cname + suf + ".gz"), "wb"), check=True)
                os.unlink(src)
        (td / f"{cname}.stdout.txt").write_text(p.stdout)
    return row


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/t3out"); ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seeds", type=int, nargs="*", default=[42]); ap.add_argument("--cfgs", nargs="*", default=list(CFGS))
    ap.add_argument("--bs", type=int, nargs="*", default=BS)
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    resf = out / "results.jsonl"
    done = {(d["cfg"], d["B"], d["seed"]) for d in map(json.loads, resf.read_text().splitlines())} if resf.exists() else set()
    jobs = [(c, B, s) for s in a.seeds for c in a.cfgs for B in a.bs if (c, B, s) not in done]
    print(f"{len(jobs)} cells to run", flush=True)
    def work(c):
        try: return c, run_cell(c, out), None
        except Exception as e: return c, None, str(e)
    with ThreadPoolExecutor(a.workers) as ex:
        for c, row, err in ex.map(work, jobs):
            if err: print("FAIL", c, err, flush=True); continue
            with open(resf, "a") as fh: fh.write(json.dumps(row) + "\n")
            print("ok", c, row["fct_max"], row["pct_random"], "rtos", row["rtos"], "frz", row["freeze_entries"], row["secs"], flush=True)
