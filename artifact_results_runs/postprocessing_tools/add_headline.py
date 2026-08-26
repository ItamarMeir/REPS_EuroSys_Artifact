"""
Generic headline-banner overlay for plots that already have a real matplotlib legend
rendered into the PNG (fig_5, fig_10, fig_11, fig_12, fig_13, fig_14 family) — only a
figure-level headline is missing, so a full re-plot isn't needed.

Stamps a white banner + headline text across the top of the image and writes a new
PNG. Never touches the source PNG or artifact_scripts/artifact_results/. PNG-only,
matching the annotated-plots convention (no PDF).

Usage: python3 add_headline.py <src_png> <out_png> <headline>
"""
import sys
from PIL import Image, ImageDraw, ImageFont


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    src_png, out_png, headline = sys.argv[1:4]

    img = Image.open(src_png).convert('RGB')
    w, h = img.size

    font_size = max(14, w // 40)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", font_size)
    except OSError:
        font = ImageFont.load_default()

    draw_tmp = ImageDraw.Draw(img)
    bbox = draw_tmp.multiline_textbbox((0, 0), headline, font=font)
    text_h = bbox[3] - bbox[1]
    banner_h = text_h + 24

    canvas = Image.new('RGB', (w, h + banner_h), 'white')
    canvas.paste(img, (0, banner_h))
    draw = ImageDraw.Draw(canvas)
    draw.text((12, 12), headline, fill='black', font=font)

    canvas.save(out_png)
    print(f"wrote {out_png}")


if __name__ == '__main__':
    main()
