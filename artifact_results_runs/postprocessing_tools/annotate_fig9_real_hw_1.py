"""
Annotated re-plot of fig_9_real_hw_1 (real-hardware goodput bar charts).

Original script sets label='OPS'/'REPS' on the bars but never calls ax.legend().
Data is hardcoded literals in the original script (real hardware measurements, not
htsim output) — reproduced here verbatim. Adds legend + headline to both panels.

Does NOT touch artifact_scripts/ or artifact_results/.

Usage: python3 annotate_fig9_real_hw_1.py <out_dir> <headline1> <headline2>
"""
import os
import sys
import numpy as np
import matplotlib.pyplot as plt


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    out_dir, headline1, headline2 = sys.argv[1:4]
    os.makedirs(out_dir, exist_ok=True)

    plt.rcParams.update({
        'axes.titlesize': 16, 'axes.labelsize': 14, 'xtick.labelsize': 10.6,
        'ytick.labelsize': 10.6, 'legend.fontsize': 10, 'figure.titlesize': 13,
        'grid.alpha': 0.8, 'grid.color': '#cccccc', 'axes.grid': True,
    })
    static_color_mapping = {'OPS': '#d95f02', 'REPS': '#e6ab02'}

    # --- Panel 1: symmetric, two switch setups ---
    x_labels = ['Switch setup-1', 'Switch setup-2']
    reps = [86.5, 96.75]
    ops = [96.8, 93.3]
    reps_min = [86.3, 96.71]
    reps_max = [86.9, 96.76]
    ops_min = [96.6, 93.0]
    ops_max = [96.9, 93.6]
    x = np.arange(len(x_labels))
    width = 0.4
    reps_errors = [np.array(reps) - np.array(reps_min), np.array(reps_max) - np.array(reps)]
    ops_errors = [np.array(ops) - np.array(ops_min), np.array(ops_max) - np.array(ops)]

    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    ax.bar(x - width / 2, ops, width, label='OPS', color=static_color_mapping["OPS"], linewidth=2.2)
    ax.bar(x + width / 2, reps, width, label='REPS', color=static_color_mapping["REPS"], linewidth=2.2)
    ax.errorbar(x - width / 2, ops, yerr=ops_errors, fmt='none', ecolor="black", capsize=5, elinewidth=3)
    ax.errorbar(x + width / 2, reps, yerr=reps_errors, fmt='none', ecolor="black", capsize=5, elinewidth=3)
    ax.axhline(y=100, color='gray', linestyle='--', linewidth=1.5)
    ax.set_ylabel('Avg. Per-Flow Goodput (Gbps)', fontsize=12.8)
    ax.set_xlabel('Switch Setup', fontsize=13.5)
    ax.set_xticks(x)
    ax.set_xticklabels(x_labels)
    ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1.0), fontsize=10,
              frameon=True, borderaxespad=0)
    plt.ylim(0, 120)
    plt.grid(True, which='both', linestyle=':', linewidth=0.75, alpha=0.75)
    fig.suptitle(headline1, fontsize=11, y=1.03)
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, "symmetric_annotated.png"), dpi=300, bbox_inches='tight')

    # --- Panel 2: asymmetric, single comparison ---
    x_labels2 = ['OPS', 'REPS']
    reps2 = [71.5]
    ops2 = [51.8]
    reps_max2 = [72.1]
    reps_min2 = [71.3]
    ops_min2 = [51.6]
    ops_max2 = [52]
    x2 = np.arange(len(x_labels2))
    values = [ops2[0], reps2[0]]
    errors = [
        [ops2[0] - ops_min2[0], reps2[0] - reps_min2[0]],
        [ops_max2[0] - ops2[0], reps_max2[0] - reps2[0]],
    ]

    fig2, ax2 = plt.subplots(figsize=(4.6, 3.2))
    bars = ax2.bar(x2, values, color=[static_color_mapping["OPS"], static_color_mapping["REPS"]], linewidth=2.2)
    ax2.errorbar(x2, values, yerr=errors, fmt='none', ecolor='black', capsize=5, elinewidth=3)
    ax2.axhline(y=75, color='gray', linestyle='--', linewidth=1.5)
    ax2.set_ylabel('Avg. Per-Flow Goodput (Gbps)', fontsize=12.8)
    ax2.set_xlabel('Load Balancing Algorithm', fontsize=13.5)
    ax2.set_xticks(x2)
    ax2.set_xticklabels(x_labels2)
    ax2.legend(bars, x_labels2, loc='upper left', bbox_to_anchor=(1.02, 1.0),
               fontsize=10, frameon=True, borderaxespad=0)
    plt.ylim(0, 100)
    plt.grid(True, which='both', linestyle=':', linewidth=0.75, alpha=0.75)
    fig2.suptitle(headline2, fontsize=11, y=1.03)
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, "asymmetric_annotated.png"), dpi=300, bbox_inches='tight')

    print("wrote symmetric_annotated + asymmetric_annotated")


if __name__ == '__main__':
    main()
