# Workloads

Shared traffic matrices used across `exp01`, `exp02`, `exp03`. All target a 128-host topology unless noted.

## Quick reference

| Name | TM path | Flows | Total bytes | Has incast? | Has mice? |
|---|---|---|---:|---|---|
| pureperm | `../../htsim/sim/datacenter/connection_matrices/perm_n128_s8388608.cm` (reused, not copied) | 128 × 8 MB | ~1 GB | no | no |
| composite | `composite.cm` | 416 (96+256+64) | ~942 MB | yes (4 hotspots, 16:1) | yes (256 × 32 KB) |
| mice-heavy | `mice_heavy.cm` | 272 (16+256) | ~72 MB | no | yes (256 × 32 KB) |
| elephant-heavy | `elephant_heavy.cm` | 64 × 16 MB | ~1 GB | no | no |

Generators: `gen_composite.py`, `gen_v3_workloads.py`. Both write next to themselves; no `/tmp/` paths. Re-run any time to regenerate.

---

## pure permutation (reused from `htsim/`)

- **TM file**: `htsim/sim/datacenter/connection_matrices/perm_n128_s8388608.cm`
- 128 flows × 8 MB each, all starting at t = 0
- Each host is source of exactly one flow and destination of exactly one flow (random permutation)
- **Class assignment in this study**: all flows → `elephant`

Stress-tests the LB's spatial distribution. No incast, no latency-sensitive flows. On a non-blocking topology with sufficient `-paths`, this should be near-optimal in vanilla mode.

## composite

- **TM file**: `composite.cm` (regenerate with `python3 gen_composite.py`)
- **416 flows**, three classes:

| Class | ids | Flow count | Size each | Start time | Notes |
|---|---|---:|---:|---|---|
| elephant | 1-96 | 96 | 8 MB | t = 0 | random src→dst sample (rng seed 20) |
| mice | 97-352 | 256 | 32 KB | 16 waves of 16, every 25 μs starting at t = 10 μs | random src/dst per flow |
| incast | 353-416 | 64 | 2 MB | all at t = 80 μs | 4 hotspots × 16 senders → 1 victim; victims = {3, 41, 77, 119} |

Note the **incast deliberately starts at t = 80 μs**, which is inside the failure window (50→200 μs) for all failure scenarios in exp03. This is the richest workload — it exercises mice latency, elephant throughput, and destination incast all concurrently while the network is degraded.

## mice-heavy

- **TM file**: `mice_heavy.cm` (regenerate with `python3 gen_v3_workloads.py`)
- **272 flows**, two classes:

| Class | ids | Flow count | Size each | Start time |
|---|---|---:|---:|---|
| elephant | 1-16 | 16 | 4 MB | t = 0 (background load) |
| mice | 17-272 | 256 | 32 KB | 8 waves of 32, every 30 μs starting at t = 10 μs |

Latency-sensitive workload. Each mouse is small enough to complete in ~1 RTT under healthy conditions. The 16 elephants provide background contention.

## elephant-heavy

- **TM file**: `elephant_heavy.cm` (regenerate with `python3 gen_v3_workloads.py`)
- **64 flows × 16 MB each**, all start at t = 0
- Random src→dst permutation across 64 selected senders (the other 64 hosts are idle)
- **Class assignment**: all flows → `elephant`

Bandwidth-saturated regime with *larger and fewer* flows than pure-perm. Different spatial pattern (only half the topology participates).

---

## Class-id ranges used by the aggregator

The `v3_aggregate.py` script classifies each finished flow into mice/elephant/incast based on its `flowId`, using the same boundaries listed above. If you author new workloads, either:
1. Match these boundaries (ids 1..96 elephant, 97..352 mice, 353..416 incast for composite-style), or
2. Update `CLASS_BY_WORKLOAD` in `exp03_matrix_sweep_v3/scripts/v3_aggregate.py` to add your new workload's classifier function.

---

## File-format notes

The TM tokenized parser at [`htsim/sim/datacenter/connection_matrix.cpp:752-799`](../../htsim/sim/datacenter/connection_matrix.cpp#L752-L799) treats numeric `start` as **picoseconds** when an `id` field is present in the same line. All our generators emit `start <us * 1_000_000>` to encode microseconds correctly. The fallback non-id parser at line 688 instead treats `start` as `double` microseconds, which is a different format — easy to mix up.

Class assignment is purely by id-range convention; the file format itself has no class field. Don't reorder generators or skip ids without also updating the aggregator's classifier.

---

## Paper workloads (MSwift/MNSCC, arXiv:2509.07907)

Reproduces the workloads from "Congestion Control for Spraying with Congested Paths" (Gerstein, Silberstein, Keslassy). One generator: `python3 gen_paper_workloads.py` — idempotent, writes 15 `.cm` files (5 families × 3 seeds).

| Workload | TM pattern | Flows | Per-flow size | Paper § |
|---|---|---|---|---|
| Baseline (perm + 4 ECMP) | `paper_baseline_s{42,43,44}.cm` | 4 ECMP + 124 sprayed | 64 MB / 8 MB | IV-B |
| Pure permutation | `…/connection_matrices/perm_n128_s8388608.cm` (reused, not regenerated) | 128 | 8 MB | IV-C |
| HSDP Llama-70B | `paper_hsdp_s{42,43,44}.cm` | 128 ring flows | 13,697,024 B (= 3344 × 4 KB) | IV-C |
| Incast 32→1 | `paper_incast32_s{42,43,44}.cm` | 32 | 8 MB | IV-E |
| Sensitivity: 16 MB messages | `paper_baseline_16mb_s{…}.cm` | 4 + 124 | 64 MB / 16 MB | IV-D Fig. 9 |
| Sensitivity: 8 ECMP flows | `paper_baseline_8ecmp_s{…}.cm` | 8 + 120 | 64 MB / 8 MB | IV-D Fig. 10 |

**Topology**: paper uses a 128-host 3-tier fat-tree at 800 Gbps → run against [`htsim/sim/datacenter/topologies/reps/fat_tree_128_1os_3t_800g.topo`](../../htsim/sim/datacenter/topologies/reps/fat_tree_128_1os_3t_800g.topo).

### Paper simulator settings (§IV-A Settings)

Verbatim from the paper, plus the htsim flag values that approximate each one (assuming the ~4 KB packet size htsim uses).

| Paper quantity | Value | htsim flag (≈ 4 KB MTU; queue/cwnd units are packets) |
|---|---|---|
| Topology | 3-layer non-blocking fat-tree, 128 nodes | `-topo .../fat_tree_128_1os_3t_800g.topo` |
| Link bandwidth | 800 Gbps | `-linkspeed 800000` |
| Link latency | 0.5 µs per hop | encoded in the .topo file |
| Switch queue discipline | Standard droptail FIFO, ECN-enabled, **no packet trimming** | htsim default |
| Per-port buffer | **800 KB** | `-q 200` (200 × 4084 B ≈ 800 KB) |
| ECN marking threshold | **40 KB** | `-ecn 10 50` (low = 10 pkts ≈ 40 KB; high = 50 pkts ≈ 200 KB — paper does not specify a high threshold, judgment call) |
| Packet size (MTU) | **4 KB** (RoCEv2-sized) | smoke tests show htsim emits 4084 B/pkt; pair with `-sack_threshold 4000` |
| Target queueing delay (Swift / NSCC) | **≈ 1 µs** | NSCC default in this build (matches paper's apples-to-apples comparison) |
| Initial cwnd | **Ideal value = BDP** (paper: "set each initial cwnd to its ideal value … rather than waiting many RTTs to converge", §IV-A) | `-cwnd 100` (BDP at 800 G × ~4 µs RTT ÷ 4 KB ≈ 100 pkts) |
| Sprayed flow LB | OPS, AR, REPS | this repo only implements REPS (paper's REPS = `-load_balancing_algo freezing`) |
| Background ECMP elephants | Single-path | **not supported in htsim's global `-load_balancing_algo`** — documented in the ECMP-vs-sprayed caveat below |

**Important**: prior experiments in this repo (exp01–exp10) use `-q 100 -ecn 25 76 -cwnd 151`, which translates to ~400 KB buffer / 100 KB low-ECN-threshold / 151-pkt cwnd at 4 KB MTU — **roughly half the buffer and 2.5× the ECN threshold of the paper's configuration**. As a result, our prior 800 G runs (exp10 redo) saw zero ECN ACKs across all 192 cells. Use the paper-faithful flags above (`-q 200 -ecn 10 50 -cwnd 100`) when comparing against paper results; this regime is the one in which their ECN/median-based mechanisms engage.

### Class-id ranges

- `paper_baseline_s*` / `paper_baseline_16mb_s*`: ids **1-4** = ECMP elephants (64 MB), ids **5-128** = sprayed permutation.
- `paper_baseline_8ecmp_s*`: ids **1-8** = ECMP elephants (64 MB), ids **9-128** = sprayed permutation.
- `paper_hsdp_s*`: ids **1-128** = ring flows (logical i → logical (i+8) mod 128, with seeded random physical placement).
- `paper_incast32_s*`: ids **1-32** = senders, all → a single seeded victim.

All flows start at `t = 0`.

### Fidelity to the paper

| Workload | Fidelity | What's approximated |
|---|---|---|
| Pure permutation | **Exact** | — |
| Incast 32→1 | **Exact** | — |
| HSDP | **Exact to the paper's analytical model** | The paper itself is a simplified model (rings + per-flow packet count), not a real Llama-70B trace. |
| Baseline / 16MB / 8ECMP | **Structural match with caveats** | (1) Paper says "long-lived" without specifying ECMP-elephant size — we use 64 MB. (2) htsim has no per-flow LB selector (see below). |

**Caveat — ECMP vs sprayed**: htsim's `-load_balancing_algo` is **global**. The "ECMP elephant" IDs in the baseline TMs identify which flows the paper would have routed via ECMP; in practice they will use whichever LB the simulator was invoked with — i.e. they become long-lived sprayed elephants that produce equivalent in-network congestion. Splitting LB per-flow would require an htsim code change.

### Skipped paper sensitivities (not workload properties)

- **Scale-to-250-host** — needs an 800 Gbps 250-host topo (only 400 Gbps exists: `fat_tree_250_1os_3t_400g.topo`).
- **1 % random link failures** — use the `-fail_link_target` / `-fail_link_time` simulator flags.
- **DRR fair switch scheduling** — switch-config, not TM.
