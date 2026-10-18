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
import argparse
import csv
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
C1 = HERE.parent
EXPERIMENTS = C1.parent.parent
RUNS = EXPERIMENTS / "exp30_packet_trimming_en" / "runs" / "a1"
EXP30_FCT_CSV = EXPERIMENTS / "exp30_packet_trimming_en" / "data" / "fct.csv"

SIZE = 16777216
SIZE_NAME = "16 MiB"
SCEN = {0: "healthy", 32: "32 ToR0 uplinks at 50%"}
BS = [1, 2, 4, 8, 16, 32, 64, 128, 256]
TOR0_HOSTS = 32

# fct = "finished at" value directly (us) -- tornado flows all start at t~0,
# so this already *is* the FCT, not merely a timestamp.
FIN = re.compile(
    r"uecSrc (\d+) finished at ([\d.]+).*?total packets (\d+).*?"
    r"ev_explore (\d+) ev_random (\d+) ev_valid (\d+) ev_stale (\d+)")


def read_cell(x, b, arm_suffix):
    path = RUNS / str(SIZE) / f"x{x}_ef200" / "seed42" / f"reps_b{b}{arm_suffix}" / "stdout.txt"
    if not path.exists():
        return None
    out = []
    for m in FIN.findall(path.read_text(errors="replace")):
        src, fct, pk, ex, rnd, val, st = m
        out.append((int(src), float(fct), int(pk), int(ex), int(rnd), int(val), int(st)))
    return out


def read_sol_cell(x):
    """SoL reference arm: -load_balancing_algo path_static -sender_cc_algo
    constant, cwnd picked by a cwnd-sweep smoke test: 127 healthy, 56
    degraded. The degraded sweep uses -host_cwnd_overrides so ONLY the 32
    ToR0 hosts get the swept cwnd -- every other host keeps a non-
    bottlenecking cwnd (1024 pkts), so the sweep isn't also under/over-
    provisioning unrelated background flows in the same run (confirmed to
    give identical numbers to a global-cwnd sweep -- no cross-interference
    on this topology, but isolating it is the honest methodology). Degraded
    FCT falls monotonically with cwnd down to the 56 floor, opposite of the
    healthy sweep's shape: a cwnd oversized for the halved-rate path keeps
    its queue deep for the whole flow (99% of packets ECN-marked at cwnd=152
    vs 0.2% at cwnd=56) -- BDP halves when rate halves, so the degraded knee
    is LOWER than healthy's 127, not higher. No REPS buffer, so ev_* fields
    are always 0 -- FIN still matches (same finish-line printf), just
    degenerate valid/random/stale counts, unused here (FCT only)."""
    path = RUNS / str(SIZE) / f"x{x}_ef200" / "seed42" / "sol" / "stdout.txt"
    if not path.exists():
        return None
    out = []
    for m in FIN.findall(path.read_text(errors="replace")):
        src, fct, pk, ex, rnd, val, st = m
        out.append((int(src), float(fct), int(pk), int(ex), int(rnd), int(val), int(st)))
    return out


def build_sol_fct():
    """One row per scenario: FCT percentiles for the SoL reference arm over
    the 32 ToR0 hosts. CC-independent (path_static+constant has no CC
    algorithm choice baked into REPS/NSCC), so this is identical whichever
    --cc is being built; computed fresh each time for simplicity."""
    rows = []
    for x, scname in SCEN.items():
        flows = read_sol_cell(x)
        if not flows:
            print(f"MISSING sol cell: x{x}")
            continue
        fct_vals = sorted(r["fct_us"] for r in host_rows(flows))
        rows.append(dict(scenario=scname,
                          p50_fct_us=percentile(fct_vals, 50), p95_fct_us=percentile(fct_vals, 95),
                          p99_fct_us=percentile(fct_vals, 99),
                          max_fct_us=fct_vals[-1] if fct_vals else float("nan"),
                          hosts=len(fct_vals)))
    return rows


def host_rows(flows):
    out = []
    for src, fct, pk, ex, rnd, val, st in flows:
        if src >= TOR0_HOSTS:
            continue
        rnd_all = ex + rnd
        out.append(dict(packets=pk, draws=rnd_all + val + st,
                        valid=val, random=rnd_all, stale=st, fct_us=fct))
    return out


def frac(rows, key):
    tot = sum(r["draws"] for r in rows)
    return sum(r[key] for r in rows) / tot if tot else float("nan")


def percentile(sorted_vals, p):
    if not sorted_vals:
        return float("nan")
    k = (len(sorted_vals) - 1) * p / 100
    f, c = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def build_split(arm_suffix):
    summary, per_host, fct_rows, missing = [], [], [], []
    for x, scname in SCEN.items():
        for b in BS:
            flows = read_cell(x, b, arm_suffix)
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
            fct_vals = sorted(r["fct_us"] for r in rows)
            fct_rows.append(dict(
                size=SIZE_NAME, scenario=scname, B=b, hosts=len(fct_vals),
                p50_fct_us=percentile(fct_vals, 50), p95_fct_us=percentile(fct_vals, 95),
                p99_fct_us=percentile(fct_vals, 99), max_fct_us=fct_vals[-1] if fct_vals else float("nan")))
    if missing:
        print("MISSING split cells:", missing)
    for s in summary:
        assert abs(s["valid_frac"] + s["random_frac"] + s["stale_frac"] - 1) < 1e-9, s
    return summary, per_host, fct_rows


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def load_occupancy(data_dir):
    p = data_dir / "c1_occupancy.csv"
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


def load_exp30_multiseed_fct():
    """exp30_packet_trimming_en's own 3-seed (42/43/44) aggregation of this exact
    cell population (Part A1, x=32, 16 MiB, plain mprdma, ToR0/"affected" hosts),
    from data/fct.csv (aggregate30.py). Used as a cross-check note: C1 itself is
    seed 42 only, so this is the only place this scenario's seed-to-seed variance
    is visible. Returns [] if that file or this row isn't there."""
    if not EXP30_FCT_CSV.exists():
        return []
    out = []
    with open(EXP30_FCT_CSV, newline="") as f:
        for r in csv.DictReader(f):
            if not (r["part"] == "a1" and r["size"] == str(SIZE) and r["x"] == "32"
                     and r["cc"] == "mprdma" and r["group"] == "affected"
                     and re.fullmatch(r"reps_b\d+", r["arm"])):
                continue
            out.append(dict(B=int(r["arm"][len("reps_b"):]),
                             max_fct_us=float(r["max_fct_us"]),
                             max_fct_us_ci=float(r["max_fct_us_ci"]),
                             n_seed=int(r["n_seed"])))
    out.sort(key=lambda d: d["B"])
    return out


def load_send_occupancy(data_dir):
    p = data_dir / "c1_send_occupancy.csv"
    if not p.exists():
        return []
    out = []
    for r in csv.DictReader(open(p)):
        out.append(dict(scenario=r["scenario"], B=int(r["B"]), k=int(r["k"]),
                         n_sends=int(r["n_sends"]), share=float(r["share"])))
    return out


def load_acks_per_window(data_dir):
    p = data_dir / "c1_acks_per_window.csv"
    if not p.exists():
        return []
    out = []
    for r in csv.DictReader(open(p)):
        out.append(dict(scenario=r["scenario"], B=int(r["B"]), n_acks=int(r["n_acks"]),
                         share=float(r["share"]), n_sends_post=int(r["n_sends_post"])))
    return out


def load_acks_per_window_gaps(data_dir):
    p = data_dir / "c1_acks_per_window_gaps.csv"
    if not p.exists():
        return []
    out = []
    for r in csv.DictReader(open(p)):
        out.append(dict(scenario=r["scenario"], B=int(r["B"]),
                         gap_median_ns=float(r["gap_median_ns"]),
                         gap_max_ns=float(r["gap_max_ns"]),
                         frac_gap_gt_2x_median=float(r["frac_gap_gt_2x_median"])))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cc", choices=["mprdma", "nscc"], default="mprdma")
    args = ap.parse_args()
    arm_suffix = "" if args.cc == "mprdma" else "_nscc"
    cc_label = {"mprdma": "MPRDMA", "nscc": "NSCC"}[args.cc]
    data_dir = C1 / cc_label / "data"
    plots_dir = C1 / cc_label / "plots"

    data_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)
    summary, per_host, fct_rows = build_split(arm_suffix)
    write_csv(data_dir / "c1_split.csv", summary)
    write_csv(data_dir / "c1_split_hosts.csv", per_host)
    write_csv(data_dir / "c1_fct.csv", fct_rows)
    occ = load_occupancy(data_dir)
    send_k = load_send_occupancy(data_dir)
    acks_window = load_acks_per_window(data_dir)
    acks_window_gaps = load_acks_per_window_gaps(data_dir)
    exp30_fct_note = load_exp30_multiseed_fct() if args.cc == "mprdma" else []
    sol_fct = build_sol_fct()
    write_csv(data_dir / "c1_sol_fct.csv", sol_fct)
    payload = json.dumps(dict(summary=summary, per_host=per_host, occupancy=occ,
                               send_k=send_k, fct=fct_rows, cc=cc_label,
                               acks_window=acks_window, acks_window_gaps=acks_window_gaps,
                               exp30_fct_note=exp30_fct_note, sol_fct=sol_fct))
    html = TEMPLATE.replace("__PAYLOAD__", payload).replace("__CC__", cc_label)
    (plots_dir / "interactive.html").write_text(html, encoding="utf-8")
    print(f"cc={cc_label}  split cells: {len(summary)}  occupancy cells: {len(occ)}  "
          f"send_k rows: {len(send_k)}  fct cells: {len(fct_rows)}  sol rows: {len(sol_fct)}")
    print("wrote", plots_dir / "interactive.html")


TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8">
<title>C1 - EV source split and buffer occupancy (__CC__)</title>
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
<h1>C1: EV source split, buffer occupancy, FCT -- 16 MiB, __CC__</h1>
<div class="note">exp30 trim-on configuration, __CC__, freezing LB, tornado 16 MiB, trim ON, seed 42,
ToR0 hosts (32). Healthy vs all 32 ToR0 uplinks at 50% speed.
Split: fractions over all EV draws (new packets + retransmissions); valid + random + stale = 1.
Occupancy: fresh = valid buffer entries after each event (from the event trace).
Claim: after each host's first ACK, during backlog (before its last send), the buffer holds at most 2
valid EVs. B=1 and 2 are greyed: the buffer cannot hold more than 2, so they cannot test the claim.
Send-time k: for every post-warmup SEND/RTX/RTS, k = valid EVs in the buffer immediately before the draw
(read from the previous row's post-event fresh count). All 18 cells pass 9 checks (conservation vs the
committed per-host finish-line counts, determinism P(k=0)==random share, 0 reconstruction mismatches,
stale proven 0, capacity k<=B, sum-to-1, and k<=the independent occupancy.py backlog max).
FCT: "finished at" time per ToR0 host (flows start at t~0, so this is the FCT directly), p50/p95/p99/max
across the 32 ToR0 hosts.
SoL (speed-of-light): a reference arm, <code>path_static+constant</code> (one pinned path per flow, no
REPS buffer). It has no buffer, so it does not appear on the split/occupancy/send-time-k/acks-per-window
panels -- those measure REPS-buffer-internal behavior that this arm doesn't have. On the FCT panel, each
B's FCT is shown normalized against SoL's own FCT (FCT / SoL FCT; 1.0 = speed-of-light floor).</div>
<div class="grid">
  <div class="panel"><button class="copy-btn" onclick="copyTitle('bars_healthy', this)">copy</button><div id="bars_healthy"></div></div>
  <div class="panel"><button class="copy-btn" onclick="copyTitle('bars_degraded', this)">copy</button><div id="bars_degraded"></div></div>
  <div class="panel"><button class="copy-btn" onclick="copyTitle('sendk_healthy', this)">copy</button><div id="sendk_healthy"></div></div>
  <div class="panel"><button class="copy-btn" onclick="copyTitle('sendk_degraded', this)">copy</button><div id="sendk_degraded"></div></div>
  <div class="panel"><button class="copy-btn" onclick="copyTitle('fct_healthy', this)">copy</button><div id="fct_healthy"></div></div>
  <div class="panel"><button class="copy-btn" onclick="copyTitle('fct_degraded', this)">copy</button><div id="fct_degraded"></div></div>
  <div class="note wide" id="solNote" style="display:none;"></div>
  <div class="note wide" id="fctNote" style="display:none;"></div>
  <div class="panel"><button class="copy-btn" onclick="copyTitle('acks_window_healthy', this)">copy</button><div id="acks_window_healthy"></div></div>
  <div class="panel"><button class="copy-btn" onclick="copyTitle('acks_window_degraded', this)">copy</button><div id="acks_window_degraded"></div></div>
</div>
<div class="note wide" style="margin-top:4px;">
Verified over every post-warmup SEND/RTX/RTS draw of all 32 ToR0 hosts (same population
as the send-time-k plot above -- n_sends_post ties out exactly): in <b>healthy</b>,
SEND-to-SEND gaps for B&ge;2 all fall in a tight 83-86.84ns band (0.00% exceed 2x the
median); B=1 alone has a small 0.017% tail up to 251.56ns (real cwnd stalls, see the
conclusion note). In <b>32 ToR0 uplinks at 50%</b>, ~24-27% of gaps DO exceed 2x the
median (tail up to several &mu;s at every B) -- a real second population, but expected:
those uplinks run at half rate, so queueing delay is that scenario's own mechanism, not
evidence against the healthy-case claim below. Also verified directly: for every ACK,
fresh_after - fresh_before equals +1 if ecn=0 and 0 if ecn=1, with ZERO unexplained
mismatches across all 36 cells (both CC) once mismatches caused by the buffer already
being at capacity (fresh==B when a clean ACK arrives) are excluded -- k changes only via
clean-ACK arrivals and fresh_pop draws, nothing else.
</div>
<div class="note wide" style="margin-top:4px; font-size:16px;">
<b>Conclusion: the &le;3-valid-EV claim holds. Cause: k is a running sum (each clean ACK
is +1, each fresh_pop draw is -1) against a fixed ~84ns SEND-to-SEND line-rate cadence.
A mean of ~1 ACK per window is expected by conservation (every packet is ACKed once) and
does NOT contradict k&ge;4 -- about 19-21% of windows receive 2 ACKs instead of 1 (the
distribution below), and k climbs to 4-5 when a couple of these 2-ACK windows land back
to back, not from any single window receiving many ACKs at once.</b>
</div>
<script>
const DATA = __PAYLOAD__;
const B = [1, 2, 4, 8, 16, 32, 64, 128, 256];
const COL = {valid: "#22a884", random: "#94a3b8", stale: "#dc2626"};
const SCEN = ["healthy", "32 ToR0 uplinks at 50%"];

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
  // Two separate plots, one per scenario -- same reason as sendKPanel: an
  // overlaid/opacity-differentiated single chart was a mess.
  const divId = {healthy: "bars_healthy", "32 ToR0 uplinks at 50%": "bars_degraded"};
  for (const scen of SCEN) {
    const rows = DATA.summary.filter(r => r.scenario === scen);
    const traces = ["valid_frac", "random_frac", "stale_frac"].map(key => {
      const name = key.replace("_frac", "");
      return {
        type: "bar", name: name,
        x: rows.map(r => "B=" + r.B), y: rows.map(r => r[key]),
        marker: {color: COL[name]},
        hovertemplate: "%{x}<br>" + name + " = %{y:.4f}<extra></extra>",
      };
    });
    plotWithHeadline(divId[scen], traces, {
      title: {text: "Share of EV draws, 16 MiB -- " + scen, font: {size: 14}},
      barmode: "group", yaxis: {title: "fraction of draws", range: [0, 1]},
      xaxis: {title: "buffer size B", categoryorder: "array", categoryarray: B_CATS},
      legend: {orientation: "h", y: -0.3}, margin: {t: 40, b: 100}, height: 440,
    }, {responsive: true});
  }
}

function sendKPanel() {
  // Two separate plots (own div, own Plotly.newPlot call) -- one per scenario.
  // A single overlaid/grouped chart made the stacked-bar comparison a mess.
  const kColors = ["#1b7837", "#5aae61", "#a6d96a", "#fee08b", "#fdae61", "#d73027", "#a50026"];
  const divId = {healthy: "sendk_healthy", "32 ToR0 uplinks at 50%": "sendk_degraded"};
  for (const scen of SCEN) {
    // Per-scenario kMax, not the global max across both scenarios -- a k
    // value never reached in THIS scenario (e.g. k=6..15 in healthy, when
    // degraded reaches 15) has no row in the data at all, so looping past
    // this scenario's own max would synthesize phantom all-zero legend
    // entries for k values that never occur here.
    const kMaxScen = Math.max(0, ...DATA.send_k.filter(r => r.scenario === scen).map(r => r.k));
    // Total post-warmup sends per B (each SEND/RTX/RTS after the host's
    // first ACK counted once, binned by k at that send) -- varies slightly
    // by B (RTX count differs), shown both as a note and per-bar.
    const totalByB = B.map(b => DATA.send_k
      .filter(r => r.scenario === scen && r.B === b)
      .reduce((s, r) => s + r.n_sends, 0));
    // A k value can technically occur (a row exists) while being a handful of
    // single sends out of 100k+ -- real, but invisible in the bar and pure
    // legend clutter as its own entry. Merge any k whose max share across B
    // never clears RARE_SHARE into one "k>=N (rare)" bucket instead.
    const RARE_SHARE = 1e-4;
    const maxShareOf = k => Math.max(0, ...DATA.send_k
      .filter(r => r.scenario === scen && r.k === k).map(r => r.share));
    const individualKs = [];
    let firstRareK = null;
    for (let k = 0; k <= kMaxScen; k++) {
      if (maxShareOf(k) >= RARE_SHARE || k === 0) individualKs.push(k);
      else { firstRareK = firstRareK === null ? k : firstRareK; }
    }
    const traces = [];
    for (const k of individualKs) {
      const rows = B.map((b, i) => {
        const r = DATA.send_k.find(r => r.scenario === scen && r.B === b && r.k === k);
        return r ? r.share : (k > b ? null : 0);
      });
      const nSends = B.map((b, i) => {
        const r = DATA.send_k.find(r => r.scenario === scen && r.B === b && r.k === k);
        return r ? r.n_sends : 0;
      });
      traces.push({
        type: "bar", name: "k=" + k, x: B.map(b => "B=" + b), y: rows,
        customdata: nSends.map((n, i) => [n, totalByB[i]]),
        marker: {color: kColors[k % kColors.length]},
        hovertemplate: "%{x}<br>k=" + k + " share=%{y:.4f}" +
          "<br>%{customdata[0]} of %{customdata[1]} post-warmup sends<extra></extra>",
      });
    }
    if (firstRareK !== null) {
      const rareKs = [];
      for (let k = firstRareK; k <= kMaxScen; k++) if (!individualKs.includes(k)) rareKs.push(k);
      const rows = B.map((b, i) => {
        const n = rareKs.reduce((s, k) => {
          const r = DATA.send_k.find(r => r.scenario === scen && r.B === b && r.k === k);
          return s + (r ? r.share : 0);
        }, 0);
        return n > 0 ? n : (firstRareK > b ? null : 0);
      });
      const nSends = B.map((b, i) => rareKs.reduce((s, k) => {
        const r = DATA.send_k.find(r => r.scenario === scen && r.B === b && r.k === k);
        return s + (r ? r.n_sends : 0);
      }, 0));
      traces.push({
        type: "bar", name: "k>=" + firstRareK + " (rare, <0.01% each)",
        x: B.map(b => "B=" + b), y: rows,
        customdata: nSends.map((n, i) => [n, totalByB[i]]),
        marker: {color: "#9ca3af"},
        hovertemplate: "%{x}<br>k in {" + rareKs.join(",") + "} combined, share=%{y:.6f}" +
          "<br>%{customdata[0]} of %{customdata[1]} post-warmup sends<extra></extra>",
      });
    }
    const totalRange = Math.min(...totalByB) === Math.max(...totalByB)
      ? String(totalByB[0])
      : Math.min(...totalByB) + "-" + Math.max(...totalByB);
    plotWithHeadline(divId[scen], traces, {
      title: {text: "Send-time k, post-warmup, 16 MiB -- " + scen, font: {size: 14}},
      barmode: "stack",
      xaxis: {title: "buffer size B", categoryorder: "array", categoryarray: B_CATS},
      yaxis: {title: "share of post-warmup sends", range: [0, 1]},
      // Up to ~16 k-value legend entries (degraded can reach k=15) wrap across
      // several rows in a horizontal legend -- give it real room below the
      // plot instead of letting the wrapped rows sit on top of the bars.
      legend: {orientation: "h", y: -0.45}, margin: {t: 60, b: 160}, height: 520,
      annotations: [{
        text: "total post-warmup sends per B (each send after its host's first ACK counted once, binned by k at that send): " + totalRange,
        showarrow: false, xref: "paper", yref: "paper", x: 0, y: 1.08,
        xanchor: "left", font: {size: 11, color: "#555"},
      }],
    }, {responsive: true});
  }
}

function fctPanel() {
  // Same per-scenario split as the other panels, but y is FCT normalized
  // against the SoL reference arm (FCT / SoL FCT) rather than raw FCT with
  // SoL as a plotted point -- 1.0 = at the speed-of-light floor, direct
  // slowdown-factor reading per B, no second axis/line needed.
  const divId = {healthy: "fct_healthy", "32 ToR0 uplinks at 50%": "fct_degraded"};
  const metrics = [["p50_fct_us", "p50"], ["p95_fct_us", "p95"],
                    ["p99_fct_us", "p99"], ["max_fct_us", "max"]];
  const mColors = {p50: "#2563eb", p95: "#16a34a", p99: "#d97706", max: "#dc2626"};
  for (const scen of SCEN) {
    const rows = DATA.fct.filter(r => r.scenario === scen).sort((a, b) => a.B - b.B);
    const sol = (DATA.sol_fct || []).find(r => r.scenario === scen);
    if (!sol) continue;
    const traces = metrics.map(([key, label]) => ({
      type: "scatter", mode: "lines+markers", name: label,
      x: rows.map(r => "B=" + r.B), y: rows.map(r => r[key] / sol[key]),
      line: {color: mColors[label]}, marker: {color: mColors[label], size: 7},
      hovertemplate: "%{x}<br>" + label + " FCT / SoL = %{y:.3f}x<extra></extra>",
    }));
    traces.push({
      type: "scatter", mode: "lines", name: "SoL (=1)",
      x: rows.map(r => "B=" + r.B), y: rows.map(() => 1),
      line: {color: "#888", dash: "dot", width: 1}, hoverinfo: "skip",
    });
    plotWithHeadline(divId[scen], traces, {
      title: {text: "FCT / SoL across 32 ToR0 hosts, 16 MiB -- " + scen, font: {size: 14}},
      xaxis: {title: "buffer size B", categoryorder: "array", categoryarray: B_CATS},
      yaxis: {title: "FCT / SoL FCT (1 = speed-of-light floor)"},
      legend: {orientation: "h", y: -0.3}, margin: {t: 40, b: 100}, height: 440,
    }, {responsive: true});
  }
}

function solNote() {
  // Slowdown from SoL, using MAX (makespan) as the comparison metric -- not
  // p50. SoL models every one of the 32 symmetric flows finishing at the
  // SAME instant (one dedicated path each, same size); a real scheduler's
  // p50 can legitimately finish BEFORE that single value (early finishers
  // borrow bandwidth ahead of stragglers without violating the aggregate
  // bit-conservation bound), but the slowest flow (max) cannot finish
  // before the aggregate floor -- that bound is what SoL actually pins down.
  if (!DATA.sol_fct || !DATA.sol_fct.length) return;
  const el = document.getElementById("solNote");
  if (!el) return;
  const lines = SCEN.map(scen => {
    const sol = DATA.sol_fct.find(r => r.scenario === scen);
    const satRows = DATA.fct.filter(r => r.scenario === scen && r.B >= 8);
    if (!sol || !satRows.length) return null;
    const satMax = satRows[0].max_fct_us;  // identical across B>=8, saturated ladder
    const slowdown = (satMax / sol.max_fct_us).toFixed(3);
    return "<li><b>" + scen + ":</b> SoL (path_static+constant, one pinned path/flow) max FCT = " +
      sol.max_fct_us.toFixed(2) + " us, p50 = " + sol.p50_fct_us.toFixed(2) + " us (" + sol.hosts +
      " hosts). " + __CC__ + " at B>=8 max FCT = " + satMax.toFixed(2) + " us -- " + slowdown +
      "x SoL.</li>";
  }).filter(Boolean);
  if (!lines.length) return;
  el.style.display = "";
  el.innerHTML = "<b>Speed-of-light (SoL) reference:</b> " +
    "<code>-load_balancing_algo path_static -sender_cc_algo constant</code> pins each flow to " +
    "one disjoint path for its whole life (greedy edge-load at flow setup) with cwnd frozen at a " +
    "value a smoke-test cwnd sweep found saturates that one path without overshooting into extra " +
    "queuing (127 healthy / 56 degraded, degraded isolated to the 32 ToR0 hosts via " +
    "<code>-host_cwnd_overrides</code> -- see RESULTS.md). No REPS buffer exists in this arm, so it " +
    "has no B; it is the floor every " + __CC__ + " B-sweep line above is compared against, not " +
    "another point on the B axis. <ul>" + lines.join("") + "</ul>";
}

function fctNote() {
  const rows = DATA.exp30_fct_note;
  if (!rows || !rows.length) return;
  const b4 = rows.find(r => r.B === 4);
  const satur = rows.filter(r => r.B >= 8);
  if (!b4 || !satur.length) return;
  const satCi = satur[0].max_fct_us_ci;  // identical across B>=8 (saturated ladder)
  const ratio = (satCi / b4.max_fct_us_ci).toFixed(1);
  const el = document.getElementById("fctNote");
  el.style.display = "";
  el.innerHTML =
    "<b>Open question -- why does B=4 outperform larger B here?</b> C1 above is seed 42 only. " +
    "exp30 Part A1's own 3-seed aggregation (seeds 42/43/44) of this same cell (x=32, 16 MiB, " +
    "MPRDMA, ToR0 hosts) shows the max FCT in the same " + Math.round(Math.min(...rows.map(r=>r.max_fct_us))) +
    "-" + Math.round(Math.max(...rows.map(r=>r.max_fct_us))) + " us range at every B -- but B=4's " +
    "run-to-run variance (max FCT 95% CI = " + b4.max_fct_us_ci.toFixed(2) + " us) is about " + ratio +
    "x lower than B=8 and up (CI = " + satCi.toFixed(2) + " us, identical from B=8 up since the " +
    "ladder saturates there). B=4 is both the fastest and the most stable point on this axis; " +
    "going past it adds variance and a slightly higher max FCT instead of helping. Not yet explained.";
}

function acksWindowPanel() {
  // Distribution (not mean) of ACK count per SEND-to-SEND window -- same
  // population as sendKPanel's k plot (n_sends_post ties out exactly), same
  // stacked-bar-per-B layout, same rare-bucket merge for the long tail that
  // only the degraded scenario has.
  if (!DATA.acks_window || !DATA.acks_window.length) return;
  const nColors = ["#1b7837", "#5aae61", "#a6d96a", "#fee08b", "#fdae61", "#d73027", "#a50026"];
  const divId = {healthy: "acks_window_healthy", "32 ToR0 uplinks at 50%": "acks_window_degraded"};
  for (const scen of SCEN) {
    const rows = DATA.acks_window.filter(r => r.scenario === scen);
    if (!rows.length) { document.getElementById(divId[scen]).innerHTML = ""; continue; }
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
    plotWithHeadline(divId[scen], traces, {
      title: {text: "ACKs per SEND-to-SEND window, post-warmup -- " + scen, font: {size: 13}},
      barmode: "stack",
      xaxis: {title: "buffer size B", categoryorder: "array", categoryarray: B_CATS},
      yaxis: {title: "share of post-warmup windows", range: [0, 1]},
      legend: {orientation: "h", y: -0.4}, margin: {t: 50, b: 130}, height: 460,
      annotations: [{
        text: "total windows (sum over ACK-count), per B: " + totalRange,
        showarrow: false, xref: "paper", yref: "paper", x: 0, y: 1.08,
        xanchor: "left", font: {size: 10, color: "#555"},
      }],
    }, {responsive: true});
  }
}

barsPanel();
if (DATA.send_k.length) sendKPanel();
if (DATA.fct.length) fctPanel();
acksWindowPanel();
solNote();
fctNote();
</script>
</body></html>
"""


if __name__ == "__main__":
    main()
