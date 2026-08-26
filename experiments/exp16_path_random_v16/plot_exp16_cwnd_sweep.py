#!/usr/bin/env python3
"""Plot PATH_STATIC+constant FCT slowdown vs cwnd (MTUs) to locate BDP.

Reads:  data/cwnd_sweep/cwnd<N>_tornado_n16_s67108864_seed<S>.out
Writes: plots/exp16_cwnd_sweep.png

BDP (optimal cwnd) is where FCT slowdown is minimised:
  cwnd < BDP  → sender under-utilises pipe, FCT ∝ 1/cwnd
  cwnd ≈ BDP  → FCT ≈ optimal (≈1.0×)
  cwnd >> BDP → standing queue, FCT rises slowly again
"""

import csv
import math
import re
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import scipy.stats

ROOT     = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "cwnd_sweep"
PLOTS    = ROOT / "plots"
PLOTS.mkdir(exist_ok=True)

LINK_RATE_BPS  = 400e9
NUM_HOPS       = 6
HOP_LATENCY_US = 0.5
MTU_BYTES      = 4150
PKT_SERIAL_US  = MTU_BYTES * 8 / LINK_RATE_BPS * 1e6
SIZE_BYTES     = 67108864

FLOW_RE = re.compile(
    r"^Flow\s+\S+\s+flowId\s+(\d+)\s+uecSrc\s+(\d+)\s+"
    r"finished at\s+([\d.]+)\s+flowSize\s+(\d+)"
)
FILE_RE = re.compile(r"^cwnd(\d+)_tornado_n16_s(\d+)_seed(\d+)\.out$")


def optimal_fct_us(flow_size_bytes):
    t_serial       = flow_size_bytes * 8 / LINK_RATE_BPS * 1e6
    data_traversal = NUM_HOPS * (HOP_LATENCY_US + PKT_SERIAL_US)
    ack_return     = NUM_HOPS * HOP_LATENCY_US
    return t_serial + data_traversal + ack_return


def ci95(vals):
    n = len(vals)
    if n < 2:
        return (vals[0] if n == 1 else float("nan")), 0.0
    m = sum(vals) / n
    s = math.sqrt(sum((v - m) ** 2 for v in vals) / (n - 1))
    t = scipy.stats.t.ppf(0.975, df=n - 1)
    return m, t * s / math.sqrt(n)


def parse_out(path):
    seen = set()
    flows = []
    with path.open(errors="ignore") as f:
        for line in f:
            m = FLOW_RE.match(line)
            if not m:
                continue
            flowid = int(m.group(1))
            src    = int(m.group(2))
            fct    = float(m.group(3))
            size   = int(m.group(4))
            if (flowid, src) in seen:
                continue
            seen.add((flowid, src))
            flows.append((fct, size))
    return flows


def load():
    # grouped[cwnd] = {"avg": [per_seed_avg_slowdown], "max": [...]}
    grouped = defaultdict(lambda: {"avg": [], "max": []})
    opt = optimal_fct_us(SIZE_BYTES)

    for f in sorted(DATA_DIR.glob("cwnd*_tornado_n16_s*_seed*.out")):
        m = FILE_RE.match(f.name)
        if not m:
            print(f"WARN skip: {f.name}")
            continue
        cwnd   = int(m.group(1))
        size   = int(m.group(2))
        if size != SIZE_BYTES:
            continue
        flows = parse_out(f)
        if not flows:
            print(f"WARN no flows: {f.name}")
            continue
        fcts = [fct for fct, _ in flows]
        grouped[cwnd]["avg"].append(sum(fcts) / len(fcts) / opt)
        grouped[cwnd]["max"].append(max(fcts) / opt)

    return grouped


def main():
    if not DATA_DIR.exists() or not any(DATA_DIR.glob("*.out")):
        print(f"ERROR: no data in {DATA_DIR} — run 06_run_exp16_cwnd_sweep.sh first")
        return

    grouped = load()
    cwnds = sorted(grouped.keys())

    avg_means, avg_errs = [], []
    max_means, max_errs = [], []
    for c in cwnds:
        am, ae = ci95(grouped[c]["avg"])
        mm, me = ci95(grouped[c]["max"])
        avg_means.append(am); avg_errs.append(ae)
        max_means.append(mm); max_errs.append(me)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.errorbar(cwnds, avg_means, yerr=avg_errs, fmt="o-", capsize=4,
                color="#1565C0", label="Avg-FCT slowdown")
    ax.errorbar(cwnds, max_means, yerr=max_errs, fmt="s--", capsize=4,
                color="#C62828", label="Max-FCT slowdown")
    ax.axhline(1.0, color="black", linewidth=1.0, linestyle=":", label="Optimal (1.0×)")

    # Mark the minimum
    min_idx = avg_means.index(min(avg_means))
    ax.axvline(cwnds[min_idx], color="#2E7D32", linewidth=1.2, linestyle="--",
               label=f"Min avg at cwnd={cwnds[min_idx]} MTUs")

    ax.set_xlabel("cwnd (MTUs = × 4150 bytes)")
    ax.set_ylabel("FCT / Optimal FCT")
    ax.set_title(
        "exp16 cwnd sweep: PATH_STATIC+constant, 64 MiB tornado, 4-ary fat-tree 3-tier 400 Gbps\n"
        "BDP ≈ 150 MTUs (12.5 µs RTT × 400 Gbps / 8 / 4150 bytes)\n"
        "Lower = better; minimum marks the optimal cwnd ≈ BDP",
        fontsize=9,
    )
    ax.legend(fontsize=8)
    ax.set_xticks(cwnds)
    ax.set_ylim(bottom=0.9)

    plt.tight_layout()
    out = PLOTS / "exp16_cwnd_sweep.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved {out}")

    print("\nSummary (mean ± 95% CI across seeds):")
    print(f"{'cwnd':>6}  {'Avg-slowdown':>14}  {'Max-slowdown':>14}")
    for c, am, ae, mm, me in zip(cwnds, avg_means, avg_errs, max_means, max_errs):
        marker = " ← min" if c == cwnds[min_idx] else ""
        print(f"{c:>6}  {am:>8.4f}±{ae:.4f}  {mm:>8.4f}±{me:.4f}{marker}")


if __name__ == "__main__":
    main()
