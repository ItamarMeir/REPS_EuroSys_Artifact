#!/usr/bin/env python3
"""Random-draw statistics per cell and per (fail, B), added as extra columns to data/t1_summary.csv (run AFTER aggregate_t1.py, which
rewrites the summary from scratch). Per cell (post-warmup draws = SEND/RTX/RTS after the source's first ACK, as run_m4.analyze):
  n_draws_post, n_random_post (draws with ev_src == random), n_fresh_pop_post, pct_random (these three come from results.jsonl; M4-reused
  cells included), and from the trace: n_random_degraded = random draws whose EV maps to a degraded uplink, pct_random_degraded (of the
  random draws), pct_send_degraded (all new sends on degraded paths).
Degraded set, not assumed from parity: parsed from the cell's stdout `Failure: LS0->US<a>(0) linkspeed set to <Mbps>` lines; a is degraded when
its speed is the lower of the two speeds present. T1 is 2-tier, 32 paths, EV -> path = ev % 32 = agg index. The parity rule (even = degraded)
is only used as a cross-check (column parity_ok).
The M4-reused cells (r = 0.25 and r = 0.5, B <= 64) read their trace from meeting_23_10_26/M4/traces. Cells without any kept trace, and uniform r = 0.5 (one link speed, no degraded set), have NaN in the degraded columns.
Outputs: data/t1_random_stats_cells.csv (one row per cell), extra columns *_mean / *_ci95 in data/t1_summary.csv."""
import gzip, json, re
from pathlib import Path
import numpy as np, pandas as pd

H = Path(__file__).resolve().parents[1]
M4 = H.parents[1] / "meeting_23_10_26" / "M4"
P = 32
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571}


def ci(x):
    x = np.asarray(x, float); x = x[~np.isnan(x)]
    return T975[len(x) - 1] * x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else np.nan


def degraded_paths(stdout):
    sp = {}
    for ln in stdout.splitlines():
        m = re.match(r"Failure: LS0->US(\d+)\(\d+\) linkspeed set to (\d+)", ln)
        if m: sp[int(m.group(1))] = int(m.group(2))
    if not sp or len(set(sp.values())) < 2: return None
    lo = min(sp.values())
    return np.array([sp.get(a) == lo for a in range(P)])


def cell_stats(fail, B, seed):
    name = f"matched_{fail}_B{B}_s{seed}"
    t, s = H / "traces" / f"{name}.csv.gz", H / "traces" / f"{name}.stdout.txt"
    if not (t.exists() and s.exists()):                       # M4-reused cells: same flags/seeds, traces of hosts 0-7 kept in M4/traces
        t, s = M4 / "traces" / f"{name}.csv.gz", M4 / "traces" / f"{name}.stdout.txt"
    if not (t.exists() and s.exists()): return {}
    deg = degraded_paths(s.read_text())
    if deg is None: return {}
    df = pd.read_csv(t, usecols=["src_id", "event", "ev", "ev_src"], dtype={"ev_src": str})
    df["seen_ack"] = df.groupby("src_id").event.transform(lambda v: (v == "ACK").cummax())
    post = df[df.event.isin(["SEND", "RTX", "RTS"]) & df.seen_ack]
    rnd = post[post.ev_src == "random"]
    on = deg[(rnd.ev % P).to_numpy()]
    new = df[df.event == "SEND"]
    return dict(n_random_degraded=int(on.sum()), pct_random_degraded=float(100 * on.mean()) if len(rnd) else np.nan,
                pct_send_degraded=float(100 * deg[(new.ev % P).to_numpy()].mean()), n_degraded_paths=int(deg.sum()),
                parity_ok=bool((deg == (np.arange(P) % 2 == 0)).all()))


rows = [json.loads(l) for l in (H / "data/results.jsonl").read_text().splitlines()]
m4 = [json.loads(l) for l in (M4 / "data/results.jsonl").read_text().splitlines()]
have = {(r["fail"], r["B"], r["seed"]) for r in rows}
rows += [r for r in m4 if r["rate"] == "matched" and r["fail"] in ("uniform50", "nonuniform") and r["seed"] in (42, 43, 44) and (r["fail"], r["B"], r["seed"]) not in have]
out = []
for r in rows:
    d = dict(fail=r["fail"], B=r["B"], seed=r["seed"], n_draws_post=r["draws_post"], n_random_post=r["n_random_post"], n_fresh_pop_post=r["n_fresh_pop_post"],
             pct_random=r["pct_random"], **cell_stats(r["fail"], r["B"], r["seed"]))
    out.append(d)
cells = pd.DataFrame(out).sort_values(["fail", "B", "seed"])
cells.to_csv(H / "data/t1_random_stats_cells.csv", index=False)
COLS = ["n_draws_post", "n_random_post", "n_fresh_pop_post", "n_random_degraded", "pct_random_degraded", "pct_send_degraded"]
g = cells.groupby(["fail", "B"])
add = g[COLS].mean().add_suffix("_mean").join(g[COLS].agg(ci).add_suffix("_ci95")).join(g.n_random_degraded.count().rename("n_seeds_degraded_stat")).reset_index()
summ = pd.read_csv(H / "data/t1_summary.csv")
summ = summ.drop(columns=[c for c in add.columns if c not in ("fail", "B") and c in summ.columns])   # idempotent
summ.merge(add, on=["fail", "B"], how="left").to_csv(H / "data/t1_summary.csv", index=False)
print(cells[cells.n_random_degraded.notna()].parity_ok.value_counts())
print(add[add.fail.isin(["nonuniform", "r010", "r005", "r001"])][["fail", "B", "n_random_post_mean", "n_random_degraded_mean", "pct_random_degraded_mean", "pct_send_degraded_mean"]].round(2).to_string())
