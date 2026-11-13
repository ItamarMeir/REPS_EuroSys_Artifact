#!/usr/bin/env python3
"""Extra data for plots/nsweep.html (follow-up of 2026-11-04): speed of light, uplink classes (5% vs 95% links), EV distribution of the max-FCT vs best-FCT host, warmup, queue table.
Imported by build_page_nsweep.py. Inputs (data/): n_sol_sim.csv (n_sol.py), n_um_<lat>.csv (n_uplink_mech.py), n_warm_<lat>.csv (n_warmup.py), n_results.jsonl.
SRv6: path j = ToR0 uplink j = EV % 8; even EV = 5% link (20G), odd EV = 95% link (380G)."""
from __future__ import annotations

import glob
from pathlib import Path

import numpy as np
import pandas as pd

T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306}


def ci(v):
    v = np.asarray(v, float)
    n = len(v)
    return float(T975.get(n - 1, 1.96) * np.std(v, ddof=1) / np.sqrt(n)) if n > 1 else 0.0


def load(D: Path):
    sol = pd.read_csv(D / "n_sol_sim.csv")
    sol["f"] = sol[["fct1", "fct2", "fct3", "fct4"]].mean(axis=1)
    um = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(str(D / "n_um_[0-9]*.csv")))])
    um["lat"] = um.cfg.str.extract(r"lat(\d+)")[0].astype(int)
    wm = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(str(D / "n_warm_[0-9]*.csv")))])
    wm["lat"] = wm.cfg.str.extract(r"lat(\d+)")[0].astype(int)
    return sol, um, wm


def sol_by_lat(sol):
    return {int(L): float(g.f.mean()) for L, g in sol[sol.variant == "sol"].groupby("lat_ns")}


def class_series(um, lats, bad, keys):
    """Per N and B, the max-FCT host of messages 2-4: share of its sends on 5% links, and trim / ECN rates by link class. Per seed (counts summed over the 3 messages), then mean and 95% CI over seeds."""
    out = {m: [] for m in ("sendshare", "trim5", "ecn5", "trim95", "ecn95")}
    for i, L in enumerate(lats):
        g = um[(um.lat == L) & (um.role == "max") & (um.msg >= 2)]
        g = g[[(f"h128_p8_msgN_lat{L}", b, s) not in bad for b, s in zip(g.B, g.seed)]]
        rows = {m: [] for m in out}
        for B, h in g.groupby("B"):
            s = h.groupby("seed")[[c for c in h.columns if c.startswith(("pb_", "pg_"))]].sum()
            sb = s.pb_r + s.pb_f + s.pb_o
            sg = s.pg_r + s.pg_f + s.pg_o
            v = {"sendshare": 100 * sb / (sb + sg),
                 "trim5": 100 * s.pb_nk / (s.pb_a0 + s.pb_a1 + s.pb_nk).replace(0, np.nan),
                 "ecn5": 100 * s.pb_a1 / (s.pb_a0 + s.pb_a1).replace(0, np.nan),
                 "trim95": 100 * s.pg_nk / (s.pg_a0 + s.pg_a1 + s.pg_nk).replace(0, np.nan),
                 "ecn95": 100 * s.pg_a1 / (s.pg_a0 + s.pg_a1).replace(0, np.nan)}
            for m, x in v.items():
                x = x.dropna().to_numpy()
                if len(x):
                    rows[m].append({"x": f"B={int(B)}", "y": round(float(x.mean()), 3), "ci": round(min(ci(x), float(x.mean())), 3), "n": len(x)})
        for m in out:
            out[m].append({"label": keys[i][0], "style": keys[i][1], "bfct": None, "noBand": False, "rows": rows[m]})
    return out


def ev_dist(um, lats, bad):
    """EV distribution (% of the host's sends per EV 0..7) of the max-FCT and the best-FCT host among hosts 0-7: warmup (message 1, before the first fresh_pop) and post-warmup (rest of message 1 + messages 2-4)."""
    out = {}
    for L in lats:
        g = um[um.lat == L]
        g = g[[(f"h128_p8_msgN_lat{L}", b, s) not in bad for b, s in zip(g.B, g.seed)]]
        for B, h in g.groupby("B"):
            ent = {}
            for role in ("max", "best"):
                r = h[h.role == role]
                for ph, sel in (("w", r[r.msg == 1]), ("p", r)):
                    per_seed = []
                    for _, s in sel.groupby("seed"):
                        v = np.array([s[f"hist_{ph}_{e}"].sum() for e in range(8)], float)
                        if v.sum() > 0:
                            per_seed.append(100 * v / v.sum())
                    if per_seed:
                        a = np.array(per_seed)
                        ent[f"{role}_{ph}"] = {"y": [round(float(x), 2) for x in a.mean(axis=0)], "ci": [round(ci(a[:, e]), 2) for e in range(8)], "n": len(a),
                                               "bad": round(float(a[:, 0::2].sum(axis=1).mean()), 2), "bad_ci": round(ci(a[:, 0::2].sum(axis=1)), 2)}
            out[f"{L}|{int(B)}"] = ent
    return out


def warm_table(wm, lats, Ns):
    rows = []
    for L, N in zip(lats, Ns):
        g = wm[wm.lat == L]
        rows.append({"lat": L / 1000, "N": int(N), "med": float(g.n_warm.median()), "lo": int(g.n_warm.min()), "hi": int(g.n_warm.max()),
                     "t_ack": float(((g.t_first_ack - g.t_first_send) / 1000).median()), "bad": float(g.bad_share.mean() * 100), "cells": int(len(g)),
                     "labels_ok": bool((~g.labels.str.contains("explore")).all()), "bdp_ratio": float(g.n_warm.median() / N)})
    return rows


def queue_table(res, lats):
    """max queue (bytes -> packets of 4150 B) observed on the 5% (even) and 95% (odd) ToR0 uplinks per latency, over all cells."""
    rows = []
    for L in lats:
        q = np.array([x for x in res[res.lat == L].uplink_max_q.tolist()], float)
        rows.append({"lat": L / 1000, "bad_pk": float(q[:, 0::2].max() / 4150), "good_pk": float(q[:, 1::2].max() / 4150), "cells": int(len(q))})
    return rows
