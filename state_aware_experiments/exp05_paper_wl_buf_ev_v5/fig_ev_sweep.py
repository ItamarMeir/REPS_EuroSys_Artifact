#!/usr/bin/env python3
"""
fig_ev_sweep.py — exp05 Part B: REPS FREEZING EV domain sweep.

Paper workloads (perm_n128_s8388608.cm, test_symm16.cm), 2-tier 128-host topology.
Follows the paper's artifact script style — directly analogous to fig_12_evs_cc.py.

EV domain values {32, 256, 65535} match the paper's fig_12 sweep exactly.

Produces 5 figures:
  B1a  FCT CDF per EV count — perm_n128  (direct comparison with paper's fig_12)
  B1b  FCT CDF per EV count — symm16
  B2   Max FCT vs EV count  — both wl    (like fig_8)
  B3   Port utilisation per uplink        (like fig_1, routing efficiency)
  B4   cwnd time-series per EV count      (CC behaviour)
"""

import os, re, csv as csv_module
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from collections import defaultdict

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

matplotlib.rcParams['pdf.fonttype'] = 42
matplotlib.rcParams['ps.fonttype'] = 42

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT  = SCRIPT_DIR.parent.parent
HTSIM  = str(REPO_ROOT / "htsim/sim/datacenter/htsim_uec")
TOPO   = str(REPO_ROOT / "htsim/sim/datacenter/topologies/reps/fat_tree_128_1os_2t_400g.topo")
CM_DIR = REPO_ROOT / "htsim/sim/datacenter/connection_matrices"
PERM_CM = str(CM_DIR / "perm_n128_s8388608.cm")
SYMM_CM = str(CM_DIR / "test_symm16.cm")
DATA_DIR = SCRIPT_DIR / "data"
PLOT_DIR = SCRIPT_DIR / "plots"

for d in [DATA_DIR/"fct_B", DATA_DIR/"cwnd_B", DATA_DIR/"portutil_B", PLOT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── Constants ──────────────────────────────────────────────────────────────────
LINK_RATE_BPS   = 400_000_000_000
EV_VALUES       = [32, 256, 65535]                      # matches paper's fig_12
EV_LABELS       = ["32 EVs", "256 EVs", "64K EVs"]     # matching fig_12 legend
SEEDS           = [42, 43, 44]
SEVS            = [0, 1]
FLOW_SIZE_PERM  = 8_388_608    # 8 MB
FLOW_SIZE_SYMM  = 16_777_216   # 16 MB
PKT_BYTES_UTIL  = 4096
BIN_NS          = 20_000       # 20 µs bins

# Paper colour palette
DARK2 = ['#1b9e77','#d95f02','#7570b3','#e7298a','#66a61e','#e6ab02','#a6761d','#666666']
MARKERS = ['o','s','D','^','v','p','*','X']
SEV_STYLE = {0: ('-', '#2171b5', 'No failure'), 1: ('--', '#cb181d', 'Sev=1 (link fail)')}

matplotlib.rcParams['pdf.fonttype'] = 42
matplotlib.rcParams['ps.fonttype'] = 42
plt.rcParams.update({
    'axes.titlesize': 13, 'axes.labelsize': 12,
    'xtick.labelsize': 10, 'ytick.labelsize': 10,
    'legend.fontsize': 9,  'grid.alpha': 0.75,
    'grid.color': '#cccccc', 'axes.grid': True,
    'grid.linestyle': '-',
})

# ── Simulator helpers ──────────────────────────────────────────────────────────
COMMON = (
    f"-sack_threshold 4000 -end 5000 -sender_cc_only -sender_cc_algo nscc "
    f"-topo {TOPO} -linkspeed 400000 -ecn 25 76 -q 100 -cwnd 151 "
    f"-load_balancing_algo freezing -reps_buffer_size 1024 -disable_tor_ecn"
)

def fail_flags(sev):
    return "-fail_link_time 50 200 -fail_link_target 0 0" if sev == 1 else ""

def ideal_fct_us(size_bytes):
    return size_bytes * 8 / LINK_RATE_BPS * 1e6 + 4.0

# ── Parsing helpers ────────────────────────────────────────────────────────────
def get_fcts(path):
    """Parse 'finished at <us>' lines. Captures full float (e.g. 177.042 µs)."""
    fcts = []
    try:
        with open(path) as f:
            for line in f:
                m = re.search(r"finished at (\d+(?:\.\d+)?)", line)
                if m:
                    fcts.append(float(m.group(1)))
    except FileNotFoundError:
        pass
    return fcts

def parse_cwnd_file(path):
    times, cwnds = [], []
    try:
        with open(path) as f:
            reader = csv_module.DictReader(f)
            for row in reader:
                try:
                    times.append(float(row["time_us"]))
                    cwnds.append(float(row["cwnd_pkts"]))
                except (KeyError, ValueError):
                    continue
    except FileNotFoundError:
        pass
    return np.array(times), np.array(cwnds)

def parse_port_util(save_dir):
    port_file = Path(save_dir) / "port" / "portSwitch_LowerPod_0_.txt"
    pattern = re.compile(r"LS\d+->US(\d+)")
    bins = defaultdict(lambda: defaultdict(int))
    try:
        with open(port_file) as f:
            for line in f:
                ts_str = line.split(",", 1)[0]
                try:
                    ts_ns = int(ts_str)
                except ValueError:
                    continue
                m = pattern.search(line)
                if m:
                    port = int(m.group(1))
                    bins[(ts_ns // BIN_NS) * BIN_NS][port] += 1
    except FileNotFoundError:
        return {}
    result = defaultdict(list)
    for bin_ns in sorted(bins):
        for port, count in bins[bin_ns].items():
            gbps = count * PKT_BYTES_UTIL * 8 / BIN_NS
            result[port].append((bin_ns / 1000.0, gbps))
    return {p: (np.array([t for t,_ in v]), np.array([g for _,g in v]))
            for p, v in result.items()}

# ── Build commands ─────────────────────────────────────────────────────────────
fct_cmds, cwnd_cmds, portutil_cmds = [], [], []

# FCT: all ev × workload × sev × seed
for ev in EV_VALUES:
    for wl, cm in [("perm_n128", PERM_CM), ("symm16", SYMM_CM)]:
        for sev in SEVS:
            for seed in SEEDS:
                out = DATA_DIR / "fct_B" / f"ev{ev}_{wl}_sev{sev}_s{seed}.out"
                if out.exists():
                    continue
                fct_cmds.append(
                    f"{HTSIM} {COMMON} -paths {ev} "
                    f"-tm {cm} -seed {seed} {fail_flags(sev)} > {out} 2>&1"
                )

# cwnd: perm_n128, sev=1, seed=42 — for B4
for ev in EV_VALUES:
    d = DATA_DIR / "cwnd_B" / f"ev{ev}"
    d.mkdir(exist_ok=True)
    if (d / "run.out").exists():
        continue
    cwnd_cmds.append(
        f"{HTSIM} {COMMON} -paths {ev} "
        f"-tm {PERM_CM} -seed 42 {fail_flags(1)} "
        f"-log_reps_state {d/'reps_state.csv'} -log_reps_state_src 0 > {d/'run.out'} 2>&1"
    )

# Port util: symm16, seed=42, both sev — for B3
for ev in EV_VALUES:
    for sev in SEVS:
        save_dir = DATA_DIR / "portutil_B" / f"ev{ev}_sev{sev}"
        save_dir.mkdir(parents=True, exist_ok=True)
        if (save_dir / "run.out").exists():
            continue
        portutil_cmds.append(
            f"{HTSIM} {COMMON} -paths {ev} "
            f"-tm {SYMM_CM} -seed 42 {fail_flags(sev)} "
            f"-save_data_folder {save_dir} -log_link -collect_data > {save_dir}/run.out 2>&1"
        )

total = len(fct_cmds) + len(cwnd_cmds) + len(portutil_cmds)
if total:
    print(f"Launching {total} commands "
          f"({len(fct_cmds)} FCT + {len(cwnd_cmds)} cwnd + {len(portutil_cmds)} portutil) "
          f"with 4 workers ...")
    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(os.system, fct_cmds + cwnd_cmds + portutil_cmds))
    print("All runs complete.")
else:
    print("All outputs already exist — skipping runs.")

# ══════════════════════════════════════════════════════════════════════════════
# B1: FCT CDF per EV count  (directly analogous to fig_12)
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== Plotting ===")
for wl_name, wl_size in [("perm_n128", FLOW_SIZE_PERM), ("symm16", FLOW_SIZE_SYMM)]:
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.0), sharey=True)
    ideal = ideal_fct_us(wl_size)

    for ax, sev in zip(axes, SEVS):
        for i, (ev, label) in enumerate(zip(EV_VALUES, EV_LABELS)):
            all_fcts = []
            for seed in SEEDS:
                out = DATA_DIR / "fct_B" / f"ev{ev}_{wl_name}_sev{sev}_s{seed}.out"
                all_fcts.extend(get_fcts(str(out)))
            if not all_fcts:
                continue
            data_sorted = np.sort(all_fcts)
            cdf = np.arange(1, len(data_sorted) + 1) / len(data_sorted)

            # Line style matching fig_12: solid for REPS, dotted for OPS
            # Here: all are FREEZING, vary EV domain; use same colour scheme as fig_12
            ax.plot(data_sorted, cdf,
                    label=label,
                    color=DARK2[i % len(DARK2)],
                    marker=MARKERS[i % len(MARKERS)],
                    markevery=[len(data_sorted) - 1],
                    markersize=5.5, linewidth=2.0)

        ax.axvline(ideal, color='gray', linestyle=':', linewidth=1.5, alpha=0.8,
                   label=f"ideal ({ideal:.0f} µs)")
        ax.set_xlabel("Flow Completion Time (µs)", fontsize=11)
        if sev == 0:
            ax.set_ylabel("CDF", fontsize=11)
        ax.set_title("No failure" if sev == 0 else "Sev=1 (link fail t=50–200 µs)", fontsize=10)
        ax.grid(True, linestyle=':', linewidth=0.75, alpha=0.75)
        ax.set_ylim(0, 1.05)

    legend_elems = [
        Line2D([0],[0], color=DARK2[i], marker=MARKERS[i], lw=2, label=l)
        for i, l in enumerate(EV_LABELS)
    ] + [Line2D([0],[0], color='gray', lw=1.5, linestyle=':', label='ideal FCT')]
    axes[1].legend(handles=legend_elems, loc='lower right', fontsize=8,
                   ncol=2, frameon=False, bbox_to_anchor=(1, -0.35))

    fig.suptitle(f"FCT CDF — EV Domain Sweep  ({wl_name})", fontsize=11)
    fig.tight_layout()
    tag = f"B1_fct_cdf_ev_{wl_name}"
    for ext in (".png", ".pdf"):
        fig.savefig(str(PLOT_DIR / (tag + ext)), dpi=300, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved {tag}.png")

# ══════════════════════════════════════════════════════════════════════════════
# B2: Max FCT vs EV count  (like fig_8)
# ══════════════════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 2, figsize=(9, 3.2), sharey=False)

for ax, (wl_name, wl_size) in zip(axes, [("perm_n128", FLOW_SIZE_PERM), ("symm16", FLOW_SIZE_SYMM)]):
    ideal = ideal_fct_us(wl_size)

    for sev in SEVS:
        ls, color, sev_label = SEV_STYLE[sev]
        max_means, max_stds = [], []
        for ev in EV_VALUES:
            seed_maxes = []
            for seed in SEEDS:
                out = DATA_DIR / "fct_B" / f"ev{ev}_{wl_name}_sev{sev}_s{seed}.out"
                fcts = get_fcts(str(out))
                if fcts:
                    seed_maxes.append(max(fcts))
            if seed_maxes:
                max_means.append(np.mean(seed_maxes))
                max_stds.append(np.std(seed_maxes))
            else:
                max_means.append(float('nan'))
                max_stds.append(0.0)

        x = range(len(EV_VALUES))
        ax.errorbar(x, max_means, yerr=max_stds,
                    color=color, marker='o', linewidth=2.2, markersize=7,
                    linestyle=ls, label=sev_label, capsize=3)

        for i, mf in enumerate(max_means):
            if np.isnan(mf):
                continue
            slowdown = max(0.0, (mf / ideal - 1) * 100)
            ax.text(i, mf + ideal * 0.04, f"{slowdown:.0f}%",
                    fontsize=8, ha='center', va='bottom', color=color)

    ax.plot(range(len(EV_VALUES)), [ideal] * len(EV_VALUES),
            color='gray', linestyle=':', linewidth=1.5, label=f"ideal ({ideal:.0f} µs)")
    ax.set_xticks(range(len(EV_VALUES)))
    ax.set_xticklabels(EV_LABELS)
    ax.set_xlabel("EV Domain", fontsize=11)
    ax.set_ylabel("Max FCT (µs)", fontsize=11)
    ax.set_title(wl_name, fontsize=11)
    ax.legend(fontsize=8, frameon=False)
    ax.grid(True, linestyle=':', linewidth=0.75, alpha=0.75)

fig.suptitle("Max FCT vs EV Domain Size", fontsize=12)
fig.tight_layout()
for ext in (".png", ".pdf"):
    fig.savefig(str(PLOT_DIR / ("B2_max_fct_vs_ev" + ext)), dpi=300, bbox_inches='tight')
plt.close(fig)
print("  Saved B2_max_fct_vs_ev.png")

# ══════════════════════════════════════════════════════════════════════════════
# B3: Port utilisation per uplink  (like fig_1 — routing efficiency)
# Show ev=65535 vs ev=32 as 2-row × 2-col grid
# ══════════════════════════════════════════════════════════════════════════════
UPLINK_CM = plt.cm.get_cmap('tab10', 8)

fig, axes = plt.subplots(2, 2, figsize=(10, 5.5))
for row, ev in enumerate([65535, 32]):
    ev_label = "64K" if ev == 65535 else str(ev)
    for col, sev in enumerate(SEVS):
        ax = axes[row][col]
        save_dir = DATA_DIR / "portutil_B" / f"ev{ev}_sev{sev}"
        port_data = parse_port_util(save_dir)

        if not port_data:
            ax.text(0.5, 0.5, "No data", ha='center', va='center',
                    transform=ax.transAxes, fontsize=12)
        else:
            num_ports = len(port_data)
            fair_share = 400.0 / max(num_ports, 1)
            for port_id in sorted(port_data):
                t, g = port_data[port_id]
                ax.plot(t, g, color=UPLINK_CM(port_id % 8),
                        linewidth=1.5, label=f"US{port_id}", alpha=0.9)
            ax.axhline(fair_share, color='gray', linestyle='--',
                       linewidth=1.0, alpha=0.6, label="fair share")

        fail_str = "no fail" if sev == 0 else "sev=1 (link fail t=50–200 µs)"
        ax.set_title(f"EV={ev_label},  {fail_str}", fontsize=10)
        ax.set_xlim(0, 700)
        ax.set_ylim(0, 450)
        ax.set_xlabel("Time (µs)", fontsize=9)
        ax.set_ylabel("Uplink Throughput (Gbps)", fontsize=9)
        ax.grid(True, linestyle=':', linewidth=0.75, alpha=0.75)
        if row == 0 and col == 1:
            ax.legend(fontsize=7, ncol=4, loc='upper right', frameon=False)

fig.suptitle(
    "Port Utilisation per LS0 Uplink (symm16, seed=42)\n"
    "Top row: EV=64K (full diversity)   Bottom row: EV=32 (limited domain)",
    fontsize=10,
)
fig.tight_layout()
for ext in (".png", ".pdf"):
    fig.savefig(str(PLOT_DIR / ("B3_port_util_ev" + ext)), dpi=300, bbox_inches='tight')
plt.close(fig)
print("  Saved B3_port_util_ev.png")

# ══════════════════════════════════════════════════════════════════════════════
# B4: cwnd time-series per EV count  (CC behaviour)
# ══════════════════════════════════════════════════════════════════════════════
fig, ax = plt.subplots(1, 1, figsize=(7, 3.2))

for i, (ev, label) in enumerate(zip(EV_VALUES, EV_LABELS)):
    state_path = DATA_DIR / "cwnd_B" / f"ev{ev}" / "reps_state.csv"
    times, cwnds = parse_cwnd_file(state_path)
    if len(times) == 0:
        continue
    ax.plot(times, cwnds, color=DARK2[i % len(DARK2)], linewidth=1.5,
            label=label, alpha=0.9)

ax.axvline(50,  color='red',   linestyle='--', linewidth=1.0, alpha=0.7, label='link fail (t=50 µs)')
ax.axvline(200, color='green', linestyle='--', linewidth=1.0, alpha=0.7, label='link restore (t=200 µs)')
ax.set_xlabel("Time (µs)", fontsize=11)
ax.set_ylabel("cwnd (packets)", fontsize=11)
ax.set_title(
    "CC Window Time-Series — EV Domain Sweep\n"
    "(perm_n128, seed=42, sev=1)",
    fontsize=10,
)
ax.legend(fontsize=8, ncol=3, frameon=False)
ax.grid(True, linestyle=':', linewidth=0.75, alpha=0.75)

fig.tight_layout()
for ext in (".png", ".pdf"):
    fig.savefig(str(PLOT_DIR / ("B4_cwnd_timeseries_ev" + ext)), dpi=300, bbox_inches='tight')
plt.close(fig)
print("  Saved B4_cwnd_timeseries_ev.png")

print(f"\nAll Part B plots saved to {PLOT_DIR}")
