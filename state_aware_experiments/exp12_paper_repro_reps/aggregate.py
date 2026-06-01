#!/usr/bin/env python3
"""
aggregate.py — Parse htsim_uec output files and produce two tidy CSVs:

  data/fcts.csv    — one row per flow: fig, cc, seed, [pct], fct_us, size_bytes
  data/cct.csv     — one row per (fig, cc, seed): cct_pct, cct_us, max_fct_us
                     plus mean/ci95 computed across seeds

Zero-queueing lower bound (ZQLB) is computed empirically:
  For each (fig, target_flow_size) combination we take the minimum FCT observed
  across ALL CCAs and seeds. This makes CCT% independent of hard-coded hop-latency
  assumptions and reflects what the simulator actually achieves.

For HSDP (Fig 7): flow size varies; ZQLB is the minimum FCT across all flows in
that run (all flows have the same target — ring steps).

CCT% = (max_FCT - ZQLB) / ZQLB × 100

Run from the exp12 directory:
  python3 aggregate.py
"""
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

# ── Paths ────────────────────────────────────────────────────────────────────
EXP_DIR  = Path(__file__).parent
DATA_DIR = EXP_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Incast: all senders share the receiver's downlink → ZQLB is collective, not per-flow.
INCAST_FIGS    = {"fig14"}
N_INCAST_FLOWS = 32
LINK_RATE_BPS  = 800_000_000_000   # 800 Gbps (BASE128 in lib_common.sh)
BASE_RTT_US    = 3.0               # 3 hops × 0.5 µs × 2 (round-trip in 3-tier fat-tree)

# Target flow size in bytes for CCT computation (filters out elephant/background flows).
# CCT is measured over the short sprayed flows, not over long-lived elephants.
TARGET_SIZE_BY_FIG = {
    "fig4":  8_388_608,     # 8 MB sprayed flows (exclude 64 MB elephants)
    "fig5c": 8_388_608,
    "fig6":  8_388_608,
    "fig7":  None,          # HSDP: all flows are target (no background)
    "fig8":  8_388_608,
    "fig9":  16_777_216,
    "fig10": 8_388_608,
    "fig11": 8_388_608,
    "fig12": 8_388_608,
    "fig14": 8_388_608,
}

# ── FCT line parser ──────────────────────────────────────────────────────────
# Line format: Flow <name> flowId <id> uecSrc <id> finished at <fct_us> flowSize <bytes> [...]
FLOW_RE = re.compile(
    r"^Flow\s+\S+\s+flowId\s+\d+\s+uecSrc\s+\d+\s+finished\s+at\s+"
    r"(\d+\.?\d*(?:e[+-]?\d+)?)\s+flowSize\s+(\d+)"
)

def parse_fcts(path: Path):
    """Return list of (fct_us, size_bytes) from a single .out file."""
    rows = []
    try:
        with open(path, "r") as fh:
            for line in fh:
                m = FLOW_RE.match(line)
                if m:
                    rows.append((float(m.group(1)), int(m.group(2))))
    except FileNotFoundError:
        pass
    return rows

# ── Discover output files ─────────────────────────────────────────────────────
all_rows = []

for outfile in sorted(DATA_DIR.glob("*.out")):
    name = outfile.stem                          # e.g. "fig4_nscc_s42"
    parts = name.split("_")

    # Detect fig12 variant: fig12_mswift_p50_s42
    fig     = parts[0]
    pct_str = None
    if len(parts) == 4 and parts[2].startswith("p"):
        cc      = parts[1]
        pct_str = parts[2][1:]                   # "50"
        seed    = int(parts[3][1:])
    elif len(parts) == 3:
        cc   = parts[1]
        seed = int(parts[2][1:])
    else:
        print(f"[warn] Unrecognised filename pattern: {name}", file=sys.stderr)
        continue

    fcts = parse_fcts(outfile)
    if not fcts:
        print(f"[warn] No FCT lines in {outfile.name}", file=sys.stderr)
        continue

    for fct_us, size_bytes in fcts:
        row = {
            "fig": fig, "cc": cc, "seed": seed,
            "pct": pct_str,
            "fct_us": fct_us, "size_bytes": size_bytes,
        }
        all_rows.append(row)

if not all_rows:
    print("[aggregate] No output files found in data/. Run the simulation scripts first.")
    sys.exit(0)

fcts_df = pd.DataFrame(all_rows)
fcts_df.to_csv(DATA_DIR / "fcts.csv", index=False)
print(f"[aggregate] Wrote {len(fcts_df)} flow rows to data/fcts.csv")

# ── Compute empirical ZQLB per (fig, target_size) ────────────────────────────
# ZQLB = minimum FCT across all CCAs/seeds for flows of the target size.
# For fig7 (HSDP), all flows are target; ZQLB = global min FCT.
# Keyed as (fig_str, size_bytes_or_None).
empirical_zqlb = {}
for fig in fcts_df["fig"].unique():
    target_size = TARGET_SIZE_BY_FIG.get(fig)
    mask = fcts_df["fig"] == fig
    if target_size is not None:
        mask = mask & (fcts_df["size_bytes"] == target_size)
    sub = fcts_df[mask]
    if sub.empty:
        empirical_zqlb[fig] = None
    elif fig in INCAST_FIGS and target_size is not None:
        # Incast bottleneck is the receiver's downlink: ZQLB = total bytes / link rate + base_rtt.
        empirical_zqlb[fig] = (
            N_INCAST_FLOWS * target_size * 8.0 / LINK_RATE_BPS * 1e6 + BASE_RTT_US
        )
    else:
        empirical_zqlb[fig] = float(sub["fct_us"].min())

print("\n[aggregate] Empirical ZQLB per figure:")
for fig, zqlb in sorted(empirical_zqlb.items()):
    print(f"  {fig}: {zqlb:.3f} µs" if zqlb else f"  {fig}: (no data)")

# ── Compute CCT% per (fig, cc, seed[, pct]) ──────────────────────────────────
cct_rows = []

group_cols = ["fig", "cc", "seed", "pct"]
for (fig, cc, seed, pct), grp in fcts_df.groupby(group_cols, dropna=False):
    # Filter to target flow size (exclude elephant/background flows from CCT).
    target_size = TARGET_SIZE_BY_FIG.get(fig)
    if target_size is not None:
        grp = grp[grp["size_bytes"] == target_size]

    if grp.empty:
        print(f"[warn] No target-size flows for fig={fig} cc={cc} seed={seed}; skipping.")
        continue

    zqlb = empirical_zqlb.get(fig)
    if zqlb is None or zqlb == 0:
        print(f"[warn] No ZQLB for fig={fig}; skipping CCT computation.")
        continue

    max_fct = grp["fct_us"].max()
    cct_pct = (max_fct - zqlb) / zqlb * 100.0

    cct_rows.append({
        "fig": fig, "cc": cc, "seed": seed, "pct": pct,
        "max_fct_us": max_fct, "zqlb_us": zqlb, "cct_pct": cct_pct,
        "n_flows": len(grp),
    })

cct_df = pd.DataFrame(cct_rows)

# ── Summary: mean ± 95% CI across seeds ──────────────────────────────────────
summary_rows = []
for (fig, cc, pct), grp in cct_df.groupby(["fig", "cc", "pct"], dropna=False):
    vals = grp["cct_pct"].values
    n = len(vals)
    mean = vals.mean()
    if n >= 2:
        ci95 = stats.t.ppf(0.975, df=n-1) * vals.std(ddof=1) / np.sqrt(n)
    else:
        ci95 = float("nan")
    summary_rows.append({
        "fig": fig, "cc": cc, "pct": pct,
        "n_seeds": n, "mean_cct_pct": mean, "ci95": ci95,
        "min_cct_pct": vals.min(), "max_cct_pct": vals.max(),
    })

summary_df = pd.DataFrame(summary_rows)
summary_df.to_csv(DATA_DIR / "cct.csv", index=False)
print(f"\n[aggregate] Wrote {len(summary_df)} summary rows to data/cct.csv")
print()
print(summary_df.to_string(index=False, float_format="%.1f"))
