#!/usr/bin/env python3
"""Parse long-flow sweep results and print per-size tables."""
import re, os, glob, sys
import numpy as np

TAG = "baseline"
for i, a in enumerate(sys.argv[1:]):
    if a == "--tag" and i + 2 <= len(sys.argv) - 1:
        TAG = sys.argv[i + 2]

ROOT = f"results/long_flow/{TAG}"

EXPERIMENTS = ["reps_nscc", "reps_linerate",
               "klb_k4", "hklb_k4",
               "klb_k8", "hklb_k8"]

FCT_RE = re.compile(r"Flow .+ finished at (\S+) flowSize (\d+)")

def parse_fcts(path):
    fcts = []
    with open(path) as f:
        for line in f:
            m = FCT_RE.search(line)
            if m:
                fcts.append(float(m.group(1)))
    return fcts

def stat(vals):
    if not vals:
        return float("nan"), 0.0
    return float(np.mean(vals)), float(np.std(vals))

print(f"Tag: {TAG}")
sizes = sorted(glob.glob(f"{ROOT}/*"), key=lambda p: {"8MB":0, "32MB":1, "128MB":2}.get(os.path.basename(p), 99))
for size_dir in sizes:
    size = os.path.basename(size_dir)
    hdr = (f"\n=== {size} ===\n"
           f"{'Experiment':<16} {'Seeds':>5} {'Mean':>9} {'±':>5} "
           f"{'p50':>9} {'±':>5} {'p99':>9} {'±':>5} {'Max':>9} {'±':>5}")
    print(hdr)
    print("-" * (len(hdr) - 1))
    for label in EXPERIMENTS:
        base = f"{size_dir}/{label}"
        seed_dirs = sorted(glob.glob(f"{base}/seed*"))
        if not seed_dirs:
            print(f"{label:<16}  (no results)"); continue
        per_mean, per_p50, per_p99, per_max = [], [], [], []
        ok = 0
        for sd in seed_dirs:
            f = os.path.join(sd, "stdout.txt")
            if not os.path.exists(f): continue
            fcts = parse_fcts(f)
            if not fcts: continue
            ok += 1
            per_mean.append(np.mean(fcts))
            per_p50.append(np.percentile(fcts, 50))
            per_p99.append(np.percentile(fcts, 99))
            per_max.append(np.max(fcts))
        if not ok:
            print(f"{label:<16}  (no FCT data)"); continue
        m_m, s_m = stat(per_mean)
        m_5, s_5 = stat(per_p50)
        m_9, s_9 = stat(per_p99)
        m_x, s_x = stat(per_max)
        print(f"{label:<16} {ok:>5} {m_m:>9.1f} {s_m:>5.1f} "
              f"{m_5:>9.1f} {s_5:>5.1f} {m_9:>9.1f} {s_9:>5.1f} "
              f"{m_x:>9.1f} {s_x:>5.1f}")
