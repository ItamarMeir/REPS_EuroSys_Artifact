# exp05 — Paper Workloads: Buffer Size & EV Domain Sweep

**Status**: In progress.

---

## Motivation

exp04 tested the same two REPS design axes (buffer size and EV domain) on our custom workloads (perm_128MB, composite). This experiment repeats the sweep using **the paper's own workloads** (paper - SMARTT-REPS) — `perm_n128_s8388608.cm` and `test_symm16.cm` — and follows **the paper's script and figure structure** directly (self-contained Python scripts, fig_12-style CDF, fig_8-style max-FCT lines, fig_1-style port utilisation, fig_13-style balls-in-bins). This enables direct comparison with the paper's published baseline.

---

## Topology & Workloads

**Topology**: `fat_tree_128_1os_2t_400g.topo` — 2-tier, 128 hosts, 400 Gbps — **matching paper's fig_12**.

| Name | File | Flows | Size | Start | Pattern |
|---|---|---|---|---|---|
| `perm_n128` | `perm_n128_s8388608.cm` | 128 | 8 MB each | t=0 | Full-bisection permutation (fixed TM, same as fig_12) |
| `symm16` | `test_symm16.cm` | 8 | 16 MB each | t=0 | Symmetric: host 0→64, 1→65, …, 7→71 (same as fig_1) |

Physical path diversity in a k=8 2-tier fat-tree: **16 distinct cross-pod paths**.

---

## Common Simulator Flags

```
-sack_threshold 4000 -end 5000 -sender_cc_only -sender_cc_algo nscc
-topo fat_tree_128_1os_2t_400g.topo -linkspeed 400000
-ecn 25 76 -q 100 -cwnd 151
-load_balancing_algo freezing -disable_tor_ecn
```

- `-end 5000` (5 ms): all flows complete well within this window (ideal FCT ≤ 340 µs).
- `-sender_cc_algo nscc`: consistent with exp04. The paper uses `mprdma`; this is intentional — we study NSCC behaviour.
- `-disable_tor_ecn`: mandatory with `-sender_cc_only` (see CLAUDE.md gotcha).
- Vanilla FREEZING only (no `-state_aware_ecn`) — isolates the LB axis.

**Failure**: `sev=0` = no failure; `sev=1` = one Agg↔Core link fails at t=50 µs, restores at t=200 µs (`-fail_link_time 50 200 -fail_link_target 0 0`).

**Seeds**: 42, 43, 44.

---

## Design Matrices

### Part A — Buffer size sweep (fig_buf_sweep.py)

- `reps_buffer_size` ∈ {1, 2, 4, 8, 1024}; fixed `-paths 65535`
- FCT runs: 5 × 2 workloads × 2 sev × 3 seeds = 60 runs
- cwnd runs: 5 × perm_n128 × sev=1 × seed=42 = 5 runs
- Port-util runs: 5 × symm16 × 2 sev × seed=42 = 10 runs
- **Total: 75 runs**

### Part B — EV domain sweep (fig_ev_sweep.py)

- `-paths` ∈ {32, 256, 65535} — **matching paper's fig_12 sweep exactly**; fixed `-reps_buffer_size 1024`
- FCT runs: 3 × 2 workloads × 2 sev × 3 seeds = 36 runs
- cwnd runs: 3 × perm_n128 × sev=1 × seed=42 = 3 runs
- Port-util runs: 3 × symm16 × 2 sev × seed=42 = 6 runs
- **Total: 45 runs**

### Part C — Balls-in-bins (fig_ballsbins.py)

Pure Python analytical simulation — no htsim. Instantaneous.

---

## How to Run

```bash
# Balls-in-bins (instant, no simulator)
python3 fig_ballsbins.py

# Buffer sweep (~25 minutes)
python3 fig_buf_sweep.py

# EV sweep (~15 minutes)
python3 fig_ev_sweep.py
```

All scripts are **idempotent** — safe to re-run; already-completed runs are skipped.

---

## Figures

### Part A — Buffer sweep

| File | Description |
|---|---|
| `A1_fct_cdf_buf_perm_n128.png` | FCT CDF per buf — perm_n128 (like fig_12) |
| `A1_fct_cdf_buf_symm16.png` | FCT CDF per buf — symm16 |
| `A2_max_fct_vs_buf.png` | Max FCT vs buffer size with slowdown annotations (like fig_8) |
| `A3_port_util_buf.png` | Per-uplink throughput, buf=∞ vs buf=1 (like fig_1 — routing efficiency) |
| `A4_cwnd_timeseries_buf.png` | CC window over time per buffer size (CC behaviour) |

### Part B — EV domain sweep

| File | Description |
|---|---|
| `B1_fct_cdf_ev_perm_n128.png` | FCT CDF per EV count — perm_n128 (directly comparable to paper's fig_12) |
| `B1_fct_cdf_ev_symm16.png` | FCT CDF per EV count — symm16 |
| `B2_max_fct_vs_ev.png` | Max FCT vs EV domain (like fig_8) |
| `B3_port_util_ev.png` | Per-uplink throughput, EV=64K vs EV=32 (routing efficiency) |
| `B4_cwnd_timeseries_ev.png` | CC window over time per EV count |

### Part C — Balls-in-bins

| File | Description |
|---|---|
| `C1_ballsbins_ev_domain.png` | Avg max queue vs EV domain (extends paper's fig_13) |
| `C2_ballsbins_buf_size.png` | Avg max queue vs buffer size (novel — analytical backing for Part A) |

**Key insight from C1/C2**: both axes work through the same mechanism (effective port diversity = min(axis_value, physical_ports)). The cliff at 16 paths is the topology ceiling; values below 16 cause super-linear queue growth.

---

## Relationship to Paper Figures

| This exp | Paper figure | Analogy |
|---|---|---|
| B1 (perm_n128, no fail) | fig_12 (EV sweep CDF) | Direct comparison — same workload, topology, EV values |
| A3, B3 | fig_1 (port util timeseries) | Same `portSwitch_LowerPod_0_.txt` parsing |
| A2, B2 | fig_8 (max FCT vs sweep) | Same annotation style |
| C1 | fig_13 (balls-in-bins) | Same simulation, extended to our EV range |
| C2 | fig_13 (balls-in-bins) | Novel — buffer-size parameterised variant |

---

## Lineage

| Predecessor | Relationship |
|---|---|
| exp04 | Same two axes on different workloads (perm_128MB, composite, 3-tier topology) |
| paper fig_12 | B1 is directly comparable; EV values {32, 256, 65535} match exactly |
| paper fig_13 | C1 extends to our EV range; C2 is novel |

---

## Findings

### Summary

Both the buffer size (Part A) and EV domain (Part B) axes have **smaller effects** on the paper's workloads than on exp04's heavy custom workloads. The reason: `perm_n128` (8 MB, ideal FCT ≈ 172 µs) and `symm16` (16 MB, ideal FCT ≈ 340 µs) are short-lived flows that complete in ≪ 1 ms; the CC window never has time to converge, congestion is mild, and the topology's 8 uplinks naturally spread even a single-path FREEZING sender. The EV domain axis is still visible and directionally matches paper fig_12; the buffer size axis is essentially invisible at these flow sizes.

---

### Part A — Buffer size sweep

**FCT is nearly flat across all buffer sizes.**

| buf | perm_n128 max FCT | slowdown vs ideal | symm16 max FCT | slowdown vs ideal |
|---|---|---|---|---|
| 1   | 186.4 µs | +8.5% | 351.0 µs | +3.4% |
| 2   | 185.3 µs | +7.9% | 351.0 µs | +3.4% |
| 4   | 184.9 µs | +7.6% | 351.0 µs | +3.4% |
| 8   | 184.7 µs | +7.5% | 351.0 µs | +3.4% |
| ∞ (1024) | 184.7 µs | +7.5% | 351.0 µs | +3.4% |

*(ideal: perm_n128 = 171.8 µs, symm16 = 339.5 µs; means over 3 seeds, sev=0 shown — sev=1 identical, see below)*

- **Verdict: buffer size does not matter for these workloads.** The total FCT spread across buf=1 to buf=∞ is only **1.7 µs** for perm_n128 and **0 µs** for symm16. This is consistent with exp04's Part A finding (also nearly flat), but here the effect is even weaker because the flows are far shorter.

- **Failure is not visible (sev=0 ≡ sev=1).** FCT is identical with and without the injected failure across all buffer values. Root cause: `-fail_link_target 0 0` specifies agg=0, core=0 in a 2-tier topology where that coordinate may not correspond to a valid link. The simulator does log "Scheduled dynamic link failure: fail at 50 us" (scheduling succeeds), but no path is disrupted. **The failure injection should be revisited for the 2-tier topology before drawing conclusions about failure recovery.**

- **CC window is flat at 153 packets for all buffer configurations.** NSCC starts with cwnd = `-cwnd 151` MSS = 153 packets. Flows complete before NSCC can respond to any congestion signals (completion at ≈ 183 µs; propagation RTT = 4 µs → NSCC needs multiple RTTs to adapt). The cwnd timeseries plots (A4) show a constant horizontal line.

- **Port utilization is identical across all buffer values.** All 8 uplinks of LS0 are utilised (8/8) with a load imbalance of **1.02×** for every buffer size including buf=1. This is consistent with the balls-in-bins analysis (C2): with 8 FREEZING senders each maintaining an independent single-slot buffer, they collectively happen to spread across 8 distinct uplinks even at buf=1. The relevant insight is that FREEZING's effective diversity depends on the number of independent senders, not just the buffer size per sender, when the flow count equals the uplink count.

---

### Part B — EV domain sweep

**EV domain has a small but visible effect, matching the paper's fig_12 direction.**

| EV domain | perm_n128 max FCT | slowdown vs ideal | symm16 max FCT | slowdown vs ideal |
|---|---|---|---|---|
| 32       | 189.6 µs | +10.4% | 375.2 µs | +10.5% |
| 256      | 185.0 µs | +7.7%  | 352.4 µs | +3.8%  |
| 65535    | 184.7 µs | +7.5%  | 351.0 µs | +3.4%  |

*(means over 3 seeds; sev=0 shown — sev=1 identical for same failure-injection reason as Part A)*

- **EV=32 causes a modest FCT penalty**: +5 µs (+2.7%) for perm_n128 and +24 µs (+7.1%) for symm16 relative to EV=64K. Both are statistically meaningful (consistent across seeds). **EV=256 already saturates**: the difference between EV=256 and EV=64K is ≤ 2 µs for both workloads.

- **Port utilization directly confirms the EV domain effect:**

| EV domain | Uplinks used | Load imbalance |
|---|---|---|
| 32     | 7/8 | 1.26× |
| 256    | 8/8 | 1.11× |
| 65535  | 8/8 | 1.02× |

  EV=32 misses one uplink and distributes load 26% less evenly. EV=64K achieves near-perfect spread. This mirrors the paper's fig_1 port utilisation result and provides a causal explanation for the FCT difference.

- **CC window is flat at 153 packets for all EV configurations**, same as Part A. The EV domain effect on FCT is driven purely by load balancing (routing to fewer paths), not by CC backing off more aggressively.

- **Comparison with exp04 Part B (3-tier, heavy workloads):** exp04 found dramatic FCT degradation at ev_domain=1 (5× inflation, flows failing to complete). Here the effect is much smaller (10% at EV=32) because: (1) flows are shorter so timing constraints are less tight; (2) the 2-tier topology has a different physical path structure; (3) EV=32 is still a large domain (not single-path). The directional finding agrees: **larger EV domain = better**, with diminishing returns above the physical path count.

---

### Part C — Balls-in-bins

**Both axes work through the same fundamental mechanism: effective output-port diversity.**

- **C1 (EV domain):** Queue depth grows super-linearly below 16 effective ports. The critical cliff is at EV=16 (= number of physical cross-pod paths in a k=8 2-tier fat-tree). EV values above 16 are equivalent — min(ev, 16) = 16. Values below 16 cause O(n/k) queue growth where k is effective ports.

- **C2 (buffer size):** Buffer size maps to effective diversity via min(buf, 16). buf=1 gives a single persistent path → queue grows as O(n). buf≥16 achieves the theoretical minimum (same as buf=∞). The analytical cliff is at buf=16, consistent with C1.

- **Key insight:** Both axes are projections of the same underlying variable — effective output-port diversity. The buffer size axis works through stale-path persistence (small buffer → same EV reused → same path always taken), while the EV domain axis works through hash-space compression (small domain → multiple senders hash to same port). At the physical path ceiling (16 for this topology), adding more EVs or larger buffers yields no additional benefit.

- **Why buf=1 doesn't hurt much in practice (reconciling C2 with Part A):** The analytical model assumes all N packets in a round go to the same port for buf=1. In practice, with 8 independent FREEZING senders each having their own buf=1 buffer, the single slot per sender is independently initialized to a random EV. The aggregate behavior is closer to 8-path diversity (one path per sender) than 1-path — hence the empirical 1.02× imbalance even at buf=1.

---

### Cross-cutting observations

1. **These workloads are too short-lived to stress CC.** The 2-tier topology with 8 MB and 16 MB flows at 400 Gbps completes in ≪ 1 ms. NSCC's cwnd adaptation requires multiple RTTs. For any conclusion about CC behaviour under path restriction, the experiments should use either: (a) larger flows (≥ 32 MB as in exp04), or (b) a 3-tier topology where propagation RTT is longer.

2. **Failure injection requires debugging for the 2-tier topology.** The `-fail_link_target 0 0` coordinates that work in a 3-tier topology appear not to correspond to a real link in the 2-tier topology. Future experiments on this topology should identify valid agg↔core link indices from the topology file and use those.

3. **EV domain findings are consistent with paper fig_12.** The paper reports that reducing EV domain from 65535 to 32 degrades FCT; our B1 plots replicate this qualitatively. The magnitude differs (paper uses mprdma CC; we use nscc with `-cwnd 151`).

4. **Buffer size finding matches exp04.** Both experiments find FCT is flat across buffer sizes, with at most a few percent difference. The 8-slot default is sufficient; the design is robust to buffer size across both heavy and lightweight workloads.
