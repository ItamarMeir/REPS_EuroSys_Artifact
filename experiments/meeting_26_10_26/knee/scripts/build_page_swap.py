#!/usr/bin/env python3
"""knee/plots/swap.html: dial G, time-varying degradation (-swap_tor_uplinks), in the plot_common style (skill interactive-plotter).
Input: data/g_results.jsonl (T 8..1000, B 2..128, 3 seeds), data/g2_results.jsonl (T 10..24, B 1..128, 5 seeds),
data/g3_control_results.jsonl (path_random control, 5 seeds). experiments/**/*.html is gitignored.
    python3 build_page_swap.py"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
KNEE = HERE.parent
sys.path.insert(0, str(HERE.parents[2] / "tools"))
from plot_common import (aside, build_page, callout, chip, end, h2, note,  # noqa: E402
                         plot, question, table, tile)

D = KNEE / "data"
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306}   # two-sided 95% t, df -> value


def load(f):
    return pd.DataFrame(map(json.loads, (D / f).read_text().splitlines()))


G, G2, CTL = load("g_results.jsonl"), load("g2_results.jsonl"), load("g3_control_results.jsonl")
G["T"] = G.cfg.str.extract(r"swapT(\d+)")[0].astype(int)
G2["T"] = G2.cfg.str.extract(r"swapT(\d+)")[0].astype(int)


def agg(df, by, col="fct_max"):
    out = []
    for k, g in df.groupby(by):
        v = g[col].to_numpy()
        n = len(v)
        ci = float(T975.get(n - 1, 1.96) * v.std(ddof=1) / np.sqrt(n)) if n > 1 else 0.0
        out.append(dict(zip(by, k if isinstance(k, tuple) else (k,)), mean=float(v.mean()), ci=ci, n=n))
    return pd.DataFrame(out)


# a swap period is clean only if every one of its cells has 0 RTOs and 0 Freezing Mode entries
gate = G.groupby("T").agg(cells=("B", "size"), rtos=("rtos", "sum"), frz=("freeze_entries", "sum")).reset_index()
clean_T = set(gate[(gate.rtos == 0) & (gate.frz == 0)]["T"]) | set(G2["T"])
ALL = pd.concat([G2, G[~G["T"].isin(set(G2["T"]))]])
ALL = ALL[ALL["T"].isin(clean_T)]


def rows(df, fmt):
    return [{"x": fmt.format(int(r[df.columns[0]])), "y": round(r["mean"], 2), "ci": round(r.ci, 2), "n": int(r.n)}
            for _, r in df.iterrows()]


a = agg(G2, ["T", "B"])
fct = {"series": [{"label": f"swap every {t} us", "bfct": None,
                   "rows": rows(a[a["T"] == t][["B", "mean", "ci", "n"]].sort_values("B"), "B={}")}
                  for t in (10, 12, 16, 20, 24)]}
b = agg(ALL, ["T", "B"])
per = {"series": []}
for B in (2, 8, 128):
    s = b[b.B == B][["T", "mean", "ci", "n"]].sort_values("T")
    per["series"].append({"label": f"REPS B={B}", "bfct": None, "rows": rows(s, "T={}")})
CTL["T"] = CTL.cfg.str.extract(r"swapT(\d+)")[0]
c = agg(CTL[CTL["T"].notna()].assign(T=lambda d: d["T"].astype(int)), ["T"])
per["series"].append({"label": "no recycling (path_random)", "bfct": None, "rows": rows(c, "T={}")})
static_rand = float(CTL[CTL.cfg.str.contains("static")].fct_max.mean())
r16 = agg(G2[G2["T"] == 16], ["B"], "pct_random")
rnd = {"series": [{"label": "swap every 16 us: random EV draws", "bfct": None, "rows": rows(r16[["B", "mean", "ci", "n"]], "B={}")}]}
gt = [{"T": int(r.T), "cells": int(r.cells), "rtos": int(r.rtos), "frz": int(r.frz), "ok": bool(r.rtos == 0 and r.frz == 0)}
      for r in gate.itertuples()]

b16 = a[a["T"] == 16].set_index("B")["mean"]
d1 = b16[128] - b16[1]
ctl16 = c[c["T"] == 16]["mean"].iloc[0]
chips = [chip("ok", f"{len(ALL)} cells in the plots: 0 RTOs, 0 Freezing Mode entries"),
         chip("bad", "swap periods 60 to 500 us excluded: every one enters Freezing Mode (table)"),
         chip("warn", "T = 8, 30, 1000 us: 3 seeds; T = 10 to 24 us: 5 seeds; control: 5 seeds"),
         chip("warn", "a swap period below ~3.3 us is invalid: the rate is sampled at service start")]
tiles = [tile("max FCT, B=1 vs B=128, T=16 us", f"-{d1:.0f} us", f"{100 * d1 / b16[128]:.1f}% faster with the smallest buffer", "bad"),
         tile("no recycling, T=16 us", f"{ctl16:.0f} us", "random spraying beats every REPS size"),
         tile("static 5/95 for comparison", "708 us", f"REPS B>=8; random spraying {static_rand:.0f} us")]

body = [
    h2("Does a bigger buffer hurt when the slow links keep changing?", 1),
    plot("fct"),
    callout("Prediction", "Written before the run: when the two halves of the ToR0 uplinks trade rates every 1.5 to 3 RTT, a recycled EV "
                          "points at the link that was fast and is now slow, so max FCT rises with B."),
    callout("Result", f"Held. At T = 16 us max FCT is {b16[1]:.0f}, {b16[2]:.0f}, {b16[4]:.0f}, {b16[8]:.0f}, {b16[128]:.0f} us at "
                      f"B = 1, 2, 4, 8, 128: B=1 is {d1:.0f} us ({100 * d1 / b16[128]:.1f}%) faster than B=128. In the static case "
                      "B=1 is 135 us slower."),
    end(),
    h2("Is it the swap, or the recycling?", 2),
    plot("per"),
    note("The control replaces REPS by `-load_balancing_algo path_random` (no recycling). It is faster than every REPS size at "
         "T = 16 and 18 us, so what is slow here is the recycled EV, not the swap."),
    callout("Caveat", "`path_random` picks a full path per packet, so it is 'no recycling', not exactly 'B = 0'. It was run at T = 16 and 18 us only. At T = 1000 us the swap is too slow to matter and REPS behaves as in the static case: B=2 is slower than B=128."),
    end(),
    h2("Random draws do not explain it", 3, tag="supporting check"),
    plot("rnd"),
    note("About 60% of draws are random at every B, yet B=1 is fastest: at this period a random draw is better than a recycled EV."),
    aside("Where the dial stops working",
          "Periods of 60 to 500 us make every REPS cell enter Freezing Mode (a sender waits on the slow half longer than the RTO), "
          "so they are not comparable. At T = 10 us the effect is within noise."),
    end(),
    h2("Gate by swap period", 4, tag="supporting check"),
    table("gtbl"),
    end(),
]

PAGE_JS = r"""
function draw() {
  PC.fctVsB('fct', DATA.fct.series, 'Max FCT vs B - ToR0 uplinks swap rates every T (128 hosts, 5 seeds, 95% CI)');
  PC.fctVsB('per', DATA.per.series, 'Max FCT vs swap period T - REPS B and the no-recycling control (95% CI)');
  PC.fctVsB('rnd', DATA.rnd.series, 'Random EV draws vs B at T = 16 us (5 seeds, 95% CI)', { ylabel: '% random draws' });
}
document.getElementById('gtbl').innerHTML = '<thead><tr><th>T (us)</th><th>cells</th><th>RTOs</th><th>freeze entries</th><th>in the plots</th></tr></thead><tbody>'
  + DATA.gate.map(r => `<tr><td>${r.T}</td><td>${r.cells}</td><td>${r.rtos}</td><td>${r.frz}</td><td>${r.ok ? 'yes' : 'no'}</td></tr>`).join('') + '</tbody>';
draw(); PC.onRedraw(draw);
"""

if __name__ == "__main__":
    build_page(
        KNEE / "plots" / "swap.html",
        title="Dial G: swapping the slow links",
        eyebrow="meeting 26/10/26 · knee study · dial G",
        h1="When the slow links keep swapping, a bigger REPS buffer is slower",
        lede=f"Swapping which ToR0 uplinks are slow every 16 us makes max FCT rise with B: B=1 is {d1:.0f} us ({100 * d1 / b16[128]:.1f}%) "
             "faster than B=128. Random spraying with no recycling is faster than every REPS size.",
        cfg="primary metric: max FCT over all flows · matched 200G constant-rate sender · ToR0 uplinks 5/95, rates swapped every T us "
            "(`-swap_tor_uplinks 0 T 3000`) · 128 hosts, radix 8, tornado 16 MiB · freezing, trimming on",
        full_cmd="run_m4.flags('matched','healthy',B,seed) + ['-swap_tor_uplinks','0',str(T),'3000'] "
                 "(knee/scripts/make_knee_configs.py, run by run_knee.py in container m23-dev). Details: knee/README.md, Dial G.",
        brief=question("Does a larger REPS buffer hurt when the degradation distribution changes over time?",
                       "Swap the service rates of the two halves of the ToR0 uplinks every T us (T = 8 to 1000), sweep B = 1 to 128, "
                       "3 to 5 seeds, plus a no-recycling control.",
                       "Max FCT against B and against T; the random-draw share only as a check."),
        chips=chips, tiles=tiles, body=body, page_js=PAGE_JS,
        payload={"fct": fct, "per": per, "rnd": rnd, "gate": gt},
        footer="Source `knee/data/g_results.jsonl`, `g2_results.jsonl`, `g3_control_results.jsonl`. "
               "Regenerate: `python3 experiments/meeting_26_10_26/knee/scripts/build_page_swap.py`.")
