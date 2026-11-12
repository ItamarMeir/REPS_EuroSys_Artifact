#!/usr/bin/env python3
"""Emit plots/combined.html -- a_i and k distributions across the rate
sweep (REPS) plus path_static (collision-free reference). Only the two
panels the user asked to keep."""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data" / "combined.json"
OUT = HERE.parent / "plots" / "combined.html"

TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8">
<title>C1.1 - a_i and k across the rate sweep</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/plotly.js/2.35.3/plotly.min.js"></script>
<style>
body { font-family: system-ui, sans-serif; margin: 16px; color: #111; }
h1 { font-size: 18px; margin: 0 0 4px; }
.note { font-size: 12px; color: #555; margin-bottom: 10px; max-width: 980px; }
.panel { border: 1px solid #ddd; border-radius: 6px; padding: 6px; margin-bottom: 14px; position: relative; }
.copy-btn { position: absolute; top: 6px; right: 6px; z-index: 10; opacity: 0;
  transition: opacity .15s; font-size: 11px; padding: 3px 8px; cursor: pointer;
  background: #fff; border: 1px solid #bbb; border-radius: 4px; color: #333; }
.panel:hover .copy-btn { opacity: 1; }
.copy-btn.copied { background: #dcfce7; border-color: #16a34a; color: #166534; }
.warn { color: #b45309; font-weight: 600; }
</style></head>
<body>
<h1>C1.1: a_i and k across the rate sweep (REPS) + path_static reference</h1>
<div class="note">REPS = <code>-load_balancing_algo freezing</code> (the paper's REPS mechanism; B=256,
non-limiting). <b>100G</b> uses <b>cwnd90, fixed Q=101</b> (not BDP-scaled Q=28): this beat the
BDP-scaled cwnd36 cell on FCT (~2785 ns/flow vs ~2834) and is non-window-bound, so the BDP-scaled 100G
cell was dropped to cut noise. <span class="warn">200G cwnd66 is still window-bound</span> (inflight
sits within ~1 packet of cwnd most of the time; BDP-scaled Q, grey/dashed in the plots) -- no
alternative cwnd has been run at 200G yet, so it's the only 200G cell shown and is not a clean
serialization-only reading. 100G's fixed-Q policy is not directly comparable to the BDP-scaled
200G/400G/800G cells on a single Q policy, so rates are NOT connected by a line -- grouped bars per
cell instead.
<br><br>
<b>k's exact definition</b> (event order, no aggregation, no seed parameter): k=0 before any event for
a host. A clean ACK (ecn=0): k+=1, capped at B. A draw (SEND/RTX/RTS): k-=1 if k&gt;0, else unchanged.
Gate-validated against REPS 400G's own real measured k, full event order including pre-warmup rows:
<span class="gate-ok">__GATE__/__GATE_N__ mismatches</span>. Post-warmup only (same convention as every
other cell here: draws before a host's first ACK are excluded).
<br><br>
<b>path_static</b> (400G, same cwnd/Q/ECN as the REPS 400G cell) pins one path per flow, no REPS
buffer, zero collisions with other flows -- so it has no real k to read. What's plotted is the
<b>counterfactual</b>: the k a REPS buffer WOULD hold if driven by path_static's own ACK stream, using
the exact rule above. This is not a measurement of path_static itself, only of what its ACK timing
would do to a buffer if one existed.
<br><br>
<b>Why that counterfactual k sits near 3 while its a_i sits near 1:</b> k is a running accumulator of
a_i's deviations from 1, not a snapshot of a_i. path_static's a_i settles into a balanced, near-exactly
periodic pattern (mean exactly 1 -> zero net drift once established), so k just preserves whatever
level the early transient left it at, forever -- it never drifts back toward 1. That level is set by a
reflecting floor at k=0 (a draw that finds the buffer empty can't decrement further, so it gets one
"free" step every time it touches bottom) interacting with one early burst of 2 clean ACKs back-to-back
in the warmup -- that reflection is what lifts k up to the level (3) it then holds for the rest of the
flow. Because k=0 is a hard initial condition (not a free parameter), this level is a fixed function of
path_static's own ACK sequence, not an artifact of how the reconstruction was seeded.
<br><br>
<b>REPS's k does NOT behave this way</b>: it keeps drifting upward across the whole flow (mean ~1.9
early, ~3.0 by the end at 400G) rather than settling once. This looked like a growing standing queue
from collisions, but checking pooled mean in-flight at 400G doesn't confirm that cleanly: in-flight
rises early (110 -> 124 packets) then falls back some by the end (~120) -- it doesn't climb
monotonically the way k does. So REPS's upward k drift is real, but its cause is still open; "a growing
collision queue" is a plausible read, not yet a confirmed one.</div>

<div class="panel"><button class="copy-btn" onclick="copyTitle('a_hist', this)">copy</button><div id="a_hist" style="height:420px;"></div></div>
<div class="panel"><button class="copy-btn" onclick="copyTitle('k_hist', this)">copy</button><div id="k_hist" style="height:420px;"></div></div>

<script>
const DATA = __PAYLOAD__;
const COLORS = {
  "100g_fixedq_cwnd90": "#c026d3", "200g_cwnd66": "#9ca3af",
  "400g_cwnd127": "#2a78d6", "800g_cwnd249": "#1baf7a",
};
const PATH_STATIC_COLOR = "#eb6834";

const TITLE_BY_ID = {};
function plotWithHeadline(divId, traces, layout, opts) {
  TITLE_BY_ID[divId] = layout.title.text.replace(/&gt;/g, ">").replace(/&lt;/g, "<");
  Plotly.newPlot(divId, traces, layout, opts);
}
function copyTitle(divId, btn) {
  const text = TITLE_BY_ID[divId] || "";
  const done = () => {
    const prev = btn.textContent;
    btn.textContent = "copied!";
    btn.classList.add("copied");
    setTimeout(() => { btn.textContent = prev; btn.classList.remove("copied"); }, 1200);
  };
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
  } else {
    fallbackCopy(text, done);
  }
}
function fallbackCopy(text, done) {
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand("copy"); } catch (e) {}
  document.body.removeChild(ta);
  done();
}

// Same presentation as C1/NSCC "Send-time k": one stacked bar per cell, one
// segment per value (k or a_i), rare values merged into one grey bucket.
const VAL_COLORS = ["#1b7837", "#5aae61", "#a6d96a", "#fee08b", "#fdae61", "#d73027", "#a50026"];
const RARE_SHARE = 1e-4;
function stackedPanel(divId, field, name, title, ytitle, totalNote) {
  const cells = DATA.cells.concat([Object.assign({dir: "path_static", short: "path_static 400G (counterfactual)"}, DATA.path_static)]);
  const xs = cells.map(c => c.short || c.label.split(" (")[0]);
  const vals = new Set();
  for (const c of cells) for (const k of Object.keys(c[field])) vals.add(Number(k));
  const vmax = Math.max(0, ...vals);
  const shareOf = (c, v) => c[field][String(v)] || 0;
  const maxShareOf = v => Math.max(0, ...cells.map(c => shareOf(c, v)));
  const individual = [];
  let firstRare = null;
  for (let v = 0; v <= vmax; v++) {
    if (maxShareOf(v) >= RARE_SHARE || v === 0) individual.push(v);
    else if (firstRare === null) firstRare = v;
  }
  const traces = individual.map(v => ({
    type: "bar", name: name + "=" + v, x: xs, y: cells.map(c => shareOf(c, v)),
    customdata: cells.map(c => [Math.round(shareOf(c, v) * c.n), c.n]),
    marker: {color: VAL_COLORS[v % VAL_COLORS.length]},
    hovertemplate: "%{x}<br>" + name + "=" + v + " share=%{y:.4f}" +
      "<br>%{customdata[0]} of %{customdata[1]}<extra></extra>",
  }));
  if (firstRare !== null) {
    const rare = [];
    for (let v = firstRare; v <= vmax; v++) if (!individual.includes(v)) rare.push(v);
    traces.push({
      type: "bar", name: name + ">=" + firstRare + " (rare, <0.01% each)", x: xs,
      y: cells.map(c => rare.reduce((t, v) => t + shareOf(c, v), 0)),
      customdata: cells.map(c => [Math.round(rare.reduce((t, v) => t + shareOf(c, v), 0) * c.n), c.n]),
      marker: {color: "#9ca3af"},
      hovertemplate: "%{x}<br>" + name + " in {" + rare.join(",") + "} combined, share=%{y:.6f}" +
        "<br>%{customdata[0]} of %{customdata[1]}<extra></extra>",
    });
  }
  plotWithHeadline(divId, traces, {
    title: {text: title, font: {size: 14}},
    barmode: "stack",
    xaxis: {title: "cell (link rate)", categoryorder: "array", categoryarray: xs},
    yaxis: {title: ytitle, range: [0, 1]},
    legend: {orientation: "h", y: -0.45}, margin: {t: 60, b: 160}, height: 520,
    annotations: [{
      text: totalNote, showarrow: false, xref: "paper", yref: "paper", x: 0, y: 1.08,
      xanchor: "left", font: {size: 11, color: "#555"},
    }],
  }, {responsive: true});
}

stackedPanel("a_hist", "a_hist", "a",
  "a_i: clean ACKs per SEND-to-SEND slot, post-warmup, 16 MiB -- healthy",
  "share of post-warmup slots",
  "total post-warmup slots per cell: " + DATA.cells.map(c => c.n).join(" / ") + " (path_static: " + DATA.path_static.n + ")");
stackedPanel("k_hist", "k_hist", "k",
  "Send-time k, post-warmup, 16 MiB -- healthy (path_static: counterfactual)",
  "share of post-warmup sends",
  "total post-warmup sends per cell: " + DATA.cells.map(c => c.n).join(" / ") + " (path_static: " + DATA.path_static.n + ")");
</script>
</body></html>
"""


def main() -> None:
    payload = json.loads(DATA.read_text(encoding="utf-8"))
    html = (TEMPLATE
            .replace("__PAYLOAD__", json.dumps(payload))
            .replace("__GATE__", str(payload["path_static"]["gate_mismatches"]))
            .replace("__GATE_N__", str(payload["path_static"]["gate_checked"])))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
