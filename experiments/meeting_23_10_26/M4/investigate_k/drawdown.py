"""k is a reflected walk; with no upper cap (B=inf) it is exactly the drawdown of M(t) = in-flight + (ECN-marked ACKs so far) from its running maximum,
where the maximum is taken from the source's first ACK. Report, per cell (srcs 0-7, draws 100-600 us): mean drawdown, how late the last new maximum was
set, the in-flight peak reached before 100 us and the mean in-flight afterwards."""
import sys, numpy as np, pandas as pd
def run(path):
    df = pd.read_csv(path, usecols=["time_ns", "src_id", "event", "ecn", "inflight_pkts"]); df = df[df.src_id < 8]
    res = []
    for s, g in df.groupby("src_id"):
        t = g.time_ns.to_numpy() / 1e3; ev = g.event.to_numpy(); infl = g.inflight_pkts.to_numpy(float)
        ack = ev == "ACK"; marked = np.cumsum(ack & (g.ecn.to_numpy() > 0))
        M = infl + marked; first = np.argmax(ack)
        rm = np.maximum.accumulate(M[first:]); dd = rm - M[first:]; tt = t[first:]
        draw = np.isin(ev[first:], ["SEND", "RTX", "RTS"]) & (tt >= 100) & (tt < 600)
        newmax_t = tt[np.r_[True, np.diff(rm) > 0]]
        pre = M[first:][tt < 100]; post = M[first:][(tt >= 100) & (tt < 600)]
        res.append((dd[draw].mean(), newmax_t[newmax_t < 600].max(), pre.max(), post.mean(), np.median(dd[draw])))
    return np.mean(res, axis=0)
if __name__ == "__main__":
    print(f"{'cell':14s} mean_drawdown(B=inf) median  last_new_max_us  M_peak(<100us)  M_mean(100-600us)")
    for c in sys.argv[1:]:
        lab, p = c.split("=", 1); a = run(p); print(f"{lab:14s} {a[0]:10.2f} {a[4]:10.1f} {a[1]:14.0f} {a[2]:14.1f} {a[3]:14.1f}")
