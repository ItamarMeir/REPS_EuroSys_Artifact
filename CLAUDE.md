# CLAUDE.md — Project guide for Claude Code agents

> **Maintainer note:** `CLAUDE.original.md` is uncompressed source of truth. Edit that
> file, not this one — this file regenerated from it via `/caveman-compress`.

First-read doc for any Claude Code session in this repo. What built, where things live, what gotchas are. No rediscover from scratch.

---

## What this repo is

**REPS EuroSys artifact** — research simulator plus analysis code for paper "REPS: Recycled Entropy Packet Spraying for Adaptive Load Balancing and Failure Mitigation". Simulator is `htsim`, extended with REPS.

On top of paper artifact we built several independent extensions, all gated behind CLI flags, all live in `htsim/sim/`:
1. **State-aware NSCC + REPS** (`-state_aware_ecn`) — binary ECN gate driven by REPS freeze/unfreeze events + dynamic link-failure machinery. Experiments: exp01–03.
2. **Smart filter** (`-smart_filter_mode`) — continuous, evidence-based dampening of NSCC's MD step using REPS buffer saturation. Mutually exclusive with state-aware. Experiments: exp06.
3. **WTD in NSCC** (`-wtd_in_nscc`) — paper's "Wait to Decrease" (SMaRTT-REPS §3.6.1), gates MD on `_exp_avg_ecn ≥ 0.25`. Mutually exclusive with state-aware and smart-filter. Experiments: exp07 (complete; null result — see exp07 README §Results).
4. **PATH_RR** (`-load_balancing_algo path_rr`) — true round-robin over distinct physical paths using full source routing; bypasses per-hop ECMP. Clean baseline vs entropy-spray algorithms.

Experiments for both live in `state_aware_experiments/`.

---

## Base artifact: setup, build, run, test

**Build/run `htsim_uec` via Docker (see Docker section), not host or WSL directly.** Hard
requirement, not preference: cross-filesystem WSL builds (`/mnt/c/...`) hit clock-skew
warnings/incomplete builds; host-built binaries can fail inside a container with
`GLIBCXX_*`/`GLIBC_*` errors if bind-mounted. Docker = one toolchain/filesystem every time.

Python env (from repo root, clean venv):
```bash
python3 -m venv .venv
source .venv/bin/activate
./reps_pkg_install.sh
```

Full clean rebuild of `htsim` (same as `## Building` below, but from clean):
```bash
cd htsim/sim
make clean && cd datacenter/ && make clean && cd ..
make -j 8 && cd datacenter/ && make -j 8 && cd ..
```

Reproduce paper figures (from `artifact_scripts/`, run after building `htsim_uec`):
```bash
cd artifact_scripts
./reps_quick.sh    # <2h, Figures 1,3,5,6,8,9,10,11,12,13,14
./reps_medium.sh   # ~4-6h, adds Figure 2
./reps_full.sh     # ~10h+, all figures
```
Or run single figure's Python script direct (e.g. `python fig_1_symmetric_micro.py`). Results land in `artifact_results/<experiment>/`. **Never modify `artifact_scripts/` or `artifact_results/`** — paper's original, unmodified artifact.

`traffic_gen/` unit tests (connection-matrix generator, independent of `htsim`):
```bash
cd traffic_gen
python -m unittest test_traffic_gen_utils.py
python -m unittest test_custom_random_number_generator.py
```

No test suite for `htsim/sim/` itself or `state_aware_experiments/` — correctness validated by running experiments and inspecting output (grep for `enable on tor downlink 1`, event-count sanity checks, etc. — see `state_aware_experiments/RUNNING_EXPERIMENTS.md`).

---

## Docker environment

**Required for `htsim_uec` build/run**, not just dirty-host fallback. `Dockerfile` (repo root)
builds self-contained Ubuntu 22.04 image, C++17 toolchain, `libgraphviz-dev`, Python 3 +
`requirements.txt`, prebuilt `htsim_uec`.

**Gotcha:** `.dockerignore` excludes `**/*.cm` (generated connection-matrix workloads) +
`.o`/`.a`/binaries/`.csv`/`.png`/`.pdf`. Experiment needing a `.cm` not on the image →
`Failed to load connection matrix`. Fix: `docker cp <host-file> <container>:<path>` before
running, or regenerate via `traffic_gen/`.

```bash
docker build -t reps-artifact .
docker run -it --rm reps-artifact                              # self-contained, image's own copy of the repo
docker run -it --rm -v "$(pwd):/workspace" reps-artifact        # live bind-mount for editing from the host
```

**Gotcha:** bind-mount overlays host's `htsim/sim` build artifacts (`.o` files, `htsim_uec`)
on top of image's. If those built on host (different glibc/libstdc++), container
fails to run them with `GLIBCXX_*`/`GLIBC_*` "version not found" error. Always rebuild inside
container after mounting:
```bash
cd htsim/sim && make clean && cd datacenter && make clean && cd .. \
  && make -j$(nproc) && cd datacenter && make -j$(nproc)
```
`.o`/binary files gitignored, so this never touches tracked files. Full instructions: README.md
§"Running in Docker".

### docker-compose

`docker-compose.yml` (repo root) wraps bind-mount workflow above into single service
(`reps-artifact-dev`, image `reps-artifact`, `.` mounted at `/workspace`):
```bash
docker compose build
docker compose run --rm reps-artifact-dev
```
Same rebuild-after-mount gotcha — rebuild `htsim/sim` inside container before running
anything. `docker exec -it reps-artifact-dev bash` opens second shell into already-running
container. Verified end-to-end (build, compose run, in-container rebuild, single-flow sim on
`fat_tree_16_1os_3t_400g.topo`) on 2026-08-13.

---

## Directory map

```text
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

Binary is `htsim/sim/datacenter/htsim_uec`. Build warnings safe to ignore.

---

## The state-aware NSCC + REPS extension

### What it does

Every incoming ACK carries ECN bit. Architecture splits how bit consumed:

- **Load Balancer (REPS or FREEZING)** — always sees real ECN bit. ECN-marked ACKs rotate out EV naturally.
- **Congestion Controller (NSCC)** — sees *gated* ECN bit. CC honors ECN only when sender's internal flag `_network_is_asymmetric` set. Else CC sees ECN=0, holds rate, lets LB handle spatial collisions.

`_network_is_asymmetric` flag set organically when LB enters frozen mode (triggered by RTO, which fires when link failure kills ACKs), cleared when LB exits frozen mode. No control-plane broadcast needed.

### CLI flags added

| Flag | Effect |
|---|---|
| `-state_aware_ecn` | Master toggle (off by default). Enables CC gate + asymmetric-flag wiring. Forces `repsUseFreezing = true`. |
| `-disable_tor_ecn` | Enables leaf exception (`force_disable_tor_ecn = true`). **Required whenever `-sender_cc_only` also passed.** |
| `-fail_link_time <fail_us> <recover_us>` | Schedules dynamic Agg↔Core pipe failure and recovery. |
| `-fail_link_target <agg> <core>` | Repeatable. Selects which Agg↔Core link(s) to fail. |
| `-log_reps_state <file>` + `-log_reps_state_src <id>` | Per-ACK CSV diagnostic log. |
| `-log_reps_events <file>` + `-log_reps_events_src <id>` | Unified send+ACK+freeze event trace (SEND/RTX/RTS/ACK/NACK/FREEZE/UNFREEZE, slot-indexed buffer snapshot per row). Independent file/schema from `-log_reps_state`. See `state_aware_experiments/tools/README.md` for schema + the `reps_event_viewer.py` HTML viewer. |

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

`-load_balancing_algo reps` is code-only simpler variant (unbounded `_next_pathid` list). Kept for archaeology. Buffer instrumentation column to track: `fresh` (FREEZING) vs `recycle` (REPS).

---

## The critical `-disable_tor_ecn` gotcha

**Burned us once, will burn you again if you forget.**

At `main_uec.cpp:739`:
```cpp
bool ecn_on_tor_dl = !receiver_driven && !force_disable_tor_ecn;
```

`-sender_cc_only` sets `receiver_driven = false`. Without `-disable_tor_ecn`, this **re-enables ECN on ToR downlinks**, flooding mice flows with spurious CE marks and inflating FCTs. Leaf exception needs `force_disable_tor_ecn = true`, set only by `-disable_tor_ecn`.

**Rule:** any command with `-sender_cc_only` MUST also include `-disable_tor_ecn`.

Detect bug in output: grep for `enable on tor downlink 1` in simulator stdout. See it, you forgot flag.

---

## Experiment history and findings

### exp01 — LB dynamics under REPS (`-load_balancing_algo reps`)

Raw outputs lost; findings in `exp01_lb_dynamics_reps_v1/README.md`. Unbounded `_next_pathid`
EV set not predictive of ECN (`corr(recycle, ECN) ≈ 0`) → triggered switch to `freezing` for exp02.

### exp02 — LB dynamics under FREEZING (`-load_balancing_algo freezing`)

Raw outputs lost; findings in `exp02_lb_dynamics_freezing_v2/README.md`. Key finding:
`fresh = 0 ⇒ P(next ACK ECN-marked) ≈ 1.0` in every workload — bounded 8-slot buffer emptiness
is near-deterministic congestion signal. Motivated v4 future idea (gate CC on `fresh ≤ 1`).

### exp03 — Matrix sweep (primary result, full artifacts preserved)

- **4 workloads × 5 failure severities × 2 modes × 5 seeds = 200 cells.**
- **Full artifacts**: 16 plots, 2 CSVs (~44k flow rows, 200 event rows), 3 scripts, `runs.tar.gz`.
- All in `state_aware_experiments/exp03_matrix_sweep_v3/`.

**Headline**: once `-disable_tor_ecn` correctly in place, state-aware mode FCT impact on synthetic workloads is **small**. Strongest signal: incast p99 improves ~14 μs in healthy composite. Architecture wires correctly (SA flag flips exactly equal FREEZING entries; zero false positives in 40 healthy-state runs), but FCT win narrow.

**Event-count validation** (state-aware wiring correctness check):
- `SA asymmetric-flag flips == SA FREEZING_starts` at every single cell.
- Both equal 0 at sev=0 across all 40 healthy-state runs.

---

## Future directions (not implemented)

1. **v4 buffer-fill gate**: change CC ECN-masking from `cc_ecn = ecn && asymmetric` to `cc_ecn = ecn && (asymmetric || fresh ≤ 1)`. One-line change at `uec.cpp:~1209`. Justified by exp02's `fresh=0 ⇒ P(ECN)≈1.0` finding.
2. **Long-failure stress**: all experiments use 150 μs failure window (50→200 μs). 1-10 ms window would exercise freeze-expiry / auto-thaw path, currently never reached.
3. **Real-CDF workloads**: Datamining/Hadoop/Websearch CDFs (used in paper) instead of synthetic permutations.
4. **Topology sweep**: extend exp03 to k=8 2-tier and 1024-host 3-tier topologies.
5. **EV-lifetime sweep**: implement buffer-cache idea via `-reps_lifetime N`, re-run exp02-style instrumentation. Mechanism already exists (`repsMaxLifetimeEntropy`) but gated off. See project memory `reps_buffer_cache_idea.md`.

---

## How to run a new experiment

Full recipe in `state_aware_experiments/RUNNING_EXPERIMENTS.md`. Short version:

1. Create `state_aware_experiments/expNN_short_name/` with subdirs `plots/`, `data/`, `scripts/`.
2. Write bash driver that iterates design matrix, is idempotent, always passes `-disable_tor_ecn`.
3. Write Python aggregator that outputs tidy CSV (columns: `workload`, `mode`, `sev`, `seed`, `flow_id`, `fct_us`, `size`, `flow_class`).
4. Write Python plotter emitting PNGs to `plots/` with 95% CI error bars (t-distribution, not naive ±SE).
5. Compress runs: `tar -czf expNN/runs.tar.gz -C expNN/runs . && rm -rf expNN/runs/`.
6. Write `README.md` with required sections; use relative image paths (`plots/foo.png`, never `/tmp/`).
7. Add row to `state_aware_experiments/README.md` lineage table.
8. Run quick checklist from `RUNNING_EXPERIMENTS.md § 11`.

---

## Common pitfalls

| Pitfall | Symptom | Fix |
|---|---|---|
| Forgot `-disable_tor_ecn` | Mice FCT inflated; `enable on tor downlink 1` in stdout | Add flag; re-run |
| `df.mode` in pandas | Returns dtype, not column | Use `df["mode"]` |
| Hardcoded `/tmp/` paths in scripts | Works locally, breaks on re-run | Resolve from `__file__` / `${BASH_SOURCE[0]}` |
| Forgot `-sender_cc_algo nscc` | Mysteriously slow flows | Default sender CC not NSCC |
| Used `-load_balancing_algo reps` for state-aware | `fresh` column stuck at 0 | Use `freezing` (= paper-REPS) |
| Single seed, claiming trend | Differences vanish on rerun | Sweep ≥ 3–5 seeds, plot 95% CI |
| Committed raw `runs/` dir | Repo bloat (200+ files, 45 MB) | Compress to `runs.tar.gz` first |
| Modifying `artifact_scripts/` or `artifact_results/` | Corrupts paper's original artifact | Leave those dirs alone |

---

## Project memory

Long-term design hypotheses saved under:
```text
/root/.claude/projects/-home-itamar-WSL-Clones-REPS-EuroSys-Artifact/memory/
```

Current entries (see `MEMORY.md` in that directory):
- `reps_buffer_cache_idea.md` — hypothesis that REPS' bounded buffer should cache known-good EVs (lifetime > 1) across draws, not invalidate per use. `repsMaxLifetimeEntropy` mechanism already in code but gated off.

Experiment reveals new design hypothesis worth keeping across sessions: save there with standard frontmatter (`name`, `description`, `metadata.type`), add line to `MEMORY.md`, link to it from experiment's README.

---

## What has NOT been changed

- No original lines deleted from `htsim/sim/`. Every modification is addition or wrap.
- `artifact_scripts/` and `artifact_results/` untouched (paper's original artifact).
- With all new flags absent, binary produces byte-identical behavior to vanilla NSCC + REPS/FREEZING.

---

## Modifications inventory

**Repo-wide original-vs-ours map**: [`PROVENANCE.md`](PROVENANCE.md) — top-level dirs/files,
verified against first commit `e19b8d0`. Use for anything outside `htsim/sim/`.

Full detail for `htsim/sim/`: [`state_aware_experiments/MODIFICATIONS.md`](state_aware_experiments/MODIFICATIONS.md)
— source of truth for original-vs-added boundary. Index below.
**Rule for future additions:** every new mechanism MUST have (i) `// ===== ADDED (<name>) =====`
banner at every modification site, (ii) row in MODIFICATIONS.md, (iii) ARCHITECTURE doc under
`state_aware_experiments/`.

`[ORIGINAL]` — all of `htsim/sim/` except rows below; `artifact_scripts/`/`artifact_results/` untouched.

| Name | Gate | One-line |
|---|---|---|
| `state-aware` | `-state_aware_ecn` | CC ECN-mask gate + link-failure machinery |
| `smart-filter` | `-smart_filter_mode` | Continuous NSCC MD dampening from REPS buffer saturation |
| `wtd-in-nscc` | `-wtd_in_nscc` | Gate MD on `_exp_avg_ecn < 0.25` (SMaRTT-REPS §3.6.1) |
| `ev-health-counter` | `-smart_filter_counter evhealth` | Per-EV ECN-state tracker, replaces broken `fresh_inv` |
| `swift-cc` | `-sender_cc_algo swift\|lswift\|mswift\|mnscc` | New CCA implementations (arXiv:2509.07907v2 repro) |
| `min-rto-flag` | `-min_rto <us>` | CLI override for RTO floor |
| `swift-md-counter` | always compiled | Diagnostic `_swift_md_fires` counter, no behavior change |
| `per-host-lb` | `-host_lb_overrides` | Per-host LB algorithm override |
| `target-qdelay-respect-cli` (FIX) | n/a, applied 2026-05-30 | Removed post-CLI reset that silently discarded `-target_q_delay` |
| `median-buf-paper-faithful` (FIX) | n/a, applied 2026-06-01 | `DelayMedianBuffer` H-cap 32→128 + no-flush-on-shrink, paper Eq (8-9) fidelity |
| `swift-sack-hole-md` | `_sender_cc_algo==SWIFT`, always compiled | Swift MDs on SACK holes from OOO (paper 2 §IV.B correction) |
| `path-rr` | `-load_balancing_algo path_rr` | True RR over distinct physical paths via full source routing |
| `path-rr-npaths` | `-path_rr_npaths_override` | Per-host cap on number of PATH_RR paths |
| `path-rr-startslot` | `-path_rr_start_mode src_mod2` | 5th RR start-slot mode |
| `path-random` | `-load_balancing_algo path_random` | Per-packet uniform-random path selection |
| `path-static` | `-load_balancing_algo path_static` | Flow pinned to 1 path (greedy edge-load) + reverse-path routing fix |
| `srv6` | `-use_srv6` | SRv6 source-routing substrate, orthogonal to LB algo |
| `freezing-pxr` | `-load_balancing_algo freezing_pxr` | Path-eXcluding REPS: exclude RTO-triggering EV instead of full freeze |
| `reps-event-trace` | `-log_reps_events` | Unified send+ACK+freeze event trace + interactive HTML buffer viewer (`state_aware_experiments/tools/`) |
