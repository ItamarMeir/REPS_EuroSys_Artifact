#!/usr/bin/env python3
"""
exp31 static plots. Reuses exp28 plot_sweep style_for.

  cct_by_scenario.png   grouped bars, x=scenario, bar/arm, log-y, censored hatched
  cct_pct.png           CCT / healthy-CCT, same layout
  knee.png              CCT vs B (1,2,4) per scenario, CI bars -- the b1->b2 knee
  steps.png             per-ring-step FCT series, healthy vs a failing scenario
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(EXP_DIR.parent / "exp28_link_degradation_sweep" / "scripts"))
from plot_sweep import style_for  # noqa: E402

DATA = EXP_DIR / "data"
PLOTS = EXP_DIR / "plots"
PLOTS.mkdir(exist_ok=True)
BS = [1, 2, 4]


def _order(df):
    scs = [s for s in ["healthy"] + sorted(x for x in df.scenario.unique()
                                           if x != "healthy")]
    return scs


def cct_bars(cct, col, title, fname, *, logy=True, ylab="CCT (us)"):
    scs = _order(cct)
    xi = np.arange(len(scs))
    bw = 0.26
    fig, ax = plt.subplots(figsize=(max(9, len(scs) * 0.95), 5))
    for j, b in enumerate(BS):
        s = cct[cct.buf_size == b].set_index("scenario")
        vals = [s[col].get(sc, np.nan) for sc in scs]
        cis = [s.get("cct_us_ci", pd.Series()).get(sc, 0) if col == "cct_us" else 0
               for sc in scs]
        cens = [bool(s.get("censored", pd.Series()).get(sc, False)) for sc in scs]
        st = style_for(f"reps_b{b}")
        bars = ax.bar(xi + (j - 1) * bw, vals, bw, yerr=cis, capsize=2,
                      color=st["color"], edgecolor="black", lw=0.4,
                      label=f"B={b}")
        for rect, c in zip(bars, cens):
            if c:
                rect.set_hatch("xxx")
    if logy:
        ax.set_yscale("log")
    ax.set_xticks(xi)
    ax.set_xticklabels(scs, rotation=35, ha="right", fontsize=8)
    ax.set_ylabel(ylab)
    ax.set_title(title + "   (hatched = ring did not complete, CCT censored at -end)",
                 fontsize=11)
    ax.grid(True, axis="y", ls=":", lw=0.7, alpha=0.7)
    ax.legend(frameon=False, ncol=3)
    fig.tight_layout()
    fig.savefig(PLOTS / fname, dpi=110)
    plt.close(fig)
    print("wrote", fname)


def knee(cct):
    scs = _order(cct)
    n = len(scs)
    ncol = 4
    nrow = -(-n // ncol)
    fig, axes = plt.subplots(nrow, ncol, figsize=(3.5 * ncol, 3.0 * nrow), squeeze=False)
    axes = axes.ravel()
    for ax, sc in zip(axes, scs):
        s = cct[cct.scenario == sc].set_index("buf_size")
        ys = [s.cct_us.get(b, np.nan) for b in BS]
        es = [s.cct_us_ci.get(b, 0) for b in BS]
        ax.errorbar(BS, ys, yerr=es, fmt="o-", color="#21918c", lw=2, ms=7, capsize=3)
        ax.set_title(sc, fontsize=9)
        ax.set_xticks(BS)
        ax.set_xlabel("B")
        ax.set_yscale("log")
        ax.grid(True, which="both", ls=":", lw=0.6, alpha=0.7)
    for ax in axes[n:]:
        ax.set_visible(False)
    fig.suptitle("exp31 -- ring CCT vs buffer size B  (log y; the b1->b2 knee)", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(PLOTS / "knee.png", dpi=110)
    plt.close(fig)
    print("wrote knee.png")


CHAIN_LEN = 31   # 2*RING_RANKS-1; the .cm is 16 serially-dependent chains of 31 hops


def steps(st):
    # flowId order in the .cm is chain-major: ids 1..31 = chain 0, 32..62 = chain 1, ...
    # Fold onto hop = (step-1) % CHAIN_LEN and average the 16 chains, so a stall that
    # recurs at the same ring position shows as a hump instead of being smeared out.
    scs = [s for s in ["healthy", "fail_one_cable", "degrade_one_cable",
                       "5_percent_failed_cables"] if s in st.scenario.unique()]
    fig, axes = plt.subplots(len(scs), 1, figsize=(11, 2.6 * len(scs)), squeeze=False)
    for ax, sc in zip(axes.ravel(), scs):
        for b in BS:
            s = st[(st.scenario == sc) & (st.arm == f"reps_b{b}")].copy()
            if s.empty:
                continue
            s["hop"] = (s.step - 1) % CHAIN_LEN
            g = s.groupby("hop").fct_mean_us
            m, sd = g.mean(), g.std()
            c = style_for(f"reps_b{b}")["color"]
            ax.plot(m.index, m.values, lw=1.4, color=c, label=f"B={b}")
            ax.fill_between(m.index, (m - sd).clip(lower=0), m + sd, color=c, alpha=0.12)
        ax.set_title(sc, fontsize=10)
        ax.set_ylabel("hop FCT (us)")
        ax.set_yscale("log")
        ax.grid(True, ls=":", lw=0.6, alpha=0.7)
        ax.legend(frameon=False, ncol=3, fontsize=8)
    axes.ravel()[-1].set_xlabel("ring hop position  (step-1 mod 31; band = +/-1 sd over the 16 chains)")
    fig.suptitle("exp31 -- FCT vs ring-hop position: flat = healthy, a recurring "
                 "mid-ring hump = cyclic congestion",
                 fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(PLOTS / "steps.png", dpi=110)
    plt.close(fig)
    print("wrote steps.png")


def main():
    cct = pd.read_csv(DATA / "cct.csv")
    st = pd.read_csv(DATA / "steps.csv")
    cct_bars(cct, "cct_us", "exp31 -- ring all-reduce CCT by failure scenario",
             "cct_by_scenario.png")
    cct_bars(cct, "cct_pct_of_healthy",
             "exp31 -- CCT as % of healthy (capacity-first framing)",
             "cct_pct.png", logy=True, ylab="CCT / healthy CCT  (%)")
    knee(cct)
    steps(st)


if __name__ == "__main__":
    main()
