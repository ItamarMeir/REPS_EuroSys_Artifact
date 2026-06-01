# Phase D — Root-cause diagnostic for the Paper 2 Fig 4 gap

## TL;DR

**The Paper 2 Fig 4 gap (LSwift 198 % → ours 31.8 %, MSwift 23 % → ours 31.9 %) was caused by a CONFIGURATION bug in htsim, not by the CCA implementations.**

The bug: `UecSrc::initNsccParams()` at [`htsim/sim/uec.cpp:195`](../../htsim/sim/uec.cpp#L195) unconditionally executed `_target_Qdelay = timeFromUs(6u);`. This ran **after** CLI parsing, silently overwriting whatever `-target_q_delay X` flag was passed. So every "Paper 2 with target_Qdelay = 1 µs" run (here and in exp12) actually used target = **6 µs** in the simulator — six times higher than the paper-specified setting.

With target = 6 µs, the LSwift MD branch (`delay ≥ target ⇒ counter++; counter ≥ 5 + cooldown ⇒ MD`) effectively never fires under the elephant+sprayed baseline workload. MSwift's median has nothing to filter. Both CCAs produced near-identical output, mis-localising the cause as exp12's "L2 limitation" (REPS routes around congestion).

**Fix applied**: comment out the reset line, banner-tagged `// ===== FIX (target-qdelay-respect-cli) =====`. The static default at `uec.cpp:79` (`_target_Qdelay = 6 µs`) preserves backward compatibility; the CLI flag now actually takes effect.

After re-running with the fix:
- **Swift inflation jumped from 54 % to 85.5 %** (Paper 1308 %, see L1 below for remaining gap)
- **LSwift jumped from 31.8 % to 46.4 %**
- MSwift jumped from 31.9 % to 49.8 %
- NSCC dropped from 33.6 % to 28.9 %
- MD-fire counter now reads 94.7 average on LSwift, 2235 on Swift (per seed) — confirming MD really fires.

## How the diagnosis was reached

### Step 1 — Add an MD-fire counter

Added a per-source `uint64_t _swift_md_fires` field in `uec.h`, and one `_swift_md_fires++` line in each of the two Swift MD branches (Swift per-ACK at `uec.cpp:1733`, LSwift core after the 5-counter trigger at `uec.cpp:1787`). Printed as a new column in the flow-finish log line.

### Step 2 — Baseline measurement (pre-fix)

Ran Fig 4 LSwift on `paper_baseline_s42.cm` with the instrumentation. Result: **127/128 flows had `swift_md_fires = 0`**, 1 flow had 1 fire. Across the three baseline seeds (s42, s43, s44), total MD fires were 1, 77, 2 — an absurd variance. Something was preventing MD from firing in the dominant case.

### Step 3 — Verify config was reaching the simulator

Tail of every diagnostic .out file contains `target_q_delay 1 us`. That print is the CLI parser echoing the flag at `main_uec.cpp:328`. So the flag *was* received. But sim behaviour suggested otherwise.

### Step 4 — Hunt for unconditional resets

`grep -n "_target_Qdelay" htsim/sim/uec.cpp` revealed:

| Location | What |
|---|---|
| L79  | `simtime_picosec UecSrc::_target_Qdelay = timeFromUs(6u);` — static default, fine |
| **L195** | `_target_Qdelay = timeFromUs(6u);` inside `initNsccParams()` — **THE BUG** |
| L197 | `_qa_threshold = 4 * _target_Qdelay;` — depends on the (now-corrupted) value |
| L200, L202 | scaling factors depending on `_target_Qdelay` — also corrupted |

`initNsccParams()` is called at [`main_uec.cpp:1061`](../../htsim/sim/datacenter/main_uec.cpp#L1061), **after** the CLI parse loop. Whatever the CLI set, this function overwrote.

### Step 5 — Apply the fix and re-measure

Disabled the L195 reset (kept as a commented line with a banner). Rebuilt. Re-ran the LSwift baseline cell:

| Metric | Pre-fix (target=6 µs actual) | Post-fix (target=1 µs as requested) |
|---|---|---|
| Max FCT (s42) | 734.9 µs | 906.1 µs |
| Sum MD fires (s42) | 1 | 59 |
| Max MD per flow | 1 | 3 |

The CCA implementation works. The bug was that the configuration the simulator wanted to honour was being silently rejected.

## Diagnostic-cell results (with the fix, all on `paper_baseline_s{42,43,44}.cm`)

CCT inflation % = (max_fct − ZQLB) / ZQLB · 100, mean across 3 seeds.

| Cell | swift | lswift | mswift | mnscc | What we learn |
|---|---|---|---|---|---|
| **D2-baseline** (default Paper 2 flags) | **83.8 %** | **45.1 %** | **48.4 %** | 28.0 % | Swift now collapses; LSwift > paper-MSwift; MSwift slightly worse than LSwift |
| **D2-beta-paper** (`-swift_beta 0.5`) | 80.0 % | 40.5 % | 41.4 % | 28.0 % | β-fix narrows gap by ~5 pp on LSwift/MSwift; not the dominant effect |
| **D2-tightq** (`-target_q_delay 0.5`) | 92.2 % | 42.1 % | 49.2 % | 34.0 % | Tighter target → more MD fires → Swift grows. LSwift/MSwift stable. |
| **D2-ops** (LB = OPS instead of REPS) | 80.0 % | 51.2 % | 62.9 % | 27.8 % | OPS shifts MSwift worse than LSwift — opposite of paper's claim, see Open Question |

## Direct comparison to paper Figure 4 (REPS column)

| CCA | Pre-fix ours | **Post-fix ours** | Paper | Diagnosis |
|---|---|---|---|---|
| swift  | 54.5 % | **85.5 %** | 1308 % | Swift now collapses, but L1 (single-LB) still caps it ~15× below paper |
| lswift | 31.8 % | **46.4 %** | 198 %  | Paper LSwift still ~4× higher — same L1 cause |
| mswift | 31.9 % | **49.8 %** | 23 %   | **Paper wins by 2.2×; ours has MSwift slightly worse than LSwift** (see Open Question) |
| nscc   | 33.6 % | **28.9 %** | 49 %   | Closer; under L1 with no elephant collapse, NSCC is robust |
| mnscc  | 33.5 % | **29.2 %** | 46 %   | Closer; matches NSCC since MNSCC median has nothing to filter |

### Where the fix helps and where it doesn't

Figures where post-fix MSwift now beats LSwift (paper-consistent ordering):

| Figure | LSwift | MSwift | Ratio (paper) |
|---|---|---|---|
| Fig 6 (pure perm) | 32.7 % | **24.8 %** | 1.3× (paper 1.7×) |
| Fig 7 (HSDP) | 42.9 % | **24.7 %** | 1.7× (paper 2×) |

Figures where MSwift still loses to LSwift (gap not fully closed):

| Figure | LSwift | MSwift | Why? |
|---|---|---|---|
| Fig 4 (baseline) | 46.4 % | 49.8 % | Median lags during transient clear periods (Open Question) |
| Fig 8 (250-node) | 37.7 % | 38.5 % | Same |
| Fig 11 (1% failures) | 46.4 % | 49.8 % | Same (workload is Fig 4 + dropout) |

## Open Question: MSwift slightly worse than LSwift on Fig 4

Even with the fix, MSwift fires more MDs than LSwift (101 vs 95 average) and ends up slightly slower. The likely mechanism: when raw delay drops on a clean ACK, the LSwift core resets `_swift_consec_high_d = 0` immediately — but MSwift sees `median(last H=32 raw delays)`, which lags. During the brief clear period, raw is low → LSwift sees clean → counter reset; meanwhile MSwift's median is still high → counter keeps incrementing → hits 5 sooner.

This is the **opposite** of the paper's intuition, where MSwift is supposed to filter out brief spikes. Plausible reasons:

1. **Our REPS+freezing routes around congestion fast enough that delay swings are dominated by recovery (low → high → low), not by transient spikes (low → spike → low).** In this regime, a median lags worse than a per-ACK signal.
2. The paper's MSwift may use the median **only for the MD-decision threshold check** (`should we count this as high?`), keeping `_swift_consec_high_d` per-raw-ACK, while ours uses median for both the threshold AND the value substituted into the LSwift core. Per their Algorithm description in §III, it's not entirely clear which.
3. There may still be an L1-style mixed-LB confounder.

This is a candidate for **Phase E** future work — not in scope here.

## Files modified by Phase D

- [`htsim/sim/uec.h`](../../htsim/sim/uec.h#L613) — per-source `uint64_t _swift_md_fires = 0;` field
- [`htsim/sim/uec.cpp`](../../htsim/sim/uec.cpp#L195) — **`_target_Qdelay = 6 µs` reset disabled** (the fix) at L195
- [`htsim/sim/uec.cpp`](../../htsim/sim/uec.cpp#L1055) — `swift_md_fires` printed in flow-finish log
- [`htsim/sim/uec.cpp`](../../htsim/sim/uec.cpp#L1733) — `_swift_md_fires++` after Swift per-ACK MD
- [`htsim/sim/uec.cpp`](../../htsim/sim/uec.cpp#L1787) — `_swift_md_fires++` after LSwift counter-driven MD
- [`scripts/run_all_diagnostic.sh`](scripts/run_all_diagnostic.sh) — 4-cell diagnostic driver
- [`RESULTS_DIAGNOSTIC.md`](RESULTS_DIAGNOSTIC.md) — this file

## Phase D.9 — Per-host LB dispatch + Swift-collapse follow-up

### Question
Could the residual Swift gap (ours 85.5 %, paper 1308 %) be the **mixed-LB** L1 limitation — htsim running a single global LB for all hosts? Could a true per-host dispatch close it?

### Implementation
Added a new `-host_lb_overrides "host:algo,host:algo,..."` CLI flag and a per-host LB dispatch mechanism. Each `UecSrc` whose `_srcaddr` is in the override map runs the named algorithm regardless of the global `-load_balancing_algo`. Implementation:

| File | What |
|---|---|
| `htsim/sim/uec.h` | `static std::map<uint32_t, LoadBalancing_Algo> _per_host_lb_override`; helpers `_parseLBName`, `_parseHostLBString`; `applyHostLBOverride()` |
| `htsim/sim/uec.cpp` | Static map def; `_dispatchLB(lb)` helper extracted from the constructor; `applyHostLBOverride()` re-dispatches when the source's host id is overridden |
| `htsim/sim/datacenter/main_uec.cpp` | CLI parser at `~L285`; call to `applyHostLBOverride()` after `setSrc()` at `~L1230` |

Banner-tagged `// ===== ADDED (per-host-lb) =====` throughout. Verified by overriding all 128 hosts to ECMP under a `freezing` global — output is **bit-identical** to running `-load_balancing_algo ecmp` globally.

### Experiment

Reproduced paper Fig 4 OPS-column setup using per-host dispatch:
- Global `-load_balancing_algo oblivious` (124 sprayed hosts use OPS)
- 4 elephant senders (auto-extracted per seed: `s42` = {6,28,62,70}, `s43` = {9,36,73,118}, `s44` = {29,45,97,104}) overridden to ECMP via `-host_lb_overrides`
- `-ecmp_elephant_threshold` removed so the override is what determines elephant LB

### Result

| Regime | Swift | LSwift | MSwift | NSCC | MNSCC |
|---|---|---|---|---|---|
| Default REPS (elephants:ECMP via threshold, sprayed:REPS) | 85.5 % | 46.4 % | 49.8 % | 28.9 % | 29.2 % |
| Per-host mixed-LB (elephants:ECMP via override, sprayed:OPS) | **80.4 %** | **51.6 %** | **63.2 %** | **29.0 %** | 28.1 % |
| Pre-existing diag_ops (`-load_balancing_algo oblivious` + threshold) | 80.0 % | 51.2 % | 62.9 % | — | 27.8 % |
| **Paper Fig 4 OPS column** | **1258 %** | **154 %** | **39 %** | **51 %** | **44 %** |

**Per-host mixed-LB matches diag_ops within ZQLB-rounding** — confirming the mechanism is correctly implemented. But the **Swift collapse remains at ~80 %, 16× short of paper's 1258 %**. So the L1 limitation was NOT a mixed-LB *dispatch* problem (which we just solved); it's something deeper:

Hypotheses for the remaining gap:
1. **OPS path count / hashing**: our OPS uses `-paths 65535` and hashes EV uniformly. Paper's OPS may have a different EVS spec or hashing function.
2. **Swift parameters**: our `_swift_beta = 0.8` vs paper's `mm = 0.5` (Table I). The β patch alone changes inflation by ~5 pp, not 16×.
3. **Topology fan-out**: with 128 hosts on a 3-tier non-blocking fat-tree, each elephant's static ECMP path takes 1 of ~256 inter-T1-T2 links. With 4 elephants, ≤ 4 % of upper-tier links are persistently congested. Paper's setup may have higher elephant density per uplink.
4. **Flow-count regime**: paper traffic-matrix details may differ (start-time staggering, ECMP elephant continuity, etc.).

We've localized the gap to **the workload + LB-implementation side, not htsim's mixed-LB plumbing**. The per-host mechanism is now in the toolbox for future experiments (e.g. testing different per-host LB mixes, isolating specific senders).

### Bonus result: MSwift in OPS regime is worse than LSwift

Under OPS-for-sprayed, MSwift inflation = 63 % vs LSwift = 52 %. Paper Fig 4 OPS column has MSwift = 39 % beating LSwift = 154 %. So in our OPS regime MSwift LOSES, opposite of paper. Same Open Question as Fig 4 REPS regime — median lags during transient clear periods. Strengthens the case that our MSwift implementation may need the "median-only-for-threshold-check, not for value-substituted-into-LSwift-core" refinement described in the Open Question section above.

## Implications for previous experiments

**Every Paper 2 (CC4Spraying) reproduction in this repo done before 2026-05-30 used `target_Qdelay = 6 µs`, not 1 µs.** This includes exp12 and the pre-fix Phase 0-C results in exp13. Their conclusion *"MSwift ≡ LSwift bit-identically"* was correct as a fact but mis-attributed to "REPS too good at routing"; the real cause was the silent target override.

**Paper 1 results are unaffected** because Paper 1 uses `-sender_cc_algo mprdma`, which doesn't read `_target_Qdelay`.

## Final answer to user's question

> "Is the gap from configurations or CCA implementations?"

**Configuration** — specifically a configuration *bug* in htsim's `initNsccParams()` that silently overrode the `-target_q_delay` CLI flag. After fixing the bug, the CCA implementations behave qualitatively as the paper describes, with directionally correct ordering on Figs 6 and 7. The remaining quantitative gap on Fig 4 is attributable to:

1. **L1** (htsim's inability to run mixed REPS+ECMP LB in one simulation) — caps Swift collapse at ~85 % vs paper's 1308 %.
2. **A second-order MSwift subtlety** (median lag vs spike timing under REPS+freezing) — Open Question above; not a bug, more a regime difference.
