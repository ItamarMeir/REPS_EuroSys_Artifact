"""Counterfactual on the drawdown of M(t) = in-flight + marked ACKs (B=inf k): add a linear ramp a*t (pkts/us) to M, or remove the fitted linear trend ('detrend').
Same srcs/windows as drawdown.py (running max from first ACK, drawdown averaged over draws 100-600 us)."""
import sys, numpy as np, pandas as pd
def series(path):
    df = pd.read_csv(path, usecols=["time_ns", "src_id", "event", "ecn", "inflight_pkts"]); df = df[df.src_id < 8]
    out = []
    for s, g in df.groupby("src_id"):
        t = g.time_ns.to_numpy() / 1e3; ev = g.event.to_numpy(); ack = ev == "ACK"
        M = g.inflight_pkts.to_numpy(float) + np.cumsum(ack & (g.ecn.to_numpy() > 0)); f = np.argmax(ack)
        out.append((t[f:], M[f:], np.isin(ev[f:], ["SEND", "RTX", "RTS"])))
    return out
def dd(S, a=0.0, detrend=False):
    r = []
    for t, M, d in S:
        m = M + a * t
        if detrend:
            w = (t >= 100) & (t < 600); sl = np.polyfit(t[w], M[w], 1)[0]; m = M - sl * t
        dm = np.maximum.accumulate(m) - m; sel = d & (t >= 100) & (t < 600); r.append(dm[sel].mean())
    return np.mean(r)
if __name__ == "__main__":
    print(f"{'cell':12s} actual | +0.005/us +0.01 +0.02 +0.04 | detrended")
    for c in sys.argv[1:]:
        lab, p = c.split("=", 1); S = series(p)
        print(f"{lab:12s} {dd(S):5.2f} | " + " ".join(f"{dd(S, a):6.2f}" for a in (0.005, 0.01, 0.02, 0.04)) + f" | {dd(S, detrend=True):5.2f}")
