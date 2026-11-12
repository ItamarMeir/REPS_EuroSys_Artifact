"""Summarize run_single.py cells: FCT vs ideal, RTT first/last, in-flight and RTT slope, ECN, rtx, max queue per layer."""
import sys, glob, os, re, numpy as np, pandas as pd
d = sys.argv[1]
rows = []
for gz in sorted(glob.glob(os.path.join(d, "*.csv.gz"))):
    n = os.path.basename(gz)[:-7]; R = int(n.split("_R")[1])
    so = open(os.path.join(d, n + ".stdout.txt")).read()
    fl = [l for l in so.splitlines() if l.startswith("Flow") and " finished at " in l]
    fct = {l.split()[1]: float(l.split(" finished at ")[1].split()[0]) for l in fl}
    ecn = sum(int(l.split()[l.split().index("ecn_acks") + 1]) for l in fl)
    rtx = 0
    df = pd.read_csv(gz, usecols=["time_ns", "src_id", "event", "seqno", "ecn", "inflight_pkts", "ev_src"], dtype={"ev_src": str})
    res = dict(cell=n)
    for s in sorted(df.src_id.unique()):
        x = df[df.src_id == s]
        snd = x[x.event == "SEND"]; ack = x[x.event == "ACK"]
        rtx += int((x.event == "RTX").sum())
        m = snd[["seqno", "time_ns"]].merge(ack[["seqno", "time_ns"]], on="seqno", suffixes=("_s", "_a")); m["rtt"] = (m.time_ns_a - m.time_ns_s) / 1e3
        t0, t1 = 0.25 * m.time_ns_s.max(), 0.85 * m.time_ns_s.max()
        w = m[(m.time_ns_s >= t0) & (m.time_ns_s <= t1)]
        si = snd[(snd.time_ns >= t0) & (snd.time_ns <= t1)]
        res[f"s{s}_npk"] = len(snd); res[f"s{s}_rtt_us"] = round(w.rtt.mean(), 2)
        res[f"s{s}_rtt_slope_ns_per_us"] = round(np.polyfit(w.time_ns_s / 1e3, w.rtt, 1)[0] * 1e3, 2)
        res[f"s{s}_infl_slope"] = round(np.polyfit(si.time_ns / 1e3, si.inflight_pkts, 1)[0], 4)
        res[f"s{s}_rnd%"] = round(100 * (snd.ev_src == "random").mean(), 2)
    npk = res["s0_npk"]
    res["fct_us"] = ",".join(f"{v:.1f}" for v in fct.values())
    res["ideal_us"] = round(npk * 4150 * 8 / (R * 1e3), 1)   # n packets x 4150 B at R, ignoring the final RTT
    res["ecn_acks"] = ecn; res["rtx"] = rtx
    q = pd.read_csv(os.path.join(d, n + ".queues.tsv"), sep="\t")
    for lay in ("E->A", "A->E", "E->H"):
        res["maxq_" + lay] = int(q[q.layer == lay].max_q_total_bytes.max())
    rows.append(res)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
t = pd.DataFrame(rows).set_index("cell")
print(t.drop(columns=[c for c in t.columns if c.startswith("s512")] if "s512_npk" not in t or t["s512_npk"].isna().all() else []).to_string())
