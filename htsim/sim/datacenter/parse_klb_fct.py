#!/usr/bin/env python3
"""
Parse K-LB evaluation results. Aggregates FCT across all seeds per experiment
and reports mean +/- std for mean/p50/p99/max FCT.

Also computes convergence time when ECN_TIMESERIES lines are present in stdout
(written by `-log_ecn_timeseries`). Convergence is defined per-tier as the last
100us bin in which the ECN mark rate exceeded 5% of the peak rate observed in
that tier over the run. A lower convergence time means the algorithm reached
steady state faster.

Note on K=N vs REPS: K=N KLB is NOT a REPS reproduction. REPS pops each EV from
its `_next_pathid` queue when used (uec.cpp:2333) and re-enqueues on PATH_GOOD
ACK; the set of in-use EVs naturally cycles. KLB/SKLB/HKLB keep their K active
EVs persistent and only replace on PATH_ECN. So K=N KLB reuses the same N EVs
deterministically, whereas REPS effectively re-draws an EV per ACK cycle.

Usage:
  python3 parse_klb_fct.py                          # k=6 results (results/klb)
  python3 parse_klb_fct.py --dir results/klb_k8     # k=8 results
  python3 parse_klb_fct.py --ecn-sweep              # ECN-threshold sweep results
"""
import re, os, glob, sys
import numpy as np

ECN_SWEEP = "--ecn-sweep" in sys.argv
results_dir = "results/klb"
ecn_sweep_dir = "results/ecn_sweep"
ecn_filter = None  # if set, only display these ECN values in --ecn-sweep mode
for i, arg in enumerate(sys.argv[1:]):
    if arg == "--dir" and i + 2 <= len(sys.argv) - 1:
        results_dir = sys.argv[i + 2]
        ecn_sweep_dir = sys.argv[i + 2]
    if arg == "--ecn-only" and i + 2 <= len(sys.argv) - 1:
        ecn_filter = set(int(x) for x in sys.argv[i + 2].split(","))

EXPERIMENTS = [
    "reps_nscc", "reps_linerate",
    "klb_k1", "klb_k2", "klb_k4", "klb_k8", "klb_k16", "klb_k32",
    "sklb_k2", "sklb_k4", "sklb_k8",
    "hklb_k2", "hklb_k4", "hklb_k8",
    "hklb_se_k4", "hklb_se_k8",
]
def discover_ecn_sweep_experiments(base):
    """Return ordered list of experiment labels found under base/<ecn_dir>/<label>/.

    Auto-detected so the parser works for any K-set without code changes.
    Order: baselines first, then klb/hklb/sklb by ascending K.
    """
    if not os.path.isdir(base):
        return []
    labels = set()
    for ecn_dir in os.listdir(base):
        full = os.path.join(base, ecn_dir)
        if not os.path.isdir(full):
            continue
        for lbl in os.listdir(full):
            if os.path.isdir(os.path.join(full, lbl)):
                labels.add(lbl)
    def sort_key(l):
        prio = {"reps_nscc": 0, "reps_linerate": 1}
        if l in prio:
            return (prio[l], 0)
        for fam, idx in [("klb_", 2), ("hklb_", 3), ("sklb_", 4)]:
            if l.startswith(fam):
                try:
                    k = int(l.split("_k")[1])
                except (IndexError, ValueError):
                    k = 0
                return (idx, k)
        return (99, 0)
    return sorted(labels, key=sort_key)

FCT_RE = re.compile(r"Flow .+ finished at (\S+) flowSize (\d+)")
ECN_BIN_RE = re.compile(
    r"ECN_BIN t_us=(\d+) "
    r"tor_m=(\d+) tor_p=(\d+) "
    r"agg_m=(\d+) agg_p=(\d+) "
    r"core_m=(\d+) core_p=(\d+)"
)

def parse_fcts(path):
    fcts = []
    with open(path) as f:
        for line in f:
            m = FCT_RE.search(line)
            if m:
                fcts.append(float(m.group(1)))
    return fcts

def parse_ecn_timeseries(path):
    """Return list of (t_us, tor_rate, agg_rate, core_rate) in 100us bins."""
    bins = []
    with open(path) as f:
        for line in f:
            m = ECN_BIN_RE.search(line)
            if not m:
                continue
            t_us = int(m.group(1))
            tm, tp = int(m.group(2)), int(m.group(3))
            am, ap = int(m.group(4)), int(m.group(5))
            cm, cp = int(m.group(6)), int(m.group(7))
            tor_rate  = tm / tp if tp else 0.0
            agg_rate  = am / ap if ap else 0.0
            core_rate = cm / cp if cp else 0.0
            bins.append((t_us, tor_rate, agg_rate, core_rate))
    return bins

def convergence_us(bins, idx, frac=0.05):
    """Last bin t where tier `idx` (1=tor,2=agg,3=core) ECN rate > frac*peak.

    Returns None if peak rate is 0 (already converged or no congestion).
    """
    if not bins:
        return None
    rates = [b[idx] for b in bins]
    peak = max(rates)
    if peak == 0.0:
        return None
    thresh = max(frac * peak, 0.001)
    last_t = bins[0][0]
    for b in bins:
        if b[idx] > thresh:
            last_t = b[0]
    return last_t

def steady_state_rate(bins, idx, start_frac=0.2, end_frac=0.8):
    """Median ECN rate in the middle portion of the run (excludes ramp-up and tail).

    Returns the median rate during bins [start_frac*N, end_frac*N). When ECN
    never drops to zero, this is more meaningful than convergence_us.
    """
    if not bins:
        return None
    n = len(bins)
    if n < 3:
        return float(np.median([b[idx] for b in bins])) if n else None
    lo, hi = int(n * start_frac), int(n * end_frac)
    if lo >= hi:
        lo, hi = 0, n
    return float(np.median([bins[i][idx] for i in range(lo, hi)]))

def stat(vals):
    if not vals:
        return float("nan"), 0.0
    return np.mean(vals), np.std(vals)

def report(label, seed_dirs):
    per_seed_mean, per_seed_p50, per_seed_p99, per_seed_max = [], [], [], []
    ss_tor, ss_agg, ss_core = [], [], []  # steady-state ECN rates (median of middle 60%)
    conv_core = []                          # core convergence time (last bin > 5% peak)
    seeds_ok = 0
    for sd in seed_dirs:
        stdout = os.path.join(sd, "stdout.txt")
        if not os.path.exists(stdout):
            continue
        fcts = parse_fcts(stdout)
        if not fcts:
            continue
        seeds_ok += 1
        per_seed_mean.append(np.mean(fcts))
        per_seed_p50.append(np.percentile(fcts, 50))
        per_seed_p99.append(np.percentile(fcts, 99))
        per_seed_max.append(np.max(fcts))
        bins = parse_ecn_timeseries(stdout)
        if bins:
            for tier_idx, store in [(1, ss_tor), (2, ss_agg), (3, ss_core)]:
                r = steady_state_rate(bins, tier_idx)
                if r is not None:
                    store.append(r)
            c = convergence_us(bins, 3)
            if c is not None:
                conv_core.append(c)
    if not seeds_ok:
        return None
    m_mean, s_mean = stat(per_seed_mean)
    m_p50,  s_p50  = stat(per_seed_p50)
    m_p99,  s_p99  = stat(per_seed_p99)
    m_max,  s_max  = stat(per_seed_max)
    m_tor,  _      = stat(ss_tor)
    m_agg,  _      = stat(ss_agg)
    m_cor,  _      = stat(ss_core)
    m_conv, _      = stat(conv_core)
    return (seeds_ok, m_mean, s_mean, m_p50, s_p50, m_p99, s_p99, m_max, s_max,
            m_tor, m_agg, m_cor, m_conv)

if ECN_SWEEP:
    print("ECN-threshold sweep results (binary Kmin=Kmax)")
    print("Steady-state ECN rate = median ECN mark rate during bins [20%, 80%] of run.")
    print("Conv = last 100us bin where core ECN rate > 5% of peak (effectively end of active load).")
    print("ECN_tor reflects ToR uplink (ToR downlink ECN is disabled).")
    print()
    base = ecn_sweep_dir
    if not os.path.isdir(base):
        print(f"No directory: {base}")
        sys.exit(1)
    ecn_dirs = sorted([d for d in os.listdir(base) if d.startswith("ecn")],
                      key=lambda x: int(x.replace("ecn", "")))
    if ecn_filter is not None:
        ecn_dirs = [d for d in ecn_dirs if int(d.replace("ecn", "")) in ecn_filter]
    experiments_list = discover_ecn_sweep_experiments(base)
    hdr = (f"{'ECN':>4} {'Experiment':<14} {'Seeds':>5} "
           f"{'Mean':>8} {'±':>4} "
           f"{'p99':>8} {'±':>4} "
           f"{'SS_tor':>7} {'SS_agg':>7} {'SS_core':>8} "
           f"{'Conv_us':>9}")
    print(hdr)
    print("-" * len(hdr))
    for ecn_dir in ecn_dirs:
        ecn_k = ecn_dir.replace("ecn", "")
        for label in experiments_list:
            full = f"{base}/{ecn_dir}/{label}"
            seeds = sorted(glob.glob(f"{full}/seed*"))
            if not seeds:
                continue
            r = report(label, seeds)
            if r is None:
                continue
            (n, mm, sm, p50, sp50, p99, sp99, mx, smx,
             ss_t, ss_a, ss_c, conv_us) = r
            def fmt(v, w, d):
                return f"{v:>{w}.{d}f}" if not (isinstance(v, float) and np.isnan(v)) else f"{'n/a':>{w}}"
            print(f"{ecn_k:>4} {label:<14} {n:>5} "
                  f"{mm:>8.1f} {sm:>4.1f} "
                  f"{p99:>8.1f} {sp99:>4.1f} "
                  f"{fmt(ss_t,7,3)} {fmt(ss_a,7,3)} {fmt(ss_c,8,3)} "
                  f"{fmt(conv_us,9,0)}")
        print()
    sys.exit(0)

print(f"Results directory: {results_dir}")
hdr = (f"{'Experiment':<20} {'Seeds':>5} "
       f"{'Mean FCT':>11} {'±':>4} "
       f"{'p50':>9} {'±':>4} "
       f"{'p99':>9} {'±':>4} "
       f"{'Max':>9} {'±':>4}")
print(hdr)
print("-" * len(hdr))

for label in EXPERIMENTS:
    base = f"{results_dir}/{label}"
    seed_dirs = sorted(glob.glob(f"{base}/seed*"))
    if not seed_dirs:
        old = f"{base}/stdout.txt"
        if os.path.exists(old):
            seed_dirs = [base]
        else:
            print(f"{label:<20}  (no results)")
            continue
    r = report(label, seed_dirs)
    if r is None:
        print(f"{label:<20}  (no FCT data)")
        continue
    (n, mm, sm, p50, sp50, p99, sp99, mx, smx, ss_t, ss_a, ss_c, conv_us) = r
    print(f"{label:<20} {n:>5} "
          f"{mm:>11.1f} {sm:>4.1f} "
          f"{p50:>9.1f} {sp50:>4.1f} "
          f"{p99:>9.1f} {sp99:>4.1f} "
          f"{mx:>9.1f} {smx:>4.1f}")
