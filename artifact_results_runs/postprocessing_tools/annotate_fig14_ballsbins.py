"""
Annotated re-plot of fig_14_ballsbins (oblivious_vs_reps_balls_bins_rounds.png).

Original script builds a real legend (line 178: plt.legend(ncol=2)) then immediately
overwrites it with an empty one (line 183: plt.legend('', frameon=False)) right before
savefig -- the legend never reaches the PNG. Since all 8 "Oblivious Output Port N" lines
share one color/style (and same for the 8 REPS lines), a per-port legend would be 17
redundant entries; this collapses it to 3: Oblivious, REPS, Threshold.

Pure Python, no simulation/file I/O (self-contained model) -- safe to source-patch and
exec directly. Never touches artifact_scripts/ or artifact_results/.

Usage: python3 annotate_fig14_ballsbins.py <artifact_scripts_dir> <out_dir> <headline>
"""
import os
import sys


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    scripts_dir, out_dir, headline = sys.argv[1:4]
    os.makedirs(out_dir, exist_ok=True)

    src_path = os.path.join(scripts_dir, "fig_14_ballsbins.py")
    with open(src_path, 'r') as f:
        src = f.read()

    # Collapse the per-port duplicate labels to one legend entry per series.
    src = src.replace(
        "    plt.plot(range(rounds), queue_sizes_oblivious[port], \n"
        "             label=f'Oblivious Output Port {port}', \n"
        "             color=dark2_hex_colors[1], linestyle='--', linewidth=2.5)",
        "    plt.plot(range(rounds), queue_sizes_oblivious[port], \n"
        "             label=('Oblivious' if port == 0 else None), \n"
        "             color=dark2_hex_colors[1], linestyle='--', linewidth=2.5)",
    )
    src = src.replace(
        "    plt.plot(range(rounds), queue_sizes_reps[port], \n"
        "             label=f'REPS Output Port {port}', \n"
        "             color=dark2_hex_colors[0], linestyle='-', linewidth=2.5)",
        "    plt.plot(range(rounds), queue_sizes_reps[port], \n"
        "             label=('REPS' if port == 0 else None), \n"
        "             color=dark2_hex_colors[0], linestyle='-', linewidth=2.5)",
    )

    # Keep the real legend, drop the empty one that overwrote it.
    src = src.replace(
        "plt.legend(ncol=2)\n"
        "plt.grid(True, which='both', linestyle=':', linewidth=0.75, alpha=0.75)  # Dotted lines with reduced visibility\n"
        "\n"
        "# Adjust layout to avoid clipping\n"
        "plt.tight_layout()\n"
        "plt.legend('', frameon=False)",
        "plt.grid(True, which='both', linestyle=':', linewidth=0.75, alpha=0.75)  # Dotted lines with reduced visibility\n"
        "plt.tight_layout()\n"
        "plt.legend(loc='upper left', bbox_to_anchor=(1.02, 1.0), ncol=1, borderaxespad=0, frameon=True)",
    )

    out_png = os.path.join(out_dir, "oblivious_vs_reps_balls_bins_rounds_annotated.png").replace("\\", "/")
    src = src.replace(
        'plt.savefig("../artifact_results/fig_14_ballsbins/plots/oblivious_vs_reps_balls_bins_rounds.png", bbox_inches=\'tight\')\n'
        'plt.savefig("../artifact_results/fig_14_ballsbins/plots/oblivious_vs_reps_balls_bins_rounds.pdf", bbox_inches=\'tight\')',
        f'plt.gcf().suptitle({headline!r}, fontsize=12, y=1.05)\n'
        f'plt.savefig({out_png!r}, bbox_inches=\'tight\')',
    )

    exec(compile(src, src_path, 'exec'), {'__name__': '__main__'})
    print(f"wrote {out_png}")


if __name__ == '__main__':
    main()
