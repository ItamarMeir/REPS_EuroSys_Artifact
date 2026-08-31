# exp26 — SRv6 + REPS circular-buffer sweep vs restricted-EV OPS

## Purpose

Re-run the five "network health" artifact figures — `fig_2_symmetric`,
`fig_4_asymmetric`, `fig_6_failures_micro`, `fig_7_failures`,
`fig_8_extreme_failures` — with **exactly** their original
topologies / connection matrices / failure scenarios / seeds / flags, changing
**only** the load-balancing arm set:

1. **`-use_srv6` on every run.** The entropy value is folded onto an explicit
   precomputed physical path (`ev % _paths.size()`, `main_uec.cpp:1601-1604`),
   bypassing per-hop ECMP hashing.
2. **`-paths` restricted to the topology's distinct physical-path count** on every
   run, so the entropy domain equals the set of real paths (the "restricted-EV"
   condition requested for the OPS baseline, applied uniformly).
3. The per-figure LB sweep (plb, mprdma, bitmap, flowlet, ecmp, mp, nvidia, …) is
   replaced by:
   - **`ops`** — `-load_balancing_algo oblivious` — restricted-EV OPS baseline
     (uniform per-packet spray over exactly the N physical paths).
   - **`reps_b<B>`** — `-load_balancing_algo freezing -reps_buffer_size <B>` for
     `B = 1, 2, 4, 8, … , N` (N = distinct paths).

No `-smart_filter_*` flags: smart-filter stays off by default; `-reps_buffer_size`
only calls `CircularBufferREPS::setBufferSize` (`main_uec.cpp:857-863`).

Every other flag is copied verbatim from the original figure's command.

## Topologies and path counts (verified 2026-08-29)

`-use_srv6` prints `SRv6: <s>-><d> distinct_paths=N`. Measured:

| figure | topology | hosts | n_paths | B ladder | seed |
|--------|----------|-------|---------|----------|------|
| fig_2 micro | `fat_tree_1024_1os_2t_400g` | 1024 | 32 | 1,2,4,8,16,32 | 42 |
| fig_2 dc / ai | `fat_tree_128_1os_2t_400g` | 128 | 8 | 1,2,4,8 | 1019 |
| fig_4 micro / dc / ai | `fat_tree_128_1os_2t_400g` | 128 | 8 | 1,2,4,8 | micro 42, dc/ai 1019 |
| fig_6 | `fat_tree_128_1os_3t_400g` | 128 | 16 (inter-pod) | 1,2,4,8,16 | 5 |
| fig_7 | `fat_tree_32_1os_2t_400g` | 32 | 4 | 1,2,4 | 42 |
| fig_8 | `fat_tree_1024_1os_2t_400g` | 1024 | 32 | 1,2,4,8,16,32 | 44 |

fig_6's flows (`test_symm32.cm`: `0→64`, `1→65`, …) are inter-pod, so n_paths = 16
(pod-local pairs would be 4). Intra-rack pairs have exactly 1 path and are
insensitive to B — not present in these workloads.

## Conditions kept exactly

- **fig_2** — no failures. micro = {perm, tornado, incast d=8} × sizes
  {4194304, 8388608, 16777216}; dc = {40,60,80,100}`load_ae.cm`;
  ai = {alltoall4/8/16, allreduce, allreduce_t}, `-down_ratio` 0.25 for allreduce
  else 0.5. `-enable_qa_gate` on the micro panel, `-q 101 -ecn 25 76` (micro),
  `-q 100 -ecn 25 76` (dc/ai).
- **fig_4** — fig_2 + `-failed 4` on every run, `-skip_asy` on the micro panel;
  micro panel topology is 128 (not 1024).
- **fig_6** — `-failed 42 -log_link -collect_data -exit_freeze 100000000` (freezing
  arms only), `-q 100 -ecn 20 80`, tm `test_symm32.cm`, per-arm `-save_data_folder`.
- **fig_7** — 8 `-failures_input` scenarios × {permutation, dc, ai};
  `-connections_mapping -disable_trim -other_location`, `-q 101 -ecn 25 76`.
- **fig_8** — cable-failure levels 0/10/20/30/40/50 %, tm `perm_n1024_s33554432.cm`,
  `-q 100 -ecn 20 80`, `-exit_freeze 10000000000` (freezing arms only), trimming
  left ON (no `-disable_trim`).

## Layout

```
scripts/
  common.py        path table, B ladder, arm→flags, filtered run helper
  run_fig7.py      fig_7 conditions   (96 runs)
  run_fig8.py      fig_8 conditions   (42 runs)
  run_fig6.py      fig_6 conditions   (6 runs, trace style)
  run_sym.py       --figure fig2|fig4 (fig_2 / fig_4 conditions)
  aggregate.py     runs/ -> data/flows.csv.gz, data/summary.csv
  plot.py          data/ -> plots/fig{2,4,7}_all.png (3-panel composites),
                            plots/fig{2,4,7}_{micro,dc,ai}.png (same, standalone),
                            plots/fig8_failures.png, legend_arms.png, LEGEND.md
  plot_fig6.py     runs/fig6 raw_output -> plots/fig6_trace.png
runs/<fig>/<workload>/<condition>/<arm>/stdout.txt   (+ raw_output/ for fig6)
data/   flows.csv.gz (gzipped, ~800k rows), summary.csv, fig6_timeseries.csv.gz
plots/  *.png, legend_arms.png, LEGEND.md, README.md
```

### Plots — faithful reproductions of the paper figures

Each PNG reproduces the **form, x-axis, y-metric and panel layout** of the
matching paper "network health" figure
(`artifact_results_runs/full/fig_*/plots/`); the paper's 9-way LB legend is
replaced by `{OPS, REPS B=1,2,4,…}` (all `-use_srv6`). Plot logic is ported
from the paper generators `htsim/sim/datacenter/plot_{symmetric,load,collective,failures}.py`
and the inline plotting in `artifact_scripts/fig_{6,8}_*.py`.

| exp26 PNG | paper original (artifact / PDF) | form |
|---|---|---|
| `fig2_all.png`, `fig4_all.png` | `fig_2_symmetric` / `fig_4_asymmetric` = PDF Fig 2 / 4 | 3-panel composite in the paper's order, shared legend at the bottom |
| ├ `fig{2,4}_micro.png` | `microbenchmarks_notrim` | horizontal scatter, y = workload category, x = **Speedup vs OPS** (Max FCT) |
| ├ `fig{2,4}_dc.png` | `dc_notrim` | line, x = **Load Level (%)**, y = **Average FCT (µs)** |
| └ `fig{2,4}_ai.png` | `ai_notrim` | grouped bars, x = collective, y = **Collective Runtime (ms)** |
| `fig7_all.png` + `fig7_{micro,dc,ai}.png` | `fig_7_failures` = **PDF Fig 6** | horizontal scatter, y = **Failure Mode**, x = **Speedup vs OPS** (Max / Avg / last-flow) |
| `fig8_failures.png` | `fig_8_extreme_failures` = PDF Fig 8 | line, x = **cable-failure %**, y = **Max FCT (µs)** linear, + ideal line + % slowdown labels |
| `fig6_trace.png` | `fig_6_failures_micro` = **PDF Fig 7** | one stacked panel per arm, x = **Time (µs)**, y = **Queue Size (KB)**, per-uplink lines, 2 ECN ref lines |

Headlines are adapted from the paper's own captions
(`papers/REPS-new.pdf`); note the artifact-script numbering and the PDF
numbering disagree for `fig_6_failures_micro` and `fig_7_failures`, so every
headline prints both.

Two forced deviations from the paper:
- **Baseline** — paper fig_2/fig_4 micro plot "Speedup vs ECMP"; exp26 has no
  ECMP arm, so the baseline is the `ops` arm ("Speedup vs OPS"), the convention
  the paper's own fig_7 already uses. dc/ai panels are absolute (no baseline).
- **fig_6 util axis omitted** — `-use_srv6` routes every packet on an explicit
  source route and never enters `FatTreeSwitch::getEgressPort()`, the only place
  `-log_link` writes the `port/` / `link_util/` per-port packet logs
  (`fat_tree_switch.cpp:449-462`). Port utilisation is therefore unrecoverable
  from these runs; only the queue-size logs survive, so each fig_6 panel shows
  just the queue axis (with the paper's two `-ecn 20 80` reference lines).

`stdout.txt` is stream-filtered: htsim's newline-less `Dropping a PKT` spam is
collapsed to a count (writing it verbatim onto the WSL `/mnt/c` mount is
minutes-slow). Only `finished at` lines and banners are needed downstream.

## How to run

Runs execute the Linux `htsim_uec` binary; on this Windows host they go through
WSL:

```bash
wsl.exe -d Ubuntu-24.04 -e bash -lc '
  cd /mnt/c/git_repos/REPS_EuroSys_Artifact/experiments/exp26_srv6_buffer_sweep/scripts
  python3 run_fig7.py
  python3 run_fig6.py
  python3 run_sym.py --figure fig2
  python3 run_sym.py --figure fig4
  python3 run_fig8.py
  python3 aggregate.py
  python3 plot.py
  python3 plot_fig6.py'
```

All drivers are idempotent (a run whose `stdout.txt` already ended with
`Bounced:` or has `finished at` lines is skipped; an interrupted one is re-run).
Each takes `--quick` and `--arms` / `--workloads` / `--scenarios` / `--levels`
filters for incremental filling.

### Execution environment

Docker Desktop's engine was down at the start of this work, so fig_6/fig_7 were
first run under WSL against the committed 2026-08-25 binary (verified current
with source). Once Docker came back, htsim was rebuilt clean inside the
`reps-artifact` container (`docker compose up -d` + `make clean && make` per the
CLAUDE.md bind-mount gotcha) and **fig_7 was re-run in the container and compared
flow-by-flow against the WSL run** (`scripts/compare_docker.py`):

- **93 of 96 cells: bit-identical FCTs** (delta 0.000 µs).
- **1 cell diverged** — `dc / 5_percent_failed_switches_and_cables / reps_b2`,
  ~2.7 ms max delta. `ops`, `reps_b1`, `reps_b4` of that *same* scenario+panel
  match exactly, so the failure set is identical; the divergence is htsim's own
  run-to-run sensitivity in a heavily-failed scenario (pointer-ordered iteration
  / timing), not toolchain skew. Present in the paper artifact too.

The Docker fig_7 run is adopted as canonical; fig_6 and fig_2/4/8 all run in the
container.

### Connection-matrix audit (2026-08-30) and the ai re-run

Every one of the 342 cells was re-checked by parsing htsim's own
`Nodes: <N> Connections: <C>` banner out of `runs.tar.gz` and comparing `N`
against the host count in the run's `-topo`. One real deviation surfaced:

- **fig_2 / fig_4 `ai` first ran 32-rank collectives on the 128-host topology.**
  `alltoall{4,8,16}.cm` and `allreduce{,_t}.cm` are *not* topology-keyed, and
  `gen_files.py` overwrites them in place — fig_7 generates them at 32 ranks
  (`run_all_failure.py:54`), fig_2/fig_4 at 128
  (`run_all_symm.py:75`, `run_all_asy.py:57`). exp26's `run_sym.py` had no
  generation step, so it consumed whatever fig_7 left behind: 992 / 496 / 160
  flows instead of 16 256 / 8 128 / 896. **Fixed**: `run_sym.py --prep-cms`
  regenerates at 128 ranks, runs the panel, and restores the git-tracked 32-rank
  files in a `finally` block so fig_7 stays reproducible; all 50 ai cells were
  re-run. `common.py` now aborts loudly on any `Nodes:`-vs-topology mismatch.

Two things the audit confirmed are *not* bugs:

- **fig_2 / fig_4 `dc` deliberately runs 32-rank `*load_ae.cm` on 128 hosts.**
  `run_dc.py`'s `--ae_runs` ("artifact evaluation") defaults to `True` and no
  caller overrides it; `gen_files_remote.py` never writes `*_ae.cm` at all, so
  they are git-tracked fixtures. The paper's own fig_2 dc panel does exactly
  this. Cross-check: exp26's OPS at 100 % load = 160 µs vs the paper's ≈180 µs.
- **Failure sets are identical across arms.** exp26 reuses the cached draws in
  `htsim/sim/failures_input/saved/` instead of re-drawing, so `ops` and every
  `reps_b<B>` in a cell hit the same links — verified directly (all four arms of
  `fig7/permutation/5_percent_failed_cables` report cable ids 85, 93, 129 at the
  same times). It is a fixed pre-existing draw, not one generated for this
  experiment.

## Cost

≈ 340 sims. fig_7 (32 hosts) and fig_6 (4 flows) are minutes total; the
1024-host cells (fig_8 = 42 runs, fig_2 micro = 63 runs) dominate and take many
hours. Fill incrementally.

## Status (2026-08-30)

- [x] path-count smoke test — 4 / 8 / 16 / 32 confirmed against `distinct_paths=`
- [x] `-reps_buffer_size 1` edge case — terminates cleanly on fat_tree_32
- [x] WSL-vs-Docker fig_7 flow-by-flow check — 93/96 cells bit-identical
- [x] **fig_7** — 96/96 (Docker), 0 failures
- [x] **fig_6** — 6/6 (Docker), 0 failures
- [x] **fig_4** — 90/90 (Docker), 0 failures
- [x] **fig_2** — 108/108 (Docker), 0 failures
- [x] **fig_8** — 42/42 (Docker), 0 failures
- [x] connection-matrix audit of all 342 cells (`Nodes:` banner vs `-topo` hosts)
- [x] **fig_2 / fig_4 ai re-run at 128 ranks** — 50 cells, after the audit found
      they had used fig_7's 32-rank collectives
- [x] aggregate + plots (`data/summary.csv` 342 cells, `data/flows.csv.gz` 809 479 flow rows)
- [x] `runs/` archived to `runs.tar.gz`; driver logs kept at `data/run_logs/`

**Full matrix complete.** All runs done in the `reps-artifact` container
(htsim rebuilt clean inside it). To reproduce from the archive:

```bash
docker compose up -d
tar -xzf experiments/exp26_srv6_buffer_sweep/runs.tar.gz \
    -C experiments/exp26_srv6_buffer_sweep/runs   # or just rerun the drivers
docker exec reps-artifact-dev bash -lc '
  cd /workspace/experiments/exp26_srv6_buffer_sweep/scripts
  python3 run_fig6.py && python3 run_fig7.py && python3 run_fig8.py &&
  python3 run_sym.py --figure fig2 --panels micro,dc &&
  python3 run_sym.py --figure fig4 --panels micro,dc &&
  python3 run_sym.py --figure fig2 --panels ai --prep-cms &&
  python3 run_sym.py --figure fig4 --panels ai --prep-cms &&
  python3 aggregate.py && python3 plot.py && python3 plot_fig6.py'
```

**Run the `ai` panels last, and always with `--prep-cms`.** They regenerate the
five collective `.cm` files at 128 ranks and restore the git-tracked 32-rank ones
afterwards; fig_7 needs the 32-rank versions, so interleaving them silently
poisons whichever figure runs second (see the audit section below).

## Results

Metrics are the paper's own, per panel: **Max FCT** for the synthetic-benchmark
panels, **Average FCT** for DC traces, **last-flow finish** for AI collectives.
Speedups are against the restricted-EV OPS arm in the same cell. One seed per
cell (the paper's), so single-cell outliers are noise, not trend.

### fig_2 — symmetric, healthy (no failures)

| panel | result | buffer size B |
|---|---|---|
| synthetic | incast ≈1.0×; **permutation 1.07–1.23×**, **tornado 1.06–1.40×** | flat above B=2; B=1 costs ~1–3 % |
| DC traces | ≈1× (156–164 µs vs OPS 160 µs at 100 % load) | **B=1 is the only loser** — 0.92× at 60 %, 0.92× at 80 % load |
| AI collectives | ≈1× for AllToAll and ring AllReduce; **butterfly AllReduce 1.76–1.79×** | flat |

Even with no failure at all, REPS beats restricted-EV OPS on the *tail*: Max FCT
punishes OPS's unluckiest flow, and oblivious spray always has one. On mean FCT
the same cells are ≈1.0×. So this is a tail-latency win, not a throughput win.

### fig_4 — asymmetric (`-failed 4`, ≈2 % of ToR uplinks degraded)

| panel | result | buffer size B |
|---|---|---|
| synthetic | incast ≈1.0×; **permutation 1.40–1.71×**, **tornado 1.34–1.76×** | flat |
| DC traces | **1.17–1.26× at 80–100 % load** (97 µs vs 127 µs; 157 µs vs 199 µs) | **clear knee at B=4**: 80 % load goes 116 µs (B=1) → 105 (B=2) → 97 (B=4), then flat |
| AI collectives | AllToAll(8) 1.48×, AllToAll(16) 1.20× at B=4; butterfly AllReduce 1.49–1.66× | **knee at B=4 again**: AllToAll(8) 0.75× (B=1) → 1.48× (B=4); AllToAll(16) 0.64× → 1.20× |

**This is the one place buffer size clearly matters.** Under sustained asymmetry a
1- or 2-slot circular buffer is *worse than OPS* on the heavier collectives — too
few cached entropy values to route around the degraded uplinks — and the win
appears at B=4 and then flattens.

**The fig_4 ring-AllReduce B=2 spike is real, and it has a mechanism.** That arm
finishes in 10.2 ms vs 1.2 ms for OPS (0.12×), while B=4 finishes in 0.11 ms
(11×). Verified from the raw stdout:

- All 8128 flows complete in every arm; p50 is 91 µs for B=2, the same as B=4
  and B=8. The distribution is **bimodal**: 7997 flows finish under 200 µs and
  **131 flows land between 2 ms and 10.2 ms**. No other arm has a single flow
  above 2 ms.
- Those 131 slow flows carry **1225 of the run's 1266 RTS events** (97 %); the
  7997 fast flows carry 41. Affected flows average ~16 RTS each, versus 1 per
  flow for B=1 / B=4 / B=8.
- The identical cell **without** `-failed 4` (fig_2, same workload, same B=2) is
  completely clean: max 92.7 µs.

So under the 4 degraded links a B=2 buffer gets stuck: a flow that lands on a bad
path freezes, and with only two slots it cycles inside a tiny entropy set instead
of accumulating known-good paths. B=1 escapes it (degenerate — effectively
re-randomises every draw) and B≥4 has room to cache good paths. B=2 is the
pathological middle.

How to read the magnitude: the panel's metric is **last-flow finish** — the
paper's own choice (`plot_collective.py::get_last_flow_time`) — so a tail hitting
1.6 % of flows sets the whole bar. On **mean** FCT the same cell is 204 µs vs OPS
158 µs, i.e. 1.3× worse rather than 8.7×. The run also uses the paper's single
seed (1019, from `run_collective.py`); exp26 deliberately does **not** add seeds,
because the point of this experiment is to hold every condition the paper fixes
and vary only the LB arm. So the bar is exactly what the paper's own methodology
reports for this arm — a real, mechanistically-explained failure mode, measured
the way the paper measures it, with the paper's sampling.

### fig_7 — failure modes (fat_tree_32, 4 paths)

- **Hard failures** (switch, switch+cable, cable): REPS+SRv6 beats OPS by a wide
  margin — permutation **40–71×** on Max FCT, DC traces **2.1–5.5×** on Avg FCT,
  ring AllReduce **4.6–16.5×**. OPS pins ~1/4 of a 4-path entropy domain onto
  dead paths and never recovers inside the 90 ms window.
- **BER degradation** (1 % on a cable or a switch): ≈1× — no path is fully dead,
  so uniform spray is fine. On DC traces OPS is in fact marginally *ahead*
  (0.7–0.9×).
- In three cells OPS never finishes the workload at all (215/496, 419/496,
  2136/2138); its FCT there is measured over finished flows only, so those
  speedups are lower bounds.
- **B is flat** across every scenario — the win comes from freeze/rotate reacting
  to RTOs, not from how many entropy values the buffer holds.

### fig_6 — single-link degradation trace (fat_tree_128 3-tier, 16 paths)

After the link degrades, OPS's leaf-0 uplink queues keep oscillating out to
~1250 µs; every REPS-B arm has drained by ~850 µs. B changes the transient only
slightly (B=1 is visibly noisier through the 400–500 µs re-route).

### fig_8 — extreme cable failure (fat_tree_1024, 32 paths)

OPS Max FCT climbs from ~0.8 ms (0 %) to the **90 ms simulation cap by 40 %**,
where it stops finishing flows (1021/1024 at 40 %, 909/1024 at 50 %). Every
REPS-B arm stays within ~1.3× of the analytic ideal across the whole range
(0.70 → 1.85 ms), tracking each other closely; **B is flat**, B=1 marginally the
worst at 50 %.

### Overall

The REPS-vs-restricted-EV-OPS advantage under SRv6 splits cleanly by metric and
by condition:

- **Tail vs mean.** Even in a perfectly healthy network REPS wins 1.1–1.4× on
  *Max* FCT for permutation/tornado while being ≈1× on mean. Under failures the
  gap grows to 2–71× (fig_7) and to "OPS stops finishing" (fig_8).
- **Incast never benefits.** All three incast rows sit at ≈1.0× in both fig_2 and
  fig_4 — the bottleneck is the receiver's downlink, which no load balancer can
  spread.
- **Buffer size B mostly does not matter, with one real exception.** Flat under
  hard failure (fig_7), extreme failure (fig_8) and in a healthy network (fig_2,
  beyond a small B=1 penalty). But under *sustained asymmetric load* (fig_4 DC
  and AI) there is a clear knee: B=1–2 can be worse than OPS, B=4 recovers the
  full win, and B=8/16/32 add nothing. The paper's B=8 is safely past the knee;
  nothing here shows a payoff for going above ~4 on these topologies.
