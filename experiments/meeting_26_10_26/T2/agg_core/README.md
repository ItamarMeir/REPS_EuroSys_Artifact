# T2b: 3-tier k=8, agg->core uplinks of pod0 (4 aggs x 4 cores, 16 links)

Sub-experiment B of [`../README.md`](../README.md) (setup, predictions, checks and the discussion of results are there). Degraded links: agg->core uplinks of pod0 (4 aggs x 4 cores, 16 links); in each switch 2 of the 4 uplinks at ratio r and 2 at 1 - r (mean 0.5), queues `US<a>->CS<a+4l>`, degrade lines `agg_core agg core ratio` (new key). Matched 200G, REPS (`freezing`), B in {1, 2, 4, 5, 6, 7, 8, 16, 32, 64, 128} (5, 6 and 7 added later), seeds 42-46.

## Files

- `data/results.jsonl`: one row per cell (4 shapes + the healthy reference: 5 configs x 11 B x 5 seeds = 275 rows (B in 1, 2, 4, 5, 6, 7, 8, ..., 128)); `data/t2_summary.csv` (mean, 95% t-CI, k and ACK-window distributions, gate), `data/t2_knees.csv`, `data/t2_steady_k.csv`, `data/t2_uplinks.json` (degraded-scope links, seed-mean), `data/run_seeds*.log`.
- `plots/t2_fct_overwrite.png` (max FCT, pod0-source max FCT, overwrites against B), the interactive page is one page for both scopes: [`../plots/interactive.html`](../plots/interactive.html) (gitignored).
- `traces/`: gzip'd `-log_reps_events` (16 pod0 hosts), `-log_queue_stats` and simulator stdout per cell (gitignored, never deleted).

## Knees and per-shape statistics (5 seeds, B=8 columns at B=8)

| shape | steady k p50 / p99 / max | drain k max | B_ks99 | B_ow | B_fct | B_fct (pod0 src) | B_fct (p99) | % random EVs B=8 | overwrites % B=8 | ECN ACKs B=8 | retransmits B=8 | % sends on degraded links B=8 | gate | speed proof |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| healthy | 4.0 / 5.4 / 6.4 | 6.4 | 8 | 5 | 1 | 1 | 1 | 0.06 | 0.000 | 0 | 0 | 50.9 | clear | - |
| uniform 50/50 | 4.6 / 8.2 / 11.0 | 9.8 | 16 | 16 | 5 | 5 | 5 | 0.84 | 0.142 | 178 | 0 | 50.0 | clear | ok |
| 25/75 | 12.4 / 17.6 / 19.6 | 19.4 | 32 | 16 | 8 | 8 | 8 | 2.74 | 0.396 | 1229 | 142 | 23.8 | clear | ok |
| 10/90 | 6.4 / 10.2 / 12.4 | 12.4 | 16 | 16 | 7 | 7 | 8 | 2.49 | 0.282 | 629 | 663 | 9.2 | clear | ok |
| 5/95 | 4.8 / 8.4 / 10.8 | 11.0 | 16 | 16 | 8 | 8 | 8 | 2.97 | 0.172 | 627 | 970 | 4.1 | clear | ok |

The max-FCT table against B is in [`../README.md`](../README.md).

### B = 5, 6 and 7 added (5 seeds; predictions and outcomes in [`../README.md`](../README.md))

| shape | max FCT B=4 / 5 / 6 / 7 / 8 / 128 | % random B=4 / 5 / 6 / 7 / 8 | n random B=4 / 5 / 6 / 7 / 8 | n random on degraded B=4 / 5 / 6 / 7 / 8 | overwrites % B=4 / 5 / 6 / 7 / 8 |
|---|---|---|---|---|---|
| uniform 50/50 | 709.1 / 708.5 / 708.1 / 707.8 / 707.7 / 707.5 | 9.67 / 5.49 / 2.68 / 1.89 / 0.84 | 6230 / 3540 / 1727 / 1219 / 540 | - / - / - / - / - | 5.679 / 3.071 / 1.333 / 0.552 / 0.142 |
| 25/75 | 712.4 / 711.1 / 710.4 / 709.5 / 708.8 / 707.6 | 10.08 / 6.90 / 5.11 / 3.51 / 2.74 | 6509 / 4461 / 3300 / 2268 / 1770 | 3250 / 2221 / 1634 / 1121 / 874 | 5.841 / 3.541 / 2.150 / 1.013 / 0.396 |
| 10/90 | 721.2 / 718.3 / 717.6 / 716.1 / 715.3 / 714.2 | 10.40 / 7.24 / 4.92 / 3.45 / 2.49 | 6782 / 4718 / 3201 / 2244 / 1619 | 3363 / 2353 / 1594 / 1118 / 813 | 4.837 / 2.590 / 1.524 / 0.798 / 0.282 |
| 5/95 | 732.0 / 727.3 / 722.2 / 720.8 / 718.4 / 717.8 | 9.48 / 6.74 / 4.88 / 3.65 / 2.97 | 6262 / 4427 / 3193 / 2390 / 1943 | 3116 / 2219 / 1595 / 1195 / 979 | 4.348 / 2.495 / 1.170 / 0.507 / 0.172 |

The `B_fct` columns in the table above are on the finer grid. Uniform 50/50 has one link speed, so there is no degraded set (shown as -). Random draws land on the degraded paths 49 to 51% of the time (uniform draws over half the paths).
