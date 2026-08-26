"""
Annotated re-plot of fig_11_ack_compression (both panels).

Panel 2 (compressed_acks_failures.png) has its legend call commented out in the
original script -- same bug pattern as fig_1/3/6. Source-patches the original script
in memory: neutralizes os.system (reuses .out files already on disk from the base
sim run, no re-simulation), redirects data reads + plot writes to results_dir/out_dir,
enables panel 2's legend, adds a headline to both, PNG-only output. Never touches
artifact_scripts/ or artifact_results/.

Usage: python3 annotate_fig11_ack_compression.py <artifact_scripts_dir> <results_dir> <out_dir> <headline1> <headline2>
"""
import os
import sys


def main():
    if len(sys.argv) != 6:
        print(__doc__)
        sys.exit(1)
    scripts_dir, results_dir, out_dir, headline1, headline2 = sys.argv[1:6]
    os.makedirs(out_dir, exist_ok=True)

    src_path = os.path.join(scripts_dir, "fig_11_ack_compression.py")
    with open(src_path, 'r') as f:
        src = f.read()

    # Redirect all data/plot paths at this fig's results dir instead of the live
    # artifact_results/ tree.
    results_dir_posix = results_dir.replace("\\", "/")
    src = src.replace(
        "../artifact_results/fig_11_ack_compression",
        f"{results_dir_posix}/fig_11_ack_compression",
    )

    # Skip re-simulation: .out files already exist from the base run.
    src = src.replace("import os\n", "import os\nos.system = lambda *a, **k: 0\n", 1)

    # Enable panel 2's suppressed legend (same handles/position as panel 1).
    src = src.replace(
        "# plt.legend(handles=legend_elements, loc='lower right', bbox_to_anchor=(1.04, -0.05), fontsize=11, ncol=1, frameon=False)",
        "plt.legend(handles=legend_elements, loc='lower right', bbox_to_anchor=(1.04, -0.35), fontsize=11, ncol=8, frameon=False)",
    )

    out_png1 = os.path.join(out_dir, "ack_compression_normal_annotated.png").replace("\\", "/")
    out_png2 = os.path.join(out_dir, "compressed_acks_failures_annotated.png").replace("\\", "/")

    src = src.replace(
        f"plt.savefig('{results_dir_posix}/fig_11_ack_compression/plots/ack_compression_normal.png', dpi=300, bbox_inches='tight')\n"
        f"plt.savefig('{results_dir_posix}/fig_11_ack_compression/plots/ack_compression_normal.pdf', dpi=300, bbox_inches='tight')",
        f"plt.gcf().suptitle({headline1!r}, fontsize=11, y=1.35)\n"
        f"plt.savefig({out_png1!r}, dpi=300, bbox_inches='tight')",
    )
    src = src.replace(
        f"plt.savefig('{results_dir_posix}/fig_11_ack_compression/plots/compressed_acks_failures.png', dpi=300, bbox_inches='tight')\n"
        f"plt.savefig('{results_dir_posix}/fig_11_ack_compression/plots/compressed_acks_failures.pdf', dpi=300, bbox_inches='tight')",
        f"plt.gcf().suptitle({headline2!r}, fontsize=11, y=1.35)\n"
        f"plt.savefig({out_png2!r}, dpi=300, bbox_inches='tight')",
    )

    exec(compile(src, src_path, 'exec'), {'__name__': '__main__'})
    print(f"wrote {out_png1}")
    print(f"wrote {out_png2}")


if __name__ == '__main__':
    main()
