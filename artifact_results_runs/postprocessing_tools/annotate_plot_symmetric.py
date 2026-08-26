"""
Generic annotated re-plot for anything routed through plot_symmetric.py
(fig_2/4/7's "microbenchmarks" panel, and fig_5's bg-traffic panels).

Same root-cause fix as fig_5: plot_symmetric.py positions its LB-name legend at
bbox_to_anchor=(-0.71, 1.8) -- off-canvas -- which savefig's bbox_inches='tight'
fails to capture (confirmed: legend missing from the ORIGINAL un-annotated PNGs too).
Source-patches the legend position on-canvas (right of axes), widens the figure to
fit it, passes bbox_extra_artists explicitly (tight-bbox alone still dropped it even
on-canvas), and adds a headline. No re-simulation -- reuses whatever input_folder_exp
already has on disk. Never touches artifact_scripts/, artifact_results/, or the
original plot_symmetric.py file.

Usage: python3 annotate_plot_symmetric.py <datacenter_dir> <input_folder_exp> <out_dir> <out_base> <headline> [bg_type]
  bg_type: optional; if given, passes --bg_mode --bg_type <bg_type> (fig_5's use case)
"""
import os
import sys


def main():
    if len(sys.argv) not in (6, 7):
        print(__doc__)
        sys.exit(1)
    datacenter_dir, input_folder_exp, out_dir, out_base, headline = sys.argv[1:6]
    bg_type = sys.argv[6] if len(sys.argv) == 7 else None
    os.makedirs(out_dir, exist_ok=True)

    src_path = os.path.join(datacenter_dir, "plot_symmetric.py")
    with open(src_path, 'r') as f:
        src = f.read()

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
        f'_headline_artist = plt.gcf().suptitle({headline!r}, fontsize=12, y=1.05)\n'
        f'plt.savefig({out_png!r}, bbox_inches=\'tight\', bbox_extra_artists=(lb_name_legend, _headline_artist))',
    )

    argv = [
        "plot_symmetric.py",
        "--input_folder_exp", input_folder_exp,
        "--name", "notrim", "--dont_show",
        "--save_folder", out_dir, "--filename", out_base,
    ]
    if bg_type is not None:
        argv[1:1] = ["--bg_mode", "--bg_type", str(bg_type)]
    sys.argv = argv
    os.chdir(datacenter_dir)
    exec(compile(src, src_path, 'exec'), {'__name__': '__main__'})
    print(f"wrote {out_png}")


if __name__ == '__main__':
    main()
