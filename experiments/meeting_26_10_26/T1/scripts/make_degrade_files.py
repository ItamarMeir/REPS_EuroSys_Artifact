#!/usr/bin/env python3
"""Write degrade_r<RRR>.txt: ToR0 uplinks, even agg ratio r, odd agg ratio 1-r (mean 0.5, same layout as
meeting_23_10_26/M4/data/degrade_nonuniform_25_75.txt, which is the r=0.25 case)."""
from pathlib import Path
D = Path(__file__).resolve().parents[1] / "data"
for tag, r in (("r010", 0.10), ("r005", 0.05), ("r001", 0.01)):
    lines = ["# tor agg ratio (ToR0 uplinks; ratio = speed fraction kept)"]
    lines += [f"0 {a} {r if a % 2 == 0 else round(1 - r, 4)}" for a in range(32)]
    (D / f"degrade_{tag}.txt").write_text("\n".join(lines) + "\n")
