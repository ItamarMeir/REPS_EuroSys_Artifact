# exp25 — Core-downlink queue occupancy over time: REPS vs FREEZING B=64

## Motivation

exp24 confirmed REPS's deterministic first-window round-robin (`nextEntropy_REPS`,
`uec.cpp:3044-3073`) — not buffer boundedness — explains its FCT penalty vs FREEZING on
tornado (disabling it puts REPS's FCT inside the FREEZING B=1..64 band). The proposed
mechanism (discussed in this session, not yet directly measured before this experiment): the
round-robin sequence is identical across all 1024 simultaneously-starting flows, so their
first ~64 packets (a burst completing in a few µs at 400 Gbps line rate — well under one
RTT, before any ACK/feedback returns) land on the same core-switch downlink ports at
(near-)the same instant across many flows, causing a brief but severe synchronized queue
spike that poisons NSCC's earliest rate decision, an effect that then compounds over the
rest of the flow. FREEZING draws random from packet 1, so no such synchronized spike should
form.

exp25 tests this directly by logging actual queue occupancy over time.

## New instrumentation (permanent, banner-gated)

New sampler `CoreDownlinkQueueSampler` (`htsim/sim/datacenter/main_uec.cpp`, banner
`// ===== ADDED (core-downlink-queue-log) =====`), gated by `-log_core_downlink_queues
<file>`. Samples the **core→agg downlink** queues (`queues_nc_nup[core][agg][0]`) — the
opposite direction from exp20's `CoreQueueSampler`, which logs agg→core uplink
(`queues_nup_nc`) — for the **first 16 of 64 core switches** (all their connected agg ports;
256 (core,agg) pairs in this K=16 topology, since each core connects to 16 aggs, not all
128), every **0.2 µs**. CSV columns: `time_us,core,agg,bytes`. Row/registered per
[`state_aware_experiments/MODIFICATIONS.md`](../MODIFICATIONS.md).

Subset/interval choice: 16-of-64 cores keeps the CSV bounded at fine time resolution;
0.2 µs was chosen to resolve the few-µs scale of a 64-packet burst at 400 Gbps line rate.

## Design matrix

Reuses exp21's topology/workload/flags (`fat_tree_1024_1os_3t_400g.topo`,
`tornado_n1024_s8388608.cm`, `-paths 64 -use_srv6`), and a **shortened run window**
(`-end 500` instead of exp21's `-end 90000`) since only early/mid queue dynamics matter here.
Originally NSCC only; a **CONSTANT-linerate** pass was added as a follow-up (same flags,
`-sender_cc_algo constant -cwnd 1000` instead of NSCC, same 0.2 µs downlink-queue logging).

| Label | LB algorithm |
|---|---|
| `freezing_b64` | FREEZING, buffer size 64 |
| `reps` | REPS (original, with round-robin) |

3 seeds (42, 43, 44) × 2 algorithms × 2 CC modes = 12 runs total (6 NSCC + 6 CONSTANT),
built and run via Docker.

```bash
$HTSIM -topo $TOPO -tm $WL -paths 64 -sender_cc_only -disable_tor_ecn \
  -linkspeed 400000 -hop_latency 0.5 -q 60 -ecn 12 48 -sack_threshold 4000 \
  -exit_freeze 200000000 -end 500 \
  <algo flags> -sender_cc_algo {nscc -cwnd 100 | constant -cwnd 1000} -seed <seed> \
  -log_core_downlink_queues queues_<algo>[_constant]_s<seed>.csv
```

All 12 runs completed cleanly (rc=0, no ToR-ECN leak line), 639744 CSV rows each
(2499 timesteps × 256 queues). CONSTANT-CC files use a `_constant_` tag in the name so they
don't collide with the original (implicitly-NSCC) files.

## Results — does NOT support the synchronized-spike hypothesis at this subset/resolution

Aggregated to per-timestep **mean** and **p95** queue depth (packets, MTU=4150B) across the
256 sampled queues, then averaged over 3 seeds (±95% CI, t-distribution).

**Overall (0–500 µs) mean queue depth**: FREEZING B=64 = 0.346 pkt, REPS = 0.347 pkt —
essentially identical. **Overall p95**: FREEZING = 0.396 pkt, REPS = 0.414 pkt — REPS
marginally higher, but both far below the 60-packet buffer cap (`-q 60`).

**Peak single-queue depth across the whole run** (max over all 256 queues at each timestep,
then max over time): FREEZING = 1.118 pkt at t=16.6 µs; REPS = 1.113 pkt at t=112.6 µs —
essentially identical magnitude. Neither algorithm produces anything resembling a real
congestion spike on this switch subset; queue depths stay under ~1.1 packets throughout.

**First-window burst region (t=0–14 µs, before REPS's round-robin phase completes)**:
contrary to the hypothesis, **FREEZING's mean queue is higher than REPS's** in this window
(0.591 pkt vs 0.523 pkt) — the opposite of "REPS spikes higher at first." FREEZING also
shows a distinct oscillation the observed subset — ramp to ~0.9–1.0 pkt by t≈8 µs, hold, then
drain to ~0 at t≈13–16 µs, then ramp again — that REPS does not show in the same window;
REPS instead ramps more gradually and monotonically toward the same ~1.0 pkt level, reaching
it slightly later (~t≈9–11 µs).

**Convergence-time gap (NSCC)**: the mean-queue curves (`plots/mean_queue.png`) show REPS's
queue draining to empty (< 0.01 pkt, `CONV_THRESHOLD_PKTS` in `queue_plot_common.py`) later
than FREEZING's — FREEZING converges by **t=198.8 µs**, REPS by **t=205.0 µs**, a **6.20 µs
gap**. This matches exp24's absolute mean-FCT gap almost exactly: FREEZING B=64 = 205.6 µs
vs REPS = 211.5 µs, a **5.95 µs gap** (`plots/mean_fct.png`, NSCC bars; real FCT reused
read-only from exp24's data, no rerun). The tail-end queue-drain delay, not an early spike,
is where the FCT penalty actually shows up in this data.

**CONSTANT-linerate CC**: the same measurement repeated under CONSTANT CC
(`plots/mean_queue_constant.png`) shows the identical pattern at smaller magnitude —
FREEZING converges by **t=194.2 µs**, REPS by **t=196.4 µs**, a **2.20 µs gap**, matching
CONSTANT's absolute mean-FCT gap of **2.89 µs** (FREEZING B=64 = 200.9 µs vs REPS = 203.8 µs,
`plots/mean_fct.png`, CONSTANT bars). Both CC modes show the same drain-time-tracks-FCT-gap
relationship; CONSTANT's smaller gap tracks its smaller FCT penalty.

Plots: `plots/mean_queue.png`, `plots/p95_queue.png`, `plots/mean_queue_constant.png`,
`plots/mean_fct.png` (now combined NSCC + CONSTANT, 4 labeled bars).

## Interpretation

**On this switch subset (first 16 of 64 cores, their 256 downlink ports) and at 0.2 µs
resolution, the data does not show REPS producing a higher or spikier queue than FREEZING at
flow start.** If anything the opposite is true in the earliest window, and both algorithms'
peak occupancy across the whole 500 µs stays under ~1.1 packets — far from saturating the
60-packet buffer.

This does **not** refute exp24's FCT finding (REPS's round-robin genuinely causes the FCT
penalty — that result is solid, cross-checked against buffer-occupancy stats and a direct
ablation). It means the *specific mechanism* proposed this session — a synchronized queue
buildup on a subset of core switches, visible as elevated mean/peak queue depth in this
data — is **not supported by this measurement**. Two live possibilities, not disambiguated by
this experiment:

1. **Wrong subset**: the round-robin's synchronized load may land on cores *outside* the
   first-16 sampled here (SRv6/EV-to-physical-path mapping determines which of the 64 cores
   each flow's round-robin index hits; the first 16 cores are not guaranteed to be the ones
   under correlated load). A full 64-core sweep (or specifically tracking the cores actually
   touched by round-robin path indices 0–63 for a sample of flows) would close this gap.
2. **Wrong mechanism entirely**: the FCT penalty may arise from a different effect of the
   round-robin phase — e.g. correlated *packet reordering / OOO SACK-hole* effects, or a
   subtler interaction with NSCC's rate-update timing — rather than link-queue buildup as
   such. exp24's ablation proves the round-robin *causes* the FCT gap; it does not prove
   queueing is the *channel* by which it does so.

**Practical implication**: don't cite "REPS causes a synchronized queue spike" as the
established mechanism behind exp24's finding — that specific claim was tested here and not
confirmed. exp24's result (round-robin → FCT penalty) stands; the causal *pathway* remains
open.

**But the tail-end convergence-time gap is a real, matching signal, in both CC modes.**
REPS's sampled queues take 6.20 µs (NSCC) / 2.20 µs (CONSTANT) longer than FREEZING's to
fully drain, and exp24's absolute mean FCT gaps are 5.95 µs / 2.89 µs respectively — a
near-exact match in both cases. This reframes the story: it isn't that REPS causes bigger
queues early on (it doesn't, on this subset), it's that REPS's round-robin delays when the
*last* flows — and so the last queued packets on this subset — finish, by essentially the
same amount the FCT numbers show, consistently across CC modes. The drain-time gap looks
like the more direct queue-level correlate of exp24's finding than any early-burst spike.

## Files

```
exp25_queue_dynamics_v25/
├── scripts/queue_plot_common.py    shared ci95/convergence_time/line_plot (both CC modes)
├── scripts/aggregate.py            parses runs/queues_{algo}_s{seed}.csv (NSCC) -> data/exp25_queue_ts.csv
├── scripts/aggregate_constant.py   parses runs/queues_{algo}_constant_s{seed}.csv -> data/exp25_queue_ts_constant.csv
├── scripts/plot.py                 NSCC mean/p95 queue depth vs time + convergence-gap marker
├── scripts/plot_queue_constant.py  CONSTANT mean queue depth vs time + convergence-gap marker
├── scripts/plot_fct.py             absolute mean-FCT bar chart, NSCC+CONSTANT combined (reuses exp24_flows.csv, no rerun)
├── data/exp25_queue_ts.csv          14994 rows (2 algos x 3 seeds x 2499 timesteps, NSCC)
├── data/exp25_queue_ts_constant.csv 14994 rows (2 algos x 3 seeds x 2499 timesteps, CONSTANT)
├── plots/mean_queue.png            NSCC
├── plots/p95_queue.png             NSCC
├── plots/mean_queue_constant.png   CONSTANT
├── plots/mean_fct.png              NSCC + CONSTANT, 4 bars
└── runs.tar.gz                     raw simulator outputs + per-run queue CSVs, both CC modes (compressed)
```

## Build/run environment note

Built and run via Docker (`docker compose build` → `reps-artifact` image), per this repo's
mandatory Docker workflow for `htsim_uec`. `tornado_n1024_s8388608.cm` is `.dockerignore`d
(generated workload) — `docker cp` it into a running container before invoking `htsim_uec`
if missing from the image.
