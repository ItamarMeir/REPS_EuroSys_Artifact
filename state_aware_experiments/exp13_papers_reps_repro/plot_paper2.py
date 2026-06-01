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


def zqlb_for(fig, rows_for_fig):
    """Pick the right ZQLB for a figure."""
    if fig == "fig14":
        return INCAST_ZQLB_US
    # Otherwise: empirical ZQLB = min(FCT) across all flows and CCAs (per-flow).
    # Approximate via the min max_fct then divide by ~something? Use min avg_fct.
    # Actually use min max_fct directly — this is the "best possible CCT" observed.
    return min(r["max_fct"] for r in rows_for_fig)


def plot_one_fig(fig_tag, rows, title=None):
    sub = [r for r in rows if r["fig"] == fig_tag]
    if not sub:
        return
    zqlb = zqlb_for(fig_tag, sub)
    by = defaultdict(list)
    for r in sub:
        algo_label = r["algo"] if not r["pct"] else f"mswift_P{r['pct']}"
        infl = (r["max_fct"] - zqlb) / zqlb * 100.0
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
    ax.set_ylabel("CCT inflation (%)")
    ax.set_title(title or f"Paper 2 {fig_tag} — REPS column")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    out = PLOTS / f"paper2_{fig_tag}.png"
    fig.savefig(out, dpi=150)
    print(f"wrote {out}  ({len(items)} bars, ZQLB={zqlb:.1f} µs)")


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
    for fig_tag in ["fig04", "fig06", "fig07", "fig08", "fig09", "fig10",
                    "fig11", "fig12", "fig14"]:
        plot_one_fig(fig_tag, rows)
    plot_fig5c_cdf()


if __name__ == "__main__":
    main()
