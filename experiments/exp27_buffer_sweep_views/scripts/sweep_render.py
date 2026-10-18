#!/usr/bin/env python3
"""
Shared 2-panel sweep renderer for exp27's BDP-sweep (plot 4 / F4) and
flow-size-sweep (plot 5 / F5) figures, in either ``lines`` or ``bars`` form.

Both fig2 (healthy) and fig4 (-failed) drivers call ``render_sweep`` — the only
differences are the x column, the condition set, and reference vlines.

frames : ordered dict {condition_label: DataFrame}. Each DataFrame must have the
         x column, ``arm``, ``max_fct_us``, ``speedup_vs_ops_max``.  The LAST
         condition is drawn solid / full-strength; earlier ones are faded.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np

from plot_micro_bars import OPS_COLOR, arm_style

# marker per REPS buffer B for the line form (OPS is always a filled square)
_SHAPES = ["o", "D", "^", "v", "X", "P", "*"]


def _shape(arm: str, bladder: list[int]) -> str:
    if arm == "ops":
        return "s"
    b = int(arm[len("reps_b"):])
    return _SHAPES[bladder.index(b) % len(_SHAPES)] if b in bladder else "o"


def _val(df, xcol, xv, arm, col):
    s = df.loc[(df[xcol] == xv) & (df.arm == arm), col]
    return float(s.iloc[0]) if len(s) else np.nan


def render_sweep(frames, *, xcol, xvals, xtick_labels, xlabel, arms, bladder,
                 out: Path, title: str, kind: str, vlines=None,
                 raw_ylabel="Max FCT (μs)", log_raw=False, spd_cloud=None):
    """spd_cloud: optional list of (xval, speedup, color) points scattered
    translucently on the speedup panel — used to show per-seed spread at a
    single x where the plotted (seed-42) value is not representative."""
    style = arm_style(bladder)
    conds = list(frames)
    last = conds[-1]
    x = np.arange(len(xvals))
    fig, (ax_raw, ax_spd) = plt.subplots(2, 1, figsize=(max(8, 1.5 * len(xvals) + 2), 9),
                                         sharex=True)
    panels = [(ax_raw, "max_fct_us", "%.0f"),
              (ax_spd, "speedup_vs_ops_max", "%.2f")]
    bw = 0.0

    if kind == "bars":
        combos = [(c, a) for c in conds for a in arms]
        bw = 0.8 / len(combos)
        label_bars = len(combos) <= 7        # skip value labels when too dense
        for gi, (cond, arm) in enumerate(combos):
            df = frames[cond]
            faded = cond != last
            for ax, col, fmt in panels:
                vals = [_val(df, xcol, xv, arm, col) for xv in xvals]
                cont = ax.bar(x + gi * bw, vals, bw, color=style[arm]["color"],
                              hatch=style[arm]["hatch"], edgecolor="black",
                              lw=0.4, alpha=0.4 if faded else 1.0)
                if label_bars:
                    ax.bar_label(cont, fmt=fmt, rotation=90, padding=2, fontsize=6)
        xt = x + 0.4 - bw / 2
    else:  # lines
        for cond in conds:
            df = frames[cond]
            faded = cond != last
            lw, alpha, ls = (1.3, 0.4, "--") if faded else (2.4, 1.0, "-")
            for arm in arms:
                s = df[df.arm == arm].sort_values(xcol)
                if s.empty:
                    continue
                col = OPS_COLOR if arm == "ops" else style[arm]["color"]
                mk = _shape(arm, bladder)
                xs = [xvals.index(v) for v in s[xcol]]
                kw = dict(color=col, ls=ls, lw=lw, alpha=alpha, marker=mk, ms=8,
                          mew=1.6, mfc=(col if arm == "ops" else "none"), mec=col,
                          zorder=5 if arm == "ops" else 3)
                ax_raw.plot(xs, s.max_fct_us, **kw)
                ax_spd.plot(xs, s.speedup_vs_ops_max, **kw)
        xt = x

    xvals = list(xvals)
    if spd_cloud:
        seen = set()
        for xv, y, c in spd_cloud:
            if xv not in xvals:
                continue
            xi = xvals.index(xv) + (0.02 if kind == "lines" else 0.4 - bw / 2)
            ax_spd.scatter([xi], [y], s=42, color=c, alpha=0.30,
                           edgecolors="none", zorder=6,
                           label=("per-seed (n>1)" if "cloud" not in seen else None))
            seen.add("cloud")
    for ax, col, _fmt in panels:
        if vlines:
            for vx, vc in vlines:
                if vx in xvals:
                    xi = xvals.index(vx) + (0.4 - bw / 2 if kind == "bars" else 0)
                    ax.axvline(xi, color=vc, ls=":", lw=1.4)
        ax.grid(True, axis="y" if kind == "bars" else "both", ls=":", lw=0.7,
                alpha=0.7)
    if log_raw:
        ax_raw.set_yscale("log")
    ax_spd.axhline(1.0, color="grey", ls="--", lw=1.1)
    # speedup panel: zoom to a tight window around 1.0 (never start at 0 — the
    # bars/markers all sit near 1.x and a 0-based axis flattens the differences)
    sp = np.concatenate([np.asarray(f["speedup_vs_ops_max"], dtype=float).ravel()
                         for f in frames.values()])
    sp = sp[np.isfinite(sp)]
    if sp.size:
        lo, hi = min(1.0, sp.min()), sp.max()
        pad = (hi - lo) * 0.08 or 0.02
        ax_spd.set_ylim(lo - pad, hi + pad * (3.0 if kind == "bars" else 1.6))
    ax_raw.set_ylabel(raw_ylabel, fontsize=12)
    ax_spd.set_ylabel("Speedup vs OPS (Max FCT)", fontsize=12)
    ax_spd.set_xticks(xt)
    ax_spd.set_xticklabels(xtick_labels, fontsize=9)
    ax_spd.set_xlabel(xlabel, fontsize=12)
    ax_raw.set_title(title, fontsize=10.5)

    if kind == "bars":
        handles = [Patch(facecolor=style[a]["color"], hatch=style[a]["hatch"],
                         edgecolor="black",
                         label="OPS" if a == "ops" else f"REPS B={a[6:]}")
                   for a in arms]
    else:
        handles = [Line2D([], [], color=OPS_COLOR, marker="s", ms=8,
                          mfc=OPS_COLOR, label="OPS")]
        for a in arms[1:]:
            handles.append(Line2D([], [], color=style[a]["color"],
                                  marker=_shape(a, bladder), ms=9, mfc="none",
                                  mec=style[a]["color"], mew=1.6,
                                  label=f"REPS B={a[6:]}"))
    if len(conds) > 1:
        handles += [Line2D([], [], color="#555", ls="--", lw=1.3, alpha=0.6,
                           label=conds[0]),
                    Line2D([], [], color="#555", ls="-", lw=2.4, label=last)]
    if spd_cloud:
        cc = spd_cloud[0][2]
        xv = spd_cloud[0][0]
        handles.append(Line2D([], [], color=cc, marker="o", ls="", ms=7,
                              alpha=0.30, mec="none",
                              label=f"B=1 per-seed ({xv} MiB)"))
    fig.legend(handles=handles, loc="lower center", ncol=min(7, len(handles)),
               fontsize=9, frameon=False, bbox_to_anchor=(0.5, -0.02))
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}")
