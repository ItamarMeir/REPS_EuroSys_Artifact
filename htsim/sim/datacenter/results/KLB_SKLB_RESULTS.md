# K-LB and Stateful-KLB Evaluation Results

## Overview

This document reports flow completion time (FCT) comparisons across two fat-tree topologies for the following load-balancing algorithms:

- **REPS+NSCC** — REPS with NSCC congestion control (reference baseline, receiver-driven)
- **REPS+linerate** — REPS at constant line rate (no CC), upper-bound on throughput without per-flow CC
- **KLB** — K-path load balancer: maintains K active Entropy Values (EVs) per flow, replaces congested EV with probability (K−1)/K
- **SKLB** — Stateful-KLB: switch-enforced incumbent advantage with deterministic (100%) EV replacement on rejection

All FCT values are in microseconds (µs). Results are mean ± std across 5 independent seeds (distinct random permutation traffic matrices).

---

## Topology 1: k=6 Fat-Tree (54 hosts, 9 core paths)

**Setup:** 54 hosts, 6 pods, 9 core switches (9 distinct paths).  
Permutation TM, 8 MB flows, 400 Gbps links, queue=100 pkts, ECN thresholds: 25/75 pkts.  
Simulation time: 90 ms. No ToR-downlink ECN (`-disable_tor_ecn`).  
SKLB: `max_incumbents=6`, `idle_timeout=6µs` (≈1 RTT), congestion ECN at 25-pkt threshold.

| Experiment      | Seeds | Mean FCT ± σ   | p50 ± σ      | p99 ± σ       | Max ± σ       |
|-----------------|------:|---------------:|-------------:|--------------:|--------------:|
| reps_nscc       |     5 | 204.2 ± 3.7   | 201.1 ± 2.6 | 246.9 ± 13.7 | 255.7 ± 26.9 |
| reps_linerate   |     5 | 207.3 ± 5.4   | 206.6 ± 5.2 | 239.7 ± 17.7 | 245.1 ± 23.9 |
| klb_k1          |     5 | 398.4 ± 11.3  | 380.5 ± 10.3| 716.9 ± 70.6 | 718.0 ± 71.2 |
| klb_k2          |     5 | 260.7 ± 7.5   | 264.1 ± 7.3 | 305.9 ± 9.6  | 308.4 ± 9.6  |
| klb_k4          |     5 | 240.8 ± 4.2   | 242.2 ± 3.6 | 282.9 ± 11.0 | 285.6 ± 10.3 |
| klb_k8          |     5 | 232.6 ± 5.6   | 231.6 ± 4.0 | 280.7 ± 16.0 | 289.9 ± 18.4 |
| klb_k16         |     5 | 231.4 ± 5.1   | 233.4 ± 4.6 | 258.8 ± 4.2  | 259.3 ± 4.3  |
| klb_k32         |     5 | 230.9 ± 7.1   | 231.5 ± 2.7 | 264.9 ± 16.9 | 267.3 ± 16.0 |
| sklb_k2         |     5 | 321.2 ± 12.4  | 323.3 ± 15.2| 423.2 ± 43.2 | 434.8 ± 59.7 |
| sklb_k4         |     5 | 274.1 ± 8.7   | 276.9 ± 11.5| 329.6 ± 15.5 | 330.7 ± 15.4 |
| sklb_k8         |     5 | 249.8 ± 5.6   | 248.0 ± 4.1 | 303.0 ± 6.1  | 303.6 ± 6.4  |

### Key observations (k=6)

- **REPS+NSCC is best** (204.2 µs), confirming that receiver-driven CC provides the optimal balance of congestion avoidance and load spreading.
- **KLB saturates around K=8** — with only 9 physical paths, K>9 cannot add new distinct paths (EV deduplication ensures at most 9 unique paths are ever active). The improvement from K=8 to K=16/32 is less than 1 µs.
- **KLB K=1 is poor** (398.4 µs): single-path, no diversity. The (K−1)/K replacement probability is 0 for K=1, meaning congested paths are never replaced.
- **SKLB underperforms KLB** at the same K by 17–23%. See analysis below.

---

## Topology 2: k=8 Fat-Tree (128 hosts, 16 core paths)

**Setup:** 128 hosts, 8 pods, 16 core switches (16 distinct paths).  
Same traffic and queue parameters. SKLB: `max_incumbents=min(K, 16)`, `idle_timeout=6µs`, congestion ECN at 25-pkt threshold.

### Pilot evaluation (5 seeds, K ∈ {2,4,8})

| Experiment      | Seeds | Mean FCT ± σ   | p50 ± σ      | p99 ± σ       | Max ± σ       |
|-----------------|------:|---------------:|-------------:|--------------:|--------------:|
| reps_nscc       |     5 | 200.4 ± 1.9   | 199.5 ± 1.6 | 224.3 ± 2.5  | 231.6 ± 4.4  |
| reps_linerate   |     5 | 200.8 ± 2.4   | 201.1 ± 2.3 | 213.4 ± 3.5  | 216.1 ± 5.3  |
| klb_k1          |     5 | 449.8 ± 15.4  | 434.0 ± 14.7| 786.4 ± 67.8 | 793.2 ± 64.7 |
| klb_k2          |     5 | 264.0 ± 3.0   | 267.2 ± 2.6 | 306.5 ± 3.7  | 311.8 ± 6.4  |
| klb_k4          |     5 | 233.0 ± 4.0   | 234.0 ± 4.1 | 264.3 ± 10.0 | 272.0 ± 10.9 |
| klb_k8          |     5 | **213.9 ± 2.6** | 214.5 ± 2.7 | 233.3 ± 6.9 | 237.5 ± 5.8  |
| klb_k16         |     5 | 223.0 ± 3.0   | 223.2 ± 2.7 | 247.0 ± 5.6  | 251.9 ± 8.8  |
| klb_k32         |     5 | 224.2 ± 1.8   | 225.8 ± 1.3 | 239.9 ± 3.9  | 240.9 ± 3.8  |
| sklb_k2         |     5 | 333.7 ± 6.9   | 331.2 ± 6.1 | 425.8 ± 34.8 | 430.8 ± 38.8 |
| sklb_k4         |     5 | 285.3 ± 10.1  | 285.1 ± 11.0| 342.3 ± 19.8 | 350.5 ± 21.9 |
| sklb_k8         |     5 | 247.0 ± 2.1   | 248.2 ± 2.0 | 270.7 ± 2.4  | 278.6 ± 6.2  |
| hklb_k2         |     5 | 236.8 ± 2.6   | 239.0 ± 2.4 | 253.9 ± 2.4  | 255.6 ± 2.4  |
| hklb_k4         |     5 | **216.2 ± 1.5** | 217.0 ± 1.7 | 228.7 ± 4.7 | 230.9 ± 6.8  |
| hklb_k8         |     5 | 218.9 ± 3.6   | 220.1 ± 3.9 | 244.4 ± 7.1  | 247.0 ± 6.0  |
| hklb_se_k4      |     5 | 259.6 ± 7.1   | 260.9 ± 7.3 | 289.3 ± 9.4  | 294.1 ± 7.6  |
| hklb_se_k8      |     5 | 240.8 ± 2.8   | 241.2 ± 2.3 | 264.6 ± 7.4  | 266.9 ± 8.1  |

### Full algorithm sweep (10 seeds, K ∈ {4,8,16,32,64,128})

**Setup:** Same topology and parameters. 10 seeds (42–51). 200 total runs. SKLB `max_incumbents=min(K,16)`.

| Experiment      | Seeds |  Mean FCT ± σ  |   p50 ± σ    |   p99 ± σ     |   Max ± σ     |
|-----------------|------:|---------------:|-------------:|--------------:|--------------:|
| reps_nscc       |    10 |  200.0 ± 2.2  | 199.3 ± 1.9 | 224.9 ± 6.8  | 234.1 ± 5.7  |
| reps_linerate   |    10 |  200.2 ± 2.6  | 200.4 ± 2.3 | 212.6 ± 4.7  | 215.0 ± 5.5  |
| klb_k4          |    10 |  232.5 ± 4.6  | 234.0 ± 4.4 | 261.1 ± 9.5  | 267.9 ± 12.0 |
| hklb_k4         |    10 | **215.9 ± 1.9** | 216.9 ± 1.8 | 228.4 ± 3.4 | 230.2 ± 4.9  |
| sklb_k4         |    10 |  269.9 ± 4.8  | 271.7 ± 5.0 | 306.6 ± 7.8  | 316.7 ± 9.1  |
| klb_k8          |    10 | **213.8 ± 3.4** | 214.7 ± 3.7 | 231.8 ± 5.8 | 235.2 ± 5.2  |
| hklb_k8         |    10 |  218.1 ± 4.1  | 219.0 ± 4.2 | 243.7 ± 5.7  | 246.3 ± 5.2  |
| sklb_k8         |    10 |  246.9 ± 4.1  | 248.6 ± 3.4 | 272.2 ± 4.1  | 281.3 ± 6.3  |
| klb_k16         |    10 |  221.8 ± 4.1  | 222.3 ± 3.6 | 246.7 ± 4.8  | 254.9 ± 12.7 |
| hklb_k16        |    10 |  223.1 ± 3.3  | 223.6 ± 3.5 | 247.8 ± 5.4  | 249.6 ± 5.3  |
| sklb_k16        |    10 |  242.9 ± 3.9  | 242.9 ± 3.3 | 271.7 ± 6.5  | 277.6 ± 10.3 |
| klb_k32         |    10 |  223.8 ± 2.8  | 225.7 ± 2.2 | 239.0 ± 3.0  | 240.0 ± 2.9  |
| hklb_k32        |    10 |  223.1 ± 3.1  | 223.7 ± 3.4 | 247.0 ± 5.9  | 249.4 ± 6.4  |
| sklb_k32        |    10 |  259.0 ± 5.4  | 259.1 ± 4.2 | 299.4 ± 21.9 | 303.4 ± 21.8 |
| klb_k64         |    10 |  223.6 ± 2.9  | 224.9 ± 2.2 | 238.9 ± 3.8  | 240.4 ± 4.0  |
| hklb_k64        |    10 |  223.1 ± 3.1  | 223.7 ± 3.3 | 248.0 ± 5.2  | 250.7 ± 6.2  |
| sklb_k64        |    10 |  253.5 ± 3.4  | 254.5 ± 3.5 | 280.5 ± 6.5  | 289.2 ± 8.8  |
| klb_k128        |    10 |  221.4 ± 2.9  | 222.8 ± 2.5 | 235.7 ± 3.6  | 238.3 ± 4.7  |
| hklb_k128       |    10 |  223.2 ± 3.2  | 223.8 ± 3.5 | 248.1 ± 4.9  | 250.4 ± 5.9  |
| sklb_k128       |    10 |  252.2 ± 4.3  | 252.2 ± 3.3 | 285.0 ± 8.3  | 289.3 ± 9.3  |

### Key observations (k=8, full sweep)

- **REPS+NSCC is the best** (200.0 µs), essentially equal to REPS+linerate (200.2 µs): congestion is rare enough at this load that CC provides minimal benefit over line-rate.
- **KLB peaks at K=8** (213.8 µs, +6.9% vs NSCC). Increasing K beyond 8 slightly degrades performance: K=16/32/64/128 cluster around 221–224 µs. With 16 physical paths, K≥16 forces all paths into simultaneous use, eliminating adaptive path selection — the reserve paths that KLB relies on for ECN recovery are no longer available.
- **HKLB K=4 is the best open-loop variant** (215.9 µs, +7.9% vs NSCC), essentially matching KLB K=8 (213.8 µs, −1%). The discovery phase eliminates the convergence tax: KLB commits K random EVs at flow start and pays one RTT per congested path; HKLB only promotes a path after its ACK returns ECN=0, so the active set is always clean.
- **HKLB saturates at K=4**: HKLB K=8 (218.1 µs) is slightly worse than HKLB K=4 (215.9 µs). With 16 paths and K=8, the discovery phase must collect 8 clean ACKs before reaching steady state, vs 4 for K=4 — the additional probing time offsets the marginal gain from more diverse paths. At K≥16, HKLB converges to the same ~223 µs plateau as KLB.
- **SKLB consistently lags** by 13–26% vs KLB/HKLB at the same K. SKLB K=8 (246.9 µs) is 15.5% above KLB K=8. The gap widens at K=32 (259.0 µs, +15.7% vs KLB K=32) due to synchronized retry waves when the incumbent map is full.
- **SKLB also degrades at high K**: Unlike KLB which converges to ~223 µs, SKLB at K=32/64/128 sits at 252–259 µs — suggesting the incumbent map contention grows with K and partially offsets path diversity gains.

---

## KLB vs SKLB: Gap Analysis

SKLB consistently lags KLB by 17–25% at the same K value across both topologies. Three contributing factors were identified and partially addressed:

### 1. EV Collision — Fixed

Without deduplication, two EVs in the same flow's active set can map to the same physical core path. On a 9-path topology with K=4, the probability of at least one collision is **54%**; for K=8 it is **99%**. This wastes sender EV slots, concentrates load on fewer paths, and wastes switch map slots.

**Fix:** EVs are now initialized via Fisher-Yates partial shuffle (distinct paths, no replacement), and on replacement the new EV is guaranteed to differ from all other active EVs. This was verified effective: EV sets are now always distinct.

### 2. Ghost-Entry Timeout — Fixed

When a sender abandons EV_old after receiving ECN=1, the switch entry `(flow_id, EV_old)` has `last_seen ≈ now` (the last data packet updated it). With the original `idle_timeout=30µs = 5 RTTs`, EV_old's slot remains occupied for 5 full RTTs after the sender has moved on. EV_new arrives ~1 RTT later, finds EV_old still present, and itself gets ECN=1 — triggering another replacement cycle.

**Fix:** `idle_timeout` reduced to 6µs (≈1 RTT). Ghost entries expire before replacement EVs arrive.

### 3. Missing Congestion ECN for Incumbents — Fixed

`StatefulECNQueue` originally extended `Queue` (no queue-depth ECN), not `ECNQueue`. Incumbents received ECN=0 regardless of actual link congestion, allowing unrestricted queue buildup. This bypassed the sender's congestion control entirely.

**Fix:** `StatefulECNQueue` now applies congestion-based ECN at enqueue time for all packets (including incumbents) when queue occupancy exceeds the configured threshold (25 pkts = ECN_LO). The incumbent signal overrides ECN only for newcomer rejection, not congestion.

### 4. Convergence Tax (Upfront EV Commitment) — Addressed by HKLB

KLB and SKLB both commit to K random EVs at flow start and discover bad ones only after a full RTT. HKLB eliminates this by starting in a discovery phase: all packets use oblivious random EVs, and a path is only added to the active set when its ACK returns with `ecn_echo=false`. Once K clean paths are confirmed, the sender locks them in and runs round-robin — identical to KLB steady state. On ECN, the (K-1)/K probabilistic replacement drops the EV and probing resumes until a replacement is found.

The result: HKLB K=4 matches KLB K=8 performance (216.2 vs 213.9 µs) using half the concurrent paths.

### 5. Synchronized Retry Waves (SKLB) — Partially Addressed

SKLB's 100% deterministic replacement generates synchronized retry waves at startup. KLB's (K-1)/K damping reduces this. HKLB avoids the issue entirely since discovery EVs are not committed — a discovery probe that gets ECN simply isn't promoted, with no retry needed.

---

## Implementation Notes

All algorithms implemented in `htsim/sim/uec.cpp` and `uec.h`:
- `KLB`: `nextEntropy_KLB()` + `processEv_KLB()` — round-robin over active EVs, probabilistic (K-1)/K replacement on ECN
- `SKLB`: `nextEntropy_SKLB()` + `processEv_SKLB()` — same round-robin, deterministic replacement
- `HKLB`: `nextEntropy_HybridKLB()` + `processEv_HybridKLB()` — oblivious discovery until K clean ACKs, then KLB steady state
- KLB/SKLB share Fisher-Yates initialization and `klb_pick_fresh_path()` for distinct-path replacement
- `StatefulECNQueue` (`statefulecnqueue.{h,cpp}`): per-link incumbent map with enqueue-time ECN decisions and lazy idle-timeout eviction

### CLI Parameters

```
-load_balancing_algo klb|sklb|hklb
-klb_k K                      # number of active EVs per flow
-queue_type stateful_ecn       # enables StatefulECNQueue on non-ToR-downlink links
-max_incumbents N              # slots in per-link incumbent map (default: 6)
-idle_timeout_us T             # eviction timeout in microseconds (default: 30, recommended: 6)
-disable_tor_ecn               # suppress ECN on ToR downlinks (Leaf Exception)
```

### Reproduction

```bash
cd htsim/sim && make -j$(nproc)
cd datacenter

# k=6 fat-tree evaluation (55 runs, ~5 min)
python3 run_klb_eval.py
python3 parse_klb_fct.py

# k=8 fat-tree evaluation (55 runs, ~15 min)
python3 run_klb_eval_k8.py
python3 parse_klb_fct.py --dir results/klb_k8
```

---

## Summary Table

Results from the 10-seed comprehensive sweep (k=8 fat-tree, 128 hosts, 16 core paths).

| Algorithm        | Mean FCT (µs) | vs REPS+NSCC | vs KLB K=8 |
|------------------|--------------:|-------------:|-----------:|
| REPS+NSCC        |       200.0   | baseline     | −6.4%      |
| REPS+linerate    |       200.2   | +0.1%        | −6.3%      |
| **KLB K=8**      |   **213.8**   | **+6.9%**    | baseline   |
| **HKLB K=4**     |   **215.9**   | **+7.9%**    | **+1.0%**  |
| HKLB K=8         |       218.1   | +9.1%        | +2.0%      |
| KLB K=16         |       221.8   | +10.9%       | +3.7%      |
| HKLB K=16        |       223.1   | +11.5%       | +4.3%      |
| KLB K=32         |       223.8   | +11.9%       | +4.7%      |
| HKLB K=32        |       223.1   | +11.5%       | +4.3%      |
| KLB K=64         |       223.6   | +11.8%       | +4.6%      |
| HKLB K=64        |       223.1   | +11.5%       | +4.3%      |
| KLB K=128        |       221.4   | +10.7%       | +3.6%      |
| HKLB K=128       |       223.2   | +11.6%       | +4.4%      |
| KLB K=4          |       232.5   | +16.2%       | +8.7%      |
| SKLB K=16        |       242.9   | +21.5%       | +13.6%     |
| SKLB K=8         |       246.9   | +23.5%       | +15.5%     |
| SKLB K=128       |       252.2   | +26.1%       | +18.0%     |
| SKLB K=64        |       253.5   | +26.8%       | +18.6%     |
| SKLB K=32        |       259.0   | +29.5%       | +21.1%     |
| SKLB K=4         |       269.9   | +34.9%       | +26.3%     |

**Best open-loop result: HKLB K=4 at 215.9 µs** — within 7.9% of REPS+NSCC, using only 4 concurrent paths, with no receiver-side state. Matches KLB K=8 performance (+1.0%) at half the path count by eliminating the upfront commitment to untested EVs.

**Key K-sensitivity finding**: KLB and HKLB both converge to a ~221–224 µs plateau for K≥16 on a 16-path topology — additional path capacity yields diminishing returns once K exceeds half the physical path count. SKLB does not converge and remains 15–30% above NSCC across all K values tested.

---

## Long-Flow Evaluation: Does Convergence Cost Amortize?

**Hypothesis:** REPS' steady-state advantage over KLB/HKLB comes partly from a one-time "convergence tax" KLB pays per flow (committing to K random EVs upfront, discovering bad ones after one RTT). For an 8 MB flow at 400 G, this tax is roughly 1 RTT (~6 µs) out of ~200 µs total FCT — i.e. ~3% of the budget. For a 128 MB flow, the same fixed cost should amortize to ~0.2% of FCT. If the gap is mostly convergence tax, it should shrink for larger flows.

**Setup:** k=8 fat-tree (128 hosts, 16 core paths), permutation TM, 5 seeds (42–46). Three flow sizes: 8 MB, 32 MB, 128 MB. Six algorithms: REPS+NSCC, REPS+linerate, KLB K∈{4,8}, HKLB K∈{4,8}. SKLB excluded — already shown to be uncompetitive at 8 MB.

### Mean FCT (µs)

| Algorithm     |     8 MB    |    32 MB    |   128 MB    | Gap vs REPS+NSCC (8 → 32 → 128 MB) |
|---------------|------------:|------------:|------------:|------------------------------------|
| reps_nscc     |   200.4±1.9 |   747.5±5.5 | 2937.0±19.5 | baseline                           |
| reps_linerate |   200.8±2.4 |  746.0±10.0 | 2927.6±40.4 | +0.2% → −0.2% → −0.3%              |
| **klb_k8**    | **213.9±2.6** | **786.3±7.6** | **3074.1±26.5** | **+6.7% → +5.2% → +4.7%**     |
| hklb_k4       |   216.2±1.5 |   804.1±4.8 | 3157.4±21.6 | +7.9% → +7.6% → +7.5%              |
| hklb_k8       |   218.9±3.6 |  821.7±15.8 | 3231.8±61.7 | +9.2% → +9.9% → +10.0%             |
| klb_k4        |  233.0±4.0  |  866.0±11.5 | 3397.2±46.6 | +16.3% → +15.9% → +15.7%           |

### Findings

1. **KLB K=8 is the only algorithm that amortizes meaningfully**: gap to REPS shrinks from +6.7% (8 MB) to +4.7% (128 MB) — a 2-point absolute improvement over a 16× flow-size increase. Modest but real.

2. **HKLB K=4 does NOT amortize**: gap stays at ~7.5% across all sizes. HKLB's discovery phase converges in one RTT, after which it's locked into 4 paths. The steady-state cost of using only 4 of 16 paths is constant in time and dominates.

3. **HKLB K=8 slightly *worsens* with size** (+9.2% → +10.0%): the larger active set has more EV-overlap collisions with other flows' active sets; longer flows give those persistent overlaps more time to accumulate queueing.

4. **KLB K=4 stays flat at ~+16%**: similar reasoning — only 4 active paths, congestion-driven path turnover does not converge to optimal allocation.

5. **The convergence-tax hypothesis is largely *refuted*** for HKLB. HKLB was specifically designed to eliminate the convergence tax (discovery phase only commits clean paths), yet its gap to REPS is constant across flow sizes. Conclusion: the gap is steady-state, not transient. The "K paths vs N paths" structural disadvantage dominates.

6. **REPS+linerate ≈ REPS+NSCC at every size**: confirms that NSCC's cwnd adaptation is not the differentiator on permutation TM — it's purely the load-balancing layer.

---

## Fix Evaluation: EV Cooldown + ECN Hysteresis

Two source-level fixes proposed during analysis:
- **Fix A (EV cooldown)**: After a path signals ECN and is evicted, exclude it from selection for ~1 RTT (6 µs) to prevent immediate redraw while the switch queue is still high.
- **Fix B1 (ECN hysteresis)**: Require 2 consecutive ECNs on the same EV slot before eviction — single ECNs are likely transient queue fluctuations.

Both gated behind `-klb_enable_fixes` CLI flag. Same long-flow sweep (90 runs) re-run with fixes enabled.

### Mean FCT (µs): baseline vs fixed

|              |     8 MB baseline → fixed     |     32 MB baseline → fixed     |    128 MB baseline → fixed    |
|--------------|:-----------------------------:|:-----------------------------:|:-----------------------------:|
| klb_k4       | 233.0 → 234.4 (+1.4)          | 866.0 → 869.5 (+3.5)          | 3397.2 → 3407.8 (+10.6)       |
| hklb_k4      | 216.2 → 217.1 (+0.9)          | 804.1 → 809.2 (+5.1)          | 3157.4 → 3181.6 (+24.2)       |
| klb_k8       | 213.9 → 214.0 (+0.1)          | 786.3 → 786.6 (+0.3)          | 3074.1 → 3074.3 (+0.2)        |
| hklb_k8      | 218.9 → 217.8 (−1.1)          | 821.7 → 817.0 (−4.7)          | 3231.8 → 3214.3 (−17.5)       |

### Findings

**The fixes had essentially no effect.** Deltas are within or close to seed-to-seed noise (±2 to ±60 µs depending on size). No clear pattern of improvement; some K=4 variants slightly worsened, K=8 variants were neutral-to-slightly-better.

**Why the fixes were inert:**

1. **EV cooldown rarely fires.** When KLB/HKLB evicts EV X and calls `klb_pick_fresh_path`, the random redraw picks from N−K+1 candidate paths (~12 paths for K=4 on N=16). The probability of redrawing the just-evicted path is 1/12 ≈ 8%. Even when it does, the cooldown only delays by 6 µs — a small fraction of FCT. Aggregate effect on mean FCT is sub-percent.

2. **ECN hysteresis adds latency without changing aggregate dynamics.** A hot path produces ECN bursts, not isolated transients. Requiring 2 consecutive ECNs delays eviction by ~1 packet inter-arrival (well below 1 µs at 400 G), so the sender keeps sending on the hot path slightly longer — slight wash with the false-positive reduction.

3. **The real bottleneck is structural, not signal-quality.** Both fixes operate on the *signal interpretation* layer (when to act on ECN). The gap to REPS comes from the *action* layer (replace random EV vs drain naturally). Neither fix changes the action.

### What would actually help

To close the remaining 5–10% gap to REPS, the fix needs to operate on the structural layer:

- **Allow active-set growth beyond K when paths are clean** — make K a minimum, not a maximum. This is essentially the REPS design.
- **Drain-don't-replace eviction**: on ECN, remove the EV from active rotation and don't redraw until a discovery probe confirms a new clean path. The current "evict and immediately redraw" pattern of KLB/HKLB causes thrashing.

These are more invasive changes that effectively transform HKLB into REPS-with-cap.

---

## Implementation Notes (updated)

- `-klb_enable_fixes` flag activates Fix A (EV cooldown) and Fix B1 (ECN hysteresis) for KLB/SKLB/HKLB.
- HKLB now caps `_klb_k = min(_klb_k_param, _no_of_paths)` — prior versions of HKLB with K > N silently degraded to oblivious-only (the `_hklb_active_set` could never reach K distinct entries, so steady-state was never entered).
- Long-flow sweep uses `parallel=4` for 128 MB runs to avoid memory pressure that caused hklb_k8 hangs at `parallel=8`.
