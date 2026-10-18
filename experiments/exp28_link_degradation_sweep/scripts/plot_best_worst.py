#!/usr/bin/env python3
"""
exp28 best/worst-B envelope figures — per metric, per X value, which REPS
buffer size B is best (min) and which is worst (max). Every exp28 metric is
lower-is-better (FCT stats, ECN/RTO/freeze/random-EV rate), so this is
unambiguous. The winning B can (and does) change across X -- this is a min/max
envelope across the full B ladder, not two fixed B series -- so each
point/bar is annotated with the B that achieved it.

    python3 plot_best_worst.py --part 1
    python3 plot_best_worst.py --part 2

Reuses plot_sweep.py's load()/agg_ci()/x_of()/XLABEL (same CSVs, same 95% CI
across seeds where the seed-43/44 subset exists). Writes
plots/part<N>/best_worst/{fct_stats,diagnostics}{,_bars}.png.
"""
from __future__ import annotations

import argparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from plot_sweep import EXP_DIR, METRIC_COLS, XLABEL, _yerr, agg_ci, load

BEST = dict(color="#1b9e5a", marker="o", label="Best B")
WORST = dict(color="#d1272d", marker="X", label="Worst B")

FCT_PANELS = [("max_fct_us", "Max FCT"), ("p99_fct_us", "p99 FCT"),
              ("fct_p95_us", "p95 FCT"), ("p50_fct_us", "Median FCT")]
DIAG_PANELS = [("ecn_per_host", "ECN-marked ACKs per host"),
               ("rto_per_host", "RTOs per host"),
               ("freeze_us_mean", "Time in freezing (µs)"),
               ("ev_random_rate", "Random-EV draw rate (random draws / pkt)")]


def envelope(df_agg: pd.DataFrame, col: str) -> pd.DataFrame:
    """One row per x: best (min) / worst (max) value + CI + which B won it."""
    rows = []
    for x, g in df_agg.groupby("x"):
        g = g[g[col].notna()]
        if g.empty:
            continue
        b = g.loc[g[col].idxmin()]
        w = g.loc[g[col].idxmax()]
        rows.append(dict(x=x, best_val=b[col], best_ci=b[col + "_ci"],
                         best_b=int(b.buf_size), worst_val=w[col],
                         worst_ci=w[col + "_ci"], worst_b=int(w.buf_size)))
    return pd.DataFrame(rows).sort_values("x")


def _plot_lines(ax, df_agg, col, xvals):
    env = envelope(df_agg, col)
    for pfx, st in (("best", BEST), ("worst", WORST)):
        ax.errorbar(env.x, env[f"{pfx}_val"],
                    yerr=_yerr(env[f"{pfx}_val"], env[f"{pfx}_ci"]),
                    fmt="-" + st["marker"], color=st["color"], lw=2.2, ms=8,
                    mew=1.6, ecolor=st["color"], elinewidth=1.3, capsize=3,
                    label=st["label"])
        for _, r in env.iterrows():
            ax.annotate(f"B{int(r[f'{pfx}_b'])}", (r.x, r[f"{pfx}_val"]),
                        textcoords="offset points",
                        xytext=(0, 7 if pfx == "best" else -12),
                        fontsize=7, ha="center", color=st["color"])
    ax.set_xticks(xvals)
    ax.grid(True, which="both", ls=":", lw=0.7, alpha=0.7)


def _plot_bars(ax, df_agg, col, xvals):
    env = envelope(df_agg, col).set_index("x")
    xi = np.arange(len(xvals))
    bw = 0.38
    vmin, vmax = np.inf, -np.inf
    for j, (pfx, st) in enumerate((("best", BEST), ("worst", WORST))):
        vals = [env[f"{pfx}_val"].get(xv, np.nan) for xv in xvals]
        cis = [env[f"{pfx}_ci"].get(xv, 0.0) for xv in xvals]
        bs = [env[f"{pfx}_b"].get(xv, None) for xv in xvals]
        bars = ax.bar(xi + j * bw, vals, bw,
                      yerr=_yerr(np.nan_to_num(vals), cis), capsize=2,
                      error_kw=dict(elinewidth=1.0), color=st["color"],
                      edgecolor="black", lw=0.4, label=st["label"])
        for rect, b, v in zip(bars, bs, vals):
            if b is not None and np.isfinite(v):
                ax.annotate(f"B{int(b)}", (rect.get_x() + rect.get_width() / 2, v),
                            textcoords="offset points", xytext=(0, 3),
                            fontsize=7, ha="center")
        fin = [v for v in vals if np.isfinite(v)]
        if fin:
            vmin, vmax = min(vmin, min(fin)), max(vmax, max(fin))
    if np.isfinite(vmin):
        pad = (vmax - vmin) * 0.15 or abs(vmax) * 0.05 or 1
        ax.set_ylim(max(0, vmin - pad), vmax + pad)
    ax.set_xticks(xi + bw / 2)
    ax.set_xticklabels([str(v) for v in xvals], fontsize=9)
    ax.grid(True, axis="y", ls=":", lw=0.7, alpha=0.7)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", type=int, required=True, choices=[1, 2])
    args = ap.parse_args()
    part = args.part

    raw = load(part)
    raw = raw[raw.arm != "ops"]
    df = agg_ci(raw, METRIC_COLS)
    xvals = sorted(df.x.unique())
    outdir = EXP_DIR / "plots" / f"part{part}" / "best_worst"
    outdir.mkdir(parents=True, exist_ok=True)
    xl = XLABEL[part]
    tag = (f"exp28 part {part} best/worst B — tornado 16 MiB, "
           f"fat_tree_1024_1os_2t_400g, -paths 32, seed 42 (+43/44 at a "
           f"subset of X); best/worst chosen independently per metric per X")

    for kind in ("lines", "bars"):
        sfx = "" if kind == "lines" else "_bars"
        draw = _plot_lines if kind == "lines" else _plot_bars

        fig, axes = plt.subplots(2, 2, figsize=(12, 8.5),
                                 sharex=(kind == "lines"))
        for ax, (col, name) in zip(axes.ravel(), FCT_PANELS):
            draw(ax, df, col, xvals)
            ax.set_title(name, fontsize=11)
            ax.set_ylabel("µs", fontsize=10)
        for ax in axes[1]:
            ax.set_xlabel(xl, fontsize=10)
        fig.suptitle(tag, fontsize=10)
        h, l = axes[0, 0].get_legend_handles_labels()
        fig.legend(h, l, loc="lower center", ncol=2, fontsize=9,
                   frameon=False, bbox_to_anchor=(0.5, -0.02))
        fig.tight_layout(rect=(0, 0.05, 1, 0.95))
        fig.savefig(outdir / f"fct_stats{sfx}.png", dpi=150, bbox_inches="tight")
        plt.close(fig)

        fig, axes = plt.subplots(2, 2, figsize=(12, 8.5),
                                 sharex=(kind == "lines"))
        for ax, (col, name) in zip(axes.ravel(), DIAG_PANELS):
            draw(ax, df, col, xvals)
            ax.set_title(name, fontsize=10.5)
        for ax in axes[1]:
            ax.set_xlabel(xl, fontsize=10)
        fig.suptitle(tag, fontsize=10)
        h, l = axes[0, 0].get_legend_handles_labels()
        fig.legend(h, l, loc="lower center", ncol=2, fontsize=9,
                   frameon=False, bbox_to_anchor=(0.5, -0.02))
        fig.tight_layout(rect=(0, 0.05, 1, 0.95))
        fig.savefig(outdir / f"diagnostics{sfx}.png", dpi=150,
                    bbox_inches="tight")
        plt.close(fig)

    print(f"wrote {outdir}/{{fct_stats,diagnostics}}{{,_bars}}.png")


if __name__ == "__main__":
    main()
