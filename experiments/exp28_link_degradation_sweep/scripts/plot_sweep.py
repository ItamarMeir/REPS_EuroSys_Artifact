#!/usr/bin/env python3
"""
exp28 figures — FCT + diagnostics vs failure severity, one line per LB arm.

    python3 plot_sweep.py --part 1     # X = # degraded ToR->spine-0 links
    python3 plot_sweep.py --part 2     # X = degradation %

Reads:
  data/part<N>/summary.csv   (from exp26/scripts/aggregate.py — FCT max/p99/p50,
                              speedup_vs_ops_max)
  data/part<N>/metrics.csv   (from aggregate28.py — p95 FCT + diagnostics)
For --part 2 the 0 % point is pulled from data/part1/{summary,metrics}.csv
(condition "healthy").

Writes plots/part<N>/ in both line and grouped-bar form:
  fct_stats.png  / fct_stats_bars.png    2x2: Max / p99 / p95 / median FCT (us)
  diagnostics.png / diagnostics_bars.png 2x2: ECN/host, RTO/host, freeze time,
                                         random-EV draw rate
one series per REPS buffer B. NO OPS arm (excluded from exp28), so no speedup view.

Arm styling matches exp26/exp27: REPS B = viridis ramp + hollow marker cycled
`o D ^ v X P` (lines) / per-B hatch (bars). Single seed 42 -> no error bars.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd
from scipy import stats as sp_stats

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR = SCRIPT_DIR.parent

OPS_COLOR = "#d95f02"
B_LADDER = [1, 2, 4, 8, 16, 32]
B_SHAPES = ["o", "D", "^", "v", "X", "P", "*"]
B_HATCH = ["//", "\\\\", "xx", "..", "oo", "**", "++"]   # exp26/27 convention


def style_for(arm: str) -> dict:
    cmap = plt.get_cmap("viridis")
    if arm == "ops":
        return dict(color=OPS_COLOR, marker="s", filled=True, label="OPS")
    b = int(arm[len("reps_b"):])
    i = B_LADDER.index(b)
    return dict(color=cmap(i / (len(B_LADDER) - 1)), marker=B_SHAPES[i],
               filled=False, label=f"REPS B={b}")


def arm_order(df: pd.DataFrame) -> list[str]:
    bs = sorted(int(x) for x in pd.to_numeric(
        df.loc[df.arm != "ops", "buf_size"], errors="coerce").dropna().unique())
    return (["ops"] if (df.arm == "ops").any() else []) + [f"reps_b{b}" for b in bs]


def x_of(part: int, condition: str) -> float | None:
    if part == 1:
        if condition == "healthy":
            return 0
        m = re.fullmatch(r"asym(\d+)", condition)
        return int(m.group(1)) if m else None
    if condition == "healthy":
        return 0
    m = re.fullmatch(r"asym4_r(\d+)", condition)
    return int(m.group(1)) if m else None


METRIC_COLS = ("max_fct_us", "p99_fct_us", "p50_fct_us", "fct_p95_us",
               "speedup_vs_ops_max", "ecn_per_host", "rto_per_host",
               "freeze_entries_total", "freeze_us_mean", "ev_random_rate",
               "ev_random_per_host")


def load(part: int) -> pd.DataFrame:
    """One tidy frame, one row per (arm, x, seed): arm, buf_size, x, seed,
    <fct stats>, speedup_vs_ops_max, <diag>. Most (arm, x) have a single seed
    (42 only); the seed-43/44 subset points (see common28/run_part{1,2}.py
    --seed) add 2 more rows there for agg_ci() to build a 95% CI from."""
    def _read(p: int) -> pd.DataFrame:
        d = EXP_DIR / "data" / f"part{p}"
        s = pd.read_csv(d / "summary.csv")
        m = pd.read_csv(d / "metrics.csv")
        s = s.merge(m[["workload", "condition", "arm", "fct_p95_us",
                       "ecn_per_host", "rto_per_host", "freeze_entries_total",
                       "freeze_us_mean", "ev_random_rate", "ev_random_per_host"]],
                    on=["workload", "condition", "arm"], how="left")
        s["x"] = s.apply(lambda r: x_of(p, r.condition), axis=1)
        s["seed"] = (s["workload"].str.extract(r"_seed(\d+)_")[0]
                     .fillna(42).astype(int))
        return s[s.x.notna()]

    frames = [_read(part)]
    if part == 2:                      # borrow the 0 % (healthy) cell from part 1
        p1 = _read(1)
        frames.append(p1[p1.x == 0])   # carries its own seed column, matched below
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset=["arm", "x", "seed"], keep="first")
    for c in METRIC_COLS + ("buf_size",):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values(["x", "seed"])


def agg_ci(df: pd.DataFrame, cols) -> pd.DataFrame:
    """Collapse per-seed rows to one row per (arm, x): mean of each metric plus
    a 95% CI half-width (Student-t, n = seed count in that group). Groups with
    a single seed (the seed-42-only X points) get ci = 0 -- not an error, just
    no spread to estimate; ax.errorbar renders a 0-yerr point as a plain
    marker, so those points are visually unchanged."""
    g = df.groupby(["arm", "x"])   # sorted, stable group order shared by all aggs below
    out = g.agg(buf_size=("buf_size", "first"), n_seed=("seed", "nunique")).reset_index()
    for c in cols:
        mean = g[c].mean().reset_index(drop=True)
        std = g[c].std(ddof=1).reset_index(drop=True)
        n = g[c].count().reset_index(drop=True)
        ci = np.where(n >= 2, sp_stats.t.ppf(0.975, (n - 1).clip(lower=1))
                     * std.fillna(0) / np.sqrt(n.clip(lower=1)), 0.0)
        out[c] = mean
        out[c + "_ci"] = ci
    return out


XLABEL = {1: "# degraded ToR→spine-0 links",
          2: "Link degradation (%)  — 4 fixed ToR→spine-0 links"}


def _yerr(vals, ci):
    """Asymmetric error: clip the lower whisker at 0 — every metric here (FCT,
    ECN/RTO counts, freeze µs, EV rate) is non-negative, so a symmetric t-CI
    on a near-zero mean must not draw a physically impossible negative bar."""
    ci = np.asarray(ci, float)
    return np.vstack([np.minimum(ci, np.asarray(vals, float)), ci])


def _plot_lines(ax, df, col, arms, *, logy=False):
    """df must carry `col` (mean) and `col + '_ci'` (95% half-width, 0 where
    only 1 seed exists — renders as a plain marker, no visible bar)."""
    for arm in arms:
        s = df[df.arm == arm].sort_values("x")
        s = s[s[col].notna()]
        if s.empty:
            continue
        st = style_for(arm)
        ax.errorbar(s.x, s[col], yerr=_yerr(s[col], s[col + "_ci"]),
                    fmt=("-" if arm != "ops" else "--") + st["marker"],
                    color=st["color"], lw=2.2, ms=8, mew=1.6,
                    mfc=st["color"] if st["filled"] else "none",
                    mec=st["color"], ecolor=st["color"], elinewidth=1.3,
                    capsize=3, zorder=5 if arm == "ops" else 3)
    ax.set_xticks(sorted(df.x.unique()))
    if logy:
        ax.set_yscale("log")
    ax.grid(True, which="both", ls=":", lw=0.7, alpha=0.7)


def _plot_bars(ax, df, col, arms, xvals):
    """Grouped bars: one group per x value, one bar per arm. y-axis clipped to
    the data range (bars are all near each other, a 0-based axis flattens them).
    `col + '_ci'` (0 where only 1 seed) drawn as an error bar on each bar."""
    xi = np.arange(len(xvals))
    bw = 0.82 / len(arms)
    vmin, vmax = np.inf, -np.inf
    for j, arm in enumerate(arms):
        s = df[df.arm == arm].set_index("x")
        vals = [s[col].get(xv, np.nan) for xv in xvals]
        cis = [s[col + "_ci"].get(xv, 0.0) for xv in xvals]
        st = style_for(arm)
        ax.bar(xi + j * bw, vals, bw, yerr=_yerr(np.nan_to_num(vals), cis),
               capsize=2,
               error_kw=dict(elinewidth=1.0), color=st["color"],
               hatch=B_HATCH[B_LADDER.index(int(re.match(r"reps_b(\d+)", arm).group(1))) % len(B_HATCH)],
               edgecolor="black", lw=0.4)
        fin = [v for v in vals if np.isfinite(v)]
        if fin:
            vmin, vmax = min(vmin, min(fin)), max(vmax, max(fin))
    if np.isfinite(vmin):
        pad = (vmax - vmin) * 0.12 or abs(vmax) * 0.05 or 1
        ax.set_ylim(max(0, vmin - pad), vmax + pad)
    ax.set_xticks(xi + 0.41 - bw / 2)
    ax.set_xticklabels([str(v) for v in xvals], fontsize=9)
    ax.grid(True, axis="y", ls=":", lw=0.7, alpha=0.7)


def _legend(fig, arms, *, bars=False):
    from matplotlib.patches import Patch
    if bars:
        h = [Patch(facecolor=style_for(a)["color"], edgecolor="black",
                   hatch=B_HATCH[B_LADDER.index(int(re.match(r"reps_b(\d+)", a).group(1))) % len(B_HATCH)],
                   label=style_for(a)["label"]) for a in arms]
        fig.legend(handles=h, loc="lower center", ncol=min(7, len(h)),
                   fontsize=9, frameon=False, bbox_to_anchor=(0.5, -0.02))
        return

    h = []
    for a in arms:
        st = style_for(a)
        h.append(Line2D([], [], color=st["color"], marker=st["marker"], lw=2,
                        ms=8, mfc=st["color"] if st["filled"] else "none",
                        mec=st["color"], mew=1.6, label=st["label"]))
    fig.legend(handles=h, loc="lower center", ncol=min(7, len(h)), fontsize=9,
               frameon=False, bbox_to_anchor=(0.5, -0.02))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", type=int, required=True, choices=[1, 2])
    args = ap.parse_args()
    part = args.part
    raw = load(part)
    raw = raw[raw.arm != "ops"]       # OPS excluded from exp28 entirely
    df = agg_ci(raw, METRIC_COLS)     # mean + 95% CI across seeds per (arm, x)
    arms = reps = arm_order(df)
    xvals = sorted(df.x.unique())
    outdir = EXP_DIR / "plots" / f"part{part}"
    outdir.mkdir(parents=True, exist_ok=True)
    xl = XLABEL[part]
    tag = (f"exp28 part {part} — tornado 16 MiB, fat_tree_1024_1os_2t_400g, "
           f"-paths 32, seed 42 (+43/44 at a subset of X, 95% CI where n=3)")

    FCT_PANELS = [("max_fct_us", "Max FCT"), ("p99_fct_us", "p99 FCT"),
                  ("fct_p95_us", "p95 FCT"), ("p50_fct_us", "Median FCT")]
    DIAG_PANELS = [("ecn_per_host", "ECN-marked ACKs per host"),
                   ("rto_per_host", "RTOs per host"),
                   ("freeze_us_mean", "Time in freezing (µs)"),
                   ("ev_random_rate", "Random-EV draw rate (random draws / pkt)")]

    for kind in ("lines", "bars"):
        sfx = "" if kind == "lines" else "_bars"
        draw = _plot_lines if kind == "lines" else \
            (lambda ax, d, c, a: _plot_bars(ax, d, c, a, xvals))

        # --- FCT ---
        fig, axes = plt.subplots(2, 2, figsize=(12, 8.5),
                                 sharex=(kind == "lines"))
        for ax, (col, name) in zip(axes.ravel(), FCT_PANELS):
            draw(ax, df, col, arms)
            ax.set_title(name, fontsize=11)
            ax.set_ylabel("µs", fontsize=10)
        for ax in axes[1]:
            ax.set_xlabel(xl, fontsize=10)
        fig.suptitle(tag, fontsize=10.5)
        _legend(fig, arms, bars=(kind == "bars"))
        fig.tight_layout(rect=(0, 0.06, 1, 0.96))
        fig.savefig(outdir / f"fct_stats{sfx}.png", dpi=150, bbox_inches="tight")
        plt.close(fig)

        # --- diagnostics ---
        fig, axes = plt.subplots(2, 2, figsize=(12, 8.5),
                                 sharex=(kind == "lines"))
        for ax, (col, name) in zip(axes.ravel(), DIAG_PANELS):
            draw(ax, df, col, arms)
            ax.set_title(name, fontsize=10.5)
        if kind == "lines":
            ax2 = axes[1, 0].twinx()
            for arm in reps:
                s = df[df.arm == arm].sort_values("x")
                ax2.plot(s.x, s.freeze_entries_total, ":",
                         color=style_for(arm)["color"], lw=1.2, alpha=0.6)
            ax2.set_ylabel("freeze entries (total, dotted)", fontsize=8)
        axes[1, 1].annotate("ev_explore ≡ 0 (freezes never auto-thaw, "
                            "-exit_freeze 200 µs > flow lifetime)",
                            xy=(0, -0.22), xycoords="axes fraction", fontsize=7.5)
        for ax in axes[1]:
            ax.set_xlabel(xl, fontsize=10)
        fig.suptitle(tag, fontsize=10.5)
        _legend(fig, arms, bars=(kind == "bars"))
        fig.tight_layout(rect=(0, 0.06, 1, 0.96))
        fig.savefig(outdir / f"diagnostics{sfx}.png", dpi=150,
                    bbox_inches="tight")
        plt.close(fig)

    print(f"wrote {outdir}/{{fct_stats,diagnostics}}{{,_bars}}.png")


if __name__ == "__main__":
    main()
