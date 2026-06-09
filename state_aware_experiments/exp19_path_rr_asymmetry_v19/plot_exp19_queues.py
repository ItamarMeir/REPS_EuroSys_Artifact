#!/usr/bin/env python3
"""Plot exp19 queue panels.

Panel A — agg→core queue integral per core switch (baseline vs constrained)
Panel B — ToR→agg queue integral per (ToR, agg) link (baseline vs constrained)

Reads:
  data/queue_integral.csv       (agg→core)
  data/tor_queue_integral.csv   (ToR→agg)

Writes: plots/exp19_queues.png
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

COLORS = {"baseline": "#1565C0", "constrained": "#E65100"}
LABELS = {"baseline": "Baseline (4 paths)", "constrained": "Constrained (host 0: 3 paths)"}
CONDITIONS = ["baseline", "constrained"]


def ci95(s):
    n = len(s)
    if n < 2:
        return 0.0
    return float(stats.t.ppf(0.975, df=n - 1) * s.std(ddof=1) / np.sqrt(n))


def bar_group(ax, ids, get_vals, xlabel, ylabel, title, label_fn):
    x = np.arange(len(ids))
    width = 0.35
    for ci, cond in enumerate(CONDITIONS):
        means, errs = [], []
        for idx in ids:
            vals = get_vals(cond, idx)
            means.append(vals.mean())
            errs.append(ci95(vals))
        offset = (ci - 0.5) * width
        ax.bar(x + offset, means, width, yerr=errs, capsize=3,
               color=COLORS[cond], label=LABELS[cond], alpha=0.85)
    ax.set_xticks(x)
    ax.set_xticklabels([label_fn(i) for i in ids], fontsize=8)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=9)
    ax.set_ylim(bottom=0)
    ax.legend(fontsize=8)


def main():
    qi_path  = DATA / "queue_integral.csv"
    tqi_path = DATA / "tor_queue_integral.csv"

    if not qi_path.exists() or not tqi_path.exists():
        print("ERROR: run aggregate_exp19.py first")
        return

    qi  = pd.read_csv(qi_path)
    tqi = pd.read_csv(tqi_path)

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(16, 5))
    fig.suptitle(
        "exp19 — PATH_RR path asymmetry: queue integrals (bytes·µs)\n"
        "256 MiB tornado, PATH_RR src_mod, NSCC, cwnd=155, seeds 42–51 (n=10)",
        fontsize=10)

    # ── Panel A: agg→core queue integral per core switch ──────────────────────
    # Sum over all agg switches to get total load on each core switch.
    core_ids = sorted(qi["core"].unique())

    def get_core_vals(cond, core):
        return qi.query("condition == @cond and core == @core")\
                 .groupby("seed")["queue_byte_us"].sum()

    bar_group(ax_a, core_ids, get_core_vals,
              xlabel="Core switch index",
              ylabel="Σ queue integral (bytes·µs)",
              title="A — Agg→Core queue integral per core (summed over all agg switches)",
              label_fn=lambda c: f"Core {c}")

    # Annotate: mark which cores host 0 avoids
    ax_a.text(0.98, 0.97,
              "Host 0 skips the last-indexed core\n(full_paths truncated at 3)",
              transform=ax_a.transAxes, fontsize=7, ha="right", va="top",
              bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow", alpha=0.8))

    # ── Panel B: ToR→agg queue integral ───────────────────────────────────────
    # Each (tor, agg) pair is one uplink. Label as "T{tor}→A{agg}".
    # Highlight ToR 0 (the one shared by hosts 0 and 1).
    tor_agg_pairs = sorted(tqi[["tor", "agg"]].drop_duplicates().itertuples(index=False))

    def get_tor_vals(cond, pair):
        tor, agg = pair
        return tqi.query("condition == @cond and tor == @tor and agg == @agg")\
                  .groupby("seed")["queue_byte_us"].sum()

    x = np.arange(len(tor_agg_pairs))
    width = 0.35
    for ci, cond in enumerate(CONDITIONS):
        means, errs = [], []
        for pair in tor_agg_pairs:
            vals = get_tor_vals(cond, pair)
            means.append(vals.mean())
            errs.append(ci95(vals))
        offset = (ci - 0.5) * width
        ax_b.bar(x + offset, means, width, yerr=errs, capsize=3,
                 color=COLORS[cond], label=LABELS[cond], alpha=0.85)

    ax_b.set_xticks(x)
    ax_b.set_xticklabels([f"T{p.tor}→A{p.agg}" for p in tor_agg_pairs],
                         fontsize=7, rotation=45, ha="right")
    ax_b.set_xlabel("ToR→Agg uplink")
    ax_b.set_ylabel("Σ queue integral (bytes·µs)")
    ax_b.set_title("B — ToR→Agg queue integral per uplink\n"
                   "(ToR 0 = hosts 0 & 1; ToR 1 = hosts 2 & 3)", fontsize=9)
    ax_b.set_ylim(bottom=0)
    ax_b.legend(fontsize=8)

    # Shade ToR 0 uplinks
    tor0_xs = [i for i, p in enumerate(tor_agg_pairs) if p.tor == 0]
    if tor0_xs:
        ax_b.axvspan(min(tor0_xs) - 0.5, max(tor0_xs) + 0.5,
                     alpha=0.08, color="red", label="ToR 0 (hosts 0 & 1)")
        ax_b.legend(fontsize=7)

    plt.tight_layout()
    out = PLOTS / "exp19_queues.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved {out}")

    # ── summary ───────────────────────────────────────────────────────────────
    print("\n=== Agg→Core queue integral (mean across seeds, bytes·µs) ===")
    for core in core_ids:
        b = get_core_vals("baseline",    core)
        c = get_core_vals("constrained", core)
        print(f"  Core {core}: baseline={b.mean():.0f}  constrained={c.mean():.0f}"
              f"  Δ={c.mean()-b.mean():+.0f} ({(c.mean()/b.mean()-1)*100:+.1f}%)")

    print("\n=== ToR→Agg queue integral (mean across seeds, bytes·µs) ===")
    for pair in tor_agg_pairs:
        b = get_tor_vals("baseline",    pair)
        c = get_tor_vals("constrained", pair)
        tag = "  <-- host 0 & 1" if pair.tor == 0 else ""
        print(f"  T{pair.tor}→A{pair.agg}: baseline={b.mean():.0f}"
              f"  constrained={c.mean():.0f}"
              f"  Δ={c.mean()-b.mean():+.0f} ({(c.mean()/b.mean()-1)*100:+.1f}%){tag}")


if __name__ == "__main__":
    main()
