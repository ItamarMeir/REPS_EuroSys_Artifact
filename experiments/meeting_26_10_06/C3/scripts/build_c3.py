#!/usr/bin/env python3
"""C3 results page: does claim 1 (buffer-size-insensitivity at backlog) hold
once src0 pauses? Reads analyze_c3.py's CSVs (c3_fct.csv, c3_boundary.csv,
c3_decay.csv) -- run analyze_c3.py first.

3 panels (see PLAN.md "Interactive plot", advisor-reviewed down from 6):
  1. FCT normalized per N: FCT(B)/FCT(B=1) WITHIN each N series -- raw FCT
     grows with N by ~N*RTT regardless of B (each burst's own ~1RTT tail),
     so normalizing within N isolates the B-effect from the N-effect.
  2. Fresh-at-burst-start observed vs predicted min(B,tail), per N, long-gap
     N=4 folded in as a dashed overlay.
  3. Valid-draw decay by send-index within a burst, N=16 only, one line/B.
"""
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
C3 = HERE.parent
DATA = C3 / "data"
PLOTS = C3 / "plots"

BS = [1, 2, 4, 8, 16, 32, 64, 128, 256]
SEEDS = [42, 43, 44]
STEM_TO_N = {"c3_n1_drained": 1, "c3_n4_drained": 4, "c3_n16_drained": 16, "c3_n4_longgap": 4}
STEM_IS_LONGGAP = {"c3_n4_longgap"}


def load_csv(path, keys_types):
    if not path.exists():
        return []
    out = []
    for r in csv.DictReader(open(path)):
        out.append({k: t(r[k]) for k, t in keys_types.items()})
    return out


VALID_SRC = {"fresh_pop", "frozen_pop_valid"}


def classify(ev_src):
    if ev_src in VALID_SRC:
        return "valid"
    if ev_src == "frozen_pop_stale":
        return "stale"
    if ev_src in ("random", "explore"):
        return "random"
    return "other"


def build_fct_panel_data(fct_rows):
    """cm_stem,B,seed -> total FCT (sum over bursts). Then per (stem,seed),
    ratio = total_fct(B) / total_fct(B=1)."""
    totals = {}  # (stem, b, seed) -> total_fct_us
    for r in fct_rows:
        key = (r["cm_stem"], r["B"], r["seed"])
        totals[key] = totals.get(key, 0.0) + r["fct_us"]
    out = []
    for stem in STEM_TO_N:
        for seed in SEEDS:
            base = totals.get((stem, 1, seed))
            if base is None or base == 0:
                continue
            for b in BS:
                tot = totals.get((stem, b, seed))
                if tot is None:
                    continue
                out.append(dict(cm_stem=stem, N=STEM_TO_N[stem], longgap=(stem in STEM_IS_LONGGAP),
                                 B=b, seed=seed, ratio=tot / base))
    return out


def build_boundary_panel_data(boundary_rows):
    """cm_stem,B -> mean observed_fresh, mean predicted, over all boundaries+seeds."""
    agg = {}
    for r in boundary_rows:
        key = (r["cm_stem"], r["B"])
        a = agg.setdefault(key, dict(obs=[], pred=[]))
        a["obs"].append(r["observed_fresh"])
        a["pred"].append(r["predicted"])
    out = []
    for (stem, b), a in agg.items():
        if not a["obs"]:
            continue
        out.append(dict(cm_stem=stem, N=STEM_TO_N[stem], longgap=(stem in STEM_IS_LONGGAP), B=b,
                         mean_observed=sum(a["obs"]) / len(a["obs"]),
                         mean_predicted=sum(a["pred"]) / len(a["pred"]),
                         n=len(a["obs"])))
    return out


def build_decay_panel_data(decay_rows):
    """N=16 cells only. (B, send_index) -> P(valid draw)."""
    agg = {}
    for r in decay_rows:
        if r["cm_stem"] != "c3_n16_drained":
            continue
        key = (r["B"], r["send_index"])
        a = agg.setdefault(key, dict(valid=0, total=0))
        a["total"] += 1
        if classify(r["ev_src"]) == "valid":
            a["valid"] += 1
    out = []
    for (b, si), a in agg.items():
        out.append(dict(B=b, send_index=si, p_valid=a["valid"] / a["total"], n=a["total"]))
    return out


def main():
    fct_rows = load_csv(DATA / "c3_fct.csv", dict(
        cm_stem=str, B=int, seed=int, N=int, burst_index=int,
        start_us=float, finish_us=float, fct_us=float))
    boundary_rows = load_csv(DATA / "c3_boundary.csv", dict(
        cm_stem=str, B=int, seed=int, N=int, boundary=int,
        observed_fresh=int, tail=int, predicted=int,
        cwnd_pkts_end=lambda s: int(s) if s not in ("", None) else None))
    decay_rows = load_csv(DATA / "c3_decay.csv", dict(
        cm_stem=str, B=int, seed=int, burst_index=int, send_index=int, ev_src=str,
        fresh=int))

    fct_panel = build_fct_panel_data(fct_rows)
    boundary_panel = build_boundary_panel_data(boundary_rows)
    decay_panel = build_decay_panel_data(decay_rows)

    PLOTS.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(dict(fct_panel=fct_panel, boundary_panel=boundary_panel, decay_panel=decay_panel))
    html = TEMPLATE.replace("__PAYLOAD__", payload)
    (PLOTS / "interactive.html").write_text(html, encoding="utf-8")
    print(f"fct rows: {len(fct_rows)} boundary rows: {len(boundary_rows)} decay rows: {len(decay_rows)}")
    print(f"fct_panel: {len(fct_panel)} boundary_panel: {len(boundary_panel)} decay_panel: {len(decay_panel)}")
    print("wrote", PLOTS / "interactive.html")


TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8">
<title>C3 - Bursty-sender buffer-size sensitivity</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/plotly.js/2.35.3/plotly.min.js"></script>
<style>
body { font-family: system-ui, sans-serif; margin: 16px; color: #111; }
h1 { font-size: 18px; margin: 0 0 4px; }
.note { font-size: 12px; color: #555; margin-bottom: 12px; max-width: 980px; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.panel { border: 1px solid #ddd; border-radius: 6px; padding: 6px; position: relative; }
.wide { grid-column: 1 / -1; }
.copy-btn { position: absolute; top: 6px; right: 6px; z-index: 10; opacity: 0;
  transition: opacity .15s; font-size: 11px; padding: 3px 8px; cursor: pointer;
  background: #fff; border: 1px solid #bbb; border-radius: 4px; color: #333; }
.panel:hover .copy-btn { opacity: 1; }
.copy-btn.copied { background: #dcfce7; border-color: #16a34a; color: #166534; }
</style></head>
<body>
<h1>C3: bursty src0 -- does buffer-size insensitivity (claim 1) hold without constant backlog?</h1>
<div class="note">Healthy fabric, NSCC, trim ON, 16 MiB tornado, 3 seeds (42/43/44). Only src0 (host 0)
is bursty: its 16 MiB is split into N bursts (16MiB/N bytes each) with a gap between them, sharing one
REPS buffer across the gaps (-connections_mapping). The other 31 ToR0 hosts send one continuous backlogged
16 MiB flow each, sized up to outlast src0's whole schedule, so src0's pauses happen against a normal busy
fabric. N=1,4,16 at a 5-RTT "drained" gap (~41.7us); N=4 also at a 50-RTT "long" gap (~417us) as a
gap-length control. B swept over the full ladder 1..256. Prediction: each burst after the first should
start with fresh ~= min(B, tail), tail = clean ACKs trickling in during the gap -- i.e. a real B-dependent
boost, unlike C1's backlogged finding of only 1-2 valid EVs ever sitting in the buffer.</div>
<div class="note">Hover a plot and click "copy" (top-right) to copy that plot's headline to the clipboard.</div>
<div class="grid">
  <div class="panel wide"><button class="copy-btn" onclick="copyTitle('fct_panel', this)">copy</button><div id="fct_panel"></div></div>
  <div class="panel wide"><button class="copy-btn" onclick="copyTitle('boundary_panel', this)">copy</button><div id="boundary_panel"></div></div>
  <div class="panel wide"><button class="copy-btn" onclick="copyTitle('decay_panel', this)">copy</button><div id="decay_panel"></div></div>
  <div class="note wide">Each point: pooled sum(valid)/sum(total) over all 16 bursts x 3 seeds at that
  send index, not a per-burst mean (bursts are equal-sized, so the two happen to coincide here).</div>
</div>
<script>
const DATA = __PAYLOAD__;
const B = [1, 2, 4, 8, 16, 32, 64, 128, 256];
const NS = [1, 4, 16];
const NCOLORS = {1: "#2563eb", 4: "#d97706", 16: "#16a34a"};
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

function mean(a) { return a.length ? a.reduce((x,y)=>x+y,0)/a.length : null; }
function tcrit95(n) {
  // t-distribution 95% two-sided critical value, small-n table (df = n-1)
  const T = {1: 12.71, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571};
  return T[Math.min(n-1,5)] || 1.96;
}

function fctPanel() {
  if (!DATA.fct_panel.length) {
    document.getElementById("fct_panel").innerHTML =
      "<p style='color:#888;font-size:13px;'>No FCT data (c3_fct.csv not built yet).</p>";
    return;
  }
  const traces = [];
  for (const n of NS) {
    for (const longgap of [false, true]) {
      const rows = DATA.fct_panel.filter(r => r.N === n && r.longgap === longgap);
      if (!rows.length) continue;
      const byB = B.map(b => {
        const vals = rows.filter(r => r.B === b).map(r => r.ratio);
        return {b, vals, m: mean(vals)};
      }).filter(d => d.vals.length);
      const label = "N=" + n + (longgap ? " (50-RTT gap)" : "");
      traces.push({
        type: "scatter", mode: "lines+markers", name: label,
        x: byB.map(d => String(d.b)), y: byB.map(d => d.m),
        line: {color: NCOLORS[n], dash: longgap ? "dash" : "solid"},
        marker: {size: 7},
        error_y: {type: "data", array: byB.map(d => d.vals.length > 1 ?
          tcrit95(d.vals.length) * Math.sqrt(d.vals.reduce((s,v)=>s+(v-d.m)**2,0)/(d.vals.length-1)) / Math.sqrt(d.vals.length) : 0)},
      });
      // per-seed points, faint
      traces.push({
        type: "scatter", mode: "markers", name: label + " (seeds)", showlegend: false,
        x: rows.map(r => String(r.B)), y: rows.map(r => r.ratio),
        marker: {size: 4, color: NCOLORS[n], opacity: 0.35},
        hovertemplate: "B=%{x}<br>ratio=%{y:.3f}<br>" + label + "<extra></extra>",
      });
    }
  }
  plotWithHeadline("fct_panel", traces, {
    title: {text: "Panel 1: src0 total FCT normalized within each N -- FCT(B)/FCT(B=1), categorical B", font: {size: 14}},
    xaxis: {title: "buffer size B", type: "category", categoryorder: "array", categoryarray: B.map(String)},
    yaxis: {title: "FCT(B) / FCT(B=1), within same N"},
    legend: {orientation: "h", y: -0.25}, margin: {t: 40, b: 90}, height: 440,
  }, {responsive: true});
}

function boundaryPanel() {
  if (!DATA.boundary_panel.length) {
    document.getElementById("boundary_panel").innerHTML =
      "<p style='color:#888;font-size:13px;'>No boundary data (c3_boundary.csv not built yet).</p>";
    return;
  }
  const traces = [];
  for (const n of [4, 16]) {
    for (const longgap of [false, true]) {
      const rows = DATA.boundary_panel.filter(r => r.N === n && r.longgap === longgap)
        .sort((a,c)=>a.B-c.B);
      if (!rows.length) continue;
      const label = "N=" + n + (longgap ? " (50-RTT gap)" : "") + " observed";
      traces.push({
        type: "scatter", mode: "lines+markers", name: label,
        x: rows.map(r => String(r.B)), y: rows.map(r => r.mean_observed),
        line: {color: NCOLORS[n], dash: longgap ? "dash" : "solid"}, marker: {size: 7},
        hovertemplate: "B=%{x}<br>observed fresh=%{y:.2f}<br>" + label + "<extra></extra>",
      });
    }
  }
  // predicted min(B,tail) -- one line is enough (tail barely varies with N at drained gap,
  // per PLAN.md's prediction); show it once using N=4 drained's predicted values.
  const predRows = DATA.boundary_panel.filter(r => r.N === 4 && !r.longgap).sort((a,c)=>a.B-c.B);
  if (predRows.length) {
    traces.push({
      type: "scatter", mode: "lines", name: "predicted min(B, tail)",
      x: predRows.map(r => String(r.B)), y: predRows.map(r => r.mean_predicted),
      line: {color: "#888", dash: "dot", width: 2},
    });
  }
  plotWithHeadline("boundary_panel", traces, {
    title: {text: "Panel 2: fresh-at-burst-start, observed vs predicted min(B,tail), categorical B (dashed = 50-RTT gap control)", font: {size: 14}},
    xaxis: {title: "buffer size B", type: "category", categoryorder: "array", categoryarray: B.map(String)},
    yaxis: {title: "mean EVs valid at first draw of next burst"},
    legend: {orientation: "h", y: -0.25}, margin: {t: 40, b: 90}, height: 440,
  }, {responsive: true});
}

function decayPanel() {
  if (!DATA.decay_panel.length) {
    document.getElementById("decay_panel").innerHTML =
      "<p style='color:#888;font-size:13px;'>No decay data (c3_decay.csv not built yet, or N=16 cells not run).</p>";
    return;
  }
  const BCOLORS = ["#8c510a","#bf812d","#dfc27d","#80cdc1","#35978f","#01665e",
                    "#762a83","#9970ab","#d6604d"];
  const traces = B.map((b,i) => {
    const rows = DATA.decay_panel.filter(r => r.B === b).sort((a,c)=>a.send_index-c.send_index);
    return {
      type: "scatter", mode: "lines", name: "B=" + b,
      x: rows.map(r => r.send_index), y: rows.map(r => r.p_valid),
      line: {color: BCOLORS[i % BCOLORS.length]},
      hovertemplate: "send #%{x} in burst<br>B=" + b + "<br>P(valid draw)=%{y:.3f}<extra></extra>",
    };
  });
  plotWithHeadline("decay_panel", traces, {
    title: {text: "Panel 3: P(valid draw) by send index within a burst, N=16 only, one line per B", font: {size: 14}},
    xaxis: {title: "send index since burst start (0 = first send of this burst)"},
    yaxis: {title: "P(valid draw)", range: [0, 1]},
    legend: {orientation: "h", y: -0.25}, margin: {t: 40, b: 90}, height: 440,
  }, {responsive: true});
}

fctPanel();
boundaryPanel();
decayPanel();
</script>
</body></html>
"""


if __name__ == "__main__":
    main()
