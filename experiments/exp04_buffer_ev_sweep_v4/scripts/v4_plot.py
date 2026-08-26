#!/usr/bin/env python3
"""
v4_plot.py — exp04 plotter.

Reads data/v4_fct.csv, data/v4_cwnd.csv, data/v4_events.csv
and emits ~12 PNG plots to plots/.

Error bars are 95% CI using the t-distribution across 5 seeds.

Plot catalogue
--------------
Part A (buffer sweep, paths=16):
  A1. FCT p99 slowdown vs buf_size — pureperm_8mb   (sev=0 vs sev=4)
  A2. FCT p99 slowdown vs buf_size — perm_128mb     (sev=0 vs sev=4)
  A3. FCT p99 slowdown vs buf_size — composite incast (sev=0 vs sev=4)
  A4. Mean cwnd/BDP vs buf_size                     (sev=0 vs sev=4)
  A5. Mean in_flight/cwnd (fill_rate) vs buf_size   (sev=0 vs sev=4)
  A6. cwnd_pkts time-series (pureperm_8mb, seed=42, sev=4): one line per buf value

Part B (EV domain sweep, buf=1024):
  B1. FCT p99 slowdown vs ev_domain — pureperm_8mb  (sev=0 vs sev=4)
  B2. FCT p99 slowdown vs ev_domain — perm_128mb    (sev=0 vs sev=4)
  B3. FCT p99 slowdown vs ev_domain — composite incast (sev=0 vs sev=4)
  B4. Mean cwnd/BDP vs ev_domain                    (sev=0 vs sev=4)
  B5. Mean in_flight/cwnd (fill_rate) vs ev_domain  (sev=0 vs sev=4)
  B6. cwnd_pkts time-series (pureperm_8mb, seed=42, sev=4): one line per ev_domain
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
PLOT_DIR   = EXP_DIR / "plots"
PLOT_DIR.mkdir(parents=True, exist_ok=True)

# ── CI helper ─────────────────────────────────────────────────────────────────
def ci95(values):
    """Return (mean, half-width of 95% CI) for a 1-D array."""
    a = np.asarray(values, dtype=float)
    a = a[np.isfinite(a)]
    n = len(a)
    if n < 2:
        return (a[0] if n == 1 else np.nan), np.nan
    m = a.mean()
    se = stats.sem(a)
    h = se * stats.t.ppf(0.975, df=n-1)
    return m, h

# ── Load data ─────────────────────────────────────────────────────────────────
def load_data():
    fct    = pd.read_csv(DATA_DIR / "v4_fct.csv")
    cwnd   = pd.read_csv(DATA_DIR / "v4_cwnd.csv")
    events = pd.read_csv(DATA_DIR / "v4_events.csv")
    # Cap fill_rate at 2.0 to remove integer-overflow artifacts
    # (45/4.4M rows where _in_flight briefly goes negative and wraps to 2^32-1)
    cwnd["fill_rate"] = cwnd["fill_rate"].clip(upper=2.0)
    return fct, cwnd, events

# ── Shared style ──────────────────────────────────────────────────────────────
SEV_COLORS   = {0: "#2196F3", 4: "#F44336"}   # blue=healthy, red=failure
SEV_LABELS   = {0: "sev=0 (no failure)", 4: "sev=4 (4 links failed)"}
SEV_MARKERS  = {0: "o", 4: "s"}

BUF_TICKS    = [1, 2, 4, 8, 1024]
BUF_XLABELS  = ["1", "2", "4", "8", "∞ (1024)"]
EV_TICKS     = [1, 2, 4, 8, 16]
EV_XLABELS   = ["1", "2", "4", "8", "16 (full)"]

TIME_COLORS  = plt.cm.viridis  # for time-series multi-line plots

plt.rcParams.update({"figure.dpi": 150, "font.size": 9})


# ── Generic per-seed aggregation + bar chart ──────────────────────────────────
def agg_per_seed(df: pd.DataFrame, dim_col: str, val_col: str,
                 sev_filter: int) -> pd.DataFrame:
    """
    Aggregate val_col per (dim_col, seed) using median (for FCT) or mean.
    Returns columns: [dim_col, seed, value].
    """
    sub = df[df["sev"] == sev_filter]
    return (
        sub.groupby([dim_col, "seed"])[val_col]
        .median()
        .reset_index()
        .rename(columns={val_col: "value"})
    )


def plot_sweep(ax, df: pd.DataFrame, dim_col: str, dim_ticks, dim_xlabels,
               val_col: str, sevs=(0, 4), agg_fn="median"):
    """
    Line chart with 95% CI, one line per severity.
    agg_fn: 'median' (for FCT slowdown) or 'mean' (for CC metrics).
    """
    fn = np.median if agg_fn == "median" else np.mean
    for sev in sevs:
        sub = df[df["sev"] == sev]
        means, herrs = [], []
        for dv in dim_ticks:
            vals = sub[sub[dim_col] == dv].groupby("seed")[val_col].apply(fn)
            m, h = ci95(vals.values)
            means.append(m); herrs.append(h)
        # Replace nan CI half-widths with 0 (happens when only 1 seed available)
        herrs_safe = [0.0 if (v is None or np.isnan(v)) else v for v in herrs]
        means_safe = [np.nan if (v is None or np.isnan(v)) else v for v in means]
        ax.errorbar(
            range(len(dim_ticks)), means_safe, yerr=herrs_safe,
            label=SEV_LABELS[sev],
            color=SEV_COLORS[sev],
            marker=SEV_MARKERS[sev],
            capsize=3, linewidth=1.5,
        )
    ax.set_xticks(range(len(dim_ticks)))
    ax.set_xticklabels(dim_xlabels)
    ax.legend(fontsize=7)
    ax.grid(axis="y", alpha=0.3)


# ── Plot A1/A2/A3 and B1/B2/B3: FCT p99 slowdown ─────────────────────────────
def plot_fct_slowdown(fct: pd.DataFrame, part: str,
                      workload: str, flow_class: str,
                      dim_col: str, dim_ticks, dim_xlabels,
                      xlabel: str, out_name: str):
    sub = fct[fct["part"] == part]
    sub = sub[sub["workload"] == workload]
    if flow_class != "all":
        sub = sub[sub["flow_class"] == flow_class]

    if sub.empty:
        print(f"  SKIP (no data): {out_name}")
        return

    fig, ax = plt.subplots(figsize=(5, 3.5))

    for sev in (0, 4):
        s = sub[sub["sev"] == sev]
        means, herrs = [], []
        for dv in dim_ticks:
            vals = s[s[dim_col] == dv].groupby("seed")["slowdown"].quantile(0.99)
            m, h = ci95(vals.values)
            means.append(m); herrs.append(h)
        herrs_safe = [0.0 if (v is None or np.isnan(v)) else v for v in herrs]
        means_safe = [np.nan if (v is None or np.isnan(v)) else v for v in means]
        ax.errorbar(
            range(len(dim_ticks)), means_safe, yerr=herrs_safe,
            label=SEV_LABELS[sev],
            color=SEV_COLORS[sev],
            marker=SEV_MARKERS[sev],
            capsize=3, linewidth=1.5,
        )

    ax.axhline(1.0, color="gray", linestyle="--", linewidth=0.8, label="ideal (1×)")
    ax.set_xticks(range(len(dim_ticks)))
    ax.set_xticklabels(dim_xlabels)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("FCT p99 slowdown")
    fc_label = flow_class if flow_class != "all" else ""
    ax.set_title(f"{workload}{' — '+fc_label if fc_label else ''}")
    ax.legend(fontsize=7)
    ax.grid(axis="y", alpha=0.3)

    fig.tight_layout()
    outpath = PLOT_DIR / out_name
    fig.savefig(outpath)
    plt.close(fig)
    print(f"  Saved {outpath}")


# ── Plot A4/B4: mean cwnd/BDP ─────────────────────────────────────────────────
def plot_cwnd_bdp(cwnd: pd.DataFrame, part: str,
                  dim_col: str, dim_ticks, dim_xlabels,
                  xlabel: str, out_name: str):
    sub = cwnd[cwnd["part"] == part]
    if sub.empty:
        print(f"  SKIP (no data): {out_name}")
        return

    fig, ax = plt.subplots(figsize=(5, 3.5))
    plot_sweep(ax, sub, dim_col, dim_ticks, dim_xlabels,
               "cwnd_bdp", agg_fn="mean")
    ax.axhline(1.0, color="gray", linestyle="--", linewidth=0.8, label="1 BDP")
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Mean cwnd / BDP")
    ax.set_title(f"CC window efficiency ({part})")
    ax.legend(fontsize=7)
    fig.tight_layout()
    outpath = PLOT_DIR / out_name
    fig.savefig(outpath)
    plt.close(fig)
    print(f"  Saved {outpath}")


# ── Plot A5/B5: fill_rate ─────────────────────────────────────────────────────
def plot_fill_rate(cwnd: pd.DataFrame, part: str,
                   dim_col: str, dim_ticks, dim_xlabels,
                   xlabel: str, out_name: str):
    sub = cwnd[cwnd["part"] == part]
    if sub.empty:
        print(f"  SKIP (no data): {out_name}")
        return

    fig, ax = plt.subplots(figsize=(5, 3.5))
    plot_sweep(ax, sub, dim_col, dim_ticks, dim_xlabels,
               "fill_rate", agg_fn="mean")
    ax.axhline(1.0, color="gray", linestyle="--", linewidth=0.8, label="window fully used")
    ax.set_ylim(0, 1.15)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Mean in_flight / cwnd")
    ax.set_title(f"Window fill rate ({part})\n"
                 "(≈1 → CC limits throughput; <1 → flow limited / light load)")
    ax.legend(fontsize=7)
    fig.tight_layout()
    outpath = PLOT_DIR / out_name
    fig.savefig(outpath)
    plt.close(fig)
    print(f"  Saved {outpath}")


# ── Plot A6/B6: cwnd time-series ──────────────────────────────────────────────
def plot_cwnd_timeseries(cwnd: pd.DataFrame, part: str,
                         dim_col: str, dim_values, dim_label: str,
                         out_name: str):
    """
    Single representative run: pureperm_8mb, seed=42, sev=4.
    One line per dim_value.
    """
    sub = cwnd[
        (cwnd["part"] == part) &
        (cwnd["workload"] == "pureperm_8mb") &
        (cwnd["seed"] == 42) &
        (cwnd["sev"] == 4)
    ]
    if sub.empty:
        print(f"  SKIP (no data): {out_name}")
        return

    cmap = plt.cm.viridis
    n = len(dim_values)

    fig, ax = plt.subplots(figsize=(6, 3.5))
    for idx, dv in enumerate(dim_values):
        s = sub[sub[dim_col] == dv].sort_values("time_us")
        if s.empty:
            continue
        color = cmap(idx / max(n - 1, 1))
        label = f"{dim_label}={dv}" if dv != 1024 else f"{dim_label}=∞"
        ax.plot(s["time_us"], s["cwnd_pkts"], color=color, label=label,
                linewidth=0.8, alpha=0.85)

    ax.axvline(50, color="red", linestyle="--", linewidth=0.8, label="failure t=50µs")
    ax.axvline(200, color="orange", linestyle="--", linewidth=0.8, label="recovery t=200µs")
    ax.set_xlabel("Simulation time (µs)")
    ax.set_ylabel("cwnd (packets)")
    ax.set_title(f"CC window dynamics — pureperm_8mb, seed=42, sev=4 ({part})")
    ax.legend(fontsize=6, ncol=2)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    outpath = PLOT_DIR / out_name
    fig.savefig(outpath)
    plt.close(fig)
    print(f"  Saved {outpath}")


# ── Plot A7/B7: per-flow goodput (network utilisation) ────────────────────────
WORKLOAD_ORDER   = ["pureperm_8mb", "perm_32mb", "perm_128mb", "composite"]
WORKLOAD_COLORS  = {"pureperm_8mb": "#1565C0", "perm_32mb": "#2E7D32",
                    "perm_128mb": "#6A1B9A", "composite": "#E65100"}
WORKLOAD_MARKERS = {"pureperm_8mb": "o", "perm_32mb": "s",
                    "perm_128mb": "^", "composite": "D"}
LINK_RATE_GBPS   = 400.0

def plot_goodput(fct: pd.DataFrame, part: str,
                 dim_col: str, dim_ticks, dim_xlabels,
                 xlabel: str, out_name: str):
    """
    Two-panel figure (sev=0 left, sev=4 right).
    Each panel: mean per-flow goodput (Gbps) vs dim, one line per workload.
    95% CI across seeds.

    goodput_Gbps = flow_size_bytes * 8 / fct_us * 1e-3
    Mice flows (composite) are plotted on a secondary y-axis to keep scale readable.
    """
    sub = fct[fct["part"] == part].copy()
    # Exclude mice flows from composite: their FCT ≈ base RTT regardless of size,
    # making goodput = size/RTT >> link rate and the metric meaningless.
    # FCT slowdown (A3/B3) already covers mice performance.
    sub = sub[~((sub["workload"] == "composite") & (sub["flow_class"] == "mice"))].copy()
    sub["goodput_gbps"] = sub["size"] * 8 / sub["fct_us"] * 1e-3

    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=False)

    for ax, sev in zip(axes, [0, 4]):
        s = sub[sub["sev"] == sev]

        # Separate composite-mice (tiny goodput) from large flows
        large_wls = [w for w in WORKLOAD_ORDER if w != "composite"]
        ax2 = ax.twinx()  # secondary axis for composite mice

        for wl in WORKLOAD_ORDER:
            ws = s[s["workload"] == wl]
            if ws.empty:
                continue
            means, herrs = [], []
            for dv in dim_ticks:
                vals = ws[ws[dim_col] == dv].groupby("seed")["goodput_gbps"].mean()
                m, h = ci95(vals.values)
                means.append(m); herrs.append(h)

            herrs_safe = [0.0 if (v is None or (isinstance(v, float) and np.isnan(v))) else v for v in herrs]
            means_safe = [np.nan if (v is None or (isinstance(v, float) and np.isnan(v))) else v for v in means]

            target_ax = ax2 if wl == "composite" else ax
            target_ax.errorbar(
                range(len(dim_ticks)), means_safe, yerr=herrs_safe,
                label=wl,
                color=WORKLOAD_COLORS[wl],
                marker=WORKLOAD_MARKERS[wl],
                capsize=3, linewidth=1.5,
                linestyle="--" if wl == "composite" else "-",
            )

        ax.axhline(LINK_RATE_GBPS, color="black", linestyle=":", linewidth=1.0,
                   label=f"line rate ({LINK_RATE_GBPS:.0f} Gbps)")
        ax.set_xticks(range(len(dim_ticks)))
        ax.set_xticklabels(dim_xlabels)
        ax.set_xlabel(xlabel)
        ax.set_ylabel("Mean per-flow goodput (Gbps)", fontsize=8)
        ax2.set_ylabel("composite goodput (Gbps)", fontsize=7, color=WORKLOAD_COLORS["composite"])
        ax2.tick_params(axis="y", labelcolor=WORKLOAD_COLORS["composite"], labelsize=7)
        ax.set_ylim(0, LINK_RATE_GBPS * 1.08)
        ax.set_title(f"sev={sev}", fontsize=9)
        ax.grid(axis="y", alpha=0.3)

        # Combined legend (primary axis only, composite noted as dashed)
        handles, labels = ax.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax.legend(handles + h2, labels + l2, fontsize=6, ncol=2)

    fig.suptitle(f"Per-flow network utilisation ({part})\n"
                 "(goodput = flow_size/FCT; line rate = 400 Gbps; "
                 "composite = elephant+incast only, mice excluded — see A3/B3)", fontsize=8)
    fig.tight_layout()
    outpath = PLOT_DIR / out_name
    fig.savefig(outpath)
    plt.close(fig)
    print(f"  Saved {outpath}")


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print("Loading CSVs …")
    try:
        fct, cwnd, events = load_data()
    except FileNotFoundError as e:
        print(f"ERROR: {e}\nRun v4_aggregate.py first.", file=sys.stderr)
        sys.exit(1)

    print(f"  fct: {len(fct)} rows | cwnd: {len(cwnd)} rows | events: {len(events)} rows")

    # ── Part A plots ──────────────────────────────────────────────────────────
    print("\n=== Part A: buffer sweep ===")

    plot_fct_slowdown(fct, "partA", "pureperm_8mb", "all",
                      "buf", BUF_TICKS, BUF_XLABELS,
                      "REPS buffer size", "A1_fct_p99_slowdown_pureperm_buf.png")

    plot_fct_slowdown(fct, "partA", "perm_128mb", "all",
                      "buf", BUF_TICKS, BUF_XLABELS,
                      "REPS buffer size", "A2_fct_p99_slowdown_perm128mb_buf.png")

    plot_fct_slowdown(fct, "partA", "composite", "incast",
                      "buf", BUF_TICKS, BUF_XLABELS,
                      "REPS buffer size", "A3_fct_p99_slowdown_composite_incast_buf.png")

    plot_cwnd_bdp(cwnd, "partA",
                  "buf", BUF_TICKS, BUF_XLABELS,
                  "REPS buffer size", "A4_cwnd_bdp_buf.png")

    plot_fill_rate(cwnd, "partA",
                   "buf", BUF_TICKS, BUF_XLABELS,
                   "REPS buffer size", "A5_fill_rate_buf.png")

    plot_cwnd_timeseries(cwnd, "partA",
                         "buf", BUF_TICKS, "buf",
                         "A6_cwnd_timeseries_buf.png")

    plot_goodput(fct, "partA",
                 "buf", BUF_TICKS, BUF_XLABELS,
                 "REPS buffer size", "A7_goodput_utilisation_buf.png")

    # ── Part B plots ──────────────────────────────────────────────────────────
    print("\n=== Part B: EV domain sweep ===")

    plot_fct_slowdown(fct, "partB", "pureperm_8mb", "all",
                      "ev_domain", EV_TICKS, EV_XLABELS,
                      "EV domain size", "B1_fct_p99_slowdown_pureperm_ev.png")

    plot_fct_slowdown(fct, "partB", "perm_128mb", "all",
                      "ev_domain", EV_TICKS, EV_XLABELS,
                      "EV domain size", "B2_fct_p99_slowdown_perm128mb_ev.png")

    plot_fct_slowdown(fct, "partB", "composite", "incast",
                      "ev_domain", EV_TICKS, EV_XLABELS,
                      "EV domain size", "B3_fct_p99_slowdown_composite_incast_ev.png")

    plot_cwnd_bdp(cwnd, "partB",
                  "ev_domain", EV_TICKS, EV_XLABELS,
                  "EV domain size", "B4_cwnd_bdp_ev.png")

    plot_fill_rate(cwnd, "partB",
                   "ev_domain", EV_TICKS, EV_XLABELS,
                   "EV domain size", "B5_fill_rate_ev.png")

    plot_cwnd_timeseries(cwnd, "partB",
                         "ev_domain", EV_TICKS, "ev",
                         "B6_cwnd_timeseries_ev.png")

    plot_goodput(fct, "partB",
                 "ev_domain", EV_TICKS, EV_XLABELS,
                 "EV domain size", "B7_goodput_utilisation_ev.png")

    print(f"\nAll plots written to {PLOT_DIR}")


if __name__ == "__main__":
    main()
