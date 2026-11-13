import re, numpy as np, pandas as pd
from pathlib import Path
T = Path(__file__).resolve().parents[1] / "traces"
T975 = {2: 4.303}
def fct(c, B, s):
    v = [float(m.group(2)) for l in open(T / f"{c}_B{B}_s{s}.stdout.txt") for m in [re.search(r"Uec_(\d+)_(\d+) .*?finished at ([\d.]+)", l)] if m and int(m.group(1)) < 32 for m in [re.search(r"Uec_(\d+)_\d+ .*?finished at ([\d.]+)", l)]]
    return np.mean(v)
rows = []
cfgs = ["base_h1024_p32", "lat_u2000", "lat_m2000", "lat_m5000", "lat_m20000", "r010_R200", "r015_R200", "r025_R200", "r035_R200", "r045_R200"]
for c in cfgs:
    Bs = sorted({int(re.search(r"_B(\d+)_s", p.name).group(1)) for p in T.glob(f"{c}_B*_s42.stdout.txt")})
    m = {B: [fct(c, B, s) for s in (42, 43, 44)] for B in Bs}
    ref = m[128]; rm, rci = np.mean(ref), 4.303 * np.std(ref, ddof=1) / np.sqrt(3)
    ok = []
    for B in Bs:
        mm, ci = np.mean(m[B]), 4.303 * np.std(m[B], ddof=1) / np.sqrt(3)
        ok.append(mm <= rm + max(ci, rci, 0.002 * rm))
    knee = next(B for i, B in enumerate(Bs) if all(ok[i:]))
    rows.append(dict(cfg=c, knee_mean_tor0=knee, **{f"B{B}": round(np.mean(m[B]), 2) for B in Bs}))
d = pd.DataFrame(rows); pd.set_option("display.width", 250); print(d.to_string(index=False)); d.to_csv(Path(__file__).parent / "data/tor0_mean_knee.csv", index=False)
