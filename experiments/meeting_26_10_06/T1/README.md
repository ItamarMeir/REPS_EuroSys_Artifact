# T1 - sanity check: does FCT scale with lost bandwidth?

## Question
Before trusting any buffer-size result under degradation, check that the simulator behaves proportionally: if a fraction of the links lose half their bandwidth, FCT should grow by the averaged capacity loss (Chen Avin, 2026-10-06: "if twice as many links fall, FCT should be twice as long"). Model: with n of 32 ToR0 uplinks at 50% speed, a flow sprayed over all 32 paths sees capacity `(64 - n) / 64` of normal, so FCT ratio = `64 / (64 - n)` (2.0 at n = 32), minus a small dilution from fixed latency.

## Setup
- Fabric `fat_tree_1024_1os_2t_400g`, tornado, 4 MiB and 16 MiB, **NSCC**, packet trimming ON, 3 seeds (42, 43, 44). Degradation: `-failed n -down_ratio 0.5` without `-skip_asy`, which concentrates all n degraded uplinks on ToR0; n in {0, 1, 2, 4, 8, 16, 32}. Affected group: the 32 ToR0 senders.
- Two arms: **`reps_b8_nscc`** (REPS, B = 8; reused from `exp30_packet_trimming_en`, no rerun) and **`path_static`** (each flow pinned to one path, new runs: 42 runs, 0 failures).
- `-disable_tor_ecn` is not passed, as in C1 and C2 (the exp30 trim-on base), for direct comparability.
- A first full sweep accidentally ran MPRDMA instead of NSCC (a flag-building bug in `common_t1.py`); it was caught, deleted and rerun under NSCC. The ratios were nearly identical.

## Results
- **`reps_b8_nscc`, whole-group p50 ratio vs the `64/(64-n)` model** (16 MiB): n = 1: 1.024 vs 1.016; n = 2: 1.039 vs 1.032; n = 4: 1.069 vs 1.067; n = 8: 1.140 vs 1.143; n = 16: 1.304 vs 1.333; **n = 32: 1.928 vs 2.000**. The 4 MiB pattern is the same, slightly more latency-diluted (n = 32: 1.874). Because REPS sprays each flow over all paths, each flow feels the average loss, as the model assumes.
- **`path_static` is a binary split, not a smooth pool.** Exactly n of the 32 flows are pinned to a degraded uplink and the rest are untouched (for example 16 MiB, n = 8: 24 flows at 354.25 us and 8 at 700.49 us). So the whole-group p50 stays at 1.000 until n = 16 and is the wrong statistic below that. The right statistic is the degraded subset's own FCT: **1.915x (4 MiB) and 1.977x (16 MiB) of baseline at every n from 1 to 32**, matching the n = 32 model value of 2.0 within 1 to 4% (the gap is fixed per-packet latency).
- **Diagnostics gate:** RTOs, fast-loss entries and freeze entries are exactly 0 in every cell of both arms, and ECN marks rise steeply with n. The slowdown is a pure bandwidth effect, not RTO or freeze amplification.
- **Verdict:** the model holds. n <= 4 predicts under 7% change, inside seed noise, so no claim is made there.

## Out of scope / caveats
- The kill axis (`-timed_fail_tor_uplinks`) was not run: exp30 Part B at F = 24 shows about 30x median FCT against a roughly 4x bandwidth loss, which is RTO and load-balancer dominated and would fail proportionality for reasons unrelated to bandwidth.
- B is swept only at 8 for the NSCC arm (exp30 Part A found B flat across the n ladder).
- 3 seeds; the degraded-subset CIs are effectively 0 (same per-flow value every seed).

## Reproduce
```bash
cd /workspace/experiments/meeting_06_10_26/T1/scripts
python3 run_t1.py --smoke      # 1 seed, n in {0, 32}, 16 MiB
python3 run_t1.py              # full: seeds 42/43/44, both sizes
python3 aggregate_t1.py        # -> ../data/ratio.csv, fct_path_static.csv, diagnostics_path_static.csv
python3 build_interactive.py   # -> ../plots/interactive.html
```

## Files
`PLAN.md` (original plan), `RESULTS.md` (full write-up, source of the numbers above), `scripts/`, `data/` (`ratio.csv` per (arm, size, n) with 95% CIs and the model value), `plots/interactive.html`.
