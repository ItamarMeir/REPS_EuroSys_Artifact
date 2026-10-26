# experiments — guide

Loaded only when working on files under `experiments/`. Repo-wide rules are in the root `CLAUDE.md`. Creating a new experiment: use the `new-experiment` skill (recipe in `RUNNING_EXPERIMENTS.md`).

## Where things are

- `README.md` — lineage table of every experiment + takeaways. Start here; add a row for each new experiment.
- `ARCHITECTURE.md` — state-aware design. Other mechanism docs: `PATH_RR_ARCHITECTURE.md`, `SWIFT_CC_ARCHITECTURE.md`, `RATE_CONST_ARCHITECTURE.md`, `OFAN_ARCHITECTURE.md`, `SRV6_VALIDATION_REPORT.md`.
- `MODIFICATIONS.md` — source of truth for original-vs-added code in `htsim/sim/`.
- `RUNNING_EXPERIMENTS.md` — how to add an experiment.
- `workloads/` — shared TM files + generators. `tools/` — trace viewers (`tools/README.md`).
- Per-experiment dirs `expNN_*` and `meeting_*`, each with its own `README.md`.

## Conventions

- Each experiment dir: `plots/`, `data/`, `scripts/`, `README.md` with relative image paths (`plots/foo.png`, never `/tmp/`).
- Scripts resolve paths from `__file__` / `${BASH_SOURCE[0]}`; drivers are idempotent and always pass `-disable_tor_ecn`.
- Tidy CSV columns: `workload`, `mode`, `sev`, `seed`, `flow_id`, `fct_us`, `size`, `flow_class`. Plots use 95% CI (t-distribution), >= 3-5 seeds.
- Compress raw runs to `runs.tar.gz` before committing.
- Logging and retention: log traces (`-log_reps_events` for one representative host, `-log_queue_stats`, ...) in the same run as the stats run, plot immediately, then `gzip -9` and keep them on disk, never delete, never commit. Details in skill `new-experiment`.
- `experiments/**/*.html` is gitignored; interactive pages are published in the thesis repo (see `thesis-sync` skill, only on user request).
- No test suite for `htsim/sim/` or `experiments/`: validate by running and inspecting output (root `CLAUDE.md` validation checklist).

## Early findings (exp01-03; detail in each README)

- **exp01** (`-load_balancing_algo reps`): raw outputs lost. Unbounded `_next_pathid` EV set not predictive of ECN (`corr(recycle, ECN) ≈ 0`), which triggered the switch to `freezing`.
- **exp02** (`freezing`): raw outputs lost. `fresh = 0 ⇒ P(next ACK ECN-marked) ≈ 1.0` in every workload: bounded 8-slot buffer emptiness is a near-deterministic congestion signal. Motivated the v4 buffer-fill-gate idea (`htsim/sim/CLAUDE.md`, future directions).
- **exp03** (`exp03_matrix_sweep_v3/`, full artifacts): 4 workloads × 5 failure severities × 2 modes × 5 seeds = 200 cells. With `-disable_tor_ecn` correctly set, state-aware FCT impact on synthetic workloads is small (strongest: incast p99 improves ~14 μs in healthy composite). Wiring validated: SA asymmetric-flag flips == SA FREEZING starts at every cell; both 0 across all 40 healthy runs.
