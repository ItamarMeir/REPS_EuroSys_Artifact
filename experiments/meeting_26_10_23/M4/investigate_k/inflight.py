"""k vs in-flight packets at each draw. With no random draws and no overwrites, valid EVs = (clean ACKs received) - (draws made) + const, i.e.
k = C - inflight, so the spread of k equals the spread of in-flight. Steady state 100-600 us, srcs 0-7, per source then averaged."""
import sys, numpy as np, pandas as pd
def stat(path):
    df = pd.read_csv(path, usecols=["time_ns", "src_id", "event", "fresh", "inflight_pkts"]); df = df[df.src_id < 8]
    g = df.groupby("src_id"); df["pf"] = g.fresh.shift(1).fillna(0)
    d = df[df.event.isin(["SEND", "RTX", "RTS"]) & (df.time_ns >= 100e3) & (df.time_ns < 600e3)]
    r = []
    for s, x in d.groupby("src_id"):
        infl = x.inflight_pkts.to_numpy(float) - 1   # row logged after the send increments it
        r.append((x.pf.mean(), x.pf.std(), infl.mean(), infl.std(), np.corrcoef(x.pf, infl)[0, 1]))
    return np.mean(r, axis=0)
if __name__ == "__main__":
    print(f"{'cell':14s} k_mean k_std  inflight_mean inflight_std  corr(k,inflight)")
    for c in sys.argv[1:]:
        lab, p = c.split("=", 1); a = stat(p); print(f"{lab:14s} {a[0]:.2f}   {a[1]:.2f}   {a[2]:7.1f}      {a[3]:.2f}          {a[4]:+.2f}")
