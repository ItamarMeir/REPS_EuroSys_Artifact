# exp19 — PATH_RR with one host restricted to 3 of 4 paths

**Question.** PATH_RR cycles each flow over all distinct physical paths. What happens to the whole fabric when one host can use fewer paths than the others? Is the damage local to that host, or does it spread?

**Setup.** `-load_balancing_algo path_rr`, `-path_rr_start_mode src_mod`, NSCC, `-cwnd 155 -q 60 -ecn 12 48 -disable_tor_ecn`, k=4 3-tier fat tree (16 hosts, 4 paths per pair), tornado, 256 MiB per flow. Two conditions: `baseline`, and `constrained` (`-path_rr_npaths_override "0:3"`: host 0 may use only 3 of its 4 paths). The script `scripts/01_run_exp19.sh` writes per-run core-queue, ToR-queue and host-0 cwnd traces. Its header comment says 3 seeds; the data on disk covers 10 seeds (42-51), so 20 runs.

**Result** (FCT slowdown vs the topology optimum, seeds 42-44 / all 10 seeds):

| | baseline | constrained |
|---|---|---|
| host 0 | 1.039 / 1.037 | 1.240 / 1.237 |
| flow 1 (same pod, shares host 0's agg switches) | 1.039 / 1.037 | 1.131 / 1.121 |
| all other flows | unchanged (< 0.001) | |

The damage stays local: only the restricted host and the one flow that shares its upstream links are slowed; congestion stays at the pod-0 agg→core links and does not spread network-wide. Flows into the destination pod improve by about 0.002.

**Files.** `scripts/01_run_exp19.sh` (driver), `aggregate_exp19.py`, `plot_exp19*.py`, `plots/{exp19_fct,exp19_queues,exp19_path_rr_asymmetry}.png`, `data/` (per-run `.out` and trace CSVs). `output_metrics/` holds derived per-run summaries.

**Follow-up.** [exp20](../exp20_path_rr_asymmetry_k8_v20/) repeats this on a k=8 fabric.
