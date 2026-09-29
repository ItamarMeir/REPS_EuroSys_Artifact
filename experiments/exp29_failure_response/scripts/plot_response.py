#!/usr/bin/env python3
"""
exp29 figures.

    python3 plot_response.py

Legibility: 5 B-series with n=3-seed 95% CI (t-mult 4.30) overlap badly on a
shared axis. Countermeasures here:
  * every line figure x-dodges the B-series so whiskers sit side-by-side
  * a grouped-bar twin of each figure, y-axis clipped to the data range
  * a Delta-from-B8 figure (severity ramp cancelled, y auto-zoomed to the
    between-B band)
  * best_worst/ : 5 B-series collapsed to a min-B / max-B envelope
  * data/resolvable.csv (from aggregate29.py) is the numeric verdict the plots
    only gesture at.

  plots/response_vs_f.png        + _bars   : 2x4 vs F, one series per B
  plots/response_vs_f_delta.png            : metric(B) - metric(B=8), CI
  plots/exit_freeze.png          + _bars   : p99 FCT vs F, ef=100 vs ef=250
  plots/timeseries.png                     : B=1 vs B=8 (+ B in {2,4,32} band)
  plots/best_worst/fct.png       + _bars   : min-B / max-B FCT envelope

Reads data/{timeseries,response,fct}.csv from aggregate29.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR = SCRIPT_DIR.parent
DATA = EXP_DIR / "data"
PLOTS = EXP_DIR / "plots"

# shared style primitives from exp28 (same shim common29.py uses for exp26)
sys.path.insert(0, str(EXP_DIR.parent / "exp28_link_degradation_sweep" / "scripts"))
from plot_sweep import B_HATCH, B_LADDER, _yerr, style_for  # noqa: E402

EF_PRIMARY = 100
REF_ARM = "reps_b8"          # Delta reference: exp28 says nothing above B=4 resolves
FAIL_US, RECOVER_US = 100, 200


def arms_in(df: pd.DataFrame) -> list[str]:
    present = set(df.arm.unique())
    return [f"reps_b{b}" for b in B_LADDER if f"reps_b{b}" in present]


def _lines(ax, agg, xcol, col, arms, *, logy=False):
    """One mean line per B at the true x, with a shaded 95% CI band (exp28's
    interactive style -- no x-dodge, no error-bar caps). The lower edge of the
    band is clipped at 0 for non-negative metrics."""
    xs = sorted(agg[xcol].unique())
    for arm in arms:
        s = agg[agg.arm == arm].sort_values(xcol)
        s = s[s[col].notna()]
        if s.empty:
            continue
        st = style_for(arm)
        x = s[xcol].to_numpy(float)
        y = s[col].to_numpy(float)
        ci = np.asarray(s[col + "_ci"], float)
        lo = np.where(col.endswith("_us") | col.startswith("d_")
                      | (col == "frozen_frac") | ("per_host" in col)
                      | ("rate" in col), np.maximum(y - ci, 0.0), y - ci)
        ax.fill_between(x, lo, y + ci, color=st["color"], alpha=0.15, lw=0)
        ax.plot(x, y, "-" + st["marker"], color=st["color"], lw=2, ms=7,
                mfc="none", mec=st["color"], label=f"B={arm[6:]}")
    ax.set_xticks(xs)
    if logy:
        ax.set_yscale("log")
    ax.grid(True, which="both", ls=":", lw=0.7, alpha=0.7)


def _bars(ax, agg, xcol, col, arms, xvals):
    xi = np.arange(len(xvals))
    bw = 0.82 / len(arms)
    vmin, vmax = np.inf, -np.inf
    for j, arm in enumerate(arms):
        s = agg[agg.arm == arm].set_index(xcol)
        vals = [s[col].get(xv, np.nan) for xv in xvals]
        cis = [s[col + "_ci"].get(xv, 0.0) for xv in xvals]
        st = style_for(arm)
        ax.bar(xi + j * bw, vals, bw, yerr=_yerr(np.nan_to_num(vals), cis),
               capsize=2, error_kw=dict(elinewidth=1.0), color=st["color"],
               hatch=B_HATCH[B_LADDER.index(int(arm[6:])) % len(B_HATCH)],
               edgecolor="black", lw=0.4)
        fin = [(v, c) for v, c in zip(vals, cis) if np.isfinite(v)]
        if fin:
            vmin = min(vmin, min(v - c for v, c in fin))
            vmax = max(vmax, max(v + c for v, c in fin))
    if np.isfinite(vmin):
        pad = (vmax - vmin) * 0.08 or abs(vmax) * 0.05 or 1
        ax.set_ylim(max(0, vmin - pad), vmax + pad)
    ax.set_xticks(xi + 0.41 - bw / 2)
    ax.set_xticklabels([str(v) for v in xvals], fontsize=9)
    ax.grid(True, axis="y", ls=":", lw=0.7, alpha=0.7)


def _delta(ax, agg, xcol, col, arms):
    ref = agg[agg.arm == REF_ARM].set_index(xcol)
    xs = sorted(agg[xcol].unique())
    for arm in [a for a in arms if a != REF_ARM]:
        s = agg[agg.arm == arm].sort_values(xcol)
        x = s[xcol].to_numpy(float)
        d = s[col].to_numpy(float) - ref[col].reindex(s[xcol]).to_numpy(float)
        # CI of a difference of independent means
        ci = np.sqrt(np.asarray(s[col + "_ci"], float) ** 2
                     + ref[col + "_ci"].reindex(s[xcol]).to_numpy(float) ** 2)
        st = style_for(arm)
        ax.fill_between(x, d - ci, d + ci, color=st["color"], alpha=0.15, lw=0)
        ax.plot(x, d, "-" + st["marker"], color=st["color"], lw=2, ms=7,
                mfc="none", mec=st["color"], label=f"B={arm[6:]}")
    ax.axhline(0, color="k", lw=1)
    ax.set_xticks(xs)
    ax.grid(True, ls=":", lw=0.7, alpha=0.7)


def _envelope(agg, xcol, col):
    rows = []
    for x, g in agg.groupby(xcol):
        g = g[g[col].notna()]
        if g.empty:
            continue
        b, w = g.loc[g[col].idxmin()], g.loc[g[col].idxmax()]
        rows.append(dict(x=x, best_val=b[col], best_ci=b[col + "_ci"],
                         best_b=int(b.buf_size), worst_val=w[col],
                         worst_ci=w[col + "_ci"], worst_b=int(w.buf_size)))
    return pd.DataFrame(rows).sort_values("x")


def _b_handles(arms):
    return [Line2D([], [], color=style_for(a)["color"], marker=style_for(a)["marker"],
                   lw=2, mfc="none", mec=style_for(a)["color"], label=f"B={a[6:]}")
            for a in arms]


def _b_patches(arms):
    return [Patch(facecolor=style_for(a)["color"], edgecolor="black",
                  hatch=B_HATCH[B_LADDER.index(int(a[6:])) % len(B_HATCH)],
                  label=f"B={a[6:]}") for a in arms]


PANELS = [
    ("fct", "p50_fct_us", "affected p50 FCT (us)"),
    ("fct", "p99_fct_us", "affected p99 FCT (us)"),
    ("fct", "max_fct_us", "affected max FCT (us)"),
    ("during", "d_rto", "RTOs / affected host  (during 100-200us)"),
    ("during", "frozen_frac", "frozen fraction  (during)"),
    ("recovery", "frozen_frac", "frozen fraction  (recovery 200-950us)"),
    ("recovery", "d_rto", "RTOs / affected host  (recovery)"),
    ("recovery", "d_ev_random", "ev_random / host  (recovery) -- buffer refresh"),
]


def _panel_frame(fct, resp, src, ef):
    if src == "fct":
        return fct[(fct.group == "affected") & (fct.ef == ef)]
    return resp[(resp.group == "affected") & (resp.ef == ef) & (resp.phase == src)]


def fig_response_vs_f(fct, resp, kind):
    ef = EF_PRIMARY
    arms = arms_in(fct[fct.ef == ef])
    Fs = sorted(fct[fct.ef == ef].F.unique())
    fig, axes = plt.subplots(2, 4, figsize=(20, 9))
    for ax, (src, col, name) in zip(axes.ravel(), PANELS):
        d = _panel_frame(fct, resp, src, ef)
        if kind == "lines":
            _lines(ax, d, "F", col, arms)
        else:
            _bars(ax, d, "F", col, arms, Fs)
        ax.set_title(name, fontsize=10.5)
    if kind == "lines":
        axes[0][0].axhline(356, color="grey", ls="--", lw=1)
    for ax in axes[1]:
        ax.set_xlabel("# failed ToR0 spine uplinks (F)")
    h = _b_patches(arms) if kind == "bars" else _b_handles(arms)
    fig.legend(handles=h, loc="lower center", ncol=len(arms), fontsize=10,
               frameon=False, bbox_to_anchor=(0.5, -0.02))
    fig.suptitle("exp29 -- REPS failure-response vs # simultaneously-dead paths F  "
                 "(tornado 16 MiB, fail t in (100,200)us, exit_freeze=100us, "
                 f"seeds 42/43/44, 95% CI){'  [grouped bars, y clipped]' if kind=='bars' else ''}",
                 fontsize=11)
    fig.tight_layout(rect=(0, 0.03, 1, 0.96))
    PLOTS.mkdir(parents=True, exist_ok=True)
    sfx = "" if kind == "lines" else "_bars"
    fig.savefig(PLOTS / f"response_vs_f{sfx}.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig_delta(fct, resp):
    ef = EF_PRIMARY
    arms = arms_in(fct[fct.ef == ef])
    panels = [("fct", "p50_fct_us", "Δ p50 FCT vs B=8 (us)"),
              ("fct", "p99_fct_us", "Δ p99 FCT vs B=8 (us)"),
              ("during", "d_rto", "Δ RTOs/host (during) vs B=8"),
              ("recovery", "d_ev_random", "Δ ev_random/host (recovery) vs B=8")]
    fig, axes = plt.subplots(1, 4, figsize=(20, 4.6))
    for ax, (src, col, name) in zip(axes, panels):
        _delta(ax, _panel_frame(fct, resp, src, ef), "F", col, arms)
        ax.set_title(name, fontsize=10.5)
        ax.set_xlabel("# failed ToR0 spine uplinks (F)")
    fig.legend(handles=_b_handles([a for a in arms if a != REF_ARM]),
               loc="lower center", ncol=len(arms) - 1, fontsize=10,
               frameon=False, bbox_to_anchor=(0.5, -0.04))
    fig.suptitle("exp29 -- B relative to B=8 (severity trend removed; a band "
                 "clear of 0 is a real effect)", fontsize=11)
    fig.tight_layout(rect=(0, 0.06, 1, 0.94))
    fig.savefig(PLOTS / "response_vs_f_delta.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig_exit_freeze(fct, kind):
    aff = fct[fct.group == "affected"]
    efs = sorted(aff.ef.unique())
    if len(efs) < 2:
        print("  (single exit_freeze -- skipping exit_freeze figure)")
        return
    arms = arms_in(aff)
    Fs = sorted(aff[aff.ef == efs[1]].F.unique())
    fig, axes = plt.subplots(1, len(efs), figsize=(7 * len(efs), 5), sharey=True)
    for ax, ef in zip(axes, efs):
        d = aff[(aff.ef == ef) & (aff.F.isin(Fs))]
        if kind == "lines":
            _lines(ax, d, "F", "p99_fct_us", arms)
        else:
            _bars(ax, d, "F", "p99_fct_us", arms, Fs)
        ax.set_title(f"exit_freeze = {ef} us", fontsize=11)
        ax.set_xlabel("# failed ToR0 uplinks (F)")
    axes[0].set_ylabel("affected p99 FCT (us)")
    h = _b_patches(arms) if kind == "bars" else _b_handles(arms)
    fig.legend(handles=h, loc="lower center", ncol=len(arms), fontsize=9,
               frameon=False, bbox_to_anchor=(0.5, -0.03))
    fig.suptitle("exp29 -- freeze-timeout heuristic: failure-duration (100us) vs "
                 "recovery+buffer (250us)", fontsize=11)
    fig.tight_layout(rect=(0, 0.04, 1, 0.93))
    sfx = "" if kind == "lines" else "_bars"
    fig.savefig(PLOTS / f"exit_freeze{sfx}.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig_timeseries(ts):
    aff = ts[(ts.group == "affected") & (ts.ef == EF_PRIMARY)].copy()
    fsub = [f for f in (1, 8, 16, 31) if f in aff.F.unique()]
    metrics = [("d_ecn_acks", "ECN acks / host / win"),
               ("d_rto", "RTOs / host / win"),
               ("d_freeze_entries", "freeze entries / host / win"),
               ("frozen_frac", "frozen fraction"),
               ("d_ev_random", "ev_random / host / win")]
    band_arms = [a for a in ("reps_b2", "reps_b4", "reps_b32") if a in aff.arm.unique()]
    fig, axes = plt.subplots(len(metrics), len(fsub),
                             figsize=(3.6 * len(fsub), 2.2 * len(metrics)),
                             sharex=True, squeeze=False)
    for r, (col, name) in enumerate(metrics):
        for c, F in enumerate(fsub):
            ax = axes[r][c]
            sub = aff[aff.F == F]
            if band_arms:
                piv = sub[sub.arm.isin(band_arms)].pivot_table(
                    index="t_us", columns="arm", values=col)
                if not piv.empty:
                    ax.fill_between(piv.index, piv.min(axis=1), piv.max(axis=1),
                                    color="grey", alpha=0.25, lw=0)
            for arm, cstyle in (("reps_b1", style_for("reps_b1")),
                                ("reps_b8", style_for("reps_b8"))):
                s = sub[sub.arm == arm].sort_values("t_us")
                if not s.empty:
                    ax.plot(s.t_us, s[col], color=cstyle["color"], lw=1.7,
                            label=f"B={arm[6:]}")
            ax.axvline(FAIL_US, color="k", ls="--", lw=0.8)
            ax.axvline(RECOVER_US, color="k", ls=":", lw=0.8)
            ax.grid(True, ls=":", lw=0.6, alpha=0.6)
            if r == 0:
                ax.set_title(f"F={F}", fontsize=10)
            if c == 0:
                ax.set_ylabel(name, fontsize=8)
            if r == len(metrics) - 1:
                ax.set_xlabel("t (us)", fontsize=9)
    h = [Line2D([], [], color=style_for("reps_b1")["color"], lw=2, label="B=1"),
         Line2D([], [], color=style_for("reps_b8")["color"], lw=2, label="B=8"),
         Patch(facecolor="grey", alpha=0.25, label="B in {2,4,32} range")]
    fig.legend(handles=h, loc="lower center", ncol=3, fontsize=9, frameon=False,
               bbox_to_anchor=(0.5, -0.01))
    fig.suptitle("exp29 -- affected-host metric rates vs time  "
                 "(B=1 vs B=8; dashed = fail @100us, dotted = recover @200us)",
                 fontsize=10.5)
    fig.tight_layout(rect=(0, 0.03, 1, 0.96))
    fig.savefig(PLOTS / "timeseries.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


DIAG_PANELS = [
    ("ecn_per_host", "ECN-marked ACKs / host"),
    ("rto_per_host", "RTOs / host"),
    ("rts_per_host", "RTS / host"),
    ("freeze_us_mean", "time in freezing (µs)"),
    ("ev_random_per_host", "random-EV draws / host"),
    ("ev_random_rate", "random-EV draw rate (draws / pkt)"),
]


def fig_diagnostics(diag, kind):
    ef = EF_PRIMARY
    d = diag[(diag.group == "affected") & (diag.ef == ef)]
    arms = arms_in(d)
    Fs = sorted(d.F.unique())
    fig, axes = plt.subplots(2, 3, figsize=(16, 8.5))
    for ax, (col, name) in zip(axes.ravel(), DIAG_PANELS):
        if kind == "lines":
            _lines(ax, d, "F", col, arms)
        else:
            _bars(ax, d, "F", col, arms, Fs)
        ax.set_title(name, fontsize=10.5)
        ax.set_xticks(Fs)
    for ax in axes[1]:
        ax.set_xlabel("# failed ToR0 spine uplinks (F)")
    h = _b_patches(arms) if kind == "bars" else _b_handles(arms)
    fig.legend(handles=h, loc="lower center", ncol=len(arms), fontsize=10,
               frameon=False, bbox_to_anchor=(0.5, -0.02))
    fig.suptitle("exp29 -- whole-flow per-host diagnostics vs F  "
                 "(affected ToR0 senders, exit_freeze=100us, seeds 42/43/44, 95% CI)"
                 f"{'  [grouped bars, y clipped]' if kind=='bars' else ''}",
                 fontsize=11)
    fig.tight_layout(rect=(0, 0.04, 1, 0.95))
    sfx = "" if kind == "lines" else "_bars"
    fig.savefig(PLOTS / f"diagnostics{sfx}.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def fig_best_worst(fct, kind):
    aff = fct[(fct.group == "affected") & (fct.ef == EF_PRIMARY)]
    Fs = sorted(aff.F.unique())
    panels = [("p50_fct_us", "p50 FCT"), ("p99_fct_us", "p99 FCT"),
              ("max_fct_us", "max FCT")]
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    for ax, (col, name) in zip(axes, panels):
        env = _envelope(aff, "F", col)
        if kind == "lines":
            for pfx, cc, mk, dy in (("best", "#1b9e5a", "o", 7),
                                    ("worst", "#d1272d", "X", -12)):
                ax.errorbar(env.x, env[f"{pfx}_val"],
                            yerr=_yerr(env[f"{pfx}_val"], env[f"{pfx}_ci"]),
                            fmt="-" + mk, color=cc, lw=2.2, ms=8, capsize=3,
                            label=f"{pfx.title()} B")
                for _, rr in env.iterrows():
                    ax.annotate(f"B{int(rr[f'{pfx}_b'])}", (rr.x, rr[f"{pfx}_val"]),
                                textcoords="offset points", xytext=(0, dy),
                                fontsize=7, ha="center", color=cc)
            ax.set_xticks(Fs)
        else:
            xi = np.arange(len(Fs))
            e = env.set_index("x")
            for j, (pfx, cc) in enumerate((("best", "#1b9e5a"), ("worst", "#d1272d"))):
                vals = [e[f"{pfx}_val"].get(x, np.nan) for x in Fs]
                cis = [e[f"{pfx}_ci"].get(x, 0.0) for x in Fs]
                bs = [e[f"{pfx}_b"].get(x, None) for x in Fs]
                bars = ax.bar(xi + j * 0.38, vals, 0.38,
                              yerr=_yerr(np.nan_to_num(vals), cis), capsize=2,
                              color=cc, edgecolor="black", lw=0.4,
                              label=f"{pfx.title()} B")
                for rect, b, v in zip(bars, bs, vals):
                    if b is not None and np.isfinite(v):
                        ax.annotate(f"B{int(b)}",
                                    (rect.get_x() + rect.get_width() / 2, v),
                                    textcoords="offset points", xytext=(0, 3),
                                    fontsize=7, ha="center")
            fin = [v for v in env.best_val.tolist() + env.worst_val.tolist()
                   if np.isfinite(v)]
            if fin:
                lo, hi = min(fin), max(fin)
                pad = (hi - lo) * 0.15 or 1
                ax.set_ylim(max(0, lo - pad), hi + pad)
            ax.set_xticks(xi + 0.19)
            ax.set_xticklabels([str(x) for x in Fs])
        ax.set_title(name, fontsize=11)
        ax.set_xlabel("# failed ToR0 uplinks (F)")
        ax.grid(True, ls=":", lw=0.7, alpha=0.7)
    axes[0].set_ylabel("us")
    h, ll = axes[0].get_legend_handles_labels()
    fig.legend(h, ll, loc="lower center", ncol=2, fontsize=9, frameon=False,
               bbox_to_anchor=(0.5, -0.02))
    fig.suptitle("exp29 -- best-B / worst-B affected-FCT envelope  "
                 "(best & worst chosen per F per metric; label = winning B)",
                 fontsize=11)
    fig.tight_layout(rect=(0, 0.05, 1, 0.94))
    outdir = PLOTS / "best_worst"
    outdir.mkdir(parents=True, exist_ok=True)
    sfx = "" if kind == "lines" else "_bars"
    fig.savefig(outdir / f"fct{sfx}.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def main():
    fct = pd.read_csv(DATA / "fct.csv")
    resp = pd.read_csv(DATA / "response.csv")
    ts = pd.read_csv(DATA / "timeseries.csv")
    diag = pd.read_csv(DATA / "diagnostics.csv")
    for kind in ("lines", "bars"):
        fig_response_vs_f(fct, resp, kind)
        fig_exit_freeze(fct, kind)
        fig_best_worst(fct, kind)
        fig_diagnostics(diag, kind)
    fig_delta(fct, resp)
    fig_timeseries(ts)
    print(f"wrote {PLOTS}/response_vs_f{{,_bars,_delta}}.png, exit_freeze{{,_bars}}.png, "
          f"diagnostics{{,_bars}}.png, timeseries.png, best_worst/fct{{,_bars}}.png")


if __name__ == "__main__":
    main()
