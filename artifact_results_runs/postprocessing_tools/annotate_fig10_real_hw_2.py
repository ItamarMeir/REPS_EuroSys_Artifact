"""
Annotated re-plot of fig_10_real_hw_2 (asymmetric_fct.png + failures.png).

fig_10_real_hw_2.py is pure plotting from hardcoded literal data (no os.system/htsim
calls, no file reads) so it's safe to source-patch and exec in-process: legend gets
enabled + moved outside the axes, a headline is added, savefig is redirected to
out_dir (PNG-only), and the directory-creation loop (which targets artifact_results/)
is stripped since it's unneeded (nothing is read from disk).

Never touches artifact_scripts/ or artifact_results/ — reads the original script as
text only, execs a patched in-memory copy.

Usage: python3 annotate_fig10_real_hw_2.py <artifact_scripts_dir> <out_dir> <headline1> <headline2>
"""
import os
import re
import sys


def main():
    if len(sys.argv) != 5:
        print(__doc__)
        sys.exit(1)
    scripts_dir, out_dir, headline1, headline2 = sys.argv[1:5]
    os.makedirs(out_dir, exist_ok=True)

    src_path = os.path.join(scripts_dir, "fig_10_real_hw_2.py")
    with open(src_path, 'r') as f:
        src = f.read()

    # Strip the directory-creation loop that targets artifact_results/ (unneeded: no
    # file reads happen anywhere in this script).
    src = re.sub(
        r"# Ensure output directories exist\nfor directory in \[\n(?:.*\n)*?\]:\n(?:[ \t]*os\.makedirs.*\n)?",
        "",
        src,
        count=1,
    )

    # Enable + reposition the suppressed legend on panel 1.
    src = src.replace(
        "plt.legend([], [], frameon=False)",
        "plt.legend(loc='upper left', bbox_to_anchor=(1.02, 1.0), borderaxespad=0, frameon=True)",
    )

    # Panel 2's bars have no `label=` at all -> add a legend built from the bar handles.
    src = src.replace(
        'bars = ax.bar(x, values, color=[static_color_mapping["OPS"], static_color_mapping["REPS"]], linewidth=2.2)',
        'bars = ax.bar(x, values, color=[static_color_mapping["OPS"], static_color_mapping["REPS"]], linewidth=2.2)\n'
        "ax.legend(bars, x_labels, loc='upper left', bbox_to_anchor=(1.02, 1.0), borderaxespad=0, frameon=True)",
    )

    out_png1 = os.path.join(out_dir, "asymmetric_fct_annotated.png").replace("\\", "/")
    out_png2 = os.path.join(out_dir, "real_hw_packet_drops_annotated.png").replace("\\", "/")

    # Redirect savefig targets; drop the .pdf saves.
    src = src.replace(
        '''plt.savefig("../artifact_results/fig_10_real_hw_2/plots/asymmetric_fct.png", bbox_inches='tight')\n'''
        '''plt.savefig("../artifact_results/fig_10_real_hw_2/plots/asymmetric_fct.pdf", bbox_inches='tight')''',
        f'''plt.gcf().suptitle({headline1!r}, fontsize=12, y=1.03)\n'''
        f'''plt.savefig("{out_png1}", bbox_inches='tight')''',
    )
    src = src.replace(
        """plt.savefig('../artifact_results/fig_10_real_hw_2/plots/failures.png', dpi=300, bbox_inches='tight')\n"""
        """plt.savefig('../artifact_results/fig_10_real_hw_2/plots/failures.pdf', dpi=300, bbox_inches='tight')""",
        f'''plt.gcf().suptitle({headline2!r}, fontsize=12, y=1.03)\n'''
        f'''plt.savefig("{out_png2}", dpi=300, bbox_inches='tight')''',
    )

    exec(compile(src, src_path, 'exec'), {'__name__': '__main__'})
    print(f"wrote {out_png1}")
    print(f"wrote {out_png2}")


if __name__ == '__main__':
    main()
