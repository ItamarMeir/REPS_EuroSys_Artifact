#!/usr/bin/env python3
"""M4 sweep: rate x failure x B x seed, constant-rate sender, no CC, REPS(freezing), trim on.
One pass per cell: simulate with -log_reps_events for ToR0 hosts 0..7, stream-analyze the trace,
append one JSON line to results.jsonl, delete the trace. Resumable (skips finished cells).
Run inside the build container:  python3 run_m4.py --out /out [--workers 6] [--seeds 42 43 ...] [--cells rate:fail:B ...]
"""
import argparse, json, os, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

DC = Path("/build/htsim_main/sim/datacenter")
RATES = {"under": 100, "matched": 200, "over": 400}          # Gbps; capacity of degraded ToR0 = 200G
FAILS = {"healthy": None, "uniform50": "/work/degrade_uniform50.txt", "nonuniform": "/work/degrade_nonuniform_25_75.txt"}
BS = [1, 2, 4, 8, 16, 32, 64]
SEEDS = [42, 43, 44, 45, 46]
TRACE_SRCS = list(range(8))

def flags(rate, fail, B, seed):
    f = ["-connections_mapping", "-sack_threshold", "4000", "-tm", "connection_matrices/tornado_n1024_s16777216.cm",
         "-end", "90000", "-seed", str(seed), "-sender_cc_only", "-sender_cc_algo", "constant",
         "-topo", "topologies/reps/fat_tree_1024_1os_2t_400g.topo", "-enable_qa_gate", "-linkspeed", "400000",
         "-ecn", "25", "76", "-q", "101", "-exit_freeze", "200000000", "-load_balancing_algo", "freezing",
         "-reps_buffer_size", str(B), "-use_srv6", "-paths", "32", "-disable_tor_ecn",
         "-rate_const_gbps", str(RATES[rate])]
    if FAILS[fail]:
        f += ["-degrade_links_file", FAILS[fail]]
    return f

def overwrite_stats(df, B):
    """Valid-EV overwrites. A clean (ecn=0) ACK calls CircularBufferREPS::add(), which writes at `head`; if that slot is
    still valid (prev_fresh >= B) a valid EV is lost. add_mismatch checks the reconstruction (fresh == min(prev+1, B)).
    ACKs after a source's last draw (flow tail: no more pops, buffer just fills) cannot hurt any send, so the headline
    metric (`ev_overwrites`, `pct_overwrite`) counts only clean ACKs before the source's last draw; `*_all` keeps the rest."""
    import numpy as np
    d = df[df.event.isin(["SEND", "RTX", "RTS"])]
    last = df.src_id.map(d.groupby("src_id").n.max())
    ack = df[(df.event == "ACK") & (df.ecn == 0)]
    over = ack.prev_fresh >= B
    pre = ack.n < last[ack.index]
    exp = np.minimum(ack.prev_fresh + 1, B)
    return dict(clean_acks=int(len(ack)), ev_overwrites_all=int(over.sum()),
                pct_overwrite_all=float(100 * over.mean()) if len(ack) else 0.0,
                clean_acks_pre=int(pre.sum()), ev_overwrites=int((over & pre).sum()),
                pct_overwrite=float(100 * (over & pre).sum() / max(int(pre.sum()), 1)),
                add_mismatch=int((ack.fresh != exp).sum()))

def analyze(trace, stdout, B):
    import numpy as np, pandas as pd
    fcts, rtos, frz, ecn, t0f = [], 0, 0, 0, []
    for ln in stdout.splitlines():
        if ln.startswith("Flow") and " finished at " in ln:
            t = ln.split(" finished at ")[1].split()
            fcts.append(float(t[0]))
            tk = ln.split()
            rtos += int(tk[tk.index("rtos") + 1]); frz += int(tk[tk.index("freeze_entries") + 1])
            ecn += int(tk[tk.index("ecn_acks") + 1])
            if int(tk[tk.index("srcaddr") + 1]) < 32: t0f.append(float(t[0]))   # ToR0 hosts
    r = dict(flows=len(fcts), fct_p50=float(np.percentile(fcts, 50)), fct_p99=float(np.percentile(fcts, 99)),
             fct_max=float(max(fcts)), fct_tor0_mean=float(np.mean(t0f)), fct_tor0_max=float(max(t0f)), rtos=rtos, freeze_entries=frz, ecn_acks=ecn)
    df = pd.read_csv(trace, usecols=["n", "src_id", "event", "ev", "ev_src", "fresh", "ecn"], dtype={"ev_src": str})
    # k = valid EVs in the buffer immediately BEFORE a draw = the previous row's post-event `fresh` of the same
    # source (a row's own `fresh` is already post-pop). Post-warmup = after the source's first ACK, same
    # definition as meeting_06_10_26/C1/scripts/send_occupancy.py. Draw events = SEND, RTX, RTS.
    g = df.groupby("src_id")
    df["prev_fresh"] = g.fresh.shift(1).fillna(0).astype(int)
    df["seen_ack"] = g.event.transform(lambda s: (s == "ACK").cummax())
    draws = df[df.event.isin(["SEND", "RTX", "RTS"])]
    post = draws[draws.seen_ack]
    k = post.prev_fresh.to_numpy()
    new = df[df.event == "SEND"]
    pop = post[post.ev_src == "fresh_pop"]; rnd = post[post.ev_src == "random"]
    mism = int((pop.fresh != pop.prev_fresh - 1).sum() + ((rnd.prev_fresh != 0) | (rnd.fresh != 0)).sum())
    kh = np.bincount(np.minimum(k, 32), minlength=33)
    r.update(sends=int(len(new)), rtx=int((draws.event == "RTX").sum()), draws_post=int(len(post)),
             draws_warmup=int(len(draws) - len(post)), n_random_post=int((post.ev_src == "random").sum()),
             n_fresh_pop_post=int(len(pop)), n_other_post=int(len(post) - len(pop) - len(rnd)), recon_mismatch=mism,
             pct_random=float(100 * (post.ev_src == "random").mean()),
             pct_random_incl_warmup=float(100 * (draws.ev_src == "random").mean()),
             k_mean=float(k.mean()), k_max=int(k.max()), k_hist=[int(v) for v in kh],
             **{f"k_ge{j}": float(100 * (k >= j).mean()) for j in (1, 2, 3, 4, 8)},
             distinct_ev_per_src=float(new.groupby("src_id").ev.nunique().mean()))
    # Valid-EV overwrites: a clean (ecn=0) ACK calls CircularBufferREPS::add(), which writes at `head`; if that slot is
    # still valid (buffer full, fresh == B, not frozen) a valid EV is lost. Detected from the previous row's post-event
    # fresh. add_mismatch checks the reconstruction: a clean ACK must leave fresh == min(prev_fresh + 1, B).
    r.update(overwrite_stats(df, B))
    r["ack_total"] = int((df.event == "ACK").sum())
    # spray width: distinct EVs in each consecutive window of 32 sends, averaged
    w = []
    for _, g in new.groupby("src_id"):
        e = g.ev.to_numpy(); n = len(e) // 32
        if n: w.append(np.mean([len(set(e[i * 32:(i + 1) * 32])) for i in range(n)]))
    r["spray_width32"] = float(np.mean(w))
    return r

def run_cell(cell, out):
    out = Path(out)
    rate, fail, B, seed = cell
    tr = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, dir="/tmp").name
    cmd = ["./htsim_uec"] + flags(rate, fail, B, seed) + ["-log_reps_events", tr, "-log_reps_events_max", "50000000"]
    for s in TRACE_SRCS: cmd += ["-log_reps_events_src", str(s)]
    t0 = time.time()
    p = subprocess.run(cmd, cwd=DC, capture_output=True, text=True, timeout=7200)
    try:
        if p.returncode: raise RuntimeError(p.stderr[-300:])
        row = dict(rate=rate, rate_gbps=RATES[rate], fail=fail, B=B, seed=seed, **analyze(tr, p.stdout, B), secs=round(time.time() - t0, 1))
    finally:
        # keep the trace (gzip -9), per the standing one-pass rule: never delete, needed for later on-demand analysis
        if os.path.exists(tr):
            td = out / "traces"; td.mkdir(parents=True, exist_ok=True)
            name = f"{rate}_{fail}_B{B}_s{seed}.csv"
            subprocess.run(["gzip", "-9", "-c", tr], stdout=open(td / (name + ".gz"), "wb"), check=True)
            (td / f"{rate}_{fail}_B{B}_s{seed}.stdout.txt").write_text(p.stdout)
            os.unlink(tr)
    return row

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/out"); ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seeds", type=int, nargs="*", default=SEEDS)
    ap.add_argument("--cells", nargs="*", help="rate:fail:B")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    resf = out / "results.jsonl"
    done = set()
    if resf.exists():
        for ln in resf.read_text().splitlines():
            d = json.loads(ln); done.add((d["rate"], d["fail"], d["B"], d["seed"]))
    if a.cells:
        base = [(c.split(":")[0], c.split(":")[1], int(c.split(":")[2])) for c in a.cells]
    else:
        base = [(r, f, B) for r in RATES for f in FAILS for B in BS]
    jobs = [(r, f, B, s) for s in a.seeds for (r, f, B) in base if (r, f, B, s) not in done]
    print(f"{len(jobs)} cells to run", flush=True)
    def work(c):
        try: return c, run_cell(c, out), None
        except Exception as e: return c, None, str(e)
    with ThreadPoolExecutor(a.workers) as ex:
        for c, row, err in ex.map(work, jobs):
            if err: print("FAIL", c, err, flush=True); continue
            with open(resf, "a") as fh: fh.write(json.dumps(row) + "\n")
            print("ok", c, row["fct_max"], row["pct_random"], row["secs"], flush=True)
