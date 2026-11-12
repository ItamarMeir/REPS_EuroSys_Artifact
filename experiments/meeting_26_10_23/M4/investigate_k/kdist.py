"""k and ACKs-per-window distribution of one trace (srcs 0-7, post-warmup draws, same definitions as run_m4.py)."""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "..")
sys.path.insert(0, "../scripts")
from run_m4 import ack_window_stats
def kd(path):
    df = pd.read_csv(path, usecols=["src_id", "event", "fresh"])
    g = df.groupby("src_id"); df["pf"] = g.fresh.shift(1).fillna(0).astype(int)
    df["seen"] = g.event.transform(lambda s: (s == "ACK").cummax())
    d = df[df.event.isin(["SEND", "RTX", "RTS"]) & df.seen]
    k = d.pf.to_numpy(); h = 100 * np.bincount(np.minimum(k, 8), minlength=9) / len(k)
    aw = ack_window_stats(df); a = 100 * np.array(aw["aw_hist"]) / aw["aw_n"]
    return k.mean(), h, a
if __name__ == "__main__":
    for c in sys.argv[1:]:
        lab, p = c.split("=", 1); m, h, a = kd(p)
        print(f"{lab:16s} k_mean={m:.2f} k%[0..8+]=" + " ".join(f"{x:.1f}" for x in h) + "  acks/win%[0..4]=" + " ".join(f"{x:.1f}" for x in a[:5]))
