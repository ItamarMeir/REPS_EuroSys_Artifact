"""Structure function of the in-flight count: std of inflight(t+tau)-inflight(t) per source (draw events, 100-600 us), averaged over srcs 0-7,
plus the std of the 10 us moving-average-removed in-flight. Tells the amplitude of in-flight fluctuations at each time scale."""
import sys, numpy as np, pandas as pd
def sf(path, taus=(0.2, 1, 3, 10, 30, 100)):
    df = pd.read_csv(path, usecols=["time_ns", "src_id", "event", "inflight_pkts"]); df = df[df.src_id < 8]
    d = df[df.event.isin(["SEND", "RTX", "RTS"]) & (df.time_ns >= 100e3) & (df.time_ns < 600e3)]
    out = {tau: [] for tau in taus}; hf = []
    for s, g in d.groupby("src_id"):
        t = g.time_ns.to_numpy() / 1e3; x = g.inflight_pkts.to_numpy(float)
        grid = np.arange(t[0], t[-1], 0.1); xi = np.interp(grid, t, x)
        for tau in taus:
            lag = int(round(tau / 0.1)); out[tau].append((xi[lag:] - xi[:-lag]).std())
        k = int(round(10 / 0.1)); ma = np.convolve(xi, np.ones(k) / k, mode="same"); hf.append((xi - ma)[k:-k].std())
    return [np.mean(out[t]) for t in taus], np.mean(hf)
if __name__ == "__main__":
    print(f"{'cell':14s} " + " ".join(f"d({t}us)" for t in (0.2, 1, 3, 10, 30, 100)) + "  hf-std(10us MA removed)")
    for c in sys.argv[1:]:
        lab, p = c.split("=", 1); v, h = sf(p); print(f"{lab:14s} " + " ".join(f"{x:7.2f}" for x in v) + f"   {h:.2f}")
