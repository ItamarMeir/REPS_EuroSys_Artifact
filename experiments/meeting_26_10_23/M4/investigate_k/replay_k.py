"""Counterfactual replay of the buffer-occupancy counter k from the event stream of srcs 0-7 (constant-rate sender: send timing does not depend on k).
Dynamics, as in CircularBufferREPS (no freezing): clean ACK -> k=min(k+1,B); ECN-marked ACK -> k unchanged; draw (SEND/RTX/RTS) -> k=max(k-1,0).
 'replay'   = the actual events (must reproduce the traced k exactly: identity check)
 'nomarks'  = every ECN-marked ACK treated as clean
 'drop p'   = each clean ACK is additionally lost with probability p (extra EV loss at rate p x ACK rate), seed-fixed
usage: python replay_k.py B label=path.csv.gz ...    -> mean k, % at k=2, over post-first-ACK draws"""
import sys, numpy as np, pandas as pd
def replay(path, B=8, mode="replay", p=0.0, seed=1):
    df = pd.read_csv(path, usecols=["src_id", "event", "ecn", "fresh"]); df = df[df.src_id < 8]
    rng = np.random.default_rng(seed); ks = []; chk = 0; n = 0
    for s, g in df.groupby("src_id", sort=True):
        ev = g.event.to_numpy(); ecn = g.ecn.to_numpy(); fr = g.fresh.to_numpy()
        k = 0; seen = False
        u = rng.random(len(ev))
        for i in range(len(ev)):
            e = ev[i]
            if e == "ACK":
                seen = True
                marked = ecn[i] > 0 and mode != "nomarks"
                if not marked and not (mode == "drop" and u[i] < p): k = min(k + 1, B)
            elif e in ("SEND", "RTX", "RTS"):
                if seen: ks.append(k)
                k = max(k - 1, 0)
            if mode == "replay" and e != "ACK" or mode == "replay":
                n += 1; chk += int(k != fr[i]) if e in ("SEND", "RTX", "RTS", "ACK") else 0
    ks = np.array(ks)
    return ks.mean(), 100 * (ks == 2).mean(), chk
if __name__ == "__main__":
    B = int(sys.argv[1])
    for c in sys.argv[2:]:
        lab, p = c.split("=", 1)
        m0, t0, mis = replay(p, B)
        print(f"{lab:26s} replay k={m0:.2f} k2={t0:4.1f}% (mismatch rows vs trace: {mis})", end="")
        m1, t1, _ = replay(p, B, "nomarks"); print(f" | marks->clean k={m1:.2f} k2={t1:4.1f}%", end="")
        for pp in (0.0025, 0.005):
            m2, t2, _ = replay(p, B, "drop", pp); print(f" | +drop {100*pp:.2f}% k={m2:.2f} k2={t2:4.1f}%", end="")
        print(flush=True)
