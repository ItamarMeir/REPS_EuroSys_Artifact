#!/usr/bin/env python3
"""DPS arm configs of the 16-path study: one cfg per (distribution, latency), derived from the god cfg (same fabric, workload, degrade file, traced hosts),
never retyped. `dps` = the -dps_dist arguments; the runner (run_knee16_dps.py) swaps the REPS flags for -load_balancing_algo dps -dps_dist <dps>.
DPS has no buffer, so one B value per cell (it is passed as -reps_buffer_size and ignored; kept so the cell is comparable with the B ladder)."""
import json
from pathlib import Path
import params as Pm
HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
DISTS = {                                  # tag -> -dps_dist arguments. Only the 95% / 5% case is run (the mechanism supports any distribution, see DPS_ARCHITECTURE.md)
    "cap": ["capacity"],                   # 95% / 5% on this fabric: the capacity-proportional distribution (god-mode weights, no buffer)
}
B_DPS = 8
base = {c["name"]: c for c in json.loads((DATA / "configs_knee16.json").read_text())}
cfgs, bs = [], {}
for L in Pm.LATS:
    god = base[f"{Pm.CFG_GOD}_lat{L}"]
    extra = god["extra"][:-2]              # drop "-reps_draw_weights capacity"
    assert god["extra"][-2:] == ["-reps_draw_weights", "capacity"]
    for tag, args in DISTS.items():
        name = f"h512_p16_msgNhD{tag}_lat{L}"
        cfgs.append(dict(god, name=name, extra=extra, dps=args))
        bs[name] = [B_DPS]
json.dump(cfgs, open(DATA / "configs_knee16_dps.json", "w"), indent=1)
json.dump(bs, open(DATA / "bsmap_knee16_dps.json", "w"), indent=1)
print(len(cfgs), "DPS configs;", len(DISTS), "distributions x", len(Pm.LATS), "latencies; B =", B_DPS)
