# exp18 — PATH_RR start-slot sweep: does staggering help?

**Added:** 2026-06-09
**Status:** complete — see results below

---

## Motivation

exp15 showed that the *starting index* mode (zero/src_mod/dst_mod/srcdst_hash) had zero effect
on FCT when using `cwnd=90`. exp17 corrected `cwnd` to 155 but only tested `zero` as the
PATH_RR start mode. This experiment asks: at the correct cwnd, does **staggering** the start
slot across flows matter?

In a k=4 fat-tree with `np=4` paths per host-pair, if all 16 tornado flows start at slot 0 they
cycle in lock-step: packet 0 of every flow goes to path 0, packet 1 to path 1, etc. Staggering
by `src % np` distributes the 16 senders into 4 groups of 4, each starting at a different slot.
Does this reduce path collisions and lower FCT?

---

## Design

**Fixed**: tornado workload, N=16, 4-ary fat-tree 3-tier, 400 Gbps, cwnd=155, seeds 42/43/44,
256 MiB flows only.

**Variable**: start-slot offset mode × CC algorithm

| Condition | Start mode | Meaning | CC |
|-----------|-----------|---------|-----|
| `off0_constant` | `zero`     | All flows start at slot 0 | constant |
| `off0_nscc`     | `zero`     | All flows start at slot 0 | NSCC |
| `off1_constant` | `src_mod`  | Flow from host h starts at `h % np` | constant |
| `off1_nscc`     | `src_mod`  | Flow from host h starts at `h % np` | NSCC |
| `off2_constant` | `src_mod2` | Flow from host h starts at `(h*2) % np` | constant |
| `off2_nscc`     | `src_mod2` | Flow from host h starts at `(h*2) % np` | NSCC |
| `path_static_constant` | PATH_STATIC | Reference — no shared edges | constant |
| `path_static_nscc`     | PATH_STATIC | Reference — no shared edges | NSCC |

`off0` and `path_static` data are reused directly from exp17 (byte-identical files, just renamed).
12 new runs: `off1` and `off2`, both CC variants, 3 seeds = 12 new simulation runs.

**New mode added to binary**: `src_mod2` (`PATH_RR_START_SRC2` enum value), adds `(src*2) % np`
start assignment. With `np=4`, this yields slots [0,2,0,2,...] for the 16 tornado senders — only
2 distinct slots vs 4 distinct slots for `src_mod`.

---

## Results

See [plots/exp18_startslot_256mib.png](plots/exp18_startslot_256mib.png).

### Summary (mean ± 95% CI across 3 seeds, 256 MiB)

| Condition | Avg-slowdown | Max-slowdown |
|-----------|-------------|-------------|
| off0_constant     | 1.0405±0.0029 | 1.0426±0.0058 |
| off0_nscc         | 1.0363±0.0028 | 1.0389±0.0040 |
| off1_constant     | 1.0411±0.0016 | 1.0446±0.0006 |
| off1_nscc         | 1.0368±0.0017 | 1.0411±0.0024 |
| off2_constant     | 1.0415±0.0036 | 1.0451±0.0094 |
| off2_nscc         | 1.0369±0.0012 | 1.0395±0.0023 |
| path_static_constant | 1.0334±0.0000 | 1.0334±0.0000 |
| path_static_nscc  | 1.0324±0.0000 | 1.0324±0.0000 |

### FCT spread (finish-time spread across 16 flows within one run, seed=42)

| Condition | Spread |
|-----------|--------|
| off0 | ~20 µs |
| off1 | ~38 µs |
| off2 | ~63 µs |
| path_static | 0.00 µs |

---

## Findings

### Finding 1: Staggering provides no average FCT improvement

All three offset modes (off0, off1, off2) produce avg FCT within 0.001× of each other — well
within the 95% CI overlap. The null result from exp15 holds even at the correct cwnd=155.

### Finding 2: Staggering *increases* FCT spread

Counter-intuitively, better phase distribution does **not** produce more uniform finish times.
FCT spread actually worsens: off0=20 µs → off1=38 µs → off2=63 µs. When all flows start at the
same slot they create synchronised bursts but also synchronised relief. When staggered, some flows
encounter bursts from earlier flows mid-transmission, creating irregular interference.

### Finding 3: PATH_STATIC's advantage is structural, not phase-coordination

PATH_STATIC achieves 1.033× (vs PATH_RR ~1.040×) and zero FCT spread not because of any
phase trick, but because its greedy edge-load assignment guarantees no two flows ever share a
data-path link. Start-slot staggering cannot replicate this structural guarantee.

---

## How to reproduce

```bash
# Build binary first (from repo root):
cd htsim/sim && make -j8 && cd ../..

# Ensure exp17 data exists (off0 and path_static are copied from there):
bash state_aware_experiments/exp17_cwnd_corrected_v17/scripts/02_run_exp17_256mib.sh

# Run exp18 (copies exp17 data + runs 12 new sims):
bash state_aware_experiments/exp18_path_rr_startslot_v18/scripts/01_run_exp18.sh

# Aggregate and plot:
python3 state_aware_experiments/exp18_path_rr_startslot_v18/aggregate_exp18.py
python3 state_aware_experiments/exp18_path_rr_startslot_v18/plot_exp18.py
```
