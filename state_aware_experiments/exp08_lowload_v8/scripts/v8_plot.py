#!/usr/bin/env python3
"""
v8_plot.py — exp08 plotter.

Reads data/v8_fct.csv and data/v8_events.csv, produces PNGs in plots/.

95% CI uses t-distribution (scipy.stats.t) with df = n_seeds - 1.

Plots generated:
  fig1_p99_slowdown.png        — p99 FCT slowdown per mode × sev × workload
  fig2_mean_fct.png            — mean FCT per mode × sev × workload
  fig3_ecn_counter_dist.png    — ecn_counter distribution at ECN=1 ACKs:
                                  histogram columns 0..8, faceted by workload × sev,
                                  8 mode lines. Central question: is P(counter≥4|ECN=1)
                                  low at sparse load? (exp07 baseline was 65%)
  fig4_high_counter_rate.png   — bar chart: P(ecn_counter≥4 | ecn=1) per mode × sev
                                  faceted by workload. Reveals whether filter has
                                  a signal to act on.
  fig5_wtd_block_rate.png      — WTD block rate per workload × sev (diagnostic)
  fig6_fct_cdf.png             — FCT CDF per workload (2-panel sev=0/4, 8 modes)
  fig7_evhealth_vs_ecn_gain.png — scatter: mean_ecn_sf_gain vs high_counter_rate;
                                   shows whether evhealth counter tracks the
                                   attenuation gap vs plain ECN counter
  fig8_p99_vs_concurrency.png  — line plot: p99 slowdown vs flow count (2, 16, 32)
                                   per mode × sev. Reveals the load threshold
                                   where filter modes diverge from vanilla.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR    = SCRIPT_DIR.parent
DATA_DIR   = EXP_DIR / "data"
PLOTS_DIR  = EXP_DIR / "plots"
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Constants ─────────────────────────────────────────────────────────────────
MODES = [
    "vanilla", "wtd",
    "sf_md_gain_ecn", "sf_md_gain_fresh",
    "sf_blend_ecn",   "sf_blend_fresh",
    "sf_md_gain_evhealth", "sf_blend_evhealth",
]
MODE_LABELS = {
    "vanilla":             "Vanilla",
    "wtd":                 "WTD",
    "sf_md_gain_ecn":      "MdGain-ECN",
    "sf_md_gain_fresh":    "MdGain-Fresh",
    "sf_blend_ecn":        "Blend-ECN",
    "sf_blend_fresh":      "Blend-Fresh",
    "sf_md_gain_evhealth": "MdGain-EvHlth",
    "sf_blend_evhealth":   "Blend-EvHlth",
}
MODE_COLORS = {
    "vanilla":             "#333333",
    "wtd":                 "#888888",
    "sf_md_gain_ecn":      "#1f77b4",
    "sf_md_gain_fresh":    "#aec7e8",
    "sf_blend_ecn":        "#ff7f0e",
    "sf_blend_fresh":      "#ffbb78",
    "sf_md_gain_evhealth": "#2ca02c",
    "sf_blend_evhealth":   "#98df8a",
}
WORKLOADS = ["perm_2c_8mb", "perm_16c_8mb", "perm_32c_8mb"]
WORKLOAD_LABELS = {
    "perm_2c_8mb":  "2 flows / 8 MB",
    "perm_16c_8mb": "16 flows / 8 MB",
    "perm_32c_8mb": "32 flows / 8 MB",
}
WORKLOAD_CONNS = {"perm_2c_8mb": 2, "perm_16c_8mb": 16, "perm_32c_8mb": 32}
SEV_COLORS  = {0: "steelblue", 4: "tomato"}
SEV_LABELS  = {0: "sev=0 (healthy)", 4: "sev=4 (1 link fail)"}

# ── Statistics helper ─────────────────────────────────────────────────────────
def ci95(values):
    """Return (mean, half-width of 95% CI) using t-distribution. df = n-1."""
    n = len(values)
    if n == 0:
        return np.nan, np.nan
    if n == 1:
        return float(values[0]), np.nan
    m = np.mean(values)
    se = stats.sem(values)
    h = se * stats.t.ppf(0.975, df=n - 1)
    return float(m), float(h)


def p99_per_seed(df_group):
    """Return list of per-seed p99 slowdown values."""
    vals = []
    for seed, g in df_group.groupby("seed"):
        vals.append(np.percentile(g["slowdown"].dropna(), 99))
    return vals


def mean_fct_per_seed(df_group):
    vals = []
    for seed, g in df_group.groupby("seed"):
        vals.append(g["fct_us"].mean())
    return vals

# ── Load data ─────────────────────────────────────────────────────────────────
def load_data():
    fct_path = DATA_DIR / "v8_fct.csv"
    ev_path  = DATA_DIR / "v8_events.csv"
    if not fct_path.exists():
        print(f"ERROR: {fct_path} not found. Run v8_aggregate.py first.", file=sys.stderr)
        sys.exit(1)
    fct = pd.read_csv(fct_path)
    ev  = pd.read_csv(ev_path)
    # Filter to valid rows
    fct = fct.dropna(subset=["slowdown"])
    return fct, ev


# ── Fig 1: p99 FCT slowdown ───────────────────────────────────────────────────
def fig1_p99_slowdown(fct):
    nw  = len(WORKLOADS)
    fig, axes = plt.subplots(nw, 1, figsize=(12, 4 * nw), sharex=True)
    if nw == 1:
        axes = [axes]

    x = np.arange(len(MODES))
    bw = 0.35

    for ax, wl in zip(axes, WORKLOADS):
        for si, sev in enumerate([0, 4]):
            offsets = x + (si - 0.5) * bw
            means, errs = [], []
            for mode in MODES:
                sub = fct[(fct["workload"] == wl) & (fct["sev"] == sev) & (fct["mode"] == mode)]
                vals = p99_per_seed(sub)
                m, h = ci95(vals)
                means.append(m)
                errs.append(h if not np.isnan(h) else 0)
            ax.bar(offsets, means, bw, yerr=errs, capsize=4,
                   color=SEV_COLORS[sev], alpha=0.8, label=SEV_LABELS[sev])
        ax.set_title(WORKLOAD_LABELS[wl], fontsize=11)
        ax.set_ylabel("p99 FCT slowdown")
        ax.set_xticks(x)
        ax.set_xticklabels([MODE_LABELS[m] for m in MODES], rotation=30, ha="right", fontsize=9)
        ax.legend(fontsize=8)
        ax.axhline(1.0, color="black", lw=0.7, ls="--")

    fig.suptitle("exp08: p99 FCT slowdown by mode × sev × workload\n"
                 "(error bars = 95% CI over seeds, t-dist)", fontsize=12)
    fig.tight_layout()
    out = PLOTS_DIR / "fig1_p99_slowdown.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"  {out}")


# ── Fig 2: mean FCT ───────────────────────────────────────────────────────────
def fig2_mean_fct(fct):
    nw  = len(WORKLOADS)
    fig, axes = plt.subplots(nw, 1, figsize=(12, 4 * nw), sharex=True)
    if nw == 1:
        axes = [axes]

    x = np.arange(len(MODES))
    bw = 0.35

    for ax, wl in zip(axes, WORKLOADS):
        for si, sev in enumerate([0, 4]):
            offsets = x + (si - 0.5) * bw
            means, errs = [], []
            for mode in MODES:
                sub = fct[(fct["workload"] == wl) & (fct["sev"] == sev) & (fct["mode"] == mode)]
                vals = mean_fct_per_seed(sub)
                m, h = ci95(vals)
                means.append(m)
                errs.append(h if not np.isnan(h) else 0)
            ax.bar(offsets, means, bw, yerr=errs, capsize=4,
                   color=SEV_COLORS[sev], alpha=0.8, label=SEV_LABELS[sev])
        ax.set_title(WORKLOAD_LABELS[wl], fontsize=11)
        ax.set_ylabel("Mean FCT (µs)")
        ax.set_xticks(x)
        ax.set_xticklabels([MODE_LABELS[m] for m in MODES], rotation=30, ha="right", fontsize=9)
        ax.legend(fontsize=8)

    fig.suptitle("exp08: Mean FCT by mode × sev × workload\n"
                 "(error bars = 95% CI over seeds, t-dist)", fontsize=12)
    fig.tight_layout()
    out = PLOTS_DIR / "fig2_mean_fct.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"  {out}")


# ── Fig 3: ECN counter distribution at ECN=1 ACKs ────────────────────────────
def fig3_ecn_counter_dist(ev):
    """
    Bar chart: for each mode, the mean fraction of ECN ACKs at each counter value 0..8.
    Faceted by workload × sev. Lines instead of bars for readability with 8 modes.

    This is the key diagnostic: if outlier-EV regime is active, the distribution
    should be left-skewed (most ECN ACKs at counter=0,1,2). At full bisection
    (exp07 reference) it was right-skewed (65% at counter≥4).
    """
    # We need per-ACK data for this. Load diagnostics CSV (may be large).
    diag_path = DATA_DIR / "v8_diagnostics.csv"
    if not diag_path.exists():
        print(f"  SKIP fig3: {diag_path} not found")
        return

    chunks = []
    for chunk in pd.read_csv(diag_path, chunksize=500_000):
        ecn_rows = chunk[chunk["ecn"] == 1][["mode", "workload", "sev", "ecn_counter"]]
        chunks.append(ecn_rows)
    if not chunks:
        return
    diag = pd.concat(chunks, ignore_index=True)

    nw = len(WORKLOADS)
    fig, axes = plt.subplots(nw, 2, figsize=(14, 4 * nw), sharey=False)

    for wi, wl in enumerate(WORKLOADS):
        for si, sev in enumerate([0, 4]):
            ax = axes[wi][si]
            sub = diag[(diag["workload"] == wl) & (diag["sev"] == sev)]
            for mode in MODES:
                msub = sub[sub["mode"] == mode]
                if msub.empty:
                    continue
                counts = msub["ecn_counter"].value_counts(normalize=True).sort_index()
                full_idx = range(0, 9)
                vals = [counts.get(i, 0.0) for i in full_idx]
                ax.plot(list(full_idx), vals, "o-",
                        color=MODE_COLORS[mode], label=MODE_LABELS[mode],
                        linewidth=1.5, markersize=4)
            ax.set_xlabel("ecn_counter value")
            ax.set_ylabel("Fraction of ECN ACKs")
            ax.set_title(f"{WORKLOAD_LABELS[wl]} — {SEV_LABELS[sev]}", fontsize=9)
            ax.axvline(3.5, color="red", lw=0.8, ls="--", label="B/2=4")
            if wi == 0 and si == 0:
                ax.legend(fontsize=7, ncol=2)

    fig.suptitle("exp08: ECN counter distribution at ECN-marked ACKs\n"
                 "(left-skewed = outlier-EV regime; right-skewed = diffuse = exp07 regime)",
                 fontsize=11)
    fig.tight_layout()
    out = PLOTS_DIR / "fig3_ecn_counter_dist.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"  {out}")


# ── Fig 4: high_counter_rate bar chart ───────────────────────────────────────
def fig4_high_counter_rate(ev):
    """P(ecn_counter≥4 | ecn=1) per mode × workload × sev."""
    nw  = len(WORKLOADS)
    fig, axes = plt.subplots(1, nw, figsize=(5 * nw, 5), sharey=True)
    if nw == 1:
        axes = [axes]

    x = np.arange(len(MODES))
    bw = 0.35

    for ax, wl in zip(axes, WORKLOADS):
        for si, sev in enumerate([0, 4]):
            offsets = x + (si - 0.5) * bw
            means, errs = [], []
            for mode in MODES:
                sub = ev[(ev["workload"] == wl) & (ev["sev"] == sev) & (ev["mode"] == mode)]
                vals = sub["high_counter_rate"].dropna().tolist()
                m, h = ci95(vals)
                means.append(m if not np.isnan(m) else 0)
                errs.append(h if not np.isnan(h) else 0)
            ax.bar(offsets, means, bw, yerr=errs, capsize=4,
                   color=SEV_COLORS[sev], alpha=0.8, label=SEV_LABELS[sev])
        ax.axhline(0.65, color="red", lw=0.9, ls="--", label="exp07 reference (65%)")
        ax.set_title(WORKLOAD_LABELS[wl], fontsize=10)
        ax.set_ylabel("P(ecn_counter ≥ 4 | ecn=1)")
        ax.set_xticks(x)
        ax.set_xticklabels([MODE_LABELS[m] for m in MODES], rotation=40, ha="right", fontsize=8)
        ax.legend(fontsize=7)

    fig.suptitle("exp08: High-counter rate at ECN ACKs\n"
                 "Red dashed = exp07 full-bisection reference (65%). "
                 "Low = outlier-EV regime = filter has signal.", fontsize=10)
    fig.tight_layout()
    out = PLOTS_DIR / "fig4_high_counter_rate.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"  {out}")


# ── Fig 5: WTD block rate ─────────────────────────────────────────────────────
def fig5_wtd_block_rate(ev):
    wtd_ev = ev[ev["mode"] == "wtd"]
    if wtd_ev.empty:
        print("  SKIP fig5: no WTD runs in events CSV")
        return

    nw  = len(WORKLOADS)
    fig, ax = plt.subplots(figsize=(8, 4))

    x = np.arange(nw)
    bw = 0.35
    for si, sev in enumerate([0, 4]):
        offsets = x + (si - 0.5) * bw
        means, errs = [], []
        for wl in WORKLOADS:
            sub = wtd_ev[(wtd_ev["workload"] == wl) & (wtd_ev["sev"] == sev)]
            vals = sub["wtd_block_rate"].dropna().tolist()
            m, h = ci95(vals)
            means.append(m if not np.isnan(m) else 0)
            errs.append(h if not np.isnan(h) else 0)
        ax.bar(offsets, means, bw, yerr=errs, capsize=4,
               color=SEV_COLORS[sev], alpha=0.8, label=SEV_LABELS[sev])

    ax.set_xticks(x)
    ax.set_xticklabels([WORKLOAD_LABELS[w] for w in WORKLOADS], fontsize=9)
    ax.set_ylabel("WTD block rate (fraction of ECN ACKs where MD was suppressed)")
    ax.set_title("exp08: WTD block rate per workload × sev\n"
                 "(High = WTD suppresses too many MDs; Low = WTD is a no-op)")
    ax.legend()
    fig.tight_layout()
    out = PLOTS_DIR / "fig5_wtd_block_rate.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"  {out}")


# ── Fig 6: FCT CDF ────────────────────────────────────────────────────────────
def fig6_fct_cdf(fct):
    nw = len(WORKLOADS)
    fig, axes = plt.subplots(nw, 2, figsize=(14, 4 * nw))

    for wi, wl in enumerate(WORKLOADS):
        for si, sev in enumerate([0, 4]):
            ax = axes[wi][si]
            for mode in MODES:
                sub = fct[(fct["workload"] == wl) & (fct["sev"] == sev) & (fct["mode"] == mode)]
                vals = np.sort(sub["fct_us"].dropna().values)
                if len(vals) == 0:
                    continue
                cdf = np.arange(1, len(vals) + 1) / len(vals)
                ax.plot(vals, cdf, "-", color=MODE_COLORS[mode],
                        label=MODE_LABELS[mode], linewidth=1.2)
            ax.set_xscale("log")
            ax.set_xlabel("FCT (µs, log scale)")
            ax.set_ylabel("CDF")
            ax.set_title(f"{WORKLOAD_LABELS[wl]} — {SEV_LABELS[sev]}", fontsize=9)
            ax.legend(fontsize=7, ncol=2)

    fig.suptitle("exp08: FCT CDF per workload × sev (all seeds pooled)", fontsize=12)
    fig.tight_layout()
    out = PLOTS_DIR / "fig6_fct_cdf.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"  {out}")


# ── Fig 7: evhealth gain vs high_counter_rate scatter ────────────────────────
def fig7_evhealth_scatter(ev):
    """
    Scatter: mean_ecn_sf_gain vs high_counter_rate for evhealth modes.
    Hypothesis: evhealth counter is lower (more outlier) than ECN counter,
    causing different gain profiles.
    """
    sub = ev[ev["mode"].str.contains("evhealth")]
    ref = ev[ev["mode"].str.contains("md_gain_ecn")]
    if sub.empty:
        print("  SKIP fig7: no evhealth runs in events CSV")
        return

    fig, ax = plt.subplots(figsize=(8, 5))
    for mode in ["sf_md_gain_evhealth", "sf_blend_evhealth",
                 "sf_md_gain_ecn", "sf_blend_ecn"]:
        ms = ev[ev["mode"] == mode]
        if ms.empty:
            continue
        ax.scatter(ms["high_counter_rate"], ms["mean_ecn_sf_gain"],
                   label=MODE_LABELS[mode], color=MODE_COLORS[mode],
                   alpha=0.7, s=50)

    ax.set_xlabel("P(ecn_counter ≥ 4 | ecn=1)  [high = diffuse; low = outlier-EV]")
    ax.set_ylabel("Mean MD gain at ECN ACKs  [1.0 = full MD; 0 = no MD]")
    ax.set_title("exp08: Filter attenuation vs ECN-counter concentration\n"
                 "Each dot = one run cell (mode × workload × sev × seed)")
    ax.axhline(1.0, color="gray", lw=0.8, ls="--")
    ax.legend()
    fig.tight_layout()
    out = PLOTS_DIR / "fig7_evhealth_gain_scatter.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"  {out}")


# ── Fig 8: p99 slowdown vs concurrency ───────────────────────────────────────
def fig8_p99_vs_concurrency(fct):
    """
    Line plot: p99 FCT slowdown vs flow count (2, 16, 32), per mode × sev.
    Answers: at what concurrency does each filter mode diverge from vanilla?
    """
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    conns_order = [2, 16, 32]
    wl_for_conn = {2: "perm_2c_8mb", 16: "perm_16c_8mb", 32: "perm_32c_8mb"}

    for si, sev in enumerate([0, 4]):
        ax = axes[si]
        for mode in MODES:
            xs, ms, hs = [], [], []
            for nc in conns_order:
                wl  = wl_for_conn[nc]
                sub = fct[(fct["workload"] == wl) & (fct["sev"] == sev) & (fct["mode"] == mode)]
                vals = p99_per_seed(sub)
                m, h = ci95(vals)
                xs.append(nc)
                ms.append(m if not np.isnan(m) else 0)
                hs.append(h if not np.isnan(h) else 0)
            ax.errorbar(xs, ms, yerr=hs, fmt="o-",
                        color=MODE_COLORS[mode], label=MODE_LABELS[mode],
                        linewidth=1.5, markersize=5, capsize=4)
        ax.set_xscale("log")
        ax.set_xticks(conns_order)
        ax.set_xticklabels([str(c) for c in conns_order])
        ax.set_xlabel("Number of concurrent flows (log scale)")
        ax.set_ylabel("p99 FCT slowdown")
        ax.set_title(f"{SEV_LABELS[sev]}", fontsize=10)
        ax.legend(fontsize=8, ncol=2)
        ax.axhline(1.0, color="black", lw=0.7, ls="--")

    fig.suptitle("exp08: p99 FCT slowdown vs concurrency\n"
                 "(error bars = 95% CI over seeds)", fontsize=12)
    fig.tight_layout()
    out = PLOTS_DIR / "fig8_p99_vs_concurrency.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"  {out}")


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print("Loading data...")
    fct, ev = load_data()
    print(f"  FCT rows: {len(fct):,}  Event rows: {len(ev)}")

    print("Generating plots...")
    fig1_p99_slowdown(fct)
    fig2_mean_fct(fct)
    fig3_ecn_counter_dist(ev)      # loads diagnostics CSV if available
    fig4_high_counter_rate(ev)
    fig5_wtd_block_rate(ev)
    fig6_fct_cdf(fct)
    fig7_evhealth_scatter(ev)
    fig8_p99_vs_concurrency(fct)

    print(f"\nAll plots saved to {PLOTS_DIR}")


if __name__ == "__main__":
    main()
