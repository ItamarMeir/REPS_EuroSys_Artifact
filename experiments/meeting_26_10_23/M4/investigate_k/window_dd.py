"""Same-window comparison (default 100-330 us, inside every cell's flow, which ends ~356 us at R=400). Per cell, srcs 0-7:
  k_obs      mean k (B=8, valid EVs just before a draw) over draws in the window
  dd_first   B=inf drawdown of M = in-flight + marked ACKs, running max started at the source's first ACK
  dd_win     same, running max restarted at the window start (forgets start-up)
  dd_win_dt  dd_win after removing the linear trend of M fitted inside the window
  slope      fitted slope of M in the window (pkts/us)
  hf         std of M minus its 10 us moving average, inside the window"""
import sys, numpy as np, pandas as pd
T0, T1 = 100.0, 330.0
def cell(path):
    df = pd.read_csv(path, usecols=["time_ns", "src_id", "event", "ecn", "inflight_pkts", "fresh"]); df = df[df.src_id < 8]
    r = []
    for s, g in df.groupby("src_id"):
        t = g.time_ns.to_numpy() / 1e3; ev = g.event.to_numpy(); ack = ev == "ACK"; fr = g.fresh.to_numpy()
        M = g.inflight_pkts.to_numpy(float) + np.cumsum(ack & (g.ecn.to_numpy() > 0)); f = np.argmax(ack)
        draw = np.isin(ev, ["SEND", "RTX", "RTS"]); prev = np.r_[0, fr[:-1]]
        w = (t >= T0) & (t < T1); sel = w & draw
        kobs = prev[sel & (np.arange(len(t)) > f)].mean()
        rm = np.maximum.accumulate(M[f:]); dd_first = (rm - M[f:])[(draw & w)[f:]].mean()
        tw, Mw, dw = t[w], M[w], draw[w]
        dd_win = (np.maximum.accumulate(Mw) - Mw)[dw].mean()
        sl = np.polyfit(tw, Mw, 1)[0]; Md = Mw - sl * tw
        dd_dt = (np.maximum.accumulate(Md) - Md)[dw].mean()
        k = int(round(10 / 0.05)); grid = np.arange(tw[0], tw[-1], 0.05); xi = np.interp(grid, tw, Mw)
        hf = (xi - np.convolve(xi, np.ones(k) / k, mode="same"))[k:-k].std()
        r.append((kobs, dd_first, dd_win, dd_dt, sl, hf))
    return np.mean(r, axis=0)
if __name__ == "__main__":
    print(f"window {T0}-{T1} us   cell            k_obs dd_first dd_win dd_win_dt  slope(pkt/us)  hf")
    for c in sys.argv[1:]:
        lab, p = c.split("=", 1); a = cell(p); print(f"{lab:26s} {a[0]:5.2f} {a[1]:7.2f} {a[2]:6.2f} {a[3]:9.2f} {a[4]:+10.4f} {a[5]:8.2f}")
