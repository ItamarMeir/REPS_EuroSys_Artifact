#!/usr/bin/env python3
"""C1 results page, 16 MiB only (the 4 MiB runs stay on disk, not presented here).

Inputs (both committed):
  ../data/c1_split.csv         per-packet EV source split, from exp30 trim-on C1 cells
  ../data/c1_split_hosts.csv   per ToR0 host split
  ../data/c1_occupancy.csv     buffer occupancy from the event trace, occupancy.py

Reads the exp30 trim-on C1 cell stdout directly (no copied runs) to rebuild the
split CSVs:
  exp30_packet_trimming_en/runs/a1/16777216/x<n>_ef200/seed42/reps_b<B>/stdout.txt
  x0 = healthy, x32 = all 32 ToR0 uplinks at 50% speed.

Writes:
  ../data/c1_split.csv, ../data/c1_split_hosts.csv
  ../plots/interactive.html

Split fractions: over all EV draws of the 32 ToR0 hosts (new packets + retransmissions).
random = ev_random + ev_explore. valid + random + stale = 1.
"""
import csv
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
C1 = HERE.parent
EXPERIMENTS = C1.parent.parent
RUNS = EXPERIMENTS / "exp30_packet_trimming_en" / "runs" / "a1"
DATA = C1 / "data"
PLOTS = C1 / "plots"

SIZE = 16777216
SIZE_NAME = "16 MiB"
SCEN = {0: "healthy", 32: "32 ToR0 uplinks at 50%"}
BS = [1, 2, 4, 8, 16, 32, 64, 128, 256]
TOR0_HOSTS = 32

FIN = re.compile(
    r"uecSrc (\d+) finished at.*?total packets (\d+).*?"
    r"ev_explore (\d+) ev_random (\d+) ev_valid (\d+) ev_stale (\d+)")


def read_cell(x, b):
    path = RUNS / str(SIZE) / f"x{x}_ef200" / "seed42" / f"reps_b{b}" / "stdout.txt"
    if not path.exists():
        return None
    return [tuple(int(v) for v in m) for m in FIN.findall(path.read_text(errors="replace"))]


def host_rows(flows):
    out = []
    for src, pk, ex, rnd, val, st in flows:
        if src >= TOR0_HOSTS:
            continue
        rnd_all = ex + rnd
        out.append(dict(packets=pk, draws=rnd_all + val + st,
                        valid=val, random=rnd_all, stale=st))
    return out


def frac(rows, key):
    tot = sum(r["draws"] for r in rows)
    return sum(r[key] for r in rows) / tot if tot else float("nan")


def build_split():
    summary, per_host, missing = [], [], []
    for x, scname in SCEN.items():
        for b in BS:
            flows = read_cell(x, b)
            if not flows:
                missing.append((x, b))
                continue
            rows = host_rows(flows)
            pk = sum(r["packets"] for r in rows)
            dr = sum(r["draws"] for r in rows)
            summary.append(dict(
                size_bytes=SIZE, size=SIZE_NAME, scenario=scname, x=x, B=b,
                hosts=len(rows), packets=pk, draws=dr, rtx=dr - pk,
                valid_frac=frac(rows, "valid"), random_frac=frac(rows, "random"),
                stale_frac=frac(rows, "stale")))
            for i, r in enumerate(rows):
                d = r["draws"] or 1
                per_host.append(dict(
                    size=SIZE_NAME, scenario=scname, B=b, host=i,
                    valid_frac=r["valid"] / d, random_frac=r["random"] / d,
                    stale_frac=r["stale"] / d))
    if missing:
        print("MISSING split cells:", missing)
    for s in summary:
        assert abs(s["valid_frac"] + s["random_frac"] + s["stale_frac"] - 1) < 1e-9, s
    return summary, per_host


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def load_occupancy():
    p = DATA / "c1_occupancy.csv"
    if not p.exists():
        return []
    out = []
    for r in csv.DictReader(open(p)):
        out.append(dict(
            scenario=r["scenario"], B=int(r["B"]),
            share_le2_after_t0=float(r["share_le2_after_t0"]),
            share_le2_backlog=float(r["share_le2_backlog"]),
            max_fresh_backlog=int(r["max_fresh_backlog"]),
            n_ge3_backlog=int(r["n_ge3_backlog"]),
            drain_share=float(r["drain_share"]),
            rows_backlog=int(r["rows_backlog"]),
            rows_after_t0=int(r["rows_after_t0"]),
            crosscheck_match=r["crosscheck_match"] == "True"))
    return out


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    PLOTS.mkdir(parents=True, exist_ok=True)
    summary, per_host = build_split()
    write_csv(DATA / "c1_split.csv", summary)
    write_csv(DATA / "c1_split_hosts.csv", per_host)
    occ = load_occupancy()
    payload = json.dumps(dict(summary=summary, per_host=per_host, occupancy=occ))
    (PLOTS / "interactive.html").write_text(TEMPLATE.replace("__PAYLOAD__", payload), encoding="utf-8")
    print(f"split cells: {len(summary)}  occupancy cells: {len(occ)}")
    print("wrote", PLOTS / "interactive.html")


TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8">
<title>C1 - EV source split and buffer occupancy</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/plotly.js/2.35.3/plotly.min.js"></script>
<style>
body { font-family: system-ui, sans-serif; margin: 16px; color: #111; }
h1 { font-size: 18px; margin: 0 0 4px; }
.note { font-size: 12px; color: #555; margin-bottom: 12px; max-width: 980px; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.panel { border: 1px solid #ddd; border-radius: 6px; padding: 6px; }
.wide { grid-column: 1 / -1; }
</style></head>
<body>
<h1>C1: EV source split and buffer occupancy, 16 MiB</h1>
<div class="note">exp30 trim-on configuration, MPRDMA, freezing LB, tornado 16 MiB, trim ON, seed 42,
ToR0 hosts (32). Healthy vs all 32 ToR0 uplinks at 50% speed.
Split: fractions over all EV draws (new packets + retransmissions); valid + random + stale = 1.
Occupancy: fresh = valid buffer entries after each event (from the event trace).
Claim: after each host's first ACK, during backlog (before its last send), the buffer holds at most 2
valid EVs. B=1 and 2 are greyed: the buffer cannot hold more than 2, so they cannot test the claim.</div>
<div class="grid">
  <div class="panel"><div id="bars"></div></div>
  <div class="panel"><div id="host"></div></div>
  <div class="panel wide"><div id="occ"></div></div>
</div>
<script>
const DATA = __PAYLOAD__;
const B = [1, 2, 4, 8, 16, 32, 64, 128, 256];
const COL = {valid: "#22a884", random: "#94a3b8", stale: "#dc2626"};
const SCEN = ["healthy", "32 ToR0 uplinks at 50%"];

function barsPanel() {
  const traces = [];
  for (const key of ["valid_frac", "random_frac", "stale_frac"]) {
    const name = key.replace("_frac", "");
    for (const scen of SCEN) {
      const rows = DATA.summary.filter(r => r.scenario === scen);
      traces.push({
        type: "bar", name: name + " | " + scen,
        x: rows.map(r => "B=" + r.B), y: rows.map(r => r[key]),
        marker: {color: COL[name], opacity: scen === "healthy" ? 1 : 0.55},
        legendgroup: scen, showlegend: key === "valid_frac",
        hovertemplate: "%{x}<br>" + name + " = %{y:.4f}<extra>" + scen + "</extra>",
      });
    }
  }
  Plotly.newPlot("bars", traces, {
    title: {text: "Share of EV draws, 16 MiB", font: {size: 14}},
    barmode: "group", yaxis: {title: "fraction of draws", range: [0, 1]},
    xaxis: {title: "buffer size B"}, legend: {orientation: "h", y: -0.25},
    margin: {t: 40, b: 80}, height: 420,
  }, {responsive: true});
}

function hostPanel() {
  const traces = [];
  for (const scen of SCEN) {
    const rows = DATA.per_host.filter(r => r.scenario === scen);
    traces.push({
      type: "box", name: scen, x: rows.map(r => "B=" + r.B), y: rows.map(r => r.valid_frac),
      boxpoints: "all", jitter: 0.4, pointpos: 0, marker: {size: 4}, line: {width: 1},
      hovertemplate: "%{x}<br>valid fraction = %{y:.3f}<extra>" + scen + "</extra>",
    });
  }
  Plotly.newPlot("host", traces, {
    title: {text: "Per ToR0 host: valid fraction, 16 MiB", font: {size: 14}},
    boxmode: "group", yaxis: {title: "valid / all draws", range: [0, 1]},
    xaxis: {title: "buffer size B", categoryorder: "array", categoryarray: B.map(b => "B=" + b)},
    legend: {orientation: "h", y: -0.25}, margin: {t: 40, b: 80}, height: 420,
  }, {responsive: true});
}

function occPanel() {
  const traces = [];
  const styles = {healthy: {color: "#22a884", dash: "solid"},
                  "32 ToR0 uplinks at 50%": {color: "#2563eb", dash: "dash"}};
  for (const scen of SCEN) {
    const rows = DATA.occupancy.filter(r => r.scenario === scen).sort((a, b) => a.B - b.B);
    const grey = rows.map(r => r.B <= 2);
    const hover = rows.map(r =>
      "B=" + r.B + "<br>after first ACK: " + (100 * r.share_le2_after_t0).toFixed(2) + "%" +
      "<br>backlog: " + (100 * r.share_le2_backlog).toFixed(2) + "%" +
      "<br>max fresh in backlog: " + r.max_fresh_backlog +
      "<br>backlog rows with >=3: " + r.n_ge3_backlog +
      "<br>drain share (after last send): " + (100 * r.drain_share).toFixed(1) + "%");
    traces.push({
      type: "scatter", mode: "lines+markers", name: "after first ACK | " + scen,
      x: rows.map(r => r.B), y: rows.map(r => r.share_le2_after_t0),
      line: {color: styles[scen].color, dash: "solid"},
      marker: {color: rows.map((r, i) => grey[i] ? "#9ca3af" : styles[scen].color), size: 9},
      text: hover, hovertemplate: "%{text}<extra>after first ACK</extra>",
    });
    traces.push({
      type: "scatter", mode: "lines+markers", name: "backlog only | " + scen,
      x: rows.map(r => r.B), y: rows.map(r => r.share_le2_backlog),
      line: {color: styles[scen].color, dash: "dot"},
      marker: {symbol: "x", color: styles[scen].color, size: 8},
      text: hover, hovertemplate: "%{text}<extra>backlog</extra>",
    });
  }
  Plotly.newPlot("occ", traces, {
    title: {text: "Share of trace rows with <= 2 valid EVs, 16 MiB", font: {size: 14}},
    xaxis: {title: "buffer size B", type: "log", tickvals: B, ticktext: B.map(String)},
    yaxis: {title: "share of rows with fresh <= 2", range: [0.95, 1.001], tickformat: ".1%"},
    legend: {orientation: "h", y: -0.25}, margin: {t: 40, b: 80}, height: 420,
  }, {responsive: true});
}

barsPanel();
hostPanel();
occPanel();
</script>
</body></html>
"""


if __name__ == "__main__":
    main()
