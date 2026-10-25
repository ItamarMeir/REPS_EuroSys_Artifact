#!/usr/bin/env python3
"""Per-packet RTT and ACK-stream regularity from event traces (steady-state window, ToR0 sources 0-7).
usage: python analyze_rtt.py label=path.csv.gz [label=path ...]   (window 100-300 us, override with --t0/--t1 in us)"""
import argparse, numpy as np, pandas as pd

def stats(path, t0, t1):
    df = pd.read_csv(path, usecols=["time_ns", "src_id", "event", "ev", "seqno", "ecn", "fresh"])
    df = df[df.src_id < 8]
    snd = df[df.event == "SEND"][["src_id", "seqno", "time_ns", "ev"]].rename(columns={"time_ns": "ts"})
    ack = df[df.event == "ACK"][["src_id", "seqno", "time_ns", "ecn"]].rename(columns={"time_ns": "ta"})
    m = ack.merge(snd, on=["src_id", "seqno"])
    m["rtt"] = m.ta - m.ts
    w = m[(m.ta >= t0 * 1e3) & (m.ta < t1 * 1e3)]
    sw = snd[(snd.ts >= t0 * 1e3) & (snd.ts < t1 * 1e3)]
    dt_send = sw.sort_values(["src_id", "ts"]).groupby("src_id").ts.diff().dropna()
    aw = ack[(ack.ta >= t0 * 1e3) & (ack.ta < t1 * 1e3)].sort_values(["src_id", "ta"])
    dt_ack = aw.groupby("src_id").ta.diff().dropna()
    ev_mean = w.groupby(["src_id", "ev"]).rtt.mean()
    # reorder: fraction of ACKs whose seqno is lower than an already-seen ACK of that source
    ro = aw.groupby("src_id").seqno.apply(lambda s: float((s.values < np.maximum.accumulate(s.values)).mean())).mean()
    d = snd_gap = dt_send.mean()
    return dict(send_dt_ns=d, send_cv=dt_send.std() / d, ack_dt_ns=dt_ack.mean(), ack_cv=dt_ack.std() / dt_ack.mean(),
                rtt_mean_us=w.rtt.mean() / 1e3, rtt_std_us=w.rtt.std() / 1e3, rtt_std_in_send_dts=w.rtt.std() / d,
                rtt_p99_us=w.rtt.quantile(.99) / 1e3, ev_mean_rtt_std_us=ev_mean.groupby("src_id").std().mean() / 1e3,
                ack_reorder_frac=ro, n_acks=len(w), ecn_frac=float((w.ecn > 0).mean()))

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("cells", nargs="+"); ap.add_argument("--t0", type=float, default=100); ap.add_argument("--t1", type=float, default=300)
    a = ap.parse_args()
    rows = {}
    for c in a.cells:
        lab, p = c.split("=", 1); rows[lab] = stats(p, a.t0, a.t1)
    print(pd.DataFrame(rows).T.round(3).to_string())
