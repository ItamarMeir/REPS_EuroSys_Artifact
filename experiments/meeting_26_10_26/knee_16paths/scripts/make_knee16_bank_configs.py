#!/usr/bin/env python3
"""REPS-Bank arm configs of the 16-path 5/95 study: one cfg per (target arm, latency), derived from the REPS cfg (same fabric, workload, degrade file, traced hosts), never retyped.
Bank: size 8, valid timer = 1 minRTT = the unloaded RTT of that latency (0.337 + 8 x link delay us, printed by the sim as network_max_unloaded_rtt), REPS buffer B = 8.
Target arms: `auto` = flag omitted (NSCC base_rtt + target_Qdelay = unloaded RTT + 6 us); `tight` = unloaded RTT + TIGHT_OFFSET_US (set from the pilot: fast-path raw-RTT floor offset + 1.0 us).
usage: python make_knee16_bank_configs.py [tight_offset_us]"""
import json, sys
from pathlib import Path
import params as Pm
HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
TIGHT_OFFSET_US = float(sys.argv[1]) if len(sys.argv) > 1 else None
B_BANK, SIZE = 8, 8
base = {c["name"]: c for c in json.loads((DATA / "configs_knee16.json").read_text())}
cfgs, bs = [], {}
arms = {"auto": None}
if TIGHT_OFFSET_US is not None: arms["tight"] = TIGHT_OFFSET_US
for L in Pm.LATS:
    reps = base[f"{Pm.CFG_REPS}_lat{L}"]
    rtt = round(Pm.RTT_BASE_US + 8 * L / 1000, 3)
    for tag, off in arms.items():
        name = f"{Pm.CFG_REPS}Bk{tag}_lat{L}"
        cfgs.append(dict(reps, name=name, bank=dict(size=SIZE, timer_us=rtt, target_us=None if off is None else round(rtt + off, 3))))
        bs[name] = [B_BANK]
json.dump(cfgs, open(DATA / "configs_knee16_bank.json", "w"), indent=1)
json.dump(bs, open(DATA / "bsmap_knee16_bank.json", "w"), indent=1)
print(len(cfgs), "bank configs; arms", list(arms), "; B =", B_BANK, "; bank size", SIZE)
