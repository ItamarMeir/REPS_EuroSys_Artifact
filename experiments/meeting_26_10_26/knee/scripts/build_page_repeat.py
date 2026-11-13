#!/usr/bin/env python3
"""knee/plots/repeat.html: dial E, repeated messages on one src-dst pair (-connections_mapping), plot_common style (skill interactive-plotter).
Input: data/e_permessage.csv (per message, per B, per seed: max/mean FCT of the 8 degraded sources; from e_permessage.py),
data/e_knees_tol.csv (paired knees, 4 tolerances), data/t1rep_knees_tol.csv, data/t2rep_knees_tol.csv, data/e_results.jsonl (gate).
experiments/**/*.html is gitignored.
    python3 build_page_repeat.py"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
KNEE = HERE.parent
sys.path.insert(0, str(HERE.parents[2] / "tools"))
from plot_common import (aside, build_page, callout, chip, controls, end, h2,  # noqa: E402
                         knee_fct, note, plot, question, table, tile)

D = KNEE / "data"
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306}   # two-sided 95% t by df
PM = pd.read_csv(D / "e_permessage.csv")
PM = PM[PM.cfg.str.contains("msgE_")]
KT = pd.read_csv(D / "e_knees_tol.csv")
RES = pd.DataFrame(map(json.loads, (D / "e_results.jsonl").read_text().splitlines()))

LABEL = {"h128_p8_msgE_base": "baseline (200G, 1 us links, MTU 4150)",
         "h128_p8_msgE_lat2": "links 2 us (RTT x2)",
         "h128_p8_msgE_mtu2075": "MTU 2075 (packets in flight x2)",
         "h128_p8_msgE_R100": "send rate 100G",
         "h128_p8_msgE_R100p250": "send rate 100G, messages 250 us apart",
         "h128_p8_msgE_p60": "baseline, messages 60 us apart"}
SHORT = {"h128_p8_msgE_base": "baseline", "h128_p8_msgE_lat2": "RTT x2", "h128_p8_msgE_mtu2075": "MTU 2075",
         "h128_p8_msgE_R100": "100G", "h128_p8_msgE_R100p250": "100G, 250us gap", "h128_p8_msgE_p60": "60us gap"}
# packets in flight at a message boundary N = send rate x RTT / MTU, counted from the traces (README, Dial E); R100 (messages 100 us apart) overlapped and was replaced by R100p250
INFLIGHT = {"h128_p8_msgE_base": 60, "h128_p8_msgE_p60": 60, "h128_p8_msgE_lat2": 110, "h128_p8_msgE_mtu2075": 113, "h128_p8_msgE_R100p250": 32}
names = [n for n in LABEL if n in set(PM.cfg) and n in INFLIGHT]
names_by_N = sorted(names, key=lambda n: (INFLIGHT[n], n))
CHANGE = {"h128_p8_msgE_base": "baseline", "h128_p8_msgE_p60": "control: baseline, gap 60 us",
          "h128_p8_msgE_lat2": "links 2 us (RTT x2)", "h128_p8_msgE_mtu2075": "MTU 2075", "h128_p8_msgE_R100p250": "send rate 100G"}


def series(df, label, style):
    # per cell (B, seed): mean over the selected messages of the max FCT of the degraded sources; then mean and 95% CI over seeds
    x = df.groupby(["B", "seed"])["max"].mean().reset_index()
    rows = []
    for B, g in x.groupby("B"):
        v = g["max"].to_numpy()
        n = len(v)
        rows.append(dict(B=B, fct_max_mean=v.mean(), fct_max_ci95=T975.get(n - 1, 1.96) * v.std(ddof=1) / np.sqrt(n) if n > 1 else 0.0, n_seeds=n))
    s = pd.DataFrame(rows).sort_values("B")
    return {"label": label, "style": style, "bfct": knee_fct(s), "noBand": False,
            "rows": [{"x": f"B={int(r.B)}", "y": round(r.fct_max_mean, 2), "ci": round(r.fct_max_ci95, 2), "n": int(r.n_seeds)} for r in s.itertuples()]}


fct = {n: {"title": f"{CHANGE[n]}: N = {INFLIGHT[n]} packets in flight", "series": [series(PM[(PM.cfg == n) & (PM.msg == 0)], "message 1 (fresh buffer)", "c1"),
                                         series(PM[(PM.cfg == n) & (PM.msg > 0)], "messages 2-4 (buffer carried over)", "c4")]} for n in names_by_N}

kn = {}
for tol in ("0.2", "1", "2", "5"):
    xs = [f"N={INFLIGHT[n]} ({CHANGE[n]})" for n in names_by_N]
    kn[tol] = {"labels": xs, "N": [INFLIGHT[n] for n in names_by_N]}
    for key, grp in (("first", "message 1 (fresh buffer)"), ("later", "later messages (carried over)")):
        kn[tol][key] = [int(KT[(KT.cfg == n) & (KT.group == grp) & (KT.metric == "max")][f"knee_{tol}pct"].iloc[0]) for n in names_by_N]

long_rows = []
for f, lab in (("t1rep_knees_tol.csv", "T1: 1024 hosts, 16 MiB x 2 messages, 900 us apart"), ("t2rep_knees_tol.csv", "T2: 3-tier pod0, 16 MiB x 2 messages")):
    t = pd.read_csv(D / f)
    for grp in ("message 1 (fresh buffer)", "later messages (carried over)"):
        r = t[(t.group == grp) & (t.metric == "max")].iloc[0]
        long_rows.append({"setup": lab, "group": grp, "ref": float(r.ref_us), "k02": int(r["knee_0.2pct"]), "k1": int(r["knee_1pct"]),
                          "k2": int(r["knee_2pct"]), "k5": int(r["knee_5pct"])})

bad = RES[(RES.rtos > 0) | (RES.freeze_entries > 0)]
base_later = kn["0.2"]["later"][names_by_N.index("h128_p8_msgE_base")]
mtu_later = kn["0.2"]["later"][names_by_N.index("h128_p8_msgE_mtu2075")] if "h128_p8_msgE_mtu2075" in names else None
chips = [chip("ok", f"{len(RES) - len(bad)} of {len(RES)} cells in the plots (0 RTOs, 0 Freezing Mode entries)"),
         chip("warn", f"{len(bad)} cells dropped: they entered Freezing Mode (all MTU 2075)") if len(bad) else chip("ok", "no cell dropped"),
         chip("warn", "128-host setups: 8 seeds; T1 16 MiB: 3 seeds; T2 16 MiB: 5 seeds"),
         chip("warn", "workload change: the dial is the repeated messages, not a network parameter")]
tiles = [tile("later-message knee, baseline", f"B = {base_later}", "message 1 (fresh buffer): 16 (paired, 0.2%)", "bad"),
         tile("MTU 2075 (packets in flight x2)", f"B = {mtu_later}" if mtu_later else "-", "knee follows rate x RTT / MTU"),
         tile("16 MiB flows, T1 / T2", "48 / 96", "at 0.2%; falls to 4 at 5% (cost is 0.5-1.5% of the flow)")]

body = [
    h2("What the experiment does", 1),
    note("Tornado permutation on 128 hosts: host i sends to host i+64, so there are 128 fixed pairs. Each pair carries 4 messages of 1 MiB, started on a clock "
         "(0, 100, 200, 300 us in the baseline; a message takes 52 to 65 us, so the fabric idles between them). The ToR0 uplinks are 5/95, so hosts 0 to 7 are degraded; the plots show their max FCT."),
    note("`-connections_mapping` hands the REPS buffer of a finished message to the next message on the same pair, which then starts with recycled EVs instead of an empty buffer."),
    end(),
    h2("The dial: packets in flight at a message boundary", 2),
    note("The dial is one number, **N = send rate x RTT / MTU**: the packets in flight when a message ends. The next message starts with no returning ACKs for one RTT, "
         "so it can use at most min(B, N) recycled EVs and draws the other N - B at random. The setups below are four ways to change N (RTT, MTU, send rate) and one control (message gap)."),
    controls("kn-ctl", "tolerance"),
    plot("kn"),
    note("Knee = smallest B from which every larger B is within the tolerance of the same seed at the largest B (paired, 8 seeds). Message 1 starts with an empty buffer, so it does not depend on N."),
    callout("Prediction", "Written before the run: the knee of messages 2-4 is near N (about 50 to 60 at baseline) and scales with N when RTT or MTU change (x2) or the rate halves; message 1 stays at 4 to 8; the gap between messages does not matter."),
    callout("Result", f"Held. Knee of messages 2-4 at 0.2%: {', '.join(f'{k} at N={m}' for k, m in zip(kn['0.2']['later'], kn['0.2']['N']))}. "
                      "The 60 us gap leaves it unchanged, and message 1 stays low (4 to 16 depending on the rule)."),
    end(),
    h2("Max FCT against B, per setup", 3),
    controls("fct-ctl", "setup"),
    plot("fct"),
    note("Max FCT of the 8 degraded sources. Ring = knee by the page rule (unpaired, one-sided, 0.2% floor), which can read a grid step or two below the paired knee above."),
    end(),
    h2("Long flows: 16 MiB on T1 and T2", 4, tag="supporting check"),
    callout("Caveat", "On 16 MiB flows the same dial costs only 0.5 to 1.5% of the flow, so the knee depends on the tolerance: it is large at 0.2%, back to 4 at 5%."),
    table("ltbl"),
    end(),
]

PAGE_JS = r"""
let cfg = Object.keys(DATA.fct)[0], tol = '0.2';
function drawFct() {
  const w = DATA.fct[cfg];
  PC.fctVsB('fct', w.series, 'Max FCT of the degraded sources vs B - ' + w.title + ' (8 seeds, 95% CI)');
}
function drawKn() {
  const k = DATA.kn[tol], mk = (vals, label, style) => ({ label, style, bfct: null, noBand: true,
    rows: k.labels.map((l, i) => ({ x: l, y: vals[i], ci: 0, n: 8 })) });
  PC.fctVsB('kn', [mk(k.N, 'packets in flight N = rate x RTT / MTU', 'inf'), mk(k.later, 'knee, messages 2-4 (buffer carried over)', 'c4'),
                   mk(k.first, 'knee, message 1 (fresh buffer)', 'c1')],
    'Knee B_fct vs packets in flight N - tolerance ' + tol + '% (paired, 8 seeds)', { ylabel: 'buffer entries B / packets' });
}
function drawTable() {
  document.getElementById('ltbl').innerHTML = '<thead><tr><th>setup</th><th>messages</th><th>max FCT at B=256 (us)</th>'
    + '<th>knee 0.2%</th><th>1%</th><th>2%</th><th>5%</th></tr></thead><tbody>'
    + DATA.long.map(r => `<tr><td>${r.setup}</td><td>${r.group}</td><td>${r.ref.toFixed(1)}</td><td>${r.k02}</td><td>${r.k1}</td><td>${r.k2}</td><td>${r.k5}</td></tr>`).join('') + '</tbody>';
}
PC.select('fct-ctl', Object.entries(DATA.fct).map(([k, v]) => [k, v.title]), cfg, v => { cfg = v; drawFct(); });
PC.select('kn-ctl', [['0.2', '0.2%'], ['1', '1%'], ['2', '2%'], ['5', '5%']], tol, v => { tol = v; drawKn(); });
function drawAll() { drawFct(); drawKn(); }
drawTable(); drawAll(); PC.onRedraw(drawAll);
"""

if __name__ == "__main__":
    build_page(
        KNEE / "plots" / "repeat.html",
        title="Dial E: repeated messages",
        eyebrow="meeting 26/10/26 · knee study · dial E",
        h1="With repeated messages the knee equals the packets in flight, N = rate x RTT / MTU",
        lede=f"Messages 2-4 start with the buffer of the previous message, and their knee sits at the packets in flight N = send rate x RTT / MTU "
             f"(B = {base_later} at N = 60). Change the rate, the link latency or the MTU and the knee follows N.",
        cfg="primary metric: max FCT of the 8 degraded sources · matched 200G constant-rate sender · ToR0 uplinks 5/95 · 128 hosts, 4 messages of 1 MiB per pair "
            "(`-connections_mapping`) · freezing, trimming on · needs [FIX: connection-info-cwnd-overflow]",
        full_cmd="run_m4.flags('matched','healthy',B,seed) + -connections_mapping with connection_matrices/knee/msg_n128_k4_s1M_p100.cm "
                 "(knee/scripts/make_knee_configs.py, run_knee.py in container m23-dev). Details: knee/README.md, Dial E.",
        brief=question("Can a network or workload setting push the knee above 8 by making the buffer carry state across messages?",
                       "Four messages per src-dst pair share one REPS buffer; vary RTT, MTU, send rate and message spacing, sweep B = 2 to 256, 8 seeds.",
                       "Knee of messages 2-4 against the knee of message 1, and against rate x RTT / MTU."),
        chips=chips, tiles=tiles, body=body, page_js=PAGE_JS,
        payload={"fct": fct, "kn": kn, "long": long_rows},
        footer="Source `knee/data/e_permessage.csv`, `e_knees_tol.csv`, `t1rep_knees_tol.csv`, `t2rep_knees_tol.csv`. "
               "Regenerate: `python3 experiments/meeting_26_10_26/knee/scripts/build_page_repeat.py`.")
