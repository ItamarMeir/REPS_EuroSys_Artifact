# Exp22 — SRv6 Buffer Sweep + 5% Link Failure

## Purpose

Repeat of exp21 (SRv6 buffer-size sweep, K=16 fat tree, tornado 8 MB) with 5% of core↔agg
links permanently failed. Tests how well each FREEZING buffer size and REPS adapt to a
degraded topology where some paths are unavailable.

## Link Failure Details

- **Topology**: K=16 3-tier fat tree, 1024 hosts, 64 cross-pod paths
- **Total valid agg↔core links**: 1024 (128 agg × 8 uplinks each; connectivity: `core % 8 == agg % 8`)
- **Failed links**: 51 (5%), selected deterministically with `random.seed(0)`
- **Failure timing**: permanent from t=1 µs (recovery at t=10⁹ µs >> simulation end at 90 000 µs)
- **Coverage**: 46/128 agg switches and 34/64 core switches are affected (spread across all 16 pods)
- **All algorithm runs share the same 51 failed links** — traffic seeds 42/43/44 provide statistical diversity

## Design Matrix

10 algorithms × 2 CC modes × 3 seeds = 60 runs

**Algorithms**: path_static, freezing_b1, freezing_b2, freezing_b4, freezing_b8,
freezing_b16, freezing_b32, freezing_b64, reps, oblivious64 (all with `-use_srv6`
except path_static)

**oblivious64** (added 2026-08-25): `-load_balancing_algo oblivious` (pool size = 64,
already set by the shared `-paths 64` flag) — stateless per-packet uniform-random EV
pick out of 64, no REPS-style reuse/tracking (OPS-style baseline restricted to the
same 64-EV pool as the other algorithms).

**CC modes**: NSCC (`-sender_cc_algo nscc -cwnd 100`), Constant linerate (`-cwnd 1000`)

**Seeds**: 42, 43, 44

## Hypothesis

- **Small-B FREEZING (B=1, B=2)**: Constant EV rotation → quickly discovers and avoids failed paths.
  Expected to show less FCT degradation relative to exp21 baseline.
- **Large-B FREEZING (B=16–64)**: Retains EVs longer → may stay on failed paths until RTO evicts them.
  Expected to show more FCT degradation.
- **PATH_STATIC**: Greedy oracle knows failed links at setup time (path selection re-evaluates with
  current edge load which does not account for failures). May be hit or miss.
- **REPS**: Unbounded deque — continuous rotation, similar to small-B FREEZING.

## How to Run

```bash
bash experiments/exp22_link_failure_v22/scripts/run_exp22.sh
python3 experiments/exp22_link_failure_v22/scripts/aggregate.py
python3 experiments/exp22_link_failure_v22/scripts/plot.py
python3 experiments/exp22_link_failure_v22/scripts/plot_ecn.py
python3 experiments/exp22_link_failure_v22/scripts/plot_ev_diversity.py
python3 experiments/exp22_link_failure_v22/scripts/plot_ev_heatmap.py
```

## Outputs

- `plots/mean_fct.png` — Mean FCT ratio vs PATH_STATIC+constant baseline
- `plots/p99_fct.png`  — p99 FCT ratio
- `plots/slowdown.png` — Mean slowdown ratio
- `plots/ecn_exposure.png` — Mean and p99 ECN ACKs per flow
- `plots/ev_diversity.png` — EV usage diversity (sorted rank + box plot)
- `plots/ev_heatmap.png`   — EV usage heatmap per buffer size
- `data/exp22_flows.csv` — Tidy FCT data (all runs, all seeds)
- `data/buf_{algo}_nscc_s{seed}.csv` — Per-ACK buffer state (host 0, NSCC runs only)
