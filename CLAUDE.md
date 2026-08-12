# CLAUDE.md — Project guide for Claude Code agents

This file is the first-read document for any Claude Code session in this repo. It captures what has been built, where everything lives, and what the gotchas are, so you don't have to rediscover them from scratch.

---

## What this repo is

This is the **REPS EuroSys artifact** — a research simulator plus analysis code for the paper "REPS: Recycled Entropy Packet Spraying for Adaptive Load Balancing and Failure Mitigation". The simulator is `htsim`, extended with REPS.

On top of the paper artifact we built several independent extensions, all gated behind CLI flags and living entirely in `htsim/sim/`:
1. **State-aware NSCC + REPS** (`-state_aware_ecn`) — binary ECN gate driven by REPS freeze/unfreeze events + dynamic link-failure machinery. Experiments: exp01–03.
2. **Smart filter** (`-smart_filter_mode`) — continuous, evidence-based dampening of NSCC's MD step using REPS buffer saturation. Mutually exclusive with state-aware. Experiments: exp06.
3. **WTD in NSCC** (`-wtd_in_nscc`) — paper's "Wait to Decrease" (SMaRTT-REPS §3.6.1), gates MD on `_exp_avg_ecn ≥ 0.25`. Mutually exclusive with state-aware and smart-filter. Experiments: exp07 (complete; null result — see exp07 README §Results).
4. **PATH_RR** (`-load_balancing_algo path_rr`) — true round-robin over distinct physical paths using full source routing; bypasses per-hop ECMP. Clean baseline for comparing against entropy-spray algorithms.

The experiments for both live in `state_aware_experiments/`.

---

## Base artifact: setup, build, run, test

Python env (from repo root, in a clean venv):
```bash
python3 -m venv .venv
source .venv/bin/activate
./reps_pkg_install.sh
```

Full clean rebuild of `htsim` (equivalent to the `## Building` section below, but from clean):
```bash
cd htsim/sim
make clean && cd datacenter/ && make clean && cd ..
make -j 8 && cd datacenter/ && make -j 8 && cd ..
```

Reproducing the paper's figures (from `artifact_scripts/`, run after building `htsim_uec`):
```bash
cd artifact_scripts
./reps_quick.sh    # <2h, Figures 1,3,5,6,8,9,10,11,12,13,14
./reps_medium.sh   # ~4-6h, adds Figure 2
./reps_full.sh     # ~10h+, all figures
```
Or run a single figure's Python script directly (e.g. `python fig_1_symmetric_micro.py`). Results land in `artifact_results/<experiment>/`. **Never modify `artifact_scripts/` or `artifact_results/`** — they are the paper's original, unmodified artifact.

`traffic_gen/` unit tests (connection-matrix generator, independent of `htsim`):
```bash
cd traffic_gen
python -m unittest test_traffic_gen_utils.py
python -m unittest test_custom_random_number_generator.py
```

There is no test suite for `htsim/sim/` itself or for `state_aware_experiments/` — correctness there is validated by running experiments and inspecting output (grep for `enable on tor downlink 1`, event-count sanity checks, etc. — see `state_aware_experiments/RUNNING_EXPERIMENTS.md`).

---

## Directory map

```
REPS_EuroSys_Artifact/
├── htsim/sim/                  ← C++ simulator (build target: datacenter/htsim_uec)
│   ├── uec.h / uec.cpp         ← NSCC + REPS/FREEZING CC + LB logic
│   ├── pipe.h / pipe.cpp        ← link-failure flag
│   └── datacenter/
│       ├── main_uec.cpp         ← CLI entry point (new flags added here)
│       ├── fat_tree_topology.*  ← leaf-ECN flag
│       └── connection_matrices/ ← workload TM files
├── state_aware_experiments/    ← OUR WORK (state-aware extension + experiments)
│   ├── README.md               ← start here: lineage + takeaways
│   ├── ARCHITECTURE.md         ← code-level design, line references
│   ├── RUNNING_EXPERIMENTS.md  ← how to add a new experiment (written for future agents)
│   ├── workloads/              ← shared TM files + generators
│   ├── exp01_lb_dynamics_reps_v1/   ← findings only (raw data lost)
│   ├── exp02_lb_dynamics_freezing_v2/ ← findings only (raw data lost)
│   └── exp03_matrix_sweep_v3/  ← PRIMARY: full artifacts (plots, CSVs, scripts, runs.tar.gz)
├── artifact_scripts/           ← paper's original bash runners (don't modify)
├── artifact_results/           ← paper's original results (don't modify)
└── traffic_gen/                ← traffic matrix generator (not used in our experiments)
```

---

## Building

```bash
cd htsim/sim
make -j 8
cd datacenter && make -j 8
cd ../../..
test -x htsim/sim/datacenter/htsim_uec || echo "BUILD FAILED"
```

The binary is `htsim/sim/datacenter/htsim_uec`. Warnings during build are safe to ignore.

---

## The state-aware NSCC + REPS extension

### What it does

Every incoming ACK carries an ECN bit. The architecture splits how that bit is consumed:

- **Load Balancer (REPS or FREEZING)** — always sees the real ECN bit. ECN-marked ACKs rotate out the EV naturally.
- **Congestion Controller (NSCC)** — sees a *gated* ECN bit. The CC honors ECN only when the sender's internal flag `_network_is_asymmetric` is set. Otherwise the CC sees ECN=0, holds rate, and lets the LB handle spatial collisions.

The `_network_is_asymmetric` flag is set organically when the LB enters frozen mode (triggered by RTO, which fires when a link failure kills ACKs), and cleared when the LB exits frozen mode. No control-plane broadcast required.

### CLI flags added

| Flag | Effect |
|---|---|
| `-state_aware_ecn` | Master toggle (off by default). Enables CC gate + asymmetric-flag wiring. Forces `repsUseFreezing = true`. |
| `-disable_tor_ecn` | Enables leaf exception (`force_disable_tor_ecn = true`). **Required whenever `-sender_cc_only` is also passed.** |
| `-fail_link_time <fail_us> <recover_us>` | Schedules dynamic Agg↔Core pipe failure and recovery. |
| `-fail_link_target <agg> <core>` | Repeatable. Selects which Agg↔Core link(s) to fail. |
| `-log_reps_state <file>` + `-log_reps_state_src <id>` | Per-ACK CSV diagnostic log. |

`-exit_freeze <picoseconds>` already existed; our experiments use `200000000` (= 200 ms) to suppress mid-run thaws.

### Key code locations

| What | File | Line(s) |
|---|---|---|
| CC ECN-masking gate | `htsim/sim/uec.cpp` | ~1209 |
| FREEZING freeze entry + asymmetric-flag set | `htsim/sim/uec.cpp` | ~3040 |
| FREEZING unfreeze + asymmetric-flag clear | `htsim/sim/uec.cpp` | ~2653 |
| REPS freeze entry + flag set | `htsim/sim/uec.cpp` | ~3022 |
| REPS unfreeze + flag clear | `htsim/sim/uec.cpp` | ~2310 |
| `_network_is_asymmetric` flag declaration | `htsim/sim/uec.h` | ~static toggle + per-source flag |
| `Pipe::_failed` flag + early-drop | `htsim/sim/pipe.h` ~42-48, `pipe.cpp` ~65 |
| Leaf-ECN re-enable gotcha | `htsim/sim/datacenter/main_uec.cpp` | ~739 |
| `LinkFailureEvent` class | `htsim/sim/datacenter/main_uec.cpp` |
| `_enable_ecn_on_tor_downlink` guards | `htsim/sim/datacenter/fat_tree_topology.cpp` | ~737, 754, 783 |

### REPS vs FREEZING — which to use

**Always use `-load_balancing_algo freezing` (= paper-REPS, 8-slot bounded buffer)** for any paper-comparable or state-aware work.

`-load_balancing_algo reps` is a code-only simpler variant (unbounded `_next_pathid` list). It's retained for archaeology. The buffer instrumentation column to track is `fresh` (FREEZING) vs `recycle` (REPS).

---

## The critical `-disable_tor_ecn` gotcha

**This has burned us once and will burn you again if you forget.**

At `main_uec.cpp:739`:
```cpp
bool ecn_on_tor_dl = !receiver_driven && !force_disable_tor_ecn;
```

Passing `-sender_cc_only` sets `receiver_driven = false`. Without `-disable_tor_ecn`, this **re-enables ECN on ToR downlinks**, flooding mice flows with spurious CE marks and inflating FCTs. The leaf exception requires `force_disable_tor_ecn = true`, which is set only by `-disable_tor_ecn`.

**Rule:** any command that includes `-sender_cc_only` MUST also include `-disable_tor_ecn`.

How to detect the bug in output: grep for `enable on tor downlink 1` in the simulator stdout. If you see it, you forgot the flag.

---

## Experiment history and findings

### exp01 — LB dynamics under REPS (`-load_balancing_algo reps`)

- **Raw outputs lost** between sessions. Findings preserved in `exp01_lb_dynamics_reps_v1/README.md`.
- The active EV set is `_next_pathid` (unbounded). Δ at ECN is consistently −0.5 to −1.0. `corr(recycle, ECN) ≈ 0` — the `recycle` counter is not predictive.
- Triggered the switch to `freezing` (paper-REPS) for exp02.

### exp02 — LB dynamics under FREEZING (`-load_balancing_algo freezing`)

- **Raw outputs lost** between sessions. Findings preserved in `exp02_lb_dynamics_freezing_v2/README.md`.
- **Key finding**: `fresh = 0 ⇒ P(next ACK is ECN-marked) ≈ 1.0` in every workload tested. The bounded 8-slot buffer's emptiness is a near-deterministic signal of imminent congestion.
- `corr(fresh, ECN) ≈ −0.21 to −0.24`. Mean fresh at ECN events is 30-60% lower than baseline.
- This motivated the v4 future idea: gate CC on `fresh ≤ 1` instead of (or in addition to) the asymmetric flag.

### exp03 — Matrix sweep (primary result, full artifacts preserved)

- **4 workloads × 5 failure severities × 2 modes × 5 seeds = 200 cells.**
- **Full artifacts**: 16 plots, 2 CSVs (~44k flow rows, 200 event rows), 3 scripts, `runs.tar.gz`.
- All in `state_aware_experiments/exp03_matrix_sweep_v3/`.

**Headline**: once `-disable_tor_ecn` is correctly in place, state-aware mode's FCT impact on synthetic workloads is **small**. Strongest signal: incast p99 improves ~14 μs in healthy composite. The architecture wires correctly (SA flag flips exactly equal FREEZING entries; zero false positives in 40 healthy-state runs), but the FCT win is narrow.

**Event-count validation** (state-aware wiring correctness check):
- `SA asymmetric-flag flips == SA FREEZING_starts` at every single cell.
- Both equal 0 at sev=0 across all 40 healthy-state runs.

---

## Future directions (not implemented)

1. **v4 buffer-fill gate**: change CC ECN-masking from `cc_ecn = ecn && asymmetric` to `cc_ecn = ecn && (asymmetric || fresh ≤ 1)`. One-line change at `uec.cpp:~1209`. Justified by exp02's `fresh=0 ⇒ P(ECN)≈1.0` finding.
2. **Long-failure stress**: all experiments use a 150 μs failure window (50→200 μs). A 1-10 ms window would exercise the freeze-expiry / auto-thaw path, which is currently never reached.
3. **Real-CDF workloads**: Datamining/Hadoop/Websearch CDFs (used in the paper) instead of synthetic permutations.
4. **Topology sweep**: extend exp03 to k=8 2-tier and 1024-host 3-tier topologies.
5. **EV-lifetime sweep**: implement the buffer-cache idea via `-reps_lifetime N` and re-run exp02-style instrumentation. The mechanism already exists (`repsMaxLifetimeEntropy`) but is gated off. See project memory `reps_buffer_cache_idea.md`.

---

## How to run a new experiment

The full recipe is in `state_aware_experiments/RUNNING_EXPERIMENTS.md`. Short version:

1. Create `state_aware_experiments/expNN_short_name/` with subdirs `plots/`, `data/`, `scripts/`.
2. Write a bash driver that iterates the design matrix, is idempotent, and always passes `-disable_tor_ecn`.
3. Write a Python aggregator that outputs a tidy CSV (columns: `workload`, `mode`, `sev`, `seed`, `flow_id`, `fct_us`, `size`, `flow_class`).
4. Write a Python plotter that emits PNGs to `plots/` with 95% CI error bars (t-distribution, not naive ±SE).
5. Compress runs: `tar -czf expNN/runs.tar.gz -C expNN/runs . && rm -rf expNN/runs/`.
6. Write `README.md` with required sections; use relative image paths (`plots/foo.png`, never `/tmp/`).
7. Add a row to `state_aware_experiments/README.md` lineage table.
8. Run the quick checklist from `RUNNING_EXPERIMENTS.md § 11`.

---

## Common pitfalls

| Pitfall | Symptom | Fix |
|---|---|---|
| Forgot `-disable_tor_ecn` | Mice FCT inflated; `enable on tor downlink 1` in stdout | Add the flag; re-run |
| `df.mode` in pandas | Returns dtype, not the column | Use `df["mode"]` |
| Hardcoded `/tmp/` paths in scripts | Works locally, breaks on re-run | Resolve from `__file__` / `${BASH_SOURCE[0]}` |
| Forgot `-sender_cc_algo nscc` | Mysteriously slow flows | Default sender CC isn't NSCC |
| Used `-load_balancing_algo reps` for state-aware | `fresh` column stuck at 0 | Use `freezing` (= paper-REPS) |
| Single seed, claiming a trend | Differences vanish on rerun | Sweep ≥ 3–5 seeds, plot 95% CI |
| Committed raw `runs/` dir | Repo bloat (200+ files, 45 MB) | Compress to `runs.tar.gz` first |
| Modifying `artifact_scripts/` or `artifact_results/` | Corrupts the paper's original artifact | Leave those directories alone |

---

## Project memory

Long-term design hypotheses are saved under:
```
/root/.claude/projects/-home-itamar-WSL-Clones-REPS-EuroSys-Artifact/memory/
```

Current entries (see `MEMORY.md` in that directory):
- `reps_buffer_cache_idea.md` — hypothesis that REPS' bounded buffer should cache known-good EVs (lifetime > 1) across draws, rather than invalidating per use. The `repsMaxLifetimeEntropy` mechanism already exists in the code but is gated off.

If an experiment reveals a new design hypothesis worth keeping across sessions, save it there with the standard frontmatter (`name`, `description`, `metadata.type`), add a line to `MEMORY.md`, and link to it from the experiment's README.

---

## What has NOT been changed

- No original lines deleted from `htsim/sim/`. Every modification is an addition or a wrap.
- `artifact_scripts/` and `artifact_results/` are untouched (paper's original artifact).
- With all new flags absent, the binary produces byte-identical behavior to vanilla NSCC + REPS/FREEZING.

---

## Modifications inventory

Every addition to `htsim/sim/` is tagged `[ADDED: <name>]` in code comments and below.
**Rule for future additions:** every new mechanism MUST have (i) an `// ===== ADDED (<name>) =====`
banner at every modification site, (ii) a row in this table, (iii) an ARCHITECTURE doc under
`state_aware_experiments/`. This table is the single source of truth for the original-vs-added boundary.

### `[ORIGINAL]` — paper artifact, untouched

All of `htsim/sim/` except the sections listed below. `artifact_scripts/` and `artifact_results/`
are fully untouched.

### `[ADDED: state-aware]` — gated by `-state_aware_ecn`

Architecture doc: [`state_aware_experiments/ARCHITECTURE.md`](state_aware_experiments/ARCHITECTURE.md)

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `_state_aware_ecn_enabled` static, `_network_is_asymmetric` per-source flag + setters | `-state_aware_ecn` |
| `htsim/sim/uec.cpp` | CC ECN-masking gate (~L1209); freeze/unfreeze flag hooks for REPS (~L3022, ~L2310) and FREEZING (~L3040, ~L2653); REPS-buffer CSV instrumentation | `-state_aware_ecn` |
| `htsim/sim/pipe.h/.cpp` | `Pipe::_failed` flag + early-drop in `receivePacket` | `Pipe::setFailed()` call |
| `htsim/sim/datacenter/main_uec.cpp` | CLI: `-state_aware_ecn`, `-fail_link_time`, `-fail_link_target`, `-log_reps_state`, `-log_reps_state_src`; `LinkFailureEvent` class | own flags |

### `[ADDED: smart-filter]` — gated by `-smart_filter_mode`

**Mutually exclusive with state-aware and wtd-in-nscc** (binary errors out if any two are set together).
Architecture doc: [`state_aware_experiments/exp06_smart_filter_v6/ARCHITECTURE.md`](state_aware_experiments/exp06_smart_filter_v6/ARCHITECTURE.md)

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `SmartFilterMode`/`SmartFilterCounter` enums, three statics, `_ecn_buffer_counter`/`_sf_md_gain` per-source fields, `smartFilterCounter()`/`smartFilterEcnThresh()` accessors | `-smart_filter_mode` |
| `htsim/sim/uec.cpp` | Static defs; accessor bodies; counter update + gain scratch in `processAck()` (~L1185); `else if` branch in ECN gate (~L1225); Mode A gain + Mode B delay blend in `multiplicative_decrease()` (~L1428); 9 extra CSV columns in `fprintf` (~L1238) | `-smart_filter_mode` |
| `htsim/sim/datacenter/main_uec.cpp` | CLI: `-smart_filter_mode`, `-smart_filter_counter`, `-smart_filter_ecn_thresh`; 3-way coexistence guard; CSV header update | own flags |

### `[ADDED: wtd-in-nscc]` — gated by `-wtd_in_nscc`

**Mutually exclusive with state-aware and smart-filter** (3-way coexistence guard in main_uec.cpp).
Paper reference: SMaRTT-REPS §3.6.1. Reuses `_exp_avg_ecn` (α=0.125, already computed every ACK).
Gate: if `_nscc_wtd_enabled && _exp_avg_ecn < _wtd_threshold (0.25)`, skip MD entirely.
The `_exp_avg_ecn = 1.0` reset on RTO (uec.cpp ~L2093) is preserved so WTD doesn't block MD after a timeout.

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `_nscc_wtd_enabled` (bool, false) and `_wtd_threshold` (double, 0.25) statics | `-wtd_in_nscc` |
| `htsim/sim/uec.cpp` | Static defs; WTD gate in `updateCwndOnAck_NSCC()` MD dispatch (~L1611); 2 extra CSV columns (`wtd_enabled`, `wtd_can_decrease`) in `fprintf` | `-wtd_in_nscc` |
| `htsim/sim/datacenter/main_uec.cpp` | CLI: `-wtd_in_nscc`; 3-way coexistence guard; CSV header update (+2 columns) | own flag |

### `[ADDED: ev-health-counter]` — activated by `-smart_filter_counter evhealth`

Extension of the smart-filter mechanism. Replaces the broken `fresh_inv` counter with a per-EV ECN-state tracker: counts how many EVs currently in the REPS buffer had their last ACK ECN-marked. This is the true outlier-EV signal — it is near 0 at full bisection (diffuse congestion) and rises when specific EVs are persistently congested (low-load spatial collision regime). Uses `CircularBufferREPS::getValidEntropies()` accessor (O(B²) = O(64) per ACK, acceptable). Counter stored in existing `_ecn_buffer_counter` field; `sf_counter_used=2` in CSV. Compatible with both Mode A and Mode B filter modes.

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/buffer_reps.h` | `getValidEntropies()` declaration; added `#include <vector>` | always compiled |
| `htsim/sim/buffer_reps.cpp` | `getValidEntropies()` implementation (returns valid buffer contents as `std::vector<T>`) | always compiled |
| `htsim/sim/uec.h` | `SF_COUNTER_EVHEALTH = 2` in `SmartFilterCounter` enum; `_ev_last_ecn_state` per-source `vector<uint8_t>` | `-smart_filter_counter evhealth` |
| `htsim/sim/uec.cpp` | Lazy-init of `_ev_last_ecn_state`; EV-health update block in `processAck()` smart-filter section; updated `smartFilterCounter()` comment | `-smart_filter_counter evhealth` |
| `htsim/sim/datacenter/main_uec.cpp` | `evhealth` parsed in `-smart_filter_counter` handler | own value |

### `[ADDED: swift-cc]` — gated by `-sender_cc_algo {swift,lswift,mswift,mnscc}`

New CCA implementations for paper reproduction (arXiv:2509.07907v2).  No existing code paths
are modified; new cases are added to the dispatch table only.
Architecture + results: [`state_aware_experiments/exp12_paper_repro_reps/README.md`](state_aware_experiments/exp12_paper_repro_reps/README.md)

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/delay_median_buffer.h` | New file. `DelayMedianBuffer` class: MAX_H=32 circular ring, `push(delay)`, `percentile(p)`, `setCapacity(H)`. Shared by MSwift and MNSCC. | always compiled |
| `htsim/sim/uec.h` | `SWIFT`, `LSWIFT`, `MSWIFT`, `MNSCC` appended to `Sender_CC` enum; statics `_swift_ai`, `_swift_beta`, `_swift_max_mdf`, `_lswift_dup_threshold`, `_swift_median_pct`; per-source fields `_swift_rtt`, `_swift_last_decrease`, `_swift_consec_high_d`, `_swift_consec_round_start`, `_median_delay_buf`; method declarations. | `-sender_cc_algo swift/lswift/mswift/mnscc` |
| `htsim/sim/uec.cpp` | Static defs; dispatch table entries (4 cases); `updateCwndOnAck_Swift`, `_updateCwndOnAck_LSwift_core` (RTT-round-based threshold), `updateCwndOnAck_LSwift`, `updateCwndOnAck_MSwift`, `updateCwndOnNack_Swift`, `_updateCwndOnAck_NSCC_core` (extracted helper), `updateCwndOnAck_MNSCC` | own algo flags |
| `htsim/sim/datacenter/main_uec.cpp` | CLI: `-sender_cc_algo {swift,lswift,mswift,mnscc}`, `-swift_beta`, `-swift_max_mdf`, `-swift_ai`, `-swift_median_pct`, `-lswift_dup_threshold` | own algo flags |

### `[ADDED: min-rto-flag]` — gated by `-min_rto <us>`

Single-flag override for the RTO floor (`UecSrc::_min_rto`). htsim auto-computes RTO from
`network_max_unloaded_rtt + queue_drain_time` (~7-15 µs at typical params). Paper 1 §4.1
specifies RTO = 70 µs explicitly. The flag is parsed early (~L285) and applied AFTER the
auto-compute at ~L1018 so the user value wins. Used by exp13 paper-1 runs.
Architecture + results: [`state_aware_experiments/exp13_papers_reps_repro/README.md`](state_aware_experiments/exp13_papers_reps_repro/README.md)

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/datacenter/main_uec.cpp` | `min_rto_us_override` local (~L170); CLI flag `-min_rto` parser (~L285); override apply (~L1024) | `-min_rto` |

### `[ADDED: swift-md-counter]` — always compiled, no gate

Per-source `uint64_t _swift_md_fires` counter incremented inside the Swift per-ACK MD branch
(`uec.cpp:~L1733`) and the LSwift counter-driven MD branch (`uec.cpp:~L1787`). Logged at flow
finish as a new `swift_md_fires N` column. Diagnostic-only — no behaviour change. Used in Phase D
of exp13 to verify that the `-target_q_delay` flag actually takes effect.

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `_swift_md_fires` per-source field (~L613) | always |
| `htsim/sim/uec.cpp` | 2 increment lines at MD branches (~L1733, ~L1787); new log column (~L1055) | always |

### `[ADDED: per-host-lb]` — gated by `-host_lb_overrides "host:algo,host:algo,..."`

Per-host LB algorithm override. Each `UecSrc` whose `_srcaddr` is in the map runs the named
algorithm (e.g. `ecmp`, `oblivious`, `freezing`) regardless of the global `-load_balancing_algo`.
Implemented by extracting the constructor's LB dispatch into `_dispatchLB(LoadBalancing_Algo)`
and calling `applyHostLBOverride()` after `setSrc()`. Verified by overriding all 128 hosts to ECMP
under a `freezing` global producing output bit-identical to global `-load_balancing_algo ecmp`.
Caveat: runtime checks of `_load_balancing_algo == X` (e.g. `uec.cpp:1391`) still see the global
value; only the LB function pointers and per-algo init are overridden.
Used in Phase D.9 of exp13 to test paper Fig 4 OPS-column setup (elephants:ECMP + sprayed:OPS).
Architecture + results: [`state_aware_experiments/exp13_papers_reps_repro/RESULTS_DIAGNOSTIC.md`](state_aware_experiments/exp13_papers_reps_repro/RESULTS_DIAGNOSTIC.md)

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `_per_host_lb_override` static map (~L385); `_parseLBName`/`_parseHostLBString` (~L387); `applyHostLBOverride()` (~L181); `_dispatchLB` private (~L677) | `-host_lb_overrides` |
| `htsim/sim/uec.cpp` | Static defs + parsers + `applyHostLBOverride` (~L125); `_dispatchLB` helper (~L185); constructor calls `_dispatchLB(_load_balancing_algo)` (~L635) | always compiled |
| `htsim/sim/datacenter/main_uec.cpp` | CLI flag `-host_lb_overrides` parser (~L290); `applyHostLBOverride()` call after `setSrc()` (~L1233) | `-host_lb_overrides` |

### `[FIX: target-qdelay-respect-cli]` — applied 2026-05-30

`UecSrc::initNsccParams()` at [`htsim/sim/uec.cpp:195`](htsim/sim/uec.cpp) unconditionally
overwrote `_target_Qdelay = 6 µs` AFTER CLI parsing, silently rejecting every `-target_q_delay X`
flag passed to the binary. This made all of exp12 and the initial exp13 Paper 2 runs use a 6 µs
target instead of the paper-requested 1 µs, masking LSwift/MSwift differentiation and producing
the misdiagnosed "L2 limitation". Fix: comment out the L195 reset (the L79 static default
preserves 6 µs as the no-flag fallback). Affects all NSCC/Swift-family CCs.

| File | Lines / what | Effect |
|------|-------------|--------|
| `htsim/sim/uec.cpp` | L195 reset line disabled with banner `// ===== FIX (target-qdelay-respect-cli) =====` | `-target_q_delay X` now actually takes effect |

### `[FIX: median-buf-paper-faithful]` — applied 2026-06-01

`DelayMedianBuffer` (used by MSwift + MNSCC) had two deviations from Paper 2
(arXiv:2509.07907v2) §III.B + Eqs (8-9):

1. **`MAX_H = 32`** silently clamped MSwift's window when Eq (8) `H = max(W/2, 1)`
   exceeded 32 (BDP cwnd ≈ 120 pkts → paper H = 60). Raised to 128; sort cost
   per ACK grows from ~160 to ~640 comparisons — still negligible.
2. **`setCapacity` flushed the buffer on shrink**, discarding all history right
   after MD-driven cwnd drops. Paper has no flush rule. Now keeps the most-recent
   `newCap` samples (the ring buffer already organises them tail-aligned, so
   only `_count` is truncated).

Both changes are mechanical paper-fidelity items, not algorithmic. Effect on
Paper 2 Fig 4 MSwift: 71 % → 75 % (small in this regime). MNSCC unaffected
because its own H-cap of 4 is tighter than MAX_H.

| File | Lines / what | Effect |
|------|-------------|--------|
| `htsim/sim/delay_median_buffer.h` | `MAX_H = 32 → 128`; `setCapacity` truncates `_count` instead of flushing; banner `// ===== FIX (median-buf-paper-faithful) =====` | MSwift's H now follows paper Eq (8) up to W ≈ 240; median window survives MD-induced cwnd drops |

### `[ADDED: swift-sack-hole-md]` — gated by `_sender_cc_algo == SWIFT`, always compiled

Paper 2 (CC4Spraying, arXiv:2509.07907v2) §IV.B explicitly states the Swift CCA collapses under
packet spraying because it MDs on SACK holes from out-of-order arrivals. Their footnote says
they had to correct htsim's Swift to match this. This patch implements the same correction:
inside `UecSrc::processAck()`, immediately after the per-ACK CCA dispatch, when the active CCA
is `SWIFT` and the receiver-attached out-of-order count `pkt.ooo() > 0`, apply Swift's
reordering-sensitive MD (`_cwnd *= 1 - _swift_max_mdf` with the standard per-RTT cooldown via
`_swift_last_decrease` / `_swift_rtt`). LSWIFT/MSWIFT (which are the paper's *reordering-resilient*
variants by definition) and NSCC/MNSCC are gated out and unchanged. With this fix, Paper 2 Fig 4
Swift CCT inflation jumps from 355 % to ~1577 % (paper 1308 %, within 20 %).

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.cpp` | New block in `processAck()` after the CCA dispatch (~L1444); banner `// ===== ADDED (swift-sack-hole-md) =====` | `_sender_cc_algo == SWIFT && ooo > 0` |

### `[ADDED: path-rr]` — gated by `-load_balancing_algo path_rr`

True round-robin over distinct physical paths using **full source routing** — bypasses per-hop
ECMP entirely.  At flow setup, `get_bidir_paths(src, dst)` enumerates all distinct end-to-end
`Route*` objects and stores them in `UecSrc::_paths`.  Each packet is created with the next
route in the cycle as its explicit route (not just an entropy value).  Switches never run their
ECMP hash on these packets.  `processEv_path_rr` is a no-op (pure RR, no feedback).
Architecture doc: [`state_aware_experiments/PATH_RR_ARCHITECTURE.md`](state_aware_experiments/PATH_RR_ARCHITECTURE.md)

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `PATH_RR` appended to `LoadBalancing_Algo` enum; `_path_rr_idx` per-source field; `setPaths()` / `setPathRRStartIdx()` methods; `nextEntropy_path_rr` / `processEv_path_rr` declarations; `PathRRStartMode` enum + static | `-load_balancing_algo path_rr` |
| `htsim/sim/uec.cpp` | `_parseLBName` entry; `_dispatchLB` case; `processEv_path_rr` (no-op); `nextEntropy_path_rr` (advances `_path_rr_idx`); `effective_route` override in `sendNewPacket` and `sendRtxPacket`; `_path_rr_start_mode` static def | `-load_balancing_algo path_rr` |
| `htsim/sim/datacenter/main_uec.cpp` | CLI: `path_rr` parsed in `-load_balancing_algo` handler; `-path_rr_start_mode {zero\|src_mod\|dst_mod\|srcdst_hash\|src_mod2}`; `get_bidir_paths` + `setPaths` + `setPathRRStartIdx` call per flow after `connectPort` | `-load_balancing_algo path_rr` |

### `[ADDED: path-rr-npaths]` — gated by `-path_rr_npaths_override "host:N,..."`

Per-host cap on the number of PATH_RR paths. After `get_bidir_paths` builds `full_paths`,
truncates the vector to at most N entries for any host in the override map. Purely a
`main_uec.cpp` change — no uec.h/uec.cpp modifications. Used in exp19 to simulate one
host having access to only 3 of 4 physical paths (fabric failure / misconfigured routing).
Results: [`state_aware_experiments/exp19_path_rr_asymmetry_v19/README.md`](state_aware_experiments/exp19_path_rr_asymmetry_v19/README.md)

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/datacenter/main_uec.cpp` | `path_rr_npaths_override` local map (~L214); CLI flag `-path_rr_npaths_override` parser (~L371); truncate `full_paths` before `setPaths` in PATH_RR setup block | `-path_rr_npaths_override` |

### `[ADDED: path-rr-startslot]` — extends `-path_rr_start_mode`

Adds a fifth start-slot mode `src_mod2`: each flow's RR start index is `(src × 2) % np`. With
`np=4` this yields slots [0,2,0,2,...] — 2 distinct slots vs 4 for `src_mod`. Tested in exp18
alongside the existing `zero` and `src_mod` modes against PATH_STATIC reference.
Results: [`state_aware_experiments/exp18_path_rr_startslot_v18/README.md`](state_aware_experiments/exp18_path_rr_startslot_v18/README.md)

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `PATH_RR_START_SRC2` appended to `PathRRStartMode` enum | `-path_rr_start_mode src_mod2` |
| `htsim/sim/datacenter/main_uec.cpp` | `src_mod2` branch in `-path_rr_start_mode` parser; `PATH_RR_START_SRC2` case in `setPathRRStartIdx` switch: `start_idx = (src * 2) % np` | `-path_rr_start_mode src_mod2` |

### `[ADDED: path-random]` — gated by `-load_balancing_algo path_random`

Per-packet uniform-random path selection using the same source-routing infrastructure as PATH_RR.
Reuses `UecSrc::_paths[]` populated by `get_bidir_paths` at flow setup.  On every packet,
`rand() % _paths.size()` is stored into `_path_rr_idx` (scratch register) before the route is
selected, so route and pathid are consistent.  `processEv_path_random` is a no-op.
Results: [`state_aware_experiments/exp16_path_random_v16/README.md`](state_aware_experiments/exp16_path_random_v16/README.md)

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `PATH_RANDOM` appended to `LoadBalancing_Algo` enum; `nextEntropy_path_random` / `processEv_path_random` declarations | `-load_balancing_algo path_random` |
| `htsim/sim/uec.cpp` | `_parseLBName` entry; `_dispatchLB` case; `processEv_path_random` (no-op); `nextEntropy_path_random` (returns scratch `_path_rr_idx`); `rand()` roll in `sendNewPacket` and `sendRtxPacket`; `effective_route` guard extended to cover `PATH_RANDOM` | `-load_balancing_algo path_random` |
| `htsim/sim/datacenter/main_uec.cpp` | CLI: `path_random` parsed in `-load_balancing_algo` handler; path-population condition extended to `PATH_RR || PATH_RANDOM` | `-load_balancing_algo path_random` |

### `[ADDED: path-static]` — gated by `-load_balancing_algo path_static`

Each flow is pinned to a single fixed path for its entire lifetime. Path is chosen at flow-setup
time by a **greedy edge-load algorithm**: for each new flow, pick the path whose
maximum-loaded edge (`PacketSink*`) has the minimum current load, then increment load counts
for all edges on the chosen path. `Route*` objects reuse the same `Queue*`/`Pipe*` pointers for
shared physical links, so tracking `PacketSink*` identity correctly identifies shared links
without any topology-specific knowledge. For balanced workloads like tornado, all 16 flows are
assigned with `max_edge_load=0` — truly no shared data-path edges.

**Reverse-path routing for ACK/PULL:** The NIC sends control packets (PULLs, ACKs, NACKs) by
calling `sink->getPortRoute(port)`, which by default returns only the first hop (dst→ToR) and
relies on ECMP for the rest. In bidirectional tornado, ECMP hash collisions on the return path
caused a bimodal FCT distribution (~80 µs gap). The fix: after the greedy selects `best`, build
`rev = new Route(*orig_r->reverse(), *uec_src->getPort(p))` and call
`uec_snk->getPort(p)->setRoute(*rev)`, overriding the sink port's route with the full source-routed
reverse path. All 16 flows now finish at identical times (zero FCT spread), and PATH_STATIC achieves
`1.0334×` avg/max slowdown — best of all five algorithms tested.
Results: [`state_aware_experiments/exp17_cwnd_corrected_v17/`](state_aware_experiments/exp17_cwnd_corrected_v17/)

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `PATH_STATIC` appended to `LoadBalancing_Algo` enum; `nextEntropy_path_static` / `processEv_path_static` declarations | `-load_balancing_algo path_static` |
| `htsim/sim/uec.cpp` | `_parseLBName` entry; `_dispatchLB` case; `processEv_path_static` (no-op); `nextEntropy_path_static` (`_path_rr_idx % 1` → always 0); `effective_route` guard extended to cover `PATH_STATIC` | `-load_balancing_algo path_static` |
| `htsim/sim/datacenter/main_uec.cpp` | CLI: `path_static` parsed; `path_static_edge_load` map; greedy selection; `get_bidir_paths` called with `reverse=true`; reverse route built and registered via `uec_snk->getPort(p)->setRoute(*rev)`; cross-linked with `set_reverse` for trim safety | `-load_balancing_algo path_static` |

### `[ADDED: srv6]` — gated by `-use_srv6`

SRv6 source routing substrate: orthogonal to the LB algorithm. When `-use_srv6` is passed, the
sender converts the EV chosen by whatever LB algorithm is active into a physical-path index
(`ev % _paths.size()`) and uses the corresponding pre-computed `Route*` from `_paths[]` instead
of relying on per-hop ECMP hashing. Switches simply follow the explicit hop list.

**EV-to-path mapping faithfulness**: for the 3-tier K=4 fat tree, `get_bidir_paths` enumerates
inter-pod paths in Agg-major, Core-minor order. `ev % 4` maps EV bit[0]=Core choice (= paper
"plane") and bit[1]=Agg choice (= paper "T0 uplink") — exactly the SRv6 uSID bit decomposition
described in MRC §2.3 (Fig. 3).

**Timing constraint**: `effective_route` must be determined before `newpkt()` locks the route,
but `nextEntropy()` is normally called after packet creation. Solution: SRv6 pre-draw block calls
`nextEntropy()` early in `sendNewPacket`/`sendRtxPacket`, stores the EV in `_srv6_pending_ev`,
and sets `route_path_idx`. The original `nextEntropy()` dispatch is then replaced by returning
the cached value — the LB state machine advances exactly once per packet.

Can be combined with any existing LB algorithm: `-load_balancing_algo freezing -use_srv6`,
`-load_balancing_algo ecmp -use_srv6`, etc.

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `_use_srv6` static bool; `_srv6_pending_ev` per-source scratch field | `-use_srv6` |
| `htsim/sim/uec.cpp` | static def; SRv6 pre-draw block + `route_path_idx` local + `effective_route` condition extended + `nextEntropy` guard in `sendNewPacket` and `sendRtxPacket` | `-use_srv6` |
| `htsim/sim/datacenter/main_uec.cpp` | CLI `-use_srv6`; path-population condition extended to include `_use_srv6` | `-use_srv6` |

**Verification tests**: `state_aware_experiments/test_srv6/scripts/run_tests.sh` — 13/13 pass.
Tests verify: (1) FREEZING+SRv6 smoke, (2) PATH_RR FCT identical with/without SRv6 (within 0.1%),
(3) 1-path SRv6 stalls when path[0]=(agg=0,core=0) is failed, (4) 1-path SRv6 unaffected when
other links fail, (5) 4-path SRv6 shows ≥3× FCT degradation when each path's (agg,core) link fails,
(6) ECMP+SRv6 completes tornado workload.

### `[ADDED: freezing-pxr]` — gated by `-load_balancing_algo freezing_pxr`

Path-eXcluding REPS. On RTO, adds the triggering EV (captured from `sendRecord::sent_ev`) to a
per-source **excluded set** and refreshes a sliding deadline (`now + _pxr_window`). Normal REPS
sampling continues but skips excluded EVs on every draw. When the deadline elapses with no new
RTO, the entire excluded set is cleared atomically. Never enters frozen mode.

Unlike FREEZING, there is no frozen-mode cycling of stale buffer entries. The sender simply keeps
drawing from the remaining healthy EVs, giving ~31% P99 FCT improvement over FREEZING B=8 under
51 failed links (exp23).

`sendRecord` was extended to store `sent_ev` so the RTO handler can identify which EV caused
the timeout. `createSendRecord` updated to accept and forward `ev` at all 3 call sites.

Experiment + results: [`state_aware_experiments/exp23_freezing_pxr_v23/README.md`](state_aware_experiments/exp23_freezing_pxr_v23/README.md)

| File | Lines / what | Gate |
|------|-------------|------|
| `htsim/sim/uec.h` | `FREEZING_PXR` in `LoadBalancing_Algo` enum; `_pxr_excluded_evs` + `_pxr_clear_deadline` per-source fields; `_pxr_window` public static; `nextEntropy_freezing_pxr` / `processEv_freezing_pxr` declarations; `sent_ev` added to `sendRecord`; `createSendRecord` declaration updated | `-load_balancing_algo freezing_pxr` |
| `htsim/sim/uec.cpp` | `_pxr_window` static def (200 ms default); `_parseLBName` entry; `_dispatchLB` case; `nextEntropy_freezing_pxr` (timer check + saturation guard + filtered REPS draw); `processEv_freezing_pxr` (filtered buffer add); RTO branch (exclusion + sliding deadline); `createSendRecord` stores `ev`; `rto_trigger_ev` captured before erase; `pxr_excluded_count` + `pxr_excluded_evs` CSV columns | `-load_balancing_algo freezing_pxr` |
| `htsim/sim/datacenter/main_uec.cpp` | `freezing_pxr` in `-load_balancing_algo` handler; `-pxr_window_us <N>` flag; CSV header update | own flags |
