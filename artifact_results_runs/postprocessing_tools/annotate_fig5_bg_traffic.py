"""
Annotated re-plot of fig_5_bg_traffic (main_traffic.png / bg_traffic.png).

Root cause of the missing legend: plot_symmetric.py (htsim/sim/datacenter/) positions
the LB-name legend at bbox_to_anchor=(-0.71, 1.8) with loc='upper left' -- far outside
the axes -- which gets clipped out of the saved PNG instead of being captured by
bbox_inches='tight'. Confirmed the ORIGINAL (un-annotated) PNG already lacks the legend,
independent of our headline-overlay tooling.

Fix: source-patch plot_symmetric.py in memory (move the legend to an on-canvas position
to the right of the axes) and exec it directly, reusing the sim data already generated
by fig_5_bg_traffic.py under htsim/sim/datacenter/bg_run_128symm_notrim_synth/ (no
re-simulation). Adds a headline too. Never touches artifact_scripts/, artifact_results/,
or the original plot_symmetric.py file.

Usage: python3 annotate_fig5_bg_traffic.py <datacenter_dir> <input_folder_exp> <bg_type> <out_dir> <out_base> <headline>
Example:
  python3 annotate_fig5_bg_traffic.py /workspace/htsim/sim/datacenter \
      /workspace/htsim/sim/datacenter/bg_run_128symm_notrim_synth 0 \
      /workspace/artifact_results_runs/quick/postprocessed_plots main_traffic 'Fig 5 - ...'
"""
import os
import sys


def main():
    if len(sys.argv) != 7:
        print(__doc__)
        sys.exit(1)
    datacenter_dir, input_folder_exp, bg_type, out_dir, out_base, headline = sys.argv[1:7]
    os.makedirs(out_dir, exist_ok=True)

    src_path = os.path.join(datacenter_dir, "plot_symmetric.py")
    with open(src_path, 'r') as f:
        src = f.read()

    # Move the LB-name legend from an off-canvas position (clipped out of the saved
    # PNG) to just outside the right edge of the axes.
    src = src.replace(
        "    bbox_to_anchor=(-0.71, 1.8),  # Adjusted positioning for the LB Name legend\n"
        "    loc='upper left',\n"
        "    fontsize=16.5,  # Increased legend font size\n"
        "    title_fontsize='15',  # Increased legend title font size\n"
        "    ncol=5,  # Split legend into 2 columns\n",
        "    bbox_to_anchor=(1.02, 1.0),\n"
        "    loc='upper left',\n"
        "    fontsize=11,\n"
        "    title_fontsize='11',\n"
        "    ncol=1,\n"
        "    borderaxespad=0,\n",
    )

    src = src.replace(
        "plt.figure(figsize=(5.5, 3.65))  # Adjusted figure size for better readability",
        "plt.figure(figsize=(7.5, 3.65))  # widened to fit legend outside axes",
    )

    out_png = os.path.join(out_dir, f"{out_base}_annotated.png").replace("\\", "/")
    src = src.replace(
        'plt.savefig(f"{args.save_folder}/{output_name}.png", bbox_inches=\'tight\')\n'
        'plt.savefig(f"{args.save_folder}/{output_name}.pdf", bbox_inches=\'tight\')',
        f'plt.gcf().suptitle({headline!r}, fontsize=12, y=1.05)\n'
        f'plt.savefig({out_png!r}, bbox_inches=\'tight\', bbox_extra_artists=(lb_name_legend,))',
    )

    sys.argv = [
        "plot_symmetric.py",
        "--bg_mode", "--bg_type", str(bg_type),
        "--input_folder_exp", input_folder_exp,
        "--name", "notrim", "--dont_show",
        "--save_folder", out_dir, "--filename", out_base,
    ]
    os.chdir(datacenter_dir)
    exec(compile(src, src_path, 'exec'), {'__name__': '__main__'})
    print(f"wrote {out_png}")


if __name__ == '__main__':
    main()
