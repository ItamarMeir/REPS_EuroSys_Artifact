#!/usr/bin/env python3
"""Plot Paper 1 (REPS, arXiv:2407.21625) figures from data/cct.csv.

Coverage:
  Fig 2 (left) — Synthetic speedup vs ECMP (incast/perm/tornado × 4/8/16 MiB)
  Fig 2 (middle) — DC avg FCT vs load (WebSearch + Hadoop)
  Fig 4 — Asymmetric speedup vs ECMP (4 links degraded)
  Fig 6 — Failure-mode speedup vs OPS
  Fig 8 — Extreme failures max FCT (REPS vs OPS, 16 MiB perm)

Outputs go to plots/paper1_*.png.
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
PLOTS = ROOT / "plots"
PLOTS.mkdir(exist_ok=True)


def load_cct():
    rows = []
    with DATA.open() as f:
        for r in csv.DictReader(f):
            if r["paper"] != "p1":
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


def group_by(rows, key_fn, val_fn):
    g = defaultdict(list)
    for r in rows:
        k = key_fn(r)
        if k is None:
            continue
        g[k].append(val_fn(r))
    return {k: mean_ci(vs) for k, vs in g.items()}


def workload_type_size(tm):
    """Return (kind, size_mb) from a tmstem like 'perm_128n_128c_8MB_s42'.
    Returns (None, None) if not matched."""
    if tm.startswith("perm_"):
        kind = "P"
    elif tm.startswith("incast_"):
        kind = "I"
    elif tm.startswith("tornado_"):
        kind = "T"
    else:
        return None, None
    for tok in tm.split("_"):
        if tok.endswith("MB") and tok[:-2].isdigit():
            return kind, int(tok[:-2])
    return kind, None


# ─────────────────────────────────────────────────────────────────────
# Fig 2 (left) — Synthetic speedup-vs-ECMP
# ─────────────────────────────────────────────────────────────────────
def fig2_synth(rows, fig_tag="fig02_synth", suffix="", tier_label="2-tier"):
    # Paper §4.3.1: "we visualize a summary of the performance ... by looking
    # at the runtime of the workloads (max FCT)". Match the paper's metric.
    sub = [r for r in rows if r["fig"] == fig_tag]
    by = group_by(sub, lambda r: (r["algo"], workload_type_size(r["workload"])),
                  lambda r: r["max_fct"])
    bars = []
    kinds = ["I", "P", "T"]
    sizes = [4, 8, 16]
    for kind in kinds:
        for sz in sizes:
            ecmp_key = ("ecmp", (kind, sz))
            reps_key = ("freezing", (kind, sz))
            if ecmp_key in by and reps_key in by:
                speedup = by[ecmp_key][0] / by[reps_key][0]
                bars.append((f"{kind}{sz}", speedup))
    if not bars:
        print(f"WARN: no {fig_tag} data")
        return

    fig, ax = plt.subplots(figsize=(7, 4))
    labels, vals = zip(*bars)
    ax.bar(range(len(vals)), vals, color="tab:orange")
    ax.axhline(1.0, color="gray", linestyle="--", linewidth=0.6)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_ylabel("REPS speedup vs ECMP (×, max-FCT)")
    ax.set_title(f"Paper 1 Fig 2 (left) — Synthetic {tier_label}, REPS / ECMP max-FCT (runtime) ratio")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    out = PLOTS / f"paper1_fig02_synth{suffix}.png"
    fig.savefig(out, dpi=150)
    print(f"wrote {out}  ({len(bars)} bars)")


# ─────────────────────────────────────────────────────────────────────
# Fig 2 (middle) — DC avg FCT vs load
# ─────────────────────────────────────────────────────────────────────
def fig2_dc(rows):
    sub = [r for r in rows if r["fig"] == "fig02_dc"]
    by = defaultdict(list)  # (trace, load) -> [avg_fct]
    for r in sub:
        if r["algo"] != "freezing":
            continue
        tm = r["workload"]  # cdf_<trace>_l<load>_s<seed>
        parts = tm.split("_")
        if len(parts) < 4:
            continue
        trace = parts[1]
        load = int(parts[2].lstrip("l"))
        by[(trace, load)].append(r["avg_fct"])
    if not by:
        print("WARN: no fig02_dc data")
        return

    series = defaultdict(list)
    for (trace, load), vals in by.items():
        m, ci = mean_ci(vals)
        series[trace].append((load, m, ci))

    fig, ax = plt.subplots(figsize=(6, 4))
    for trace, pts in series.items():
        pts.sort()
        loads = [p[0] for p in pts]
        means = [p[1] for p in pts]
        cis = [p[2] for p in pts]
        ax.errorbar(loads, means, yerr=cis, marker="o", label=trace)
    ax.set_xlabel("Load level (%)")
    ax.set_ylabel("Avg FCT (µs)")
    ax.set_title("Paper 1 Fig 2 (middle) — DC traces, REPS")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    out = PLOTS / "paper1_fig02_dc.png"
    fig.savefig(out, dpi=150)
    print(f"wrote {out}")


# ─────────────────────────────────────────────────────────────────────
# Fig 4 — Asymmetric speedup vs ECMP
# ─────────────────────────────────────────────────────────────────────
def fig4_asym(rows, fig_tag="fig04_asym", suffix="", tier_label="2-tier"):
    # Same metric rule as Fig 2: paper §4.3.1 uses max FCT (workload runtime).
    sub = [r for r in rows if r["fig"] == fig_tag]
    by = group_by(sub, lambda r: (r["algo"], workload_type_size(r["workload"])),
                  lambda r: r["max_fct"])
    bars = []
    for kind in ["I", "P", "T"]:
        for sz in [4, 8, 16]:
            ecmp_key = ("ecmp", (kind, sz))
            reps_key = ("freezing", (kind, sz))
            if ecmp_key in by and reps_key in by:
                speedup = by[ecmp_key][0] / by[reps_key][0]
                bars.append((f"{kind}{sz}", speedup))
    if not bars:
        print(f"WARN: no {fig_tag} data")
        return

    fig, ax = plt.subplots(figsize=(7, 4))
    labels, vals = zip(*bars)
    ax.bar(range(len(vals)), vals, color="tab:red")
    ax.axhline(1.0, color="gray", linestyle="--", linewidth=0.6)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_ylabel("REPS speedup vs ECMP (×, max-FCT)")
    ax.set_title(f"Paper 1 Fig 4 — Asymmetric {tier_label} (4 degraded uplinks, max-FCT ratio)")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    out = PLOTS / f"paper1_fig04_asym{suffix}.png"
    fig.savefig(out, dpi=150)
    print(f"wrote {out}  ({len(bars)} bars)")


# ─────────────────────────────────────────────────────────────────────
# Fig 6 — Per-failure-mode speedup vs OPS
# ─────────────────────────────────────────────────────────────────────
def fig6_failures(rows):
    sub = [r for r in rows if r["fig"].startswith("fig06_")]
    by = defaultdict(list)  # (mode, wl, algo) -> [avg_fct]
    for r in sub:
        parts = r["fig"].split("_")  # fig06_<mode>_<wl>
        if len(parts) < 3:
            continue
        # mode may have underscores (5pct_cables); wl is the last token
        wl = parts[-1]
        mode = "_".join(parts[1:-1])
        by[(mode, wl, r["algo"])].append(r["avg_fct"])
    if not by:
        print("WARN: no fig06 data")
        return

    # Aggregate to (mode, wl) -> (reps_avg, ops_avg, speedup)
    bars = defaultdict(dict)
    for (mode, wl, algo), vals in by.items():
        m, _ = mean_ci(vals)
        bars[(mode, wl)][algo] = m

    rows_out = []
    for (mode, wl), d in bars.items():
        if "freezing" in d and "oblivious" in d:
            rows_out.append((mode, wl, d["oblivious"] / d["freezing"]))

    if not rows_out:
        print("WARN: fig06 — no REPS+OPS pairs")
        return

    # Plot one panel per workload
    workloads = sorted({wl for _, wl, _ in rows_out})
    fig, axes = plt.subplots(1, len(workloads), figsize=(4 * len(workloads), 4), sharey=True)
    if len(workloads) == 1:
        axes = [axes]
    for ax, wl in zip(axes, workloads):
        wl_rows = [(m, s) for m, w, s in rows_out if w == wl]
        wl_rows.sort()
        labels = [m for m, _ in wl_rows]
        vals = [s for _, s in wl_rows]
        ax.bar(range(len(vals)), vals, color="tab:purple")
        ax.axhline(1.0, color="gray", linestyle="--", linewidth=0.6)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=60, ha="right")
        ax.set_title(f"workload={wl}")
        ax.set_ylabel("Speedup vs OPS (×)")
        ax.grid(axis="y", alpha=0.3)
    fig.suptitle("Paper 1 Fig 6 — Per-failure-mode REPS / OPS speedup")
    fig.tight_layout()
    out = PLOTS / "paper1_fig06_failures.png"
    fig.savefig(out, dpi=150)
    print(f"wrote {out}")


# ─────────────────────────────────────────────────────────────────────
# Fig 8 — Extreme failures (max FCT vs % cables failed)
# ─────────────────────────────────────────────────────────────────────
def fig8_extreme(rows):
    sub = [r for r in rows if r["fig"].startswith("fig08_sev")]
    by = defaultdict(list)
    for r in sub:
        sev = int(r["fig"][len("fig08_sev"):])
        by[(r["algo"], sev)].append(r["max_fct"])
    if not by:
        print("WARN: no fig08 data")
        return

    series = defaultdict(list)
    for (algo, sev), vals in by.items():
        m, ci = mean_ci(vals)
        series[algo].append((sev, m, ci))

    fig, ax = plt.subplots(figsize=(6, 4))
    for algo, pts in sorted(series.items()):
        pts.sort()
        sevs = [p[0] for p in pts]
        means = [p[1] for p in pts]
        cis = [p[2] for p in pts]
        ax.errorbar(sevs, means, yerr=cis, marker="o", label=algo)
    ax.set_xlabel("% Cables failed")
    ax.set_ylabel("Max FCT (µs)")
    ax.set_title("Paper 1 Fig 8 — Extreme failures (perm 16 MiB)")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    out = PLOTS / "paper1_fig08_extreme.png"
    fig.savefig(out, dpi=150)
    print(f"wrote {out}")


def main():
    rows = load_cct()
    print(f"loaded {len(rows)} p1 rows")
    fig2_synth(rows)
    fig2_synth(rows, fig_tag="fig02_synth3t", suffix="_3t", tier_label="3-tier")
    fig2_dc(rows)
    fig4_asym(rows)
    fig4_asym(rows, fig_tag="fig04_asym3t", suffix="_3t", tier_label="3-tier")
    fig6_failures(rows)
    fig8_extreme(rows)


if __name__ == "__main__":
    main()
