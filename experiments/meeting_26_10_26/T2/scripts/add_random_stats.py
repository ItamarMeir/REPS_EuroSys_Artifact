#!/usr/bin/env python3
"""Random-draw statistics per cell and per (cfg, B) for T2, added as extra columns to <sub>/data/t2_summary.csv (run AFTER aggregate_t2.py,
which rewrites the summary). usage: python add_random_stats.py tor_agg|agg_core
Per cell (post-warmup draws = SEND/RTX/RTS after the source's first ACK, as run_m4.analyze):
  n_draws_post, n_random_post, n_fresh_pop_post (from results.jsonl), and from the trace: n_random_degraded = random draws whose EV maps to a path
  that crosses a degraded link, pct_random_degraded (of the random draws), pct_send_degraded (new sends on such paths).
Degraded set, not assumed from parity: parsed from the cell's stdout `Failure: <from>-><to>(0) linkspeed set to <Mbps>` lines; a link is slow when
its speed is the lower of the two speeds present (uniform 50/50 and healthy have one speed or none: trace-derived columns are NaN there).
Path structure (fat_tree_topology.cpp get_bidir_paths, 3 tiers, k=8): EV -> path = ev % 16 (SRv6, 16 paths); path p = agg a = p // 4 of the source pod,
uplink l = p % 4, core c = a + 4 l; hops LS<tor>->US<a> (tor = src // 4) and US<a>->CS<c>. A path is degraded if either hop is a slow link.
Validation (printed): the share of new sends on degraded paths computed this way against the queue-based slow_share of the same cell.
Outputs: <sub>/data/t2_random_stats_cells.csv, extra *_mean / *_ci95 columns in <sub>/data/t2_summary.csv."""
import json, re, sys, warnings
from pathlib import Path
import numpy as np, pandas as pd
warnings.simplefilter("ignore")

H = Path(__file__).resolve().parents[1] / sys.argv[1]
P, HOSTS_PER_TOR = 16, 4
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306}


def ci(x):
    x = np.asarray(x, float); x = x[~np.isnan(x)]
    return T975[len(x) - 1] * x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else np.nan


def slow_links(stdout):
    sp = {}
    for ln in stdout.splitlines():
        m = re.match(r"Failure: (\w+)->(\w+)\(\d+\) linkspeed set to (\d+)", ln)
        if m: sp[(m.group(1), m.group(2))] = int(m.group(3))
    if not sp or len(set(sp.values())) < 2: return None
    lo = min(sp.values())
    return {k for k, v in sp.items() if v == lo}


def path_degraded(slow, tor):
    """bool[P]: path p crosses a slow link for a source under ToR `tor` of pod 0."""
    out = np.zeros(P, bool)
    for p in range(P):
        a, l = p // 4, p % 4
        out[p] = (f"LS{tor}", f"US{a}") in slow or (f"US{a}", f"CS{a + 4 * l}") in slow
    return out


def cell_stats(cfg, B, seed):
    name = f"{cfg}_B{B}_s{seed}"
    t, s = H / "traces" / f"{name}.csv.gz", H / "traces" / f"{name}.stdout.txt"
    if not (t.exists() and s.exists()): return {}
    slow = slow_links(s.read_text())
    if slow is None: return {}
    df = pd.read_csv(t, usecols=["src_id", "event", "ev", "ev_src"], dtype={"ev_src": str})
    df["seen_ack"] = df.groupby("src_id").event.transform(lambda v: (v == "ACK").cummax())
    tab = np.vstack([path_degraded(slow, tor) for tor in range(4)])       # [tor, path]; traced sources are hosts 0-15 (pod0)
    post = df[df.event.isin(["SEND", "RTX", "RTS"]) & df.seen_ack]
    rnd = post[post.ev_src == "random"]
    on = tab[(rnd.src_id // HOSTS_PER_TOR).to_numpy(), (rnd.ev % P).to_numpy()]
    new = df[df.event == "SEND"]
    sd = tab[(new.src_id // HOSTS_PER_TOR).to_numpy(), (new.ev % P).to_numpy()]
    return dict(n_random_degraded=int(on.sum()), pct_random_degraded=float(100 * on.mean()) if len(rnd) else np.nan, pct_send_degraded=float(100 * sd.mean()),
                n_degraded_paths=int(tab[0].sum()))


rows = [json.loads(l) for l in (H / "data/results.jsonl").read_text().splitlines()]
out = []
for r in rows:
    out.append(dict(cfg=r["cfg"], shape=r["shape"], B=r["B"], seed=r["seed"], n_draws_post=r["draws_post"], n_random_post=r["n_random_post"],
                    n_fresh_pop_post=r["n_fresh_pop_post"], pct_random=r["pct_random"], **cell_stats(r["cfg"], r["B"], r["seed"])))
cells = pd.DataFrame(out).sort_values(["cfg", "B", "seed"])
cells.to_csv(H / "data/t2_random_stats_cells.csv", index=False)
COLS = ["n_draws_post", "n_random_post", "n_fresh_pop_post", "n_random_degraded", "pct_random_degraded", "pct_send_degraded"]
g = cells.groupby(["cfg", "B"])
add = g[COLS].mean().add_suffix("_mean").join(g[COLS].agg(ci).add_suffix("_ci95")).join(g.n_random_degraded.count().rename("n_seeds_degraded_stat")).reset_index()
summ = pd.read_csv(H / "data/t2_summary.csv")
summ = summ.drop(columns=[c for c in add.columns if c not in ("cfg", "B") and c in summ.columns])
summ = summ.merge(add, on=["cfg", "B"], how="left"); summ.to_csv(H / "data/t2_summary.csv", index=False)
v = summ[summ.pct_send_degraded_mean.notna() & (summ.B == 8)][["cfg", "pct_send_degraded_mean", "slow_share_mean"]]
print("validation, B=8: share of new sends on degraded paths (trace) vs slow_share (queues):"); print(v.round(2).to_string(index=False))
print(summ[summ.B.isin([4, 5, 6, 8]) & (summ["shape"] != "healthy")][["cfg", "B", "pct_random_mean", "n_random_post_mean", "n_random_degraded_mean", "pct_random_degraded_mean"]].round(2).to_string(index=False))
