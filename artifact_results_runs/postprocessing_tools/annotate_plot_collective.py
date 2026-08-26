"""
Annotated re-plot for anything routed through plot_collective.py (fig_2/4/7's
"ai"/collective panel). Its ax.legend(...) call is commented out entirely -- same bug
pattern as fig_1/3/6. Source-patches it back in (moved outside the axes) and adds a
headline. No re-simulation -- reuses whatever input_folder_exp already has on disk.
Never touches artifact_scripts/, artifact_results/, or the original plot_collective.py.

Usage: python3 annotate_plot_collective.py <datacenter_dir> <input_folder_exp> <out_dir> <out_base> <headline>
"""
import os
import sys


def main():
    if len(sys.argv) != 6:
        print(__doc__)
        sys.exit(1)
    datacenter_dir, input_folder_exp, out_dir, out_base, headline = sys.argv[1:6]
    os.makedirs(out_dir, exist_ok=True)

    src_path = os.path.join(datacenter_dir, "plot_collective.py")
    with open(src_path, 'r') as f:
        src = f.read()

    src = src.replace(
        "#ax.legend(ncol=4, loc='lower center', bbox_to_anchor=(0.50, 0.95), frameon=False)",
        "ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1.0), fontsize=10, borderaxespad=0, frameon=True)",
    )
    src = src.replace(
        'fig, ax = plt.subplots(figsize=(5.5, 3.5))',
        'fig, ax = plt.subplots(figsize=(7.5, 3.5))',
    )

    out_png = os.path.join(out_dir, f"{out_base}_annotated.png").replace("\\", "/")
    src = src.replace(
        'plt.savefig(f"{args.save_folder}/{output_name}.png", bbox_inches=\'tight\')\n'
        'plt.savefig(f"{args.save_folder}/{output_name}.pdf", bbox_inches=\'tight\')',
        f'_headline_artist = plt.gcf().suptitle({headline!r}, fontsize=12, y=1.05)\n'
        f'plt.savefig({out_png!r}, bbox_inches=\'tight\', bbox_extra_artists=(_headline_artist,))',
    )

    sys.argv = [
        "plot_collective.py",
        "--input_folder_exp", input_folder_exp,
        "--name", "notrim", "--dont_show",
        "--save_folder", out_dir, "--filename", out_base,
    ]
    os.chdir(datacenter_dir)
    exec(compile(src, src_path, 'exec'), {'__name__': '__main__'})
    print(f"wrote {out_png}")


if __name__ == '__main__':
    main()
