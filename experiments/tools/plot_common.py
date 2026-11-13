#!/usr/bin/env python3
"""
Shared builder for self-contained interactive Plotly pages (no server, Plotly
from cdnjs). One theme, one palette, one set of per-panel buttons, so every
experiment page reads the same.

A page is: header (eyebrow, h1, lede, small config line, status chips) + KPI
tiles + an ordered list of blocks (heading, note, callout, aside, plot, table)
+ footer. Explanations between plots are just `note`/`callout`/`aside` blocks
placed in that order -- no HTML editing.

    from plot_common import *
    body = [h2("p99 FCT climbs with F", 1), plot("fct", "p99 FCT vs F", ...),
            note("Why: ..."), callout("Result", "...")]
    build_page(out, title=..., h1=..., lede=..., body=body, page_js=JS,
               payload={...})

The page JS gets `PC` (draw, lineTrace, vmarks, radio, onRedraw, style) and
`DATA` (your payload plus DATA._pc, the palette).
"""
from __future__ import annotations

import html as _html
import json
import re

# --------------------------------------------------------------------------
# Palette: one table, keyed by entity. Color AND symbol AND dash identify a
# series, so it still reads in grayscale / for color-blind readers.
# B 1..32 = exp28 interactive (canonical); symbols in the same order as exp28.
# `dark` overrides B=1/2 only: the canonical hexes are 1.1:1 / 2.0:1 on the dark
# surface. Light-surface ends (B=16/32 at 1.9:1 / 1.2:1) keep the canonical hex:
# darkening them costs adjacent CVD separation (dE 10.5 -> ~3), so shape, halo,
# legend and the copy-data/table view carry them instead.
# --------------------------------------------------------------------------
STYLES = {
    "1":       dict(color="#440154", dark="#a35bc4", symbol="circle-open"),
    "2":       dict(color="#414487", dark="#7f86e8", symbol="diamond-open"),
    "4":       dict(color="#2a788e", symbol="triangle-up-open"),
    "8":       dict(color="#22a884", symbol="triangle-down-open"),
    "16":      dict(color="#7ad151", symbol="x-open"),
    "32":      dict(color="#fde725", symbol="cross-open"),
    # not in any earlier interactive page -- proposed (see reference.md)
    "64":      dict(color="#c2185b", dark="#ec4899", symbol="hexagon-open"),
    "inf":     dict(color="#1a1f2b", dark="#e6e9ef", symbol="square-open", dash="dash"),
    # exp29/30
    "dual":    dict(color="#dc2626", symbol="star-open", dash="dash"),
    "dualcap": dict(color="#2563eb", symbol="pentagon-open", dash="dash"),
    # static-plot pair
    "vanilla": dict(color="#1f77b4", symbol="circle-open"),
    "sa":      dict(color="#ff7f0e", symbol="diamond-open", dash="dash"),
    # T3 knee metrics (colors as in the earlier T3 page)
    "k99":     dict(color="#2a788e", symbol="triangle-up-open"),
    "bow":     dict(color="#7c3aed", dark="#a78bfa", symbol="diamond-open"),
    "bfct":    dict(color="#dc2626", symbol="square-open"),
    "other":   dict(color="#94a3b8", symbol="x-open"),   # cells outside the clean regime
    "bks":     dict(color="#d97706", symbol="circle-open"),
    # generic config series (up to 6 per figure): ink, teal, green, amber, red, violet
    "c0":      dict(color="#1a1f2b", dark="#e6e9ef", symbol="circle-open"),
    "c1":      dict(color="#2a788e", symbol="diamond-open"),
    "c2":      dict(color="#22a884", symbol="triangle-up-open"),
    "c3":      dict(color="#d97706", symbol="triangle-down-open"),
    "c4":      dict(color="#dc2626", symbol="x-open"),
    "c5":      dict(color="#7c3aed", dark="#a78bfa", symbol="cross-open"),
    # N ladder (packets in flight, low to high): sequential viridis-like ramp, last step darkened so it stays visible on the light surface
    "n0":      dict(color="#440154", dark="#a35bc4", symbol="circle-open"),
    "n1":      dict(color="#443983", dark="#8f86e8", symbol="diamond-open"),
    "n2":      dict(color="#31688e", dark="#6ba6d6", symbol="triangle-up-open"),
    "n3":      dict(color="#21918c", symbol="triangle-down-open"),
    "n4":      dict(color="#35b779", symbol="x-open"),
    "n5":      dict(color="#8a9a00", symbol="cross-open"),
    "n6":      dict(color="#c25e00", symbol="hexagon-open"),
}

LEDE_MAX, NOTE_MAX = 220, 450


def _warn(kind: str, text: str, limit: int) -> None:
    if len(text) > limit:
        print(f"[plot_common] WARNING: {kind} is {len(text)} chars (> {limit}); "
              f"shorten it or move detail into an aside: {text[:50]!r}...")


def inline(text: str) -> str:
    """Escape, then **bold** and `code`. Everything else is literal."""
    t = _html.escape(text, quote=False)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    return re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)


# ----------------------------------------------------------------- blocks
def h2(text: str, n: int | None = None, tag: str | None = None) -> str:
    """Section heading. `tag` (e.g. "supporting check") marks a section that
    backs up a claim instead of answering the question."""
    num = f'<span class="n">{n}</span>' if n is not None else ""
    t = f'<span class="stag">{inline(tag)}</span>' if tag else ""
    return f"<section><h2>{num}{inline(text)}{t}</h2>"


def question(ask: str, test: str, compare: str) -> str:
    """The 3-line brief at the top: what we wanted to find out, how it is
    tested, and what is compared side by side. Keep each line to one sentence."""
    for k, v in (("ask", ask), ("test", test), ("compare", compare)):
        _warn(f"question.{k}", v, 200)
    rows = "".join(f'<div class="qr"><span class="ql">{k}</span><span>{inline(v)}</span></div>'
                   for k, v in (("find out", ask), ("test", test), ("compare", compare)))
    return f'<div class="question">{rows}</div>'


def end() -> str:
    """Close a section opened by h2()."""
    return "</section>"


def note(text: str) -> str:
    _warn("note", text, NOTE_MAX)
    return f'<p class="note">{inline(text)}</p>'


CALLOUT_KINDS = ("Prediction", "Result", "Caveat", "Retracted")


def callout(kind: str, text: str) -> str:
    assert kind in CALLOUT_KINDS, kind
    _warn("callout", text, NOTE_MAX)
    return (f'<div class="callout {kind.lower()}"><span class="tag">{kind}</span>'
            f"<p>{inline(text)}</p></div>")


def aside(summary: str, text: str) -> str:
    return (f'<details class="aside"><summary>{inline(summary)}</summary>'
            f"<p>{inline(text)}</p></details>")


def synthetic_banner() -> str:
    return ('<div class="synth">SYNTHETIC DEMO DATA &mdash; invented numbers, '
            "only to show the plot style</div>")


def controls(div: str, label: str) -> str:
    return f'<div class="controls" id="{div}"><label>{inline(label)}</label></div>'


def plot(div: str, footnotes: list[str] | None = None, height: int = 420) -> str:
    """Panel with the standard toolbar. The title lives inside the figure
    (set by PC.draw), so PNG export and copy-title carry it."""
    fn = ""
    if footnotes:
        fn = '<ol class="fn">' + "".join(f"<li>{inline(f)}</li>" for f in footnotes) + "</ol>"
    return (f'<div class="chart"><div class="tools">'
            f'<button onclick="PC.copyTitle(\'{div}\',this)" title="copy the plot headline">copy title</button>'
            f'<button onclick="PC.copyData(\'{div}\',this)" title="copy plotted values as TSV">copy data</button>'
            f'<button onclick="PC.copyImage(\'{div}\',this)" title="copy the figure as an image">copy image</button>'
            f'<button onclick="PC.png(\'{div}\')" title="download PNG">PNG</button></div>'
            f'<div id="{div}" style="height:{height}px"></div></div>{fn}')


def table(div: str) -> str:
    return f'<div class="tblwrap"><table id="{div}"></table></div>'


def tile(k: str, v: str, s: str = "", cls: str = "") -> str:
    return (f'<div class="tile"><p class="k">{inline(k)}</p>'
            f'<div class="v {cls}">{_html.escape(v)}</div>'
            f'<div class="s">{inline(s)}</div></div>')


def chip(kind: str, text: str) -> str:
    glyph = {"ok": "&#10003;", "warn": "!", "bad": "&#10007;"}[kind]
    return f'<span class="chip {kind}"><b>{glyph}</b> {inline(text)}</span>'


# ------------------------------------------------------------------- CSS
_LIGHT = """--ground:#f6f7f9;--surface:#ffffff;--ink:#1a1f2b;--muted:#5b6472;
--hairline:#e3e6ec;--accent:#c2410c;--accent-soft:#fde9dc;--good:#15803d;
--warn:#a16207;--bad:#b91c1c;--shadow:0 1px 2px rgba(20,25,40,.06);"""
_DARK = """--ground:#101319;--surface:#191d26;--ink:#e6e9ef;--muted:#99a1b0;
--hairline:#2b313d;--accent:#fb923c;--accent-soft:#3a2417;--good:#4ade80;
--warn:#facc15;--bad:#f87171;--shadow:0 1px 2px rgba(0,0,0,.4);"""

CSS = f"""
:root{{{_LIGHT}}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{{_DARK}}}}}
:root[data-theme="dark"]{{{_DARK}}}
*{{box-sizing:border-box}}
body{{background:var(--ground);color:var(--ink);margin:0;
  font:400 14px/1.55 "IBM Plex Sans",system-ui,sans-serif}}
.wrap{{max-width:1040px;margin:0 auto;padding:28px 24px 64px}}
header{{border-bottom:1px solid var(--hairline);padding-bottom:14px;position:relative}}
.eyebrow{{font:500 11px/1 "IBM Plex Mono",monospace;letter-spacing:.12em;
  text-transform:uppercase;color:var(--accent);margin:0 0 8px}}
h1{{font-weight:600;font-size:20px;line-height:1.25;margin:0;text-wrap:balance}}
.lede{{font-size:14px;color:var(--muted);max-width:70ch;margin:8px 0 0}}
.cfg{{font:400 11px/1.6 "IBM Plex Mono",monospace;color:var(--muted);margin:10px 0 0;
  max-width:110ch}}
.cfg code{{background:none;padding:0;color:var(--ink);font:inherit}}
details.cmd{{font:400 11px/1.5 "IBM Plex Mono",monospace;color:var(--muted);margin-top:4px}}
details.cmd summary{{cursor:pointer}}
details.cmd pre{{white-space:pre-wrap;margin:6px 0 0;color:var(--ink);background:var(--surface);
  border:1px solid var(--hairline);border-radius:6px;padding:8px 10px}}
.chips{{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}}
.chip{{font:500 11px/1 "IBM Plex Mono",monospace;padding:5px 9px;border-radius:999px;
  border:1px solid currentColor}}
.chip b{{font-weight:600;margin-right:3px}}
.chip.ok{{color:var(--good)}}.chip.warn{{color:var(--warn)}}.chip.bad{{color:var(--bad)}}
#themebtn{{position:absolute;top:0;right:0;font:500 11px/1 "IBM Plex Mono",monospace;
  color:var(--muted);background:var(--surface);border:1px solid var(--hairline);
  border-radius:6px;padding:6px 9px;cursor:pointer}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px;
  margin:18px 0 4px}}
.tile{{background:var(--surface);border:1px solid var(--hairline);border-radius:8px;
  padding:12px 14px;box-shadow:var(--shadow)}}
.tile .k{{font:500 10px/1.2 "IBM Plex Mono",monospace;letter-spacing:.08em;
  text-transform:uppercase;color:var(--muted);margin:0 0 7px}}
.tile .v{{font:500 20px/1.1 "IBM Plex Mono",monospace;font-variant-numeric:tabular-nums}}
.tile .v.good{{color:var(--good)}}.tile .v.bad{{color:var(--bad)}}
.tile .s{{font-size:12px;color:var(--muted);margin-top:6px}}
.question{{margin:18px 0 0;padding:10px 14px;background:var(--surface);
  border:1px solid var(--hairline);border-left:3px solid var(--accent);border-radius:0 8px 8px 0;
  font-size:13px;max-width:90ch}}
.qr{{display:flex;gap:12px;margin:3px 0}}
.ql{{flex:0 0 64px;font:600 10px/1.9 "IBM Plex Mono",monospace;letter-spacing:.08em;
  text-transform:uppercase;color:var(--accent)}}
.stag{{font:500 10px/1 "IBM Plex Mono",monospace;color:var(--muted);border:1px solid var(--hairline);
  border-radius:999px;padding:3px 8px;margin-left:10px;vertical-align:middle;font-weight:500}}
section{{margin-top:34px}}
h2{{font-weight:600;font-size:15px;margin:0 0 10px;padding-bottom:6px;
  border-bottom:1px solid var(--hairline)}}
h2 .n{{display:inline-block;min-width:20px;margin-right:8px;color:var(--accent);
  font-family:"IBM Plex Mono",monospace}}
.note{{font-size:13px;color:var(--muted);max-width:70ch;margin:8px 0 12px}}
code{{font:500 .92em "IBM Plex Mono",monospace;background:var(--accent-soft);
  padding:1px 5px;border-radius:4px;color:var(--ink)}}
.callout{{max-width:70ch;margin:10px 0 14px;padding:8px 12px;font-size:13px;
  border-left:3px solid var(--muted);background:var(--surface);border-radius:0 6px 6px 0}}
.callout p{{margin:2px 0 0}}
.callout .tag{{font:600 10px/1 "IBM Plex Mono",monospace;letter-spacing:.1em;
  text-transform:uppercase;color:var(--muted)}}
.callout.prediction{{border-color:var(--accent)}}.callout.prediction .tag{{color:var(--accent)}}
.callout.result{{border-color:var(--good)}}.callout.result .tag{{color:var(--good)}}
.callout.caveat{{border-color:var(--warn)}}.callout.caveat .tag{{color:var(--warn)}}
.callout.retracted{{border-color:var(--bad)}}.callout.retracted .tag{{color:var(--bad)}}
.callout.retracted p{{text-decoration:line-through;color:var(--muted)}}
details.aside{{max-width:70ch;margin:6px 0 12px;font-size:13px;color:var(--muted)}}
details.aside summary{{cursor:pointer;color:var(--ink)}}
details.aside p{{margin:6px 0 0 14px}}
.controls{{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:0 0 10px;
  font:500 12px/1 "IBM Plex Mono",monospace}}
.controls label{{color:var(--muted);margin-right:2px}}
.controls button{{font:inherit;color:var(--ink);background:var(--surface);
  border:1px solid var(--hairline);border-radius:6px;padding:6px 10px;cursor:pointer}}
.controls button[aria-pressed="true"]{{background:var(--accent);color:#fff;border-color:var(--accent)}}
.controls select{{font:inherit;color:var(--ink);background:var(--surface);
  border:1px solid var(--hairline);border-radius:6px;padding:6px 8px;max-width:100%}}
button:focus-visible,select:focus-visible{{outline:2px solid var(--accent);outline-offset:2px}}
.chart{{background:var(--surface);border:1px solid var(--hairline);border-radius:8px;
  box-shadow:var(--shadow);padding:6px 8px 4px;overflow-x:auto;position:relative}}
.chart>div:last-child{{min-width:600px}}
.tools{{display:flex;justify-content:flex-end;gap:4px;padding:2px 2px 0}}
.tools button{{font:500 10px/1 "IBM Plex Mono",monospace;color:var(--muted);
  background:none;border:1px solid var(--hairline);border-radius:5px;padding:4px 7px;cursor:pointer}}
.tools button:hover{{color:var(--ink);border-color:var(--muted)}}
.tools button.done{{color:var(--good);border-color:var(--good)}}
.tools button.fail{{color:var(--bad);border-color:var(--bad)}}
ol.fn{{counter-reset:fn;list-style:none;padding:0;margin:8px 0 0;font-size:12px;color:var(--muted)}}
ol.fn li{{counter-increment:fn;margin:2px 0}}
ol.fn li::before{{content:counter(fn);display:inline-block;width:16px;height:16px;line-height:14px;
  text-align:center;border:1px solid var(--ink);border-radius:50%;color:var(--ink);
  font:500 10px/14px "IBM Plex Mono",monospace;margin-right:8px}}
.synth{{font:600 11px/1 "IBM Plex Mono",monospace;letter-spacing:.06em;color:#fff;
  background:var(--bad);padding:6px 10px;border-radius:6px 6px 0 0;margin-top:10px}}
.synth+.chart{{border-top-left-radius:0;border-top-right-radius:0}}
.tblwrap{{overflow-x:auto;background:var(--surface);border:1px solid var(--hairline);border-radius:8px}}
table{{border-collapse:collapse;width:100%;font-size:12px}}
th,td{{text-align:right;padding:6px 12px;border-bottom:1px solid var(--hairline);
  font-variant-numeric:tabular-nums;white-space:nowrap}}
th{{font:500 10px/1 "IBM Plex Mono",monospace;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}}
td:first-child,th:first-child{{text-align:left}}tr:last-child td{{border-bottom:none}}
.pill{{font:500 10px/1 "IBM Plex Mono",monospace;padding:3px 8px;border-radius:999px;border:1px solid currentColor}}
.pill.no{{color:var(--good)}}.pill.yes{{color:var(--accent)}}
footer{{margin-top:40px;padding-top:12px;border-top:1px solid var(--hairline);
  color:var(--muted);font-size:11px}}
@media (prefers-reduced-motion:reduce){{*{{transition:none!important}}}}
"""

# -------------------------------------------------------------------- JS
COMMON_JS = r"""
const PC = (() => {
  const S = DATA._pc.styles;
  const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const themeName = () => document.documentElement.dataset.theme
    || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  // color of an entity on the current surface (display step where contrast needs it)
  const color = k => { const s = S[k]; return s[themeName()] || s.color; };
  const rgba = (hex, a) => { const n = parseInt(hex.slice(1), 16);
    return `rgba(${n>>16&255},${n>>8&255},${n&255},${a})`; };
  const TITLES = {};

  function theme() {
    const ink = css('--ink'), grid = css('--hairline'), paper = css('--surface');
    return {
      paper_bgcolor: paper, plot_bgcolor: paper,
      font: { family: 'IBM Plex Sans, sans-serif', color: ink, size: 11 },
      xaxis: { gridcolor: grid, zerolinecolor: grid, linecolor: grid, title: { font: { size: 11 } } },
      yaxis: { gridcolor: grid, zerolinecolor: grid, linecolor: grid, title: { font: { size: 11 } } },
      margin: { l: 62, r: 64, t: 40, b: 46 },
      legend: { orientation: 'h', y: -0.2, font: { size: 11 } },
      hovermode: 'x unified', modebar: { orientation: 'v' },
    };
  }
  const CFG = { displaylogo: false, responsive: true,
    modeBarButtonsToRemove: ['lasso2d', 'select2d', 'toImage'] };

  // Plotly.react rebuilds traces on every redraw; carry legend visibility
  // forward by legendgroup so a hidden series stays hidden.
  function draw(id, traces, layout, title) {
    const el = document.getElementById(id);
    if (el && el.data) {
      const vis = {};
      el.data.forEach(t => { if (t.legendgroup) vis[t.legendgroup] = t.visible; });
      traces.forEach(t => { if (t.legendgroup && vis[t.legendgroup] !== undefined) t.visible = vis[t.legendgroup]; });
    }
    TITLES[id] = title;
    layout.title = { text: title, x: 0, xref: 'paper', xanchor: 'left',
      font: { size: 12, family: 'IBM Plex Sans, sans-serif', color: css('--ink') } };
    Plotly.react(id, traces, layout, CFG);
    requestAnimationFrame(() => Plotly.Plots.resize(document.getElementById(id)));
  }

  // One series = [halo, CI band, line]. rows: [{x, y, ci, n}]. key = STYLES key.
  // Direct end label only when few series (the legend is always there).
  function lineTrace(key, rows, label, o = {}) {
    const c = color(key), st = S[key], surf = css('--surface');
    const xs = rows.map(r => r.x), ys = rows.map(r => r.y);
    const ci = rows.map(r => r.ci ?? 0), n = rows.map(r => r.n ?? 0);
    const base = st.symbol;
    const group = 'g' + key;
    if (o.markers) {  // dot plot: markers only, no line / CI
      return [{ x: xs, y: ys, name: label, type: 'scatter', mode: 'markers', legendgroup: group,
        marker: { color: c, symbol: base, size: 10, line: { color: c, width: 2 } },
        error_y: o.err ? { type: 'data', array: ci, visible: true, thickness: 1.2, width: 4, color: c } : undefined,
        hovertemplate: o.hover || (o.err ? '%{y:.4g} \u00b1%{customdata[0]:.3g}' : '%{y:.4g}'),
        customdata: rows.map((r, i) => [ci[i], n[i]]) }];
    }
    const halo = { x: xs, y: ys, mode: 'lines', type: 'scatter', hoverinfo: 'skip',
      showlegend: false, legendgroup: group, line: { color: surf, width: 5 } };
    const band = { x: [...xs, ...xs.slice().reverse()],
      y: [...ys.map((y, i) => y + ci[i]), ...ys.map((y, i) => o.signed ? y - ci[i] : Math.max(y - ci[i], 0)).reverse()],
      fill: 'toself', fillcolor: rgba(c, 0.13), line: { width: 0 }, mode: 'lines',
      hoverinfo: 'skip', showlegend: false, type: 'scatter', legendgroup: group };
    const line = { x: xs, y: ys, name: label, type: 'scatter', legendgroup: group,
      mode: o.endLabel ? 'lines+markers+text' : 'lines+markers',
      line: { color: c, width: 2.4, dash: st.dash || 'solid' },
      // single-seed points (n < 2) are drawn filled and carry no CI
      marker: { color: c, size: 8, line: { color: c, width: 1.8 },
        symbol: n.map(v => (v > 0 && v < 2) ? base.replace('-open', '') : base) },
      customdata: rows.map((r, i) => [ci[i], n[i]]),
      hovertemplate: o.hover || '%{y:.4g} ±%{customdata[0]:.3g}  (n=%{customdata[1]})' };
    if (o.endLabel) {
      line.text = xs.map((_, i) => i === xs.length - 1 ? label : '');
      line.textposition = 'middle right'; line.textfont = { color: css('--ink'), size: 11 };
      line.cliponaxis = false;
    }
    return o.noBand ? [halo, line] : [halo, band, line];
  }

  // Grouped bar series: solid fill for the first style, patterned fill for the others so
  // bars differ by more than color. rows: [{x, y, ci, n}] (ci = 95% CI half-width, drawn as error bar).
  const PATTERN = { c0: '', c1: '', c2: '/', c3: '\\', c4: 'x', c5: '+', other: '.' };
  function barTrace(key, rows, label, o = {}) {
    const c = color(key), pat = PATTERN[key] ?? '';
    return { type: 'bar', name: label, legendgroup: 'g' + key,
      x: rows.map(r => r.x), y: rows.map(r => r.y),
      customdata: rows.map(r => [r.ci ?? 0, r.n ?? 0]),
      marker: { color: pat ? c : rgba(c, 0.85), line: { color: c, width: 1.2 },
        pattern: pat ? { shape: pat, fgcolor: c, bgcolor: css('--surface'), size: 6, solidity: 0.55 } : undefined },
      error_y: { type: 'data', array: rows.map(r => r.ci ?? 0), visible: true, thickness: 1.2, width: 3, color: c },
      hovertemplate: o.hover || '%{y:.4g} \u00b1%{customdata[0]:.3g}  (n=%{customdata[1]})' };
  }

  // Horizontal reference line across the plot with a small right-aligned label.
  function hline(y, text) {
    const m = css('--muted');
    return {
      shapes: [{ type: 'line', xref: 'paper', x0: 0, x1: 1, y0: y, y1: y, line: { color: m, width: 1, dash: 'dot' } }],
      annotations: [{ xref: 'paper', x: 1, y, xanchor: 'right', yanchor: 'bottom', showarrow: false,
        text, font: { size: 10, color: m } }] };
  }

  // The headline plot of every page: primary metric (max FCT) against B, one
  // line per config with its 95% CI band and a ring at the knee B_fct.
  // series: [{label, style?, bfct, rows:[{x:'B=..', y, ci, n}]}]
  // o: {yrange, ylabel, note}
  function fctVsB(id, series, title, o = {}) {
    const traces = [];
    series.forEach((s, i) => {
      const key = s.style || ('c' + i);
      traces.push(...lineTrace(key, s.rows, s.label, { noBand: s.noBand, signed: o.signed }));   // o.signed: values can be negative (differences), do not clip the CI band at 0
      const kr = s.rows.find(r => r.x === 'B=' + s.bfct);
      if (kr) traces.push({ x: [kr.x], y: [kr.y], type: 'scatter', mode: 'markers', showlegend: false,
        legendgroup: 'g' + key, hovertemplate: 'knee B_fct = ' + s.bfct + '<extra></extra>',
        marker: { symbol: 'circle-open', size: 18, color: color(key), line: { width: 1.4, color: color(key) } } });
    });
    if (o.extra) traces.push(...o.extra);   // extra traces (e.g. dashed reference lines), built by the page with its own legendgroup
    const t = theme();
    t.xaxis.type = 'category'; t.yaxis.title.text = o.ylabel || 'max FCT (\u00b5s)';
    if (o.cats) { t.xaxis.categoryorder = 'array'; t.xaxis.categoryarray = o.cats; }
    if (o.yrange) t.yaxis.range = o.yrange;
    if (o.refY != null) { const r = hline(o.refY, o.refText || ''); t.shapes = r.shapes; t.annotations = r.annotations; }
    draw(id, traces, t, title);
  }

  // Numbered vertical marks: footnote N under the plot explains mark N.
  function vmarks(list) {  // [{x, n, dash}]
    const ink = css('--ink');
    return {
      shapes: list.map(m => ({ type: 'line', x0: m.x, x1: m.x, yref: 'paper', y0: 0, y1: 1,
        line: { color: ink, width: 1, dash: m.dash || 'dash' } })),
      annotations: list.map(m => ({ x: m.x, y: 1, yref: 'paper', yanchor: 'bottom', showarrow: false,
        text: String(m.n), font: { size: 10, color: ink }, bordercolor: ink, borderwidth: 1,
        borderpad: 2, bgcolor: css('--surface') })),
    };
  }

  function flash(btn, ok, text) {
    const prev = btn.dataset.l || (btn.dataset.l = btn.textContent);
    btn.textContent = text; btn.classList.add(ok ? 'done' : 'fail');
    setTimeout(() => { btn.textContent = prev; btn.classList.remove('done', 'fail'); }, 1300);
  }
  function fallbackCopy(text) {
    const ta = document.createElement('textarea'); ta.value = text;
    ta.style.cssText = 'position:fixed;opacity:0'; document.body.appendChild(ta); ta.select();
    let ok = false; try { ok = document.execCommand('copy'); } catch (e) {}
    document.body.removeChild(ta); return ok;
  }
  function copyText(text, btn) {
    const done = ok => flash(btn, ok, ok ? 'copied!' : 'failed');
    if (navigator.clipboard && navigator.clipboard.writeText)
      navigator.clipboard.writeText(text).then(() => done(true)).catch(() => done(fallbackCopy(text)));
    else done(fallbackCopy(text));
  }
  const copyTitle = (id, btn) => copyText(TITLES[id] || '', btn);
  function copyData(id, btn) {  // every named series: series, x, y, ci, n
    const el = document.getElementById(id), rows = ['series\tx\ty\tci95\tn'];
    el.data.filter(t => t.name && t.showlegend !== false).forEach(t =>
      t.x.forEach((x, i) => rows.push([t.name, x, t.y[i],
        t.customdata ? t.customdata[i][0] : '', t.customdata ? t.customdata[i][1] : ''].join('\t'))));
    copyText(rows.join('\n'), btn);
  }
  const IMG = { format: 'png', width: 1100, height: 520, scale: 2 };
  function copyImage(id, btn) {
    const el = document.getElementById(id);
    if (!(navigator.clipboard && window.ClipboardItem)) return flash(btn, false, 'use PNG');
    const blob = Plotly.toImage(el, IMG).then(u => fetch(u)).then(r => r.blob());
    navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })])
      .then(() => flash(btn, true, 'copied!')).catch(() => flash(btn, false, 'use PNG'));
  }
  const png = id => Plotly.downloadImage(document.getElementById(id), { ...IMG, filename: id });

  function radio(host, names, current, cb) {
    const el = document.getElementById(host);
    names.forEach(nm => {
      const b = document.createElement('button');
      b.textContent = nm; b.setAttribute('aria-pressed', nm === current);
      b.onclick = () => {
        el.querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', x === b));
        cb(nm);
      };
      el.appendChild(b);
    });
  }

  function select(host, names, current, cb) {
    const el = document.getElementById(host), s = document.createElement('select');
    names.forEach(([v, lab]) => { const o = document.createElement('option'); o.value = v;
      o.textContent = lab; s.appendChild(o); });
    s.value = current; s.onchange = () => cb(s.value); el.appendChild(s);
  }

  function onRedraw(fn) {
    matchMedia('(prefers-color-scheme: dark)').addEventListener('change', fn);
    new MutationObserver(fn).observe(document.documentElement,
      { attributes: true, attributeFilter: ['data-theme'] });
    let rt;
    addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(() =>
      document.querySelectorAll('.chart > div:last-child').forEach(e => e._fullLayout && Plotly.Plots.resize(e)), 120); });
  }
  // theme button cycles auto -> light -> dark
  const tb = document.getElementById('themebtn');
  tb.onclick = () => {
    const r = document.documentElement, cur = r.dataset.theme;
    if (!cur) r.dataset.theme = 'light'; else if (cur === 'light') r.dataset.theme = 'dark';
    else delete r.dataset.theme;
    tb.textContent = 'theme: ' + (r.dataset.theme || 'auto');
  };
  return { css, color, rgba, theme, draw, lineTrace, barTrace, hline, fctVsB, vmarks, copyTitle, copyData, copyImage, png,
    radio, select, onRedraw, style: k => S[k] };
})();
"""


def _asciiify(page: str) -> str:
    """Pure-ASCII output so a mis-negotiated charset cannot mojibake it:
    non-ASCII becomes &#N; in HTML/CSS and \\uXXXX inside <script> blocks."""
    non = re.compile(r"[^\x00-\x7f]")
    out = []
    for part in re.split(r"(<script>\n[\s\S]*?</script>)", page):
        if part.startswith("<script>\n"):
            out.append(non.sub(lambda m: "\\u%04x" % ord(m.group(0)), part))
        else:
            out.append(non.sub(lambda m: "&#%d;" % ord(m.group(0)), part))
    return "".join(out)


def knee_fct(s, key: str = "fct_max", tol_floor: float = 0.002):
    """One-sided knee B_fct: smallest B such that every larger B is within the
    CI (or tol_floor of the value) of the largest-B reference, or better.
    `s` = per-B rows sorted by B with columns `<key>_mean`, `<key>_ci95`
    (same rule as T3/scripts/aggregate_t3.py)."""
    import numpy as np
    ref = s.iloc[-1]
    ok = []
    for _, r in s.iterrows():
        tol = max(np.nan_to_num(r[f"{key}_ci95"]), np.nan_to_num(ref[f"{key}_ci95"]),
                  tol_floor * ref[f"{key}_mean"])
        ok.append(r[f"{key}_mean"] <= ref[f"{key}_mean"] + tol)
    for i in range(len(ok)):
        if all(ok[i:]):
            return int(s.iloc[i].B)
    return None


def fct_series(s, label: str, style: str | None = None, key: str = "fct_max") -> dict:
    """One line of 'max FCT vs B' for PC.fctVsB: rows per B with 95% CI and n,
    plus the knee B_fct. `style` = STYLES key (default: by position)."""
    s = s.sort_values("B")
    rows = [{"x": f"B={int(r.B)}", "y": round(float(r[f"{key}_mean"]), 2),
             "ci": round(float(r[f"{key}_ci95"]) if r[f"{key}_ci95"] == r[f"{key}_ci95"] else 0.0, 2),
             "n": int(r.n_seeds)} for _, r in s.iterrows()]
    return {"label": label, "style": style, "bfct": knee_fct(s, key), "rows": rows, "noBand": False}


def records(df):
    """DataFrame -> list of dicts with NaN as null (valid JSON)."""
    return json.loads(df.to_json(orient="records"))


def build_page(out, *, title: str, eyebrow: str, h1: str, lede: str, cfg: str,
               body: list[str], page_js: str, payload: dict, footer: str,
               full_cmd: str | None = None, chips: list[str] = (),
               tiles: list[str] = (), brief: str = "") -> None:
    """Write the page. `cfg` = only the flags that differ from baseline (small
    mono line); `full_cmd` = the whole command, collapsed. `payload` becomes
    `const DATA = ...` (kept as one blob: thesis-sync packs it)."""
    _warn("lede", lede, LEDE_MAX)
    cmd = (f'<details class="cmd"><summary>full command</summary><pre>{_html.escape(full_cmd)}</pre></details>'
           if full_cmd else "")
    data = dict(payload)
    data["_pc"] = {"styles": STYLES}
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_html.escape(title)}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>{CSS}</style></head><body>
<div class="wrap">
<header>
  <button id="themebtn" aria-label="toggle theme">theme: auto</button>
  <p class="eyebrow">{inline(eyebrow)}</p>
  <h1>{inline(h1)}</h1>
  <p class="lede">{inline(lede)}</p>
  <p class="cfg">{inline(cfg)}</p>{cmd}
  <div class="chips">{''.join(chips)}</div>
</header>
{brief}
<div class="tiles">{''.join(tiles)}</div>
{''.join(body)}
<footer>{inline(footer)}</footer>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/plotly.js/2.35.3/plotly.min.js"></script>
<script>
const DATA = {json.dumps(data)};
{COMMON_JS}
{page_js}
</script>
</body></html>
"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_asciiify(page), encoding="utf-8")
    print(f"wrote {out}  ({len(page)/1024:.0f} KB)")
