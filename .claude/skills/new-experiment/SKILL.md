---
name: new-experiment
description: Create a new expNN_* experiment directory in experiments/ (driver, aggregator, plotter, README, lineage row). Use when adding or scaffolding an experiment.
---

Full recipe: `experiments/RUNNING_EXPERIMENTS.md` (layout in §1, final checklist in §11). Read it before starting. Summary:

1. Create `experiments/expNN_short_name/` (NN = next integer) with `plots/`, `data/`, `scripts/`.
2. Bash driver iterates the design matrix, is idempotent, and always passes `-disable_tor_ecn`. Derive flags from the previous experiment's `flags()`; never retype them. Run `htsim_uec` through Docker.
   **Routing default: every sim runs with SRv6 source routing (`-use_srv6 -paths <P>`, EV -> `_paths[ev % P]`) unless the task says otherwise.** ECMP (no `-use_srv6`) is used only when the user asks for it, and the README then says so. Prove it from stdout of every cell: the line `SRv6 source routing enabled` and `no of paths <P>` (grep all cells, 0 exceptions). Under SRv6 the EV decides the physical path (e.g. path j = ToR uplink j), so per-path analysis needs no hash model.
3. Python aggregator writes a tidy CSV (`workload`, `mode`, `sev`, `seed`, `flow_id`, `fct_us`, `size`, `flow_class`).
4. Python plotter writes PNGs to `plots/` with 95% CI error bars (t-distribution, not naive ±SE); >= 3-5 seeds.
4b. If the experiment gets an interactive page, use skill `interactive-plotter` (plan which plots, in what order, before coding).
5. Compress runs: `tar -czf expNN/runs.tar.gz -C expNN/runs . && rm -rf expNN/runs/`.
6. Write `README.md` with required sections and relative image paths (`plots/foo.png`, never `/tmp/`). Write predictions before looking at results.
7. Add a row to the `experiments/README.md` lineage table.
8. Run the checklist in `RUNNING_EXPERIMENTS.md` §11, and the validation / sanity-check rules in the root `CLAUDE.md`. If the experiment introduces or changes a mechanism in `htsim/sim/`, use skill `add-mechanism` (it calls `validate-mechanism`).

## Logging and retention (every cell, from the first version of the runner)

- Log everything in the **same run** as the stats run; never a separate unlogged "official" run plus a logged rerun. Always pass `-log_reps_events <path>` and `-log_queue_stats <path>`; add `-log_reps_state` and similar if the diagnostic might be wanted later, even if the current analysis does not use it.
- Log **one representative source host** per cell, not all: `-log_reps_events_src <id>` (repeat only if the analysis needs more). Prefer a host under the degraded or failed element (e.g. a host under the degraded ToR0 links). Record the choice and why in the README, since a trace from the wrong host is useless later without a rerun.
- Build plots and stats immediately from that one run. Build buffer-view pages only on demand (expensive), from the saved trace.
- After plotting, **compress, never delete**: `gzip -9` each trace/log (`.csv.gz`, `.tsv.gz`) and `tar -czf runs.tar.gz` the raw `.out` files. Keep them on disk (gitignored, never committed).
- README table: file / cell / logged host / what it holds, so a later session can find the right trace.
