#!/usr/bin/env python3
"""Extra data for plots/nsweep.html (follow-up of 2026-11-04): speed of light, uplink classes (5% vs 95% links), EV distribution of the max-FCT vs best-FCT host, warmup, queue table.
Imported by build_page_nsweep.py. Inputs (data/): n_sol_sim.csv (n_sol.py), n_um_<lat>.csv (n_uplink_mech.py), n_warm_<lat>.csv (n_warmup.py), n_results.jsonl.
SRv6: path j = ToR0 uplink j = EV % 16; even EV = 5% link (20G), odd EV = 95% link (380G)."""
from __future__ import annotations

import glob
from pathlib import Path

import numpy as np
import pandas as pd
import params as Pm

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


def class_series(um, lats, bad, keys, cfg=Pm.CFG_REPS):
    """Per N and B, the max-FCT host of messages 2-4: share of its sends on 5% links, and trim / ECN rates by link class. Per seed (counts summed over the 3 messages), then mean and 95% CI over seeds."""
    out = {m: [] for m in ("sendshare", "trim5", "ecn5", "trim95", "ecn95")}
    for i, L in enumerate(lats):
        g = um[(um.lat == L) & (um.role == "max") & (um.msg >= 2)]
        g = g[[(f"{cfg}_lat{L}", b, s) not in bad for b, s in zip(g.B, g.seed)]]
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


def ev_dist(um, lats, bad, cfg=Pm.CFG_REPS):
    """EV distribution (% of the host's sends per EV 0..7) of the max-FCT and the best-FCT host among hosts 0-7: warmup (message 1, before the first fresh_pop) and post-warmup (rest of message 1 + messages 2-4)."""
    out = {}
    for L in lats:
        g = um[um.lat == L]
        g = g[[(f"{cfg}_lat{L}", b, s) not in bad for b, s in zip(g.B, g.seed)]]
        for B, h in g.groupby("B"):
            ent = {}
            for role in ("max", "best"):
                r = h[h.role == role]
                for ph, sel in (("w", r[r.msg == 1]), ("p", r)):
                    per_seed = []
                    for _, s in sel.groupby("seed"):
                        v = np.array([s[f"hist_{ph}_{e}"].sum() for e in range(Pm.P)], float)
                        if v.sum() > 0:
                            per_seed.append(100 * v / v.sum())
                    if per_seed:
                        a = np.array(per_seed)
                        ent[f"{role}_{ph}"] = {"y": [round(float(x), 2) for x in a.mean(axis=0)], "ci": [round(ci(a[:, e]), 2) for e in range(Pm.P)], "n": len(a),
                                               "bad": round(float(a[:, 0::2].sum(axis=1).mean()), 2), "bad_ci": round(ci(a[:, 0::2].sum(axis=1)), 2)}
            out[f"{L}|{int(B)}"] = ent
    return out


def ev_agg(um, lats, bad, keys, cfg=Pm.CFG_REPS):
    """Share of the sends of the max-FCT and of the best-FCT host that go to the 5% links (even EV) and to the 95% links (odd EV), against B, one series per N.
    Warmup (w) = message 1 before the first fresh_pop; post-warmup (p) = all later sends of messages 1-4. Per seed (counts summed over the messages), then mean and 95% CI over the seeds.
    Result: out[role][phase][cls] = list of series (one per latency), cls in ("bad", "good")."""
    out = {r: {ph: {c: [] for c in ("bad", "good")} for ph in ("w", "p")} for r in ("max", "best")}
    for i, L in enumerate(lats):
        g = um[um.lat == L]
        g = g[[(f"{cfg}_lat{L}", b, s) not in bad for b, s in zip(g.B, g.seed)]]
        rows = {(r, ph, c): [] for r in out for ph in ("w", "p") for c in ("bad", "good")}
        for B, h in g.groupby("B"):
            for role in out:
                r_ = h[h.role == role]
                for ph, sel in (("w", r_[r_.msg == 1]), ("p", r_)):
                    shares = {"bad": [], "good": []}
                    for _, s in sel.groupby("seed"):
                        v = np.array([s[f"hist_{ph}_{e}"].sum() for e in range(Pm.P)], float)
                        if v.sum() > 0:
                            shares["bad"].append(100 * v[0::2].sum() / v.sum())
                            shares["good"].append(100 * v[1::2].sum() / v.sum())
                    for c, x in shares.items():
                        if x:
                            x = np.array(x)
                            rows[(role, ph, c)].append({"x": f"B={int(B)}", "y": round(float(x.mean()), 3), "ci": round(min(ci(x), float(x.mean())), 3), "n": len(x)})
        for (role, ph, c), rr in rows.items():
            out[role][ph][c].append({"label": keys[i][0], "style": keys[i][1], "bfct": None, "noBand": False, "rows": rr})
    return out


def random_share(mh, lats, bad, keys, cfg=Pm.CFG_REPS):
    """% of the ORIGINAL sends (SEND events: 1027 per message) of the max-FCT host of messages 2-4 whose EV was a random draw (ev_src random); the rest came from the buffer (fresh_pop).
    Retransmissions (RTX) are not in the denominator (their count is rtx_all in the same file). Per seed (counts summed over the 3 messages), then mean and 95% CI over the seeds.
    `mh` = n_mech_maxhost*.csv of the arm. One series per latency (= per N) against B."""
    out = []
    for i, L in enumerate(lats):
        g = mh[(mh.cfg == f"{cfg}_lat{L}") & (mh.msg >= 2)]
        g = g[[(f"{cfg}_lat{L}", b, s) not in bad for b, s in zip(g.B, g.seed)]]
        rows = []
        for B, h in g.groupby("B"):
            s = h.groupby("seed")[["rand_all", "sends_all"]].sum()
            x = (100 * s.rand_all / s.sends_all).to_numpy()
            rows.append({"x": f"B={int(B)}", "y": round(float(x.mean()), 3), "ci": round(min(ci(x), float(x.mean())), 3), "n": len(x)})
        out.append({"label": keys[i][0], "style": keys[i][1], "bfct": None, "noBand": False, "rows": rows})
    return out


def buf_dist(bs, um, lats, bad, cfg=Pm.CFG_REPS):
    """Buffer state when messages 2-4 have finished (n_bufstate*.csv: valid slots per path, last event row of each traced flow). Role = the max-FCT / best-FCT host of that message
    (host from n_um) or all 16 hosts (mean over the hosts per seed). Per seed, then mean and 95% CI over the seeds.
    Returns {"<role>|<lat>|<B>": {"<msg>": {"valid", "valid_ci", "B", "y": [16], "ci": [16], "sy": [16] (% of the valid entries), "sci": [16], "n"}}}, msg in 2, 3, 4."""
    P = Pm.P
    out = {}
    for L in lats:
        name = f"{cfg}_lat{L}"
        g = bs[(bs.cfg == name) & (bs.msg >= 2)]
        g = g[[(name, b, s) not in bad for b, s in zip(g.B, g.seed)]]
        u = um[(um.cfg == name) & (um.msg >= 2)]
        for role in ("max", "best", "all"):
            h = g if role == "all" else g.merge(u[u.role == role][["cfg", "B", "seed", "msg", "host"]].drop_duplicates(["cfg", "B", "seed", "msg", "host"]), on=["cfg", "B", "seed", "msg", "host"])
            for B, hb in h.groupby("B"):
                ent = {}
                for msg, hm in hb.groupby("msg"):
                    per = hm.groupby("seed")[[f"p{j}" for j in range(P)] + ["valid", "invalid"]].mean()
                    cnt = per[[f"p{j}" for j in range(P)]].to_numpy()
                    val = per["valid"].to_numpy()
                    inv = per["invalid"].to_numpy()
                    cl = lambda x: round(min(ci(x), float(x.mean())), 4)   # counts are >= 0: the lower whisker is clipped at 0
                    # counts of valid entries per path + invalid = B for every seed; 4 decimals so that the percent of B view (count / B) adds up to 100
                    ent[str(int(msg))] = {"valid": round(float(val.mean()), 4), "valid_ci": cl(val), "B": int(B), "n": int(len(val)), "inv": round(float(inv.mean()), 4), "inv_ci": cl(inv),
                                          "y": [round(float(cnt[:, j].mean()), 4) for j in range(P)], "ci": [cl(cnt[:, j]) for j in range(P)]}
                out[f"{role}|{L}|{int(B)}"] = ent
    return out


def ev_sent(es, um, lats, bad, cfg=Pm.CFG_REPS):
    """Packets sent per EV in messages 2-4 (n_evsends*.csv: SEND and RTX per EV and source, hosts 0-15). Role = the max-FCT / best-FCT host of that message (host from n_um) or all 16 hosts
    (mean over the hosts per seed). Per seed, then mean and 95% CI over the seeds (CI clipped at 0). Two count options: `all` = SEND + RTX, `snd` = original sends only.
    Returns {"<role>|<lat>|<B>": {"<msg>": {"all": [16], "all_ci": [16], "snd": [16], "snd_ci": [16], "n", "tot" (mean SEND + RTX), "s" (mean SEND), "x" (mean RTX)}}}."""
    P = Pm.P
    sr = [f"sr{e}" for e in range(P)]; sf = [f"sf{e}" for e in range(P)]; xr = [f"xr{e}" for e in range(P)]; xf = [f"xf{e}" for e in range(P)]
    out = {}
    for L in lats:
        name = f"{cfg}_lat{L}"
        g = es[(es.cfg == name) & (es.msg >= 2)].copy()
        g = g[[(name, b, s) not in bad for b, s in zip(g.B, g.seed)]]
        S = g[sr].to_numpy() + g[sf].to_numpy(); X = g[xr].to_numpy() + g[xf].to_numpy()
        for e in range(P):
            g[f"n{e}"] = S[:, e]; g[f"t{e}"] = S[:, e] + X[:, e]
        u = um[(um.cfg == name) & (um.msg >= 2)]
        for role in ("max", "best", "all"):
            h = g if role == "all" else g.merge(u[u.role == role][["cfg", "B", "seed", "msg", "host"]].drop_duplicates(["cfg", "B", "seed", "msg", "host"]), on=["cfg", "B", "seed", "msg", "host"])
            for B, hb in h.groupby("B"):
                ent = {}
                for msg, hm in hb.groupby("msg"):
                    per = hm.groupby("seed")[[f"t{e}" for e in range(P)] + [f"n{e}" for e in range(P)]].mean()
                    tt = per[[f"t{e}" for e in range(P)]].to_numpy(); nn = per[[f"n{e}" for e in range(P)]].to_numpy()
                    cl = lambda x: round(min(ci(x), float(x.mean())), 4)   # counts are >= 0
                    ent[str(int(msg))] = {"all": [round(float(tt[:, e].mean()), 4) for e in range(P)], "all_ci": [cl(tt[:, e]) for e in range(P)],
                                          "snd": [round(float(nn[:, e].mean()), 4) for e in range(P)], "snd_ci": [cl(nn[:, e]) for e in range(P)], "n": int(len(tt)),
                                          "tot": round(float(tt.sum(axis=1).mean()), 4), "s": round(float(nn.sum(axis=1).mean()), 4), "x": round(float((tt.sum(axis=1) - nn.sum(axis=1)).mean()), 4)}
                out[f"{role}|{L}|{int(B)}"] = ent
    return out


def warm_table(wm, lats, Ns):
    rows = []
    for L, N in zip(lats, Ns):
        g = wm[wm.lat == L]
        rows.append({"lat": L / 1000, "N": int(N), "med": float(g.n_warm.median()), "lo": int(g.n_warm.min()), "hi": int(g.n_warm.max()),
                     "t_ack": float(((g.t_first_ack - g.t_first_send) / 1000).median()), "bad": float(g.bad_share.mean() * 100), "cells": int(len(g)),
                     "labels_ok": bool((~g.labels.str.contains("explore")).all()), "bdp": Pm.bdp_packets(L), "bdp_ratio": float(g.n_warm.median() / Pm.bdp_packets(L)), "n_minus_bdp": float(N - Pm.bdp_packets(L))})
    return rows


def queue_table(res, lats):
    """max queue (bytes -> packets of 4150 B) observed on the 5% (even) and 95% (odd) ToR0 uplinks per latency, over all cells."""
    rows = []
    for L in lats:
        q = np.array([x for x in res[res.lat == L].uplink_max_q.tolist()], float)
        rows.append({"lat": L / 1000, "bad_pk": float(q[:, 0::2].max() / 4150), "good_pk": float(q[:, 1::2].max() / 4150), "cells": int(len(q))})
    return rows
