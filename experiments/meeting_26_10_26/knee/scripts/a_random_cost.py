#!/usr/bin/env python3
"""Phase A: cost of extra random draws. Per (config, B, seed, host 0-7): finish time (last ACK), random draws (all / on even=degraded EVs / in the last 10% of sends),
overwrites (clean ACK arriving with the buffer full) and the parity of the evicted EV. Excess is taken against B=128 of the same seed and host.
usage: python a_random_cost.py   -> data/a_hosts.csv, data/a_cells.csv"""
from pathlib import Path
import numpy as np, pandas as pd
EXP = Path(__file__).resolve().parents[2]
SRC = {"r025": [EXP / "../meeting_23_10_26/M4/traces", EXP / "T1/traces"], "r010": [EXP / "T1/traces"], "r005": [EXP / "T1/traces"], "t3r005": [EXP / "T3/traces"]}
PREFIX = {"r025": "matched_nonuniform", "r010": "matched_r010", "r005": "matched_r005", "t3r005": "base_h1024_p32"}
BS = (1, 2, 4, 6, 8, 12, 16, 128)
SEEDS = (42, 43, 44)
OUT = EXP / "knee/data"; OUT.mkdir(exist_ok=True)

def find(cfg, B, s):
    for d in SRC[cfg]:
        p = d / f"{PREFIX[cfg]}_B{B}_s{s}.csv.gz"
        if p.exists(): return p

rows = []
for cfg in SRC:
    for B in BS:
        for s in SEEDS:
            p = find(cfg, B, s)
            if p is None: continue
            x = pd.read_csv(p, usecols=["time_ns", "src_id", "event", "ev", "ev_src", "ecn", "fresh", "head", "slots"])
            x["pfresh"] = x.groupby("src_id")["fresh"].shift(1)
            x["pslots"] = x.groupby("src_id")["slots"].shift(1)
            for h, g in x.groupby("src_id"):
                if h > 7: continue
                snd = g[g.event.isin(["SEND", "RTX", "RTS"])]; ack = g[g.event == "ACK"]
                rnd = snd[snd.ev_src == "random"]
                cut = snd.time_ns.iloc[int(len(snd) * 0.9)]
                clean = ack[(ack.ecn == 0) & (ack.time_ns <= snd.time_ns.max())]  # drop the drain after the last send (flow-tail artefact)
                ow = clean[clean.pfresh >= B]
                ev_par, in_par = [], []
                if B <= 16:
                    for ev_in, hd, ps in zip(ow.ev, ow["head"], ow.pslots):
                        sl = ps.split("|")
                        ev_par.append(int(sl[(hd - 1) % B].split(":")[0]) % 2 == 0)
                        in_par.append(ev_in % 2 == 0)
                rows.append(dict(cfg=cfg, B=B, seed=s, host=h, finish_us=ack.time_ns.max() / 1000, n_send=len(snd),
                                 rnd=len(rnd), rnd_deg=int((rnd.ev % 2 == 0).sum()), rnd_tail=int((rnd.time_ns >= cut).sum()),
                                 rnd_deg_tail=int(((rnd.time_ns >= cut) & (rnd.ev % 2 == 0)).sum()),
                                 clean_acks=len(clean), ow=len(ow), ow_evict_deg=int(sum(ev_par)), ow_in_deg=int(sum(in_par)),
                                 ecn_acks=int((ack.ecn == 1).sum()), deg_sends=int((snd.ev % 2 == 0).sum())))
            print(cfg, B, s, flush=True)
d = pd.DataFrame(rows); d.to_csv(OUT / "a_hosts.csv", index=False)
base = d[d.B == 128].set_index(["cfg", "seed", "host"])
for c in ("finish_us", "rnd", "rnd_deg", "rnd_tail", "rnd_deg_tail"):
    d["d_" + c] = d[c].values - base.loc[list(zip(d.cfg, d.seed, d.host)), c].values
d.to_csv(OUT / "a_hosts.csv", index=False)
g = d.groupby(["cfg", "B"])
cells = g.agg(finish=("finish_us", "mean"), d_finish=("d_finish_us", "mean"), d_rnd=("d_rnd", "mean"), d_rnd_deg=("d_rnd_deg", "mean"),
              d_rnd_deg_tail=("d_rnd_deg_tail", "mean"), ow=("ow", "mean"), ecn_acks=("ecn_acks", "mean"),
              evict_deg=("ow_evict_deg", "sum"), in_deg=("ow_in_deg", "sum"), ow_n=("ow", "sum")).reset_index()
cells["conv"] = cells.d_rnd / cells.ow
cells["frac_deg_of_extra"] = cells.d_rnd_deg / cells.d_rnd
cells["evict_deg_share"] = cells.evict_deg / cells.ow_n
cells["in_deg_share"] = cells.in_deg / cells.ow_n
cells.to_csv(OUT / "a_cells.csv", index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
print(cells.round(3).to_string())
# A3: per-host regression of excess finish on extra degraded random draws
for cfg in SRC:
    for lo in (None,):
        z = d[(d.cfg == cfg) & (d.B < 16)]
        xx, yy = z.d_rnd_deg.values, z.d_finish_us.values
        A = np.vstack([xx, np.ones_like(xx)]).T
        sl, ic = np.linalg.lstsq(A, yy, rcond=None)[0]
        r2 = 1 - ((yy - (sl * xx + ic)) ** 2).sum() / ((yy - yy.mean()) ** 2).sum()
        print(f"A3 {cfg}: n={len(z)} slope={sl:.3f} us per extra degraded random draw, intercept={ic:.2f}, R2={r2:.2f}")
