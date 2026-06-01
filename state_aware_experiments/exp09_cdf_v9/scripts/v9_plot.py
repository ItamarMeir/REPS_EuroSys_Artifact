#!/usr/bin/env python3
"""
v9_plot.py — exp09 plotter.

Reads data/v9_fct.csv, v9_events.csv, v9_diagnostics.csv and emits PNG plots to
plots/.

Figures:
  fig1_p99_slowdown.png          — p99 FCT slowdown per mode × sev × workload
  fig2_mean_fct.png              — mean FCT per mode × sev × workload
  fig3_ecn_counter_dist.png      — ECN-counter distribution at ecn=1 ACKs
  fig4_high_counter_rate.png     — P(ecn_counter≥4|ecn=1) per workload/load
  fig5_wtd_block_rate.png        — WTD block rate per workload × sev
  fig6_fct_cdf.png               — FCT CDF per load × sev
  fig7_evhealth_gain_scatter.png — filter attenuation vs counter concentration
  fig8_p99_vs_load.png           — p99 slowdown vs load level per CDF
  fig9_ecn_vs_load.png           — n_ecn_acks vs load per CDF (Phase-1 probe)
  fig10_size_bucket_breakdown.png— slowdown per mode × size-bucket × CDF
"""

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats as scipy_stats

warnings.filterwarnings("ignore")

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR    = SCRIPT_DIR.parent
DATA_DIR   = EXP_DIR / "data"
PLOT_DIR   = EXP_DIR / "plots"

MODES = [
    "vanilla", "wtd",
    "sf_md_gain_ecn", "sf_md_gain_fresh",
    "sf_blend_ecn",   "sf_blend_fresh",
    "sf_md_gain_evhealth", "sf_blend_evhealth",
]
MODE_LABELS = {
    "vanilla":             "Vanilla",
    "wtd":                 "WTD",
    "sf_md_gain_ecn":      "MdGain/ECN",
    "sf_md_gain_fresh":    "MdGain/Fresh",
    "sf_blend_ecn":        "Blend/ECN",
    "sf_blend_fresh":      "Blend/Fresh",
    "sf_md_gain_evhealth": "MdGain/EvHealth",
    "sf_blend_evhealth":   "Blend/EvHealth",
}
MODE_COLORS = plt.cm.tab10(np.linspace(0, 1, len(MODES)))
MODE_COLOR  = dict(zip(MODES, MODE_COLORS))

LOAD_LABELS  = {30: "30%", 60: "60%", 90: "90%"}
SEV_LABELS   = {0: "Healthy (sev=0)", 4: "Failure (sev=4)"}
WL_LABELS    = {"websearch": "WebSearch", "hadoop": "Hadoop"}


# ── Statistics helpers ────────────────────────────────────────────────────────
def ci95(vals):
    """95% CI half-width using t-distribution."""
    vals = np.array(vals)
    n = len(vals)
    if n < 2:
        return 0.0
    return scipy_stats.t.ppf(0.975, df=n-1) * vals.std(ddof=1) / np.sqrt(n)


def p99(series):
    return series.quantile(0.99)


# ── Load data ─────────────────────────────────────────────────────────────────
def load_data():
    fct  = pd.read_csv(DATA_DIR / "v9_fct.csv")
    ev   = pd.read_csv(DATA_DIR / "v9_events.csv")
    diag_path = DATA_DIR / "v9_diagnostics.csv"
    diag = pd.read_csv(diag_path) if diag_path.exists() else pd.DataFrame()
    return fct, ev, diag


# ── Figure 1: p99 slowdown per mode × sev × workload ─────────────────────────
def fig1_p99_slowdown(fct: pd.DataFrame):
    workloads = sorted(fct["workload"].unique())
    sevs      = sorted(fct["sev"].unique())
    modes_present = [m for m in MODES if m in fct["mode"].unique()]
    loads     = sorted(fct["load"].unique())

    # Aggregate p99 per (mode, workload, load, sev, seed) then plot across seeds
    fig, axes = plt.subplots(len(sevs), len(workloads),
                              figsize=(5 * len(workloads), 4 * len(sevs)),
                              sharey=True)
    if len(sevs) == 1:
        axes = [axes]
    if len(workloads) == 1:
        axes = [[ax] for ax in axes]

    for ri, sev in enumerate(sevs):
        for ci, wl in enumerate(workloads):
            ax = axes[ri][ci]
            sub = fct[(fct["workload"] == wl) & (fct["sev"] == sev)]
            if sub.empty:
                ax.set_title(f"{WL_LABELS.get(wl,wl)} sev={sev} — no data")
                continue

            x = np.arange(len(loads))
            width = 0.8 / len(modes_present)

            for mi, mode in enumerate(modes_present):
                msub = sub[sub["mode"] == mode]
                vals = msub.groupby(["load", "seed"])["slowdown"].apply(p99).reset_index()
                means = vals.groupby("load")["slowdown"].mean()
                errs  = vals.groupby("load")["slowdown"].apply(ci95)
                y     = [means.get(l, np.nan) for l in loads]
                e     = [errs.get(l, 0)       for l in loads]
                ax.bar(x + mi * width, y, width, yerr=e,
                       label=MODE_LABELS.get(mode, mode),
                       color=MODE_COLOR[mode], capsize=3, alpha=0.85)

            ax.set_xticks(x + width * len(modes_present) / 2)
            ax.set_xticklabels([LOAD_LABELS.get(l, str(l)) for l in loads])
            ax.set_xlabel("Load")
            ax.set_ylabel("p99 FCT slowdown")
            ax.set_title(f"{WL_LABELS.get(wl,wl)} — {SEV_LABELS.get(sev,sev)}")
            ax.axhline(1.0, color="black", lw=0.7, ls="--")
            if ri == 0 and ci == len(workloads) - 1:
                ax.legend(fontsize=7, ncol=2)

    fig.suptitle("exp09 — p99 FCT slowdown by mode, load, workload, severity")
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "fig1_p99_slowdown.png", dpi=150)
    plt.close(fig)
    print("  fig1_p99_slowdown.png")


# ── Figure 2: mean FCT per mode × sev × workload ─────────────────────────────
def fig2_mean_fct(fct: pd.DataFrame):
    workloads = sorted(fct["workload"].unique())
    sevs      = sorted(fct["sev"].unique())
    modes_present = [m for m in MODES if m in fct["mode"].unique()]
    loads     = sorted(fct["load"].unique())

    fig, axes = plt.subplots(len(sevs), len(workloads),
                              figsize=(5 * len(workloads), 4 * len(sevs)),
                              sharey=True)
    if len(sevs) == 1:
        axes = [axes]
    if len(workloads) == 1:
        axes = [[ax] for ax in axes]

    for ri, sev in enumerate(sevs):
        for ci, wl in enumerate(workloads):
            ax = axes[ri][ci]
            sub = fct[(fct["workload"] == wl) & (fct["sev"] == sev)]
            if sub.empty:
                continue

            x = np.arange(len(loads))
            width = 0.8 / len(modes_present)

            for mi, mode in enumerate(modes_present):
                msub = sub[sub["mode"] == mode]
                vals = msub.groupby(["load", "seed"])["fct_us"].mean().reset_index()
                means = vals.groupby("load")["fct_us"].mean()
                errs  = vals.groupby("load")["fct_us"].apply(ci95)
                y     = [means.get(l, np.nan) for l in loads]
                e     = [errs.get(l, 0)       for l in loads]
                ax.bar(x + mi * width, y, width, yerr=e,
                       label=MODE_LABELS.get(mode, mode),
                       color=MODE_COLOR[mode], capsize=3, alpha=0.85)

            ax.set_xticks(x + width * len(modes_present) / 2)
            ax.set_xticklabels([LOAD_LABELS.get(l, str(l)) for l in loads])
            ax.set_xlabel("Load")
            ax.set_ylabel("Mean FCT (µs)")
            ax.set_title(f"{WL_LABELS.get(wl,wl)} — {SEV_LABELS.get(sev,sev)}")
            if ri == 0 and ci == len(workloads) - 1:
                ax.legend(fontsize=7, ncol=2)

    fig.suptitle("exp09 — Mean FCT by mode, load, workload, severity")
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "fig2_mean_fct.png", dpi=150)
    plt.close(fig)
    print("  fig2_mean_fct.png")


# ── Figure 3: ECN counter distribution at ECN=1 ACKs ─────────────────────────
def fig3_ecn_counter_dist(diag: pd.DataFrame):
    if diag.empty or "ecn" not in diag.columns:
        print("  fig3 skipped (no diagnostics)")
        return

    ecn_rows = diag[diag["ecn"] == 1]
    if ecn_rows.empty:
        print("  fig3 skipped (zero ECN ACKs in diagnostics)")
        return

    workloads = sorted(diag["workload"].unique())
    loads     = sorted(diag["load"].unique())

    fig, axes = plt.subplots(len(workloads), len(loads),
                              figsize=(5 * len(loads), 4 * len(workloads)),
                              sharey=True)
    if len(workloads) == 1:
        axes = [axes]
    if len(loads) == 1:
        axes = [[ax] for ax in axes]

    B = 8
    bins = np.arange(B + 2) - 0.5

    for ri, wl in enumerate(workloads):
        for ci, load in enumerate(loads):
            ax = axes[ri][ci]
            sub = ecn_rows[(ecn_rows["workload"] == wl) & (ecn_rows["load"] == load)]
            if sub.empty:
                ax.set_title(f"{WL_LABELS.get(wl,wl)} l={load}% — no ECN")
                continue
            ax.hist(sub["ecn_counter"], bins=bins, density=True, alpha=0.7,
                    label=f"n={len(sub):,}")
            ax.axvline(B / 2, color="red", lw=1, ls="--", label="B/2=4")
            ax.set_xlabel("ecn_counter at ECN ACK")
            ax.set_ylabel("Density")
            ax.set_title(f"{WL_LABELS.get(wl,wl)} l={load}%")
            ax.legend(fontsize=7)

    fig.suptitle("exp09 — ECN counter distribution at ECN=1 ACKs")
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "fig3_ecn_counter_dist.png", dpi=150)
    plt.close(fig)
    print("  fig3_ecn_counter_dist.png")


# ── Figure 4: high_counter_rate per workload/load ────────────────────────────
def fig4_high_counter_rate(ev: pd.DataFrame):
    vanilla = ev[ev["mode"] == "vanilla"]
    if vanilla.empty:
        print("  fig4 skipped")
        return

    workloads = sorted(ev["workload"].unique())
    loads     = sorted(ev["load"].unique())

    fig, ax = plt.subplots(figsize=(8, 4))
    x = np.arange(len(loads))
    width = 0.8 / len(workloads)

    for wi, wl in enumerate(workloads):
        sub = vanilla[vanilla["workload"] == wl]
        means = sub.groupby("load")["high_counter_rate"].mean()
        errs  = sub.groupby("load")["high_counter_rate"].apply(ci95)
        y = [means.get(l, np.nan) for l in loads]
        e = [errs.get(l, 0)       for l in loads]
        ax.bar(x + wi * width, y, width, yerr=e,
               label=WL_LABELS.get(wl, wl), capsize=3, alpha=0.85)

    ax.axhline(0.65, color="red", lw=1, ls="--", label="exp07 baseline (65%)")
    ax.set_xticks(x + width * len(workloads) / 2)
    ax.set_xticklabels([LOAD_LABELS.get(l, str(l)) for l in loads])
    ax.set_xlabel("Load")
    ax.set_ylabel("P(ecn_counter≥4 | ecn=1)")
    ax.set_title("exp09 — ECN diffuseness (high counter rate)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "fig4_high_counter_rate.png", dpi=150)
    plt.close(fig)
    print("  fig4_high_counter_rate.png")


# ── Figure 5: WTD block rate ─────────────────────────────────────────────────
def fig5_wtd_block_rate(ev: pd.DataFrame):
    wtd = ev[ev["mode"] == "wtd"]
    if wtd.empty:
        print("  fig5 skipped (no wtd data)")
        return

    workloads = sorted(ev["workload"].unique())
    loads     = sorted(ev["load"].unique())
    sevs      = sorted(ev["sev"].unique())

    fig, axes = plt.subplots(1, len(sevs), figsize=(6 * len(sevs), 4))
    if len(sevs) == 1:
        axes = [axes]

    for si, sev in enumerate(sevs):
        ax = axes[si]
        x = np.arange(len(loads))
        width = 0.8 / len(workloads)
        for wi, wl in enumerate(workloads):
            sub = wtd[(wtd["workload"] == wl) & (wtd["sev"] == sev)]
            means = sub.groupby("load")["wtd_block_rate"].mean()
            errs  = sub.groupby("load")["wtd_block_rate"].apply(ci95)
            y = [means.get(l, np.nan) for l in loads]
            e = [errs.get(l, 0)       for l in loads]
            ax.bar(x + wi * width, y, width, yerr=e,
                   label=WL_LABELS.get(wl, wl), capsize=3, alpha=0.85)
        ax.set_xticks(x + width * len(workloads) / 2)
        ax.set_xticklabels([LOAD_LABELS.get(l, str(l)) for l in loads])
        ax.set_xlabel("Load")
        ax.set_ylabel("WTD block rate")
        ax.set_title(f"{SEV_LABELS.get(sev,sev)}")
        ax.legend()

    fig.suptitle("exp09 — WTD block rate (fraction of ECN ACKs blocked from MD)")
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "fig5_wtd_block_rate.png", dpi=150)
    plt.close(fig)
    print("  fig5_wtd_block_rate.png")


# ── Figure 6: FCT CDF ────────────────────────────────────────────────────────
def fig6_fct_cdf(fct: pd.DataFrame):
    workloads = sorted(fct["workload"].unique())
    loads     = sorted(fct["load"].unique())
    sevs      = sorted(fct["sev"].unique())
    modes_present = [m for m in MODES if m in fct["mode"].unique()]

    fig, axes = plt.subplots(len(sevs) * len(workloads), len(loads),
                              figsize=(5 * len(loads), 4 * len(sevs) * len(workloads)))
    axes = np.array(axes).reshape(len(sevs) * len(workloads), len(loads))

    ri = 0
    for sev in sevs:
        for wl in workloads:
            for ci, load in enumerate(loads):
                ax = axes[ri][ci]
                sub = fct[(fct["workload"] == wl) & (fct["sev"] == sev)
                          & (fct["load"] == load)]
                for mode in modes_present:
                    msub = sub[sub["mode"] == mode]["slowdown"].dropna().sort_values()
                    if msub.empty:
                        continue
                    cdf = np.linspace(0, 1, len(msub))
                    ax.plot(msub.values, cdf,
                            label=MODE_LABELS.get(mode, mode),
                            color=MODE_COLOR[mode], lw=1.2)
                ax.set_xlabel("FCT slowdown")
                ax.set_ylabel("CDF")
                ax.set_title(f"{WL_LABELS.get(wl,wl)} l={load}% {SEV_LABELS.get(sev,sev)}")
                ax.set_xlim(left=1.0)
                if ci == len(loads) - 1:
                    ax.legend(fontsize=6)
            ri += 1

    fig.suptitle("exp09 — FCT slowdown CDF")
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "fig6_fct_cdf.png", dpi=150)
    plt.close(fig)
    print("  fig6_fct_cdf.png")


# ── Figure 7: evhealth gain scatter ──────────────────────────────────────────
def fig7_evhealth_gain_scatter(ev: pd.DataFrame, diag: pd.DataFrame):
    evh_modes = [m for m in MODES if "evhealth" in m]
    if not evh_modes or diag.empty:
        print("  fig7 skipped (no evhealth data)")
        return

    fig, ax = plt.subplots(figsize=(7, 5))
    for mode in evh_modes:
        sub_ev = ev[ev["mode"] == mode]
        if sub_ev.empty:
            continue
        ax.scatter(sub_ev["high_counter_rate"], sub_ev["mean_ecn_sf_gain"],
                   label=MODE_LABELS.get(mode, mode), alpha=0.6, s=30)

    ax.set_xlabel("High counter rate (P(ecn_counter≥4|ecn=1))")
    ax.set_ylabel("Mean SF gain when ECN=1")
    ax.axhline(1.0, color="black", lw=0.7, ls="--")
    ax.set_title("exp09 — Filter attenuation vs counter concentration (evhealth modes)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "fig7_evhealth_gain_scatter.png", dpi=150)
    plt.close(fig)
    print("  fig7_evhealth_gain_scatter.png")


# ── Figure 8: p99 slowdown vs load ───────────────────────────────────────────
def fig8_p99_vs_load(fct: pd.DataFrame):
    workloads = sorted(fct["workload"].unique())
    sevs      = sorted(fct["sev"].unique())
    loads     = sorted(fct["load"].unique())
    modes_present = [m for m in MODES if m in fct["mode"].unique()]

    fig, axes = plt.subplots(len(sevs), len(workloads),
                              figsize=(6 * len(workloads), 4 * len(sevs)))
    if len(sevs) == 1:
        axes = [axes]
    if len(workloads) == 1:
        axes = [[ax] for ax in axes]

    for ri, sev in enumerate(sevs):
        for ci, wl in enumerate(workloads):
            ax = axes[ri][ci]
            sub = fct[(fct["workload"] == wl) & (fct["sev"] == sev)]
            for mode in modes_present:
                msub = sub[sub["mode"] == mode]
                vals = msub.groupby(["load", "seed"])["slowdown"].apply(p99).reset_index()
                means = vals.groupby("load")["slowdown"].mean()
                errs  = vals.groupby("load")["slowdown"].apply(ci95)
                y = [means.get(l, np.nan) for l in loads]
                e = [errs.get(l, 0)       for l in loads]
                ax.errorbar(loads, y, yerr=e,
                            label=MODE_LABELS.get(mode, mode),
                            color=MODE_COLOR[mode],
                            marker="o", capsize=3, lw=1.5)
            ax.axhline(1.0, color="black", lw=0.7, ls="--")
            ax.set_xlabel("Load (%)")
            ax.set_ylabel("p99 FCT slowdown")
            ax.set_xticks(loads)
            ax.set_title(f"{WL_LABELS.get(wl,wl)} — {SEV_LABELS.get(sev,sev)}")
            if ri == 0 and ci == len(workloads) - 1:
                ax.legend(fontsize=7, ncol=2)

    fig.suptitle("exp09 — p99 FCT slowdown vs load level")
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "fig8_p99_vs_load.png", dpi=150)
    plt.close(fig)
    print("  fig8_p99_vs_load.png")


# ── Figure 9: ECN count vs load (Phase-1 probe diagnostic) ───────────────────
def fig9_ecn_vs_load(ev: pd.DataFrame):
    vanilla = ev[ev["mode"] == "vanilla"]
    if vanilla.empty:
        print("  fig9 skipped")
        return

    workloads = sorted(ev["workload"].unique())
    loads     = sorted(ev["load"].unique())
    sevs      = sorted(ev["sev"].unique())

    fig, axes = plt.subplots(1, len(sevs), figsize=(6 * len(sevs), 4))
    if len(sevs) == 1:
        axes = [axes]

    for si, sev in enumerate(sevs):
        ax = axes[si]
        for wl in workloads:
            sub = vanilla[(vanilla["workload"] == wl) & (vanilla["sev"] == sev)]
            means = sub.groupby("load")["n_ecn_acks"].mean()
            errs  = sub.groupby("load")["n_ecn_acks"].apply(ci95)
            y = [means.get(l, np.nan) for l in loads]
            e = [errs.get(l, 0)       for l in loads]
            ax.errorbar(loads, y, yerr=e,
                        label=WL_LABELS.get(wl, wl), marker="o", capsize=3)
        ax.axhline(50, color="green", lw=1, ls="--", label="Phase-1 threshold (50)")
        ax.set_xlabel("Load (%)")
        ax.set_ylabel("n_ecn_acks (3 logged sources)")
        ax.set_xticks(loads)
        ax.set_title(f"{SEV_LABELS.get(sev,sev)}")
        ax.legend()

    fig.suptitle("exp09 — Phase-1 probe: total ECN ACKs vs load (vanilla only)")
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "fig9_ecn_vs_load.png", dpi=150)
    plt.close(fig)
    print("  fig9_ecn_vs_load.png")


# ── Figure 10: size-bucket FCT breakdown ─────────────────────────────────────
def fig10_size_bucket_breakdown(fct: pd.DataFrame):
    buckets       = ["mice", "medium", "elephant"]
    workloads     = sorted(fct["workload"].unique())
    modes_present = [m for m in MODES if m in fct["mode"].unique()]
    loads         = sorted(fct["load"].unique())

    # Combine sev=0 only for clarity
    sub = fct[fct["sev"] == 0]
    if sub.empty:
        print("  fig10 skipped (no sev=0 data)")
        return

    n_bkts = len([b for b in buckets if b in sub["flow_class"].unique()])
    if n_bkts == 0:
        print("  fig10 skipped (no flow_class data)")
        return

    fig, axes = plt.subplots(len(workloads), n_bkts,
                              figsize=(5 * n_bkts, 4 * len(workloads)))
    if len(workloads) == 1:
        axes = [axes]
    if n_bkts == 1:
        axes = [[ax] for ax in axes]

    present_buckets = [b for b in buckets if b in sub["flow_class"].unique()]

    for ri, wl in enumerate(workloads):
        for ci, bkt in enumerate(present_buckets):
            ax = axes[ri][ci]
            bsub = sub[(sub["workload"] == wl) & (sub["flow_class"] == bkt)]
            if bsub.empty:
                ax.set_title(f"{WL_LABELS.get(wl,wl)} {bkt} — no data")
                continue

            x = np.arange(len(loads))
            width = 0.8 / len(modes_present)
            for mi, mode in enumerate(modes_present):
                msub = bsub[bsub["mode"] == mode]
                vals = msub.groupby(["load", "seed"])["slowdown"].apply(p99).reset_index()
                means = vals.groupby("load")["slowdown"].mean()
                errs  = vals.groupby("load")["slowdown"].apply(ci95)
                y = [means.get(l, np.nan) for l in loads]
                e = [errs.get(l, 0)       for l in loads]
                ax.bar(x + mi * width, y, width, yerr=e,
                       label=MODE_LABELS.get(mode, mode),
                       color=MODE_COLOR[mode], capsize=3, alpha=0.85)

            ax.set_xticks(x + width * len(modes_present) / 2)
            ax.set_xticklabels([LOAD_LABELS.get(l, str(l)) for l in loads])
            ax.set_xlabel("Load")
            ax.set_ylabel("p99 slowdown")
            ax.set_title(f"{WL_LABELS.get(wl,wl)} — {bkt}")
            ax.axhline(1.0, color="black", lw=0.7, ls="--")
            if ri == 0 and ci == n_bkts - 1:
                ax.legend(fontsize=7, ncol=2)

    fig.suptitle("exp09 — p99 slowdown per size bucket (sev=0)")
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "fig10_size_bucket_breakdown.png", dpi=150)
    plt.close(fig)
    print("  fig10_size_bucket_breakdown.png")


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    for f in [DATA_DIR / "v9_fct.csv", DATA_DIR / "v9_events.csv"]:
        if not f.exists():
            sys.exit(f"ERROR: {f} not found — run v9_aggregate.py first.")

    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    fct, ev, diag = load_data()

    print(f"Loaded: {len(fct)} flow rows, {len(ev)} event rows, "
          f"{len(diag)} diag rows")

    fig1_p99_slowdown(fct)
    fig2_mean_fct(fct)
    fig3_ecn_counter_dist(diag)
    fig4_high_counter_rate(ev)
    fig5_wtd_block_rate(ev)
    fig6_fct_cdf(fct)
    fig7_evhealth_gain_scatter(ev, diag)
    fig8_p99_vs_load(fct)
    fig9_ecn_vs_load(ev)
    fig10_size_bucket_breakdown(fct)

    print(f"\nAll plots written to {PLOT_DIR}")


if __name__ == "__main__":
    main()
