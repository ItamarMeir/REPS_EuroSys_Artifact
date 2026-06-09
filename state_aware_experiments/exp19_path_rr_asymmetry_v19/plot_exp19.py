#!/usr/bin/env python3
"""Plot exp19: PATH_RR path-count asymmetry (host 0 constrained to 3 of 4 paths).

Reads:
  data/fcts.csv             (from aggregate_exp19.py)
  data/queue_integral.csv   (from aggregate_exp19.py)
  data/exp19_*_seed42_cwnd.csv   (cwnd traces for host 0)

Writes: plots/exp19_path_rr_asymmetry.png
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

ROOT  = Path(__file__).resolve().parent
DATA  = ROOT / "data"
PLOTS = ROOT / "plots"
PLOTS.mkdir(exist_ok=True)

BASE_RTT_US = 13.0
BIN_SIZE = 400 * 1024 * 1024  # 400 Gbps × 1 µs ÷ 8 / 4150 ≈ BDP; use flow size as ref
FLOW_SIZE = 268435456
MIN_FCT_US = FLOW_SIZE * 8 / (400e9) * 1e6  # unloaded FCT at 400 Gbps

COLORS = {"baseline": "#1565C0", "constrained": "#E65100"}
LABELS = {"baseline": "Baseline (4 paths)", "constrained": "Constrained (host 0: 3 paths)"}


def ci95(series):
    """95% CI half-width using t-distribution."""
    n = len(series)
    if n < 2:
        return 0.0
    return float(stats.t.ppf(0.975, df=n - 1) * series.std(ddof=1) / np.sqrt(n))


def slowdown(fct_us):
    return fct_us / MIN_FCT_US


def main():
    # ── load data ──────────────────────────────────────────────────────────────
    fcts_path = DATA / "fcts.csv"
    qi_path   = DATA / "queue_integral.csv"

    if not fcts_path.exists():
        print("ERROR: run aggregate_exp19.py first")
        return

    fcts = pd.read_csv(fcts_path)
    fcts["slowdown"] = slowdown(fcts["fct_us"])

    has_qi = qi_path.exists()
    qi = pd.read_csv(qi_path) if has_qi else None

    conditions = ["baseline", "constrained"]

    fig, axes = plt.subplots(2, 2, figsize=(16, 11))
    fig.suptitle(
        "exp19 — PATH_RR path asymmetry: host 0 constrained to 3 of 4 paths\n"
        "256 MiB tornado, PATH_RR src_mod, NSCC, cwnd=155, seeds 42/43/44",
        fontsize=10)

    # ── Panel A: per-flow avg FCT slowdown ────────────────────────────────────
    ax = axes[0, 0]
    ax.set_title("A — Per-flow avg FCT slowdown (lower = better)", fontsize=9)

    flow_ids = sorted(fcts["flow_id"].unique())
    x = np.arange(len(flow_ids))
    width = 0.35

    for i, cond in enumerate(conditions):
        sub = fcts[fcts["condition"] == cond]
        means, errs = [], []
        for fid in flow_ids:
            s = sub[sub["flow_id"] == fid]["slowdown"]
            means.append(s.mean())
            errs.append(ci95(s))
        offset = (i - 0.5) * width
        ax.bar(x + offset, means, width, yerr=errs, capsize=3,
               color=COLORS[cond], label=LABELS[cond], alpha=0.85)

    ax.set_xticks(x)
    ax.set_xticklabels([str(f) for f in flow_ids], fontsize=7)
    ax.set_xlabel("Flow ID (host index)")
    ax.set_ylabel("FCT slowdown (×)")
    ax.axvline(0 - 0.5, color="gray", linewidth=0.5, linestyle="--")  # pod boundary markers
    for pod_boundary in [3.5, 7.5, 11.5]:
        ax.axvline(pod_boundary, color="gray", linewidth=0.5, linestyle="--")
    ax.text(0, ax.get_ylim()[1] * 0.97, "pod0", fontsize=7, ha="left", va="top")
    ax.set_ylim(bottom=1.0)
    ax.legend(fontsize=8)

    # ── Panel B: aggregate avg / max FCT slowdown ─────────────────────────────
    ax = axes[0, 1]
    ax.set_title("B — Aggregate FCT slowdown (avg and max)", fontsize=9)

    metrics = {"avg": fcts.groupby(["condition", "seed"])["slowdown"].mean(),
               "max": fcts.groupby(["condition", "seed"])["slowdown"].max()}

    x2 = np.array([0, 1])
    width2 = 0.35
    for mi, (metric_name, series) in enumerate(metrics.items()):
        for ci, cond in enumerate(conditions):
            vals = series.xs(cond, level="condition")
            offset = (ci - 0.5) * width2 + mi * 1.5
            ax.bar(offset, vals.mean(), width2, yerr=ci95(vals), capsize=4,
                   color=COLORS[cond], alpha=0.85,
                   label=f"{metric_name} {LABELS[cond]}" if mi == 0 else "")
    ax.set_xticks([mi * 1.5 for mi in range(len(metrics))])
    ax.set_xticklabels(["Avg FCT slowdown", "Max FCT slowdown"], fontsize=9)
    ax.set_ylabel("FCT slowdown (×)")
    ax.set_ylim(bottom=1.0)
    ax.legend(fontsize=7, ncol=1)

    # ── Panel C: core queue integral ──────────────────────────────────────────
    ax = axes[1, 0]
    ax.set_title("C — Core queue integral (bytes·µs) per core switch", fontsize=9)

    if has_qi and qi is not None:
        core_ids = sorted(qi["core"].unique())
        qi_by_core = qi.groupby(["condition", "seed", "core"])["queue_byte_us"].sum()

        x3 = np.arange(len(core_ids))
        for ci, cond in enumerate(conditions):
            means, errs = [], []
            for core in core_ids:
                try:
                    vals = qi_by_core.xs((cond, slice(None), core),
                                        level=["condition", "seed", "core"])
                    # pandas multi-index xs with slice needs groupby instead
                    v = qi.query("condition == @cond and core == @core")\
                           .groupby("seed")["queue_byte_us"].sum()
                    means.append(v.mean())
                    errs.append(ci95(v))
                except Exception:
                    means.append(0)
                    errs.append(0)
            offset = (ci - 0.5) * 0.35
            ax.bar(x3 + offset, means, 0.35, yerr=errs, capsize=3,
                   color=COLORS[cond], label=LABELS[cond], alpha=0.85)

        ax.set_xticks(x3)
        ax.set_xticklabels([f"Core {c}" for c in core_ids])
        ax.set_ylabel("Σ queue integral (bytes·µs)")
        ax.legend(fontsize=8)
        ax.set_ylim(bottom=0)
    else:
        ax.text(0.5, 0.5, "queue_integral.csv not found\nRun aggregate_exp19.py",
                ha="center", va="center", transform=ax.transAxes)

    # ── Panel D: cwnd trace for host 0 ────────────────────────────────────────
    ax = axes[1, 1]
    ax.set_title("D — cwnd trace for host 0 (seed 42, overview)", fontsize=9)

    for cond in conditions:
        cwnd_path = DATA / f"exp19_{cond}_seed42_cwnd.csv"
        if not cwnd_path.exists():
            ax.text(0.5, 0.5, "cwnd CSVs not found\nRun scripts/01_run_exp19.sh",
                    ha="center", va="center", transform=ax.transAxes)
            break
        df = pd.read_csv(cwnd_path)[::10]  # stride 10 for speed
        # time column is nanoseconds (from eventlist().now()/1000 which gives ns)
        t_us = df["time_us"].to_numpy() / 1e3
        cwnd = df["cwnd_pkts"].to_numpy()
        # bin into 200 µs buckets
        t_lo, t_hi = t_us.min(), t_us.max()
        bins = np.arange(t_lo, t_hi + 200, 200)
        grp = pd.Series(cwnd, dtype=float).groupby(pd.cut(t_us, bins=bins))
        centers = np.array([iv.mid for iv in grp.mean().index])
        ax.plot(centers, grp.mean().to_numpy(), color=COLORS[cond],
                linewidth=1.2, label=LABELS[cond])

    ax.set_xlabel("Time (µs)  [200 µs bins]")
    ax.set_ylabel("cwnd (packets)")
    ax.legend(fontsize=8)
    ax.set_ylim(bottom=0)

    plt.tight_layout()
    out = PLOTS / "exp19_path_rr_asymmetry.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved {out}")

    # ── summary stats ─────────────────────────────────────────────────────────
    print("\n=== FCT slowdown summary ===")
    for cond in conditions:
        sub = fcts[fcts["condition"] == cond]
        avg_s = sub.groupby("seed")["slowdown"].mean()
        max_s = sub.groupby("seed")["slowdown"].max()
        print(f"  {cond:<14} avg={avg_s.mean():.4f}x (±{ci95(avg_s):.4f})"
              f"  max={max_s.mean():.4f}x (±{ci95(max_s):.4f})")

    print("\n=== Per-flow victim analysis (constrained vs baseline) ===")
    for fid in sorted(fcts["flow_id"].unique()):
        b = fcts[(fcts["condition"] == "baseline")    & (fcts["flow_id"] == fid)]["slowdown"]
        c = fcts[(fcts["condition"] == "constrained") & (fcts["flow_id"] == fid)]["slowdown"]
        if len(b) and len(c):
            delta = c.mean() - b.mean()
            marker = " <-- CONSTRAINED HOST" if fid == 0 else (" <-- VICTIM?" if delta > 0.001 else "")
            print(f"  flow {fid:2d}: baseline={b.mean():.4f}x  constrained={c.mean():.4f}x"
                  f"  Δ={delta:+.4f}{marker}")


if __name__ == "__main__":
    main()
