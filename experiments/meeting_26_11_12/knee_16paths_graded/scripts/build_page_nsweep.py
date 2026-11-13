#!/usr/bin/env python3
"""knee_16paths/plots/nsweep.html: the N sweep on a 16-path fabric (512 hosts, 16 hosts per ToR, 16 uplinks, k = 32 fat tree); dial E with ONE parameter (delay of every fabric link) sweeping N = packets in flight,
max FCT vs B with one line per N, in the plot_common style (skill interactive-plotter).
Input (copied out of the container, see knee/README.md "Dial E, N sweep"):
  data/n_results.jsonl  (run_knee results, gate columns, trims)  data/n_permessage.csv (e_permessage.py: per message max FCT of hosts 0-15)
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
import params as Pm  # noqa: E402
ALL_LATS = (250, 500, 1000, 2000, 4000, 8000, 16000)   # latencies of the 7-latency page (knee_16paths); colour index = position there
LI = [ALL_LATS.index(int(L)) for L in Pm.LATS]
N_LABEL = {250: 25, 1000: 65, 4000: 208, 16000: 788}   # N of the 5/95 page (knee_16paths) for the same latencies
from plot_common import (aside, build_page, callout, chip, controls, end, h2,  # noqa: E402
                         note, plot, question, table, tile)

import os
D = KNEE / os.environ.get("K16_DATA", "data")          # data_mini = the mini-sweep gate
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306}   # two-sided 95% t by df
TOLS = (0.002, 0.01, 0.02, 0.05)

RES = pd.DataFrame(map(json.loads, (D / "n_results.jsonl").read_text().splitlines())).drop_duplicates(["cfg", "B", "seed"])
RES["lat"] = RES.cfg.str.extract(r"lat(\d+)")[0].astype(int)
PM = pd.read_csv(D / "n_permessage.csv")
MECH = pd.read_csv(D / "n_mech.csv")
MH = pd.read_csv(D / "n_mech_maxhost.csv")           # random share of the host that had the max FCT in each message (from the single traced pass: hosts 0-15 of every message)
bad = set(map(tuple, RES[(RES.rtos > 0) | (RES.freeze_entries > 0)][["cfg", "B", "seed"]].values))
LATS = sorted(RES.lat.unique())
CFG = {L: f"{Pm.CFG_REPS}_lat{L}" for L in LATS}
RTT = {L: 0.337 + 8 * L / 1000 for L in LATS}          # unloaded RTT in us as printed by the simulator (network_max_unloaded_rtt)


SOL, UM, WM = X.load(D)
SOLV = X.sol_by_lat(SOL)


def ci(v):
    n = len(v)
    return float(T975.get(n - 1, 1.96) * np.std(v, ddof=1) / np.sqrt(n)) if n > 1 else 0.0


def per_seed(cfg, first):
    """one number per (B, seed): max FCT of the 16 degraded sources, message 1 alone or the mean of messages 2-4"""
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
    N_MEASURED = N
    N = N_LABEL[int(L)]   # same N label as the 5/95 page (its measured values), so the two pages line up; this run measured 27, 66, 217, 790
    xl = per_seed(cfg, False)
    Bs, top, refv, out, kneesL = paired(xl)
    refs.append(round(float(refv), 3))
    fill = float(m[m.B == top][["fresh_m2", "fresh_m3", "fresh_m4"]].to_numpy().mean())
    key = f"n{LI[i]}"   # colour of the 7-latency page of knee_16paths: same latency, same colour
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
RESG = pd.DataFrame(map(json.loads, (D / "n_results_god.jsonl").read_text().splitlines())).drop_duplicates(["cfg", "B", "seed"])
badg = set(map(tuple, RESG[(RESG.rtos > 0) | (RESG.freeze_entries > 0)][["cfg", "B", "seed"]].values))
PMG = PMG[[(c, b, s) not in badg for c, b, s in zip(PMG.cfg, PMG.B, PMG.seed)]]
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
        lst.append({"label": series_abs[i]["label"], "style": f"n{LI[i]}", "bfct": None, "noBand": False, "rows": rows})
sol_abs = [round(SOLV[L], 3) for L in LATS]
keys = [(s["label"], s["style"]) for s in series_abs]
CLS = X.class_series(UM, LATS, bad, keys)
EVA = X.ev_agg(UM, LATS, bad, keys)
WTAB = X.warm_table(WM, LATS, [r["N"] for r in tab])
QTAB = X.queue_table(RES, LATS)
CLSG = X.class_series(UMG, LATS, badg, keys, Pm.CFG_GOD)
EVAG = X.ev_agg(UMG, LATS, badg, keys, Pm.CFG_GOD)
MHG = pd.read_csv(D / "n_mech_maxhost_god.csv")
BUFR = pd.read_csv(D / "n_bufstate_reps.csv")
BUFG = pd.read_csv(D / "n_bufstate_god.csv")
BUF = X.buf_dist(BUFR, UM, LATS, bad)
BUFGD = X.buf_dist(BUFG, UMG, LATS, badg, Pm.CFG_GOD)
ESR = pd.read_csv(D / "n_evsends_reps.csv")
ESG = pd.read_csv(D / "n_evsends_god.csv")
SENT = X.ev_sent(ESR, UM, LATS, bad)
SENTG = X.ev_sent(ESG, UMG, LATS, badg, Pm.CFG_GOD)
BUFOPT = {str(L): sorted({int(k.split("|")[2]) for k in BUF if k.split("|")[1] == str(L)}) for L in LATS}
EVS = X.random_share(MH, LATS, bad, keys)
EVSG = X.random_share(MHG, LATS, badg, keys, Pm.CFG_GOD)

# ---- DPS arm (-load_balancing_algo dps -dps_dist capacity = ratio_j / 8 per path, 12.5% / 87.5% by class): no buffer, no B (byte-identical flow-finish lines for B = 2, 8, 64), one cell per latency and seed, seeds 42-44
DPS_FILES = ("dps_permessage.csv", "dps_results.jsonl", "dps_compare.csv")
HAS_DPS = all((D / f).exists() for f in DPS_FILES)
DPS_SEEDS = (42, 43, 44)
DPS = DCMP = DCLS = None
DPS_N = DPS_CELLS = 0
if HAS_DPS:
    CFGD = {L: f"h512_p16g_msgNhDcap_lat{L}" for L in LATS}
    RESD = pd.DataFrame(map(json.loads, (D / "dps_results.jsonl").read_text().splitlines())).drop_duplicates(["cfg", "B", "seed"])
    RESD = RESD[RESD.seed.isin(DPS_SEEDS)]
    badd = set(map(tuple, RESD[(RESD.rtos > 0) | (RESD.freeze_entries > 0)][["cfg", "B", "seed"]].values))
    PMD = pd.read_csv(D / "dps_permessage.csv")
    PMD = PMD[PMD.seed.isin(DPS_SEEDS) & (PMD.msg > 0)]
    PMD = PMD[[(c, b, s_) not in badd for c, b, s_ in zip(PMD.cfg, PMD.B, PMD.seed)]]
    DPS = {"y": [], "ci": [], "n": [], "yr": [], "cir": []}
    for L in LATS:
        v = PMD[PMD.cfg == CFGD[L]].groupby("seed")["max"].mean().to_numpy()      # per seed: mean over messages 2-4 of the max FCT of hosts 0-15 (same metric as the lines)
        DPS["y"].append(round(float(v.mean()), 2)); DPS["ci"].append(round(ci(v), 2)); DPS["n"].append(len(v))
        DPS["yr"].append(round(float(v.mean()) / SOLV[L], 4)); DPS["cir"].append(round(ci(v) / SOLV[L], 4))
    DPS_CELLS, DPS_N = len(RESD), int(RESD.seed.nunique())
    CMP = pd.read_csv(D / "dps_compare.csv").set_index("lat")
    DCATS = [f"{L / 1000:g} us (N={r['N']})" for L, r in zip(LATS, tab)]
    DCMP = []
    for lab, col, key in (("vs god, B = 8", "dps_minus_god_B=8", "c3"), ("vs god, best B of that latency", "dps_minus_god_best", "c4"),
                          ("vs REPS, B = 8", "dps_minus_REPS_B=8", "c1"), ("vs REPS, best B of that latency", "dps_minus_REPS_best", "c2")):
        DCMP.append({"label": "DPS " + lab, "style": key, "bfct": None, "noBand": False,
                     "rows": [{"x": DCATS[i], "y": round(float(CMP.loc[L, col]), 2), "ci": round(float(CMP.loc[L, col + "_ci"]), 2), "n": 3} for i, L in enumerate(LATS)]})
    UMD = pd.concat([pd.read_csv(f) for f in sorted(D.glob("dps_um_[0-9]*.csv"))])
    UMD["lat"] = UMD.cfg.str.extract(r"lat(\d+)")[0].astype(int)
    UMD = UMD[UMD.seed.isin(DPS_SEEDS)]
    DCLS = X.class_series(UMD, LATS, badd, keys, "h512_p16g_msgNhDcap")

seeds = int(PM[PM.cfg == CFG[LATS[0]]].seed.nunique())
n_all, n_ok = len(RES), len(RES) - len(bad)
Ns, Ks = kn["0.2"]["N"], kn["0.2"]["later"]
chips = [chip("ok" if not bad else "warn", f"{n_ok} of {n_all} cells in the plots (0 RTOs, 0 Freezing Mode entries)" if not bad else f"{n_ok} of {n_all} cells in the plots; {len(bad)} dropped: RTO or Freezing Mode"),
         chip("ok", f"{seeds} seeds per point, paired against the largest B of each line"),
         chip("warn", "trims per run for every N are in the per-latency table (the first RTT of message 1 is a blind random burst)"),
         chip("warn", "4 MiB messages = 1027 packets: N = %d is already %d%% of a message, so this is about the largest N this workload can read" % (max(Ns), round(100 * max(Ns) / 1027))),
         chip("warn", "link latency also changes the RTT-derived simulator parameters (NSCC reference RTT / BDP, RTO)")]
if HAS_DPS:
    chips += [chip("ok" if not badd else "warn", f"DPS arm: {len(RESD) - len(badd)} of {len(RESD)} cells in the plots (0 RTOs, no Freezing Mode possible: no buffer)" if not badd else f"DPS arm: {len(badd)} cells dropped (RTO)"),
              chip("warn", f"DPS arm has {DPS_N} seeds (REPS and god lines: {seeds}); the DPS-minus-arm plot restricts REPS and god to the same {DPS_N} seeds"),
              chip("ok", "DPS = -load_balancing_algo dps -dps_dist capacity: every packet draws its EV independently, 12.5% of the draws on the 8 slow links, 87.5% on the 8 fast ones (weight of path j = its ratio / 8); B is ignored")]
tiles = [tile("N, one parameter swept", f"{min(Ns)} to {max(Ns)}", f"delay per link {LATS[0] / 1000:g} to {LATS[-1] / 1000:g} us (RTT = 8 x), rate, MTU, queues unchanged"),
         tile("shape of max FCT vs B, messages 2-4", f"knee up to N = {max(r['N'] for r in tab if not r['dip'] and r['emin'] > -1)}", f"dip (lowest B below the largest-B value by more than 2 SE) from N = {min(r['N'] for r in tab if r['dip'])}" if any(r["dip"] for r in tab) else "no dip", "bad"),
         tile("trims per run at the largest N", f"{tab[-1]['trims_lo']:.0f}", f"at B = {tab[0]['ref'] and min(RES.B)}; {tab[0]['trims_lo']:.0f} at the smallest N")]

VERDICT = "VERDICT_PLACEHOLDER"          # replaced by the result text after the numbers are read (see below)
RESULT_TEXT = (Path(HERE) / "n_result_text.txt").read_text().strip() if (HERE / "n_result_text.txt").exists() else VERDICT
DPS_RESULT_TEXT = (Path(HERE) / "dps_result_text.txt").read_text().strip() if (HERE / "dps_result_text.txt").exists() else VERDICT

body = [
    h2("What the experiment does", 1),
    note("Tornado permutation on 512 hosts (host i sends to host i+256) of a 2-tier fat tree with 16 paths (k = 32: 16 hosts per ToR, 16 uplinks of 400G per ToR, 16 spines, 32 ToRs, SRv6 source routing over the 16 paths), 4 messages of 4 MiB per pair, started 1000 us apart; ToR0 uplinks are graded (path j = uplink j, even j slow: 5, 10, 15, 20, 5, 10, 15, 20 % of 400G = 20, 40, 60, 80 G twice; odd j fast: 95, 90, 85, 80, 95, 90, 85, 80 % = 380, 360, 340, 320 G twice; mean 50%), so hosts 0 to 15 are degraded. The slow half carries 12.5% of ToR0 capacity."),
    note("The one parameter changed is the delay of every fabric link (a path has 4 links, so RTT = 8 x the delay plus serialization), which sets the RTT and so N (labels are those of the 5/95 page so the pages line up; this run measured 27, 66, 217, 790) = the peak number of packets in flight of host 0 in message 1, measured in the trace (rate and MTU fixed). N is the unloaded bandwidth-delay product plus 11 to 15 packets (queueing on the slow links delays ACKs; table in section 7)."),
    note("`-connections_mapping` hands the REPS buffer of a finished message to the next one on the pair. Messages 2 to 4 start with up to min(B, N) recycled EVs and draw the rest at random; "
         "message 1 starts empty and is the control."),
    end(),
    h2("Max FCT vs B, one line per N", 2),
    controls("arm-ctl", "arm"),
    controls("fct-ctl", "y axis"),
    controls("sol-ctl", "speed of light (absolute view)"),
] + ([controls("dps-ctl", "DPS 95/5 (no buffer)")] if HAS_DPS else []) + [
    plot("fct"),
    note("Max FCT of the 16 degraded sources (hosts 0-15), mean of messages 2 to 4 per seed, mean and 95% CI over the seeds. Ring = paired knee at 0.2% tolerance where the curve ends flat, the lowest point where it dips below its own largest-B value by more than 2 SE. "
         "The default view divides each line by the speed of light of its own N (1.00 = speed of light), so the lines of different RTT are comparable."),
    note("Dotted line = speed of light of each N: one 200G sender and one connection, 4 x 4 MiB, nothing else running, ToR0 uplinks at 0.5 (equivalent network). The analytic value is 1026 send gaps of 0.166 us + 8 x link delay + 0.42 us; the table in the README compares it with the sim."),
    callout("Prediction", "Written before the sweep (README, section Predictions): speed of light, N and warmup length equal the 5/95 study; the slow links are less starved (12.5% of capacity instead of 5%), so small-B REPS is faster than in the 5/95 run, the REPS-god gap is smaller and the knee at the same or a smaller B."),
    callout("Result", RESULT_TEXT),
    end(),
] + ([
    h2("DPS: the capacity-weighted distribution without a buffer", 3),
    controls("dpsd-ctl", "DPS vs"),
    plot("dpsd"),
    note("DPS draws every packet's EV independently from the capacity-proportional distribution (12.5% of the packets on the 8 slow links, 87.5% on the 8 fast ones, per path ratio / 8), with no buffer and no feedback, so it does not depend on B and is one flat dashed line per N in the first plot. "
         "This plot is the paired difference to god mode (same weights plus the REPS buffer) and to REPS, same seeds, positive = DPS slower."),
    aside("What best B means here", "Best B is the B with the lowest 3-seed mean of that arm at that latency, chosen on the same seeds, so it is a favourable choice for REPS and god; the B values are in the README table."),
    callout("Prediction", "Written before the sweep (README, DPS arm): DPS loads every ToR0 uplink at exactly its capacity with independent arrivals; same conclusions as in the 5/95 run within the 3-seed interval; trims on the 5% and 10% links."),
    callout("Result", DPS_RESULT_TEXT),
    end(),
] if HAS_DPS else []) + [
    h2("Buffer after messages 2-4: max-FCT host", 4),
    controls("arm-ctl-b", "arm"),
    controls("buf-ctl-h", "host"),
    controls("buf-ctl-n", "N"),
    controls("buf-ctl-b", "B"),
    controls("buf-ctl-u", "unit"),
    plot("ev-buf"),
    note("Buffer when the message has finished (after its last ACK, before the next burst): the valid slots, binned by path (EV = path, 0 to 15; even = slow link), three bars per path for messages 2, 3 and 4. Mean and 95% CI over the seeds; the legend gives valid and invalid slots. Last column: invalid slots = B minus valid (consumed by a pop and not refilled; 0 = full buffer)."),
    controls("arm-ctl-x", "arm"),
    controls("sent-ctl-h", "host"),
    controls("sent-ctl-n", "N"),
    controls("sent-ctl-b", "B"),
    controls("sent-ctl-c", "count"),
    controls("sent-ctl-u", "unit"),
    plot("ev-sent"),
    note("Packets the host sent with each EV during messages 2, 3 and 4 (EV = path, 0 to 15; even = slow link). The sends of message m draw on the buffer left after message m-1 (plot above, same host) and on EVs refilled during the burst. Count: all transmissions (sends + retransmissions) or the 1027 original sends. Mean and 95% CI over the seeds."),
    end(),
    h2("Packets sent through the slow links", 5),
    controls("arm-ctl-c", "arm"),
    controls("cls-ctl", "measure"),
    plot("cls"),
    note("Max-FCT host of messages 2-4 (the host differs per cell), per seed over the three messages, mean and 95% CI over the seeds. Even EV = path j = ToR0 uplink j = slow link (SRv6: EV = path, 0 to 15, identity checked against the queue stats, 0 mismatches). "
         "The ECN rate is the share of ACKs carrying a mark; the trim rate the share of answers that were NACKs. A mark can also come from a later queue, so the slow versus fast contrast is the signal."),
    aside("Reading the queues of the slow links",
          "Their queue is 5 to 20 packets and their ECN thresholds are scaled by their ratio as well (the stdout prints only the healthy line, low 25 / high 76 packets): marks do occur on these links although the queue never exceeds 5 packets, "
          "which an unscaled threshold of 25 packets could not produce for the 5% and 10% links. The measured maxima of both link classes are in the queue table."),
    end(),
    h2("EV distribution against B: max-FCT host and best-FCT host", 6),
    controls("arm-ctl-e", "arm"),
    controls("ev-ctl-ph", "phase"),
    controls("ev-ctl-n", "N"),
    plot("ev-max"),
    plot("ev-best"),
    note("The two bar plots: share of the host's transmissions (sends and retransmissions) on the slow links (even EV) or the fast links (odd EV), summed over the 8 even and the 8 odd EVs. One N at a time, mean and 95% CI over the seeds. "
         "Best = smallest FCT among hosts 0-15 of the same message. Warmup = message 1 before the first valid EV send (independent of B); post-warmup = all later ones of messages 1-4."),
    controls("arm-ctl-s", "arm"),
    plot("ev-src"),
    note("Max-FCT host of each of messages 2-4 (no warmup there), one line per N; click a legend entry to hide or show that N. Counts the 1027 original sends of each message: the share with a random EV, the rest took their EV from the buffer. Retransmissions are not counted."),
    end(),
    h2("Warmup is about one bandwidth-delay product", 7, tag="supporting check"),
    table("wtbl"),
    note("Sends before the first valid EV send, per flow of message 1 (hosts 0-15, all cells); every one is a random draw, half on the slow links. Unloaded BDP = (8 x link delay + 0.337 us) / 0.166 us send gap. "
         "The first ACK returns about 0.4 us later than the unloaded RTT, so warmup is slightly above the BDP at small N."),
    end(),
    h2("Queues of the degraded links", 8, tag="supporting check"),
    table("qtbl"),
    note("Largest queue seen on the ToR0 uplinks over all cells of each latency, in packets of 4150 B. The slow links (20, 40, 60, 80 Gbit/s) have 5, 10, 15, 20-packet queues, the fast links (380, 360, 340, 320 Gbit/s) 96, 91, 86, 81-packet ones."),
    end(),
    h2("Random draws of the max-FCT host", 9, tag="supporting check"),
    plot("rnd"),
    note("Share of random EV draws over all 1027 sends of the host with the largest FCT in each message (messages 2-4 averaged per seed; the host differs per cell)."),
    end(),
    h2("Trims per run vs B", 10, tag="supporting check"),
    plot("trm"),
    note("Packets trimmed per run (all 2048 flows). Whether the trims are lowest where max FCT is lowest is read from the table of the README."),
    end(),
    h2("Per-latency table", 11, tag="supporting check"),
    table("ltbl"),
    aside("What else changes with the latency",
          "The unloaded RTT feeds the NSCC reference RTT and BDP and the RTO, so those scale with it; queues, ECN thresholds, MTU, send rate and degradation do not. "
          "The healthy uplinks have 101-packet queues and the graded uplinks 5 to 96 (queue and ECN thresholds scale with the link speed); see the queue table for the measured maxima."),
    end(),
]

PAGE_JS = r"""
let mode = 'rat', dpsOn = 'on', dpsCmp = 'all';
let arm = 'reps', armCls = 'reps', armEv = 'reps', armSrc = 'reps', armBuf = 'reps', armSent = 'reps', sentH = 'max', sentN = String(DATA.lats[DATA.lats.length - 1]), sentB = null, sentC = 'all', sentU = 'y', bufH = 'max', bufN = String(DATA.lats[DATA.lats.length - 1]), bufB = null, bufU = 'y';   // one arm per plot group: changing one does not redraw the others
function drawFct() {
  const abs = mode === 'abs', G = arm === 'god';
  if (arm === 'diff') {
    PC.fctVsB('fct', DATA.diff, 'REPS minus god mode, paired by seed (positive = god is faster) - one line per N', { ylabel: 'REPS - god max FCT (us)', cats: DATA.cats, refY: 0, refText: 'no difference', signed: true });
    return;
  }
  const series = abs ? (G ? DATA.gfct : DATA.fct) : (G ? DATA.grat : DATA.rat);
  PC.fctVsB('fct', series, (G ? 'GOD MODE: ' : '') + (abs ? 'Max FCT vs B - one line per N, link latency swept (512 hosts, 16 paths, messages 2-4, 4 seeds, 95% CI)'
                               : 'Max FCT relative to the speed of light of the same N, computed for its own link delay (1 = speed of light) - one line per N'),
    abs ? { cats: DATA.cats, extra: solTraces(true).concat(dpsTraces(true)) } : { ylabel: 'max FCT / speed of light', cats: DATA.cats, refY: 1, refText: 'speed of light', extra: dpsTraces(false) });
}
// DPS has no B: one flat dashed line per N across the whole B ladder (95% CI of its 3 seeds as a band), plus a filled marker at B = 8, the only B it was run with (ignored by DPS)
function dpsTraces(abs) {
  if (!DATA.dps || dpsOn !== 'on') return [];
  const D = DATA.dps, out = [];
  DATA.lats.forEach((L, i) => {
    const y = abs ? D.y[i] : D.yr[i], c = abs ? D.ci[i] : D.cir[i], col = PC.color('n' + DATA.li[i]), xs = DATA.cats;
    out.push({ x: xs.concat(xs.slice().reverse()), y: xs.map(() => y + c).concat(xs.map(() => Math.max(y - c, 0))), type: 'scatter', mode: 'lines', fill: 'toself',
      fillcolor: PC.rgba(col, 0.10), line: { width: 0 }, hoverinfo: 'skip', showlegend: false, legendgroup: 'gn' + i });
    out.push({ x: xs, y: xs.map(() => y), type: 'scatter', mode: 'lines', name: 'DPS 95/5 (no buffer, flat in B; one dashed line per N)', legendgroup: 'gn' + i, showlegend: false,
      line: { color: col, width: 2.2, dash: 'longdash' }, hovertemplate: 'DPS 95/5 ' + y.toFixed(abs ? 1 : 3) + ' \u00b1' + c.toFixed(abs ? 1 : 3) + ' (n=' + D.n[i] + ' seeds)<extra></extra>' });
    out.push({ x: ['B=8'], y: [y], type: 'scatter', mode: 'markers', showlegend: false, legendgroup: 'gn' + i, hoverinfo: 'skip',
      marker: { color: col, size: 9, symbol: 'diamond', line: { color: col, width: 1.5 } } });
  });
  return out;
}
function drawDpsd() {
  if (!DATA.dcmp) return;
  const keep = dpsCmp === 'all' ? DATA.dcmp : DATA.dcmp.filter(s => s.label.includes(dpsCmp));
  PC.fctVsB('dpsd', keep, 'DPS minus god mode / REPS, paired by seed (positive = DPS slower), by link delay (3 seeds, 95% CI)',
    { ylabel: 'DPS - arm, max FCT (us)', cats: DATA.dcats, refY: 0, refText: 'no difference', signed: true });
}
function drawTrm() { PC.fctVsB('trm', DATA.trm, 'Packets trimmed per run vs B (all flows, 4 seeds, 95% CI)', { ylabel: 'trimmed packets', cats: DATA.cats }); }
function drawRnd() { PC.fctVsB('rnd', DATA.rnd, 'Random EV draws over the whole message of the max-FCT host, messages 2-4, vs B (4 seeds, 95% CI)', { ylabel: '% random draws', cats: DATA.cats }); }
function drawTable() {
  document.getElementById('ltbl').innerHTML = '<thead><tr><th>link latency (us)</th><th>RTT (us)</th><th>N</th><th>fresh carried</th><th>largest B</th>'
    + '<th>floor max FCT (us)</th><th>trims, smallest B</th><th>trims, largest B</th><th>cells ok / run</th>'
    + '<th>shape</th><th>B of lowest max FCT (excess, us)</th><th>paired knee 0.2%</th><th>1%</th><th>2%</th><th>5%</th></tr></thead><tbody>'
    + DATA.tab.map(r => `<tr><td>${r.lat}</td><td>${r.rtt.toFixed(1)}</td><td>${r.N}</td><td>${r.fill}</td><td>${r.ref}</td><td>${r.floor.toFixed(1)}</td>`
      + `<td>${Math.round(r.trims_lo)}</td><td>${Math.round(r.trims_ref)}</td><td>${r.ok} / ${r.cells}</td>`
      + `<td>${r.dip ? 'dip' : 'knee'}</td><td>${r.bmin} (${r.emin.toFixed(1)} ± ${r.esem.toFixed(1)})</td><td>${r.k02}</td><td>${r.k1}</td><td>${r.k2}</td><td>${r.k5}</td></tr>`).join('') + '</tbody>';
}
PC.select('fct-ctl', [['rat', 'max FCT / speed of light (1 = speed of light)'], ['abs', 'max FCT (absolute, us)']], mode, v => { mode = v; drawFct(); });

let solOn = 'on', clsM = 'sendshare', evPh = 'p', evN = String(DATA.lats[DATA.lats.length - 1]);
const CLS_T = { sendshare: ["% of the max-FCT host's sends on slow links", '% of sends'], trim5: ['trimmed share of packets sent on slow links', '% trimmed'],
  ecn5: ['ECN-marked share of ACKs, slow links', '% of ACKs marked'], trim95: ['trimmed share of packets sent on fast links', '% trimmed'], ecn95: ['ECN-marked share of ACKs, fast links', '% of ACKs marked'] };
function solTraces(abs) {
  if (solOn !== 'on') return [];
  return DATA.sol.map((y, i) => ({ x: DATA.cats, y: DATA.cats.map(() => abs ? y : y - DATA.ref[i]), type: 'scatter', mode: 'lines',
    name: 'speed of light (one dotted line per N)', legendgroup: 'gsol', showlegend: i === 0,
    line: { color: PC.color('n' + DATA.li[i]), width: 1.6, dash: 'dot' }, hovertemplate: 'speed of light ' + y.toFixed(1) + ' us<extra></extra>' }));
}
function drawCls() { PC.fctVsB('cls', (armCls === 'dps' ? DATA.dcls : armCls === 'god' ? DATA.gcls : DATA.cls)[clsM], (armCls === 'dps' ? 'DPS capacity (only B = 8 was run; B is ignored): ' : armCls === 'god' ? 'GOD MODE: ' : '') + CLS_T[clsM][0] + ' vs B, messages 2-4 (' + (armCls === 'dps' ? '3' : '8') + ' seeds, 95% CI)', { ylabel: CLS_T[clsM][1], cats: DATA.cats }); }
const EV_PH = { p: 'post-warmup sends', w: 'warmup sends (message 1)' };
function drawEv() {
  const E = armEv === 'god' ? DATA.geva : DATA.eva, k = DATA.lats.indexOf(Number(evN));
  [['max', 'ev-max', 'max-FCT host'], ['best', 'ev-best', 'best-FCT host']].forEach(r => {
    const mk = (cl, col, nm) => PC.barTrace(col, E[r[0]][evPh][cl][k].rows.map(q => ({ x: q.x, y: q.y, ci: q.ci, n: q.n })), nm);
    const t = PC.theme(); t.barmode = 'group'; t.xaxis.type = 'category'; t.yaxis.title.text = "% of the host's sends"; t.yaxis.range = [0, 100];
    PC.draw(r[1], [mk('bad', 'c3', 'sends on slow links (8 even EVs)'), mk('good', 'c1', 'sends on fast links (8 odd EVs)')], t,
      (armEv === 'god' ? 'GOD MODE: ' : '') + '% of the ' + r[2] + "'s " + EV_PH[evPh] + ' on slow and fast links, N = ' + DATA.Ns[k] + ' (4 seeds, 95% CI)');
  });
}
function drawEvSrc() {
  PC.fctVsB('ev-src', armSrc === 'god' ? DATA.gevs : DATA.evs, (armSrc === 'god' ? 'GOD MODE: ' : '') + "% of the max-FCT host's packets sent with a random EV (rest: EV from the buffer) vs B, messages 2-4, one line per N (4 seeds, 95% CI)",
    { ylabel: '% of sends with a random EV', cats: DATA.cats });
}
function bufOptions() {
  const bs = DATA.bufopt[bufN]; if (!bs.includes(Number(bufB))) bufB = bs[Math.floor(bs.length / 2)];
  document.getElementById('buf-ctl-b').innerHTML = '';
  PC.select('buf-ctl-b', bs.map(b => [String(b), 'B = ' + b]), String(bufB), v => { bufB = v; drawBuf(); });
}
function drawBuf() {
  const E = (armBuf === 'god' ? DATA.gbuf : DATA.buf)[bufH + '|' + bufN + '|' + bufB] || {}, k = DATA.lats.indexOf(Number(bufN));
  const pct = bufU === 's', sc = pct ? 100 / Number(bufB) : 1;   // percent of B: the 16 path bars and the invalid bar add up to 100
  const cats = Array.from({ length: DATA.P }, (_, i) => 'EV ' + i + (' (' + Math.round(DATA.ratios[i] * 100) + '%)')).concat(['Invalid EVs']);
  const traces = ['2', '3', '4'].filter(m => E[m]).map((m, i) => PC.barTrace(['c1', 'c2', 'c3'][i],
    cats.map((c, j) => j === DATA.P ? { x: c, y: E[m].inv * sc, ci: E[m].inv_ci * sc, n: E[m].n } : { x: c, y: E[m].y[j] * sc, ci: E[m].ci[j] * sc, n: E[m].n }),
    'after message ' + m + ': ' + E[m].valid.toFixed(1) + ' of ' + E[m].B + ' slots valid, ' + E[m].inv.toFixed(1) + ' invalid'));
  const t = PC.theme(); t.barmode = 'group'; t.xaxis.type = 'category'; t.yaxis.title.text = pct ? '% of B (all 17 bars add up to 100%)' : 'entries (all 17 bars add up to B)';
  PC.draw('ev-buf', traces, t, (armBuf === 'god' ? 'GOD MODE: ' : '') + 'Buffer after messages 2-4, ' + ({ max: 'max-FCT host', best: 'best-FCT host', all: 'all 16 hosts' })[bufH] + ', N = ' + DATA.Ns[k] + ', B = ' + bufB + ' (4 seeds, 95% CI)');
}
function sentOptions() {
  const bs = DATA.bufopt[sentN]; if (!bs.includes(Number(sentB))) sentB = bs[Math.floor(bs.length / 2)];
  document.getElementById('sent-ctl-b').innerHTML = '';
  PC.select('sent-ctl-b', bs.map(b => [String(b), 'B = ' + b]), String(sentB), v => { sentB = v; drawSent(); });
}
function drawSent() {
  const E = (armSent === 'god' ? DATA.gsent : DATA.sent)[sentH + '|' + sentN + '|' + sentB] || {}, k = DATA.lats.indexOf(Number(sentN));
  const cats = Array.from({ length: DATA.P }, (_, i) => 'EV ' + i + (' (' + Math.round(DATA.ratios[i] * 100) + '%)')), pct = sentU === 's', all = sentC === 'all';
  const traces = ['2', '3', '4'].filter(m => E[m]).map((m, i) => {
    const y = all ? E[m].all : E[m].snd, c = all ? E[m].all_ci : E[m].snd_ci, tot = all ? E[m].tot : E[m].s, sc = pct ? 100 / tot : 1;
    return PC.barTrace(['c1', 'c2', 'c3'][i], cats.map((q, j) => ({ x: q, y: y[j] * sc, ci: c[j] * sc, n: E[m].n })),
      'message ' + m + ': ' + tot.toFixed(1) + (all ? ' packets (' + E[m].s.toFixed(0) + ' sends + ' + E[m].x.toFixed(1) + ' retransmissions)' : ' original sends'));
  });
  const t = PC.theme(); t.barmode = 'group'; t.xaxis.type = 'category'; t.yaxis.title.text = pct ? "% of the message's " + (all ? "transmissions" : "sends") : 'packets sent with the EV';
  PC.draw('ev-sent', traces, t, (armSent === 'god' ? 'GOD MODE: ' : '') + 'Packets sent per EV, messages 2-4, ' + ({ max: 'max-FCT host', best: 'best-FCT host', all: 'all 16 hosts' })[sentH] + ', N = ' + DATA.Ns[k] + ', B = ' + sentB + ' (4 seeds, 95% CI)');
}
function drawWq() {
  document.getElementById('wtbl').innerHTML = '<thead><tr><th>delay per link (us)</th><th>N (peak in flight)</th><th>unloaded BDP (packets)</th><th>N - BDP</th><th>warmup sends, median</th><th>min - max</th><th>warmup / BDP</th><th>first ACK after (us)</th><th>on slow links (%)</th><th>flows</th></tr></thead><tbody>'
    + DATA.warm.map(r => `<tr><td>${r.lat}</td><td>${r.N}</td><td>${r.bdp.toFixed(1)}</td><td>${r.n_minus_bdp.toFixed(1)}</td><td>${r.med}</td><td>${r.lo} - ${r.hi}</td><td>${r.bdp_ratio.toFixed(2)}</td><td>${r.t_ack.toFixed(2)}</td><td>${r.bad.toFixed(1)}</td><td>${r.cells}</td></tr>`).join('') + '</tbody>';
  document.getElementById('qtbl').innerHTML = '<thead><tr><th>delay per link (us)</th><th>max queue, slow links (packets)</th><th>max queue, fast links (packets)</th><th>cells</th></tr></thead><tbody>'
    + DATA.q1.map(r => `<tr><td>${r.lat}</td><td>${r.bad_pk.toFixed(1)}</td><td>${r.good_pk.toFixed(1)}</td><td>${r.cells}</td></tr>`).join('') + '</tbody>';
}
PC.select('sol-ctl', [['on', 'shown (dotted)'], ['off', 'hidden']], solOn, v => { solOn = v; drawFct(); });
if (DATA.dps) PC.select('dps-ctl', [['on', 'on: dashed line with each visible N'], ['off', 'off: no DPS']], dpsOn, v => { dpsOn = v; drawFct(); });
if (DATA.dcmp) PC.select('dpsd-ctl', [['all', 'god and REPS, B = 8 and best B'], ['god', 'god mode only'], ['REPS', 'REPS only']], dpsCmp, v => { dpsCmp = v; drawDpsd(); });
PC.select('cls-ctl', [['sendshare', 'share of sends on slow links'], ['trim5', 'trim rate, slow links'], ['ecn5', 'ECN rate, slow links'], ['trim95', 'trim rate, fast links'], ['ecn95', 'ECN rate, fast links']], clsM, v => { clsM = v; drawCls(); });
PC.select('ev-ctl-ph', [['p', 'post-warmup sends'], ['w', 'warmup sends (message 1)']], evPh, v => { evPh = v; drawEv(); });
PC.select('ev-ctl-n', DATA.lats.map((L, i) => [String(L), 'N = ' + DATA.Ns[i] + ' (' + L / 1000 + ' us)']), evN, v => { evN = v; drawEv(); });
function armCtl() {
  const two = [['reps', 'REPS (uniform random draws)'], ['god', 'god mode (draws weighted by link capacity)']];
  [['arm-ctl', two.concat([['diff', 'REPS minus god (paired, us)']]), arm, v => { arm = v; drawFct(); }],
   ['arm-ctl-c', DATA.dcls ? two.concat([['dps', 'DPS 95/5 (no buffer; B = 8 only, 3 seeds)']]) : two, armCls, v => { armCls = v; drawCls(); }],
   ['arm-ctl-e', two, armEv, v => { armEv = v; drawEv(); }],
   ['arm-ctl-s', two, armSrc, v => { armSrc = v; drawEvSrc(); }],
   ['arm-ctl-b', two, armBuf, v => { armBuf = v; drawBuf(); }],
   ['arm-ctl-x', two, armSent, v => { armSent = v; drawSent(); }]].forEach(c => {
    document.getElementById(c[0]).innerHTML = ''; PC.select(c[0], c[1], c[2], c[3]);
  });
}
armCtl();
PC.select('buf-ctl-h', [['max', 'max-FCT host'], ['best', 'best-FCT host'], ['all', 'all 16 hosts (mean)']], bufH, v => { bufH = v; drawBuf(); });
PC.select('buf-ctl-n', DATA.lats.map((L, i) => [String(L), 'N = ' + DATA.Ns[i] + ' (' + L / 1000 + ' us)']), bufN, v => { bufN = v; bufOptions(); drawBuf(); });
PC.select('buf-ctl-u', [['y', 'entries'], ['s', '% of B (sums to 100%)']], bufU, v => { bufU = v; drawBuf(); });
bufOptions();
PC.select('sent-ctl-h', [['max', 'max-FCT host'], ['best', 'best-FCT host'], ['all', 'all 16 hosts (mean)']], sentH, v => { sentH = v; drawSent(); });
PC.select('sent-ctl-n', DATA.lats.map((L, i) => [String(L), 'N = ' + DATA.Ns[i] + ' (' + L / 1000 + ' us)']), sentN, v => { sentN = v; sentOptions(); drawSent(); });
PC.select('sent-ctl-c', [['all', 'all transmissions (sends + retransmissions)'], ['snd', 'original sends only']], sentC, v => { sentC = v; drawSent(); });
PC.select('sent-ctl-u', [['y', 'packets'], ['s', '% of the message']], sentU, v => { sentU = v; drawSent(); });
sentOptions();
function drawAll() { drawFct(); drawDpsd(); drawRnd(); drawTrm(); drawCls(); drawEv(); drawEvSrc(); drawBuf(); drawSent(); }
drawTable(); drawWq(); drawAll(); PC.onRedraw(drawAll);
"""

if __name__ == "__main__":
    build_page(
        KNEE / "plots" / os.environ.get("K16_OUT", "nsweep.html"),
        title="N sweep, 16 paths",
        eyebrow="meeting 26/10/26 · knee study · dial E · N sweep · 16 paths",
        h1="N sweep on a 16-path fabric (512 hosts)",
        lede="Same experiment as the 8-path N sweep, on a k = 32 fat tree: only the link latency changes N; 16 hosts and 16 uplinks per ToR, SRv6 over 16 paths. Mostly the same as with 8 paths; misses in the result box.",
        cfg="primary metric: max FCT of the 16 degraded sources (messages 2-4) · matched 200G constant-rate sender · ToR0 uplinks graded 5-20 / 80-95% · 512 hosts, 16 paths, tornado, "
            "4 messages x 4 MiB per pair, 1000 us apart (`-connections_mapping`) · delay per link 0.25 to 16 us · freezing, trimming on · needs [FIX: connection-info-cwnd-overflow]",
        full_cmd="run_m4.flags('matched','healthy',B,seed) + -connections_mapping with connection_matrices/knee16/msg_n512_k4_s4M_p1000.cm and topologies/knee16/topo_512_d16_lat{250..16000}.topo "
                 "(knee_16paths_graded/scripts/make_knee16_configs.py, run_knee16.py --bsmap data/bsmap_knee16.json in container dps-dev). Details: knee/README.md, Dial E, N sweep.",
        brief=question("Does the knee of a repeated message move with N when only one parameter, the link latency, changes N?",
                       f"{len(LATS)} link latencies (N = {min(Ns)} to {max(Ns)} packets in flight), 4 messages of 4 MiB per pair, 512 hosts, 16 paths, B from {int(RES.B.min())} to {int(RES.B.max())}, {seeds} seeds.",
                       "Max FCT against B, one line per N, and the knee of messages 2-4 against N and against the fresh EVs carried over."),
        chips=chips, tiles=tiles, body=body, page_js=PAGE_JS,
        payload={"cats": [f"B={b}" for b in sorted({int(r["x"][2:]) for s in series_abs for r in s["rows"]})], "fct": series_abs, "rat": series_rat, "rnd": series_rnd, "trm": series_trm, "kn": kn, "tab": tab, "sol": sol_abs, "ref": refs, "cls": CLS, "eva": EVA, "evs": EVS, "gevs": EVSG, "buf": BUF, "gbuf": BUFGD, "sent": SENT, "gsent": SENTG, "bufopt": BUFOPT, "gfct": series_gabs, "grat": series_grat, "diff": series_diff, "gcls": CLSG, "geva": EVAG, "dps": DPS, "dcmp": DCMP, "dcats": (DCATS if HAS_DPS else None), "dcls": DCLS, "P": Pm.P, "ratios": Pm.RATIOS, "lats": [int(L) for L in LATS], "li": LI, "Ns": [r["N"] for r in tab], "warm": WTAB, "q1": QTAB},
        footer="Source `knee/data/n_results.jsonl`, `n_permessage.csv`, `n_mech.csv`; god arm `n_results_god.jsonl`, `n_permessage_god.csv`, `n_um_god_*.csv`; DPS arm `dps_results.jsonl`, `dps_permessage.csv`, `dps_compare.csv`, `dps_um_*.csv`. "
               "Regenerate: `python3 experiments/meeting_26_11_12/knee_16paths_graded/scripts/build_page_nsweep.py`.")
