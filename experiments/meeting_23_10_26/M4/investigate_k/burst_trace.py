"""Trace every ACK that lands inside one send window (between two consecutive draws of a host) and ask how the burst formed.

Per packet (hosts 0-7, matched by seqno = epsn of the sink-arrival log): send time, EV, sink arrival, ACK time at the sender, ECN bit.
  f = sink arrival - send (forward delay), r = ACK time - sink arrival (return delay); queueing = f - min f, r - min r.
Window = interval between consecutive SEND/RTX/RTS events of one host; its ACK count uses the same searchsorted rule as ack_gaps.py.
Spread = max - min of a quantity over the ACKs of the window.

Predictions written BEFORE running (from the user's floor argument and ack_gaps.py):
  P1 Forward side alone cannot fill a window: data leaves ToR->host at >= 83 ns spacing, so a window of W ns holds at most
     floor(W/83)+1 arrivals (3 at R=200, 2 at R=400). A window with >= 4 ACKs therefore needs ACKs whose data reached the receiver
     in different windows, i.e. return-side compression (ack spread << arrival spread).
  P2 Windows with >= 4 ACKs are much more frequent in matched (deg_R200) than in over/healthy (fab400_R400).
  P3 Native 200G (same shaper, similar return jitter) has fewer >= 4 windows than matched: return jitter needs forward clumping to stack on.
  P4 Inside bursts, ACK-ACK gaps are 1.28 ns (400G) or 2.56 ns (200G) where ACKs were serialised back to back.
  P5 Open-loop sends are periodic, so a burst's packets were sent over about n send gaps; the squeeze happens after the send.
  P6 Each of forward-only (constant r) and return-only (constant f) replays caps at 3 ACKs per window; >= 4 needs both (stacking).
  P7 (swap control, added after review; written before running) arrival times from matched + return delays r resampled from native 200G gives 4+ windows
     (about 0.5-1.4%); native arrivals + r resampled from matched gives ~0 (<0.1%); matched arrivals + r permuted within flow stays near the real 1.4%.
     If instead matched arrivals + native r gives ~0, the matched return side matters; the split is a statement about the replay, not a causal proof.
usage: python burst_trace.py swap   -> the P7 recombinations
usage: python burst_trace.py MINACK prefix ... [; python burst_trace.py decomp prefix ...  -> ACKs per window with f and/or r replaced by the per-flow median]
       python burst_trace.py MINACK prefix ...   e.g. python burst_trace.py 4 deg_R200 fab400_R400 nat_R200
       env SHOW=6 prints the per-packet table for windows with >= SHOW ACKs (default 6, at most 3 per cell/seed); SEEDS=42,43,44"""
import os, sys, numpy as np, pandas as pd
T0, T1 = 100e3, 330e3
SEEDS = [int(s) for s in os.environ.get("SEEDS", "42,43,44").split(",")]
SHOW = int(os.environ.get("SHOW", "6"))

def load(prefix, seed):
    a = pd.read_csv(f"C:/tmp/ka/{prefix}_s{seed}.arr.csv")
    e = pd.read_csv(f"C:/tmp/ka/{prefix}_s{seed}.csv.gz", usecols=["time_ns", "src_id", "event", "seqno", "ecn", "ev"]); e = e[e.src_id < 8]
    return a, e

def packets(a, e, s):
    """one row per first-sent, ACKed packet of host s: send, ev, arrival, ack time, ecn, f, r"""
    arr = a[a.flow_id == s + 1].drop_duplicates("epsn").set_index("epsn")
    g = e[e.src_id == s]
    snd = g[g.event == "SEND"].drop_duplicates("seqno").set_index("seqno")[["time_ns", "ev"]].rename(columns={"time_ns": "send", "ev": "ev"})
    ack = g[g.event == "ACK"].drop_duplicates("seqno").set_index("seqno")[["time_ns", "ecn"]].rename(columns={"time_ns": "ack"})
    p = snd.join(ack, how="inner").join(arr[["time_ps", "path_id"]], how="inner")
    p["arr"] = p.time_ps / 1e3; p["f"] = p.arr - p.send; p["r"] = p.ack - p.arr
    draws = g[g.event.isin(["SEND", "RTX", "RTS"])].time_ns.to_numpy()
    return p.sort_values("ack"), np.sort(draws)

def windows(p, draws):
    """list of (window_start, window_end, rows of ACKs inside) for windows starting in [T0,T1)"""
    ta = p.ack.to_numpy(); out = []
    for d0, d1 in zip(draws[:-1], draws[1:]):
        if not (T0 <= d0 < T1): continue
        lo, hi = np.searchsorted(ta, d0), np.searchsorted(ta, d1)
        out.append((d0, d1, p.iloc[lo:hi]))
    return out

def run(prefix, minack):
    allw = []; tabs = []; fmin_path = {}
    for seed in SEEDS:
        a, e = load(prefix, seed)
        P = {s: packets(a, e, s) for s in range(8)}
        fmin = min(P[s][0].f.min() for s in range(8)); rmin = min(P[s][0].r.min() for s in range(8))
        pf = pd.concat([P[s][0] for s in range(8)]); fmin_path[seed] = pf.groupby("path_id").f.min()
        shown = 0
        for s in range(8):
            p, dr = P[s]
            for d0, d1, w in windows(p, dr):
                n = len(w)
                row = dict(seed=seed, host=s, W=d1 - d0, n=n)
                if n >= 2:
                    row.update(send_spread=w.send.max() - w.send.min(), arr_spread=w.arr.max() - w.arr.min(), ack_spread=w.ack.max() - w.ack.min(),
                               inorder=bool((np.diff(w.send.to_numpy()) > 0).all()), arr_order_same=bool((np.diff(w.arr.to_numpy()) >= -1e-6).all()),
                               mean_f_q=(w.f - fmin).mean(), mean_r_q=(w.r - rmin).mean(), r_first=(w.r.iloc[0] - rmin), r_last=(w.r.iloc[-1] - rmin),
                               n_ecn=int((w.ecn > 0).sum()), min_arr_gap=np.diff(np.sort(w.arr.to_numpy())).min(), min_ack_gap=np.diff(w.ack.to_numpy()).min(),
                               n_distinct_arr_windows=len(set(np.searchsorted(dr, w.arr.to_numpy()))))
                allw.append(row)
                if SHOW and n >= SHOW and shown < 3:
                    shown += 1
                    t = w.copy(); t["f_q"] = t.f - fmin; t["r_q"] = t.r - rmin
                    t["send_rel"] = t.send - d0; t["arr_rel"] = t.arr - d0; t["ack_rel"] = t.ack - d0
                    tabs.append(f"--- {prefix} seed {seed} host {s}  window [{d0:.1f},{d1:.1f}] W={d1 - d0:.1f} ns, {n} ACKs (times relative to window start; f_q/r_q = queueing over the cell minimum)\n"
                                + t[["send_rel", "ev", "path_id", "arr_rel", "ack_rel", "f_q", "r_q", "ecn"]].round(2).to_string())
    df = pd.DataFrame(allw); big = df[df.n >= minack]
    print(f"=== {prefix}  hosts 0-7, seeds {SEEDS}, windows {len(df)}")
    cnt = df.n.clip(upper=6).value_counts(normalize=True).sort_index() * 100
    print("  ACKs per window  " + "  ".join(f"{int(k)}{'+' if k == 6 else ''}:{v:.1f}%" for k, v in cnt.items()))
    print("  min f per path_id (spread across paths, ns): " + ", ".join(f"s{sd}: {v.min():.1f}..{v.max():.1f}" for sd, v in fmin_path.items()))
    print(f"  windows with >= {minack} ACKs: {len(big)} ({100 * len(big) / len(df):.2f}%)")
    if len(big):
        print(f"    mean W {big.W.mean():.0f} ns | send spread {big.send_spread.mean():.0f} | arrival spread {big.arr_spread.mean():.0f} | ACK spread {big.ack_spread.mean():.0f} ns")
        print(f"    arrival spread / ACK spread (median) {np.median(big.arr_spread / np.maximum(big.ack_spread, .01)):.1f} ; data arrivals alone could fill at most floor(W/83)+1 = {int(np.floor(big.W.mean() / 83.0)) + 1}")
        print(f"    ACK order = send order {100 * big.inorder.mean():.0f}% | ACK order = arrival order {100 * big.arr_order_same.mean():.0f}% | packets' data landed in >=2 distinct send windows: {100 * (big.n_distinct_arr_windows >= 2).mean():.0f}%")
        print(f"    min arrival gap (median) {big.min_arr_gap.median():.1f} ns | min ACK gap (median) {big.min_ack_gap.median():.2f} ns | share of windows whose min ACK gap < 5 ns {100 * (big.min_ack_gap < 5).mean():.0f}%")
        print(f"    mean forward queueing {big.mean_f_q.mean():.0f} ns | mean return queueing {big.mean_r_q.mean():.0f} ns | r of first ACK {big.r_first.mean():.0f} vs last {big.r_last.mean():.0f} ns | ECN-marked ACKs/window {big.n_ecn.mean():.2f}")
    for t in tabs: print(t)
    return df

def hist(n):
    n = np.minimum(np.array(n), 6); return " ".join(f"{k}{'+' if k == 6 else ''}:{100 * np.mean(n == k):.1f}" for k in range(7))

def decomp(prefix):
    """ACKs per send window with the real timing, forward variation only (r := median), return variation only (f := median), neither"""
    res = {"real": [], "forward only (r const)": [], "return only (f const)": [], "neither": []}
    for seed in SEEDS:
        a, e = load(prefix, seed)
        for s in range(8):
            p, dr = packets(a, e, s); f0 = p.f.median(); r0 = p.r.median()
            for name, ackt in [("real", p.ack), ("forward only (r const)", p.arr + r0), ("return only (f const)", p.send + f0 + p.r), ("neither", p.send + f0 + r0)]:
                ta = np.sort(ackt.to_numpy())
                for d0, d1 in zip(dr[:-1], dr[1:]):
                    if T0 <= d0 < T1: res[name].append(np.searchsorted(ta, d1) - np.searchsorted(ta, d0))
    print(f"== {prefix}  ACKs per send window (%)")
    for k, v in res.items(): print(f"  {k:24s}", hist(v))

def swap():
    """ACKs per send window with arrival times of one cell and return delays r of another (resampled with replacement, pooled over hosts/seeds)"""
    rng = np.random.default_rng(7)
    D = {}
    for prefix in ["deg_R200", "nat_R200", "fab400_R400"]:
        D[prefix] = [(seed, s, *packets(*load(prefix, seed), s)) for seed in SEEDS for s in range(8)]
    pooled = {k: np.concatenate([p.r.to_numpy() for _, _, p, _ in v]) for k, v in D.items()}
    def cnt(arr_cell, r_fn, label):
        out = []
        for seed, s, p, dr in D[arr_cell]:
            ta = np.sort((p.arr.to_numpy() + r_fn(p)))
            out += [np.searchsorted(ta, d1) - np.searchsorted(ta, d0) for d0, d1 in zip(dr[:-1], dr[1:]) if T0 <= d0 < T1]
        o = np.array(out); print(f"  {label:58s} {hist(out)}   4+ windows: {100 * np.mean(o >= 4):.2f}%")
    print("== swap control: ACKs per send window (%), ack = arrival + r")
    cnt("deg_R200", lambda p: p.r.to_numpy(), "matched arrivals + matched r (real)")
    cnt("deg_R200", lambda p: rng.permutation(p.r.to_numpy()), "matched arrivals + matched r permuted within flow")
    cnt("deg_R200", lambda p: rng.choice(pooled["nat_R200"], len(p)), "matched arrivals + native-200G r")
    cnt("deg_R200", lambda p: rng.choice(pooled["fab400_R400"], len(p)), "matched arrivals + over/healthy r")
    cnt("nat_R200", lambda p: p.r.to_numpy(), "native arrivals + native r (real)")
    cnt("nat_R200", lambda p: rng.choice(pooled["deg_R200"], len(p)), "native arrivals + matched r")
    cnt("fab400_R400", lambda p: rng.choice(pooled["deg_R200"], len(p)), "over/healthy arrivals + matched r")

if __name__ == "__main__":
    if sys.argv[1] == "swap": swap()
    elif sys.argv[1] == "decomp":
        for pf in sys.argv[2:]: decomp(pf)
    else:
        minack = int(sys.argv[1])
        for pf in sys.argv[2:]: run(pf, minack)
