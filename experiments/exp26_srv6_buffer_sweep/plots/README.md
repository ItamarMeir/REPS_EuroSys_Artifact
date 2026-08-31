# exp26 plots — what each figure tests

Every plot here **reproduces the form, x-axis, y-metric, panel order and
headline of the matching paper "network health" figure**
(`artifact_results_runs/full/fig_*/plots/*.png`). The only change is the legend:
the paper's 9-way LB sweep (ECMP, OPS, Flowlet, BitMap, MPRDMA, PLB, MPTCP,
Adaptive RoCE, REPS) is replaced by

- `ops` — `-load_balancing_algo oblivious` — restricted-EV OPS baseline
  (per-packet uniform-random spray over exactly the `N` distinct physical paths).
- `reps_b<B>` — `-load_balancing_algo freezing -reps_buffer_size B` for
  `B = 1, 2, 4, 8, …` up to and including `N`.

and **every run adds `-use_srv6 -paths N`** (entropy folded onto an explicit
physical path, `ev % _paths.size()`, no per-hop ECMP hashing). `N` is verified
against htsim's `SRv6: … distinct_paths=N` banner. No `-smart_filter_*` flags.
Plot logic is ported verbatim from the paper generators
`htsim/sim/datacenter/plot_{symmetric,load,collective,failures}.py` and the
inline plotting in `artifact_scripts/fig_{6,8}_*.py`.

Common CC / flags on every run: `-sender_cc_only -sender_cc_algo mprdma`,
`-linkspeed 400000`, `-end 90000`, `-sack_threshold 4000`. Every other flag is
copied verbatim from the paper figure's command (seed, connection matrix,
`-failed` / `-failures_input`, `-q`, `-ecn`, `-cwnd`, `-enable_qa_gate`,
`-disable_trim`, `-other_location`, `-skip_asy`, `-down_ratio`, `-exit_freeze`).

See `LEGEND.md` / `legend_arms.png` for colours and markers (OPS = orange square
dashed; REPS = viridis ramp over `B`, X marker).

### File map, and the paper's own figure numbers

The exp26 ids follow the `artifact_scripts/fig_N_*.py` filenames. Two of those
do **not** match the numbering in the paper PDF (`papers/REPS-new.pdf`), so both
are given here and printed in every headline.

| exp26 files | artifact script | paper PDF | paper caption |
|---|---|---|---|
| `fig2_all.png` + `fig2_{micro,dc,ai}.png` | `fig_2_symmetric` | **Figure 2** | REPS performance in synthetic benchmarks (I.=Incast, P.=Permutation, T.=Tornado), DC traces and AI collectives. |
| `fig4_all.png` + `fig4_{micro,dc,ai}.png` | `fig_4_asymmetric` | **Figure 4** | …and an asymmetric network due to 2 % of the ToR uplinks being offline. |
| `fig6_trace.png` | `fig_6_failures_micro` | **Figure 7** | REPS vs. OPS in a 32 MiB permutation with two cables' failure (a shorter one and a longer one). |
| `fig7_all.png` + `fig7_{micro,dc,ai}.png` | `fig_7_failures` | **Figure 6** | REPS performance under different failure modes in a 8 MiB permutation, DC traces at 100 % load and a ring AllReduce. |
| `fig8_failures.png` | `fig_8_extreme_failures` | **Figure 8** | Extreme failures scenario. |

`<fig>_all.png` is the composite: the figure's three panels side by side **in the
paper's order** (synthetic benchmarks / DC / AI for fig2 & fig4; 8 MiB
permutation / DC 100 % / ring AllReduce for fig7) with one shared arm legend
along the bottom. The same three panels are also written standalone as
`<fig>_micro.png`, `<fig>_dc.png`, `<fig>_ai.png`. Axis labels are the paper
generators' own strings; per-panel titles use the paper's vocabulary.

**Forced deviation — speedup baseline.** Paper `fig_2`/`fig_4` micro panels plot
*Speedup vs ECMP*. exp26 has no ECMP arm, so the baseline is the `ops` arm and
the axis reads **Speedup vs OPS**. `fig_7` already uses OPS as its baseline in
the paper. dc panels show absolute Average FCT, ai panels absolute collective
runtime — no baseline.

### Reading the `OPS finished x/y flows` annotation

On some `fig7` rows a red note reads e.g. `OPS finished 419/496 flows`. It means
the `ops` arm completed only 419 of the 496 flows the connection matrix defines;
the rest never finished inside the 90 ms `-end` window, because oblivious spray
keeps pinning part of its entropy domain onto dead paths. That arm's Max/Avg FCT
is then computed over the flows that *did* finish — the easier ones — which
biases OPS's metric **downward**, so the plotted speedup on those rows is a
**lower bound** on REPS's real advantage. `data/summary.csv` carries the full
picture per cell: `n_connections` (matrix truth), `unfinished`, and
`unfinished_vs_best` (the LB-attributable part). The annotation fires on
`unfinished_vs_best`, so it never flags a *structural* shortfall — e.g. in
`fig7/permutation` under `fail_one_switch`, one host sits behind the failed
switch and **all four arms** finish 31/32; no load balancer can fix that, so it
is recorded in the CSV but not drawn.

### Workload / topology provenance

- The **dc** panels of `fig2`/`fig4` deliberately run the 32-rank
  `{40,60,80,100}load_ae.cm` matrices on the 128-host topology. This is the
  paper's own behaviour: `run_dc.py`'s `--ae_runs` ("artifact evaluation")
  argument defaults to `True` and `run_all_symm.py` / `run_all_asy.py` never
  override it, and `gen_files_remote.py` never writes `*_ae.cm` at all — they are
  git-tracked fixtures. Sanity check: exp26's OPS at 100 % load lands at 160 µs
  against the paper's ≈180 µs.
- The **ai** panels regenerate `alltoall{4,8,16}.cm` / `allreduce{,_t}.cm` at
  **128 ranks** first (`gen_files.py --size_topo 128 --all_red_size 128`,
  mirroring `run_all_symm.py:75` / `run_all_asy.py:57`), then restore the
  git-tracked 32-rank versions afterwards. Those five filenames are *not*
  topology-keyed and are shared with `fig7`, which needs them at 32 ranks —
  `scripts/run_sym.py --prep-cms` does the generate → run → restore cycle in a
  `try/finally`, and `common.py` fails loudly if a run's
  `Nodes: N` banner ever disagrees with its topology's host count.
- **Failure sets are identical across arms within a cell.** exp26 reuses the
  cached draws in `htsim/sim/failures_input/saved/` rather than re-drawing per
  run, so `ops` and every `reps_b<B>` see the same failed cables/switches
  (verified: all arms of `fig7/permutation/5_percent_failed_cables` report cable
  ids 85, 93, 129 at the same times). The cache is a fixed pre-existing draw, not
  one freshly generated for this experiment.

---

## `fig2_{micro,dc,ai}.png` — symmetric, healthy (no failures)

Basis: paper `fig_2_symmetric` (`microbenchmarks_notrim`, `dc_notrim`,
`ai_notrim`). **No `-failed`, no `-failures_input`.**

| panel | plot form | topology | hosts / paths | workloads | seed | queue / ECN / cwnd |
|---|---|---|---|---|---|---|
| `fig2_micro` | horizontal scatter — y = workload category (`I. 8:1 / P. / T.` × `4/8/16 MiB`), x = **Speedup vs OPS** (per-flow **Max FCT** ratio) | `fat_tree_1024_1os_2t_400g` | 1024 / 32 | permutation, tornado, incast (degree 8) × sizes `4194304 / 8388608 / 16777216` B | 42 | `-q 101 -ecn 25 76 -cwnd 151` (BDP), `-enable_qa_gate` |
| `fig2_dc` | line — x = **Load Level (%)** {40,60,80,100}, y = **Average FCT (µs)**, one line per arm | `fat_tree_128_1os_2t_400g` | 128 / 8 | `40/60/80/100 load_ae.cm` | 1019 | `-q 100 -ecn 25 76 -cwnd 151` |
| `fig2_ai` | grouped bars — x = collective {AlltoAll n=4/8/16, Ring AllRed, Butterfly AllRed}, y = **Collective Runtime (ms)** (last-flow finish / 1000) | `fat_tree_128_1os_2t_400g` | 128 / 8 | `alltoall4/8/16`, `allreduce`, `allreduce_t` — regenerated at **128 ranks** | 1019 | `-q 100 -ecn 25 76 -cwnd 151`; `-down_ratio 0.25` for `allreduce` else `0.5` |

Buffer ladder: micro `B ∈ {1,2,4,8,16,32}`, dc / ai `B ∈ {1,2,4,8}`.
All three also pass `-connections_mapping -disable_trim`.

The ai `n` in `AlltoAll (n=4/8/16)` is the collective's **concurrency width** —
how many peer-sends each rank keeps in flight at once. Every rank must reach
`ranks−1` peers, done in `⌈(ranks−1)/n⌉` trigger-chained rounds of `n` parallel
flows (`connection_matrices/gen_serialn_alltoall.py`, the `parallel` argument,
from `gen_files.py`'s `all_to_all_n = [1,2,4,8,16]`). Higher `n` puts more
simultaneous load on the fabric. It is **not** a host count and **not** a path
count — at 128 ranks all three AlltoAll variants carry the same 16 256 flows.

## `fig4_{micro,dc,ai}.png` — asymmetric (4 degraded links)

Basis: paper `fig_4_asymmetric`. **Identical to `fig2` plus `-failed 4` on every
run** (htsim degrades 4 RNG-selected links — static bandwidth asymmetry, not a
full failure). The micro panel additionally passes `-skip_asy` and uses the
**128-host** topology (`fat_tree_128_1os_2t_400g`, 8 paths), not 1024. dc and ai
panels are unchanged from `fig2` except for `-failed 4`. Buffer ladder
`B ∈ {1,2,4,8}` for all three panels. Same 3 plot forms as `fig2`.

## `fig6_trace.png` — single-link degradation micro-trace

Basis: paper `fig_6_failures_micro`.

| | |
|---|---|
| topology | `fat_tree_128_1os_3t_400g` — 128 hosts, **3-tier**, 16 distinct inter-pod paths |
| failure | `-failed 42` — one RNG-selected link degraded, from t=0 |
| workload | `test_symm32.cm` — 4 inter-pod flows (hosts 0→64, 1→65, 2→66, 3→67), 32 MiB each |
| seed | 5 |
| queue / ECN / cwnd | `-q 100 -ecn 20 80 -cwnd 151` |
| instrumentation | `-log_link -collect_data`, per-arm `-save_data_folder` |
| arms | `ops` (no `-exit_freeze`); `reps_b<B>` for `B ∈ {1,2,4,8,16}`, each with `-exit_freeze 100000000` |

Plot: **one stacked panel per arm** (paper has 2: "Oblivious Packet Spraying",
"REPS"), x = **Time (µs)**, y = **Queue Size (KB)**, one colour per leaf-0
uplink `LS0->US{0..3}`, grey dotted reference lines at `20·MTU` and `80·MTU` KB
(the `-ecn 20 80` marks).

**Util axis omitted.** The paper panel is dual-axis (Output Port Utilisation
Gbps + Queue Size KB). `-use_srv6` routes every packet on an explicit source
route and never enters `FatTreeSwitch::getEgressPort()`, the only place
`-log_link` writes the `port/` / `link_util/` per-port packet logs
(`fat_tree_switch.cpp:449-462`), so port utilisation is unrecoverable from these
runs. Only the queue-size logs (written by the queue objects) survive.

## `fig7_{micro,dc,ai}.png` — failure-scenario sweep

Basis: paper `fig_7_failures` (`microbenchmarks_notrim`, `dc_notrim`,
`ai_notrim` — all three are horizontal scatter, `Speedup vs OPS`).

| | |
|---|---|
| topology | `fat_tree_32_1os_2t_400g` — 32 hosts, 2-tier, 4 distinct paths |
| seed | 42 |
| queue / ECN / cwnd | `-q 101 -ecn 25 76 -cwnd 151` (BDP-derived) |
| extra flags | `-connections_mapping -disable_trim -other_location` |
| workloads | `fig7_micro` = permutation (`permutation_size8388608B.cm`, 8 MiB); `fig7_dc` = `100load_32.cm`; `fig7_ai` = `allreduce.cm` |
| metric (x) | micro = per-flow **Max FCT** ratio; dc = **Average FCT** ratio; ai = **last-flow finish** ratio — all `OPS / arm` in the same cell |
| arms | `ops` + `reps_b{1,2,4}` |

**8 failure scenarios** (y axis; each a `-failures_input
../failures_input/<file>.txt`, all from sim t=0):

| y-label | file | what fails |
|---|---|---|
| One Failed Cable | `fail_one_cable` | 1 cable, permanent |
| One Failed Switch | `fail_one_switch` | 1 switch, permanent |
| One Failed Switch/Cable | `fail_one_switch_one_cable` | 1 switch + 1 cable |
| 5% Failed Cables | `5_percent_failed_cables` | 5 % of cables, permanent |
| 5% Failed Switches | `5_percent_failed_switches` | 5 % of switches |
| 5% Failed Switches/Cables | `5_percent_failed_switches_and_cables` | 5 % switches + 5 % cables |
| BER Cable 1% | `ber_cable_one_percent` | 1 % bit-error-rate on a cable |
| BER Switch 1% | `ber_switch_one_percent` | 1 % bit-error-rate on a switch |

A red note on the right marks rows where OPS did not finish every flow (its
speedup is then understated — the ratio is over finished flows only).

## `fig8_failures.png` — extreme cable failure

Basis: paper `fig_8_extreme_failures`.

| | |
|---|---|
| topology | `fat_tree_1024_1os_2t_400g` — 1024 hosts, 2-tier, 32 distinct paths |
| seed | 44 |
| workload | `perm_n1024_s33554432.cm` — permutation, 32 MiB flows |
| queue / ECN / cwnd | `-q 100 -ecn 20 80 -cwnd 151` |
| trimming | ON (no `-disable_trim`) |
| failure levels | cable-failure `∈ {0,10,20,30,40,50}` % — `0` = no `-failures_input`; `N` = `-failures_input ../failures_input/N_percent_failed_cables.txt` |
| arms | `ops` (no `-exit_freeze`) + `reps_b{1,2,4,8,16,32}` (each `-exit_freeze 10000000000`) |

Plot: line, x = **Network Cables Failure Percentage (%)**, y = **Max FCT (µs)**
*linear*, one line per arm + the analytic **ideal** line
(`33 MiB / 400 Gbps + 20 µs`, scaled `10/(10-fail%)`) + per-point % slowdown-vs-
ideal labels for `B=8`. OPS collapses onto the 90 ms sim cap (flows never
finish) and would flatten every other curve, so the y-axis is capped to the
REPS band and OPS's range is noted in text.

## `legend_arms.png` / `LEGEND.md`

Shared arm legend: `ops` = orange (`#d95f02`) square dashed; `reps_b<B>` =
viridis ramp over `B`, X marker. A B's colour is the same in every figure.
