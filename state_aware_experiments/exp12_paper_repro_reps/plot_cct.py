#!/usr/bin/env python3
"""
plot_cct.py — CCT-inflation bar charts for Figs 4, 6–12, 14.

Usage:
  python3 plot_cct.py              # all figures
  python3 plot_cct.py --fig 4 6   # subset

Reads: data/cct.csv   (produced by aggregate.py)
Writes: plots/fig{N}_cct.png
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

EXP_DIR  = Path(__file__).parent
DATA_DIR = EXP_DIR / "data"
PLOTS_DIR = EXP_DIR / "plots"
PLOTS_DIR.mkdir(exist_ok=True)

# ── Color palette (roughly matches paper style) ───────────────────────────────
CCA_COLORS = {
    "swift":  "#f5a623",   # orange/yellow
    "lswift": "#e06020",   # orange
    "mswift": "#27ae60",   # green
    "nscc":   "#2980b9",   # blue
    "mnscc":  "#c0392b",   # red
}
CCA_LABELS = {
    "swift":  "Swift",
    "lswift": "LSwift",
    "mswift": "MSwift (P50)",
    "nscc":   "NSCC",
    "mnscc":  "MNSCC",
}

# ── Fig-specific layout ───────────────────────────────────────────────────────
FIG_CONFIGS = {
    "fig4":  dict(title="Fig 4 — Baseline (4 eleph + 124×8MB), 128 nodes, 800 Gbps",
                  ccas=["swift","lswift","mswift","nscc","mnscc"], log_y=True),
    "fig6":  dict(title="Fig 6 — Pure permutation (128×8MB), 128 nodes, 800 Gbps",
                  ccas=["lswift","mswift","nscc","mnscc"], log_y=False),
    "fig7":  dict(title="Fig 7 — HSDP ring flows, 128 nodes, 800 Gbps",
                  ccas=["lswift","mswift","nscc","mnscc"], log_y=False),
    "fig8":  dict(title="Fig 8 — Pure permutation (250×8MB), 250 nodes, 400 Gbps",
                  ccas=["lswift","mswift","nscc","mnscc"], log_y=False),
    "fig9":  dict(title="Fig 9 — Baseline 16 MB flows, 128 nodes, 800 Gbps",
                  ccas=["lswift","mswift","nscc","mnscc"], log_y=False),
    "fig10": dict(title="Fig 10 — Baseline 8-elephant variant, 128 nodes, 800 Gbps",
                  ccas=["lswift","mswift","nscc","mnscc"], log_y=False),
    "fig11": dict(title="Fig 11 — Baseline + 1% failed links, 128 nodes, 800 Gbps",
                  ccas=["lswift","mswift","nscc","mnscc"], log_y=False),
    "fig12": None,   # special: percentile sweep
    "fig14": dict(title="Fig 14 — Incast 32→1, 8 MB flows, 128 nodes, 800 Gbps",
                  ccas=["lswift","mswift","nscc","mnscc"], log_y=False),
}

def plot_cct_bar(fig_key: str, df_fig: pd.DataFrame, cfg: dict):
    ccas = cfg["ccas"]
    title = cfg["title"]
    log_y = cfg.get("log_y", False)

    # Filter to requested CCAs and compute mean ± CI
    rows = df_fig[df_fig["cc"].isin(ccas)].copy()
    if rows.empty:
        print(f"[{fig_key}] No data — skipping.")
        return

    x = np.arange(len(ccas))
    means, ci95s = [], []
    for cc in ccas:
        r = rows[rows["cc"] == cc]
        if r.empty:
            means.append(0); ci95s.append(0)
        else:
            means.append(float(r["mean_cct_pct"].iloc[0]))
            ci95s.append(float(r["ci95"].fillna(0).iloc[0]))

    fig, ax = plt.subplots(figsize=(7, 4))
    bars = ax.bar(x, means, yerr=ci95s, capsize=4,
                  color=[CCA_COLORS.get(c, "#888") for c in ccas],
                  edgecolor="black", linewidth=0.7, error_kw={"elinewidth": 1.2})
    ax.set_xticks(x)
    ax.set_xticklabels([CCA_LABELS.get(c, c) for c in ccas], fontsize=10)
    ax.set_ylabel("CCT Inflation (%)", fontsize=11)
    ax.set_title(title, fontsize=10, pad=8)
    if log_y:
        ax.set_yscale("log")
        ax.set_ylabel("CCT Inflation (%, log scale)", fontsize=11)
        valid = [m for m in means if m > 0]
        if valid:
            ax.set_ylim(bottom=max(0.5, min(valid) * 0.5),
                        top=max(valid) * 3.0)
    else:
        ax.set_ylim(bottom=0, top=max(means) * 1.35 if any(m > 0 for m in means) else 10)

    # Annotate bars with values
    for bar, mean in zip(bars, means):
        if mean > 0:
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() * 1.05,
                    f"{mean:.0f}%", ha="center", va="bottom", fontsize=8)
    plt.tight_layout()
    outpath = PLOTS_DIR / f"{fig_key}_cct.png"
    plt.savefig(outpath, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[plot] Saved {outpath.name}")


def plot_fig12(df_fig12: pd.DataFrame):
    """Fig 12: MSwift P10/P50/P90 side-by-side."""
    if df_fig12.empty:
        print("[fig12] No data — skipping.")
        return

    pcts = ["10","50","90"]
    pct_labels = ["P10","P50","P90"]
    pct_colors = ["#3498db","#27ae60","#e74c3c"]

    x = np.arange(len(pcts))
    means, ci95s = [], []
    for pct in pcts:
        r = df_fig12[df_fig12["pct"] == pct]
        if r.empty:
            means.append(0); ci95s.append(0)
        else:
            means.append(float(r["mean_cct_pct"].iloc[0]))
            ci95s.append(float(r["ci95"].fillna(0).iloc[0]))

    fig, ax = plt.subplots(figsize=(5, 4))
    bars = ax.bar(x, means, yerr=ci95s, capsize=4,
                  color=pct_colors, edgecolor="black", linewidth=0.7,
                  error_kw={"elinewidth": 1.2})
    ax.set_xticks(x)
    ax.set_xticklabels(pct_labels, fontsize=11)
    ax.set_ylabel("CCT Inflation (%)", fontsize=11)
    ax.set_title("Fig 12 — MSwift percentile sweep (P10/P50/P90)", fontsize=10, pad=8)
    for bar, mean in zip(bars, means):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() * 1.03,
                f"{mean:.0f}%", ha="center", va="bottom", fontsize=9)
    ax.set_ylim(bottom=0)
    plt.tight_layout()
    outpath = PLOTS_DIR / "fig12_cct.png"
    plt.savefig(outpath, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[plot] Saved {outpath.name}")


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fig", nargs="*", type=str, default=None,
                        help="Figure numbers to plot (e.g. 4 6 12). Default: all.")
    args = parser.parse_args()

    csv_path = DATA_DIR / "cct.csv"
    if not csv_path.exists():
        print(f"[error] {csv_path} not found.  Run aggregate.py first.", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(csv_path, dtype={"pct": str})
    df["pct"] = df["pct"].fillna("").astype(str)

    requested = set(args.fig) if args.fig else None

    for fig_key, cfg in FIG_CONFIGS.items():
        fig_num = fig_key.replace("fig", "")
        if requested and fig_num not in requested and fig_key not in requested:
            continue

        df_fig = df[df["fig"] == fig_key]

        if fig_key == "fig12":
            df12 = df_fig[df_fig["cc"] == "mswift"]
            plot_fig12(df12)
        elif cfg is not None:
            plot_cct_bar(fig_key, df_fig, cfg)

if __name__ == "__main__":
    main()
