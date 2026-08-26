# exp15 — PATH_RR Buffer-Order Study

**Added:** 2026-06-04
**Status:** complete — see results below

---

## Motivation

In exp14, PATH_RR+constant gave ~1.78× slowdown from the theoretical optimal FCT. The question
is: how much of that overhead is due to *synchronized path starts* (all flows starting at
`_paths[0]` simultaneously, creating burst congestion at the same core switches)?

The hypothesis: staggering the starting index — e.g., flow with src `s` starts at `s % 4` —
would spread traffic evenly across core switches at every time step and reduce FCT.

---

## Design

**Fixed**: PATH_RR + constant CC (line-rate), tornado N=16, 4-ary fat-tree 3-tier
**Variable**: starting-index mode for the PATH_RR cycle

| Mode | Starting index formula | Tornado behavior |
|------|----------------------|-----------------|
| `zero` | `0` (default) | All flows start at path 0 → synchronized |
| `src_mod` | `src % num_paths` | Desync by source: {0,1,2,3,0,1,2,3,...} per pod group |
| `dst_mod` | `dst % num_paths` | Desync by destination |
| `srcdst_hash` | `(src*7 + dst*3) % num_paths` | Hash-based spread |

For tornado (`src_i → (src+8)%16`): `src_mod` gives offsets {0,1,2,3} for the 4 flows per
source pod → perfectly balanced packet timing across all 4 core switches at every time slot.

4 modes × 3 sizes (4/8/16 MiB) × 3 simulator seeds = **36 runs**

---

## Results

See [plots/exp15_fct_slowdown.png](plots/exp15_fct_slowdown.png).

### Short flows (4–16 MiB)

| Mode | 4 MiB avg | 8 MiB avg | 16 MiB avg |
|------|-----------|-----------|------------|
| zero        | 1.8246±0.0008 | 1.7805±0.0012 | 1.7703±0.0003 |
| src_mod     | 1.8251±0.0009 | 1.7809±0.0003 | 1.7706±0.0006 |
| dst_mod     | 1.8251±0.0009 | 1.7809±0.0003 | 1.7706±0.0006 |
| srcdst_hash | 1.8234±0.0022 | 1.7802±0.0023 | 1.7705±0.0006 |

### Very long flows (64 MiB – 1 GiB)

| Mode | 64 MiB avg | 256 MiB avg | 1 GiB avg |
|------|------------|-------------|-----------|
| zero        | 1.7567±0.0004 | 1.7526±0.0003 | 1.7516±0.0004 |
| src_mod     | 1.7567±0.0004 | 1.7526±0.0001 | 1.7515±0.0003 |
| dst_mod     | 1.7567±0.0004 | 1.7526±0.0001 | 1.7515±0.0003 |
| srcdst_hash | 1.7564±0.0002 | 1.7525±0.0001 | 1.7515±0.0001 |

### Finding 1: buffer ordering has no measurable effect at any flow size

All 4 modes remain statistically indistinguishable across all 6 flow sizes (4 MiB → 1 GiB).
Maximum difference between modes at any point: < 0.002, well within 95% CI.

### Finding 2: the overhead converges to a constant ~1.752× for large flows

The slowdown decreases from 1.825× at 4 MiB to 1.752× at 1 GiB and appears to converge.
It does **NOT** approach 1.0. This means the overhead is **proportional**, not absolute:
even for a 1 GiB flow, ~75% more time is spent than the theoretical minimum.

The small decrease from 4 MiB → 1 GiB is a fixed setup overhead becoming negligible:
- 4 MiB → 1 GiB: slowdown drops by 0.073 over a 256× size increase
- This ~4% reduction is the one-time startup cost amortized over the larger flow

### Finding 3: zero retransmissions — pure queuing overhead

All 1 GiB runs have `RTS = 0` (verified). The overhead is entirely from steady-state
queueing delay: cwnd=90 > BDP≈73 packets creates a persistent queue at every hop. Each
packet experiences the same extra queuing delay regardless of path or flow size. Since queuing
adds a constant fraction to every packet's latency, the FCT slowdown ratio stays constant.

**Root cause**: with cwnd=90 and BDP≈73, the sender permanently over-injects by 17 packets.
In steady state, the excess fills queues and increases per-packet latency by
`excess_pkts × MTU × 8 / link_rate × num_hops`. This is proportional to cwnd, independent
of flow size or path ordering.

### Confirmed prediction: src_mod = dst_mod for tornado

For tornado (`dst = src + 8`): `dst % 4 = src % 4` for all hosts, so `src_mod` and `dst_mod`
produce bit-identical results at every size. Verified.

---

## Implications

1. **Buffer order is irrelevant** for FCT under constant CC at any flow size.
   Path synchronization does not affect the dominant overhead mechanism.
2. **The ~1.75× overhead is a steady-state cwnd/RTT artifact**, not a startup transient.
   NSCC removes it by reducing cwnd in response to congestion signals (exp14: 1.09×).
3. **The `-path_rr_start_mode` flag** is implemented and available for future use, but
   its effect is negligible in the standard parameter regime.

---

## CLI Addition

`-path_rr_start_mode {zero|src_mod|dst_mod|srcdst_hash}` — controls the initial position
in the PATH_RR cycle per flow. Default is `zero` (backward-compatible).
Implemented in `htsim/sim/uec.h`, `uec.cpp`, `datacenter/main_uec.cpp`.

---

## Files

```
exp15_path_rr_order_v15/
├── README.md
├── scripts/
│   └── 01_run_exp15.sh
├── data/
│   ├── exp15_*.out         (36 raw outputs)
│   └── fcts.csv
├── plots/
│   └── exp15_fct_slowdown.png
├── aggregate_exp15.py
└── plot_exp15.py
```
