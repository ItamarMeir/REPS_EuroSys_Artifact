# exp28 — REPS circular-buffer sweep under targeted ToR→spine-0 link degradation

## What this measures

exp26/exp27 showed REPS's healthy-fabric FCT win over restricted-EV OPS is a
BDP-provisioning + flow-size resonance, and that REPS's *durable* advantage is
the asymmetry / failure regime — but the fig4 asymmetric views only probed a
**single** fixed failure severity. exp28 makes failure severity the independent
variable, on one fixed fabric and workload, and asks how each REPS circular
buffer size `B` copes.

- **Fabric** — `fat_tree_1024_1os_2t_400g` (2-tier, 1024 hosts, **32 ToRs, 32
  spines, 32 distinct SRv6 paths**). This is exp26 fig2-micro / exp27 plot-1's
  own fabric, so its healthy tornado-16 MiB row is a free anchor.
- **Workload** — tornado, 16 MiB/flow (`tornado_n1024_s16777216.cm`), all flows
  `start 0`, seed 42.
- **Arms** — `reps_b{1,2,4,8,16,32}` only (`-load_balancing_algo freezing
  -reps_buffer_size B`), all `-use_srv6 -paths 32`, MPRDMA sender-CC, `-q 101
  -ecn 25 76 -cwnd 151`, `-exit_freeze 200000000`. **No OPS / oblivious
  baseline** — this study compares REPS buffer sizes to each other only, so there
  is no speedup-vs-OPS view.
- **Single seed 42**, matching exp26/27 → no error bars.

### The failure knob (no new htsim failure code)

Both knobs are pre-existing CLI flags, verified 2026-09-03 against
`htsim/sim/datacenter/fat_tree_topology.cpp:862-998`:

- **`-failed K -skip_asy`** degrades **exactly the spine-0 (agg index 0) uplink
  of K of the 32 ToRs** to 50 % linkspeed. `fail_every = NTOR/K` selects the
  ToRs; `skip_asy` caps it to one degraded uplink per selected ToR; the global
  `degraded_cables < K` cap makes the total exactly K. The run prints
  `Failure: LS<tor>->US0(0) linkspeed set to 200` — one line per degraded link,
  all `US0`.
- **`-down_ratio r`** sets `FatTreeTopology::_failed_link_ratio` (default 0.5).
  The degraded queue is allocated with **speed, buffer size, and ECN thresholds
  all `*= r`** (`alloc_queue(..., reduced_speed=true)`). So "50 % degradation" is
  a coupled speed+buffer+ECN cut, not a pure bandwidth cut. `r → 0` is
  degenerate (zero-speed / zero-depth / zero-ECN queue), so part 2 floors at
  `r = 0.05`.

### Part 1 — link-count sweep (`scripts/run_part1.py`)

X-axis = **# degraded ToR→spine-0 links**,
`K ∈ {0, 1, 2, 4, 5, 7, 8, 10, 11, 12, 13, 14, 15, 16, 20, 25, 32}` (17 points;
11/12/13/15 added later to resolve the knee's slope), at the default 50 %
degradation. 17 K × 6 arms = **102 runs** at seed 42; a 7-K subset
(`K ∈ {0,2,5,8,14,20,32}`) additionally re-run at seeds 43/44 for 95% CI
(+84 runs) = **186 runs total**. `-failed K -skip_asy` degrades exactly K
spine-0 uplinks — `fail_every = 32//K` picks the ToRs, `degraded_cables < K`
caps the total at K. **Placement is not uniform across the whole ladder**:
verified from stdout (`Failure: LS<tor>->US0`) that `K ≤ 16` picks
evenly-spaced ToRs (`fail_every = 32//16 = 2` → `{0,2,4,...}`, nested as K
grows: K=14/15/16 are literally the same set plus one/two more), while
`K ≥ 20` switches to `fail_every = 1` → a **contiguous block**
`{0,1,2,...,K-1}`. K=14→15→16 is a clean nested-count comparison; K=16→20 is
not — it's a simultaneous count *and* placement-pattern change. Don't read
the K=16→20 jump as pure count effect.
`runs/part1/micro/tornado_deg<K>_s16777216/{healthy|asym<K>}/<arm>/stdout.txt`.

### Part 2 — degradation-severity sweep (`scripts/run_part2.py`)

Fixed `-failed 4 -skip_asy` (spine-0 uplink of ToRs 0/8/16/24). X-axis =
**degradation %** `= (1 − r)·100`, swept via `-down_ratio r`:

| r | 1.0 | 0.90 | 0.75 | 0.50 | 0.40 | 0.30 | 0.25 | 0.20 | 0.10 | 0.05 |
|---|---|---|---|---|---|---|---|---|---|---|
| deg % | 0 | 10 | 25 | 50 | 60 | 70 | 75 | 80 | 90 | 95 |

The 0 % point is part 1's `K = 0` healthy cell (read directly by the plotter —
`-failed 4 -down_ratio 1.0` is *not* run, it still emits a spurious `Failure:`
line). 9 ratios × 6 arms = **54 runs** at seed 42 (60/70/80% added later to
resolve the tail's slope near the transition); a 3-pct subset
(`{10,50,90}`) additionally re-run at seeds 43/44 for 95% CI (+36 runs) =
**90 runs total**.
`runs/part2/micro/tornado_deg4_r<pct>_s16777216/asym4_r<pct>/<arm>/stdout.txt`.

## Metrics

FCT: **Max / p99 / p95 / median**, one line per REPS buffer B.
Diagnostics (per host, from the finish line — see below): **#ECN-marked ACKs**,
**#RTOs**, **# freeze entries + time in freezing mode**, **random-EV draw rate**
(`(ev_random + ev_explore) / total_packets` — how often REPS had to draw a fresh
random entropy value rather than recycle a known-good one).

Note: `ev_explore ≡ 0` in every cell — `explore_counter` is only refilled on
unfreeze, and with `-exit_freeze 200000000` (200 µs) against flows that finish at
~350 µs–few ms, freezes never auto-thaw within a flow's lifetime. The random-EV
rate is therefore the *buffer-empty / no-fresh-entropy* random-draw rate. Freeze
is near-binary per host (entered once, held to flow end).

### htsim change — `metrics-counters` (diagnostic only, no behaviour change)

`ecn_acks` and `RTS` were already on the flow-finish line. This patch appends
`rtos`, `freeze_entries`, `freeze_us`, `ev_explore`, `ev_random`. The counters
live in a **file-static side table** in `uec.cpp` keyed by `_node_num`, **not**
in new `UecSrc` members: adding any member to `UecSrc` on this codebase
deterministically corrupts the heap during construction (latent layout-sensitive
OOB write elsewhere — out of scope to chase here). Verified: `freeze_entries`
summed over hosts equals the `"started freezing"` printf count; RTO/freeze/ECN
are ~0 on healthy hosts and grow with degradation.
See `experiments/MODIFICATIONS.md` § `metrics-counters`.

## Deviations from the exp26/27 template (intentional — do not "fix")

1. **`-disable_tor_ecn` is omitted**, matching exp26/27 and the paper's
   `run_symmetric.py`. Every row has `tor_ecn_reenabled = 1`. (The project's
   general rule to pair `-sender_cc_only` with `-disable_tor_ecn` does not apply
   to this paper-faithful lineage; adding it would break comparability with the
   exp26/27 anchors.)
2. **`-down_ratio` couples speed + buffer + ECN thresholds.** Part 2's "% degraded"
   is not a pure bandwidth reduction.

## Reproduce

```bash
# build htsim with the metrics-counters patch (Docker, per CLAUDE.md):
docker run --rm -v "$PWD:/workspace" -w /workspace/htsim/sim reps-artifact:latest \
  bash -lc 'make -j$(nproc) && cd datacenter && make -j$(nproc)'

# run the matrix (~2-2.5 min/run at seed 42; 186 + 90 = 276 runs across
# 3 seeds at the CI subset; ~9-10h total, or add --seed/--ks/--pcts to
# run_part{1,2}.py for a partial re-run):
docker run --rm -v "$PWD:/workspace" \
  -w /workspace/experiments/exp28_link_degradation_sweep/scripts reps-artifact:latest \
  bash -lc 'python3 -u run_part1.py && python3 -u run_part2.py'

# aggregate (WSL python3): exp26's aggregator for FCT + a second pass for diagnostics
for p in part1 part2; do
  EXP26_RUNS=$PWD/experiments/exp28_link_degradation_sweep/runs/$p \
  EXP26_DATA=$PWD/experiments/exp28_link_degradation_sweep/data/$p \
    python3 experiments/exp26_srv6_buffer_sweep/scripts/aggregate.py
done
cd experiments/exp28_link_degradation_sweep/scripts
python3 aggregate28.py
python3 plot_sweep.py --part 1
python3 plot_sweep.py --part 2
python3 plot_best_worst.py --part 1
python3 plot_best_worst.py --part 2
python3 build_interactive.py        # -> plots/interactive.html (zoomable Plotly)

# compress raw runs when done:
tar -czf ../runs.tar.gz -C .. runs && rm -rf ../runs
```

`plots/interactive.html` is a standalone page (Plotly from cdnjs, aggregated data
inlined via `plot_sweep.load()` / `agg_ci()`) — part-1/part-2 toggle, metric
switcher, drag-zoom the CI bands.

Probe `K=1` and `K=32` first — if `K=1` is indistinguishable from healthy the
low end of part 1's X-axis is dead and the matrix can start at `K=2`.

## Results

**186 + 90 runs, 0 failures.** Per-host means over 1024 flows. Seed 42 at every
X-value; a subset (part1 `K∈{0,2,5,8,14,20,32}`, part2 `deg%∈{10,50,90}`)
additionally re-run at seeds 43/44, giving a 95% CI (Student-t, n=3) at those
points — the rest are seed-42-only (0-width CI, drawn as a plain marker).
Plots: `plots/part{1,2}/{fct_stats,diagnostics}{,_bars}.png`. Each part also
has a `best_worst/` subfolder — same 4 plots reduced to 2 series per panel,
whichever B is best (min) / worst (max) **independently per metric, per X
value**, annotated with the winning B, instead of all 6 B lines/bars.

**Read Max FCT with caution.** It is the single largest of 1024 per-run flows —
a one-sample statistic. Where CI exists, its half-width is often as large as
the between-B spread (e.g. part2 deg90% B=2: 386 ± 26 µs, B=32: 384 ± 22 µs) —
three seeds gave three different single flows, not three samples of a stable
quantity. Treat Max-FCT orderings as suggestive only; Median and p95/p99 (many
more samples) are where the CI-separated claims below come from.

### Part 1 — link-count sweep (K degraded spine-0 uplinks at 50 %)

- **REPS is robust to spine-0 degradation** across the whole ladder: even at
  K = 32 (every ToR loses spine-0) median FCT rises only ~356 → ~362 µs and
  p99 stays under 373 µs. (The now-removed OPS arm went 0 → 55 RTOs/host over
  the same sweep, for scale.)
- **B = 1 is worse in Median and p95, CI-separated at every K ≥ 20** — e.g. at
  K = 32, Median B=1 = 361.81 ± 0.16 µs vs B=2 = 360.54 ± 0.07 µs, a disjoint
  ~1.1 µs gap. **p99 is borderline** (B=1 sits above the pack but its CI
  overlaps B≥2 at K=20/25/32). **Max FCT is not resolvable at high K** — B=1's
  CI at K=32 (381.75 ± 8.85 µs) fully contains B=2/B=4/B=8's point estimates.
- **Three-tier structure in Median, not two**: B=1 ≫ B=2 > B≥4, all
  CI-separated (e.g. K=32: B1=361.81±0.16, B2=360.54±0.07, B4=360.50±0.15,
  B8=360.48±0.07 — B2 sits a small but real ~0.05 µs above B4/8, itself
  disjoint from B1's gap). **B4/8/16/32 are mutually indistinguishable** at
  every K checked — nothing above B=4 is a resolvable choice.
- **Knee at K = 15→16, confirmed real but placement-confounded beyond K=16.**
  Median is flat (~356.2–357.5 µs, B-dependent but K-flat) through K=15, then
  jumps at K=16 for every B. Verified from stdout: K∈{14,15,16} degrade a
  *nested*, evenly-spaced ToR set (`{0,2,4,...}`, `fail_every=32//16=2`) — the
  K=15→16 step is a clean +1-link comparison, the knee is real. But K≥20
  switches to `fail_every=1`, a **contiguous block** `{0,1,...,K-1}` — a
  different placement pattern, not just more links. Don't read the
  K=16→20 rise as a pure count effect; it's count *and* placement together.
- **RTOs stay near zero**: B=1 rises 0 → ~0.35/host over K=0→32, B=8
  0 → ~0.22/host — consistent ~1.5–2× gap at every K, matching the Median tier
  split.
- **Freeze** barely engages: zero until K≥2, then ≤18 entries fabric-wide at
  K=32, mean time-frozen <4 µs — REPS handles 50%-degradation via EV rotation
  alone, not the freeze path.
- **Random-EV draw rate**: B=1 pinned at ~0.24 (1-slot buffer perpetually
  re-drawing), B=2 ~0.06–0.10, B≥4 ~0.03–0.08, rising gently with K.

### Part 2 — degradation-severity sweep (4 fixed spine-0 uplinks, 0–95 %)

- **Median FCT is flat across 0→95%** and cleanly three-tiered, CI-separated
  at every severity checked: B=1 ~357.3 µs, B=2 ~356.4 µs, B≥4 ~356.2 µs
  (e.g. deg90%: B1=357.37±0.11, B2=356.38±0.03, B4=356.23±0.06 — all disjoint).
  Only 4/32 paths are touched, so the median host rarely sees the degraded
  links at all — the tiers are purely how each B's buffer copes with the
  minority of flows that do route through them.
- **p99 confirms B=1 diverges hard at ≥90%, CI-separated**: deg90% p99
  B1=396.75±4.65 vs B2=373.88±0.68 — no overlap, a genuine ~23 µs gap, not
  noise. Same at deg95% (single seed: 398.8 vs 378.0).
- **Max FCT is not resolvable at ≥90% severity** — B=2's CI there is
  386±26 µs and B=32's is 384±22 µs, both wide enough to contain B=1's point
  estimate; three seeds landed on three different single worst-flows. The
  p99/Median story (B=1 diverges, B≥4 flat) is the reliable one; don't read
  the Max panel's apparent B=1-vs-B=2 crossover at deg90% as real.
- **B≥4 stay flat and mutually indistinguishable** even at 95% (near-dead
  links) in every CI-backed metric — RTO/freeze-time differences among
  B=4/8/16/32 are within each other's noise band at every severity checked.

### Bottom line

With 3-seed CI, the resolvable story is narrower than a single seed suggested:
**B=1 is unambiguously worst** (Median + p99 + p95, CI-separated, at both
axes) and **B=2 is a real, small step better than B=1 but a real, small step
worse than B≥4** — a genuine three-tier structure, not "B=2 marginal." Above
B=4, nothing is resolvable — B4/8/16/32 are statistically indistinguishable
everywhere tested; Max-FCT is too noisy (single-flow, n=3) to add anything
past that. This matches the B≈2→4 knee exp26 fig4 / exp27 F1′/F4 found under
sustained asymmetry, but sharpens it: **the only two decisions with data
behind them are B=1→2 and B=2→4.** For a runtime controller, that means the
policy is a two-step threshold, not a continuous function of severity — its
value has to come from *when* it switches (transient/recovery latency after a
degradation event), not from picking among B≥4. That question needs a
dynamic (time-varying) failure experiment, which static K/severity sweeps
can't answer — see [exp29](../exp29_failure_response/) (done: transient failure; B is unresolvable on FCT there, and the freeze timeout is the knob that matters).

## Side study: soft-replay validation (not part of the Part 1/2 matrix)

`scripts/run_soft_replay_validation.py` and `aggregate_soft_replay_validation.py` (data in `data/soft_replay_validation/metrics.csv`) validate the `reps-soft-replay` mechanism (see `../MODIFICATIONS.md`). They run on **NSCC**, not MPRDMA, at fixed B=8 over healthy, asym1, asym8, asym16, asym32 and asym4_r95, with four arms: baseline, `-reps_soft_replay` with fixed P=1.0, with P = ECN EWMA, and EWMA without the filter. The results are not comparable to, and are not mixed with, the Part 1/2 CSVs.

## Lineage

Listed in [`../README.md`](../README.md). Builds on exp26/exp27
(`fat_tree_1024_1os_2t_400g`, tornado, `-use_srv6 -paths 32`, MPRDMA, seed 42);
adds one htsim diagnostic-counter patch (`metrics-counters`) and no new failure
flags — the degradation is driven entirely by the pre-existing `-failed` /
`-skip_asy` / `-down_ratio` flags.
