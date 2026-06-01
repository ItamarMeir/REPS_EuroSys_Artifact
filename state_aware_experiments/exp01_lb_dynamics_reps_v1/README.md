# exp01 — LB-buffer dynamics under `-load_balancing_algo reps`  (v1)

**Status:** Findings preserved here from notes; raw plots and data were lost between sessions before being archived to the repo. Regeneration recipe at the bottom.

**LB algorithm:** `-load_balancing_algo reps` — a code-only variant of REPS in this htsim fork that uses an unbounded `std::list<uint16_t> _next_pathid` ([uec.h:653](../../htsim/sim/uec.h#L653)) for the active good-path set. **This is NOT the paper's REPS.** The paper's REPS corresponds to `-load_balancing_algo freezing` (see exp02), which uses an 8-slot bounded `CircularBufferREPS`. v1 was conducted under the misapprehension that `reps` was the paper's algorithm; v2 corrects that.

## What we ran

Instrumented per-ACK buffer-state logging across 6 scenarios (no failures, all healthy networks):

| Tag | Topology | Workload | `-paths` |
|---|---|---|---:|
| X1 | k=8 3-tier | pure permutation 128 × 8 MB | 16 |
| X2 | k=8 3-tier | pure permutation 128 × 8 MB | 64 |
| X3 | k=8 3-tier | pure permutation 128 × 8 MB | 65535 |
| X4 | k=8 3-tier | composite (96 elephant + 256 mice + 64 incast) | 64 |
| X5 | k=8 2-tier | pure permutation 128 × 8 MB | 64 |
| X6 | 1024-host 3-tier | pure permutation 1024 × 16 MB | 64 |

Each scenario was run twice — vanilla NSCC vs state-aware NSCC (`-state_aware_ecn`) — to compare CC behavior with and without ECN-masking. Per-ACK CSV instrumentation columns: `time_us, src_id, ecn, fresh, recycle, cwnd_pkts, exp_avg_ecn` (where `fresh = circular_buffer_reps->getNumberFreshEntropies()` and `recycle = _next_pathid.size()`).

## Key findings

1. **Wrong column.** Under `-load_balancing_algo reps`, `processEv_REPS` ([uec.cpp:2307-2320](../../htsim/sim/uec.cpp#L2307-L2320)) only pushes to `_next_pathid` and never to `circular_buffer_reps`. So the instrumentation column `fresh` stayed at **0** in every scenario. The meaningful observable for this algorithm is `recycle` (the deque length).

2. **`_next_pathid` is unbounded.** Mean queue depth ranged from 4 to 11 across scenarios, with maxima up to ~200 entries. Under sustained PATH_GOOD streams it grows without limit — completely unlike the paper's 8-slot bounded buffer.

3. **Δ at ECN consistently negative.** Across all 6 scenarios, the mean change in `_next_pathid.size()` at an ECN-marked ACK was −0.5 to −1.1 entries. Mechanism: ECN-marked ACK doesn't push the EV back into the deque (`processEv_REPS` only pushes on PATH_GOOD), but draws continue, so net Δ is negative.

4. **Dip-and-recover.** Aligning all ECN events showed the deque dipping at offset 0 and recovering to its pre-event level within ~1-3 ACKs. The recovery rate exceeded the dip rate in healthy mode.

5. **Per-ACK absolute deque size is NOT predictive of ECN.** Pearson correlation `corr(recycle, ECN)` ranged from −0.09 to +0.04 across scenarios — essentially zero. The instantaneous size is too noisy to gate the CC.

## Why this study mattered

It motivated the v2 re-run with the paper's actual REPS (`freezing` algorithm). Under FREEZING, the buffer is bounded to 8 slots, `fresh` actually moves in [0..8], and the predictive signal becomes meaningful (see exp02 README).

## Regeneration recipe

If you want to reproduce v1 results:

```bash
# Build (one-time)
cd htsim/sim && make -j 8 && cd datacenter && make -j 8 && cd ../../..

# Pick a scenario, e.g., X2 (paths=64 perm)
HTSIM=htsim/sim/datacenter/htsim_uec
TOPO=htsim/sim/datacenter/topologies/reps/fat_tree_128_1os_3t_400g.topo
TM=htsim/sim/datacenter/connection_matrices/perm_n128_s8388608.cm

# Vanilla run with instrumentation on 4 sources
$HTSIM -sack_threshold 4000 -end 5000 -seed 20 -sender_cc_only \
       -sender_cc_algo nscc -topo $TOPO -tm $TM -paths 64 \
       -linkspeed 400000 -ecn 25 76 -q 100 -cwnd 151 \
       -load_balancing_algo reps -disable_tor_ecn \
       -log_reps_state /tmp/v1_X2_vanilla.csv \
       -log_reps_state_src 0 -log_reps_state_src 32 \
       -log_reps_state_src 64 -log_reps_state_src 96 \
       > /tmp/v1_X2_vanilla.out

# State-aware run — same CLI plus -state_aware_ecn
# ... (analogous)
```

For all 6 scenarios, vary `-topo` and `-paths` per the table above. The CSV columns are described in [`../ARCHITECTURE.md`](../ARCHITECTURE.md). Plotting was done by ad-hoc Python (matplotlib + pandas) scripts that were also lost; you'd need to re-author them, but the per-ACK columns directly support time-series + histogram + aligned-ECN-trajectory analyses.

## Related

- exp02 — same study redone with the paper's REPS (preserved with all artifacts).
- [ARCHITECTURE.md](../ARCHITECTURE.md) — the `-state_aware_ecn` flag and the instrumentation it enables.
- [Project memory `reps-buffer-cache-idea`](/root/.claude/projects/-home-itamar-WSL-Clones-REPS-EuroSys-Artifact/memory/reps_buffer_cache_idea.md) — design idea that emerged from this work.
