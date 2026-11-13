#!/usr/bin/env python3
"""knee/plots/nsweep.html: dial E with ONE parameter (delay of every fabric link) sweeping N = packets in flight,
max FCT vs B with one line per N, in the plot_common style (skill interactive-plotter).
Input (copied out of the container, see knee/README.md "Dial E, N sweep"):
  data/n_results.jsonl  (run_knee results, gate columns, trims)  data/n_permessage.csv (e_permessage.py: per message max FCT of hosts 0-7)
  data/n_mech.csv       (n_mech.py: measured N, fresh EVs carried into messages 2-4, random draws in the first 300 sends)
experiments/**/*.html is gitignored.
    python3 build_page_nsweep.py"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
KNEE = HERE.parent
sys.path.insert(0, str(HERE.parents[2] / "tools"))
import nsweep_extra as X  # noqa: E402
from plot_common import (aside, build_page, callout, chip, controls, end, h2,  # noqa: E402
                         note, plot, question, table, tile)

D = KNEE / "data"
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306}   # two-sided 95% t by df
TOLS = (0.002, 0.01, 0.02, 0.05)

RES = pd.DataFrame(map(json.loads, ((D / "n_results.jsonl").read_text().splitlines() + (D / "n_results_smallB.jsonl").read_text().splitlines()))).drop_duplicates(["cfg", "B", "seed"])   # + the REPS cells at B 2-16 added for the god-mode pairing
RES["lat"] = RES.cfg.str.extract(r"lat(\d+)")[0].astype(int)
PM = pd.concat([pd.read_csv(D / "n_permessage.csv"), pd.read_csv(D / "n_permessage_smallB.csv")], ignore_index=True)
MECH = pd.read_csv(D / "n_mech.csv")
MH = pd.read_csv(D / "n_mech_maxhost.csv")           # random share of the host that had the max FCT in each message (rerun that traces hosts 0-7 of every message)
bad = set(map(tuple, RES[(RES.rtos > 0) | (RES.freeze_entries > 0)][["cfg", "B", "seed"]].values))
LATS = sorted(RES.lat.unique())
CFG = {L: f"h128_p8_msgN_lat{L}" for L in LATS}
RTT = {L: 0.337 + 8 * L / 1000 for L in LATS}          # unloaded RTT in us as printed by the simulator (network_max_unloaded_rtt)


SOL, UM, WM = X.load(D)
SOLV = X.sol_by_lat(SOL)


def ci(v):
    n = len(v)
    return float(T975.get(n - 1, 1.96) * np.std(v, ddof=1) / np.sqrt(n)) if n > 1 else 0.0


def per_seed(cfg, first):
    """one number per (B, seed): max FCT of the 8 degraded sources, message 1 alone or the mean of messages 2-4"""
    g = PM[(PM.cfg == cfg) & ((PM.msg == 0) if first else (PM.msg > 0))]
    g = g[[(cfg, b, s) not in bad for b, s in zip(g.B, g.seed)]]
    return g.groupby(["B", "seed"])["max"].mean().reset_index()


def paired(x):
    """per B: mean and SE of the paired difference to the largest B (same seed), and the knee for each tolerance"""
    Bs = sorted(x.B.unique()); top = Bs[-1]
    ref = x[x.B == top].set_index("seed")["max"]
    out = {}
    for B in Bs:
        d = (x[x.B == B].set_index("seed")["max"] - ref).dropna()
        out[B] = (d.mean(), d.std(ddof=1) / np.sqrt(len(d)) if len(d) > 1 else 0.0, ci(d.to_numpy()), len(d))
    knees = {}
    for tol in TOLS:
        knees[tol] = next(B for B in Bs if all(out[b][0] <= max(tol * ref.mean(), 1.96 * out[b][1]) for b in Bs if b >= B))
    return Bs, top, ref.mean(), out, knees


series_abs, series_rat, series_rnd, series_trm, tab = [], [], [], [], []
refs = []
kn = {str(t * 100).rstrip("0").rstrip("."): {"labels": [], "N": [], "fill": [], "later": [], "first": [], "bmin": [], "dip": []} for t in TOLS}
for i, L in enumerate(LATS):
    cfg = CFG[L]
    m = MECH[(MECH.cfg == cfg)]
    m = m[[(cfg, b, s) not in bad for b, s in zip(m.B, m.seed)]]
    Bs_all = sorted(m.B)
    N = int(round(m.peak_inflight.median()))
    xl = per_seed(cfg, False)
    Bs, top, refv, out, kneesL = paired(xl)
    refs.append(round(float(refv), 3))
    fill = float(m[m.B == top][["fresh_m2", "fresh_m3", "fresh_m4"]].to_numpy().mean())
    key = f"n{i}"
    label = f"N = {N} (links {L / 1000:g} us)"
    rows_abs = []
    for B, g in xl.groupby("B"):
        v = g["max"].to_numpy()
        rows_abs.append({"x": f"B={int(B)}", "y": round(float(v.mean()), 2), "ci": round(ci(v), 2), "n": len(v)})
    rows_rat = [{"x": r["x"], "y": round(r["y"] / SOLV[L], 4), "ci": round(r["ci"] / SOLV[L], 4), "n": r["n"]} for r in rows_abs]     # max FCT / speed of light (1 = speed of light)
    rows_rnd = []
    mh = MH[MH.cfg == cfg]
    mh = mh[[(cfg, b, s) not in bad for b, s in zip(mh.B, mh.seed)]]
    for B, g in mh.groupby("B"):
        v = g.assign(p=g.rand_all / g.sends_all * 100).groupby("seed").p.mean().to_numpy()      # per seed: mean over messages 2-4 of the max-FCT host's random share
        rows_rnd.append({"x": f"B={int(B)}", "y": round(float(v.mean()), 2), "ci": round(min(ci(v), float(v.mean())), 2), "n": len(v)})
    bmin = min(Bs, key=lambda b: out[b][0])
    dip = bool(out[bmin][0] < -2 * out[bmin][1] and bmin < top)          # the minimum is below the largest-B reference by more than 2 SE: a dip, not a knee
    k02 = int(bmin) if dip else kneesL[0.002]
    rows_trm = []
    for B, g in RES[(RES.cfg == cfg)].groupby("B"):
        g = g[[(cfg, B, s) not in bad for s in g.seed]]
        v = g.trims_total.to_numpy()
        rows_trm.append({"x": f"B={int(B)}", "y": round(float(v.mean()), 1), "ci": round(min(ci(v), float(v.mean())), 1), "n": len(v)})
    for lst, rows in ((series_abs, rows_abs), (series_rat, rows_rat), (series_rnd, rows_rnd), (series_trm, rows_trm)):
        lst.append({"label": label, "style": key, "bfct": (None if k02 is None else int(k02)), "noBand": False, "rows": rows})
    first = paired(per_seed(cfg, True))
    for t, kk in zip(TOLS, kn):
        kn[kk]["labels"].append(f"N={N} ({L / 1000:g} us)"); kn[kk]["N"].append(N); kn[kk]["fill"].append(int(round(fill)))
        kn[kk]["later"].append(int(kneesL[t])); kn[kk]["bmin"].append(int(bmin)); kn[kk]["dip"].append(dip); kn[kk]["first"].append(int(first[4][t]))
    sub = RES[(RES.cfg == cfg)]
    ok = sub[[(cfg, b, s) not in bad for b, s in zip(sub.B, sub.seed)]]
    b8 = sub[sub.B == min(8, Bs[-2])]
    tab.append({"lat": L / 1000, "rtt": RTT[L], "N": N, "fill": int(round(fill)), "ref": int(top), "floor": float(refv),
                "exc8": float(out[min(b for b in Bs if b >= 8)][0]) if any(b >= 8 for b in Bs) else None,
                "trims_lo": float(sub[sub.B == min(sub.B)].trims_total.mean()), "trims_ref": float(sub[sub.B == top].trims_total.mean()),
                "cells": len(sub), "ok": len(ok), "k02": int(kneesL[0.002]), "bmin": int(bmin), "emin": float(out[bmin][0]), "esem": float(out[bmin][1]), "dip": dip, "k1": int(kneesL[0.01]), "k2": int(kneesL[0.02]), "k5": int(kneesL[0.05])})

# ---- god arm (capacity-weighted random draws): same metric, paired difference, uplink classes, EV distribution
PMG = pd.read_csv(D / "n_permessage_god.csv")
PMG["lat"] = PMG.cfg.str.extract(r"lat(\d+)")[0].astype(int)
UMG = pd.concat([pd.read_csv(f) for f in sorted(D.glob("n_um_god_[0-9]*.csv"))])
UMG["lat"] = UMG.cfg.str.extract(r"lat(\d+)")[0].astype(int)
series_gabs, series_grat, series_diff = [], [], []
for i, L in enumerate(LATS):
    g = PMG[(PMG.lat == L) & (PMG.msg > 0)].groupby(["B", "seed"])["max"].mean().reset_index()
    r = PM[(PM.cfg == CFG[L]) & (PM.msg > 0)]
    r = r[[(CFG[L], b, s) not in bad for b, s in zip(r.B, r.seed)]].groupby(["B", "seed"])["max"].mean().reset_index()
    ra, rr, rd = [], [], []
    for B, h in g.groupby("B"):
        v = h["max"].to_numpy(); x = f"B={int(B)}"
        ra.append({"x": x, "y": round(float(v.mean()), 2), "ci": round(ci(v), 2), "n": len(v)})
        rr.append({"x": x, "y": round(float(v.mean()) / SOLV[L], 4), "ci": round(ci(v) / SOLV[L], 4), "n": len(v)})
        m = h.merge(r[r.B == B], on="seed", suffixes=("_g", "_r"))
        if len(m):
            d = (m.max_r - m.max_g).to_numpy(); rd.append({"x": x, "y": round(float(d.mean()), 2), "ci": round(ci(d), 2), "n": len(d)})
    for lst, rows in ((series_gabs, ra), (series_grat, rr), (series_diff, rd)):
        lst.append({"label": series_abs[i]["label"], "style": f"n{i}", "bfct": None, "noBand": False, "rows": rows})
sol_abs = [round(SOLV[L], 3) for L in LATS]
keys = [(s["label"], s["style"]) for s in series_abs]
CLS = X.class_series(UM, LATS, bad, keys)
EVD = X.ev_dist(UM, LATS, bad)
WTAB = X.warm_table(WM, LATS, [r["N"] for r in tab])
QTAB = X.queue_table(RES, LATS)
EVOPT = {str(L): sorted({int(k.split('|')[1]) for k in EVD if k.split('|')[0] == str(L)}) for L in LATS}
CLSG = X.class_series(UMG, LATS, set(), keys)
EVDG = X.ev_dist(UMG, LATS, set())
EVOPTG = {str(L): sorted({int(k.split('|')[1]) for k in EVDG if k.split('|')[0] == str(L)}) for L in LATS}

seeds = int(PM[PM.cfg == CFG[LATS[0]]].seed.nunique())
n_all, n_ok = len(RES), len(RES) - len(bad)
Ns, Ks = kn["0.2"]["N"], kn["0.2"]["later"]
chips = [chip("ok" if not bad else "warn", f"{n_ok} of {n_all} cells in the plots (0 RTOs, 0 Freezing Mode entries)" if not bad else f"{n_ok} of {n_all} cells in the plots; {len(bad)} dropped: RTO or Freezing Mode"),
         chip("ok", f"{seeds} seeds per point, paired against the largest B of each line"),
         chip("warn", "trims grow with N (table): the first RTT of message 1 is a blind random burst into 101-packet queues"),
         chip("warn", "4 MiB messages = 1027 packets: N = %d is already %d%% of a message, so this is about the largest N this workload can read" % (max(Ns), round(100 * max(Ns) / 1027))),
         chip("warn", "link latency also changes the RTT-derived simulator parameters (NSCC reference RTT / BDP, RTO)")]
tiles = [tile("N, one parameter swept", f"{min(Ns)} to {max(Ns)}", f"delay per link {LATS[0] / 1000:g} to {LATS[-1] / 1000:g} us (RTT = 8 x), rate, MTU, queues unchanged"),
         tile("shape of max FCT vs B, messages 2-4", f"knee up to N = {max(r['N'] for r in tab if not r['dip'] and r['emin'] > -1)}", f"dip (lowest B below the largest-B value by more than 2 SE) from N = {min(r['N'] for r in tab if r['dip'])}" if any(r["dip"] for r in tab) else "no dip", "bad"),
         tile("trims per run at the largest N", f"{tab[-1]['trims_lo']:.0f}", f"at B = {tab[0]['ref'] and min(RES.B)}; {tab[0]['trims_lo']:.0f} at the smallest N")]

VERDICT = "VERDICT_PLACEHOLDER"          # replaced by the result text after the numbers are read (see below)
RESULT_TEXT = (Path(HERE) / "n_result_text.txt").read_text().strip() if (HERE / "n_result_text.txt").exists() else VERDICT

body = [
    h2("What the experiment does", 1),
    note("Tornado permutation on 128 hosts (host i sends to host i+64), 4 messages of 4 MiB per pair, started 1000 us apart; ToR0 uplinks are 5/95, so hosts 0 to 7 are degraded. "
         "The one parameter changed is the delay of every fabric link (a path has 4 links, so RTT = 8 x the delay plus serialization), which sets the RTT and so N = packets in flight at a message boundary (rate and MTU fixed)."),
    note("`-connections_mapping` hands the REPS buffer of a finished message to the next one on the pair. Messages 2 to 4 start with up to min(B, N) recycled EVs and draw the rest at random; "
         "message 1 starts empty and is the control."),
    end(),
    h2("Max FCT vs B, one line per N", 2),
    controls("arm-ctl", "arm"),
    controls("fct-ctl", "y axis"),
    controls("sol-ctl", "speed of light (absolute view)"),
    plot("fct"),
    note("Max FCT of the 8 degraded sources, mean of messages 2 to 4 per seed, mean and 95% CI over the seeds. Ring = paired knee at 0.2% tolerance where the curve ends flat, the lowest point where it dips below its own largest-B value by more than 2 SE. "
         "The default view divides each line by the speed of light of its own N (1.00 = speed of light), so the lines of different RTT are comparable."),
    note("Dotted line = speed of light of each N: one 200G sender and one connection, 4 x 4 MiB, nothing else running, ToR0 uplinks at 0.5 (equivalent network). Sim and analytic agree within 0.12 us "
         "(1026 send gaps of 0.166 us + 8 x link delay + 0.42 us). Up to N = 111 the best B sits 5 us above it at every RTT; from N = 208 it sits 0.8 to 1.0 RTT above it."),
    callout("Prediction", "Written before the sweep: the knee of messages 2-4 is 0.9 to 1.1 times the fresh EVs carried over (about the measured N, below it at the largest N because trims kill tokens), "
                          "grows monotonically with the link latency, and message 1 stays at 4 to 16."),
    callout("Result", RESULT_TEXT),
    callout("Result", "God mode. Arm selector: random draws weighted by link capacity (5% of draws on 5% links instead of 50%), everything else unchanged, 728 cells. "
                        "Small B gets much faster (15 us at N = 26, 117 us at N = 789, B = 2) and the knee moves to B of a few tens; the dip at B = 256/320 is gone and the best FCT drops to 1.15 (N = 400) and 1.29 (N = 789) times the speed of light. "
                        "Miss: at N = 111 and large B god is 17 us slower, 40-50% random sends and ECN marks on the 95% links."),
    end(),
    h2("Packets sent through the 5% links", 3),
    controls("arm-ctl-c", "arm"),
    controls("cls-ctl", "measure"),
    plot("cls"),
    note("Max-FCT host of messages 2-4 (the host differs per cell), per seed over the three messages, mean and 95% CI over the seeds. Even EV = path j = ToR0 uplink j = 5% link (SRv6: EV % 8, identity checked against the queue stats, 0 mismatches). "
         "The ECN rate is the share of ACKs carrying a mark; the trim rate the share of answers that were NACKs. A mark can also come from a later queue, so the 5% versus 95% contrast is the signal."),
    aside("Reading the queues of the 5% links",
          "Their queue is 5 packets and their ECN thresholds are scaled by 0.05 as well (the stdout prints only the healthy line, low 25 / high 76 packets): marks do occur on these links although the queue never exceeds 5 packets, "
          "which an unscaled threshold of 25 packets could not produce. The 95% links hold up to 48 packets."),
    end(),
    h2("EV distribution: max-FCT host vs best-FCT host", 4),
    controls("arm-ctl-e", "arm"),
    controls("ev-ctl-n", "N"),
    controls("ev-ctl-b", "B"),
    plot("ev"),
    note("Share of the host's sends per EV (SRv6 EV = path = ToR0 uplink; even EV = 5% link), mean and 95% CI over the seeds. Best = smallest FCT among hosts 0-7 of the same message (same traffic class). "
         "Warmup = the sends of message 1 before the first valid (fresh_pop) EV send, that send excluded; post-warmup = all later sends of messages 1-4."),
    end(),
    h2("Warmup is one bandwidth-delay product", 5, tag="supporting check"),
    table("wtbl"),
    note("Sends before the first valid EV send, per flow of message 1 (hosts 0-7, all cells). Independent of B; every one is a random draw (no explore labels), half of them on the 5% links. "
         "The code has no explicit initial explore phase: the buffer is empty until the first unmarked ACK, which returns after one RTT."),
    end(),
    h2("Queues of the degraded links", 6, tag="supporting check"),
    table("qtbl"),
    note("Largest queue seen on the ToR0 uplinks over all cells of each latency, in packets of 4150 B. The 5% links (20 Gbit/s) have a 5-packet queue, the 95% links (380 Gbit/s) a 96-packet one."),
    end(),
    h2("Why: random draws in the first RTT of a later message", 7, tag="supporting check"),
    plot("rnd"),
    note("Share of random EV draws over all 1027 sends of the host with the largest FCT in each message (messages 2-4 averaged per seed; the host differs per cell). For N up to 111 it falls to about 0 once B reaches the carried fill. From N = 208 it stays at large B at 12% (N = 208), 22% (N = 400) and 33% (N = 789), so it does not mark where max FCT stops improving. The first 300 sends alone gave (300 - B)/300 for N of 400 and 789, which is why the window was widened."),
    end(),
    h2("Trims are lowest at the dip", 8, tag="supporting check"),
    plot("trm"),
    note("Packets trimmed per run (all flows). Trims are lowest at B = 192 (N = 208) and B = 320 (N = 400), the same B as the lowest max FCT, and 11 to 39% higher on the plateau. "
         "At N = 789 they are lowest at B = 512 while max FCT is lowest at B = 256, so the match is partial. Consistent with a trim effect only; no intervention was run."),
    end(),
    h2("Per-latency table", 9, tag="supporting check"),
    table("ltbl"),
    aside("What else changes with the latency",
          "The unloaded RTT feeds the NSCC reference RTT and BDP and the RTO, so those scale with it; queues, ECN thresholds, MTU, send rate and degradation do not. "
          "The queues stay at 101 packets while N grows, so the blind first-RTT burst of message 1 trims more packets at larger N (table). "
          "The high-N lines therefore measure N together with the token kills those trims cause."),
    end(),
]

PAGE_JS = r"""
let mode = 'rat';
let arm = 'reps';
function drawFct() {
  const abs = mode === 'abs', G = arm === 'god';
  if (arm === 'diff') {
    PC.fctVsB('fct', DATA.diff, 'REPS minus god mode, paired by seed (positive = god is faster) - one line per N', { ylabel: 'REPS - god max FCT (us)', cats: DATA.cats, refY: 0, refText: 'no difference' });
    return;
  }
  const series = abs ? (G ? DATA.gfct : DATA.fct) : (G ? DATA.grat : DATA.rat);
  PC.fctVsB('fct', series, (G ? 'GOD MODE: ' : '') + (abs ? 'Max FCT vs B - one line per N, link latency swept (128 hosts, messages 2-4, 8 seeds, 95% CI)'
                               : 'Max FCT relative to the speed of light of the same N, computed for its own link delay (1 = speed of light) - one line per N'),
    abs ? { cats: DATA.cats, extra: solTraces(true) } : { ylabel: 'max FCT / speed of light', cats: DATA.cats, refY: 1, refText: 'speed of light' });
}
function drawTrm() { PC.fctVsB('trm', DATA.trm, 'Packets trimmed per run vs B (all flows, 8 seeds, 95% CI)', { ylabel: 'trimmed packets', cats: DATA.cats }); }
function drawRnd() { PC.fctVsB('rnd', DATA.rnd, 'Random EV draws over the whole message of the max-FCT host, messages 2-4, vs B (8 seeds, 95% CI)', { ylabel: '% random draws', cats: DATA.cats }); }
function drawTable() {
  document.getElementById('ltbl').innerHTML = '<thead><tr><th>link latency (us)</th><th>RTT (us)</th><th>N</th><th>fresh carried</th><th>largest B</th>'
    + '<th>floor max FCT (us)</th><th>trims, smallest B</th><th>trims, largest B</th><th>cells ok / run</th>'
    + '<th>shape</th><th>B of lowest max FCT (excess, us)</th><th>paired knee 0.2%</th><th>1%</th><th>2%</th><th>5%</th></tr></thead><tbody>'
    + DATA.tab.map(r => `<tr><td>${r.lat}</td><td>${r.rtt.toFixed(1)}</td><td>${r.N}</td><td>${r.fill}</td><td>${r.ref}</td><td>${r.floor.toFixed(1)}</td>`
      + `<td>${Math.round(r.trims_lo)}</td><td>${Math.round(r.trims_ref)}</td><td>${r.ok} / ${r.cells}</td>`
      + `<td>${r.dip ? 'dip' : 'knee'}</td><td>${r.bmin} (${r.emin.toFixed(1)} ± ${r.esem.toFixed(1)})</td><td>${r.k02}</td><td>${r.k1}</td><td>${r.k2}</td><td>${r.k5}</td></tr>`).join('') + '</tbody>';
}
PC.select('fct-ctl', [['rat', 'max FCT / speed of light (1 = speed of light)'], ['abs', 'max FCT (absolute, us)']], mode, v => { mode = v; drawFct(); });

let solOn = 'on', clsM = 'sendshare', evN = String(DATA.lats[DATA.lats.length - 1]), evB = null;
const CLS_T = { sendshare: ["% of the max-FCT host's sends on 5% links", '% of sends'], trim5: ['trimmed share of packets sent on 5% links', '% trimmed'],
  ecn5: ['ECN-marked share of ACKs, 5% links', '% of ACKs marked'], trim95: ['trimmed share of packets sent on 95% links', '% trimmed'], ecn95: ['ECN-marked share of ACKs, 95% links', '% of ACKs marked'] };
function solTraces(abs) {
  if (solOn !== 'on') return [];
  return DATA.sol.map((y, i) => ({ x: DATA.cats, y: DATA.cats.map(() => abs ? y : y - DATA.ref[i]), type: 'scatter', mode: 'lines',
    name: 'speed of light (one dotted line per N)', legendgroup: 'gsol', showlegend: i === 0,
    line: { color: PC.color('n' + i), width: 1.6, dash: 'dot' }, hovertemplate: 'speed of light ' + y.toFixed(1) + ' us<extra></extra>' }));
}
function armC() { return arm === 'god' || arm === 'diff' ? 'god' : 'reps'; }
function drawCls() { PC.fctVsB('cls', (armC() === 'god' ? DATA.gcls : DATA.cls)[clsM], (armC() === 'god' ? 'GOD MODE: ' : '') + CLS_T[clsM][0] + ' vs B, messages 2-4 (8 seeds, 95% CI)', { ylabel: CLS_T[clsM][1], cats: DATA.cats }); }
function evOptions() {
  const host = document.getElementById('ev-ctl-b'); host.innerHTML = '';
  const bs = (armC() === 'god' ? DATA.gevopt : DATA.evopt)[evN]; if (!bs.includes(Number(evB))) evB = bs[Math.floor(bs.length / 2)];
  PC.select('ev-ctl-b', bs.map(b => [String(b), 'B = ' + b]), String(evB), v => { evB = v; drawEv(); });
}
function drawEv() {
  const e = (armC() === 'god' ? DATA.gev : DATA.ev)[evN + '|' + evB] || {}, names = [['max_w', 'max-FCT host, warmup', 'c4'], ['best_w', 'best-FCT host, warmup', 'c2'], ['max_p', 'max-FCT host, post-warmup', 'c3'], ['best_p', 'best-FCT host, post-warmup', 'c1']];
  const cats = [0, 1, 2, 3, 4, 5, 6, 7].map(i => 'EV ' + i + (i % 2 ? ' (95%)' : ' (5%)'));
  const traces = names.filter(n => e[n[0]]).map(n => PC.barTrace(n[2], cats.map((c, i) => ({ x: c, y: e[n[0]].y[i], ci: e[n[0]].ci[i], n: e[n[0]].n })), n[1] + ' - ' + e[n[0]].bad.toFixed(1) + '% on 5% links'));
  const t = PC.theme(); t.barmode = 'group'; t.xaxis.type = 'category'; t.yaxis.title.text = "% of the host's sends";
  const k = DATA.lats.indexOf(Number(evN));
  PC.draw('ev', traces, t, (armC() === 'god' ? 'GOD MODE: ' : '') + 'EV distribution, N = ' + (k >= 0 ? DATA.Ns[k] : '?') + ', B = ' + evB + ' (8 seeds, 95% CI)');
}
function drawWq() {
  document.getElementById('wtbl').innerHTML = '<thead><tr><th>delay per link (us)</th><th>N</th><th>warmup sends, median</th><th>min - max</th><th>warmup / N</th><th>first ACK after (us)</th><th>on 5% links (%)</th><th>flows</th></tr></thead><tbody>'
    + DATA.warm.map(r => `<tr><td>${r.lat}</td><td>${r.N}</td><td>${r.med}</td><td>${r.lo} - ${r.hi}</td><td>${r.bdp_ratio.toFixed(2)}</td><td>${r.t_ack.toFixed(2)}</td><td>${r.bad.toFixed(1)}</td><td>${r.cells}</td></tr>`).join('') + '</tbody>';
  document.getElementById('qtbl').innerHTML = '<thead><tr><th>delay per link (us)</th><th>max queue, 5% links (packets)</th><th>max queue, 95% links (packets)</th><th>cells</th></tr></thead><tbody>'
    + DATA.q1.map(r => `<tr><td>${r.lat}</td><td>${r.bad_pk.toFixed(1)}</td><td>${r.good_pk.toFixed(1)}</td><td>${r.cells}</td></tr>`).join('') + '</tbody>';
}
PC.select('sol-ctl', [['on', 'shown (dotted)'], ['off', 'hidden']], solOn, v => { solOn = v; drawFct(); });
PC.select('cls-ctl', [['sendshare', 'share of sends on 5% links'], ['trim5', 'trim rate, 5% links'], ['ecn5', 'ECN rate, 5% links'], ['trim95', 'trim rate, 95% links'], ['ecn95', 'ECN rate, 95% links']], clsM, v => { clsM = v; drawCls(); });
PC.select('ev-ctl-n', DATA.lats.map((L, i) => [String(L), 'N = ' + DATA.Ns[i] + ' (' + L / 1000 + ' us)']), evN, v => { evN = v; evOptions(); drawEv(); });
function armCtl() {
  const two = [['reps', 'REPS (uniform random draws)'], ['god', 'god mode (draws weighted by link capacity)']];
  [['arm-ctl', two.concat([['diff', 'REPS minus god (paired, us)']]), arm], ['arm-ctl-c', two, armC()], ['arm-ctl-e', two, armC()]].forEach(c => {
    document.getElementById(c[0]).innerHTML = ''; PC.select(c[0], c[1], c[2], v => { arm = v; armCtl(); drawFct(); drawCls(); evOptions(); drawEv(); });
  });
}
armCtl();
evOptions();
function drawAll() { drawFct(); drawRnd(); drawTrm(); drawCls(); drawEv(); }
drawTable(); drawWq(); drawAll(); PC.onRedraw(drawAll);
"""

if __name__ == "__main__":
    build_page(
        KNEE / "plots" / "nsweep.html",
        title="Dial E: sweeping N with link latency",
        eyebrow="meeting 26/10/26 · knee study · dial E · N sweep",
        h1="Sweeping N with one parameter: a knee up to N = 111, a dip from N = 400",
        lede="Only the link latency changes. Up to N = 111 the paired knee of messages 2-4 rises with the packets in flight (16, 48, 64, 128). "
             "At N = 400 and 789 max FCT has a dip, not a knee: the lowest B is 12 to 17 us below the largest.",
        cfg="primary metric: max FCT of the 8 degraded sources (messages 2-4) · matched 200G constant-rate sender · ToR0 uplinks 5/95 · 128 hosts, tornado, "
            "4 messages x 4 MiB per pair, 1000 us apart (`-connections_mapping`) · delay per link 0.25 to 16 us · freezing, trimming on · needs [FIX: connection-info-cwnd-overflow]",
        full_cmd="run_m4.flags('matched','healthy',B,seed) + -connections_mapping with connection_matrices/knee/msg_n128_k4_s4M_p1000.cm and topologies/knee/topo_128_d8_lat{250..16000}.topo "
                 "(knee/scripts/make_knee_configs.py, run_knee.py --bsmap data/n_bsmap.json in container m23-dev). Details: knee/README.md, Dial E, N sweep.",
        brief=question("Does the knee of a repeated message move with N when only one parameter, the link latency, changes N?",
                       "Seven link latencies (N = 26 to 789 packets in flight), 4 messages of 4 MiB per pair, B from 2 to 1536, 8 seeds.",
                       "Max FCT against B, one line per N, and the knee of messages 2-4 against N and against the fresh EVs carried over."),
        chips=chips, tiles=tiles, body=body, page_js=PAGE_JS,
        payload={"cats": [f"B={b}" for b in sorted({int(r["x"][2:]) for s in series_abs for r in s["rows"]})], "fct": series_abs, "rat": series_rat, "rnd": series_rnd, "trm": series_trm, "kn": kn, "tab": tab, "sol": sol_abs, "ref": refs, "cls": CLS, "ev": EVD, "evopt": EVOPT, "gfct": series_gabs, "grat": series_grat, "diff": series_diff, "gcls": CLSG, "gev": EVDG, "gevopt": EVOPTG, "lats": [int(L) for L in LATS], "Ns": [r["N"] for r in tab], "warm": WTAB, "q1": QTAB},
        footer="Source `knee/data/n_results.jsonl`, `n_permessage.csv`, `n_mech.csv`; god arm `n_permessage_god.csv`, `n_um_god_*.csv`. "
               "Regenerate: `python3 experiments/meeting_26_10_26/knee/scripts/build_page_nsweep.py`.")
