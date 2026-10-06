#!/usr/bin/env python3
"""C1 results: per-packet EV source split (valid / random / stale) at 4 MiB and 16 MiB.

Reads the exp30 trim-on C1 cells directly (no copy of the runs):
  exp30_packet_trimming_en/runs/a1/<size>/x<n>_ef200/seed42/reps_b<B>/stdout.txt
  x0 = healthy, x32 = all 32 ToR0 uplinks at 50% speed.

Writes:
  ../data/c1_split.csv      one row per (size, scenario, B)
  ../data/c1_split_hosts.csv one row per (size, scenario, B, ToR0 host)
  ../plots/interactive.html  Plotly page (same style as exp30's interactive)

Fractions are over all EV draws of the ToR0 hosts: draws = ev_random + ev_explore
+ ev_valid + ev_stale, and random = ev_random + ev_explore. Draws = new packets +
retransmissions (checked: the excess over unique packets equals the RTX count).
"""
import csv
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
C1 = HERE.parent
EXPERIMENTS = C1.parent.parent  # .../experiments
RUNS = EXPERIMENTS / "exp30_packet_trimming_en" / "runs" / "a1"
DATA = C1 / "data"
PLOTS = C1 / "plots"

SIZES = {4194304: "4 MiB", 16777216: "16 MiB"}
SCEN = {0: "healthy", 32: "32 ToR0 uplinks at 50%"}
BS = [1, 2, 4, 8, 16, 32, 64, 128, 256]
TOR0_HOSTS = 32

FIN = re.compile(
    r"uecSrc (\d+) finished at.*?total packets (\d+).*?"
    r"ev_explore (\d+) ev_random (\d+) ev_valid (\d+) ev_stale (\d+)")


def read_cell(size, x, b):
    path = RUNS / str(size) / f"x{x}_ef200" / "seed42" / f"reps_b{b}" / "stdout.txt"
    if not path.exists():
        return None
    text = path.read_text(errors="replace")
    # (src, packets, explore, random, valid, stale) per finished flow
    return [tuple(int(v) for v in m) for m in FIN.findall(text)]


def host_rows(flows):
    """ToR0 hosts only: uecSrc id < 32 (src ids of ToR0's hosts)."""
    out = []
    for src, pk, ex, rnd, val, st in flows:
        if src >= TOR0_HOSTS:
            continue
        rnd_all = ex + rnd
        draws = rnd_all + val + st
        out.append(dict(packets=pk, draws=draws, valid=val, random=rnd_all, stale=st))
    return out


def frac(rows, key):
    tot = sum(r["draws"] for r in rows)
    return sum(r[key] for r in rows) / tot if tot else float("nan")


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    PLOTS.mkdir(parents=True, exist_ok=True)
    summary, per_host = [], []
    missing = []
    for size, sname in SIZES.items():
        for x, scname in SCEN.items():
            for b in BS:
                flows = read_cell(size, x, b)
                if not flows:
                    missing.append((size, x, b))
                    continue
                rows = host_rows(flows)
                pk = sum(r["packets"] for r in rows)
                dr = sum(r["draws"] for r in rows)
                summary.append(dict(
                    size_bytes=size, size=sname, scenario=scname, x=x, B=b,
                    hosts=len(rows), packets=pk, draws=dr, rtx=dr - pk,
                    valid_frac=frac(rows, "valid"), random_frac=frac(rows, "random"),
                    stale_frac=frac(rows, "stale")))
                for i, r in enumerate(rows):
                    d = r["draws"] or 1
                    per_host.append(dict(
                        size=sname, scenario=scname, B=b, host=i,
                        valid_frac=r["valid"] / d, random_frac=r["random"] / d,
                        stale_frac=r["stale"] / d))
    if missing:
        print("MISSING cells (not run yet):", missing)
    with open(DATA / "c1_split.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        w.writeheader()
        w.writerows(summary)
    with open(DATA / "c1_split_hosts.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(per_host[0].keys()))
        w.writeheader()
        w.writerows(per_host)
    for s in summary:
        tot = s["valid_frac"] + s["random_frac"] + s["stale_frac"]
        assert abs(tot - 1) < 1e-9, s
    build_html(summary, per_host)
    print(f"cells: {len(summary)}  per-host rows: {len(per_host)}")


def build_html(summary, per_host):
    payload = json.dumps(dict(summary=summary, per_host=per_host))
    html = TEMPLATE.replace("__PAYLOAD__", payload)
    (PLOTS / "interactive.html").write_text(html, encoding="utf-8")
    print("wrote", PLOTS / "interactive.html")


TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8">
<title>C1 - EV source split</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/plotly.js/2.35.3/plotly.min.js"></script>
<style>
body { font-family: system-ui, sans-serif; margin: 16px; color: #111; }
h1 { font-size: 18px; margin: 0 0 4px; }
.note { font-size: 12px; color: #555; margin-bottom: 12px; max-width: 980px; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.panel { border: 1px solid #ddd; border-radius: 6px; padding: 6px; }
</style></head>
<body>
<h1>C1: per-packet EV source split (valid / random / stale)</h1>
<div class="note">exp30 trim-on configuration, MPRDMA, freezing LB, tornado, trim ON, seed 42.
Fractions over all EV draws of the 32 ToR0 hosts (new packets + retransmissions), so
valid + random + stale = 1. Random includes explore. Stale = frozen pop of an invalid slot
(expected 0 here: trim on, no RTO, no freeze). B=64..256 use duplicate EVs (-paths 32).</div>
<div class="grid">
  <div class="panel"><div id="bars4"></div></div>
  <div class="panel"><div id="bars16"></div></div>
  <div class="panel"><div id="host4"></div></div>
  <div class="panel"><div id="host16"></div></div>
</div>
<script>
const DATA = __PAYLOAD__;
const B = [1, 2, 4, 8, 16, 32, 64, 128, 256];
const COL = {valid: "#22a884", random: "#94a3b8", stale: "#dc2626"};
const SIZES = ["4 MiB", "16 MiB"];

function barsFor(size, divId) {
  const traces = [];
  for (const key of ["valid_frac", "random_frac", "stale_frac"]) {
    const name = key.replace("_frac", "");
    for (const scen of ["healthy", "32 ToR0 uplinks at 50%"]) {
      const rows = DATA.summary.filter(r => r.size === size && r.scenario === scen);
      traces.push({
        type: "bar", name: name + " | " + scen,
        x: rows.map(r => "B=" + r.B), y: rows.map(r => r[key]),
        marker: {color: COL[name], opacity: scen === "healthy" ? 1 : 0.55},
        legendgroup: scen, showlegend: key === "valid_frac",
        hovertemplate: "%{x}<br>" + name + " = %{y:.4f}<extra>" + scen + "</extra>",
      });
    }
  }
  Plotly.newPlot(divId, traces, {
    title: {text: "Share of EV draws, " + size, font: {size: 14}},
    barmode: "group", yaxis: {title: "fraction of draws", range: [0, 1]},
    xaxis: {title: "buffer size B"}, legend: {orientation: "h", y: -0.25},
    margin: {t: 40, b: 80}, height: 420,
  }, {responsive: true});
}

function hostsFor(size, divId) {
  const traces = [];
  for (const scen of ["healthy", "32 ToR0 uplinks at 50%"]) {
    const rows = DATA.per_host.filter(r => r.size === size && r.scenario === scen);
    traces.push({
      type: "box", name: scen, x: rows.map(r => "B=" + r.B), y: rows.map(r => r.valid_frac),
      boxpoints: "all", jitter: 0.4, pointpos: 0, marker: {size: 4},
      line: {width: 1},
      hovertemplate: "%{x}<br>valid fraction = %{y:.3f}<extra>" + scen + "</extra>",
    });
  }
  Plotly.newPlot(divId, traces, {
    title: {text: "Per ToR0 host: valid fraction, " + size, font: {size: 14}},
    boxmode: "group", yaxis: {title: "valid / all draws", range: [0, 1]},
    xaxis: {title: "buffer size B", categoryorder: "array", categoryarray: B.map(b => "B=" + b)},
    legend: {orientation: "h", y: -0.25}, margin: {t: 40, b: 80}, height: 420,
  }, {responsive: true});
}

barsFor("4 MiB", "bars4");
barsFor("16 MiB", "bars16");
hostsFor("4 MiB", "host4");
hostsFor("16 MiB", "host16");
</script>
</body></html>
"""

if __name__ == "__main__":
    main()
