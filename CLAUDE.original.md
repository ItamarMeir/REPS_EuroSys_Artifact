# CLAUDE.original.md — uncompressed source of truth for CLAUDE.md

This is the full, human-readable, uncompressed version of the project guide. **This file is
not auto-loaded as context** (its name doesn't match `CLAUDE.md`). `CLAUDE.md` is the
compressed (`/caveman-compress`) version actually loaded into agent context.

**Workflow for future agents:** when adding/editing project guidance, edit *this* file first,
then regenerate `CLAUDE.md` by running `/caveman-compress CLAUDE.original.md` (or manually
compressing this file's prose into `CLAUDE.md`, preserving all code blocks/tables/paths
exactly). Never hand-edit `CLAUDE.md` directly — edits there get overwritten on the next
regeneration and drift from this source.

---

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

**Build and run `htsim_uec` via Docker (see "Docker environment" below), not directly on the
host or via WSL.** This is a hard requirement, not a soft preference: building on the host and
running the same tree from WSL (or vice versa) hit real failures in practice — cross-filesystem
(`/mnt/c/...`) builds under WSL threw `make: warning: Clock skew detected` /
`File 'X' has modification time N s in the future`, and host-built `.o`/binaries can fail
inside a container with `GLIBCXX_*`/`GLIBC_*` "version not found" if bind-mounted (see Docker
section's gotcha). Docker sidesteps all of this — it's the same toolchain and filesystem every
time, on every OS. The venv/host instructions below remain for reference (e.g. running the
Python figure scripts, which don't have this problem) but `htsim_uec` itself should be built
and invoked through Docker.

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

## Docker environment

**Required for building/running `htsim_uec`** — not just preferred for a dirty host. A
`Dockerfile` (repo root) builds a self-contained Ubuntu 22.04 image with the C++17 toolchain,
`libgraphviz-dev`, Python 3 + `requirements.txt`, and a pre-built `htsim_uec`.

**Gotcha: `.cm`/`.dockerignore`'d files missing from the image.** `.dockerignore` excludes
`**/*.cm` (generated connection-matrix workload files) along with `.o`/`.a`/binaries/`.csv`/
`.png`/`.pdf`. Running an experiment that needs a specific `.cm` file (or other gitignored
generated artifact) not already present on the image may fail with
`Failed to load connection matrix ...`. Fix: `docker cp <host-file> <container>:<path>` into a
running container before invoking `htsim_uec`, or regenerate it in-container via
`traffic_gen/`'s generators. Same applies to topology files if they're gitignored/generated
locally rather than tracked.

```bash
docker build -t reps-artifact .
docker run -it --rm reps-artifact                              # self-contained, image's own copy of the repo
docker run -it --rm -v "$(pwd):/workspace" reps-artifact        # live bind-mount for editing from the host
```

**Gotcha:** bind-mounting overlays the host's `htsim/sim` build artifacts (`.o` files, `htsim_uec`)
on top of the image's. If those were built on the host (different glibc/libstdc++), the container
will fail to run them with a `GLIBCXX_*`/`GLIBC_*` "version not found" error. Always rebuild inside
the container after mounting:
```bash
cd htsim/sim && make clean && cd datacenter && make clean && cd .. \
  && make -j$(nproc) && cd datacenter && make -j$(nproc)
```
`.o`/binary files are gitignored, so this never touches tracked files. Full instructions: README.md
§"Running in Docker".

### docker-compose

`docker-compose.yml` (repo root) wraps the bind-mount workflow above into a single service
(`reps-artifact-dev`, image `reps-artifact`, `.` mounted at `/workspace`):
```bash
docker compose build
docker compose run --rm reps-artifact-dev
```
Same rebuild-after-mount gotcha applies — rebuild `htsim/sim` inside the container before running
anything. `docker exec -it reps-artifact-dev bash` opens a second shell into an already-running
container. Verified end-to-end (build → compose run → in-container rebuild → single-flow sim on
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
| `-log_reps_events <file>` + `-log_reps_events_src <id>` | Unified send+ACK+freeze event trace (SEND/RTX/RTS/ACK/NACK/FREEZE/UNFREEZE, slot-indexed buffer snapshot per row). Independent file and schema from `-log_reps_state`. See `state_aware_experiments/tools/README.md` for the CSV schema and the `reps_event_viewer.py` interactive HTML viewer. |

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

Raw outputs lost; findings in `exp01_lb_dynamics_reps_v1/README.md`. Unbounded `_next_pathid`
EV set not predictive of ECN (`corr(recycle, ECN) ≈ 0`) → triggered switch to `freezing` for exp02.

### exp02 — LB dynamics under FREEZING (`-load_balancing_algo freezing`)

Raw outputs lost; findings in `exp02_lb_dynamics_freezing_v2/README.md`. Key finding:
`fresh = 0 ⇒ P(next ACK ECN-marked) ≈ 1.0` in every workload — bounded 8-slot buffer emptiness
is a near-deterministic congestion signal. Motivated v4 future idea (gate CC on `fresh ≤ 1`).

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
```text
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

**Repo-wide original-vs-ours map**: [`PROVENANCE.md`](PROVENANCE.md) — which top-level
directories/files are the paper's original artifact vs our additions, verified against the
first commit (`e19b8d0`). Use that file for anything outside `htsim/sim/`.

Full detail for `htsim/sim/` itself moved to [`state_aware_experiments/MODIFICATIONS.md`](state_aware_experiments/MODIFICATIONS.md)
— source of truth for original-vs-added boundary in `htsim/sim/`. Index below; consult that
file for exact lines, rationale, and per-entry results.
**Rule for future additions:** every new mechanism MUST have (i) an `// ===== ADDED (<name>) =====`
banner at every modification site, (ii) a row in MODIFICATIONS.md, (iii) an ARCHITECTURE doc under
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
| `reps-event-trace` | `-log_reps_events` | Unified send+ACK+freeze event trace plus an interactive HTML buffer viewer (`state_aware_experiments/tools/`) |
