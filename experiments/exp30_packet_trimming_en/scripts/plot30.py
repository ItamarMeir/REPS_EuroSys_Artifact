#!/usr/bin/env python3
"""
exp30 static plots. Reuses exp28 plot_sweep helpers (style_for, _plot_lines,
_plot_bars, _legend, _yerr). Iterates whatever (part, size, ef) slices are
present in data/{fct,diagnostics}.csv, so it works on a partial matrix.

Emits to plots/:
  fct_vs_severity__s<size>.png          (+ _bars)   part a1
  fct_vs_ratio__s<size>.png             (+ _bars)   part a2
  fct_vs_kill__s<size>.png              (+ _bars)   part b (static real kill)
  diagnostics_vs_severity__s<size>.png              part a1
  diagnostics_vs_kill__s<size>.png                  part b
  best_worst__<part>_s<size>.png                    a1 / b envelopes
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(EXP_DIR.parent / "exp28_link_degradation_sweep" / "scripts"))
import plot_sweep  # noqa: E402
from plot_sweep import (  # noqa: E402
    _legend, _plot_bars, _plot_lines, style_for)

style_for_orig = style_for


DATA = EXP_DIR / "data"
PLOTS = EXP_DIR / "plots"
PLOTS.mkdir(exist_ok=True)

FCT_4 = [("p50_fct_us", "p50 FCT (us)"), ("p95_fct_us", "p95 FCT (us)"),
         ("p99_fct_us", "p99 FCT (us)"), ("max_fct_us", "max FCT (us)")]
DIAG_6 = [("ecn_per_host", "ECN acks / host"), ("rto_per_host", "RTOs / host"),
          ("freeze_entries_per_host", "freeze entries / host"),
          ("freeze_us_mean", "time in freezing (us)"),
          ("ev_random_per_host", "random-EV draws / host"),
          ("ev_random_rate", "random-EV rate (draws / pkt)")]

XLAB = {"a1": "# degraded ToR0 uplinks  (severity = n/32)",
        "a2": "link degradation (%)  -- 8 fixed ToR0 uplinks",
        "b": "# ToR0 uplinks permanently killed, F  (severity = F/32, static)"}


# Legend: label every arm with its CC so MPRDMA and NSCC rows are distinguishable.
# Colour follows B (same viridis ladder as exp28); MPRDMA = hollow circle,
# NSCC = filled square, dual-window = hollow triangle.
_CC_LABEL = {"mprdma": "MPRDMA", "nscc": "NSCC",
             "dual_mprdma_reps": "dual-window MPRDMA", "dual_mprdma_reps_cap": "dual-window MPRDMA (cap)"}
_CC_ORDER = ["mprdma", "nscc", "dual_mprdma_reps", "dual_mprdma_reps_cap"]


def style30(arm):
    b = _buf_size(arm)
    cc = _cc(arm)
    base = style_for_orig(f"reps_b{b}")
    if cc == "nscc":
        # NSCC gets its own colour ramp (magma) so it never shares a colour with
        # the MPRDMA viridis ladder at the same B; same B ordering, light->dark.
        i = [1, 2, 4, 8, 16, 32].index(b)
        base = dict(base, color=plt.get_cmap("magma")(0.15 + 0.6 * i / 5))
    marker = {"mprdma": "o", "nscc": "s", "dual_mprdma_reps": "^",
              "dual_mprdma_reps_cap": "^"}[cc]
    filled = cc == "nscc"
    return dict(color=base["color"], marker=marker, filled=filled,
                label=f"REPS B={b} ({_CC_LABEL[cc]})")


plot_sweep.style_for = style30   # shared helpers look up style_for at call time


def _buf_size(arm):
    return int(re.match(r"reps_b(\d+)", arm).group(1))


def _cc(arm):
    for suf, cc in (('_dual_cap', 'dual_mprdma_reps_cap'), ('_dual', 'dual_mprdma_reps'), ('_nscc', 'nscc')):
        if arm.endswith(suf):
            return cc
    return 'mprdma'


def _arms(df):
    arms = sorted(df.arm.unique(), key=lambda a: (_CC_ORDER.index(_cc(a)), _buf_size(a)))
    return list(arms)


def _grid(slc, panels, xlab, title, path, *, bars=False, logy=False):
    arms = _arms(slc)
    n = len(panels)
    ncol = 2 if n <= 4 else 3
    nrow = -(-n // ncol)
    fig, axes = plt.subplots(nrow, ncol, figsize=(5.4 * ncol, 3.9 * nrow), squeeze=False)
    axes = axes.ravel()
    xvals = sorted(slc.x.unique())
    for ax, (col, lab) in zip(axes, panels):
        if col not in slc.columns:
            ax.set_visible(False)
            continue
        if bars:
            _plot_bars(ax, slc, col, arms, xvals)
        else:
            _plot_lines(ax, slc, col, arms, logy=logy)
        ax.set_title(lab, fontsize=11)
        ax.set_xlabel(xlab, fontsize=9)
    for ax in axes[n:]:
        ax.set_visible(False)
    fig.suptitle(title, fontsize=13, y=1.0)
    _legend(fig, arms, bars=bars)
    fig.tight_layout(rect=(0, 0.05, 1, 0.98))
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)
    print("wrote", path.name)


def _best_worst(slc, col, xlab, title, path):
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    lo = slc.loc[slc.groupby("x")[col].idxmin()].sort_values("x")
    hi = slc.loc[slc.groupby("x")[col].idxmax()].sort_values("x")
    ax.fill_between(lo.x, lo[col], hi[col], alpha=0.18, color="#21918c")
    for d, mk, lb in ((lo, "o", "best B"), (hi, "s", "worst B")):
        ax.plot(d.x, d[col], mk + "-", color="#21918c" if lb == "best B" else "#440154",
                lw=2, ms=7, label=lb)
        for _, r in d.iterrows():
            ax.annotate(f"B{int(r.buf_size)}", (r.x, r[col]), fontsize=7,
                        textcoords="offset points", xytext=(0, 6 if lb == "best B" else -12),
                        ha="center")
    ax.set_xlabel(xlab)
    ax.set_ylabel(col)
    ax.set_title(title, fontsize=12)
    ax.grid(True, ls=":", lw=0.7, alpha=0.7)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    print("wrote", path.name)


def main() -> None:
    fct = pd.read_csv(DATA / "fct.csv")
    diag = pd.read_csv(DATA / "diagnostics.csv")
    aff = lambda d: d[d.group == "affected"]

    for size, g in aff(fct).groupby("size"):
        a1 = g[g.part == "a1"]
        if not a1.empty:
            _grid(a1, FCT_4, XLAB["a1"], f"exp30-trim-en A1 -- FCT vs severity ({size//1048576} MiB)",
                  PLOTS / f"fct_vs_severity__s{size}.png")
            _grid(a1, FCT_4, XLAB["a1"], f"exp30-trim-en A1 -- FCT vs severity ({size//1048576} MiB)",
                  PLOTS / f"fct_vs_severity__s{size}_bars.png", bars=True)
            _best_worst(a1, "p99_fct_us", XLAB["a1"],
                        f"exp30-trim-en A1 p99 FCT best/worst B ({size//1048576} MiB)",
                        PLOTS / f"best_worst__a1_s{size}.png")
        a2 = g[g.part == "a2"]
        if not a2.empty:
            _grid(a2, FCT_4, XLAB["a2"], f"exp30-trim-en A2 -- FCT vs degradation ({size//1048576} MiB)",
                  PLOTS / f"fct_vs_ratio__s{size}.png")
            _grid(a2, FCT_4, XLAB["a2"], f"exp30-trim-en A2 -- FCT vs degradation ({size//1048576} MiB)",
                  PLOTS / f"fct_vs_ratio__s{size}_bars.png", bars=True)
        b = g[g.part == "b"]
        if not b.empty:
            _grid(b, FCT_4, XLAB["b"], f"exp30-trim-en B -- FCT vs static real kill ({size//1048576} MiB)",
                  PLOTS / f"fct_vs_kill__s{size}.png", logy=True)
            _grid(b, FCT_4, XLAB["b"], f"exp30-trim-en B -- FCT vs static real kill ({size//1048576} MiB)",
                  PLOTS / f"fct_vs_kill__s{size}_bars.png", bars=True)
            _best_worst(b, "p99_fct_us", XLAB["b"],
                        f"exp30-trim-en B p99 FCT best/worst B ({size//1048576} MiB)",
                        PLOTS / f"best_worst__b_s{size}.png")

    for size, g in aff(diag).groupby("size"):
        a1 = g[g.part == "a1"]
        if not a1.empty:
            _grid(a1, DIAG_6, XLAB["a1"],
                  f"exp30-trim-en A1 -- diagnostics vs severity ({size//1048576} MiB)",
                  PLOTS / f"diagnostics_vs_severity__s{size}.png")
        b = g[g.part == "b"]
        if not b.empty:
            _grid(b, DIAG_6, XLAB["b"],
                  f"exp30-trim-en B -- diagnostics vs static real kill ({size//1048576} MiB)",
                  PLOTS / f"diagnostics_vs_kill__s{size}.png")


if __name__ == "__main__":
    main()
