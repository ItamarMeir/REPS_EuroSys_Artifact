# exp03 — Matrix sweep: state-aware vs vanilla FREEZING (paper-REPS)

**Date:** 2026-05-19
**LB algorithm:** `-load_balancing_algo freezing` (the paper's REPS, 8-slot bounded buffer)
**Headline ask:** does state-aware NSCC+REPS help under failure, and at what cost in healthy state?

> **Methodology note (required for re-runs).** Passing `-sender_cc_only` (which most experiments do) sets `receiver_driven=false`, which at [main_uec.cpp:739](../../htsim/sim/datacenter/main_uec.cpp#L739) computes `ecn_on_tor_dl = !receiver_driven && !force_disable_tor_ecn = true`. The architecture's leaf exception requires the opposite. **Always pass `-disable_tor_ecn` for state-aware experiments.** The driver script in `scripts/v3_run_matrix.sh` does this; if you build a new driver, replicate the flag. (An earlier run of this matrix was conducted with leaf ECN accidentally enabled; its outputs are not preserved here, but the lesson is.)

---

## Topology

| Field | Value |
|---|---|
| File | `htsim/sim/datacenter/topologies/reps/fat_tree_128_1os_3t_400g.topo` |
| Type | Fat-tree, k=8, 3 tiers |
| Hosts | 128 |
| ToR switches | 32 (4 hosts each) |
| Aggregation switches | 32 (4 per pod × 8 pods) |
| Core switches | 16 |
| Link speed | 400 Gbps everywhere |
| Oversubscription | 1:1 (non-blocking) |
| Inter-pod physical paths | ~32 between any two hosts |

3-tier was chosen because the failure flag `-fail_link_target <agg> <core>` addresses Agg↔Core pipes (`pipes_nup_nc` / `pipes_nc_nup`). A 2-tier file would collapse the Agg/Core distinction.

After `-disable_tor_ecn`, the marking policy on this topology is:
- **Marked**: aggregation uplinks, core uplinks, aggregation downlinks toward ToRs (low=25 packets, high=76 packets).
- **NOT marked**: ToR downlinks toward servers (leaf exception).

## Workloads (4 classes)

See [`../workloads/README.md`](../workloads/README.md) for full descriptions.

| Workload | Flows | Class id ranges |
|---|---|---|
| pureperm | 128 × 8 MB at t=0 | all elephant |
| mice-heavy | 16 elephants (4 MB) + 256 mice (32 KB, 8 waves × 30 μs) | ids 1-16 elephant, 17-272 mice |
| elephant-heavy | 64 × 16 MB at t=0 | all elephant |
| composite | 96 elephants (8 MB) + 256 mice (32 KB, 16 waves) + 64 incast (4 hotspots × 16 → 1, 2 MB at t=80 μs) | 1-96 elephant, 97-352 mice, 353-416 incast |

## Experiment matrix

| Dimension | Values | # |
|---|---|---:|
| Workload | pureperm, mice, elephant, composite | 4 |
| Failure severity (# failed Agg↔Core links, cut at 50 μs → restore at 200 μs) | 0, 1, 2, 4, 8 | 5 |
| Mode | vanilla FREEZING vs state-aware FREEZING (`-state_aware_ecn`) | 2 |
| Seed | 20, 21, 22, 23, 24 | 5 |

**200 cells total**, ~8 min wall time on a single machine. The driver
(`scripts/v3_run_matrix.sh`) is idempotent — re-running skips cells whose
`.out` already shows a completion marker.

Metrics extracted per cell:
- Per-class FCT (median, p99) with 95% CI error bars over 5 seeds
- Failure-recovery cumulative throughput
- Event counts: pipe-fails / pipe-restores / FREEZING entries / FREEZING exits / state-aware flag flips / thaws
- Mann-Whitney U significance tests on per-flow FCT distributions (vanilla vs state-aware), markers `*` p<0.05, `**` p<0.01, `***` p<0.001

---

## Headline finding: state-aware mode has essentially no FCT impact on synthetic workloads once the leaf exception is in place

With leaf ECN correctly off, ECN at core/aggregation queues becomes rare; FREEZING's own freeze-on-RTO handles failures; and the CC's masked view of ECN almost doesn't matter. The architecture is *correct* and *fires when it should*, but the corner cases where it changes FCT are narrow.

### Composite p99 FCT (5-seed mean, μs)

| sev | class | vanilla | state-aware | Δ |
|---:|---|---:|---:|---:|
| 0 | incast | 821.8 | 807.4 | **−14.4** |
| 1 | incast | 819.4 | 807.4 | **−12.0** |
| 4 | incast | 821.9 | 815.1 | **−6.8** |
| 8 | incast | 811.5 | 811.1 | −0.4 |
| 0 | mice | 66.1 | 66.1 | 0.0 |
| 1 | mice | 68.6 | 71.9 | +3.3 |
| 8 | mice | 97.5 | 101.9 | +4.4 |
| 0 | elephant | 885.9 | 883.3 | −2.6 |
| 4 | elephant | 893.5 | 874.4 | **−19.1** |
| 8 | elephant | 889.9 | 882.8 | −7.0 |

Effects are mostly within noise (sub-5% of the metric). Strongest state-aware win is a 14 μs incast-p99 improvement in the healthy state.

### Across the other three workloads

State-aware vs vanilla deltas are **essentially zero or sub-microsecond** for every class at every severity. With the leaf exception in place there's no spurious ECN for the architecture to mask, so the modes converge.

---

## Plots

### Composite (the richest workload)

![composite p99 FCT vs severity](plots/composite_p99_vs_sev.png)

![composite median FCT vs severity](plots/composite_median_vs_sev.png)

![composite event counts vs severity](plots/composite_events_vs_sev.png)

![composite failure-recovery throughput, sev=4](plots/composite_throughput_recovery_sev4.png)

### Per-workload (mice / elephant / pure-perm)

| Workload | p99 | median | events | recovery |
|---|---|---|---|---|
| pureperm | [`pureperm_p99_vs_sev.png`](plots/pureperm_p99_vs_sev.png) | [`pureperm_median_vs_sev.png`](plots/pureperm_median_vs_sev.png) | [`pureperm_events_vs_sev.png`](plots/pureperm_events_vs_sev.png) | [`pureperm_throughput_recovery_sev4.png`](plots/pureperm_throughput_recovery_sev4.png) |
| mice-heavy | [`mice_p99_vs_sev.png`](plots/mice_p99_vs_sev.png) | [`mice_median_vs_sev.png`](plots/mice_median_vs_sev.png) | [`mice_events_vs_sev.png`](plots/mice_events_vs_sev.png) | [`mice_throughput_recovery_sev4.png`](plots/mice_throughput_recovery_sev4.png) |
| elephant-heavy | [`elephant_p99_vs_sev.png`](plots/elephant_p99_vs_sev.png) | [`elephant_median_vs_sev.png`](plots/elephant_median_vs_sev.png) | [`elephant_events_vs_sev.png`](plots/elephant_events_vs_sev.png) | [`elephant_throughput_recovery_sev4.png`](plots/elephant_throughput_recovery_sev4.png) |

---

## Event-count validation across all workloads

The state-aware wiring fires correctly at every cell:

| Workload | sev | V FREEZING_starts | SA FREEZING_starts | SA asymmetric-flag flips |
|---|---:|---:|---:|---:|
| composite | 0 | 0.0 | 0.0 | **0.0** |
| composite | 1 | 49.8 | 51.4 | **51.4** |
| composite | 4 | 61.0 | 60.2 | **60.2** |
| composite | 8 | 100.8 | 100.6 | **100.6** |
| pureperm | 8 | 60.0 | 60.0 | **60.0** |
| mice | 8 | 77.4 | 77.4 | **77.4** |
| elephant | 8 | 29.0 | 29.0 | **29.0** |

Across **all** workloads × severities:
- SA flag flips exactly equals SA FREEZING_starts (the v2 wiring holds at every cell).
- Both equal 0 at sev=0 (zero false positives across 40 healthy-state runs).

---

## Three concrete takeaways

1. **The leaf exception matters as much as the state-aware machinery.** Just turning on `-disable_tor_ecn` (without state-aware) makes mice p99 in healthy composite drop dramatically by preventing leaf CE-marking. Always pass this flag.
2. **State-aware mode is doing what it claims, but the FCT signal in synthetic workloads is small** once leaf ECN is off. The real-world value proposition is probably narrower than the bug-inflated numbers from the first run suggested — likely confined to short failure windows where REPS can't fully spread load.
3. **The buffer-fill gate (v4 idea) is more attractive, not less.** With leaf ECN off, `fresh = 0` events become rarer in composite. A future design that opens the CC gate on `fresh ≤ 1` would react to genuine core-side congestion rather than leaf incast.

---

## Reproducing this experiment

```bash
# 1. Build the simulator (if not already built)
cd htsim/sim && make -j 8 && cd datacenter && make -j 8 && cd ../../..

# 2. Regenerate workloads (idempotent)
cd state_aware_experiments/workloads
python3 gen_composite.py
python3 gen_v3_workloads.py
cd ..

# 3. Run the matrix (~8 minutes on a workstation; idempotent — re-run to fill missing cells)
exp03_matrix_sweep_v3/scripts/v3_run_matrix.sh

# 4. Aggregate raw .out files into the two CSVs
python3 exp03_matrix_sweep_v3/scripts/v3_aggregate.py

# 5. Regenerate plots
python3 exp03_matrix_sweep_v3/scripts/v3_plot.py
```

---

## Files

- `plots/` — 16 PNGs (4 plots × 4 workloads).
- `data/v3_data.csv` — 44 000 rows, one per finished flow.
- `data/v3_events.csv` — 200 rows, one per (workload, mode, sev, seed) with event counts.
- `scripts/v3_run_matrix.sh` — design-matrix driver, idempotent.
- `scripts/v3_aggregate.py` — .out → CSV parser.
- `scripts/v3_plot.py` — CSV → PNG plotter.
- `runs.tar.gz` — 200 raw simulator stdouts, compressed (extract with `tar -xzf runs.tar.gz -C runs/`).
