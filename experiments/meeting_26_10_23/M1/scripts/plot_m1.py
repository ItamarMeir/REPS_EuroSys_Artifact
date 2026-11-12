import pandas as pd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
H = Path(__file__).resolve().parents[1]
s = pd.read_csv(H/"data/m1_summary.csv").set_index("cell")
ser = pd.read_csv(H/"data/m1_cwnd_series_25us.csv", index_col=0)
fig, ax = plt.subplots(1, 2, figsize=(12, 4.2))
for c in ["healthy 400G (NSCC)", "ToR0 x0.5, target 4.17us", "ToR0 x0.5 (MPRDMA)", "ALL ToR uplinks x0.5, 4.17us", "native 200G fabric+NIC (NSCC)"]:
    ax[0].plot(ser.index*25, ser[c], label=c)
ax[0].axhline(56, ls=":", c="k"); ax[0].text(5, 58, "degraded knee 56 pkts", fontsize=8)
ax[0].set_xlabel("time (us)"); ax[0].set_ylabel("median cwnd of ToR0 hosts (pkts)"); ax[0].legend(fontsize=7)
t = [("1us","ToR0 x0.5, target 1us"),("2us","ToR0 x0.5, target 2us"),("3us","ToR0 x0.5, target 3us"),("4.17us","ToR0 x0.5, target 4.17us"),("6us","ToR0 x0.5, target 6us")]
ax[1].plot([a for a,_ in t], [s.loc[c,"ecn_ack_pct"] for _,c in t], "o-", label="% ACKs ECN-marked")
ax[1].plot([a for a,_ in t], [s.loc[c,"pct_random"] for _,c in t], "s-", label="% sends with random EV")
ax[1].axhline(s.loc["healthy 400G (NSCC)","pct_random"], ls=":", c="g", label="healthy random %")
ax[1].set_xlabel("NSCC target_q_delay"); ax[1].legend(fontsize=8); ax[1].set_title("ToR0 uplinks x0.5, NSCC, B=8")
fig.tight_layout(); fig.savefig(H/"plots/m1_cwnd_and_target.png", dpi=130)
