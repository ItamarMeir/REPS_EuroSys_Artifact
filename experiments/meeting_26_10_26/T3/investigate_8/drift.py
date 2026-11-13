import sys, numpy as np, pandas as pd
from pathlib import Path
MT = Path(__file__).resolve().parents[2]
def go(path, hosts):
    x = pd.read_csv(path, usecols=["time_ns","src_id","event","ecn","fresh"])
    res=[]
    for src in hosts:
        g=x[x.src_id==src]; s=g[g.event=="SEND"].time_ns.to_numpy(); t0,t1=s.min(),s.max(); lo,hi=t0+.15*(t1-t0),t1-.15*(t1-t0)
        w=g[(g.time_ns>=lo)&(g.time_ns<=hi)]
        ev=w[w.event.isin(["ACK","NACK","SEND","RTX"])]
        clean=((ev.event=="ACK")&(ev.ecn!=1)).astype(int).to_numpy(); snd=(ev.event.isin(["SEND","RTX"])).astype(int).to_numpy()
        step=clean-snd; M=np.cumsum(step); c=M-np.minimum.accumulate(np.minimum(M,0)*0+M)  # height above running min
        n=len(M); tt=ev.time_ns.to_numpy()
        slope=np.polyfit(tt,M,1)[0]*1000   # pkts per us
        res.append((M[-1]-M[0], slope, c.mean(), np.percentile(c,99), M.max()-M.min(), clean.sum()/max(snd.sum(),1)))
    return np.mean(res,axis=0)
for name,p,h in [("T2 a_u50","T2/tor_agg/traces/a_u50_B128_s42.csv.gz",range(16)),("T2 a_r025","T2/tor_agg/traces/a_r025_B128_s42.csv.gz",range(16)),("T2 a_r010","T2/tor_agg/traces/a_r010_B128_s42.csv.gz",range(16)),("T2 a_r005","T2/tor_agg/traces/a_r005_B128_s42.csv.gz",range(16)),("T2 healthy","T2/tor_agg/traces/healthy_B128_s42.csv.gz",range(16))]:
    print(name, "dM, slope(pkt/us), c_mean, c_p99, range(M), cleanACK/sends", np.round(go(MT/p,h),3))
