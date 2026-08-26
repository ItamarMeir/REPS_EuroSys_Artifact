"""
Synthesizes a standalone legend PNG (from a known color/marker mapping -- no
underlying data needed) and merges it below an already-rendered plot PNG.

Use this when the plot's own source data is gone (e.g. overwritten in a shared,
non-stage-versioned sim-output folder) so a real re-plot isn't possible, but the
color/marker mapping is hardcoded in the original script and known.

Usage: python3 merge_legend.py <src_png> <out_png> <ncol> <label1> <color1> <marker1> [<label2> <color2> <marker2> ...]
Marker is a matplotlib marker code (o, s, v, ^, P, X, D, *, h, ...) or 'line' for a
plain line swatch (no marker).
"""
import sys
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    if len(sys.argv) < 7 or (len(sys.argv) - 4) % 3 != 0:
        print(__doc__)
        sys.exit(1)
    src_png, out_png, ncol = sys.argv[1], sys.argv[2], int(sys.argv[3])
    entries = sys.argv[4:]
    triples = [entries[i:i + 3] for i in range(0, len(entries), 3)]

    img = Image.open(src_png).convert('RGB')
    w, h = img.size

    handles = []
    for label, color, marker in triples:
        if marker == 'line':
            h_ = plt.Line2D([0], [0], color=color, lw=3, label=label)
        else:
            h_ = plt.Line2D([0], [0], color=color, marker=marker, linestyle='None',
                             markersize=10, label=label)
        handles.append(h_)

    fig = plt.figure(figsize=(w / 100, 1.2))
    fig.legend(handles=handles, loc='center', ncol=ncol, frameon=True, fontsize=11)
    fig.canvas.draw()
    legend_path = out_png + ".legend_tmp.png"
    fig.savefig(legend_path, dpi=100, bbox_inches='tight')
    plt.close(fig)

    legend_img = Image.open(legend_path).convert('RGB')
    lw, lh = legend_img.size
    if lw > w:
        legend_img = legend_img.resize((w, int(lh * w / lw)))
        lw, lh = legend_img.size

    canvas = Image.new('RGB', (w, h + lh), 'white')
    canvas.paste(img, (0, 0))
    canvas.paste(legend_img, ((w - lw) // 2, h))
    canvas.save(out_png)

    import os
    os.remove(legend_path)
    print(f"wrote {out_png}")


if __name__ == '__main__':
    main()
