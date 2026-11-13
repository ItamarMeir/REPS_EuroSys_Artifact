---
name: new-experiment
description: Create a new expNN_* experiment directory in experiments/ (driver, aggregator, plotter, README, lineage row). Use when adding or scaffolding an experiment.
---

Full recipe: `experiments/RUNNING_EXPERIMENTS.md` (layout in §1, final checklist in §11). Read it before starting. Summary:

1. Create `experiments/expNN_short_name/` (NN = next integer) with `plots/`, `data/`, `scripts/`.
2. Bash driver iterates the design matrix, is idempotent, and always passes `-disable_tor_ecn`. Derive flags from the previous experiment's `flags()`; never retype them. Run `htsim_uec` through Docker.
3. Python aggregator writes a tidy CSV (`workload`, `mode`, `sev`, `seed`, `flow_id`, `fct_us`, `size`, `flow_class`).
4. Python plotter writes PNGs to `plots/` with 95% CI error bars (t-distribution, not naive ±SE); >= 3-5 seeds.
5. Compress runs: `tar -czf expNN/runs.tar.gz -C expNN/runs . && rm -rf expNN/runs/`.
6. Write `README.md` with required sections and relative image paths (`plots/foo.png`, never `/tmp/`). Write predictions before looking at results.
7. Add a row to the `experiments/README.md` lineage table.
8. Run the checklist in `RUNNING_EXPERIMENTS.md` §11, and the validation / sanity-check rules in the root `AGENTS.md`. Log `-log_reps_events` in the same run as the stats run, not a rerun.
