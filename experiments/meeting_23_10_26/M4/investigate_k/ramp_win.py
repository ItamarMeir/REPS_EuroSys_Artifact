"""Corrected counterfactual (window 100-330 us, running max restarted at window start): drawdown of M after adding a ramp a*t (pkts/us) or removing the fitted trend.
Earlier ramp_cf.py/drawdown.py used 100-600 us, which includes the flow-end drain (in-flight collapses after ~356 us at R=400) and corrupted the fitted slope."""
import sys, numpy as np, pandas as pd
T0, T1 = 100.0, 330.0
def load(path):
    df = pd.read_csv(path, usecols=["time_ns", "src_id", "event", "ecn", "inflight_pkts"]); df = df[df.src_id < 8]; out = []
    for s, g in df.groupby("src_id"):
        t = g.time_ns.to_numpy() / 1e3; ev = g.event.to_numpy(); M = g.inflight_pkts.to_numpy(float) + np.cumsum((ev == "ACK") & (g.ecn.to_numpy() > 0))
        w = (t >= T0) & (t < T1); out.append((t[w], M[w], np.isin(ev, ["SEND", "RTX", "RTS"])[w]))
    return out
def dd(S, a=0.0, detrend=False):
    r = []
    for t, M, d in S:
        m = M - np.polyfit(t, M, 1)[0] * t if detrend else M + a * t
        r.append((np.maximum.accumulate(m) - m)[d].mean())
    return np.mean(r)
if __name__ == "__main__":
    print(f"{'cell':12s} actual | ramp +0.02 +0.035 +0.05 | detrended")
    for c in sys.argv[1:]:
        lab, p = c.split("=", 1); S = load(p)
        print(f"{lab:12s} {dd(S):5.2f} | " + " ".join(f"{dd(S, a):6.2f}" for a in (0.02, 0.035, 0.05)) + f" | {dd(S, detrend=True):5.2f}")
