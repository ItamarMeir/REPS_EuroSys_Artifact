"""Is the per-window ACK count (a_i) independent across windows, or lock-stepped?  k is a running sum of (a_i - 1) (clipped to 0..B),
so cell-to-cell differences in k at the same marginal a_i distribution must come from correlation between consecutive windows.
Reports per-source lag-1 autocorrelation of a_i and the variance of the sum of (a_i-1) over W consecutive windows (W=8,32),
relative to the independent-window value W*Var(a)."""
import sys, numpy as np, pandas as pd
def series(path):
    df = pd.read_csv(path, usecols=["src_id", "event", "time_ns"]); df = df[df.src_id < 8]
    out = {}
    for s, g in df.groupby("src_id"):
        ev = g.event.to_numpy(); t = g.time_ns.to_numpy()
        ack = (ev == "ACK"); cum = np.cumsum(ack); dr = np.isin(ev, ["SEND", "RTX", "RTS"])
        c = cum[dr]; tt = t[dr]; a = np.diff(c)
        m = (c[1:] > 0) & (tt[1:] >= 100e3) & (tt[1:] < 600e3)      # post-warmup steady state, 100-600 us
        out[s] = a[m]
    return out
def summarize(path):
    ac, r8, r32 = [], [], []
    for s, a in series(path).items():
        x = a - 1.0; v = a.var()
        ac.append(np.corrcoef(a[:-1], a[1:])[0, 1])
        for W, lst in ((8, r8), (32, r32)):
            n = len(x) // W; sums = x[:n * W].reshape(n, W).sum(1); lst.append(sums.var() / (W * v))
    return np.mean(ac), np.mean(r8), np.mean(r32)
if __name__ == "__main__":
    print(f"{'cell':14s} lag1_autocorr  var(sum8)/(8var)  var(sum32)/(32var)   [1 = independent windows, <1 = lock-stepped]")
    for c in sys.argv[1:]:
        lab, p = c.split("=", 1); a, b, d = summarize(p); print(f"{lab:14s} {a:+.3f}         {b:.3f}            {d:.3f}")
