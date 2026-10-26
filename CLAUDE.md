# CLAUDE.md — Project guide for Claude Code agents

First-read doc for any session in this repo. Task-specific detail lives in nested files and skills (see "Where detail lives").

## What this repo is

The **REPS EuroSys artifact**: research simulator plus analysis code for the paper "REPS: Recycled Entropy Packet Spraying for Adaptive Load Balancing and Failure Mitigation". The simulator is `htsim`, extended with REPS.

On top of the paper artifact we built independent extensions, all gated behind CLI flags and living in `htsim/sim/`: state-aware NSCC + REPS (`-state_aware_ecn`), smart filter (`-smart_filter_mode`), WTD in NSCC (`-wtd_in_nscc`), PATH_RR and other source-routed LB algos, Swift CCs, constant-rate sender, per-link degrade, Ofan, and more. Inventory: `htsim/sim/CLAUDE.md`. Experiments live in `experiments/`.

## Where detail lives

| Need | Where |
|---|---|
| Editing `htsim/sim/` (flags, code locations, modifications inventory, ADDED-banner rule) | `htsim/sim/CLAUDE.md` (auto-loads when you touch those files) |
| Experiment conventions, early findings | `experiments/CLAUDE.md`; lineage table in `experiments/README.md` |
| Creating a new experiment | skill `new-experiment`, recipe in `experiments/RUNNING_EXPERIMENTS.md` |
| Docker gotchas, compose, plain build | skill `build-htsim` |
| Publishing plots to the thesis repo | skill `thesis-sync` (user-invoked only) |
| Original-vs-ours map outside `htsim/sim/` | `PROVENANCE.md` |
| Original-vs-ours inside `htsim/sim/` | `experiments/MODIFICATIONS.md` |

## Build and run: Docker only

**Build and run `htsim_uec` via Docker, never on the host or WSL.** Hard requirement: cross-filesystem WSL builds hit clock-skew errors, and host-built binaries fail in containers with `GLIBCXX_*`/`GLIBC_*` errors. Docker gives the same toolchain on every OS.

```bash
docker build -t reps-artifact .
docker run -it --rm -v "$(pwd):/workspace" reps-artifact   # live bind-mount
```

After mounting, always rebuild inside the container (host `.o` files overlay the image's):
```bash
cd htsim/sim && make clean && cd datacenter && make clean && cd .. \
  && make -j$(nproc) && cd datacenter && make -j$(nproc)
```
Binary: `htsim/sim/datacenter/htsim_uec`. If you hit a segfault that reproduces on untouched baseline code, `GLIBCXX` errors, or `Failed to load connection matrix`, use skill `build-htsim`.

Python figure scripts (no Docker needed):
```bash
python3 -m venv .venv && source .venv/bin/activate && ./reps_pkg_install.sh
cd artifact_scripts
./reps_quick.sh    # <2h, Figures 1,3,5,6,8,9,10,11,12,13,14
./reps_medium.sh   # ~4-6h, adds Figure 2
./reps_full.sh     # ~10h+, all figures
```
Or run one figure script directly (e.g. `python fig_1_symmetric_micro.py`). Results land in `artifact_results/<experiment>/`. **Never modify `artifact_scripts/` or `artifact_results/`** — they are the paper's original artifact.

`traffic_gen/` unit tests: `cd traffic_gen && python -m unittest test_traffic_gen_utils.py test_custom_random_number_generator.py`. No test suite exists for `htsim/sim/` or `experiments/`; correctness is validated by running and inspecting output (see "Validating" below).

## Directory map

```text
REPS_EuroSys_Artifact/
├── htsim/sim/                  ← C++ simulator (build target: datacenter/htsim_uec)
│   ├── uec.h / uec.cpp         ← NSCC + REPS/FREEZING CC + LB logic
│   ├── pipe.h / pipe.cpp       ← link-failure flag
│   └── datacenter/
│       ├── main_uec.cpp        ← CLI entry point (new flags added here)
│       ├── fat_tree_topology.* ← leaf-ECN flag
│       └── connection_matrices/ ← workload TM files
├── experiments/                ← OUR WORK: expNN_* and meeting_* dirs, shared docs (README.md lineage table first)
├── artifact_scripts/           ← paper's original bash runners (don't modify)
├── artifact_results/           ← paper's original results (don't modify)
└── traffic_gen/                ← traffic matrix generator
```

## The critical `-disable_tor_ecn` gotcha

**This has burned us once and will burn you again if you forget.**

At `main_uec.cpp:739`:
```cpp
bool ecn_on_tor_dl = !receiver_driven && !force_disable_tor_ecn;
```

Passing `-sender_cc_only` sets `receiver_driven = false`. Without `-disable_tor_ecn`, this **re-enables ECN on ToR downlinks**, flooding mice flows with spurious CE marks and inflating FCTs. The leaf exception requires `force_disable_tor_ecn = true`, set only by `-disable_tor_ecn`.

**Rule:** any command that includes `-sender_cc_only` MUST also include `-disable_tor_ecn`. Detect the bug by grepping simulator stdout for `enable on tor downlink 1`; seeing it means the flag was forgotten.

Other always-on defaults: use `-load_balancing_algo freezing` (= paper-REPS, 8-slot bounded buffer), not `reps`, for anything paper-comparable or state-aware; pass `-sender_cc_algo nscc` explicitly (the default sender CC is not NSCC).

## Validating a mechanism, and sanity-checking every run

A mechanism that runs without error can still measure the wrong thing. On meeting_23_10_26 the constant-rate sender paced only data packets, so ACKs overloaded the degraded uplinks (~1.5%, rho ~ 1.015) and "matched" cells showed 49% random EV draws instead of ~1%; it was found only because we ran small cases with known answers. Details: `experiments/RATE_CONST_ARCHITECTURE.md`, `experiments/meeting_23_10_26/M4/investigate_k/README.md`.

### Before trusting a new mechanism
Implementing or changing anything under `htsim/sim/` goes through skill `add-mechanism`, which calls skill `validate-mechanism` (baseline binary, regression, theory-derived known-answer checks, negative controls). Mandatory, not optional.

### After every run: does this make sense?
1. **Write predictions before looking** (plan or README). A missed prediction is reported and investigated, not explained away (M5: over/healthy was predicted to tie and did not).
2. **Check theoretical twins.** Cells that theory says are equivalent must look alike (matched/degraded vs over/healthy; native 200G vs its time-scaled twin). If they differ, stop and find the cause before building on the result.
3. **Prove the configuration from the output, not the command line**: queue speeds in `-log_queue_stats`, the load-balancer line, no `enable on tor downlink 1`, flow count. Derive commands from the previous experiment's `flags()`; never retype them.
4. **Isolate the cause**: single-variable controls, at least 3 seeds, measured in the same run as the metric; use exact identities where possible (k replays from the event stream with 0 mismatches); run explicit exclusion controls (doubled ECN/queue thresholds ruled out marks and trims). Write "consistent with" unless an intervention shows causation.
5. **Suspect the analysis too**: windows containing start or drain transients, flow-tail effects (overwrites after the last draw), before/after-event off-by-one (k), symmetric CI whiskers dipping below 0 for counts.
6. **When an explanation is disproved, remove it from every README, page and plot note** (e.g. "ACK burstiness explains k" was withdrawn).

## Logs and traces: save them, compress after plotting, never delete

Every sim run saves its logs in the same invocation, even those not needed yet: stdout, `-log_reps_events` (REPS buffer state), `-log_queue_stats`, and `-log_sink_arrivals` when relevant. A later question usually needs a log nobody planned for, and a rerun costs hours. Trace only a representative host, not all of them: `-log_reps_events_src <id>` for one host under the degraded links (e.g. host 0 under ToR0), a few only if the metric needs a population (M4 used ToR0 hosts 0-7). After the stats and plots are built, compress (`gzip -9` per trace, `tar -czf` per directory) and keep the files on disk (gitignored, `traces/` next to the experiment); never delete them. The runner writes the compressed trace itself (template: `experiments/meeting_23_10_26/M5/scripts/run_m5.py`) so no cell is ever rerun just to get a log. Render buffer-view pages only on demand from the saved trace.

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
| Looking for published interactive plots in this repo | `experiments/**/*.html` is gitignored | They live in the private thesis repo; sync only when the user asks (skill `thesis-sync`) |
| Budget or rate counts only data packets | Matched cells overloaded ~1.5%, random draws jump | Enumerate every packet type using the resource; smoke-test one flow first |
| Plot disagrees with theory and we move on | Stale conclusions in READMEs/pages | Stop, find the cause, then update or retract every dependent claim |

## Conventions

- Do not touch the thesis repo (`C:\git_repos\Thesis_Itamar_BGU_Networking`) unless the user asks.
- No original lines are deleted from `htsim/sim/`; every modification is an addition or a wrap, with an `// ===== ADDED (<name>) =====` banner (details in `htsim/sim/CLAUDE.md`).
- Project guidance lives in these CLAUDE.md files; edit them directly (no separate compressed/original twin). Keep this root file short — move task-specific material to nested files or skills.
