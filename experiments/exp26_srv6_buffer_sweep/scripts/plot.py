#!/usr/bin/env python3
"""
plot.py -- exp26 figures, each a faithful reproduction of the matching paper
"network health" figure, with the paper's 9-way LB legend replaced by
{OPS, REPS B=1,2,4,...} (all runs use -use_srv6 -paths <n_paths>).

Paper originals + the generator whose plot logic and axis labels are mirrored:

  exp26 id  paper artifact script      paper PDF   generator
  fig2      fig_2_symmetric            Figure 2    plot_symmetric / _load / _collective
  fig4      fig_4_asymmetric           Figure 4    same three
  fig7      fig_7_failures             Figure 6    plot_failures.py (x3)
  fig8      fig_8_extreme_failures     Figure 8    inline in the artifact script
  fig6      fig_6_failures_micro       Figure 7    handled by plot_fig6.py

Outputs (plots/):
  fig2_all.png  fig4_all.png  fig7_all.png     3-panel composites, paper order,
                                               shared legend along the bottom
  fig2_{micro,dc,ai}.png  fig4_{...}  fig7_{...}   the same panels standalone
  fig8_failures.png
  legend_arms.png + LEGEND.md

Substantive deviation from the paper: fig2/fig4 micro and every fig7 panel use
the per-cell speedup vs the OPS arm (paper fig2/fig4 use "Speedup vs ECMP";
exp26 has no ECMP arm -- OPS is the restricted-EV oblivious baseline, the same
convention the paper's own fig7 uses). dc = absolute Average FCT, ai = absolute
collective runtime -- no baseline.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR = SCRIPT_DIR.parent
DATA_DIR = EXP_DIR / "data"
PLOTS_DIR = EXP_DIR / "plots"

OPS_COLOR = "#d95f02"      # the paper's OPS orange
OPS_MARKER = "s"
B_LADDER = [1, 2, 4, 8, 16, 32]   # global: a given B keeps its colour everywhere

# Headlines adapted from the paper's own figure captions (papers/REPS-new.pdf).
CAPTION = {
    "fig2": ("fig_2_symmetric (paper Figure 2) — REPS circular-buffer sweep in "
             "synthetic benchmarks\n(I.=Incast, P.=Permutation, T.=Tornado), "
             "DC traces and AI collectives."),
    "fig4": ("fig_4_asymmetric (paper Figure 4) — REPS circular-buffer sweep in "
             "synthetic benchmarks\n(I.=Incast, P.=Permutation, T.=Tornado), DC "
             "traces and AI collectives, and an asymmetric\nnetwork due to 2% of "
             "the ToR uplinks being offline."),
    "fig7": ("fig_7_failures (paper Figure 6) — REPS circular-buffer sweep under "
             "different failure modes\nin an 8 MiB permutation, DC traces at 100% "
             "load and a ring AllReduce."),
    "fig8": ("fig_8_extreme_failures (paper Figure 8) — Extreme failures scenario."),
}
SUBCAP = ("All arms use SRv6 source routing (-use_srv6) with the entropy domain "
          "restricted to the topology's physical paths.")

# Panel labels in the paper's own vocabulary.
PANEL_TITLE = {
    ("fig2", "micro"): "Synthetic benchmarks", ("fig2", "dc"): "DC traces",
    ("fig2", "ai"): "AI collectives",
    ("fig4", "micro"): "Synthetic benchmarks", ("fig4", "dc"): "DC traces",
    ("fig4", "ai"): "AI collectives",
    ("fig7", "micro"): "8 MiB permutation",
    ("fig7", "dc"): "DC traces at 100% load",
    ("fig7", "ai"): "Ring AllReduce",
}


# --------------------------------------------------------------------------- #
# arm styling: OPS fixed (paper colours), REPS a viridis ramp over B
# --------------------------------------------------------------------------- #
def arm_order(df: pd.DataFrame) -> list[str]:
    """Arms present in `df`, ops first then reps by ascending B."""
    bs = sorted(int(b) for b in pd.to_numeric(
        df.loc[df.arm != "ops", "buf_size"], errors="coerce").dropna().unique())
    out = ["ops"] if (df.arm == "ops").any() else []
    return out + [f"reps_b{b}" for b in bs]


def arm_style() -> dict[str, dict]:
    cmap = plt.get_cmap("viridis")
    n = len(B_LADDER) - 1
    style = {"ops": dict(color=OPS_COLOR, marker=OPS_MARKER, ls="--",
                         label="OPS (EV domain = #paths)")}
    for i, b in enumerate(B_LADDER):
        style[f"reps_b{b}"] = dict(color=cmap(i / n), marker="X", ls="-",
                                   label=f"REPS  B={b}")
    return style


def handles_for(arms: list[str]) -> list:
    st = arm_style()
    return [plt.Line2D([], [], color=st[a]["color"], marker=st[a]["marker"],
                       ls=st[a]["ls"], lw=2, ms=8, label=st[a]["label"])
            for a in arms]


def _load() -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / "summary.csv")
    for c in ("mean_fct_us", "p99_fct_us", "max_fct_us", "buf_size", "n_flows",
              "n_connections", "n_expected", "unfinished", "unfinished_vs_best",
              "speedup_vs_ops_mean", "speedup_vs_ops_max"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


# --------------------------------------------------------------------------- #
# Panel 1 — horizontal speedup-vs-OPS scatter (plot_symmetric.py / plot_failures.py)
# --------------------------------------------------------------------------- #
def draw_scatter(ax, d: pd.DataFrame, *, y_of, y_order, metric_col, xlabel,
                 ylabel="") -> None:
    d = d.copy()
    d["ylab"] = d.apply(y_of, axis=1)
    d = d[d.ylab.isin(y_order)]
    if d.empty:
        ax.set_axis_off()
        return
    style = arm_style()
    ops_metric = d[d.arm == "ops"].set_index("ylab")[metric_col].to_dict()
    yc = {lab: i for i, lab in enumerate(y_order)}

    ax.axvline(1.0, color="grey", ls="--", lw=1.5)
    for arm in arm_order(d):
        rows = d[d.arm == arm]
        xs, ys = [], []
        for _, r in rows.iterrows():
            base = ops_metric.get(r.ylab)
            if not base or not r[metric_col]:
                continue
            xs.append(base / r[metric_col])
            ys.append(yc[r.ylab])
        if not xs:
            continue
        st = style[arm]
        ax.scatter(xs, ys, s=130, marker=st["marker"], color=st["color"],
                   edgecolors="none", alpha=0.85, zorder=3)

    # Rows where OPS stalled on flows every REPS arm completed: its FCT is then
    # measured over the finished (easier) subset, so the speedup shown there is
    # a lower bound on REPS's real advantage.
    # placed in data coords just right of the OPS marker (always at x=1) and a
    # third of a row down, where no other arm's marker can sit.
    short = d[(d.arm == "ops") & (d.unfinished_vs_best.fillna(0) > 0)]
    for _, r in short.iterrows():
        ax.text(1.0, yc[r.ylab] + 0.36,
                f" OPS finished {int(r.n_flows)}/{int(r.n_connections)} flows",
                va="center", ha="left", fontsize=6, color="crimson")

    ax.set_yticks(range(len(y_order)))
    ax.set_yticklabels(y_order, fontsize=10)
    ax.set_ylim(len(y_order) - 0.4, -0.6)   # first label on top, paper order
    ax.set_xlabel(xlabel, fontsize=13)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=13)
    ax.grid(True, which="both", ls=":", lw=0.75, alpha=0.75)


# --------------------------------------------------------------------------- #
# Panel 2 — Average FCT vs Load Level line plot (plot_load.py)
# --------------------------------------------------------------------------- #
def draw_line_load(ax, d: pd.DataFrame) -> None:
    if d.empty:
        ax.set_axis_off()
        return
    d = d.copy()
    d["load"] = d.workload.str.extract(r"::(\d+)load").astype(int)
    style = arm_style()
    for arm in arm_order(d):
        s = d[d.arm == arm].sort_values("load")
        if s.empty:
            continue
        st = style[arm]
        ax.plot(s.load, s.mean_fct_us, st["ls"], marker=st["marker"],
                color=st["color"], lw=2.6, ms=11, alpha=0.9)
    ax.set_xlabel("Load Level (%)", fontsize=13)
    ax.set_ylabel("Average FCT (μs)", fontsize=13)
    ax.set_ylim(0, d.mean_fct_us.max() * 1.15)
    ax.set_xticks(sorted(d.load.unique()))
    ax.grid(True, which="both", ls=":", lw=0.75, alpha=0.75)


# --------------------------------------------------------------------------- #
# Panel 3 — Collective Runtime grouped bars (plot_collective.py)
# --------------------------------------------------------------------------- #
AI_ORDER = ["alltoall4", "alltoall8", "alltoall16", "allreduce", "allreduce_t"]
AI_LABEL = {"alltoall4": "AlltoAll\n(n=4)", "alltoall8": "AlltoAll\n(n=8)",
            "alltoall16": "AlltoAll\n(n=16)", "allreduce": "Ring\nAllRed.",
            "allreduce_t": "Buttefly\nAllRed."}   # paper's spelling, kept


def draw_bar_collective(ax, d: pd.DataFrame) -> None:
    if d.empty:
        ax.set_axis_off()
        return
    d = d.copy()
    d["coll"] = d.workload.str.split("::").str[1]
    style = arm_style()
    order = arm_order(d)
    colls = [c for c in AI_ORDER if c in set(d.coll)]

    bw = 0.8 / len(order)
    idx = np.arange(len(colls))
    for i, arm in enumerate(order):
        vals = []
        for c in colls:
            row = d[(d.coll == c) & (d.arm == arm)]
            vals.append(row.max_fct_us.iloc[0] / 1000.0 if len(row) else 0.0)
        ax.bar(idx + i * bw, vals, bw, color=style[arm]["color"])
    ax.set_xticks(idx + 0.4 - bw / 2)
    ax.set_xticklabels([AI_LABEL[c] for c in colls], fontsize=10)
    ax.set_ylabel("Collective Runtime (ms)", fontsize=13)
    ax.grid(True, which="both", ls=":", lw=0.75, alpha=0.75)


# --------------------------------------------------------------------------- #
# workload -> paper y label helpers
# --------------------------------------------------------------------------- #
MICRO_ORDER = ["I. 8:1 4MiB", "I. 8:1 8MiB", "I. 8:1 16MiB",
               "P. 4MiB", "P. 8MiB", "P. 16MiB",
               "T. 4MiB", "T. 8MiB", "T. 16MiB"]
_MICRO_PFX = {"incast": "I. 8:1", "perm": "P.", "tornado": "T."}


def micro_ylab(row) -> str:
    wl = row.workload.split("::")[1]        # e.g. perm_s8388608
    pat, _, sz = wl.partition("_s")
    try:
        mib = int(int(sz) / 1048576)
    except ValueError:
        return ""
    return f"{_MICRO_PFX.get(pat, pat)} {mib}MiB"


FAILMODE_ORDER = ["One Failed\nCable", "One Failed\nSwitch",
                  "One Failed\nSwitch/Cable", "5% Failed\nCables",
                  "5% Failed\nSwitches", "5% Failed\nSwitches/Cables",
                  "BER Cable 1%", "BER Switch 1%"]
_FAILMODE = {"fail_one_cable": "One Failed\nCable",
             "fail_one_switch": "One Failed\nSwitch",
             "fail_one_switch_one_cable": "One Failed\nSwitch/Cable",
             "5_percent_failed_cables": "5% Failed\nCables",
             "5_percent_failed_switches": "5% Failed\nSwitches",
             "5_percent_failed_switches_and_cables": "5% Failed\nSwitches/Cables",
             "ber_cable_one_percent": "BER Cable 1%",
             "ber_switch_one_percent": "BER Switch 1%"}


def failmode_ylab(row) -> str:
    return _FAILMODE.get(row.condition, "")


# --------------------------------------------------------------------------- #
# Panel dispatch: (fig_id, panel) -> (subset, draw fn)
# --------------------------------------------------------------------------- #
def panel_data(df: pd.DataFrame, fig_id: str, panel: str) -> pd.DataFrame:
    d = df[df.fig == fig_id]
    if fig_id in ("fig2", "fig4"):
        return d[d.workload.str.startswith(f"{panel}::")]
    return d[d.workload == {"micro": "permutation", "dc": "dc",
                            "ai": "ai"}[panel]]


def draw_panel(ax, df: pd.DataFrame, fig_id: str, panel: str) -> None:
    d = panel_data(df, fig_id, panel)
    if fig_id in ("fig2", "fig4"):
        if panel == "micro":
            draw_scatter(ax, d, y_of=micro_ylab, y_order=MICRO_ORDER,
                         metric_col="max_fct_us", xlabel="Speedup vs OPS")
        elif panel == "dc":
            draw_line_load(ax, d)
        else:
            draw_bar_collective(ax, d)
    else:   # fig7 -- three scatters, metric per panel as in plot_failures.py
        metric = {"micro": "max_fct_us", "dc": "mean_fct_us",
                  "ai": "max_fct_us"}[panel]
        xlabel = {"micro": "Speedup vs OPS",
                  "dc": "Speedup vs OPS (Avg FCT)",
                  "ai": "Speedup vs OPS"}[panel]
        draw_scatter(ax, d, y_of=failmode_ylab, y_order=FAILMODE_ORDER,
                     metric_col=metric, xlabel=xlabel, ylabel="Failure Mode")
    ax.set_title(PANEL_TITLE[(fig_id, panel)], fontsize=12)


def all_arms(df: pd.DataFrame, fig_id: str) -> list[str]:
    return arm_order(df[df.fig == fig_id])


# --------------------------------------------------------------------------- #
def plot_three_panel(df: pd.DataFrame, fig_id: str) -> None:
    """Composite in the paper's panel order (synthetic | DC | AI), with the arm
    legend along the bottom -- plus each panel again on its own."""
    panels = ["micro", "dc", "ai"]
    if df[df.fig == fig_id].empty:
        print(f"skip {fig_id}: no rows")
        return

    fig, axes = plt.subplots(1, 3, figsize=(16.5, 5.2),
                             gridspec_kw=dict(width_ratios=[1.05, 1, 1]))
    for i, (ax, panel) in enumerate(zip(axes, panels)):
        draw_panel(ax, df, fig_id, panel)
        if i:   # only the leftmost panel of a composite carries the y title
            ax.set_ylabel("")

    arms = all_arms(df, fig_id)
    fig.legend(handles=handles_for(arms), loc="lower center",
               ncol=min(len(arms), 7), fontsize=11, frameon=False,
               bbox_to_anchor=(0.5, 0.0))
    fig.suptitle(CAPTION[fig_id] + "\n" + SUBCAP, fontsize=11.5, y=0.995,
                 va="top")
    fig.tight_layout(rect=(0, 0.07, 1, 0.93))
    fig.savefig(PLOTS_DIR / f"{fig_id}_all.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {fig_id}_all.png")

    for panel in panels:
        w, h = (7.0, 6.4) if fig_id == "fig7" or panel == "micro" else (7.0, 4.4)
        fig, ax = plt.subplots(figsize=(w, h))
        draw_panel(ax, df, fig_id, panel)
        fig.legend(handles=handles_for(arms), loc="lower center",
                   ncol=min(len(arms), 4), fontsize=9, frameon=False,
                   bbox_to_anchor=(0.5, -0.02))
        fig.suptitle(CAPTION[fig_id].split("—")[0].strip(), fontsize=11,
                     y=0.995, va="top")
        fig.tight_layout(rect=(0, 0.10, 1, 0.95))
        fig.savefig(PLOTS_DIR / f"{fig_id}_{panel}.png", dpi=150,
                    bbox_inches="tight")
        plt.close(fig)
    print(f"wrote {fig_id}_{{micro,dc,ai}}.png")


# --------------------------------------------------------------------------- #
# fig8: Max FCT vs cable-failure % (fig_8_extreme_failures.py inline)
# --------------------------------------------------------------------------- #
def plot_fig8(df: pd.DataFrame) -> None:
    d = df[df.fig == "fig8"].copy()
    if d.empty:
        print("skip fig8")
        return
    d["pct"] = d.condition.str.extract(r"fail(\d+)").astype(int)
    style = arm_style()
    xs = sorted(d.pct.unique())

    file_size = 33554432
    ideal0 = (file_size * 8 / 400 / 1000) + 20
    ideal = [ideal0 * (10 / (10 - p / 10)) if p < 100 else np.nan for p in xs]

    # REPS + ideal set the visible range; OPS collapses onto the 90 ms sim cap
    # (flows never finish) and would flatten every other curve.
    ytop = max(d.loc[d.arm != "ops", "max_fct_us"].max(), np.nanmax(ideal)) * 1.25

    fig, ax = plt.subplots(figsize=(7.4, 3.6))
    arms = arm_order(d)
    for arm in arms:
        s = d[d.arm == arm].sort_values("pct")
        st = style[arm]
        ax.plot(s.pct, s.max_fct_us, st["ls"], marker=st["marker"],
                color=st["color"], lw=2.2, ms=7)
    ax.plot(xs, ideal, ":", color="#e7298a", lw=2, marker="^", ms=6)

    # % slowdown vs ideal at each B=8 point (the paper's default buffer)
    for _, r in d[d.arm == "reps_b8"].sort_values("pct").iterrows():
        sd = max((r.max_fct_us / ideal[xs.index(r.pct)] - 1) * 100, 1)
        ax.annotate(f"{sd:.0f}%", (r.pct, r.max_fct_us),
                    textcoords="offset points", xytext=(0, 7), ha="center",
                    fontsize=8, color=style["reps_b8"]["color"])
    off = d[(d.arm == "ops") & (d.max_fct_us > ytop)]
    if len(off):
        ax.text(0.30, 0.95,
                f"OPS off-scale: {off.max_fct_us.min()/1000:.0f}–"
                f"{off.max_fct_us.max()/1000:.0f} ms (flows hit the 90 ms sim cap)",
                transform=ax.transAxes, fontsize=8, color=OPS_COLOR, va="top")
    ax.set_ylim(0, ytop)
    ax.set_xlabel("Network Cables Failure Percentage (%)", fontsize=13)
    ax.set_ylabel("Max FCT (μs)", fontsize=13)
    ax.set_xticks(xs)
    ax.grid(True, which="both", ls=":", lw=0.75, alpha=0.75)

    handles = handles_for(arms) + [
        plt.Line2D([], [], color="#e7298a", ls=":", marker="^", lw=2, label="ideal")]
    fig.legend(handles=handles, loc="lower center", ncol=5, fontsize=9,
               frameon=False, bbox_to_anchor=(0.5, -0.03))
    fig.suptitle(CAPTION["fig8"] + "\n" + SUBCAP, fontsize=11, y=0.995, va="top")
    fig.tight_layout(rect=(0, 0.13, 1, 0.93))
    fig.savefig(PLOTS_DIR / "fig8_failures.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("wrote fig8_failures.png")


# --------------------------------------------------------------------------- #
def legend_and_doc(df: pd.DataFrame) -> None:
    style = arm_style()
    order = arm_order(df)
    fig, ax = plt.subplots(figsize=(4.2, 0.4 + 0.3 * len(order)))
    ax.axis("off")
    ax.legend(handles=handles_for(order), loc="center", frameon=False,
              title="exp26 arms (all -use_srv6 -paths N)")
    fig.savefig(PLOTS_DIR / "legend_arms.png", dpi=150, bbox_inches="tight")
    plt.close(fig)

    lines = [
        "# exp26 plot legend",
        "",
        "Every arm runs with `-use_srv6` and `-paths <n_paths>` (distinct physical",
        "paths for the panel topology: fat_tree_32=4, fat_tree_128_2t=8,",
        "fat_tree_128_3t=16, fat_tree_1024_2t=32).",
        "",
        "| arm | flags added vs the paper command | colour | marker |",
        "|-----|----------------------------------|--------|--------|",
        f"| `ops` | `-load_balancing_algo oblivious -use_srv6 -paths N` | {OPS_COLOR} (orange) | square, dashed |",
    ]
    for a in order:
        if a == "ops":
            continue
        b = a[len("reps_b"):]
        hexc = "#%02x%02x%02x" % tuple(int(255 * x) for x in style[a]["color"][:3])
        lines.append(f"| `{a}` | `-load_balancing_algo freezing -use_srv6 -paths N "
                     f"-reps_buffer_size {b}` | {hexc} | X, solid |")
    lines += [
        "",
        "A given `B` keeps the same colour in every figure. Not every figure runs",
        "every `B` -- the ladder stops at the topology's path count.",
        "",
        "The paper's fig_2 / fig_4 micro panels plot **Speedup vs ECMP**; exp26 has",
        "no ECMP arm, so the baseline is the `ops` arm and the axis reads",
        "**Speedup vs OPS**. fig_7 already uses OPS as its baseline in the paper.",
        "dc panels show absolute Average FCT; ai panels show absolute collective",
        "runtime -- no baseline.",
        "",
        "A red `OPS finished x/y flows` note marks rows where the OPS arm stalled on",
        "flows every REPS arm completed; its FCT is then measured over the finished",
        "subset only, so the speedup drawn on that row is a lower bound.",
        "",
        "fig8 keeps the paper's analytic `ideal` line",
        "(`33 MiB / 400 Gbps + 20 us`, scaled `10/(10-fail%)`) and the per-point",
        "% slowdown-vs-ideal annotations (shown for B=8, the paper's default).",
    ]
    (PLOTS_DIR / "LEGEND.md").write_text("\n".join(lines) + "\n")
    print("wrote legend_arms.png + LEGEND.md")


def main() -> None:
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    df = _load()
    for fig_id in ("fig2", "fig4", "fig7"):
        plot_three_panel(df, fig_id)
    plot_fig8(df)
    legend_and_doc(df)


if __name__ == "__main__":
    main()
