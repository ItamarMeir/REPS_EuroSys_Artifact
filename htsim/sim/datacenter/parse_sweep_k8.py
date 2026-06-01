#!/usr/bin/env python3
"""Parse results/sweep_k8 and print a summary table."""
import re, os, glob
import numpy as np

RESULTS_DIR = "results/sweep_k8"

EXPERIMENTS = [
    "reps_nscc", "reps_linerate",
    "klb_k4",   "hklb_k4",   "sklb_k4",
    "klb_k8",   "hklb_k8",   "sklb_k8",
    "klb_k16",  "hklb_k16",  "sklb_k16",
    "klb_k32",  "hklb_k32",  "sklb_k32",
    "klb_k64",  "hklb_k64",  "sklb_k64",
    "klb_k128", "hklb_k128", "sklb_k128",
]

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

hdr = (f"{'Experiment':<16} {'Seeds':>5} "
       f"{'Mean FCT':>10} {'±':>5} "
       f"{'p50':>8} {'±':>5} "
       f"{'p99':>8} {'±':>5} "
       f"{'Max':>8} {'±':>5}")
print(hdr)
print("-" * len(hdr))

for label in EXPERIMENTS:
    base      = f"{RESULTS_DIR}/{label}"
    seed_dirs = sorted(glob.glob(f"{base}/seed*"))
    if not seed_dirs:
        print(f"{label:<16}  (no results)")
        continue

    per_mean, per_p50, per_p99, per_max = [], [], [], []
    ok = 0
    for sd in seed_dirs:
        f = os.path.join(sd, "stdout.txt")
        if not os.path.exists(f):
            continue
        fcts = parse_fcts(f)
        if not fcts:
            continue
        ok += 1
        per_mean.append(np.mean(fcts))
        per_p50.append(np.percentile(fcts, 50))
        per_p99.append(np.percentile(fcts, 99))
        per_max.append(np.max(fcts))

    if not ok:
        print(f"{label:<16}  (no FCT data)")
        continue

    m_m, s_m = stat(per_mean)
    m_5, s_5 = stat(per_p50)
    m_9, s_9 = stat(per_p99)
    m_x, s_x = stat(per_max)

    print(f"{label:<16} {ok:>5} "
          f"{m_m:>10.1f} {s_m:>5.1f} "
          f"{m_5:>8.1f} {s_5:>5.1f} "
          f"{m_9:>8.1f} {s_9:>5.1f} "
          f"{m_x:>8.1f} {s_x:>5.1f}")
