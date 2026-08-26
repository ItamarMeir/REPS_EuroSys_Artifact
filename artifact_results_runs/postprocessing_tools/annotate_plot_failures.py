"""
Generic annotated re-plot for anything routed through plot_failures.py (fig_7's
"microbenchmarks"/"dc"/"ai" panels -- all 3 go through this one script, distinguished
only by --input_folder_exp/--text).

Same root-cause bug as plot_symmetric.py: legend positioned at
bbox_to_anchor=(-0.71, 1.8) -- off-canvas, dropped by bbox_inches='tight'. Source-patches
it on-canvas, widens the figure, passes bbox_extra_artists explicitly, adds a headline.
No re-simulation -- reuses whatever input_folder_exp already has on disk. Never touches
artifact_scripts/, artifact_results/, or the original plot_failures.py file.

Usage: python3 annotate_plot_failures.py <datacenter_dir> <input_folder_exp> <text> <out_dir> <out_base> <headline>
"""
import os
import sys


def main():
    if len(sys.argv) != 7:
        print(__doc__)
        sys.exit(1)
    datacenter_dir, input_folder_exp, text, out_dir, out_base, headline = sys.argv[1:7]
    os.makedirs(out_dir, exist_ok=True)

    src_path = os.path.join(datacenter_dir, "plot_failures.py")
    with open(src_path, 'r') as f:
        src = f.read()

    src = src.replace(
        "lb_name_legend = plt.legend(\n"
        "    handles=lb_name_handles,\n"
        "    bbox_to_anchor=(-0.71, 1.8),  # Adjusted positioning for the LB Name legend\n"
        "    loc='upper left',\n"
        "    fontsize=16.5,  # Increased legend font size\n"
        "    title_fontsize='15',  # Increased legend title font size\n"
        "    ncol=len(lb_name_order),  # Split legend into 2 columns\n"
        "    markerscale=1,\n"
        "    frameon=False,\n"
        "    handletextpad=1.5\n"
        ")",
        "lb_name_legend = plt.legend(\n"
        "    handles=lb_name_handles,\n"
        "    bbox_to_anchor=(1.02, 1.0),\n"
        "    loc='upper left',\n"
        "    fontsize=11,\n"
        "    title_fontsize='11',\n"
        "    ncol=1,\n"
        "    markerscale=1,\n"
        "    frameon=True,\n"
        "    borderaxespad=0\n"
        ")",
    )
    src = src.replace(
        "fig = plt.figure(figsize=(5.5, 4.2))  # Adjusted figure size for better readability",
        "fig = plt.figure(figsize=(7.5, 4.2))  # widened to fit legend outside axes",
    )

    out_png = os.path.join(out_dir, f"{out_base}_annotated.png").replace("\\", "/")
    src = src.replace(
        'plt.savefig(f"{args.save_folder}/{output_name}.png", bbox_inches=\'tight\')\n'
        'plt.savefig(f"{args.save_folder}/{output_name}.pdf", bbox_inches=\'tight\')',
        f'_headline_artist = plt.gcf().suptitle({headline!r}, fontsize=12, y=1.05)\n'
        f'plt.savefig({out_png!r}, bbox_inches=\'tight\', bbox_extra_artists=(lb_name_legend, _headline_artist))',
    )

    sys.argv = [
        "plot_failures.py",
        "--text", text,
        "--input_folder_exp", input_folder_exp,
        "--name", "notrim", "--dont_show",
        "--save_folder", out_dir, "--filename", out_base,
    ]
    os.chdir(datacenter_dir)
    exec(compile(src, src_path, 'exec'), {'__name__': '__main__'})
    print(f"wrote {out_png}")


if __name__ == '__main__':
    main()
