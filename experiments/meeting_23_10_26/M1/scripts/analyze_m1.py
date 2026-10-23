"""M1: NSCC cwnd / ECN / EV-source comparison across fabrics (reads existing traces in place)."""
import gzip, sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
C1 = ROOT / "experiments/meeting_06_10_26/C1"
HERE = Path(__file__).resolve().parents[1]
CELLS = {
    "healthy 400G (NSCC)":           C1 / "NSCC/traces/16MiB_x0_B8.csv.gz",
    "ToR0 x0.5, target 4.17us":      C1 / "NSCC/traces/16MiB_x32_B8.csv.gz",
    "ToR0 x0.5, target 6us":         C1 / "NSCC/_prev_target6us/traces/16MiB_x32_B8.csv.gz",
    "ToR0 x0.5 (MPRDMA)":            C1 / "MPRDMA/traces/16MiB_x32_B8.csv.gz",
    "native 200G fabric+NIC (NSCC)": HERE / "data/n200_t6.csv.gz",
    "ToR0 x0.5, target 3us":         HERE / "data/tgt_3.csv.gz",
    "ToR0 x0.5, target 2us":         HERE / "data/tgt_2.csv.gz",
    "ToR0 x0.5, target 1us":         HERE / "data/tgt_1.csv.gz",
    "ALL ToR uplinks x0.5, 6us":     HERE / "data/all_t6.csv.gz",
    "ALL ToR uplinks x0.5, 4.17us":  HERE / "data/all_t417.csv.gz",
}
rows, series = [], {}
for name, p in CELLS.items():
    if not p.exists():
        print("missing", p); continue
    df = pd.read_csv(p, usecols=["time_ns","src_id","event","ev_src","ecn","cwnd_pkts","inflight_pkts"])
    df = df[df.src_id < 32]                              # ToR0 hosts
    snd = df[df.event == "SEND"]; ack = df[df.event == "ACK"]
    fr = snd.ev_src.value_counts(normalize=True)
    rows.append(dict(cell=name, sends=len(snd), pct_random=100*fr.get("random", 0),
        pct_valid=100*(1-fr.get("random", 0)), ecn_ack_pct=100*(ack.ecn > 0).mean(),
        cwnd_med=ack.cwnd_pkts.median(), cwnd_p10=ack.cwnd_pkts.quantile(.1), cwnd_p90=ack.cwnd_pkts.quantile(.9),
        inflight_med=ack.inflight_pkts.median(), t_end_us=ack.time_ns.max()/1e3))
    a = ack.assign(bin=(ack.time_ns // 25000)).groupby("bin").cwnd_pkts.median()
    series[name] = a
out = pd.DataFrame(rows).round(1)
print(out.to_string(index=False))
out.to_csv(HERE / "data/m1_summary.csv", index=False)
pd.DataFrame(series).to_csv(HERE / "data/m1_cwnd_series_25us.csv")
