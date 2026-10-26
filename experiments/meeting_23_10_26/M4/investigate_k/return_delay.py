"""Per-flow return delay (ACK time at sender - sink arrival, matched by seqno=epsn), ACKs per send window, and a generation-only counterfactual (arrival + median return delay).
usage: python return_delay.py prefix ...  (reads C:/tmp/ka/<prefix>.csv.gz and .arr.csv; hosts 0-7, window 100-330 us)"""
import numpy as np, pandas as pd, sys
T0,T1=100e3,330e3  # ns
def run(prefix):
    a=pd.read_csv(f"C:/tmp/ka/{prefix}.arr.csv")
    e=pd.read_csv(f"C:/tmp/ka/{prefix}.csv.gz",usecols=["time_ns","src_id","event","seqno","ev"])
    e=e[e.src_id<8]
    out=[];hist_real=np.zeros(6);hist_cf=np.zeros(6);hist_cf0=np.zeros(6);rows=[]
    for s in range(8):
        arr=a[a.flow_id==s+1].drop_duplicates("epsn").set_index("epsn")
        g=e[e.src_id==s]
        ack=g[g.event=="ACK"].drop_duplicates("seqno").set_index("seqno")
        snd=g[g.event.isin(["SEND","RTX","RTS"])].time_ns.to_numpy()
        j=ack.join(arr[["time_ps","path_id"]],how="inner")
        j["ret"]=j.time_ns-j.time_ps/1e3
        w=(j.time_ns>T0)&(j.time_ns<T1); r=j.ret[w]
        rows.append((s,len(ack),len(j),r.mean(),r.std(),r.median(),np.percentile(r,1),np.percentile(r,99)))
        # real ACKs/window
        ta=np.sort(ack.time_ns.to_numpy()); sw=snd[(snd>T0)&(snd<T1)]
        c=np.diff(np.searchsorted(ta,sw)); hist_real+=np.bincount(np.minimum(c,5),minlength=6)[:6]
        # counterfactual: arrival + median ret (generation only)
        tcf=np.sort(j.time_ps.to_numpy()/1e3+j.ret.median())
        c=np.diff(np.searchsorted(tcf,sw)); hist_cf+=np.bincount(np.minimum(c,5),minlength=6)[:6]
        # raw arrival spacing windows (no shift)
        # path-dependence of ret: variance explained by path_id
        jj=j[w]; gm=jj.groupby("path_id").ret.transform("mean")
        rows[-1]+=(1-((jj.ret-gm)**2).sum()/((jj.ret-jj.ret.mean())**2).sum(),)
    r=pd.DataFrame(rows,columns="flow acks matched ret_mean ret_std ret_med ret_p1 ret_p99 R2_path".split())
    print(prefix); print(r.round(2).to_string(index=False))
    print(" real ACKs/win %:",np.round(hist_real/hist_real.sum()*100,1)); print(" generation-only cf %:",np.round(hist_cf/hist_cf.sum()*100,1))
for p in sys.argv[1:]: run(p)
