# exp21 — SRv6 Buffer Sweep on K=16 Fat Tree

## Motivation

With SRv6 enabled on a K=16 3-tier fat tree, the EV domain exactly matches the number of
physical paths:

- K=16 fat tree → **(K/2)² = 64** distinct paths per cross-pod flow.
- `path_entropy_size = 64` → FREEZING/REPS draw EVs as `rand() % 64` ∈ [0, 63].
- SRv6 maps `ev % 64 = ev` (**identity**) → each EV uniquely identifies one physical path.
- FREEZING's circular buffer of size B holds B distinct EVs → B distinct paths are actively used.

**Scientific question**: as B grows from 8 → 16 → 32 → 64 (= full path space), how does FCT
improve? How does REPS (unbounded) compare? Does the answer change under adaptive (NSCC) vs
fixed-linerate (CONSTANT) congestion control?

**Baseline**: PATH_STATIC assigns each flow to a single path via greedy edge-load selection
(see exp17) — the oracle upper bound for a static assignment scheme.

---

## Design Matrix

| Label | LB algorithm | Buffer | SRv6 |
|---|---|---|---|
| `path_static` | PATH_STATIC (greedy oracle) | — | no |
| `freezing_b8` | FREEZING | 8 | yes |
| `freezing_b16` | FREEZING | 16 | yes |
| `freezing_b32` | FREEZING | 32 | yes |
| `freezing_b64` | FREEZING | 64 | yes |
| `reps` | REPS (unbounded) | ∞ | yes |

CC modes: **NSCC** (`-sender_cc_algo nscc -cwnd 100`) and **CONSTANT** (`-sender_cc_algo constant -cwnd 1000`).

**3 seeds** × 6 algorithms × 2 CC modes = **36 runs**.

Topology: `fat_tree_1024_1os_3t_400g.topo` (1024 hosts, K=16, 3-tier, 400 Gbps).
Workload: `tornado_n1024_s8388608.cm` (8 MB elephant flows, tornado permutation).

Key flags: `-paths 64 -sender_cc_only -disable_tor_ecn -linkspeed 400000 -hop_latency 0.5 -q 60 -ecn 12 48 -exit_freeze 200000000 -end 90000`.

---

## Results

All 36 runs completed with 1024/1024 flows finished. 95% CIs computed via t-distribution over 3 seeds.

### NSCC mode

| Algorithm | Mean FCT (µs) | ±95% CI | p99 FCT (µs) | ±95% CI | Mean slowdown |
|---|---|---|---|---|---|
| PATH_STATIC | **192.3** | 0.0 | **192.3** | 0.0 | **1.15** |
| FREEZING B=8 | 205.5 | 0.3 | 209.2 | 1.0 | 1.23 |
| FREEZING B=16 | 205.6 | 0.3 | 209.3 | 1.6 | 1.23 |
| FREEZING B=32 | 205.6 | 0.2 | 209.3 | 1.6 | 1.23 |
| FREEZING B=64 | 205.6 | 0.2 | 209.3 | 1.6 | 1.23 |
| REPS (∞) | 211.5 | 0.3 | 215.4 | 1.6 | 1.26 |

### CONSTANT (fixed linerate) mode

| Algorithm | Mean FCT (µs) | ±95% CI | p99 FCT (µs) | ±95% CI | Mean slowdown |
|---|---|---|---|---|---|
| PATH_STATIC | **185.4** | 0.0 | **185.4** | 0.0 | **1.10** |
| FREEZING B=8 | 200.9 | 0.5 | 204.0 | 0.3 | 1.20 |
| FREEZING B=16 | 200.9 | 0.5 | 203.9 | 0.5 | 1.20 |
| FREEZING B=32 | 200.9 | 0.5 | 203.9 | 0.5 | 1.20 |
| FREEZING B=64 | 200.9 | 0.5 | 204.0 | 0.6 | 1.20 |
| REPS (∞) | 203.8 | 0.4 | 206.4 | 0.8 | 1.21 |

---

## Plots

| Plot | Description |
|---|---|
| ![Mean FCT](plots/mean_fct.png) | Mean FCT per algorithm/CC mode (95% CI over 3 seeds) |
| ![p99 FCT](plots/p99_fct.png) | p99 FCT per algorithm/CC mode |
| ![Slowdown](plots/slowdown.png) | Mean slowdown = FCT / ideal single-flow FCT at 400G |

---

## Key Findings

### 1. FREEZING buffer size has no effect on tornado (B=8 ≡ B=64)

FREEZING B=8, B=16, B=32, and B=64 produce virtually identical FCTs under both CC modes
(within CI). Increasing the buffer beyond 8 yields no measurable benefit.

**Interpretation**: tornado is a perfect permutation workload on a symmetric fat tree. Every
source-destination pair has 64 equal-cost paths with no cross-flow path contention. Elephant
flows carry enough ACK feedback that even a B=8 buffer explores the path space adequately
within the first RTT. Once a flow is in steady state on a good path, there is nothing further
to gain from a larger buffer.

### 2. REPS (unbounded) is slightly *worse* than all FREEZING variants under NSCC (+6 µs)

REPS mean FCT: 211.5 µs vs FREEZING 205.5 µs under NSCC. The difference persists across all 3
seeds (CI: ±0.3 µs for REPS, ±0.3 µs for B=8). Under CONSTANT CC, the gap narrows (203.8 vs
200.9 µs, +2.9 µs).

**Interpretation — superseded, see [`exp24_reps_no_rr_v24/README.md`](../exp24_reps_no_rr_v24/README.md).**
The original explanation here ("REPS's unbounded deque accumulates stale path IDs") was
checked against the raw per-ACK logs and does not hold: REPS's recycle-pool depth (avg 4.99,
empty 14.8% of ACKs) and FREEZING's (avg fresh 5.29, empty 16.6%) are statistically
indistinguishable — buffer occupancy is not the driver. exp24 isolated the real cause:
REPS's deterministic first-window round-robin (`uec.cpp:3046-3054`, absent in FREEZING)
synchronizes path selection across tornado's simultaneously-starting flows, correlating load
onto the same core switch/uplink. Disabling it closes the gap completely — the resulting
FCT lands inside the FREEZING B=1..64 band on every metric and CC mode tested.

### 3. PATH_STATIC is the clear winner; FREEZING/REPS pay ~7 µs overhead (NSCC) or ~15 µs (CONSTANT)

PATH_STATIC: p99 = mean = 192.3 µs (NSCC) and 185.4 µs (CONSTANT) — **zero variance** across
all 1024 flows. The greedy oracle assigns each flow to a unique path with zero contention.

FREEZING/REPS pay 7 µs overhead under NSCC and ~15 µs under CONSTANT. The CONSTANT mode gap
is larger because PATH_STATIC benefits most from removing CC overhead (no rate fluctuation),
while FREEZING/REPS spend some early RTTs on path exploration.

### 4. CONSTANT outperforms NSCC for all algorithms (+7 µs improvement for PATH_STATIC)

At full bisection with perfectly balanced load, CC adaptation adds latency without reducing
contention. PATH_STATIC under CONSTANT (185.4 µs) beats PATH_STATIC under NSCC (192.3 µs) by
a full 7 µs — the CC control loop overhead on a clean topology.

---

## Interpretation

The experiment confirms that on a symmetric permutation workload at K=16:

1. **SRv6's EV-to-path identity mapping works correctly** — every flow picks deterministic
   source-routed paths; there is no ECMP hash collision or unexpected spreading.

2. **The buffer size in FREEZING is not the bottleneck for tornado** — the workload is too
   balanced for buffer size to matter. The right question for buffer-size sensitivity is a
   *skewed* or *incast* workload where specific paths are congested and the buffer's path
   diversity determines whether the algorithm escapes.

3. **REPS should not be used when FREEZING is available** — it is consistently slower due to
   stale deque history, confirming the exp01→exp02 motivation for the switch to FREEZING.

4. **Future work**: repeat with an unbalanced workload (e.g., random permutation, incast,
   or skewed CDF) to find the buffer size at which B=8 diverges from B=64. The tornado result
   establishes the symmetric-case floor; the interesting region is asymmetric load.

---

## Files

```
exp21_srv6_buffer_sweep_k16_v21/
├── scripts/run_exp21.sh      driver (36 runs, idempotent)
├── scripts/aggregate.py      parser → data/exp21_flows.csv
├── scripts/plot.py           plotter → plots/*.png
├── data/exp21_flows.csv      36 × 1024 = 36864 rows
├── plots/mean_fct.png
├── plots/p99_fct.png
├── plots/slowdown.png
└── runs.tar.gz               raw simulator outputs (compressed)
```
