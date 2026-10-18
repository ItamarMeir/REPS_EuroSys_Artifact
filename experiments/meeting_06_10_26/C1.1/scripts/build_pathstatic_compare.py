#!/usr/bin/env python3
"""Emit plots/pathstatic_compare.html from data/pathstatic_compare.json.
Matched pair at 400G: freezing (B=256) vs path_static (no buffer, collision-
free pinned path), same cwnd/Q/ECN. See c11_pathstatic_compare.py."""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data" / "pathstatic_compare.json"
OUT = HERE.parent / "plots" / "pathstatic_compare.html"

TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8">
<title>C1.1 - freezing vs path_static (400G, matched pair)</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/plotly.js/2.35.3/plotly.min.js"></script>
<style>
body { font-family: system-ui, sans-serif; margin: 16px; color: #111; }
h1 { font-size: 18px; margin: 0 0 4px; }
h2 { font-size: 14px; margin: 18px 0 2px; }
.note { font-size: 12px; color: #555; margin-bottom: 10px; max-width: 980px; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.panel { border: 1px solid #ddd; border-radius: 6px; padding: 6px; position: relative; }
.wide { grid-column: 1 / -1; }
.copy-btn { position: absolute; top: 6px; right: 6px; z-index: 10; opacity: 0;
  transition: opacity .15s; font-size: 11px; padding: 3px 8px; cursor: pointer;
  background: #fff; border: 1px solid #bbb; border-radius: 4px; color: #333; }
.panel:hover .copy-btn { opacity: 1; }
.copy-btn.copied { background: #dcfce7; border-color: #16a34a; color: #166534; }
.gate-ok { color: #0a7a2f; font-weight: 600; }
table { border-collapse: collapse; font-size: 12px; margin-top: 6px; }
th, td { text-align: right; padding: 3px 10px; border-bottom: 1px solid #ddd; }
th:first-child, td:first-child { text-align: left; }
</style></head>
<body>
<h1>C1.1: freezing vs path_static -- matched pair at 400G</h1>
<div class="note">Same cwnd=127, Q=101, ECN=25/76, 400G, 32 MiB tornado, ToR0 hosts. Only the LB
algorithm differs: <b>freezing</b> (B=256, REPS buffer, sprays across 32 paths -- collisions with
other flows on shared links) vs <b>path_static</b> (one pinned path per flow, no buffer, no
collisions). path_static has no REPS buffer, so its "k" is <b>reconstructed</b> by chaining the
one-step recursion k_i=min(B,max(0,k_{i-1}-1)+a_i) over its measured a_i (clean ACKs per
SEND-to-SEND slot) with B=256 -- validated first against freezing's own REAL k
(<span class="gate-ok">GATE: __GATE__/__GATE_N__ mismatches</span>) before trusting it on
path_static. Unloaded BDP at 400G = __BDP__ packets.</div>

<div class="grid">
  <div class="panel">
    <button class="copy-btn" onclick="copyPanelTitle(this)">copy</button>
    <h2>k distribution (headline)</h2>
    <div id="k_hist" style="height:360px;"></div>
  </div>
  <div class="panel">
    <button class="copy-btn" onclick="copyPanelTitle(this)">copy</button>
    <h2>a_i (clean ACKs per send slot) distribution</h2>
    <div id="a_hist" style="height:360px;"></div>
  </div>
  <div class="panel wide">
    <button class="copy-btn" onclick="copyPanelTitle(this)">copy</button>
    <h2>Standing queue (mean in-flight - unloaded BDP, packets)</h2>
    <div id="queue_bar" style="height:220px;"></div>
  </div>
  <div class="panel wide">
    <button class="copy-btn" onclick="copyPanelTitle(this)">copy</button>
    <h2>Slot raster -- src 0, 30 consecutive steady-state slots</h2>
    <div class="note" style="margin:2px 0 6px;">Each tick = one SEND event (x = time since window start,
    ns). Marker color/label = a_i at that slot (clean ACKs since the previous SEND). This is the direct
    picture of "1 SEND, 1 ACK, ...": freezing shows real variation in a_i tick-to-tick; path_static
    shows the deterministic period-10 pattern even with zero collisions.</div>
    <div id="raster" style="height:260px;"></div>
  </div>
  <div class="panel wide">
    <button class="copy-btn" onclick="copyPanelTitle(this)">copy</button>
    <h2>k over time -- src 0, whole flow (downsampled)</h2>
    <div id="k_time" style="height:300px;"></div>
  </div>
</div>

<script>
const DATA = __PAYLOAD__;

function copyPanelTitle(btn) {
  const text = btn.closest(".panel").querySelector("h2").textContent;
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

function toXY(histObj) {
  const ks = Object.keys(histObj).map(Number).sort((a,b)=>a-b);
  return { x: ks.map(String), y: ks.map(k => histObj[k]) };
}

function kHistPanel() {
  const frz = toXY(DATA.k_hist.freezing);
  const ps = toXY(DATA.k_hist.path_static_reconstructed);
  Plotly.newPlot("k_hist", [
    { type:"bar", name:"freezing (measured)", x: frz.x, y: frz.y, marker:{color:"#2a78d6"} },
    { type:"bar", name:"path_static (reconstructed)", x: ps.x, y: ps.y, marker:{color:"#eb6834"} },
  ], {
    barmode:"group", xaxis:{title:"k"}, yaxis:{title:"share of draws", range:[0,1]},
    legend:{orientation:"h", y:-0.25}, margin:{t:10,b:80},
  }, {responsive:true});
}

function aHistPanel() {
  const frz = toXY(DATA.a_hist.freezing);
  const ps = toXY(DATA.a_hist.path_static);
  Plotly.newPlot("a_hist", [
    { type:"bar", name:"freezing", x: frz.x, y: frz.y, marker:{color:"#2a78d6"} },
    { type:"bar", name:"path_static", x: ps.x, y: ps.y, marker:{color:"#eb6834"} },
  ], {
    barmode:"group", xaxis:{title:"a_i (clean ACKs per slot)"}, yaxis:{title:"share of slots", range:[0,1]},
    legend:{orientation:"h", y:-0.25}, margin:{t:10,b:80},
  }, {responsive:true});
}

function queueBarPanel() {
  const q = DATA.standing_queue;
  Plotly.newPlot("queue_bar", [{
    type:"bar", x:["freezing","path_static"], y:[q.freezing, q.path_static],
    marker:{color:["#2a78d6","#eb6834"]},
    text:[q.freezing.toFixed(2)+" pkts", q.path_static.toFixed(2)+" pkts"], textposition:"outside",
  }], { yaxis:{title:"mean in-flight - unloaded BDP (packets)"}, margin:{t:10,b:30} },
  {responsive:true});
}

function rasterPanel() {
  const traces = [];
  const arms = [["freezing","#2a78d6",0],["path_static","#eb6834",1]];
  for (const [name,color,yoff] of arms) {
    const rows = DATA.raster[name];
    traces.push({
      type:"scatter", mode:"markers+text", name:name,
      x: rows.map(r=>r.t_rel_ns), y: rows.map(()=>yoff),
      marker:{color:color, size:14, symbol:"line-ns-open", line:{width:2,color:color}},
      text: rows.map(r=>String(r.a)), textposition:"top center",
      hovertemplate: name+" t=%{x:.1f}ns a_i=%{text}<extra></extra>",
    });
  }
  Plotly.newPlot("raster", traces, {
    xaxis:{title:"time since window start (ns)"},
    yaxis:{tickvals:[0,1], ticktext:["freezing","path_static"], range:[-0.5,1.5]},
    margin:{t:10,b:40}, showlegend:false,
  }, {responsive:true});
}

function kTimePanel() {
  const frz = DATA.k_over_time.freezing;
  const ps = DATA.k_over_time.path_static_reconstructed;
  Plotly.newPlot("k_time", [
    { type:"scatter", mode:"lines", name:"freezing (measured)",
      x: frz.map(p=>p[0]), y: frz.map(p=>p[1]), line:{color:"#2a78d6", width:1} },
    { type:"scatter", mode:"lines", name:"path_static (reconstructed)",
      x: ps.map(p=>p[0]), y: ps.map(p=>p[1]), line:{color:"#eb6834", width:1} },
  ], {
    xaxis:{title:"draw index (src 0)"}, yaxis:{title:"k"},
    legend:{orientation:"h", y:-0.2}, margin:{t:10,b:60},
  }, {responsive:true});
}

kHistPanel(); aHistPanel(); queueBarPanel(); rasterPanel(); kTimePanel();
</script>
</body></html>
"""


def main() -> None:
    payload = json.loads(DATA.read_text(encoding="utf-8"))
    html = (TEMPLATE
            .replace("__PAYLOAD__", json.dumps(payload))
            .replace("__GATE__", str(payload["gate_mismatches"]))
            .replace("__GATE_N__", str(payload["gate_checked"]))
            .replace("__BDP__", str(payload["bdp_400g"])))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
