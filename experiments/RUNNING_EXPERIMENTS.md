# How to run and save a new state-aware experiment

This document is written **for future Claude Code agents** (or humans) picking up this work. It's a recipe for adding a new `expNN_*/` subdirectory in the layout we already use, so the next experiment is discoverable and reproducible alongside the existing ones.

If you're new here, start with [README.md](README.md) for the lineage and [ARCHITECTURE.md](ARCHITECTURE.md) for the code-level design.

---

## 1. Layout invariant

Every new experiment is a sibling directory under `experiments/` named `expNN_short_name/` (NN = next integer), with this internal shape:

```
expNN_short_name/
├── README.md          # required
├── plots/             # PNGs only
├── data/              # tidy CSVs (one row per flow, or per measurement)
├── scripts/           # driver bash + aggregator + plotter
└── runs.tar.gz        # compressed raw .out files (after a successful run)
```

Don't deviate. If a future experiment needs additional artifacts (e.g., gnuplot files), add a sibling subdir like `traces/`, but keep the four canonical ones present.

---

## 2. Before you run anything

Sanity-check three things:

1. **Build is fresh**:
   ```bash
   cd htsim/sim && make -j 8 && cd datacenter && make -j 8 && cd ../../..
   test -x htsim/sim/datacenter/htsim_uec || echo "BUILD FAILED"
   ```
2. **Leaf exception is enabled**: any CLI you build must include `-disable_tor_ecn` whenever it also has `-sender_cc_only`. Otherwise [`main_uec.cpp:739`](../htsim/sim/datacenter/main_uec.cpp#L739) re-enables ECN on ToR downlinks and you'll measure the wrong thing. See [ARCHITECTURE.md § Leaf exception](ARCHITECTURE.md) for the full story.
3. **Seeds are pinned**: pass `-seed <N>` explicitly and sweep at least 3-5 seeds for any aggregate-FCT claim. Don't trust single-seed numbers — v3 showed the noise floor is ~10% on individual FCTs.

---

## 3. Write the driver (bash)

Pattern: one bash script that iterates the design matrix and writes per-cell `.out` files into `expNN/runs/<scenario_dir>/<seed>.out`. Make it **idempotent** — if a `.out` file already ends with `^Done` or `New: 0`, skip the cell.

Template (adapt from [`exp03_matrix_sweep_v3/scripts/v3_run_matrix.sh`](exp03_matrix_sweep_v3/scripts/v3_run_matrix.sh)):

```bash
#!/bin/bash
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${EXP_DIR}/../.." && pwd)"
HTSIM="${REPO_ROOT}/htsim/sim/datacenter/htsim_uec"
TOPO="${REPO_ROOT}/htsim/sim/datacenter/topologies/reps/fat_tree_128_1os_3t_400g.topo"
OUT_ROOT="${EXP_DIR}/runs"
mkdir -p "${OUT_ROOT}"

COMMON_FLAGS=(
  -sack_threshold 4000 -end 5000 -paths 65535
  -sender_cc_only -sender_cc_algo nscc -topo "${TOPO}"
  -linkspeed 400000 -ecn 25 76 -q 100 -cwnd 151
  -load_balancing_algo freezing -exit_freeze 200000000
  -disable_tor_ecn          # ALWAYS include
)
# ... iterate workloads × scenarios × seeds ...
```

Pin all paths relative to `${BASH_SOURCE[0]}` so the script runs from anywhere.

---

## 4. Write the aggregator (Python)

Pattern: one Python script that walks `expNN/runs/` and emits one tidy long-form CSV per metric category into `expNN/data/`.

Columns to standardize (so a future cross-experiment analysis is possible):

| Column | Type | Notes |
|---|---|---|
| `workload` | str | one of the workload names in [workloads/README.md](workloads/README.md) |
| `mode` | str | `vanilla` or `stateaware` (or extend) |
| `sev` | int | failure severity (number of failed links, or 0 for healthy) |
| `seed` | int | the `-seed` passed |
| `flow_id` | int | from the TM |
| `fct_us` | float | FCT in microseconds |
| `size` | int | flow size in bytes |
| `flow_class` | str | mice / elephant / incast (computed from flow_id via workload classifier) |

For event counts use a parallel CSV (one row per run, one column per event type).

Pitfall: `df.mode` is a reserved pandas attribute (returns dtype, not the column). Always use `df["mode"]` in code.

Template: [`exp03_matrix_sweep_v3/scripts/v3_aggregate.py`](exp03_matrix_sweep_v3/scripts/v3_aggregate.py).

---

## 5. Write the plotter (Python)

Pattern: one Python script that reads `expNN/data/*.csv` and emits PNGs into `expNN/plots/`. Conventions:

- Vanilla = `tab:blue`, state-aware = `tab:orange` (consistent across experiments).
- Error bars: **95% CI on the mean across seeds**, using `scipy.stats.t.ppf` (not naive ±SE). Min 3 seeds.
- Significance markers when comparing modes: Mann-Whitney U on pooled per-flow FCTs, markers `*` p<0.05, `**` p<0.01, `***` p<0.001.
- Title: `<workload> — <metric> vs <axis>   (<n> seeds, 95% CI)`.
- Save with `dpi=120` to keep PNGs under ~100 KB.

Template: [`exp03_matrix_sweep_v3/scripts/v3_plot.py`](exp03_matrix_sweep_v3/scripts/v3_plot.py).

---

## 6. Compress raw runs

After a successful sweep:

```bash
tar -czf expNN/runs.tar.gz -C expNN/runs .
rm -rf expNN/runs/
```

200 raw text `.out` files (~45 MB plain) → ~3 MB compressed. The tarball is the experiment's reproducibility record; don't skip it.

If you need to inspect individual files later: `tar -xzf runs.tar.gz <path-in-archive>`.

---

## 7. Write the README

Required sections, in order:

1. **Title + one-line summary**.
2. **Methodology note**: anything tricky about CLI flags or environment. **Always restate the `-disable_tor_ecn` requirement.**
3. **Topology** table.
4. **Workloads** table (link back to [`workloads/README.md`](workloads/README.md) for details).
5. **Experiment matrix** table.
6. **Key findings** with embedded plot images (relative paths under `plots/`).
7. **Event-count validation** if the experiment exercises state-aware wiring.
8. **Reproducing this experiment** — exact commands a stranger can copy-paste.
9. **Files** — what's in each subdir.

Image refs: always `plots/foo.png` (relative). Never `/tmp/...` or absolute.

---

## 8. Update the master README

Open [`experiments/README.md`](README.md), add a new row to the lineage table, and add a one-line takeaway. Keep the table chronological; don't re-order.

---

## 9. Common pitfalls

| Pitfall | Symptom | Fix |
|---|---|---|
| Forgot `-disable_tor_ecn` | mice FCT looks unexpectedly high (or low) in healthy state; `enable on tor downlink 1` in stdout | Add the flag; re-run. |
| Used `df.mode` in pandas | runtime error or unexpected behavior | Use `df["mode"]`. |
| Hardcoded `/tmp/` paths | Scripts work for you, break for others | Resolve paths from `__file__` / `${BASH_SOURCE[0]}`. |
| Forgot `-sender_cc_algo nscc` | Mysteriously slow flows | Default sender CC isn't NSCC — must specify. |
| `-load_balancing_algo reps` vs `freezing` | Buffer instrumentation column `fresh` stuck at 0 | `reps` doesn't populate the circular buffer. Use `freezing` (= paper-REPS) for state-aware work. |
| Single seed, claiming a trend | Mean differences look real but vanish on rerun | Always sweep ≥ 3 seeds, plot 95% CI. |
| Raw `runs/` dir committed (200+ files) | Repo bloat | Compress to `runs.tar.gz` and remove the raw dir before commit. |

---

## 10. Memory etiquette

If your experiment reveals a design hypothesis worth keeping past the current session, save it under the project memory directory:

```
/root/.claude/projects/-home-itamar-WSL-Clones-REPS-EuroSys-Artifact/memory/
```

Example: [`reps_buffer_cache_idea.md`](/root/.claude/projects/-home-itamar-WSL-Clones-REPS-EuroSys-Artifact/memory/reps_buffer_cache_idea.md) preserves an architectural hypothesis raised during v2 analysis. Use the same frontmatter format (`name`, `description`, `metadata.type`), and add an entry to `MEMORY.md` in the same dir.

Reference memories from your experiment's README so future readers can chase the thread.

---

## 11. Quick checklist before declaring "done"

```bash
# from repo root
EXP=expNN_short_name

# 1. Directory shape correct
for d in plots data scripts; do test -d experiments/$EXP/$d || echo "MISSING: $d/"; done
test -f experiments/$EXP/README.md       || echo "MISSING: README.md"
test -f experiments/$EXP/runs.tar.gz     || echo "WARNING: no runs.tar.gz"

# 2. README links to relative plot paths (no /tmp, no absolute)
grep -E "^!\[.*\]\((/|/tmp)" experiments/$EXP/README.md \
  && echo "BUG: absolute or /tmp image refs in README"

# 3. Scripts portable
grep -l "/tmp/" experiments/$EXP/scripts/* \
  && echo "BUG: scripts reference /tmp"

# 4. Master README mentions the new experiment
grep -q "$EXP" experiments/README.md || echo "TODO: update master README"
```

If all four checks pass, you're done.
