#!/usr/bin/env python3
"""Random-draw statistics of the host that set the max FCT of each run, and of all 32 ToR0 hosts, per cell.

Input : T1/traces/allhosts/matched_<cfg>_B<B>_s<seed>.csv.gz (-log_reps_events of ALL 32 ToR0 hosts, src_id = host 0..31)
        and the matching .stdout.txt (flow lines, Failure lines).
Output: T1/data/t1_maxhost_stats.csv, one row per cell; columns `max_*` = the max-FCT host, `all_*` = the 32 ToR0 hosts pooled.

Definitions (same as meeting_23_10_26/M4/scripts/run_m4.py analyze and T1/scripts/add_random_stats.py):
  slowest flow = max `finished at` over the 1024 flow lines; its host = `uecSrc` (tornado: source = uecSrc). Ties are listed
    (n_tied) and the lowest host id is used. If that host is not a ToR0 host (id >= 32) it has no trace: max_* is NaN.
  draws post-warmup = SEND/RTX/RTS rows of the host after its first ACK; random = ev_src == random.
  degraded random draws = random draws whose EV maps (ev % 32) to an uplink that the Failure lines set to the lower of the two
    speeds present (NaN for r = 0.5: one speed, no degraded set).
  overwrites = clean (ecn == 0) ACK rows with prev_fresh >= B (buffer full) before the host's last draw (as pct_overwrite in run_m4).
  check_last_ack_us = the host's last ACK row time (us) next to its flow finish time, to confirm the host mapping.
  Paired extra draws: the same host id in the B=128 cell of the SAME seed (all 32 ToR0 hosts are traced there too):
    max_n_random_B128_samehost / max_n_random_degraded_B128_samehost, and max_extra_all_samehost =
    max_n_random - max_n_random_B128_samehost (likewise max_extra_degraded_samehost). The `all_*` pooled columns are
    paired by construction (same 32 hosts at B and at B=128, same seed).

    python3 maxhost_stats.py
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

T1 = Path(__file__).resolve().parents[1]
TR = T1 / "traces" / "allhosts"
OUT = T1 / "data" / "t1_maxhost_stats.csv"
P = 32
FLOW = re.compile(r"Flow Uec_\d+_\d+ flowId \d+ uecSrc (\d+) finished at ([0-9.]+)")


def degraded(stdout: str):
    sp = {}
    for ln in stdout.splitlines():
        m = re.match(r"Failure: LS0->US(\d+)\(\d+\) linkspeed set to (\d+)", ln)
        if m:
            sp[int(m.group(1))] = int(m.group(2))
    if not sp or len(set(sp.values())) < 2:
        return None
    lo = min(sp.values())
    return np.array([sp.get(a) == lo for a in range(P)])


def host_stats(df: pd.DataFrame, hosts, B: int, deg) -> dict:
    d = df[df.src_id.isin(hosts)]
    draws = d[d.event.isin(["SEND", "RTX", "RTS"]) & d.seen_ack]
    rnd = draws[draws.ev_src == "random"]
    last = d[d.event.isin(["SEND", "RTX", "RTS"])].groupby("src_id").n.max()
    ack = d[(d.event == "ACK") & (d.ecn == 0)]
    pre = ack.n < ack.src_id.map(last)
    over = (ack.prev_fresh >= B) & pre
    out = dict(draws_post=len(draws), n_random=len(rnd), pct_random=100 * len(rnd) / max(len(draws), 1),
               overwrites=int(over.sum()), clean_acks_pre=int(pre.sum()), pct_overwrite=100 * over.sum() / max(int(pre.sum()), 1))
    if deg is not None:
        out["n_random_degraded"] = int(deg[(rnd.ev % P).to_numpy()].sum())
    else:
        out["n_random_degraded"] = np.nan
    return out


def main():
    rows = []
    ref128 = {}                      # (fail, seed) -> {host: stats at B=128}, for the same-host pairing
    for tr in sorted(TR.glob("matched_*_B128_s*.csv.gz")):
        m = re.match(r"matched_(.+)_B128_s(\d+)\.csv\.gz", tr.name)
        so = (TR / tr.name.replace(".csv.gz", ".stdout.txt")).read_text()
        df = pd.read_csv(tr, usecols=["n", "time_ns", "src_id", "event", "ev", "ev_src", "ecn", "fresh"], dtype={"ev_src": str})
        df["prev_fresh"] = df.groupby("src_id").fresh.shift(1).fillna(0).astype(int)
        df["seen_ack"] = df.groupby("src_id").event.transform(lambda v: (v == "ACK").cummax())
        deg = degraded(so)
        ref128[(m.group(1), int(m.group(2)))] = {h: host_stats(df, [h], 128, deg) for h in range(P)}
    for tr in sorted(TR.glob("matched_*_B*_s*.csv.gz")):
        m = re.match(r"matched_(.+)_B(\d+)_s(\d+)\.csv\.gz", tr.name)
        fail, B, seed = m.group(1), int(m.group(2)), int(m.group(3))
        so = (TR / tr.name.replace(".csv.gz", ".stdout.txt")).read_text()
        fl = [(float(t), int(h)) for h, t in FLOW.findall(so)]
        tmax = max(t for t, _ in fl)
        tied = sorted({h for t, h in fl if t == tmax})
        host = tied[0]
        df = pd.read_csv(tr, usecols=["n", "time_ns", "src_id", "event", "ev", "ev_src", "ecn", "fresh"], dtype={"ev_src": str})
        df["prev_fresh"] = df.groupby("src_id").fresh.shift(1).fillna(0).astype(int)
        df["seen_ack"] = df.groupby("src_id").event.transform(lambda v: (v == "ACK").cummax())
        deg = degraded(so)
        row = dict(fail=fail, B=B, seed=seed, max_host=host, max_fct=tmax, n_tied=len(tied), n_flows=len(fl),
                   max_host_in_trace=host < P)
        if host < P:
            ack_t = df[(df.src_id == host) & (df.event == "ACK")].time_ns.max() / 1000.0
            row["check_last_ack_us"] = round(float(ack_t), 3)
            row.update({f"max_{k}": v for k, v in host_stats(df, [host], B, deg).items()})
            r0 = ref128[(fail, seed)][host]
            row["max_n_random_B128_samehost"] = r0["n_random"]
            row["max_n_random_degraded_B128_samehost"] = r0["n_random_degraded"]
            row["max_extra_all_samehost"] = row["max_n_random"] - r0["n_random"]
            row["max_extra_degraded_samehost"] = row["max_n_random_degraded"] - r0["n_random_degraded"]
        row.update({f"all_{k}": v for k, v in host_stats(df, list(range(P)), B, deg).items()})
        rows.append(row)
        print(fail, B, seed, "host", host, "tied", len(tied), f"fct {tmax}", row.get("check_last_ack_us"), flush=True)
    pd.DataFrame(rows).to_csv(OUT, index=False)
    print("wrote", OUT, len(rows))


if __name__ == "__main__":
    main()
