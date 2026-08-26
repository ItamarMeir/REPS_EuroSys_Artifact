# exp02 — LB-buffer dynamics under `-load_balancing_algo freezing` (paper-REPS)  (v2)

**Status:** Findings preserved from notes; raw plots and data were lost between sessions before being archived to the repo. Regeneration recipe at the bottom.

**LB algorithm:** `-load_balancing_algo freezing` — **this is the paper's REPS**. Uses a fixed 8-slot `CircularBufferREPS<int>` ([buffer_reps.cpp:5](../../htsim/sim/buffer_reps.cpp#L5): `repsBufferSize = 8`) matching the paper's "less than 25 bytes of per-connection state" claim. We use `freezing` not `reps` everywhere in our state-aware work after discovering 19 of 25 paper-script experiments use this algorithm, not the simpler `reps`.

## What we ran

The same 6 instrumented scenarios as exp01, re-run with `-load_balancing_algo freezing`:

| Tag | Topology | Workload | `-paths` |
|---|---|---|---:|
| X1 | k=8 3-tier | pure permutation 128 × 8 MB | 16 |
| X2 | k=8 3-tier | pure permutation 128 × 8 MB | 64 |
| X3 | k=8 3-tier | pure permutation 128 × 8 MB | 65535 |
| X4 | k=8 3-tier | composite (96 elephant + 256 mice + 64 incast) | 64 |
| X5 | k=8 2-tier | pure permutation 128 × 8 MB | 64 |
| X6 | 1024-host 3-tier | pure permutation 1024 × 16 MB | 64 |

Each scenario run twice: vanilla NSCC vs state-aware NSCC. No failures. Instrumentation columns: `time_us, src_id, ecn, fresh, recycle, cwnd_pkts, exp_avg_ecn`. The meaningful observable here is `fresh` — bounded [0..8] under FREEZING because `processEv_freezing` ([uec.cpp:2661-2665](../../htsim/sim/uec.cpp#L2661-L2665)) calls `circular_buffer_reps->add(path_id)` on every PATH_GOOD ACK, and the buffer's 8 slots cap the count.

## Key findings (compared to v1 under `reps`)

| Observable | v1 (REPS, unbounded `_next_pathid`) | v2 (FREEZING, bounded `fresh ∈ [0..8]`) |
|---|---|---|
| Mean buffer fill | 4-11 (no cap) | 1.5-2.7 |
| Max ever observed | ~200 | 8 (cap) |
| `corr(fill, ECN)` per ACK | −0.09 to +0.04 (essentially 0) | **−0.21 to −0.24** |
| `P(ECN | fill = 0)` | undefined (unbounded list rarely 0) | **≈ 1.0 in every scenario** |
| Δ at ECN events | −0.5 to −1.1 (same mechanism) | −0.55 to −0.83 |

The headline finding from v2: **`fresh = 0` ⇒ next ACK is almost certainly ECN-marked**, across every workload and topology tested. This is the cleanest LB-state-as-CC-signal observation in the whole study.

The bounded buffer also makes the per-event signal more interpretable: a dip from 2 → 1 is a 50% reduction in available paths, whereas the same dip in an unbounded list of size 100 is invisible noise.

## Why this study mattered

It established that **the paper's bounded REPS buffer is a good predictor of imminent congestion** when it empties. The v3 sweep (exp03) then tested whether *acting on* this signal (via the state-aware CC ECN-masking gate) actually improves end-to-end FCT under failure — and found the architecture fires correctly but the FCT effect is small once the leaf exception is in place.

It also surfaced the architectural hypothesis preserved in [`reps_buffer_cache_idea.md`](/root/.claude/projects/-home-itamar-WSL-Clones-REPS-EuroSys-Artifact/memory/reps_buffer_cache_idea.md): if `fresh = 0` predicts ECN with near-certainty, maybe the buffer should *cache* known-good EVs (multiple draws per slot) rather than invalidate per draw — `repsMaxLifetimeEntropy` is the existing knob to flip.

## Regeneration recipe

```bash
# Build (one-time)
cd htsim/sim && make -j 8 && cd datacenter && make -j 8 && cd ../../..

# Pick a scenario, e.g., X4 (composite)
HTSIM=htsim/sim/datacenter/htsim_uec
TOPO=htsim/sim/datacenter/topologies/reps/fat_tree_128_1os_3t_400g.topo
TM=experiments/workloads/composite.cm

# Vanilla FREEZING with instrumentation
$HTSIM -sack_threshold 4000 -end 5000 -seed 20 -sender_cc_only \
       -sender_cc_algo nscc -topo $TOPO -tm $TM -paths 64 \
       -linkspeed 400000 -ecn 25 76 -q 100 -cwnd 151 \
       -load_balancing_algo freezing -disable_tor_ecn \
       -log_reps_state /tmp/v2_X4_vanilla.csv \
       -log_reps_state_src 0 -log_reps_state_src 32 \
       -log_reps_state_src 64 -log_reps_state_src 96 \
       > /tmp/v2_X4_vanilla.out

# State-aware FREEZING — same CLI plus -state_aware_ecn
```

Vary `-topo` and `-paths` per the scenario table. Note `-disable_tor_ecn` is now in every command — the leaf exception was the v3-discovered prerequisite for clean results.

## Related

- exp01 — same study under `reps` algorithm (different code path; outputs also lost).
- exp03 — the matrix sweep that built on this study's findings (full artifacts preserved).
- [ARCHITECTURE.md](../ARCHITECTURE.md) — explains the FREEZING vs REPS distinction.
- [Project memory `reps-buffer-cache-idea`](/root/.claude/projects/-home-itamar-WSL-Clones-REPS-EuroSys-Artifact/memory/reps_buffer_cache_idea.md).
