"""Per-packet counterfactual replay of k: which part of the delay process makes k wide or tight?

Idea. The constant-rate sender is open-loop: SEND times do not depend on ACKs (k only picks the EV, and path barely moves delay, R^2 ~ 0.03
of return delay on path_id). So every ACK time is send + forward delay + return delay. Hold the send times and the ECN bits fixed, rebuild
ACK times from modified delays, and run the buffer recursion of CircularBufferREPS (clean ACK -> k=min(k+1,B); marked ACK -> unchanged;
draw -> k=max(k-1,0)). k is sampled just before each draw from the host's first ACK on, inside 100-330 us (flow start/drain excluded).

Per packet (ToR0 hosts 0-7, matched by seqno = epsn of the sink-arrival log, `-log_sink_arrivals`):
  f = sink arrival - send time (forward delay), r = ACK time at sender - sink arrival (return delay).
Counterfactuals:
  base      unmodified; must reproduce the traced k (gate).
  constR    r := per-flow median(r)                      (removes ACK pairs / return jitter)
  lpF       f := moving average of f over 10 us of sends (keeps slow wander, removes fast clumping)
  lpF+constR
  detF      f := f - slope_f*(t-100us), slope_f fitted on f(t) in the window     (removes the in-flight trend)
  addF      f := f + c*(t-100us), c = pooled slope_f of over/healthy              (gives matched the over/healthy trend)
  lpF+addF  both
Predictions written BEFORE running (from the existing investigate_k results):
  P1 base reproduces the traced k (mean and k=2 share) in every cell.
  P2 constR changes k mean by < 0.3 in both cells.
  P3 over/healthy detF: k widens toward R=398 (mean 3.4-3.7).
  P4 matched addF: stays wide (>= 3.6), the creep alone does not tighten k.
  P5 matched lpF+addF: tight (<= 2.6). matched lpF alone: between (2.5-3.5).
usage: python replay_pkt_cf.py B label=prefix ...   (reads C:/tmp/ka/<prefix>.csv.gz and .arr.csv)"""
import sys, numpy as np, pandas as pd
T0, T1 = 100e3, 330e3          # ns
import os
LP_NS = float(os.environ.get("LP_US", "10")) * 1e3      # low-pass width for lpF (default 10 us)

def load_flow(a, g, s):
    """returns send times (ns, all draws), ACK arrays: ack_time, seqno, ecn, plus per-ACK f and r (nan if no sink arrival)"""
    arr = a[a.flow_id == s + 1].drop_duplicates("epsn").set_index("epsn").time_ps / 1e3
    draw = g[g.event.isin(["SEND", "RTX", "RTS"])]
    first_send = g[g.event == "SEND"].drop_duplicates("seqno").set_index("seqno").time_ns
    ack = g[g.event == "ACK"]
    st = ack.seqno.map(first_send).to_numpy(float); at = ack.seqno.map(arr).to_numpy(float)
    return dict(draw_t=draw.time_ns.to_numpy(float), ack_t=ack.time_ns.to_numpy(float), ack_ecn=ack.ecn.to_numpy() > 0,
                s_t=st, a_t=at)

def k_series(draw_t, ack_t, ack_ecn, B):
    ev_t = np.r_[ack_t, draw_t]; kind = np.r_[np.zeros(len(ack_t), int), np.ones(len(draw_t), int)]   # ACK before draw on ties
    clean = np.r_[~ack_ecn, np.zeros(len(draw_t), bool)]
    o = np.lexsort((kind, ev_t)); k = 0; seen = False; out = []
    for i in o:
        if kind[i] == 0:
            seen = True
            if clean[i]: k = min(k + 1, B)
        else:
            if seen and T0 <= ev_t[i] < T1: out.append(k)
            k = max(k - 1, 0)
    return out

def lowpass(t, x, w):
    o = np.argsort(t); ts, xs = t[o], x[o]; c = np.r_[0, np.cumsum(xs)]
    lo = np.searchsorted(ts, ts - w / 2); hi = np.searchsorted(ts, ts + w / 2, side="right")
    y = np.empty_like(xs); y[:] = (c[hi] - c[lo]) / (hi - lo); out = np.empty_like(y); out[o] = y; return out

def slope_f(F):
    t = np.concatenate([d["s_t"][m] for d in F for m in [np.isfinite(d["a_t"]) & (d["s_t"] > T0) & (d["s_t"] < T1)]])
    f = np.concatenate([(d["a_t"] - d["s_t"])[m] for d in F for m in [np.isfinite(d["a_t"]) & (d["s_t"] > T0) & (d["s_t"] < T1)]])
    return np.polyfit(t, f, 1)[0]

def cell(prefix, B, c_add):
    a = pd.read_csv(f"C:/tmp/ka/{prefix}.arr.csv")
    e = pd.read_csv(f"C:/tmp/ka/{prefix}.csv.gz", usecols=["time_ns", "src_id", "event", "seqno", "ecn", "fresh"]); e = e[e.src_id < 8]
    F = [load_flow(a, e[e.src_id == s], s) for s in range(8)]
    res = {}
    mods = ["base", "constR", "lpF", "lpF+constR", "detF", "addF", "lpF+addF"]
    sl = slope_f(F)
    for m in mods:
        ks = []
        for d in F:
            ok = np.isfinite(d["a_t"]) & np.isfinite(d["s_t"])
            f = (d["a_t"] - d["s_t"]); r = d["ack_t"] - d["a_t"]; st = d["s_t"]
            f3 = f.copy(); r3 = r.copy()
            if "lpF" in m:
                f3[ok] = lowpass(st[ok], f[ok], LP_NS)
            if "constR" in m:
                r3[ok] = np.median(r[ok])
            if m == "detF":
                f3[ok] = f[ok] - sl * (st[ok] - T0)
            if m == "addF" or m == "lpF+addF":
                f3[ok] = f3[ok] + c_add * (st[ok] - T0)
            new_ack = d["ack_t"].copy(); new_ack[ok] = st[ok] + f3[ok] + r3[ok]
            ks += k_series(d["draw_t"], new_ack, d["ack_ecn"], B)
        ks = np.array(ks); res[m] = (ks.mean(), 100 * (ks == 2).mean())
    traced = []
    for s in range(8):
        g = e[e.src_id == s]; t = g.time_ns.to_numpy(float); ev = g.event.to_numpy(); fr = g.fresh.to_numpy()
        prev = np.r_[0, fr[:-1]]; f0 = np.argmax(ev == "ACK")
        sel = np.isin(ev, ["SEND", "RTX", "RTS"]) & (t >= T0) & (t < T1) & (np.arange(len(t)) > f0); traced += list(prev[sel])
    traced = np.array(traced); res["traced"] = (traced.mean(), 100 * (traced == 2).mean())
    return res, sl

if __name__ == "__main__":
    B = int(sys.argv[1]); cells = [c.split("=", 1) for c in sys.argv[2:]]
    c_add = None
    for lab, p in cells:
        if lab.startswith("over"):
            a = pd.read_csv(f"C:/tmp/ka/{p}.arr.csv")
            e = pd.read_csv(f"C:/tmp/ka/{p}.csv.gz", usecols=["time_ns", "src_id", "event", "seqno", "ecn", "fresh"]); e = e[e.src_id < 8]
            c_add = slope_f([load_flow(a, e[e.src_id == s], s) for s in range(8)]); print(f"over/healthy forward-delay slope c = {c_add:.5f} ns/ns")
    for lab, p in cells:
        r, sl = cell(p, B, c_add if c_add is not None else 0.0)
        print(f"{lab:28s} slope_f={sl:+.5f} | " + " | ".join(f"{m} {v[0]:.2f}/{v[1]:4.1f}%" for m, v in r.items()), flush=True)
