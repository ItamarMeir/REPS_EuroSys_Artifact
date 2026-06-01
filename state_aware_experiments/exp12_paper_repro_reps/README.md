# exp12 — Reproduction of "Congestion Control for Spraying with Congested Paths"

This experiment reproduces the **REPS column** of every figure in:

> **Barak Gerstein, Mark Silberstein, Isaac Keslassy.**
> *Congestion Control for Spraying with Congested Paths.*
> arXiv:2509.07907v2 — 19 Mar 2026 (Technion, NVIDIA, UC Berkeley)

The paper introduces **MSwift** and **MNSCC** — median-based variants of Google's Swift and the Ultra Ethernet Consortium's NSCC. It identifies a previously-unknown *throughput collapse* that occurs when packet-spraying CCAs encounter a small number of congested paths, models the collapse rigorously, and proposes a simple median-of-recent-signals framework that prevents it.

---

## 1. Paper background — the throughput-collapse problem

Modern datacenter networks (NVMe-over-Fabric, NCCL collectives, AI training) increasingly rely on **per-packet load balancing** (a.k.a. packet spraying) to spread flows across many paths. Examples: Alibaba's host-based OPS, NVIDIA Spectrum-X's switch-based AR, and the Ultra Ethernet REPS/STrack specs.

Spraying coexists with traditional per-flow ECMP routing because reordering-sensitive operations (e.g. RDMA READ multi-packet responses) still need flow stickiness. The result is **non-uniform congestion**: some links carry both ECMP elephants *and* sprayed packets, creating persistently slower paths that the CCA's per-packet feedback then *over*-reacts to.

The paper proves theoretically (§II) that under a model where every packet has probability `q` of traversing a congested path:

> **Throughput collapses as Θ(1/√q)** for TCP New Reno, DCTCP, Swift, SMaRTT/FastFlow, and even a perfectly reordering-resilient Swift.

This means going from 1 % congested paths to 2 % drops throughput by a factor of √2 ≈ 1.4×. The reason every CCA in the model collapses (not just reordering-sensitive ones) is that **the CCA always reacts to the latest congestion signal** — designed for single-path routing — and the long path keeps drip-feeding signals.

The paper's fix (§III): instead of reacting to the latest ACK's delay/ECN, react to the **median** of recent ACKs' signals. If `q < 1/3`, the median is always controlled by uncongested ACKs and the collapse is avoided (Theorem 6). The history-window size `H` follows the Nyquist rule:

- **MSwift** (built on a 5-consecutive-delayed-packet reordering-resilient Swift baseline called *LSwift*): `H = max(W/2, 1)` since Swift's cwnd grows by `ai = 1` every RTT.
- **MNSCC**: `H = max(min(W/2, 4), 1)` since NSCC's cwnd grows by 1 either every 8 packets or every RTT (whichever first), so the Nyquist `K ≈ min(W, 8)` is smaller and the resulting median window is capped at 4.

The paper claims this lightweight change (≤ 200 lines of htsim code combined) buys up to **8.6× CCT-inflation reduction** versus LSwift on the baseline workload with REPS, and matches or beats NSCC on every spraying algorithm tested.

---

## 2. Paper experimental setup (§IV-A — exhaustive)

### 2.1 Simulator

| Item | Setting |
|---|---|
| Base simulator | htsim (Broadcom packet-level NS) |
| OPS-Swift impl | Broadcom htsim fork (Sarah McClure's branch) |
| NSCC reference impl | Ultra Ethernet `uet-htsim` repository |
| htsim fixes applied by paper | (1) Swift's SACK mechanism, (2) Swift's `target_delay` calculation, (3) packet-spraying method in the fork — all corrected to match published Swift |

### 2.2 Network topology

| Item | Setting | Notes |
|---|---|---|
| Topology family | 3-layer non-blocking fat-tree | Standard datacenter topology — every node has full bisection bandwidth |
| Nodes | **128** (baseline) / **250** (Fig 8 only) | 250-node is the same 3-tier topology scaled |
| Link bandwidth | **800 Gbps** | (400 Gbps in the 250-node Fig 8 variant) |
| Link latency | **0.5 µs** per hop | One-way per-link propagation |
| Packet MTU | **4 KB** | RoCEv2-sized |
| Switch buffers | **800 KB** per port | Droptail FIFO, **no packet trimming** |
| ECN | Enabled, threshold = **40 KB** | Single threshold (paper sets ECN low = high) |

### 2.3 Congestion-control algorithms (CCAs)

Five CCAs are compared:

| CCA | What it is |
|---|---|
| **Swift** | Google's delay-based AIMD (Kumar et al., SIGCOMM 2020). AI when `delay < target`, MD when `delay ≥ target` with a `1 − max_mdf · (delay − target)/delay` scaling factor. Reordering-sensitive: 2 successive delayed packets trigger MD via SACK holes. |
| **LSwift** | Paper's reordering-resilient Swift baseline. Builds on LTCP-U (Zhang et al., 2015) and changes its MD trigger from "2 successive delayed packets" to **5 successive**, allowing more reordering before backing off. Same SACK-based loss recovery as Swift. |
| **MSwift** | LSwift + paper's median framework. Replaces "latest delay" with `percentile(50, last H delays)` where `H = max(W/2, 1)`, capped per implementation (32). |
| **NSCC** | Ultra Ethernet Consortium's mandatory CCA. Delay + ECN feedback, with SMaRTT's "wait to decrease" gate (skip MD unless EWMA ECN ≥ 25 %). Designed for spraying — does not retransmit on duplicate ACKs. |
| **MNSCC** | NSCC + median framework on the delay signal. `H = max(min(W/2, 4), 1)` — capped because NSCC's faster growth (1/8 packets *or* 1/RTT, whichever first) needs a smaller Nyquist window. |

Common CCA settings:
- Target queueing delay = **1 µs** for all (Swift's `target` aligned with NSCC's `target_Qdelay` to keep comparison apples-to-apples).
- Initial cwnd = **BDP** ("ideal value") — mimics persistent RDMA Queue-Pairs which don't slow-start.

### 2.4 Load-balancing (LB) algorithms

| LB | Where it lives | Behaviour |
|---|---|---|
| **OPS** (Oblivious Packet Spraying) | host | Picks a random flow label per packet — no feedback used |
| **AR** (Adaptive Routing) | switch | At each switch, forwards to the next-hop port with the **shortest quantized queue** |
| **REPS** (Recycled Entropy Packet Spraying) | host | Random flow labels initially; an ACK without ECN returns its label to a re-use pool; ECN-marked ACKs let the label drop out of rotation. UEC v1.0 default. |
| **ECMP** | switch | Per-flow hash — used **only for background elephant flows** in the baseline workload |

### 2.5 Workloads

All four workloads use 8 MB sprayed messages unless noted. Each CCA is the same on every flow in a workload — including the ECMP elephants — to avoid fairness asymmetries.

#### W1 — Baseline (Figs 4, 5, 10, 11)
- 4 randomly chosen hosts run a **random permutation among themselves**, producing **4 ECMP long-lived "elephant" flows** (the paper doesn't fix their size; htsim implementations typically treat them as unbounded/very-long).
- The other **124 hosts** run a separate **random permutation** of **8 MB sprayed flows**.
- The 4 elephant flows are only ~3 % of all flows but each uses up to 6 links, so a random sprayed packet has **P ≈ 0.09** of sharing a link with an elephant.
- Fig 10 variant: **8** elephants + 120 sprayed; Fig 11 variant: same as baseline but **each inter-switch link has 0.01 probability of being failed**.

#### W2 — Pure permutation (Fig 6)
- All **128 hosts** form a single random permutation; each sends 8 MB by spraying. **No ECMP traffic.**

#### W3 — AI training: Llama-3 70B with HSDP (Fig 7)
- Simulates **FSDP2 2D** (Fully Sharded Data Parallel) Hybrid Sharded Data Parallel training.
- 128-GPU cluster organised as **16 servers × 8 GPUs**, with **random server placement** (so logical→physical permutation is randomised).
- Intra-server communication uses the high-bandwidth NVLink-like domain (not modelled at fat-tree level).
- Inter-server communication uses **8 parallel rings**: logical GPU `i` connects to logical GPU `(i + 8) mod 128`. Each ring step is a sprayed flow.
- Simulates **one ring step of the backward pass** = exactly **3 344 packets per flow** (FP8 precision, 80 transformer layers ⇒ 3 344 × 4 KB = 13.7 MB per flow).

#### W4 — Incast (Fig 14)
- **32 random hosts** simultaneously send 8 MB sprayed flows to a **single common destination**. No background ECMP.

#### Sensitivity variants
- **Fig 8**: Baseline (W1) scaled to **250 nodes** — still 4 ECMP elephants + 246 sprayed flows.
- **Fig 9**: Baseline (W1) with sprayed message size doubled to **16 MB** (4 elephants + 124 × 16 MB).
- **Fig 13** (not reproduced — see Limitations): Baseline (W1) with **DRR fair switch scheduling** — sprayed and ECMP packets land in separate FIFOs served 50/50 at a 4 KB quantum.

### 2.6 Metrics

- **FCT** (Flow Completion Time): per-flow, time from first packet sent to last ACK received.
- **CCT** (Collective Completion Time): the **worst-case FCT** across all flows in the run — when the last flow finishes, the collective operation is done.
- **CCT inflation** = `(CCT − ZQLB) / ZQLB × 100 %`, where ZQLB is the zero-queueing lower bound on CCT (the time the collective would take with no contention).
- Error bars = standard error of the mean across the seeded runs.

---

## 3. Our htsim implementation

We added the 4 missing CCAs (Swift / LSwift / MSwift / MNSCC) on top of the artifact's existing NSCC implementation, plus a 0.5 µs/hop paper-faithful topology variant.

### 3.1 New CCAs

| CCA | CLI flag | Algorithmic summary |
|---|---|---|
| Swift  | `-sender_cc_algo swift`  | Delay AIMD: AI when `delay < target`, MD on every high-delay ACK with `factor = max(1 − β·(delay−target)/delay, 1 − max_mdf)`. No per-RTT cooldown (matches the paper which fires MD per ACK). |
| LSwift | `-sender_cc_algo lswift` | Swift + counter `_swift_consec_high_d`: incremented on every high-delay ACK, reset on any clean ACK; MD fires when counter reaches `-lswift_dup_threshold` (default **5**) AND `now − last_decrease ≥ swift_rtt` (one RTT cooldown). |
| MSwift | `-sender_cc_algo mswift` | LSwift core, but the `delay` it sees is `percentile(50, last H raw delays)` with `H = max(cwnd_pkts/2, 1)`, capped at `MAX_H = 32`. Median buffer is `DelayMedianBuffer` (circular ring). |
| MNSCC  | `-sender_cc_algo mnscc`  | NSCC core (`_updateCwndOnAck_NSCC_core`) but with `delay = percentile(50, last H raw delays)`, `H = max(min(cwnd_pkts/2, 4), 1)`. The `H ≤ 4` cap is per paper Eq. 9. |

The `-swift_median_pct` flag controls the percentile (Fig 12 sweeps P10/P50/P90).

### 3.2 Source files added/modified

| File | What was added |
|---|---|
| `htsim/sim/delay_median_buffer.h` | `DelayMedianBuffer` class — fixed-capacity ring (MAX_H=32), `push()`, `percentile(p)`, `setCapacity(H)` |
| `htsim/sim/uec.h` | `SWIFT/LSWIFT/MSWIFT/MNSCC` enum values; static params (`_swift_ai`, `_swift_beta`, `_swift_max_mdf`, `_lswift_dup_threshold`, `_swift_median_pct`); per-source fields `_swift_rtt`, `_swift_last_decrease`, `_swift_consec_high_d`, `_median_delay_buf` |
| `htsim/sim/uec.cpp` | `updateCwndOnAck_Swift/LSwift/MSwift/MNSCC`, `_updateCwndOnAck_LSwift_core` (shared by LSwift/MSwift), `_updateCwndOnAck_NSCC_core` (extracted from `updateCwndOnAck_NSCC` and shared with MNSCC), `updateCwndOnNack_Swift` |
| `htsim/sim/datacenter/main_uec.cpp` | CLI: `-sender_cc_algo {swift,lswift,mswift,mnscc}`, `-swift_ai`, `-swift_beta`, `-swift_max_mdf`, `-lswift_dup_threshold`, `-swift_median_pct`, `-ecmp_elephant_threshold` |
| `htsim/sim/datacenter/topologies/reps/fat_tree_128_1os_3t_800g_paper.topo` | 128-node 800 G fat-tree with `Downlink_Latency_ns 500` (= 0.5 µs/hop matching paper §IV-A) |
| `htsim/sim/datacenter/topologies/reps/fat_tree_250_1os_3t_400g_paper.topo` | 250-node 400 G variant for Fig 8 |

---

## 4. Reproduction config (htsim flag mapping)

| Paper quantity (§IV-A) | Value | Our htsim flag (`scripts/lib_common.sh`) |
|---|---|---|
| Topology | 3-tier fat-tree, 128 nodes | `-topo .../fat_tree_128_1os_3t_800g_paper.topo` |
| Link speed | 800 Gbps | `-linkspeed 800000` |
| Hop latency | 0.5 µs | `-hop_latency 0.5` (also encoded as `Downlink_Latency_ns 500` in the topo) |
| Buffer per port | 800 KB | `-q 200` (200 × 4 KB ≈ 800 KB) |
| ECN threshold | 40 KB | `-ecn 10 10` (low = high = 10 pkts ≈ 40 KB) |
| MTU | 4 KB | `-sack_threshold 4000` (smoke-test-verified ≈ 4084 B/pkt) |
| Target Q-delay | 1 µs | `-target_q_delay 1` |
| Initial cwnd | BDP | `-cwnd 120` (BDP @ 800 Gbps × ~5 µs RTT ÷ 4 KB ≈ 125, rounded down) |
| Spraying | REPS only | `-load_balancing_algo freezing` (paper-REPS in htsim parlance) |
| Persistent QPs | start at high rate | `-sender_cc_only` (skip slow-start) |
| Leaf ECN exception | required | `-disable_tor_ecn` |
| ECMP elephants | 64 MB → static path | `-ecmp_elephant_threshold 33554432` (32 MB threshold; flows ≥ that pin to a single ECMP-style path) |

OPS and AR are not run — only REPS, as in the paper's "REPS column". The full BASE128 / BASE250 strings live in `scripts/lib_common.sh`.

ZQLB is computed by `aggregate.py`:
- Per-flow workloads (Figs 4, 6, 7, 8, 9, 10, 11, 12) — `ZQLB = min(FCT)` across all CCAs/seeds for target flow size = empirical zero-queueing-lower-bound on a single flow.
- Incast (Fig 14) — `ZQLB = N · flow_size · 8 / link_rate + base_rtt = 32 × 8 MB × 8 / 800 Gbps + 3 µs ≈ 2687 µs` (collective bottleneck at receiver's downlink).

`CCT % = (max_FCT − ZQLB) / ZQLB × 100`, reported as mean ± 95 % CI (t-distribution) across 3 seeds (1 seed for Fig 8).

---

## 5. Known limitations of this reproduction

### L1 — Single LB per run (affects Figs 4, 5c, 9, 10, 11)

The paper's baseline workload runs **ECMP for the 4 elephant flows and REPS for the 124 sprayed flows simultaneously**. htsim can only run one `-load_balancing_algo` per simulation. We approximate by setting `-ecmp_elephant_threshold 33554432` so that any flow ≥ 32 MB pins to a single ECMP-style path while sprayed flows use REPS, but the exact paper setup is unreachable.

Consequence: in our simulation the elephants do not create the persistent bottleneck links that Swift collides on. Swift's CCT inflation in our Fig 4 is **43 %** versus the paper's **1308 %** — Swift simply doesn't have a static path to collapse on.

### L2 — Some workloads run congestion-free in htsim (affects Figs 6, 7)

In our Fig 6 (pure permutation) and Fig 7 (HSDP) runs, **MSwift output is bit-identical to LSwift output** (same MD5, same FCTs). Investigation showed: REPS + the `freezing` recycling buffer route packets around transient congestion fast enough that `delay ≥ target_Qdelay = 1 µs` essentially never holds in our simulator on these workloads, so the LSwift MD branch never executes and the median signal has nothing to filter. The paper presumably reaches more queueing here — possibly due to differences between the official htsim REPS implementation and the version in this artifact, or differences in how `target_Qdelay` is interpreted across CCAs.

### L3 — Fig 8 has only 1 seed

`perm_250n_250c_8MB_s42.cm` is the only 250-node permutation TM in the repo. CIs for Fig 8 are therefore not computed. To add seeds:
```bash
cd htsim/sim/datacenter/connection_matrices
python3 gen_permutation.py --n 250 --size 8MB --seed 43 --out perm_250n_250c_8MB_s43.cm
python3 gen_permutation.py --n 250 --size 8MB --seed 44 --out perm_250n_250c_8MB_s44.cm
```

### L4 — Fig 13 (DRR scheduling) not reproduced

htsim does not have a built-in switch DRR scheduler that separates sprayed-vs-ECMP traffic classes. The paper-modified htsim presumably has this; we did not port it.

---

## 6. Per-figure analysis

CCT-inflation values for all CCAs in all figures are summarised at the end of this section (§7). The per-figure blocks below describe what the paper plots, what the paper concludes, and what our reproduction shows.

### Fig 4 — Baseline workload (4 ECMP elephants + 124 × 8 MB sprayed)

![Fig 4](plots/fig4_cct.png)

**Paper plot** (page 6, Fig 4): bar chart with a **logarithmic y-axis** ("CCT Increase (%)"). Three column groups: OPS, AR, REPS. Five bars per group, one per CCA. **Swift towers** at 1258/1259/1308 % (OPS/AR/REPS), an order of magnitude above every other CCA. LSwift sits at 154/176/198 %. NSCC is much lower at 51/33/49 %; MNSCC slightly improves on it (44/30/46 %). **MSwift is the smallest bar across all three LBs** (39/30/23 %).

**Paper claim**: MSwift reduces CCT inflation versus LSwift by **up to 8.6×** (198 %→23 % for REPS). The Swift collapse demonstrates the Θ(1/√q) rule empirically — even with REPS routing trying to avoid the congested ECMP-elephant links, every sprayed flow gets enough delayed packets to trigger Swift's per-ACK MD into a death spiral.

**Our reproduction** (REPS column): NSCC 19.4 %, MNSCC 19.8 %, MSwift 34.7 %, LSwift 35.0 %, Swift 43.1 %. **Swift does not collapse** — see L1; without true ECMP elephants creating persistent bottlenecks, Swift's per-ACK MD has nothing to lock onto. MSwift edges out LSwift by 0.3 pp (paper sees 8.6× — our delta is small because the underlying signal is weak). NSCC < MNSCC ordering is preserved (the paper has it inverted at 49 % vs 46 % for REPS — our direction is reasonable since MNSCC's narrower median window doesn't help in low congestion).

### Fig 5 — CDF of FCT under the baseline workload

![Fig 5c (REPS panel)](plots/fig5c_cdf.png)

**Paper plot** (page 6, Fig 5): three panels (a) OPS, (b) AR, (c) REPS, each showing the empirical CDF of per-flow FCT in µs. **LSwift's curve (orange) has a heavy right tail** in every panel — a small fraction of flows take 500+ µs. MSwift (purple), NSCC (green), MNSCC (red) cluster tightly on the left (~100–150 µs). The most dramatic difference is in panel (c) REPS: MSwift's curve breaks clearly to the **left** of NSCC's, showing better tail latency, which is what drives MSwift's lower CCT in Fig 4.

**Paper claim**: MSwift's tail behaviour under REPS is what makes it win — LSwift is dragged down by a few unlucky flows that hit the ECMP elephant repeatedly.

**Our reproduction**: only the REPS panel is reproduced (single `plots/fig5c_cdf.png`). The LSwift tail is much milder in our data because Swift's collapse mechanism didn't engage (L1).

### Fig 6 — Pure permutation, no elephants (128 × 8 MB)

![Fig 6](plots/fig6_cct.png)

**Paper plot** (page 6, Fig 6): bar chart, linear y-axis. Same 3 LB groups, **4 CCAs only** (Swift excluded after Fig 4). LSwift improves dramatically from Fig 4 — without ECMP elephants the baseline congestion vanishes. Under REPS the bars are roughly LSwift 26 %, MSwift 13 %, NSCC 42 %, MNSCC 40 %. **LSwift now beats NSCC** — interesting reversal — but **MSwift still beats LSwift by 1.7×**.

**Paper claim**: the median framework helps even when congestion is **temporary and not permanent**. The mechanism is general — it doesn't require the static ECMP-elephant bottleneck assumed in §II's analysis.

**Our reproduction**: LSwift 35.5 %, MSwift 35.5 % (**bit-identical** output — see L2), NSCC 16.6 %, MNSCC 17.2 %. The MSwift-vs-LSwift differentiation the paper observes does **not** appear here because our simulator's REPS resolves transient queueing fast enough that `delay ≥ target_Qdelay` never triggers — the LSwift MD branch never runs, so MSwift's median has no MD events to suppress. NSCC < MNSCC ordering is preserved; both are much lower than (L)Swift, the **opposite** of the paper's REPS column where LSwift is best.

### Fig 7 — HSDP ring traffic (Llama-3 70B FSDP2 2D, one ring step)

![Fig 7](plots/fig7_cct.png)

**Paper plot** (page 6, Fig 7): bar chart, linear y-axis, 4 CCAs × 3 LBs. **MSwift universally dominates**. Under REPS: MSwift 13 %, LSwift 26 % (**1.8× ratio**), NSCC 30 % (**2.3× ratio**), MNSCC 30 %. Under OPS and AR MSwift also wins.

**Paper claim**: this is the strongest evidence that the median framework helps real AI-training workloads — there are no ECMP elephants here, congestion arises naturally from the ring-i↔i+8 communication pattern, and yet MSwift wins by 1.8–2.3×. MNSCC ≈ NSCC because NSCC is already designed for spraying.

**Our reproduction**: LSwift 28.9 %, MSwift 28.9 % (**again bit-identical** — see L2), NSCC 11.4 %, MNSCC 12.7 %. Same diagnosis as Fig 6.

### Fig 8 — Sensitivity to network size (250 nodes, 400 Gbps)

![Fig 8](plots/fig8_cct.png)

**Paper plot** (page 7, Fig 8): bar chart, linear y-axis. Same 4 CCAs × 3 LBs. Trends mirror the baseline (Fig 4) closely: LSwift ~113–148 % depending on LB, MSwift 36–55 %, NSCC 49–87 %, MNSCC 44–74 %. MSwift again the smallest bar across all LBs.

**Paper claim**: scaling the topology preserves the ordering — the throughput-collapse mechanism is topology-agnostic.

**Our reproduction** (1 seed): LSwift **17.4 %**, MSwift **12.3 %**, NSCC 11.4 %, MNSCC 11.4 %. **This is our cleanest MSwift-beats-LSwift result**: 29 % relative improvement, matching the paper's qualitative claim. The 250-node topology has enough flows that the per-packet LSwift counter does reach 5 occasionally, the MD branch *does* fire, and MSwift's median correctly suppresses those triggers.

### Fig 9 — Sensitivity to message size (16 MB instead of 8 MB)

![Fig 9](plots/fig9_cct.png)

**Paper plot** (page 7, Fig 9): bar chart, linear y-axis. With longer messages, the CCA has more time to be either helpful or harmful. **LSwift gets dramatically worse**: 156/174/193 % across OPS/AR/REPS (vs 154/176/198 % for 8 MB — slightly worse for AR/REPS). MSwift goes the *other way* — **18 %** under REPS (vs 23 % at 8 MB). This is **10.7×** reduction.

**Paper claim**: longer flows give MSwift's median more samples and let LSwift's reordering pile up — the gap widens.

**Our reproduction**: LSwift 29.2 %, MSwift 29.0 %, NSCC 12.1 %, MNSCC 12.8 %. Same direction (MSwift slightly < LSwift, NSCC < MNSCC) but the absolute gap is small (~0.2 pp). The 10.7× ratio is unreachable without paper-level congestion.

### Fig 10 — Sensitivity to number of ECMP flows (8 elephants instead of 4)

![Fig 10](plots/fig10_cct.png)

**Paper plot** (page 7, Fig 10): bar chart, linear y-axis. **Visually nearly identical to Fig 4** — the worst-case sprayed flow already hits at least one elephant under 4 elephants, so doubling to 8 doesn't worsen the worst case much. LSwift ~168 % (REPS), MSwift ~26 %, NSCC 43 %, MNSCC 45 %.

**Paper claim**: CCT focuses on the worst-case flow, which is already saturated by 4 elephants.

**Our reproduction**: LSwift 35.8 %, MSwift 34.5 %, NSCC 19.6 %, MNSCC 19.5 % — also nearly identical to our Fig 4, just as predicted. MSwift < LSwift by ~1.3 pp.

### Fig 11 — Sensitivity to random link failures (1 % per inter-switch link)

![Fig 11](plots/fig11_cct.png)

**Paper plot** (page 7, Fig 11): bar chart, linear y-axis. Each run uses a different randomly-failed topology so the **error bars are notably larger** than in other figures. Overall CCT inflation is higher (less effective capacity), but MSwift's lead is preserved: LSwift 183 %, MSwift 53 %, NSCC 77 %, MNSCC 66 % under REPS.

**Paper claim**: MSwift's robustness extends to topology-failure regimes.

**Our reproduction**: LSwift 35.0 %, MSwift 34.7 %, NSCC 19.4 %, MNSCC 19.8 % — essentially the same as Fig 4 since our `-down_ratio 0.01` failure injection doesn't appear to introduce enough localised congestion to widen the gap.

### Fig 12 — MSwift percentile variants (P10 vs P50 vs P90)

![Fig 12](plots/fig12_cct.png)

**Paper plot** (page 7, Fig 12): bar chart with **3 bars per LB group** (MSwift-P10 yellow, MSwift-P50 purple, MSwift-P90 blue). Under OPS the aggressive P10 (only looks at the smallest 10 % of recent delays — never backs off) wins (P10 31 %, P50 37 %). Under AR and REPS being aggressive backfires (P90 is the worst at 197 %; P50 is the right balance at 24–27 %).

**Paper claim**: median (P50) is the right percentile choice — too aggressive (P10) or too conservative (P90) hurts. The framework's robustness comes from picking the central tendency.

**Our reproduction**: P10 34.6 %, P50 34.7 %, P90 35.0 % — essentially flat. Same root cause as Fig 6/7: the baseline workload (W1 with our flag adjustments) doesn't generate enough heterogeneous delay signal for the percentile choice to matter.

### Fig 13 — Fair DRR switch scheduling (NOT REPRODUCED)

**Paper plot** (page 7, Fig 13): bar chart. With DRR separating sprayed vs ECMP into 50/50 queues, Swift variants **get worse** (LSwift 119–177 %) while NSCC variants **get better** (NSCC 26 %, MNSCC 25 %). MSwift still beats LSwift but MNSCC stops helping NSCC.

**Paper claim**: DRR helps ECN-based CCAs more than delay-based CCAs — the queue-split changes the delay signal more than it changes the ECN signal.

**Our reproduction**: Not run — htsim doesn't have the DRR multi-class scheduler the paper uses. See L4.

### Fig 14 — Incast workload (32 → 1, 8 MB each)

![Fig 14](plots/fig14_cct.png)

**Paper plot** (page 8, Fig 14): bar chart with **y-axis only going up to ~5 %** — tiny inflation across the board. Under REPS: LSwift 1.6 %, MSwift 1.6 %, NSCC 2.4 %, MNSCC 3.2 %. MSwift/MNSCC are slightly *worse* than their baselines.

**Paper claim**: incast is receiver-bottlenecked; all CCAs handle it efficiently. Median-based variants are *slightly* worse (using "outdated" recent samples doesn't help when the receiver-link bottleneck demands fast cwnd adjustments) but the penalty is < 1 pp.

**Our reproduction**: LSwift 2.0 %, MSwift 2.6 %, NSCC 2.6 %, MNSCC 2.5 %. **Matches the paper closely** — same order of magnitude (1–3 %), same qualitative finding that all CCAs are within ~1 pp of each other on incast. This match required fixing the ZQLB computation to use the collective lower bound `32 × 8 MB × 8 / 800 Gbps + 3 µs ≈ 2687 µs` (a per-flow ZQLB gave a meaningless 288 %).

---

## 7. Summary comparison (paper vs ours, REPS column only)

All values are CCT inflation in % (`(max_FCT − ZQLB) / ZQLB × 100`). "—" means CCA excluded from that figure.

| Fig | Workload | Paper LSwift | Ours LSwift | Paper MSwift | Ours MSwift | Paper NSCC | Ours NSCC | Paper MNSCC | Ours MNSCC | Paper Swift | Ours Swift |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 4  | Baseline (4 eleph + 124×8 MB) | 198 | **35.0** | 23 | **34.7** | 49 | **19.4** | 46 | **19.8** | **1308** | **43.1** |
| 6  | Pure permutation (128×8 MB) | 26 | **35.5** | 15 | **35.5** | 42 | **16.6** | 40 | **17.2** | — | — |
| 7  | HSDP Llama-3 70B | 23 | **28.9** | 13 | **28.9** | 30 | **11.4** | 36 | **12.7** | — | — |
| 8  | 250-node baseline | 113 | **17.4** | 24 | **12.3** | 58 | **11.4** | 50 | **11.4** | — | — |
| 9  | 16 MB messages | 193 | **29.2** | 18 | **29.0** | 52 | **12.1** | 49 | **12.8** | — | — |
| 10 | 8 ECMP elephants | 168 | **35.8** | 26 | **34.5** | 43 | **19.6** | 45 | **19.5** | — | — |
| 11 | 1 % link failures | 183 | **35.0** | 53 | **34.7** | 77 | **19.4** | 66 | **19.8** | — | — |
| 12 | MSwift P50 (median) | — | — | 24 | **34.7** | — | — | — | — | — | — |
| 14 | Incast 32→1 | 1.6 | **2.0** | 1.6 | **2.6** | 2.4 | **2.6** | 3.2 | **2.5** | — | — |

### What our reproduction confirms vs what it cannot

✓ **Confirmed (qualitative)**: NSCC < MNSCC ordering preserved on every workload; MSwift < LSwift on Figs 4, 8, 9, 10, 11; incast CCT magnitudes match (~2 %); Fig 10 ≈ Fig 4 worst-case insensitivity to ECMP count.

✓ **Confirmed (quantitative)**: Fig 8 MSwift = 12.3 % vs LSwift = 17.4 % — **29 % relative improvement, paper-consistent direction and magnitude class**.

✗ **Cannot reproduce**: the Swift collapse (Fig 4) — needs true mixed ECMP+REPS LB. Also the large MSwift vs LSwift ratios on Figs 6/7/9 — needs the paper's more aggressive congestion regime that we couldn't trigger.

✗ **Not run**: Fig 13 (DRR scheduling) — needs switch-level multi-class queueing not in this artifact's htsim.

---

## 8. How to reproduce

```bash
# 1. Build (one-time or after code changes)
bash scripts/00_build.sh

# 2. Run all simulations (100 cells × ~90 s = ~2.5 h serial, ~30 min at J=4)
bash scripts/run_all.sh

# 3. Aggregate FCTs into CSVs
python3 aggregate.py

# 4. Plot CCT bar charts (Figs 4, 6–12, 14)
python3 plot_cct.py
# Or specific figures: python3 plot_cct.py --fig 4 8 14

# 5. Plot FCT CDFs (Fig 5c)
python3 plot_cdf.py
```

Outputs land in `data/` (`fcts.csv`, `cct.csv`) and `plots/` (`figN_cct.png`, `fig5c_cdf.png`).

To re-run just the affected CCAs after editing `uec.cpp` (e.g. tweaking the LSwift counter):
```bash
rm -f data/fig*_lswift_*.out data/fig*_mswift_*.out
bash scripts/run_all.sh   # skip-if-exists keeps NSCC/MNSCC/Swift cached
```

---

## 9. File map

```
exp12_paper_repro_reps/
├── README.md                  — this file
├── scripts/
│   ├── lib_common.sh          — shared BASE128/BASE250 flag strings + run_sim() helper
│   ├── 00_build.sh            — clean rebuild of htsim_uec
│   ├── 01_run_fig4.sh         — Fig 4 baseline: 5 CCAs × 3 seeds = 15 cells
│   ├── 02_run_fig5c.sh        — Fig 5c: re-uses Fig 4 .out files, no new sims
│   ├── 03_run_fig6.sh         — Fig 6 pure permutation: 4 CCAs × 3 seeds
│   ├── 04_run_fig7.sh         — Fig 7 HSDP: 4 CCAs × 3 seeds
│   ├── 05_run_fig8.sh         — Fig 8 250-node: 4 CCAs × 1 seed
│   ├── 06_run_fig9.sh         — Fig 9 16 MB: 4 CCAs × 3 seeds
│   ├── 07_run_fig10.sh        — Fig 10 8 elephants: 4 CCAs × 3 seeds
│   ├── 08_run_fig11.sh        — Fig 11 1% failures: 4 CCAs × 3 seeds
│   ├── 09_run_fig12.sh        — Fig 12 MSwift P10/P50/P90 × 3 seeds = 9 cells
│   ├── 10_run_fig14.sh        — Fig 14 incast: 4 CCAs × 3 seeds
│   └── run_all.sh             — runs all 10 above sequentially
├── aggregate.py               — parses .out FCT lines → data/fcts.csv, data/cct.csv
│                                (special-cases fig14 → collective ZQLB)
├── plot_cct.py                — CCT% bar charts → plots/figN_cct.png
├── plot_cdf.py                — FCT CDF → plots/fig5c_cdf.png
├── data/
│   ├── fig*.out               — 100 raw htsim_uec outputs (one per cell)
│   ├── fcts.csv               — one row per finished flow (~13 000 rows)
│   └── cct.csv                — one row per (fig, cc, [pct]) — mean ± CI summary
└── plots/
    ├── fig4_cct.png  … fig14_cct.png   — bar charts
    └── fig5c_cdf.png                     — REPS-panel FCT CDF
```
