"""ACK-to-ACK gaps at the sender, data-arrival gaps at the receiver, shuffled-return control (independent return jitter) and ACK pair/train sizes.
usage: python ack_gaps.py prefix ...  (reads C:/tmp/ka/<prefix>.csv.gz and .arr.csv; hosts 0-7, window 100-330 us)"""
import numpy as np, pandas as pd, sys
T0,T1=100e3,330e3
rng=np.random.default_rng(1)
def load(prefix):
    a=pd.read_csv(f"C:/tmp/ka/{prefix}.arr.csv")
    e=pd.read_csv(f"C:/tmp/ka/{prefix}.csv.gz",usecols=["time_ns","src_id","event","seqno"]); e=e[e.src_id<8]
    return a,e
def run(prefix):
    a,e=load(prefix)
    gaps=[];hr=np.zeros(6);hs=np.zeros(6);pair_d=[];pair_a=[];dg=[]
    for s in range(8):
        arr=a[a.flow_id==s+1].drop_duplicates("epsn").set_index("epsn")
        g=e[e.src_id==s]; ack=g[g.event=="ACK"].drop_duplicates("seqno").set_index("seqno")
        snd=g[g.event.isin(["SEND","RTX","RTS"])].time_ns.to_numpy(); snd=snd[(snd>T0)&(snd<T1)]
        j=ack.join(arr[["time_ps"]],how="inner"); j["ret"]=j.time_ns-j.time_ps/1e3
        w=(j.time_ns>T0)&(j.time_ns<T1)
        ta=np.sort(j.time_ns[w].to_numpy()); gaps+=list(np.diff(ta))
        hr+=np.bincount(np.minimum(np.diff(np.searchsorted(np.sort(j.time_ns.to_numpy()),snd)),5),minlength=6)[:6]
        # shuffle control: arrival-based gen times + permuted returns
        gen=j.time_ps.to_numpy()/1e3; ret=j.ret.to_numpy()
        ts=np.sort(gen+rng.permutation(ret))
        hs+=np.bincount(np.minimum(np.diff(np.searchsorted(ts,snd)),5),minlength=6)[:6]
        # pair test: consecutive data arrivals (by arrival time) -> gap at receiver vs gap of their ACKs at sender
        jj=j.sort_values("time_ps"); d=np.diff(jj.time_ps.to_numpy())/1e3; aa=np.diff(jj.time_ns.to_numpy())
        m=(jj.time_ns.to_numpy()[1:]>T0)&(jj.time_ns.to_numpy()[1:]<T1)
        pair_d+=list(d[m]); pair_a+=list(aa[m])
    gaps=np.array(gaps);pd_=np.array(pair_d);pa=np.array(pair_a)
    print(prefix)
    print(f" ACK-ACK gap at sender (time order): <5ns {np.mean(gaps<5)*100:.1f}%  <83ns {np.mean(gaps<83)*100:.1f}%  median {np.median(gaps):.0f}ns")
    print(f" data-arrival gap at receiver (consecutive by arrival): <83ns {np.mean(pd_<82)*100:.1f}%  median {np.median(pd_):.0f}ns")
    print(f" corr(data gap, ack gap)={np.corrcoef(pd_,pa)[0,1]:.2f}; pairs whose data gap>=80ns but ack gap<10ns: {np.mean((pd_>=80)&(pa<10))*100:.1f}% ; reordered ACK vs arrival order: {np.mean(pa<0)*100:.1f}%")
    print(" real 0/1/2/3+ %",np.round(100*np.array([hr[0],hr[1],hr[2],hr[3:].sum()])/hr.sum(),1)," shuffled-return 0/1/2/3+ %",np.round(100*np.array([hs[0],hs[1],hs[2],hs[3:].sum()])/hs.sum(),1))
for p in sys.argv[1:]: run(p)
