#!/usr/bin/env python3
"""Plot Paper 2 (CC4Spraying, arXiv:2509.07907v2) REPS-column figures.

Per figure: CCT % inflation = (max_FCT − ZQLB) / ZQLB × 100, mean ± 95 % CI across seeds.
Bar chart with one bar per CCA.
"""
import csv
import math
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "cct.csv"
FCTS = ROOT / "data" / "fcts.csv"
PLOTS = ROOT / "plots"
PLOTS.mkdir(exist_ok=True)


# ZQLB for incast: collective lower bound (32 × 8 MB × 8 / 800 Gbps + 3 µs RTT)
INCAST_ZQLB_US = 32 * 8 * 1024 * 1024 * 8 / (800 * 1e9) * 1e6 + 3.0  # ≈ 2687 µs

# Theoretical sprayed-flow ZQLB per figure (size at line rate + 1 RTT zero-queue).
# Paper §IV.A: CCT is max FCT across sprayed flows; ZQLB is the zero-queueing lower
# bound for a single sprayed flow. Elephants are treated as "long-lived" background
# and are excluded from the sprayed-flow CCT (they would otherwise dominate).
SPRAYED_SIZE_BY_FIG = {
    "fig04":  8 * 1024 * 1024,        # 8 MB sprayed (4 ECMP elephants)
    "fig06":  8 * 1024 * 1024,        # pure permutation, no elephants
    "fig07":  3344 * 4096,            # HSDP ring, 13.7 MB each
    "fig08":  8 * 1024 * 1024,        # 250-node baseline, 8 MB sprayed
    "fig09":  16 * 1024 * 1024,       # 16 MB baseline
    "fig10":  8 * 1024 * 1024,        # 8 ECMP elephants, 8 MB sprayed
    "fig11":  8 * 1024 * 1024,        # baseline + 1 % failures, 8 MB sprayed
    "fig12":  8 * 1024 * 1024,        # MSwift P sweep, 8 MB sprayed
    # fig14 = incast (special-cased via INCAST_ZQLB_US)
}
# 800 Gbps NIC, ~5 µs RTT at 0.5 µs/hop × 5 hops × 2 (paper 3-tier 128n)
LINKRATE_BPS = 800e9
BASE_RTT_US  = 5.0
# 400 Gbps for fig08 (250-node)
LINKRATE_BPS_FIG08 = 400e9


def load_rows():
    rows = []
    with DATA.open() as f:
        for r in csv.DictReader(f):
            if r["paper"] != "p2":
                continue
            for col in ("max_fct", "avg_fct", "p50_fct", "p99_fct", "n_flows"):
                r[col] = float(r[col]) if "_fct" in col else int(r[col])
            rows.append(r)
    return rows


def mean_ci(vals):
    if not vals:
        return float("nan"), float("nan")
    n = len(vals)
    m = sum(vals) / n
    if n < 2:
        return m, 0.0
    var = sum((v - m) ** 2 for v in vals) / (n - 1)
    se = math.sqrt(var) / math.sqrt(n)
    return m, 1.96 * se


def zqlb_for(fig):
    """Theoretical ZQLB (µs) for the sprayed-flow class of a figure."""
    if fig == "fig14":
        return INCAST_ZQLB_US
    sz = SPRAYED_SIZE_BY_FIG.get(fig)
    if sz is None:
        return None
    rate = LINKRATE_BPS_FIG08 if fig == "fig08" else LINKRATE_BPS
    return sz * 8 / rate * 1e6 + BASE_RTT_US


# fcts.csv loaded lazily once; used to compute max FCT over sprayed flows only.
_FCTS_BY_RUN = None
def _load_fcts():
    global _FCTS_BY_RUN
    if _FCTS_BY_RUN is not None:
        return _FCTS_BY_RUN
    _FCTS_BY_RUN = defaultdict(list)
    if not FCTS.exists():
        return _FCTS_BY_RUN
    with FCTS.open() as f:
        for r in csv.DictReader(f):
            if r["paper"] != "p2":
                continue
            key = (r["fig"], r["algo"], r.get("pct", ""), r["seed"])
            _FCTS_BY_RUN[key].append((int(r["size_B"]), float(r["fct_us"])))
    return _FCTS_BY_RUN


def max_sprayed_fct(fig, algo, pct, seed):
    """Max FCT across sprayed flows only (excluding elephants).
    Sprayed = flows whose size == SPRAYED_SIZE_BY_FIG[fig]. Anything larger is
    an elephant background flow per Paper 2 §IV-A."""
    if fig == "fig14":
        # Incast: all flows are sprayed (32 senders to 1 victim, 8 MB)
        flows = _load_fcts().get((fig, algo, pct, seed), [])
        return max((f for _, f in flows), default=None)
    target = SPRAYED_SIZE_BY_FIG.get(fig)
    if target is None:
        return None
    flows = _load_fcts().get((fig, algo, pct, seed), [])
    sprayed = [f for sz, f in flows if sz == target]
    return max(sprayed) if sprayed else None


def plot_one_fig(fig_tag, rows, title=None, ylog=False):
    sub = [r for r in rows if r["fig"] == fig_tag]
    if not sub:
        return
    zqlb = zqlb_for(fig_tag)
    if zqlb is None:
        print(f"WARN: no theoretical ZQLB defined for {fig_tag}")
        return
    by = defaultdict(list)
    for r in sub:
        algo_label = r["algo"] if not r["pct"] else f"mswift_P{r['pct']}"
        # Use sprayed-only max FCT (paper metric), not the all-flow max from cct.csv.
        s_fct = max_sprayed_fct(fig_tag, r["algo"], r["pct"], r["seed"])
        if s_fct is None:
            continue
        infl = (s_fct - zqlb) / zqlb * 100.0
        by[algo_label].append(infl)

    ccas_order = ["swift", "lswift", "mswift", "nscc", "mnscc",
                  "mswift_P10", "mswift_P50", "mswift_P90"]
    items = [(c, by[c]) for c in ccas_order if c in by]
    if not items:
        return
    fig, ax = plt.subplots(figsize=(6, 4))
    labels = [c for c, _ in items]
    means = []
    cis = []
    for _, vals in items:
        m, ci = mean_ci(vals)
        means.append(m)
        cis.append(ci)
    colors = ["tab:blue", "tab:orange", "tab:purple", "tab:green", "tab:red",
              "tab:olive", "tab:cyan", "tab:brown"][:len(means)]
    ax.bar(range(len(means)), means, yerr=cis, capsize=4, color=colors)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=20)
    for i, m in enumerate(means):
        ax.annotate(f"{m:.1f}", xy=(i, m), ha="center",
                    va="bottom", fontsize=9)
    ax.set_ylabel("CCT inflation (%)" + ("  [log]" if ylog else ""))
    ax.set_title(title or f"Paper 2 {fig_tag} — REPS column")
    if ylog:
        ax.set_yscale("log")
        # Make all bars visible on log scale (a 0 bar would collapse). Set a
        # floor of ~1 % so the smallest bar still renders.
        ax.set_ylim(bottom=max(1.0, min(m for m in means if m > 0) * 0.5))
        ax.grid(axis="y", which="both", alpha=0.3)
    else:
        ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    out = PLOTS / f"paper2_{fig_tag}.png"
    fig.savefig(out, dpi=150)
    print(f"wrote {out}  ({len(items)} bars, ZQLB={zqlb:.1f} µs, ylog={ylog})")


def plot_fig5c_cdf():
    """Re-use Fig 4 outputs: CDF of per-flow FCT."""
    if not FCTS.exists():
        return
    by_cca = defaultdict(list)
    with FCTS.open() as f:
        for r in csv.DictReader(f):
            if r["paper"] != "p2" or r["fig"] != "fig04":
                continue
            by_cca[r["algo"]].append(float(r["fct_us"]))
    if not by_cca:
        return
    fig, ax = plt.subplots(figsize=(6, 4))
    for cca in ["swift", "lswift", "mswift", "nscc", "mnscc"]:
        if cca not in by_cca:
            continue
        vals = sorted(by_cca[cca])
        n = len(vals)
        y = [(i + 1) / n for i in range(n)]
        ax.plot(vals, y, label=cca)
    ax.set_xlabel("FCT (µs)")
    ax.set_ylabel("CDF")
    ax.set_title("Paper 2 Fig 5c — FCT CDF, REPS column")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    out = PLOTS / "paper2_fig05c_cdf.png"
    fig.savefig(out, dpi=150)
    print(f"wrote {out}")


def main():
    rows = load_rows()
    print(f"loaded {len(rows)} p2 rows")
    # Figures with very wide CCT-inflation range (Swift dominates) use log y to
    # match paper plot style.
    LOG_Y_FIGS = {"fig04", "fig08", "fig09", "fig11"}
    for fig_tag in ["fig04", "fig06", "fig07", "fig08", "fig09", "fig10",
                    "fig11", "fig12", "fig14"]:
        plot_one_fig(fig_tag, rows, ylog=(fig_tag in LOG_Y_FIGS))
    plot_fig5c_cdf()


if __name__ == "__main__":
    main()
