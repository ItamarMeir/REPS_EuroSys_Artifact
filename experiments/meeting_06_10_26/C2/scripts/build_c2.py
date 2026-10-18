#!/usr/bin/env python3
"""C2 results page, 16 MiB, NSCC, trim ON. Reads C2's own runs/ (not exp30's --
every C2 cell is a fresh run produced by run_c2.py).

Writes:
  ../data/c2_split.csv, ../data/c2_split_hosts.csv, ../data/c2_fct.csv
  ../plots/interactive.html

Split: fractions over all EV draws (new packets + retransmissions) of the 32 ToR0
hosts. random = ev_random + ev_explore. valid + random + stale = 1. Unlike C1
(trim on, no RTO -> stale always 0), C2 enters Freezing Mode, so stale is expected
to be nonzero for F=16.
"""
import csv
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
C2 = HERE.parent
RUNS = C2 / "runs"
DATA = C2 / "data"
PLOTS = C2 / "plots"

SIZE_NAME = "16 MiB"
SCEN = {0: "healthy", 16: "16 ToR0 uplinks, transient kill (10-110us)"}
BS = [1, 2, 4, 8, 16, 32, 64, 128, 256]
TOR0_HOSTS = 32

FIN = re.compile(
    r"uecSrc (\d+) finished at ([\d.]+).*?total packets (\d+).*?"
    r"ev_explore (\d+) ev_random (\d+) ev_valid (\d+) ev_stale (\d+)")
FRZ = re.compile(r"uecSrc (\d+) finished at.*?freeze_entries (\d+)")
# "Keep diagnostics like exp30" -- the extra per-host counters exp30's own
# aggregate30.py tracks (DIAG_COLS), parsed separately from FIN so FIN's tuple
# shape (and every caller that unpacks it) stays unchanged.
DIAG = re.compile(
    r"uecSrc (\d+) finished at.*?total packets \d+ RTS (\d+).*?"
    r"ecn_acks (\d+) rtos (\d+) freeze_entries \d+ freeze_us (\d+).*?fast_loss (\d+)")


def arm_name(b):
    return f"reps_b{b}_nscc"


# ===== ADDED (sol-avoid-timed-failure) =====
# Oracle floor: avoids the 16 dead uplinks (data + ACK) instead of running
# NSCC+Freezing. F=16 is C2's own run_c2.py::run_sol_cell() output; F=0 is
# byte-identical to C1's x=0 `sol` run (confirmed in PLAN.md), read directly
# from there -- no rerun. Floor = ToR0-SENDER (src 0-31) FCT only, same scope
# as the rest of this page's per-host metrics.
C1_HEALTHY_SOL_STDOUT = Path(
    "/workspace/experiments/exp30_packet_trimming_en/runs/a1/16777216/"
    "x0_ef200/seed42/sol/stdout.txt")


def sol_tor0_sender_fct(path):
    if not path.exists():
        return None
    text = path.read_text(errors="replace")
    vals = sorted(float(fct) for src, fct in
                   re.findall(r"uecSrc (\d+) finished at ([\d.]+)", text)
                   if int(src) < TOR0_HOSTS)
    if not vals:
        return None
    return dict(p50=percentile(vals, 50), max=vals[-1], n=len(vals))


def sol_floors():
    f16 = sol_tor0_sender_fct(RUNS / "x16_ef200" / "seed42" / "sol" / "stdout.txt")
    f0 = sol_tor0_sender_fct(C1_HEALTHY_SOL_STDOUT)
    return dict(F0=f0, F16=f16)
# ===== END ADDED (sol-avoid-timed-failure) =====


def read_cell(f, b):
    path = RUNS / f"x{f}_ef200" / "seed42" / arm_name(b) / "stdout.txt"
    if not path.exists():
        return None, None
    text = path.read_text(errors="replace")
    flows = []
    for m in FIN.findall(text):
        src, fct, pk, ex, rnd, val, st = m
        flows.append((int(src), float(fct), int(pk), int(ex), int(rnd), int(val), int(st)))
    freeze = {int(s): int(fz) for s, fz in FRZ.findall(text)}
    diag = {int(m[0]): dict(rts=int(m[1]), ecn_acks=int(m[2]), rtos=int(m[3]),
                              freeze_us=int(m[4]), fast_loss=int(m[5]))
            for m in DIAG.findall(text)}
    return flows, freeze, diag


def host_rows(flows, freeze, diag):
    out = []
    for src, fct, pk, ex, rnd, val, st in flows:
        if src >= TOR0_HOSTS:
            continue
        rnd_all = ex + rnd
        d = diag.get(src, dict(rts=0, ecn_acks=0, rtos=0, freeze_us=0, fast_loss=0))
        out.append(dict(packets=pk, draws=rnd_all + val + st,
                        valid=val, random=rnd_all, stale=st, fct_us=fct,
                        freeze_entries=freeze.get(src, 0), **d))
    return out


def frac(rows, key):
    tot = sum(r["draws"] for r in rows)
    return sum(r[key] for r in rows) / tot if tot else float("nan")


def percentile(sorted_vals, p):
    if not sorted_vals:
        return float("nan")
    k = (len(sorted_vals) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    if lo == hi:
        return sorted_vals[lo]
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def build():
    summary, per_host, fct_rows, missing, censored = [], [], [], [], []
    for f, scname in SCEN.items():
        for b in BS:
            flows, freeze, diag = read_cell(f, b)
            if not flows:
                missing.append((f, b))
                continue
            rows = host_rows(flows, freeze, diag)
            if len(rows) != TOR0_HOSTS:
                # A host whose flow never finished (censored by -end) drops out
                # of FIN's matches entirely -- silently excluding it from FCT
                # percentiles would bias them low (missing exactly the worst
                # cases). Flag it instead, same spirit as aggregate30's own
                # "did not finish by END_US" handling.
                censored.append((f, b, len(rows)))
            pk = sum(r["packets"] for r in rows)
            dr = sum(r["draws"] for r in rows)
            n_freezing_hosts = sum(1 for r in rows if r["freeze_entries"] > 0)
            summary.append(dict(
                size=SIZE_NAME, scenario=scname, F=f, B=b,
                hosts=len(rows), packets=pk, draws=dr, rtx=dr - pk,
                valid_frac=frac(rows, "valid"), random_frac=frac(rows, "random"),
                stale_frac=frac(rows, "stale"),
                freeze_entries_total=sum(r["freeze_entries"] for r in rows),
                n_freezing_hosts=n_freezing_hosts,
                rts_total=sum(r["rts"] for r in rows),
                ecn_acks_total=sum(r["ecn_acks"] for r in rows),
                rtos_total=sum(r["rtos"] for r in rows),
                freeze_us_total=sum(r["freeze_us"] for r in rows),
                fast_loss_total=sum(r["fast_loss"] for r in rows)))
            for i, r in enumerate(rows):
                d = r["draws"] or 1
                per_host.append(dict(
                    size=SIZE_NAME, scenario=scname, B=b, host=i,
                    valid_frac=r["valid"] / d, random_frac=r["random"] / d,
                    stale_frac=r["stale"] / d, freeze_entries=r["freeze_entries"]))
            fct_vals = sorted(r["fct_us"] for r in rows)
            fct_rows.append(dict(
                size=SIZE_NAME, scenario=scname, B=b, hosts=len(fct_vals),
                p50_fct_us=percentile(fct_vals, 50), p95_fct_us=percentile(fct_vals, 95),
                p99_fct_us=percentile(fct_vals, 99),
                max_fct_us=fct_vals[-1] if fct_vals else float("nan")))
    if missing:
        print("MISSING split cells:", missing)
    if censored:
        print(f"CENSORED (host count != {TOR0_HOSTS}, some flow(s) did not finish "
              f"by -end): {censored}")
    for s in summary:
        if s["draws"]:
            assert abs(s["valid_frac"] + s["random_frac"] + s["stale_frac"] - 1) < 1e-9, s
    return summary, per_host, fct_rows


def write_csv(path, rows):
    if not rows:
        return
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def load_csv_if_present(path, keys_types):
    if not path.exists():
        return []
    out = []
    for r in csv.DictReader(open(path)):
        out.append({k: t(r[k]) for k, t in keys_types.items()})
    return out


def _opt_float(s):
    return float(s) if s not in ("", None) else None


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    PLOTS.mkdir(parents=True, exist_ok=True)
    # Still computed for archival/debugging (cheap) -- no longer rendered on the
    # page, which now answers buffer-CONTENT questions (failed_ev_buffer.py's
    # outputs below), not per-draw valid/random/stale fractions.
    summary, per_host, fct_rows = build()
    write_csv(DATA / "c2_split.csv", summary)
    write_csv(DATA / "c2_split_hosts.csv", per_host)
    write_csv(DATA / "c2_fct.csv", fct_rows)

    failed_epochs = load_csv_if_present(DATA / "c2_failed_ev_epochs.csv", dict(
        scenario=str, B=int, src=int, freeze_start_ns=float, kill_to_freeze_lag_ns=float,
        failed_n_at_freeze=int, buf_size_at_freeze=int, outcome=str,
        time_to_zero_ns=_opt_float, events_to_zero=lambda s: int(s) if s not in ("", None) else None))
    failed_series = load_csv_if_present(DATA / "c2_failed_ev_timeseries.csv", dict(
        scenario=str, B=int, bucket_start_ns=int, mean_failed_frac=float, n=int))
    good_spread = load_csv_if_present(DATA / "c2_good_ev_spread.csv", dict(
        scenario=str, B=int, bucket_start_ns=int, lambda_imbalance=_opt_float,
        ecn_rate_good=_opt_float, trim_rate_good=_opt_float,
        n_sends_good=int, n_ack_good=int, n_nack_good=int))
    good_occ = load_csv_if_present(DATA / "c2_good_ev_buffer_occupancy.csv", dict(
        scenario=str, B=int, bucket_start_ns=int, mean_n_distinct_good=float,
        mean_n_good_slots=float, n=int))

    # ===== ADDED (sol-avoid-timed-failure) =====
    floors = sol_floors()
    write_csv(DATA / "c2_fct_sol.csv", [
        dict(F=f, **v) for f, v in floors.items() if v is not None])
    print("SoL floors (ToR0-sender FCT, us):", floors)
    # ===== END ADDED (sol-avoid-timed-failure) =====

    # good_occ is still computed/written to CSV above (archival) but no longer
    # rendered. fct_rows is now rendered again (re-added for the SoL comparison).
    payload = json.dumps(dict(failed_epochs=failed_epochs, failed_series=failed_series,
                               good_spread=good_spread, fct_rows=fct_rows, sol_floors=floors))
    html = TEMPLATE.replace("__PAYLOAD__", payload)
    (PLOTS / "interactive.html").write_text(html, encoding="utf-8")
    print(f"fct rows: {len(fct_rows)}  "
          f"failed epochs: {len(failed_epochs)}  failed series rows: {len(failed_series)}  "
          f"good spread rows: {len(good_spread)}  good occ rows: {len(good_occ)}")
    print("wrote", PLOTS / "interactive.html")


TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8">
<title>C2 - Freezing-Mode buffer content vs B</title>
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
<h1>C2: Freezing-Mode buffer content -- 16 MiB, NSCC, trim ON</h1>
<div class="note">exp30_packet_trimming_en base, trim ON, NSCC, freezing LB, tornado 16 MiB, seed 42,
32 ToR0 hosts. 16 of ToR0's 32 uplinks (EVs 0-15) killed transiently at t=10-110us; EVs 16-31 survive.
Healthy (F=0) never freezes, omitted. Phases: warmup (before first ACK) -&gt; killed, not yet frozen
(t in [10us, FREEZE)) -&gt; frozen, kill active (t in [FREEZE, 110us)) -&gt; frozen, post-recovery
(t in [110us, UNFREEZE), bounded by the 200us exit_freeze timer from FREEZE time, not recovery) -&gt;
UNFREEZE (buffer wiped) -&gt; post-UNFREEZE explore burst. Metric 1 (failed-EV content) counts buffer
slots that have ever been WRITTEN (index &lt; buf_size) whose cached EV is a dead path (0-15),
regardless of whether that slot is currently "valid"/fresh -- remove_frozen() draws stale slots
exactly like valid ones, so a stale dead EV is still a live risk of being sent. Its clock starts at
KILL ONSET (t=10us), not at each host's own FREEZE (FREEZE lags the kill by ~tens of us -- healthy
ACKs already clean the buffer before freezing even starts), and stops at RECOVERY (t=110us): a dead
EV reappearing after recovery is healing, not leftover dirt. Metric 2 (good-EV spread) is send-side
load imbalance across the 16 surviving paths while frozen (lambda = max/mean-1 of frozen-mode send
counts per EV, paper's own Appendix B definition; lambda=0 is perfectly even, larger means more
sends concentrated on fewer good paths). All times bucketed at 5us, x-axis is time SINCE KILL
ONSET (kill itself = x=0; recovery = x=100000ns). The median host doesn't enter Freezing Mode until
~39.7us after the kill (RTO-driven, same across every B) -- marked with a dashed purple line on every
time-series panel -- so Metric 2 (which is defined only on frozen-mode draws) has no data before that,
by construction, not as a gap or bug.</div>
<div class="note">Hover a plot and click "copy" (top-right) to copy that plot's headline to the clipboard.</div>
<div class="grid">
  <div class="panel wide"><button class="copy-btn" onclick="copyTitle('failed_curve', this)">copy</button><div id="failed_curve"></div></div>
  <div class="panel"><button class="copy-btn" onclick="copyTitle('failed_epochs_time', this)">copy</button><div id="failed_epochs_time"></div></div>
  <div class="panel"><button class="copy-btn" onclick="copyTitle('failed_epochs_outcome', this)">copy</button><div id="failed_epochs_outcome"></div></div>
  <div class="panel wide"><button class="copy-btn" onclick="copyTitle('spread_lambda', this)">copy</button><div id="spread_lambda"></div></div>
  <div class="panel wide"><button class="copy-btn" onclick="copyTitle('fct_vs_sol', this)">copy</button><div id="fct_vs_sol"></div></div>
</div>
<script>
const DATA = __PAYLOAD__;
const B = [1, 2, 4, 8, 16, 32, 64, 128, 256];
const KILL_START_NS = 10000, KILL_END_NS = 110000;
const BCOLORS = ["#8c510a","#bf812d","#dfc27d","#80cdc1","#35978f","#01665e",
                  "#762a83","#9970ab","#d6604d"];
const colorOf = b => BCOLORS[B.indexOf(b) % BCOLORS.length];
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

// All plots here use "time since kill onset" as x, i.e. kill itself sits at x=0
// (bucket_start_ns and failed-series/spread-series are already offset this way).
// FREEZE_LAG_NS is the median kill-to-FREEZE lag (identical across every B --
// driven by RTO timing, not buffer size): the earliest a host can have ANY
// frozen-mode draw, so lambda/occupancy data has nothing to show before it.
const FREEZE_LAG_NS = 39717;
// DATA.fct carries both healthy (F=0, never freezes) and degraded (F=16) rows --
// same pattern as everything else on this page, only degraded is shown.
const DEGRADED_SCEN = "16 ToR0 uplinks, transient kill (10-110us)";

function phaseShapes(yref) {
  return [
    {type: "line", x0: 0, x1: 0, yref: yref, y0: 0, y1: 1,
     xref: "x", line: {color: "#dc2626", dash: "dot", width: 1}},
    {type: "line", x0: FREEZE_LAG_NS, x1: FREEZE_LAG_NS, yref: yref, y0: 0, y1: 1,
     xref: "x", line: {color: "#7c3aed", dash: "dot", width: 1}},
    {type: "line", x0: KILL_END_NS - KILL_START_NS, x1: KILL_END_NS - KILL_START_NS,
     yref: yref, y0: 0, y1: 1, xref: "x", line: {color: "#16a34a", dash: "dot", width: 1}},
  ];
}
function phaseAnnotations(y) {
  return [
    {x: 0, y: y, xref: "x", yref: "paper", text: "kill", showarrow: false,
     font: {size: 10, color: "#dc2626"}},
    {x: FREEZE_LAG_NS, y: y, xref: "x", yref: "paper", text: "~median FREEZE", showarrow: false,
     font: {size: 10, color: "#7c3aed"}},
    {x: KILL_END_NS - KILL_START_NS, y: y, xref: "x", yref: "paper", text: "recover", showarrow: false,
     font: {size: 10, color: "#16a34a"}},
  ];
}

function failedCurvePanel() {
  if (!DATA.failed_series.length) {
    document.getElementById("failed_curve").innerHTML =
      "<p style='color:#888;font-size:13px;'>No failed-EV time series (c2_failed_ev_timeseries.csv not built).</p>";
    return;
  }
  const traces = B.map(b => {
    const rows = DATA.failed_series.filter(r => r.B === b).sort((a,c)=>a.bucket_start_ns-c.bucket_start_ns);
    return {
      type: "scatter", mode: "lines+markers", name: "B=" + b,
      x: rows.map(r => r.bucket_start_ns), y: rows.map(r => r.mean_failed_frac),
      line: {color: colorOf(b)}, marker: {size: 4},
      hovertemplate: "t=%{x} ns since kill<br>B=" + b + "<br>mean failed-EV fraction=%{y:.4f}<extra></extra>",
    };
  });
  plotWithHeadline("failed_curve", traces, {
    title: {text: "Metric 1a: mean fraction of buffer slots holding a dead EV (0-15), vs time since kill (t=10us)", font: {size: 14}},
    xaxis: {title: "time since kill onset (ns)"},
    yaxis: {title: "mean failed-EV fraction of buffer", range: [0, 1]},
    shapes: phaseShapes("paper"), annotations: phaseAnnotations(1.05),
    legend: {orientation: "h", y: -0.25}, margin: {t: 40, b: 90}, height: 420,
  }, {responsive: true});
}

function percentile(sorted, p) {
  if (!sorted.length) return null;
  const k = (sorted.length - 1) * p / 100;
  const lo = Math.floor(k), hi = Math.min(lo + 1, sorted.length - 1);
  return lo === hi ? sorted[lo] : sorted[lo] + (sorted[hi] - sorted[lo]) * (k - lo);
}

// Metric 1b was a single box+all-288-points panel (9 B values x up to 3 outcomes,
// jittered) -- dense and hard to read. Split into what it was actually carrying:
// (a) the time-to-zero DISTRIBUTION per B (median + IQR, one point per B instead
// of up to 32 jittered points) and (b) the outcome BREAKDOWN per B (how many of
// the 32 hosts cleared vs didn't, as a plain stacked count) -- two simple shapes
// instead of one overloaded one.
function failedEpochsTimePanel() {
  if (!DATA.failed_epochs.length) {
    document.getElementById("failed_epochs_time").innerHTML =
      "<p style='color:#888;font-size:13px;'>No failed-EV epoch data (c2_failed_ev_epochs.csv not built).</p>";
    return;
  }
  const byB = B.map(b => {
    const vals = DATA.failed_epochs
      .filter(r => r.B === b && r.time_to_zero_ns !== null && r.time_to_zero_ns !== "")
      .map(r => r.time_to_zero_ns).sort((a,c)=>a-c);
    return {b, n: vals.length, p25: percentile(vals, 25), p50: percentile(vals, 50), p75: percentile(vals, 75)};
  }).filter(d => d.n > 0);
  const trace = {
    type: "scatter", mode: "lines+markers", name: "median (IQR)",
    x: byB.map(d => "B=" + d.b), y: byB.map(d => d.p50),
    error_y: {type: "data", symmetric: false,
      array: byB.map(d => d.p75 - d.p50), arrayminus: byB.map(d => d.p50 - d.p25)},
    marker: {size: 7, color: "#2563eb"}, line: {color: "#2563eb"},
    customdata: byB.map(d => d.n),
    hovertemplate: "%{x}<br>median time to zero=%{y:.0f} ns<br>n=%{customdata} cleared hosts<extra></extra>",
  };
  plotWithHeadline("failed_epochs_time", [trace], {
    title: {text: "Metric 1b: time-to-zero failed EVs vs B (median, IQR error bars; only hosts that cleared before recovery)", font: {size: 13}},
    xaxis: {title: "buffer size B", categoryorder: "array", categoryarray: B.map(b=>"B="+b)},
    yaxis: {title: "time to zero failed EVs since kill (ns)", type: "log"},
    margin: {t: 50, b: 60}, height: 420,
  }, {responsive: true});
}

function failedEpochsOutcomePanel() {
  if (!DATA.failed_epochs.length) {
    document.getElementById("failed_epochs_outcome").innerHTML = "";
    return;
  }
  const outcomes = [...new Set(DATA.failed_epochs.map(r=>r.outcome))];
  const oColors = {cleared_before_recovery: "#22a884", not_cleared_before_recovery: "#d97706",
                     ongoing_at_trace_end: "#94a3b8"};
  const traces = outcomes.map(o => ({
    type: "bar", name: o, x: B.map(b => "B=" + b),
    y: B.map(b => DATA.failed_epochs.filter(r => r.B === b && r.outcome === o).length),
    marker: {color: oColors[o] || "#888"},
    hovertemplate: "%{x}<br>" + o + ": %{y} of 32 hosts<extra></extra>",
  }));
  plotWithHeadline("failed_epochs_outcome", traces, {
    title: {text: "Metric 1b: epoch outcome counts vs B (out of 32 ToR0 hosts)", font: {size: 13}},
    barmode: "stack", xaxis: {title: "buffer size B", categoryorder: "array", categoryarray: B.map(b=>"B="+b)},
    yaxis: {title: "hosts (of 32)"},
    legend: {orientation: "h", y: -0.3}, margin: {t: 50, b: 90}, height: 420,
  }, {responsive: true});
}

function spreadLambdaPanel() {
  if (!DATA.good_spread.length) {
    document.getElementById("spread_lambda").innerHTML =
      "<p style='color:#888;font-size:13px;'>No good-EV spread data (c2_good_ev_spread.csv not built).</p>";
    return;
  }
  const traces = B.map(b => {
    const rows = DATA.good_spread.filter(r => r.B === b && r.lambda_imbalance !== null && r.lambda_imbalance !== "")
      .sort((a,c)=>a.bucket_start_ns-c.bucket_start_ns);
    return {
      type: "scatter", mode: "lines+markers", name: "B=" + b,
      x: rows.map(r => r.bucket_start_ns), y: rows.map(r => r.lambda_imbalance),
      line: {color: colorOf(b)}, marker: {size: 4},
      customdata: rows.map(r => r.n_sends_good),
      hovertemplate: "t=%{x} ns since kill<br>B=" + b + "<br>lambda=%{y:.3f}" +
        "<br>%{customdata} frozen-mode good-EV sends in bucket<extra></extra>",
    };
  });
  plotWithHeadline("spread_lambda", traces, {
    title: {text: "Metric 2a: good-EV (16-31) load imbalance while frozen, lambda = max/mean - 1", font: {size: 14}},
    xaxis: {title: "time since kill onset (ns)"},
    yaxis: {title: "lambda (0 = perfectly even across 16 good EVs)"},
    shapes: phaseShapes("paper"), annotations: phaseAnnotations(1.05),
    legend: {orientation: "h", y: -0.25}, margin: {t: 40, b: 90}, height: 420,
  }, {responsive: true});
}

// ===== ADDED (sol-avoid-timed-failure) =====
// ToR0-SENDER (src 0-31) max/p50 FCT vs B for the real F=16 Freezing+NSCC
// arm, against the SoL oracle floor (avoids the 16 dead uplinks/data+ACK
// instead of running NSCC+Freezing) for both F=0 (never fails) and F=16.
// Floors are horizontal dashed lines, not points, since the SoL arm has no
// buffer-size B knob (path_static, not freezing/REPS).
function fctVsSolPanel() {
  if (!DATA.fct_rows.length) {
    document.getElementById("fct_vs_sol").innerHTML =
      "<p style='color:#888;font-size:13px;'>No FCT data (c2_fct.csv not built).</p>";
    return;
  }
  const degRows = DATA.fct_rows.filter(r => r.scenario === DEGRADED_SCEN)
    .sort((a, c) => B.indexOf(a.B) - B.indexOf(c.B));
  const traces = [
    {type: "scatter", mode: "lines+markers", name: "F=16 real (NSCC+Freezing) max FCT",
     x: degRows.map(r => "B=" + r.B), y: degRows.map(r => r.max_fct_us),
     marker: {size: 7, color: "#dc2626"}, line: {color: "#dc2626"}},
    {type: "scatter", mode: "lines+markers", name: "F=16 real (NSCC+Freezing) p50 FCT",
     x: degRows.map(r => "B=" + r.B), y: degRows.map(r => r.p50_fct_us),
     marker: {size: 7, color: "#f59e0b"}, line: {color: "#f59e0b", dash: "dot"}},
  ];
  const shapes = [], annotations = [];
  const floor = (key, label, color) => {
    const f = DATA.sol_floors && DATA.sol_floors[key];
    if (!f) return;
    shapes.push({type: "line", xref: "paper", x0: 0, x1: 1, yref: "y",
      y0: f.max, y1: f.max, line: {color: color, dash: "dash", width: 1.5}});
    annotations.push({xref: "paper", x: 1.0, y: f.max, xanchor: "left", yanchor: "middle",
      text: label + " SoL max=" + f.max.toFixed(1) + "us", showarrow: false,
      font: {size: 10, color: color}});
  };
  floor("F0", "F=0", "#16a34a");
  floor("F16", "F=16", "#2563eb");
  plotWithHeadline("fct_vs_sol", traces, {
    title: {text: "ToR0-sender FCT vs B: real NSCC+Freezing arm vs SoL oracle floor (dashed)", font: {size: 14}},
    xaxis: {title: "buffer size B", categoryorder: "array", categoryarray: B.map(b => "B=" + b)},
    yaxis: {title: "FCT (us)"},
    shapes: shapes, annotations: annotations,
    legend: {orientation: "h", y: -0.25}, margin: {t: 40, b: 90, r: 140}, height: 420,
  }, {responsive: true});
}
// ===== END ADDED (sol-avoid-timed-failure) =====

failedCurvePanel();
failedEpochsTimePanel();
failedEpochsOutcomePanel();
spreadLambdaPanel();
fctVsSolPanel();
</script>
</body></html>
"""


if __name__ == "__main__":
    main()
