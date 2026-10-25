"""Per-packet check of the last-hop smoothing: spacing of DATA packet arrivals at the receivers of ToR0's flows (flow ids 1-8, `-log_sink_arrivals`),
steady-state window 100-330 us, vs the spacing of the returning ACKs seen at the senders (event trace of the same flows) and the arrival-time displacement of packets
from their send-order slot (how far each packet arrives from where an evenly spaced stream would put it).
usage: python arrivals.py label=cellprefix ...   (reads C:/tmp/ka/<prefix>.arr.csv and <prefix>.csv.gz)"""
import sys, numpy as np, pandas as pd
T0, T1 = 100e6, 330e6   # ps
def one(prefix):
    a = pd.read_csv(f"C:/tmp/ka/{prefix}.arr.csv"); a = a[(a.time_ps >= T0) & (a.time_ps < T1)]
    cvs, disp, out_of_order = [], [], []
    for fid, g in a.groupby("flow_id"):
        g = g.sort_values("time_ps"); dt = g.time_ps.diff().dropna().to_numpy() / 1e3     # ns
        cvs.append(dt.std() / dt.mean())
        # displacement: arrival time minus the best straight-line fit of arrival time vs sequence number (ns); std = how irregular the stream is
        e = g.sort_values("epsn"); x = e.epsn.to_numpy(float); y = e.time_ps.to_numpy(float) / 1e3
        r = y - np.polyval(np.polyfit(x, y, 1), x); disp.append(r.std())
        out_of_order.append(float((np.diff(g.epsn.to_numpy()) < 0).mean()))
    t = pd.read_csv(f"C:/tmp/ka/{prefix}.csv.gz", usecols=["time_ns", "src_id", "event"])
    k = t[(t.event == "ACK") & (t.src_id < 8) & (t.time_ns >= T0 / 1e3) & (t.time_ns < T1 / 1e3)].sort_values(["src_id", "time_ns"])
    d = k.groupby("src_id").time_ns.diff().dropna().to_numpy()
    return np.mean(cvs), np.mean(disp), np.mean(out_of_order), d.std() / d.mean(), len(a)
if __name__ == "__main__":
    print(f"{'cell':34s} data-arrival CV | arrival jitter about a straight line (ns) | reordered % | ACK-spacing CV at senders | n pkts")
    for c in sys.argv[1:]:
        lab, p = c.rsplit("=", 1); v = one(p)
        print(f"{lab:34s} {v[0]:10.2f}      {v[1]:12.0f}                    {100*v[2]:8.1f}      {v[3]:10.2f}          {v[4]}")
