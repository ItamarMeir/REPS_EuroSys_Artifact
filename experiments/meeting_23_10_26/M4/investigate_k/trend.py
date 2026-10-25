"""Is the queue stationary? Per source, steady-state 100-600 us: slope of in-flight and of per-packet RTT vs time, random draws and k_mean in 100 us bins."""
import sys, numpy as np, pandas as pd
def run(path):
    df = pd.read_csv(path, usecols=["time_ns", "src_id", "event", "ev_src", "seqno", "fresh", "inflight_pkts"]); df = df[df.src_id < 8]
    g = df.groupby("src_id"); df["pf"] = g.fresh.shift(1).fillna(0)
    df["seen"] = g.event.transform(lambda s: (s == "ACK").cummax())
    d = df[df.event.isin(["SEND", "RTX", "RTS"]) & df.seen & (df.time_ns >= 100e3) & (df.time_ns < 600e3)].copy()
    d["bin"] = ((d.time_ns - 100e3) // 100e3).astype(int)
    d["infl"] = d.inflight_pkts - 1; d["rnd"] = (d.ev_src == "random")
    snd = df[df.event == "SEND"][["src_id", "seqno", "time_ns"]].rename(columns={"time_ns": "ts"})
    ack = df[df.event == "ACK"][["src_id", "seqno", "time_ns"]].rename(columns={"time_ns": "ta"})
    m = snd.merge(ack, on=["src_id", "seqno"]); m["rtt"] = (m.ta - m.ts) / 1e3
    m = m[(m.ts >= 100e3) & (m.ts < 600e3)]
    slope = lambda t, y: np.polyfit(t / 1e3, y, 1)[0]
    sl_i = np.mean([slope(x.time_ns.to_numpy(), x.infl.to_numpy()) for _, x in d.groupby("src_id")])
    sl_r = np.mean([slope(x.ts.to_numpy(), x.rtt.to_numpy()) for _, x in m.groupby("src_id")])
    b = d.groupby("bin").agg(k=("pf", "mean"), infl=("infl", "mean"), rnd=("rnd", "mean"))
    return sl_i, sl_r, b
if __name__ == "__main__":
    for c in sys.argv[1:]:
        lab, p = c.split("=", 1); si, sr, b = run(p)
        print(f"{lab:12s} d(inflight)/dt={si:+.4f} pkts/us  d(RTT)/dt={sr*1e3:+.2f} ns/us | per-100us bins: k=" + " ".join(f"{x:.2f}" for x in b.k) +
              " | inflight=" + " ".join(f"{x:.1f}" for x in b.infl) + " | random%=" + " ".join(f"{100*x:.2f}" for x in b.rnd))
