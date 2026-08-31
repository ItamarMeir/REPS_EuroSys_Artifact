#!/usr/bin/env python3
"""
plot_fig6.py -- reproduction of paper fig_6_failures_micro
(artifact_results_runs/full/fig_6_failures_micro/plots/failures_micro.png).

Paper form: stacked dual-axis panels, one per LB arm (paper has 2:
"Oblivious Packet Spraying" and "REPS"); per panel x = Time (us), left y =
Output Port Utilisation (Gbps), right y = Queue Size (KB), one colour per
leaf-0 uplink port LS0->US{0..3}, grey dotted reference lines at 20*MTU and
80*MTU KB. Single degraded link, -failed 42, seed 5, test_symm32.cm.

exp26 change: one panel per arm -> ops, reps_b1, reps_b2, reps_b4, reps_b8,
reps_b16 (6 stacked panels), same axes.

**The utilisation (left) axis is omitted.** exp26's fig6 runs use -use_srv6,
which routes every packet on an explicit source route and bypasses
FatTreeSwitch::getEgressPort() -- the only place -log_link writes the
port/ and link_util/ per-port packet logs (fat_tree_switch.cpp:449-462).
So port util is not recoverable from these runs; only the queue-size logs
(written by the queue objects themselves) survive. Each panel therefore
shows just Queue Size (KB) vs time, with the paper's two reference lines.

Reads  runs/fig6/test_symm32/failed42/<arm>/raw_output/queueSize/queueSizeLS0->US{k}.txt
       (2-col CSV: <ns>,<raw>; KB = raw * 400/8/1e3, paper fig_6 line 103)
Writes plots/fig6_trace.png
       data/fig6_timeseries.csv.gz
"""
from __future__ import annotations

import csv
import gzip
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR = SCRIPT_DIR.parent
RUN_ROOT = EXP_DIR / "runs" / "fig6" / "test_symm32" / "failed42"
PLOTS_DIR = EXP_DIR / "plots"
DATA_DIR = EXP_DIR / "data"

UPLINKS = [0, 1, 2, 3]
KB = 400 / 8 / 1e3                       # raw -> KB (paper fig_6 line 103)
MTU = 4096
REF_LO, REF_HI = 20 * MTU / 1e3, 80 * MTU / 1e3   # -ecn 20 80 marks, in KB
DARK2 = ["#1b9e77", "#d95f02", "#7570b3", "#e7298a"]   # per-uplink, paper palette


def arm_key(arm: str):
    return (-1,) if arm == "ops" else (int(arm[len("reps_b"):]),)


def arm_title(arm: str) -> str:
    return "Oblivious Packet Spraying" if arm == "ops" else f"REPS  B={arm[6:]}"


def read_series(path: Path):
    ts, ys = [], []
    if not path.exists():
        return ts, ys
    for line in path.read_text(errors="replace").splitlines():
        p = line.split(",")
        if len(p) != 2:
            continue
        try:
            ts.append(float(p[0]) / 1000.0)   # ns -> us
            ys.append(float(p[1]) * KB)       # raw -> KB
        except ValueError:
            continue
    return ts, ys


def main() -> None:
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not RUN_ROOT.exists():
        print(f"no fig6 runs at {RUN_ROOT}")
        return

    arms = sorted((p.name for p in RUN_ROOT.iterdir() if p.is_dir()), key=arm_key)
    if not arms:
        print("no fig6 arms")
        return

    fig, axes = plt.subplots(len(arms), 1, figsize=(9, 1.9 * len(arms)),
                             sharex=True, squeeze=False)
    rows = []
    xmax = 0.0
    for ax, arm in zip(axes[:, 0], arms):
        for k in UPLINKS:
            f = RUN_ROOT / arm / "raw_output" / "queueSize" / f"queueSizeLS0->US{k}.txt"
            ts, ys = read_series(f)
            if not ts:
                continue
            xmax = max(xmax, ts[-1])
            ax.plot(ts, ys, lw=1.0, color=DARK2[k], alpha=0.85,
                    label=f"LS0->US{k}")
            for t, y in zip(ts, ys):
                rows.append({"arm": arm, "uplink": f"LS0->US{k}",
                             "t_us": round(t, 3), "queue_kb": round(y, 3)})
        ax.axhline(REF_LO, color="gray", ls=":", lw=2)
        ax.axhline(REF_HI, color="gray", ls=":", lw=2)
        ax.set_ylabel("Queue Size (KB)", fontsize=10)
        ax.set_title(arm_title(arm), fontsize=12)
        ax.grid(True, which="both", ls=":", lw=0.75, alpha=0.75)
    axes[-1, 0].set_xlabel("Time (microseconds)", fontsize=12)
    for ax in axes[:, 0]:
        ax.set_xlim(0, xmax * 1.02)
    fig.legend(handles=axes[0, 0].get_lines()[:len(UPLINKS)],
               labels=[f"LS0->US{k}" for k in UPLINKS], loc="lower center",
               ncol=len(UPLINKS), fontsize=10, frameon=False,
               bbox_to_anchor=(0.5, -0.008))
    fig.suptitle(
        "fig_6_failures_micro (paper Figure 7) —\n"
        "REPS vs. OPS in a 32 MiB permutation with two cables' failure.\n"
        "All arms use SRv6 source routing (-use_srv6) with the entropy\n"
        "domain restricted to the topology's physical paths.\n"
        "Port-utilisation axis omitted: -use_srv6 bypasses the\n"
        "-log_link port logger (see module docstring).", fontsize=9.5)
    fig.tight_layout(rect=(0, 0.02, 1, 0.965))
    fig.savefig(PLOTS_DIR / "fig6_trace.png", dpi=150)
    plt.close(fig)

    with gzip.open(DATA_DIR / "fig6_timeseries.csv.gz", "wt", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["arm", "uplink", "t_us", "queue_kb"])
        w.writeheader()
        w.writerows(rows)
    print(f"wrote fig6_trace.png + fig6_timeseries.csv.gz ({len(rows)} rows)")


if __name__ == "__main__":
    main()
