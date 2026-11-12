#!/usr/bin/env python3
"""C2 (F=16, 16 of 32 ToR0 uplinks killed transiently) restricted to draws
made WHILE frozen (frozen_mode==1): send-time k, valid/random/stale draw
split, ACKs-per-SEND-to-SEND -- same three diagnostics and SAME presentation
as C1's own interactive.html (barsPanel/sendKPanel/acksWindowPanel: B on the
x-axis as categories, stacked k/ACK-count bars with the rare-bucket merge,
grouped valid/random/stale bars, identical colors/legend/margin layout).
Only one scenario here (frozen-mode draws of F=16), so each panel is a
single plot instead of C1's healthy/degraded pair.

Reuses C2's already-committed data; see freezing_mode.py for the split/a_i
computation and send_occupancy.py for the k computation (this script only
re-filters and renormalizes its (k, frozen_mode) rows to frozen_mode==1).

Inputs (no new sim, no new trace):
  ../../C2/data/c2_send_occupancy.csv   (scenario,B,k,frozen_mode,n_sends,share)
  ../../C2/data/c2_freezing_split.csv   (scenario,B,n_frozen_draws,valid/random/stale/other_frac)
  ../../C2/data/c2_freezing_acks.csv    (scenario,B,n_acks,share,n_frozen_draws)

Writes:
  ../NSCC/data/freezing_mode.json
  ../NSCC/plots/freezing_mode.html
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
C1 = HERE.parent
C2 = C1.parent / "C2"
OUT_DIR = C1 / "NSCC"

BS = [1, 2, 4, 8, 16, 32, 64, 128, 256]
SCEN_F16 = "16 ToR0 uplinks, transient kill (10-110us)"


def k_hist_rows() -> list[dict]:
    """Same shape as C1's c1_send_occupancy.csv rows (scenario,B,k,n_sends,
    share), but re-filtered to frozen_mode==1 and renormalized so share
    sums to 1 within that subset per B (the source file's share is over
    ALL post-warmup draws, frozen and non-frozen pooled)."""
    rows = list(csv.DictReader(open(C2 / "data" / "c2_send_occupancy.csv")))
    sub = [r for r in rows if r["scenario"] == SCEN_F16 and r["frozen_mode"] == "1"]
    out = []
    for b in BS:
        bs = [r for r in sub if int(r["B"]) == b]
        n_total = sum(int(r["n_sends"]) for r in bs)
        if n_total == 0:
            continue
        for r in bs:
            out.append(dict(B=b, k=int(r["k"]), n_sends=int(r["n_sends"]),
                             share=int(r["n_sends"]) / n_total))
    return out


def split_rows() -> list[dict]:
    rows = list(csv.DictReader(open(C2 / "data" / "c2_freezing_split.csv")))
    return [dict(B=int(r["B"]), hosts=32, draws=int(r["n_frozen_draws"]),
                  valid_frac=float(r["valid_frac"]), random_frac=float(r["random_frac"]),
                  stale_frac=float(r["stale_frac"])) for r in rows]


def acks_window_rows() -> list[dict]:
    rows = list(csv.DictReader(open(C2 / "data" / "c2_freezing_acks.csv")))
    return [dict(B=int(r["B"]), n_acks=int(r["n_acks"]), share=float(r["share"]),
                  n_sends_post=int(r["n_frozen_draws"])) for r in rows]


def main() -> None:
    summary = split_rows()
    send_k = k_hist_rows()
    acks_window = acks_window_rows()
    payload = dict(summary=summary, send_k=send_k, acks_window=acks_window)

    data_dir = OUT_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "freezing_mode.json").write_text(json.dumps(payload), encoding="utf-8")
    print("wrote", data_dir / "freezing_mode.json")
    print(f"split cells: {len(summary)}  send_k rows: {len(send_k)}  "
          f"acks_window rows: {len(acks_window)}")

    html = TEMPLATE.replace("__PAYLOAD__", json.dumps(payload))
    plots_dir = OUT_DIR / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    (plots_dir / "freezing_mode.html").write_text(html, encoding="utf-8")
    print("wrote", plots_dir / "freezing_mode.html")


TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8">
<title>C2 - inside Freezing Mode (F=16)</title>
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
<h1>C2: draws made WHILE frozen -- EV source split, send-time k, ACKs/window (F=16)</h1>
<div class="note">Same three diagnostics and layout as C1's own page (<code>interactive.html</code>),
but restricted to draws with <code>frozen_mode==1</code> at draw time: F=16 (16 of 32 ToR0 uplinks
killed, transient 10-110us), NSCC, freezing LB, trim ON, 16 MiB, seed 42, ToR0 hosts (32). Only the
slice of traffic actually inside Freezing Mode -- not pooled with the surrounding normal-mode sends
before/after the kill window. Reuses C2's existing traces/data (freezing_mode.py), no new sim.
Split: fractions over frozen-mode EV draws only; valid + random + stale = 1 (random = ev_random +
ev_explore). Send-time k: valid EVs in the buffer immediately before a frozen-mode draw, renormalized
to sum to 1 within the frozen-mode subset per B. ACKs/window: ACKs received since the previous draw
(ECN-marked or not), kept only when the window's own closing draw is itself frozen_mode==1.</div>
<div class="grid">
  <div class="panel"><button class="copy-btn" onclick="copyTitle('bars_frozen', this)">copy</button><div id="bars_frozen"></div></div>
  <div class="panel"><button class="copy-btn" onclick="copyTitle('sendk_frozen', this)">copy</button><div id="sendk_frozen"></div></div>
  <div class="panel wide"><button class="copy-btn" onclick="copyTitle('acks_window_frozen', this)">copy</button><div id="acks_window_frozen"></div></div>
</div>
<script>
const DATA = __PAYLOAD__;
const B = [1, 2, 4, 8, 16, 32, 64, 128, 256];
const COL = {valid: "#22a884", random: "#94a3b8", stale: "#dc2626"};
const B_CATS = B.map(b => "B=" + b);

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

function barsPanel() {
  const rows = DATA.summary;
  const traces = ["valid_frac", "random_frac", "stale_frac"].map(key => {
    const name = key.replace("_frac", "");
    return {
      type: "bar", name: name,
      x: rows.map(r => "B=" + r.B), y: rows.map(r => r[key]),
      marker: {color: COL[name]},
      hovertemplate: "%{x}<br>" + name + " = %{y:.4f}<extra></extra>",
    };
  });
  plotWithHeadline("bars_frozen", traces, {
    title: {text: "Share of EV draws, 16 MiB -- frozen-mode draws only (F=16)", font: {size: 14}},
    barmode: "group", yaxis: {title: "fraction of frozen-mode draws", range: [0, 1]},
    xaxis: {title: "buffer size B", categoryorder: "array", categoryarray: B_CATS},
    legend: {orientation: "h", y: -0.3}, margin: {t: 40, b: 100}, height: 440,
  }, {responsive: true});
}

function sendKPanel() {
  const kColors = ["#1b7837", "#5aae61", "#a6d96a", "#fee08b", "#fdae61", "#d73027", "#a50026"];
  const kMaxScen = Math.max(0, ...DATA.send_k.map(r => r.k));
  const totalByB = B.map(b => DATA.send_k
    .filter(r => r.B === b)
    .reduce((s, r) => s + r.n_sends, 0));
  const RARE_SHARE = 1e-4;
  const maxShareOf = k => Math.max(0, ...DATA.send_k
    .filter(r => r.k === k).map(r => r.share));
  const individualKs = [];
  let firstRareK = null;
  for (let k = 0; k <= kMaxScen; k++) {
    if (maxShareOf(k) >= RARE_SHARE || k === 0) individualKs.push(k);
    else { firstRareK = firstRareK === null ? k : firstRareK; }
  }
  const traces = [];
  for (const k of individualKs) {
    const rows = B.map((b, i) => {
      const r = DATA.send_k.find(r => r.B === b && r.k === k);
      return r ? r.share : (k > b ? null : 0);
    });
    const nSends = B.map((b, i) => {
      const r = DATA.send_k.find(r => r.B === b && r.k === k);
      return r ? r.n_sends : 0;
    });
    traces.push({
      type: "bar", name: "k=" + k, x: B.map(b => "B=" + b), y: rows,
      customdata: nSends.map((n, i) => [n, totalByB[i]]),
      marker: {color: kColors[k % kColors.length]},
      hovertemplate: "%{x}<br>k=" + k + " share=%{y:.4f}" +
        "<br>%{customdata[0]} of %{customdata[1]} frozen-mode draws<extra></extra>",
    });
  }
  if (firstRareK !== null) {
    const rareKs = [];
    for (let k = firstRareK; k <= kMaxScen; k++) if (!individualKs.includes(k)) rareKs.push(k);
    const rows = B.map((b, i) => {
      const n = rareKs.reduce((s, k) => {
        const r = DATA.send_k.find(r => r.B === b && r.k === k);
        return s + (r ? r.share : 0);
      }, 0);
      return n > 0 ? n : (firstRareK > b ? null : 0);
    });
    const nSends = B.map((b, i) => rareKs.reduce((s, k) => {
      const r = DATA.send_k.find(r => r.B === b && r.k === k);
      return s + (r ? r.n_sends : 0);
    }, 0));
    traces.push({
      type: "bar", name: "k>=" + firstRareK + " (rare, <0.01% each)",
      x: B.map(b => "B=" + b), y: rows,
      customdata: nSends.map((n, i) => [n, totalByB[i]]),
      marker: {color: "#9ca3af"},
      hovertemplate: "%{x}<br>k in {" + rareKs.join(",") + "} combined, share=%{y:.6f}" +
        "<br>%{customdata[0]} of %{customdata[1]} frozen-mode draws<extra></extra>",
    });
  }
  const totalRange = Math.min(...totalByB) === Math.max(...totalByB)
    ? String(totalByB[0])
    : Math.min(...totalByB) + "-" + Math.max(...totalByB);
  plotWithHeadline("sendk_frozen", traces, {
    title: {text: "Send-time k, frozen-mode draws only -- F=16", font: {size: 14}},
    barmode: "stack",
    xaxis: {title: "buffer size B", categoryorder: "array", categoryarray: B_CATS},
    yaxis: {title: "share of frozen-mode draws", range: [0, 1]},
    legend: {orientation: "h", y: -0.45}, margin: {t: 60, b: 160}, height: 520,
    annotations: [{
      text: "total frozen-mode draws per B (each draw counted once, binned by k at that draw): " + totalRange,
      showarrow: false, xref: "paper", yref: "paper", x: 0, y: 1.08,
      xanchor: "left", font: {size: 11, color: "#555"},
    }],
  }, {responsive: true});
}

function acksWindowPanel() {
  const rows = DATA.acks_window;
  if (!rows || !rows.length) return;
  const nColors = ["#1b7837", "#5aae61", "#a6d96a", "#fee08b", "#fdae61", "#d73027", "#a50026"];
  const nMax = Math.max(0, ...rows.map(r => r.n_acks));
  const totalByB = B.map(b => rows.filter(r => r.B === b).reduce((s, r) => s + r.n_sends_post, 0));
  const RARE_SHARE = 1e-3;
  const maxShareOf = n => Math.max(0, ...rows.filter(r => r.n_acks === n).map(r => r.share));
  const individualNs = [];
  let firstRareN = null;
  for (let n = 0; n <= nMax; n++) {
    if (maxShareOf(n) >= RARE_SHARE || n <= 1) individualNs.push(n);
    else { firstRareN = firstRareN === null ? n : firstRareN; }
  }
  const traces = [];
  for (const n of individualNs) {
    const y = B.map(b => {
      const r = rows.find(r => r.B === b && r.n_acks === n);
      return r ? r.share : 0;
    });
    traces.push({
      type: "bar", name: n + " ACK" + (n === 1 ? "" : "s"), x: B.map(b => "B=" + b), y,
      marker: {color: nColors[n % nColors.length]},
      hovertemplate: "%{x}<br>" + n + " ACKs/window share=%{y:.4f}<extra></extra>",
    });
  }
  if (firstRareN !== null) {
    const rareNs = [];
    for (let n = firstRareN; n <= nMax; n++) if (!individualNs.includes(n)) rareNs.push(n);
    const y = B.map(b => rareNs.reduce((s, n) => {
      const r = rows.find(r => r.B === b && r.n_acks === n);
      return s + (r ? r.share : 0);
    }, 0));
    traces.push({
      type: "bar", name: firstRareN + "+ ACKs (rare)", x: B.map(b => "B=" + b), y,
      marker: {color: "#9ca3af"},
      hovertemplate: "%{x}<br>" + firstRareN + "+ ACKs combined, share=%{y:.5f}<extra></extra>",
    });
  }
  const totalRange = Math.min(...totalByB) === Math.max(...totalByB)
    ? String(totalByB[0]) : Math.min(...totalByB) + "-" + Math.max(...totalByB);
  plotWithHeadline("acks_window_frozen", traces, {
    title: {text: "ACKs per SEND-to-SEND window, frozen-mode draws only -- F=16", font: {size: 13}},
    barmode: "stack",
    xaxis: {title: "buffer size B", categoryorder: "array", categoryarray: B_CATS},
    yaxis: {title: "share of frozen-mode-closed windows", range: [0, 1]},
    legend: {orientation: "h", y: -0.4}, margin: {t: 50, b: 130}, height: 460,
    annotations: [{
      text: "total windows (sum over ACK-count), per B: " + totalRange,
      showarrow: false, xref: "paper", yref: "paper", x: 0, y: 1.08,
      xanchor: "left", font: {size: 10, color: "#555"},
    }],
  }, {responsive: true});
}

barsPanel();
if (DATA.send_k.length) sendKPanel();
acksWindowPanel();
</script>
</body></html>
"""


if __name__ == "__main__":
    main()
