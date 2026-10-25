"""Same-run, per-flow link between the smoothing and k: for each of the 8 traced flows (ToR0 hosts 0-7, flow id = host + 1) of a cell, the data-arrival
spacing CV at its receiver (`-log_sink_arrivals`) and its own k, drawdown and in-flight fluctuation from the event trace of the SAME simulation (window 100-330 us).
usage: python samerun.py prefix ...  (reads C:/tmp/ka/<prefix>.arr.csv and .csv.gz)  -> per-prefix means and a pooled rank correlation over all flows"""
import sys, numpy as np, pandas as pd
T0, T1 = 100.0, 330.0
def per_flow(prefix):
    a = pd.read_csv(f"C:/tmp/ka/{prefix}.arr.csv"); a = a[(a.time_ps >= T0 * 1e6) & (a.time_ps < T1 * 1e6)]
    df = pd.read_csv(f"C:/tmp/ka/{prefix}.csv.gz", usecols=["time_ns", "src_id", "event", "ecn", "inflight_pkts", "fresh"]); df = df[df.src_id < 8]
    out = []
    for s, g in df.groupby("src_id"):
        gg = a[a.flow_id == s + 1].sort_values("time_ps"); dt = gg.time_ps.diff().dropna().to_numpy()
        cv = dt.std() / dt.mean()
        t = g.time_ns.to_numpy() / 1e3; ev = g.event.to_numpy(); fr = g.fresh.to_numpy(); ack = ev == "ACK"
        M = g.inflight_pkts.to_numpy(float) + np.cumsum(ack & (g.ecn.to_numpy() > 0)); f = np.argmax(ack)
        draw = np.isin(ev, ["SEND", "RTX", "RTS"]); w = (t >= T0) & (t < T1); prev = np.r_[0, fr[:-1]]
        k = prev[draw & w & (np.arange(len(t)) > f)].mean(); dd = (np.maximum.accumulate(M[f:]) - M[f:])[(draw & w)[f:]].mean()
        tw, Mw = t[w], M[w]; kk = 200; grid = np.arange(tw[0], tw[-1], 0.05); xi = np.interp(grid, tw, Mw)
        hf = (xi - np.convolve(xi, np.ones(kk) / kk, mode="same"))[kk:-kk].std()
        out.append((s, cv, hf, dd, k))
    return pd.DataFrame(out, columns=["flow", "arr_cv", "hf", "dd", "k"])
if __name__ == "__main__":
    allr = []
    print(f"{'prefix':22s} arrival-CV   hf    drawdown  k")
    for p in sys.argv[1:]:
        d = per_flow(p); d["cell"] = p; allr.append(d); print(f"{p:22s} {d.arr_cv.mean():8.2f} {d.hf.mean():6.2f} {d.dd.mean():8.2f} {d.k.mean():6.2f}")
    D = pd.concat(allr)
    sp = lambda x, y: x.rank().corr(y.rank())   # Spearman without scipy
    print(f"\npooled over {len(D)} flows in {len(sys.argv)-1} runs: Spearman(arrival CV, in-flight fluctuation hf) = {sp(D.arr_cv, D.hf):+.2f}; "
          f"Spearman(arrival CV, k) = {sp(D.arr_cv, D.k):+.2f}; Spearman(hf, drawdown) = {sp(D.hf, D.dd):+.2f}")
