# T2a: 3-tier k=8, ToR->agg uplinks of pod0 (4 ToRs x 4 aggs, 16 links)

Sub-experiment A of [`../README.md`](../README.md) (setup, predictions, checks and the discussion of results are there). Degraded links: ToR->agg uplinks of pod0 (4 ToRs x 4 aggs, 16 links); in each switch 2 of the 4 uplinks at ratio r and 2 at 1 - r (mean 0.5), queues `LS<t>->US<a>`, degrade lines `tor agg ratio`. Matched 200G, REPS (`freezing`), B in {1, 2, 4, 5, 6, 7, 8, 16, 32, 64, 128} (5, 6 and 7 added later), seeds 42-46.

## Files

- `data/results.jsonl`: one row per cell (4 shapes + the healthy reference: 5 configs x 11 B x 5 seeds = 275 rows (B in 1, 2, 4, 5, 6, 7, 8, ..., 128)); `data/t2_summary.csv` (mean, 95% t-CI, k and ACK-window distributions, gate), `data/t2_knees.csv`, `data/t2_steady_k.csv`, `data/t2_uplinks.json` (degraded-scope links, seed-mean), `data/run_seeds*.log`.
- `plots/t2_fct_overwrite.png` (max FCT, pod0-source max FCT, overwrites against B), the interactive page is one page for both scopes: [`../plots/interactive.html`](../plots/interactive.html) (gitignored).
- `traces/`: gzip'd `-log_reps_events` (16 pod0 hosts), `-log_queue_stats` and simulator stdout per cell (gitignored, never deleted).

## Knees and per-shape statistics (5 seeds, B=8 columns at B=8)

| shape | steady k p50 / p99 / max | drain k max | B_ks99 | B_ow | B_fct | B_fct (pod0 src) | B_fct (p99) | % random EVs B=8 | overwrites % B=8 | ECN ACKs B=8 | retransmits B=8 | % sends on degraded links B=8 | gate | speed proof |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| healthy | 4.0 / 5.4 / 6.4 | 6.4 | 8 | 5 | 1 | 1 | 1 | 0.06 | 0.000 | 0 | 0 | 50.9 | clear | - |
| uniform 50/50 | 4.0 / 7.0 / 9.4 | 9.0 | 8 | 8 | 4 | 4 | 4 | 0.46 | 0.008 | 85 | 0 | 50.0 | clear | ok |
| 25/75 | 13.2 / 18.4 / 20.4 | 20.2 | 32 | 16 | 6 | 6 | 6 | 2.19 | 0.219 | 1032 | 108 | 23.6 | clear | ok |
| 10/90 | 7.4 / 11.2 / 13.0 | 13.4 | 16 | 16 | 7 | 7 | 6 | 2.17 | 0.103 | 534 | 668 | 9.2 | clear | ok |
| 5/95 | 5.2 / 9.6 / 12.2 | 13.0 | 16 | 8 | 6 | 6 | 6 | 2.32 | 0.054 | 387 | 952 | 4.3 | clear | ok |

The max-FCT table against B is in [`../README.md`](../README.md).

### B = 5, 6 and 7 added (5 seeds; predictions and outcomes in [`../README.md`](../README.md))

| shape | max FCT B=4 / 5 / 6 / 7 / 8 / 128 | % random B=4 / 5 / 6 / 7 / 8 | n random B=4 / 5 / 6 / 7 / 8 | n random on degraded B=4 / 5 / 6 / 7 / 8 | overwrites % B=4 / 5 / 6 / 7 / 8 |
|---|---|---|---|---|---|
| uniform 50/50 | 708.2 / 707.7 / 707.5 / 707.4 / 707.5 / 707.3 | 4.84 / 1.87 / 0.92 / 0.51 / 0.46 | 3122 / 1209 / 596 / 330 / 299 | - / - / - / - / - | 3.210 / 1.108 / 0.310 / 0.062 / 0.008 |
| 25/75 | 710.2 / 710.2 / 708.3 / 707.8 / 707.9 / 707.7 | 6.82 / 4.00 / 2.39 / 2.14 / 2.19 | 4403 / 2583 / 1546 / 1383 / 1411 | 2227 / 1283 / 768 / 691 / 698 | 3.588 / 1.661 / 0.496 / 0.301 / 0.219 |
| 10/90 | 719.5 / 717.4 / 716.2 / 716.1 / 714.7 / 714.6 | 7.34 / 4.81 / 3.31 / 2.45 / 2.17 | 4781 / 3130 / 2154 / 1596 / 1411 | 2389 / 1567 / 1075 / 807 / 708 | 3.149 / 1.582 / 0.767 / 0.280 / 0.103 |
| 5/95 | 727.6 / 723.3 / 719.0 / 719.4 / 718.3 / 717.8 | 7.73 / 5.10 / 3.41 / 2.60 / 2.32 | 5083 / 3341 / 2233 / 1700 / 1519 | 2534 / 1661 / 1118 / 852 / 761 | 3.110 / 1.557 / 0.645 / 0.237 / 0.054 |

The `B_fct` columns in the table above are on the finer grid. Uniform 50/50 has one link speed, so there is no degraded set (shown as -). Random draws land on the degraded paths 49 to 51% of the time (uniform draws over half the paths).
