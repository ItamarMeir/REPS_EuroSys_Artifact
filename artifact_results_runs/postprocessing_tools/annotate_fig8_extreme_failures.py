"""
Annotated re-plot of fig_8_extreme_failures (Max FCT vs cable-failure %).

Original script sets label="Max FCT" on all 3 lines (duplicate label bug) and never
calls plt.legend() at all. Re-plots from the already-generated .out files with a
correct 3-entry legend (REPS/freezing, PLB, Ideal) + a headline.

Does NOT touch artifact_scripts/ or artifact_results/ — reads only. Does NOT re-run htsim.

Usage: python3 annotate_fig8_extreme_failures.py <results_dir> <out_dir> <headline>
"""
import os
import re
import sys
import numpy as np
import matplotlib.pyplot as plt

matplotlib_pdf_fonttype = 42


def get_list_fct(path):
    out = []
    try:
        with open(path) as f:
            for line in f:
                m = re.search(r"finished at (\d+)", line)
                if m:
                    out.append(float(m.group(1)))
    except FileNotFoundError:
        print(f"missing: {path}")
    return out


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    results_dir, out_dir, headline = sys.argv[1:4]
    os.makedirs(out_dir, exist_ok=True)

    data_dir = os.path.join(results_dir, "fig_8_extreme_failures", "data")
    file_size = 33554432
    ideal_fct_0 = (file_size * 8 / 400 / 1000) + 20

    x_axis = [0, 10, 20, 30, 40, 50]
    failure = [get_list_fct(os.path.join(data_dir, f"fail_{p}.out")) for p in x_axis]
    plb_failure = [get_list_fct(os.path.join(data_dir, f"plb_fail_{p}.out")) for p in x_axis]

    if any(len(f) == 0 for f in failure) or any(len(f) == 0 for f in plb_failure):
        print("some .out files missing/empty — skipping fig_8 annotation for now")
        sys.exit(0)

    max_fcts = [max(f) for f in failure]
    plb_max_fcts = [max(f) for f in plb_failure]
    ideal_fcts = [ideal_fct_0 * (10 / (10 - p / 10)) for p in x_axis]

    static_color_mapping = {'MPTCP': '#e7698a', 'PLB': '#66a61e', 'REPS': '#e6ab02'}
    lb_markers = {'MPTCP': '^', 'PLB': 'P', 'REPS': 'X'}

    plt.rcParams.update({
        'axes.titlesize': 16, 'axes.labelsize': 14, 'xtick.labelsize': 12,
        'ytick.labelsize': 12, 'legend.fontsize': 11, 'figure.titlesize': 14,
        'grid.alpha': 0.8, 'grid.color': '#cccccc', 'axes.grid': True,
    })

    fig = plt.figure(figsize=(8.5, 3.2))
    plt.plot(x_axis, max_fcts, label='REPS (freezing)', color=static_color_mapping['REPS'],
              marker=lb_markers['REPS'], linestyle='-', linewidth=2.2, markersize=7.2)
    plt.plot(x_axis, plb_max_fcts, label='PLB', color=static_color_mapping['PLB'],
              marker=lb_markers['PLB'], linestyle='-', linewidth=2.2, markersize=7.2)
    plt.plot(x_axis, ideal_fcts, label='Ideal (no congestion)', color=static_color_mapping['MPTCP'],
              marker=lb_markers['MPTCP'], linestyle='-', linewidth=2.2, markersize=7.2)

    plt.xlabel('Network Cables Failure Percentage (%)', fontsize=13)
    plt.ylabel('Max FCT (μs)', fontsize=13)
    plt.grid(True, which='both', linestyle=':', linewidth=0.75, alpha=0.75)
    plt.legend(loc='upper left', bbox_to_anchor=(1.02, 1.0), fontsize=10,
               frameon=True, borderaxespad=0)
    fig.suptitle(headline, fontsize=12, y=1.03)

    plt.tight_layout()
    out_png = os.path.join(out_dir, "failures_annotated.png")
    plt.savefig(out_png, dpi=300, bbox_inches='tight')
    print(f"wrote {out_png}")


if __name__ == '__main__':
    main()
