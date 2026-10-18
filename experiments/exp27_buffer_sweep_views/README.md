# exp27 — buffer-sweep views

Raw-time / transposed renderings of the SRv6 buffer sweep.

- **Plot 1** re-plots **exp26**'s fig2 micro slice (no new sims).
- **Plot 2** runs the **same panel on a bigger fabric** — K=16 3-tier fat tree,
  `-paths 64`, B up to 64 — so it needs new htsim runs (`scripts/run_k16_3t.py`).
- **Plot 3** fixes the workload (tornado 4 MiB) and sweeps the 3-tier fat-tree
  radix **K = 4, 8, 16** (`#paths = (K/2)² = 4, 16, 64`) as grouped bars
  (`scripts/run_k_sweep.py` + `scripts/plot_k_sweep.py`); K=16 reuses plot 2.
- **Plot 4** holds the exp26 2-tier fabric fixed and sweeps only the **BDP the
  ECN/queue/cwnd thresholds derive from** (`scripts/run_bdp_sweep.py` +
  `scripts/plot_bdp_sweep.py`) — the control that identifies what actually
  drives the plot-1 vs plot-2/3 difference.
- **Plot 5** sweeps **tornado flow size** (1–64 MiB) with everything else fixed,
  on both fabrics (`scripts/run_small_flows.py`, `run_2tier_flows.py`,
  `plot_small_flows.py --fabric {3t,2t}`) — finds a second resonance, this one
  in flow size.
- **fig4 views (F1/F4/F5)** repeat the transpose (F1), the BDP sweep (F4) and
  the flow-size sweep (F5) on exp26's **`fig_4_asymmetric`** condition
  (`-failed`, degraded ToR uplinks) to test whether the asymmetric-regime win is
  *also* a resonance. It is not — see "## fig4 (asymmetric) views" below. The
  three run drivers take a `--failed N` flag; plots are
  `scripts/plot_fig4_{bdp_sweep,small_flows}.py` and
  `plot_micro_bars.py --fig fig4 --condition asym4`.

exp26's figures are 1:1 reproductions of the paper's "network health" figures,
which plot **speedup vs a baseline**. That form hides the raw FCT numbers and
pins the baseline arm at a fixed point. exp27 re-plots the same cells as
**absolute time**, in whatever layout makes a given comparison legible.

## Arms

| arm | LB flags | colour |
|-----|----------|--------|
| `ops` | `-load_balancing_algo oblivious -use_srv6 -paths N` | `#d95f02` (orange) |
| `reps_b<B>` | `-load_balancing_algo freezing -use_srv6 -paths N -reps_buffer_size B` | viridis ramp over B |

Plot 1: `N=32`, `B ∈ {1,2,4,8,16,32}`. Plot 2: `N=64`, `B ∈ {1,2,4,8,16,32,64}`.
All arms: SRv6 source routing, sender-only **MPRDMA** CC (`-sender_cc_only
-sender_cc_algo mprdma`). A given B keeps the same viridis colour as every exp26
figure. Neither plot passes `-disable_tor_ecn` — matching the paper's
`run_symmetric.py` template, so `tor_ecn_reenabled=1` in every row (as in exp26).

## Plots

`plots/` is split into **`fig2/`** (healthy) and **`fig4/`** (asymmetric). The
BDP-sweep and flow-size-sweep figures are emitted in two forms —
`…_lines.png` and `…_bars.png` — from one data path via
`scripts/sweep_render.py`.

### Plot 1 — `plots/fig2/fig2_micro_bars.png`

Raw-time transpose of `exp26/plots/fig2_micro.png` (paper Figure 2, synthetic
"micro" panel).

- **Source slice**: `fig == "fig2"`, `condition == "healthy"`, workload
  `micro::{incast,perm,tornado}_s<bytes>`. 9 workloads × 7 arms = 63 rows,
  written verbatim to `data/fig2_micro_maxfct.csv`.
- **Layout**: 2×3 grid. Columns = Incast 8:1 | Permutation | Tornado. Top row
  y = raw `Max FCT (µs)`, own y-scale per panel (incast reaches ~2750 µs;
  perm/tornado stay under ~400 µs, so a shared axis would flatten them). Bottom
  row = the same bars with y = **speedup vs OPS** on Max FCT
  (`speedup_vs_ops_max` = `ops_max / arm_max`, dashed reference at 1.0), common
  y-scale across the three bottom panels. This is the axis `fig2_micro` uses,
  shown beside the raw numbers it hides.
- **x-axis**: flow size, 4 / 8 / 16 MiB (grouped-bar categories).
- **bars**: one per arm (`ops`, then `reps_b1..b32`); OPS speedup is 1.0 by
  definition.
- **encoding**: exp26 arm colour + a distinct matplotlib hatch per REPS buffer
  (`//`, `\\`, `xx`, `..`, `oo`, `**` for B = 1,2,4,8,16,32); OPS left plain.
- **single seed (42)** in this slice → no error bars.

Regenerate:

```bash
cd scripts && python3 plot_micro_bars.py     # needs pandas + matplotlib (WSL python3)
```

### Plot 2 — `plots/fig2/fig2_micro_bars_k16_3t.png`

Same figure, **new simulations** on the **K=16 3-tier fat tree**
(`fat_tree_1024_1os_3t_400g.topo`, 1024 hosts, **64 distinct cross-pod paths**;
the topology exp21/exp22 use).

- **What changes vs plot 1**: `-topo` → 3-tier 1024-host; `-paths 64`; buffer
  sweep `B ∈ {1,2,4,8,16,32,64}`; flow sizes `4/8/16/32/64 MiB`; `-q/-ecn/-cwnd`
  recomputed from the 3-tier BDP.
- **3-tier BDP** (`getBDP(400,3,1000)` = 152.48 pkts ≈ 610 KB) drives
  `-q 152 -ecn 38 114 -cwnd 228` — the same "1 BDP queue / ECN 25–75 % / cwnd
  1.5 BDP" relationship exp26's micro panel uses at 2 tiers (`101 / 25 76 /
  151`). Verified: the tiers=2 form reproduces exp26's live values exactly.
- **Everything else identical to exp26 `run_sym.py` `micro_flags`** (healthy):
  seed 42, MPRDMA sender-CC, `-enable_qa_gate -disable_trim -sack_threshold 4000
  -connections_mapping -linkspeed 400000 -end 90000`.
- Matrix: 3 patterns × 5 sizes × 8 arms = **120 runs**. Driver writes the
  exp26 `runs/fig2/micro/<wl>/healthy/<arm>/` layout so `exp26/scripts/
  aggregate.py` aggregates it unchanged into `data/k16_3t/summary.csv`.

Reproduce (Docker, per CLAUDE.md — long job, ~5 h):

```bash
docker run --rm -v "$PWD:/workspace" -w /workspace/experiments/exp27_buffer_sweep_views/scripts \
  reps-artifact:latest python3 -u run_k16_3t.py --prep-cms
# then aggregate + plot (WSL python3):
EXP26_RUNS=$PWD/experiments/exp27_buffer_sweep_views/runs \
EXP26_DATA=$PWD/experiments/exp27_buffer_sweep_views/data/k16_3t \
  python3 experiments/exp26_srv6_buffer_sweep/scripts/aggregate.py
cd experiments/exp27_buffer_sweep_views/scripts && python3 plot_micro_bars.py \
  --summary ../data/k16_3t/summary.csv --sizes 4,8,16,32,64 \
  --bladder 1,2,4,8,16,32,64 --out ../plots/fig2/fig2_micro_bars_k16_3t.png \
  --title-suffix "K=16 3-tier fat tree, -paths 64"
```

### Plot 3 — `plots/fig2/fig2_tornado_k_sweep.png`

Tornado 4 MiB, SRv6, on the **3-tier** fat tree at radix **K = 4, 8, 16**, so
the SRv6 path count `(K/2)²` sweeps **4 → 16 → 64**. Grouped bars, 2 stacked
panels (raw Max FCT | speedup vs OPS), x = 3 K groups. The arms in a group are
`ops` + `reps_b{1..(K/2)²}`, so K=4 shows 4 bars, K=8 shows 6, K=16 shows 8
(not every B is relevant at every K). Colour + hatch per B kept from plots 1–2;
vertical value label on every bar; speedup panel zoomed near 1.0. `-q/-ecn/-cwnd`
= 152/38 114/228 for all K (BDP is tier-based, not K-based). K=4/8:
`fat_tree_{16,128}_1os_3t_400g.topo`, seed 42, 10 new runs; K=16 reused from
plot 2 (`data/k16_3t/summary.csv`, `micro::tornado_s4194304`).

```bash
docker run --rm -v "$PWD:/workspace" -w /workspace/experiments/exp27_buffer_sweep_views/scripts \
  reps-artifact:latest python3 -u run_k_sweep.py
EXP26_RUNS=$PWD/experiments/exp27_buffer_sweep_views/runs \
EXP26_DATA=$PWD/experiments/exp27_buffer_sweep_views/data/k_sweep \
  python3 experiments/exp26_srv6_buffer_sweep/scripts/aggregate.py
cd experiments/exp27_buffer_sweep_views/scripts && python3 plot_k_sweep.py
```

## Results

**Plot 1.** The speedup axis in `fig2_micro` compresses a real effect and a
non-effect into the same visual band; the raw bars separate them:

- **Permutation / Tornado, healthy network**: REPS beats restricted-EV OPS on
  Max FCT. Permutation 4 MiB: OPS 120.7 µs → REPS ~98 µs. Tornado 8 MiB: OPS
  215.9 µs → REPS ~184 µs. Tornado 4 MiB is the widest gap (OPS 136 → REPS 97).
- **Incast (8:1)**: no arm separates — OPS 2752.8 µs vs REPS B=8 2769.4 µs at
  16 MiB. The receiver downlink is the bottleneck; LB cannot help.
- **Buffer size B**: flat across 1..32 in every cell (B=2..32 are frequently
  bit-identical in `summary.csv`; only B=1 occasionally differs).

**Plot 2** (120 runs, 0 failures). On the K=16 3-tier / 64-path fabric the
REPS-vs-OPS Max-FCT gap **collapses to ~1.05–1.08×** (vs up to 1.4× on the
2-tier / 32-path fabric of plot 1) and is **flat across flow size** 4→64 MiB:

- perm B=8 speedup 1.05 / 1.04 / 1.06 / 1.08 / 1.07 at 4/8/16/32/64 MiB;
  tornado near-identical. The OPS tail (`max − mean`) grows in absolute µs with
  size but stays a ~constant 5–7 % of FCT — the signature of a *steady-state*
  load-imbalance penalty, not a startup transient (which is what decays with
  size on the 2-tier fabric).
- **Incast**: ~1.02× at 4 MiB, easing to **0.99–1.00× at 32/64 MiB** (REPS a
  hair slower than OPS) — the receiver downlink is the bottleneck and REPS's
  path churn is pure overhead there.
- **B**: B=1 ≈ 1.03×, B ≥ 2 plateau at ~1.05–1.08× — flat in every cell.

Why the gap shrank vs plot 1: 64 equivalent paths + a BDP-matched queue let
oblivious spray balance near-perfectly, so there is little headroom for any LB
to win. See plot 3 for the path-count sweep.

**Plot 3** (tornado 4 MiB, 3-tier, K = 4/8/16 → 4/16/64 paths; 18 cells). The
result is the *opposite* of the naïve "more paths → smaller gap": **within the
3-tier family the REPS edge grows with K** — speedup vs OPS ≈ **1.01× (K=4) →
1.03× (K=8) → 1.06× (K=16)**.

- OPS raw Max FCT climbs with fabric size (**103.7 → 107.1 → 110.3 µs**) while
  REPS is essentially K-invariant (~104–106 µs). A bigger 3-tier fabric gives
  oblivious spray more switches/hops to accumulate transient imbalance at; REPS
  steers around it and holds near-optimal.
- At **K=4** (16 hosts, 4 paths, ~4 flows/path) the network barely congests —
  REPS B=1 is even **0.4 % slower** than OPS; B ≥ 2 recover a ~1 % edge.
- **B flat** above B=2 at every K; B=1 consistently lags by ~1–2 %.

**Plot 4** — the control that settles it
(`plots/fig2/fig2_tornado_bdp_sweep_{lines,bars}.png`).
exp26's **2-tier** fabric held fixed (`fat_tree_1024_1os_2t_400g`, `-paths 32`),
tornado 4 MiB, seed 42; only the BDP feeding `-q B / -ecn B/4 3B/4 / -cwnd 1.5B`
is swept (B ∈ {50, 75, 101, 152, 250}).

| B | q / kmin | OPS max FCT | REPS B8 max | OPS ÷ REPS |
|---|---|---|---|---|
| 50 | 50 / 12 | 121.0 | 119.2 | **1.02×** |
| 75 | 75 / 18 | 124.2 | 97.6 | 1.27× |
| **101** | 101 / 25 | **136.5** | 97.1 | **1.41×** ← exp26 / plot 1 |
| 152 | 152 / 38 | 103.4 | 98.3 | **1.05×** ← plots 2–3 |
| 250 | 250 / 62 | 103.6 | 99.9 | 1.04× |

All sweep figures (`*_bdp_sweep_*`, `*_small_flows_*`, fig2 + fig4) now plot the
**full REPS ladder B = 1, 2, 4, 8, …, #paths**. It confirms the finding is not an
artifact of the {1, 8, 32/64} subset: **REPS buffer size is flat above B ≈ 2 at
every point** (B = 2/4/8/16/32[/64] land on top of each other in every cell);
only B = 1 differs — a ~1–3 % penalty on the healthy fabric, and it degrades
badly on large flows / under sustained asymmetry (see exp26 fig4 B ≤ 2 knee).

The gap is a **resonance in BDP-provisioning that peaks at B = 101 — exp26's own
config — and falls off on both sides.** At B ≤ 50 the queue (0.5 real BDP) is
undersized for *everyone* (REPS also +23 % over its optimum) so they converge; at
B 75–101 `kmin` (18–25 pkt) coincides with the all-flows-start-at-t=0 burst and
OPS's unlucky flows trip ECN, get cut, never recover; at B ≥ 152 `kmin` clears
the burst and OPS ≈ REPS.

**So the plot-1 vs plot-2/3 difference is entirely BDP-provisioning, not
topology / tiers / path count.** exp26's fig2 micro panel (and the paper's
`-q BDP -ecn BDP/4 3BDP/4` recipe at a 2-tier-sized BDP) sits on the peak of that
resonance; the 3-tier plots at B=152 sit past it. A separate isolation run —
2-tier topo + B=152 thresholds — reproduces the 3-tier ~1.05× exactly
(`data/_iso/`). REPS's durable advantage is the asymmetry / failure regime
(exp26 fig4/fig7: 1.3–70×), not the healthy symmetric fabric.

```bash
docker run --rm -v "$PWD:/workspace" -w /workspace/experiments/exp27_buffer_sweep_views/scripts \
  reps-artifact:latest python3 -u run_bdp_sweep.py
EXP26_RUNS=$PWD/experiments/exp27_buffer_sweep_views/runs \
EXP26_DATA=$PWD/experiments/exp27_buffer_sweep_views/data/bdp_sweep \
  python3 experiments/exp26_srv6_buffer_sweep/scripts/aggregate.py
cd experiments/exp27_buffer_sweep_views/scripts && python3 plot_bdp_sweep.py
```

**Plot 5** — flow-size sweep
(`plots/fig2/fig2_tornado_small_flows_{2t,3t}_{lines,bars}.png`).
Tornado, everything fixed except flow size. 3-tier 1/2/3/4 MiB new
(`run_small_flows.py`), 8/16/32/64 reused from plots 2–3; 2-tier 1/2/3 MiB new
(`run_2tier_flows.py`), 4/8/16 reused from exp26.

- **2-tier, q = 1·BDP (kmin=25)** — a **second sharp resonance, in flow size**:

  | tornado | 1–3 MiB | **4 MiB (~10 BDP)** | 8 MiB | 16 MiB |
  |---|---|---|---|---|
  | OPS ÷ REPS B8 | ~1.03–1.06 | **~1.38** | ~1.19 | ~1.07 |
  | # OPS flows hit (>1.12·p50) | **0** | **29** | 12 | 0 |

  Seed-robust (4 MiB across seeds 42/43/44: 1.40 / 1.39 / 1.35). All flows
  `start 0`; the synchronized initial burst needs τ_feedback ≈ 30–40 µs (a few
  RTT) to build a hot-link queue past kmin, mark, and cut cwnd. A flow **escapes**
  if FCT ≲ τ_feedback (≤ 3 MiB, 0 hits); is **maximally hit** if FCT ≈
  2–3·τ_feedback (caught mid-transfer, ends before additive-increase restores
  cwnd — 4 MiB); **amortizes** the fixed recovery cost if FCT ≫ τ_feedback
  (≥ 8 MiB). **exp26's fig2 micro tornado-4MiB headline sits at the intersection
  of BOTH resonances** — B/BDP ≈ 1.0 *and* size ≈ 10·BDP.

- **3-tier, q = 1·BDP (kmin=38)** — **no size spike at all**: kmin is high
  enough the synchronized burst never crosses it (0 hits at every size). Only a
  smooth steady-state gap creeping 1.03 (1 MiB) → 1.07 (64 MiB). Seed-robust
  (2/4/8 MiB across seeds 42/43/44, ±0.01).

## fig4 (asymmetric) views — F1, F4, F5

Same view methodology applied to exp26's **`fig_4_asymmetric`** (= fig2 + a set
of degraded ToR uplinks). The question: the fig2-micro headline turned out to be
a double resonance — **is the asymmetric-regime win (exp26 fig4: perm/tornado
1.4–1.76×) also a resonance, or is it the robust effect the bottom-line claim
assumes?**

**The failure knob.** exp26 fig4 micro adds `-failed 4 -skip_asy` on its
**128-host / 8-path** `fat_tree_128_1os_2t_400g` fabric: 4 seed-drawn ToR→Agg
uplinks throttled to **50 % linkspeed** (`_failed_link_ratio = 0.5`;
`fat_tree_topology.cpp:44,982`), not link-down; `-skip_asy` caps it to one
degraded uplink per selected ToR. F4/F5 reuse exp27's **1024-host** healthy
baselines (plots 4/5), so they scale the knob to **`-failed 32`** — same
degraded-uplinks-per-host ratio (≈ 3.1 %) as the 8×-smaller fig4 fabric. On the
1024-host 2-tier that is `fail_every = 1` → every ToR loses one uplink; on the
3-tier, 32 of 128 ToRs. Condition string `asym32`. New runs write
`runs/fig4/micro/<wl>/asym32/<arm>/`; `data/fig4_asym/summary.csv`.

### F1 — `plots/fig4/fig4_micro_{bars,scatter}_128host.png` (0 new sims)

Raw-time transpose of `exp26/plots/fig4_micro.png` — the exact 45-cell fig4 micro
slice (`condition == asym4`), on exp26 fig4's own **128-host / 8-path**
`fat_tree_128_1os_2t_400g` (`-failed 4`), B ≤ 8. Faithful exp26 reproduction, but
**a different fabric from plot 1**, so not directly comparable to it.

- **Permutation / Tornado**: speedup vs OPS **grows with flow size** —
  1.40 → 1.52 → 1.71× (perm) and 1.40 → 1.50 → 1.76× (tornado) at 4 / 8 / 16 MiB.
- **Incast (8:1)**: 0.98–1.00× — REPS a hair slower (receiver-downlink bound).

### F1′ — `plots/fig4/fig4_micro_{scatter,bars}_1024host.png` (fig4 micro on the plot-1 fabric)

fig4's micro matrix **rerun on the 1024-host / 32-path fig2 fabric**
(`fat_tree_1024_1os_2t_400g`), `-failed 32 -skip_asy` (`asym32`, the same
≈3.1 %-of-uplinks scaling F4/F5 use), `-q 101 -ecn 25 76 -cwnd 151`, B ≤ 32,
sizes 4/8/16, seed 42 — **63 new runs** (`run_fig4_micro.py`). Now the only
variable vs plot 1 is healthy→asym. Emitted in **both** forms: the exp26/paper
horizontal scatter (`plot_micro_scatter.py`) and the raw-time transpose
(`plot_micro_bars.py`).

| workload | plot 1 (healthy) OPS÷REPS-B8 | **F1′ (asym32) OPS÷REPS-B8** |
|---|---|---|
| P. 4 MiB  | ~1.23× | **1.41×** |
| P. 8 MiB  | ~1.18× | 1.22× |
| P. 16 MiB | ~1.13× | 1.18× |
| T. 4 MiB  | ~1.40× (healthy resonance peak) | **1.39×** |
| T. 8 MiB  | ~1.17× | 1.23× |
| T. 16 MiB | ~1.07× | 1.20× |
| I. 8:1 (all) | ~1.00× | 1.00–1.02× |

- On this fabric the fig4-micro speedup does **not** grow with flow size (that
  was an 8-path, 128-host effect in F1) — it is ~1.4× at 4 MiB, settling to a
  durable **~1.2× floor** at 8/16 MiB. Where the healthy tornado resonance has
  decayed to ~1.07× (16 MiB), asymmetry still holds ~1.2×.
- **B ≤ 2 knee reproduces**: tornado 4 MiB `reps_b1` is only **1.04×**
  (pathological — 1-slot buffer stuck cycling onto bad paths) vs `reps_b8`
  1.39× — exactly exp26 fig4's finding, now on the 1024-host fabric.
- The tornado-4 MiB `asym32` cell here matches F5-2t's `tornado_2t4194304`
  cell exactly (identical config), and B=101 of F4 within 1-packet rounding.

### F4 — `plots/fig4/fig4_tornado_bdp_sweep_{lines,bars}.png` (BDP sweep + failure)

Twin of plot 4: exp26 2-tier fabric fixed (`-paths 32`), tornado 4 MiB, sweep
only the BDP feeding `-q B -ecn B/4 3B/4 -cwnd 1.5B`. The plot shows the
`asym32` condition only (`plot_fig4_bdp_sweep.py --healthy` overlays the plot-4
healthy curves for comparison); the healthy column below is from `data/bdp_sweep/`.

| B (q / kmin) | healthy OPS÷REPS-B8 | **asym32 OPS÷REPS-B8** |
|---|---|---|
| 50 / 12  | 1.02× | **1.26×** |
| 75 / 18  | 1.27× | **1.34×** |
| **101 / 25** | **1.41×** (peak) | **1.36×** |
| 152 / 38 | 1.05× | **1.56×** |
| 250 / 62 | 1.04× | **1.84×** |

**The asym32 curve is monotone-increasing in the derived BDP and never
collapses** — it is *anti-correlated* with the healthy resonance: the asymmetry
win is **largest exactly where the healthy win vanishes** (B ≥ 152). Looser
provisioning lets OPS's healthy-path flows speed up while its ~1/32 of packets
still pinned to half-speed links do not, so the Max-FCT spread *widens*.
The healthy startup-transient resonance and the asymmetric fixed-tax effect are
**different mechanisms that happen to overlap at B = 101**.

exp26 fig4's **B ≤ 2 pathology reproduces**: at B = 101, `asym32` `reps_b1` is
only **1.01×** (stuck cycling a 1-slot buffer onto bad paths) while `reps_b8` /
`reps_b32` hold 1.36×. Same knee exp26 README §fig4 describes.

### F5 — `plots/fig4/fig4_tornado_small_flows_{2t,3t}_{lines,bars}.png` (flow-size sweep + failure)

Twin of plot 5: tornado, everything fixed except size. Plots show `asym32` only
(`plot_fig4_small_flows.py --fabric {2t,3t} --healthy` overlays the plot-5
healthy curves); healthy rows in the tables below are from plots 5 / exp26.

**2-tier, q = 1·BDP** — the healthy 4-MiB spike vs a **broad `asym32` plateau**:

| tornado | 1 MiB | 2 MiB | 3 MiB | 4 MiB | 8 MiB | 16 MiB |
|---|---|---|---|---|---|---|
| healthy OPS÷REPS-B8 | 1.03 | 1.05 | 1.06 | **1.38** | 1.19 | 1.07 |
| **asym32 OPS÷REPS-B8** | 1.15 | **1.49** | 1.50 | 1.39 | 1.23 | 1.20 |

`asym32` is ≥ 1.15× at *every* size and never returns to 1.0; the lone healthy
spike at 4 MiB is a startup transient, the `asym32` plateau is the standing tax.
(`asym32` `reps_b1` dips to 1.04× at 4 MiB — the B ≤ 2 knee again.)

**3-tier, q = 1·BDP** — healthy is dead-flat (1.03 → 1.07 across 1–64 MiB, no
size dependence at all). `asym32` instead **grows with size and then holds
high**: B8 speedup ≈ 0.99× (1 MiB) → 1.16× (2) → 1.30× (4) → 1.54× (8) →
1.61× (32) → 1.57× (64 MiB). A real, large, size-dependent gap on the exact
fabric where the healthy comparison shows none. Single seed → the point-to-point
noise is large (B=1 shows a lone 3-MiB outlier at 1.54× where B8 is 1.09×); the
trend is not.

### Verdict on the bottom-line claim

**Confirmed and strengthened.** The asymmetry-regime REPS win is **not** a
BDP-provisioning or flow-size resonance:

- it is present across the whole B sweep and *strengthens* as provisioning
  loosens (F4), where the healthy win has already collapsed;
- it is a broad plateau across flow size (F5-2t) and *grows* with size on a
  fabric where the healthy gap is flat-zero (F5-3t, F1);
- mechanism: `-failed` imposes a **fixed** per-transfer throughput tax on
  oblivious spray (a constant fraction of packets on half-speed links) that no
  ECN/queue tuning removes; REPS rotates the bad entropy values out. This is
  orthogonal to the synchronized-startup transient that drives the healthy
  double resonance.
- caveat: a 1–2 slot circular buffer is **worse than OPS** under sustained
  asymmetry (reproduces exp26 fig4); the win needs B ≥ 4.

## Bottom line

exp26's "REPS beats OPS ~1.4× on a healthy symmetric fabric" (fig2 micro) is a
**double-resonance artifact** — the paper's `q = 1·BDP` recipe *and* a ~10·BDP
flow size, with all flows starting synchronized. Move off either peak (1.5·BDP
buffer, a different flow size, a 3-tier-sized BDP, or staggered arrivals) and the
healthy-fabric advantage is ≤ ~1.1×.

REPS's robust win is the **asymmetry / failure** regime — and the fig4 views
(F1/F4/F5) show it is genuinely robust: **not** a resonance, present across every
B-provisioning and flow size, in fact *largest where the healthy win vanishes*
(exp26 fig4 synthetic 1.3–1.8×; fig7/fig8 2–110×). It needs B ≥ 4; B ≤ 2 is
pathological under sustained asymmetry.

## Lineage

Row 27 in [`../README.md`](../README.md). Plot 1 + F1 re-plot exp26; plots 2–5
and F4/F5 add new htsim runs (3-tier topologies, a BDP-threshold sweep, a
flow-size sweep on both fabrics, and the `-failed 32` asymmetric twins), no new
`htsim` flags or code — the run drivers gained a `--failed N` option that appends
the stock `-failed N -skip_asy`. Project memory:
`reps_gap_is_bdp_provisioning_not_topology.md`.

Reproduce the fig4 views:

```bash
# F1 (128-host, exp26 fig4's own fabric) — no sims:
cd scripts
for form in bars scatter; do python3 plot_micro_$form.py \
  --summary ../../exp26_srv6_buffer_sweep/data/summary.csv \
  --fig fig4 --condition asym4 --sizes 4,8,16 --bladder 1,2,4,8 \
  --out ../plots/fig4/fig4_micro_${form}_128host.png; done
# F4 + F5 — Docker (reps-artifact), ~76 sims:
docker run --rm -v "$PWD:/workspace" \
  -w /workspace/experiments/exp27_buffer_sweep_views/scripts reps-artifact:latest bash -lc '
    python3 -u run_bdp_sweep.py  --failed 32 &&
    python3 -u run_2tier_flows.py --failed 32 --sizes 1048576,2097152,3145728,4194304,8388608,16777216 &&
    python3 -u run_small_flows.py --failed 32 --sizes 1048576,2097152,3145728,4194304,8388608,16777216,33554432,67108864'
EXP26_RUNS=$PWD/experiments/exp27_buffer_sweep_views/runs \
EXP26_DATA=$PWD/experiments/exp27_buffer_sweep_views/data/fig4_asym \
  python3 experiments/exp26_srv6_buffer_sweep/scripts/aggregate.py
cd experiments/exp27_buffer_sweep_views/scripts && python3 plot_fig4_bdp_sweep.py \
  && python3 plot_fig4_small_flows.py --fabric 2t \
  && python3 plot_fig4_small_flows.py --fabric 3t
```

F1′ (fig4 micro on the 1024-host fabric):

```bash
docker run --rm -v "$PWD:/workspace" \
  -w /workspace/experiments/exp27_buffer_sweep_views/scripts reps-artifact:latest \
  python3 -u run_fig4_micro.py                       # 63 runs
# (re-aggregate as above into data/fig4_asym), then:
cd experiments/exp27_buffer_sweep_views/scripts
for form in scatter bars; do python3 plot_micro_$form.py \
  --summary ../data/fig4_asym/summary.csv \
  --fig fig4 --condition asym32 --sizes 4,8,16 --bladder 1,2,4,8,16,32 \
  --out ../plots/fig4/fig4_micro_${form}_1024host.png; done
# fig2 companion scatter (0 sims):
python3 plot_micro_scatter.py \
  --summary ../../exp26_srv6_buffer_sweep/data/summary.csv \
  --fig fig2 --condition healthy --sizes 4,8,16 --bladder 1,2,4,8,16,32 \
  --out ../plots/fig2/fig2_micro_scatter.png
```

Raw stdout for all 139 `asym*` cells (63 F1′ micro + 76 F4/F5) is archived in
`runs_fig4_asym.tar.gz` (`tar -xzf runs_fig4_asym.tar.gz -C runs`; **re-extract
before re-aggregating** or the summary loses those rows). Each `plot_fig4_*`
script also takes `--healthy` to overlay the matching fig2 curves.

**Marker/hatch convention** (all line & scatter plots, exp26 + exp27): OPS =
filled orange square; each REPS buffer B = its own hollow marker shape, cycled
`o D ^ v X P *` for B = 1/2/4/8/16/32/64. Bar panels use a per-B hatch instead.
Defined once in `scripts/sweep_render.py` (`_SHAPES`) and
`exp26/scripts/plot.py` (`B_SHAPES` / `B_HATCH`) — identical lists.
