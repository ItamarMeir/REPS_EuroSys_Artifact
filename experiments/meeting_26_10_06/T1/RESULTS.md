# T1 results — FCT vs lost bandwidth, NSCC

42 runs (path_static, both flow sizes, 3 seeds), 0 failures. `reps_b8_nscc`
cells reused directly from `exp30_packet_trimming_en/data/fct.csv` (no
rerun). Both arms use NSCC (`-sender_cc_algo nscc`) and the same degrade
config: `-failed n` (no `-skip_asy`, concentrates all `n` degraded uplinks on
ToR0), `-down_ratio 0.5`, affected group = ToR0 senders (src<32).

A real bug happened mid-run: the first full sweep (and its smoke test)
accidentally used MPRDMA (`common_t1.py` built flags from `"reps_b1"` instead
of `"reps_b1_nscc"` — the suffix is what sets `cc_algo` in
`common30.base_flags`). Caught before writing this doc, old `stdout.txt`
files deleted, reran under NSCC. Confirmed from each run's own stdout
(`sender based algo nscc`). Numbers below are the NSCC rerun; they are
numerically almost identical to the MPRDMA pass (`degraded_subset_ratio`
1.9150→1.9152, 1.9774→1.9774) — expected, since a single pinned flow on a
simply-halved link is serialization-bound regardless of CC algorithm, no
spraying/racing for the CC to affect.

## Headline: `path_static` is a binary per-flow split, not a smooth pool

Checked directly against raw per-flow FCTs (not just the aggregate): at every
`n`, path_static's 32 ToR0 flows land on exactly **two point masses**, no
values between them — e.g. 16 MiB, n=8: 24 flows at 354.25us, 8 flows at
700.49us. Exactly `n` of 32 flows are pinned to a degraded uplink (fully
halved-bandwidth, individually ~2x) and the rest are untouched. This means:

- **Whole-group p50 is the wrong statistic below n=16**: with <16 of 32 flows
  degraded, the median sits in the untouched group → ratio stays exactly
  1.000 for n=1,2,4,8 (both sizes). It only starts moving at n=16 (half the
  group) and approaches the full-degradation value at n=32.
- **The degraded subset's own FCT is the real physics check**: its ratio to
  the n=0 baseline is **flat across every n (1 through 32)** at
  **1.915 (4 MiB)** / **1.977 (16 MiB)**, CI effectively 0 (same per-flow
  value every seed) — matching the `64/(64-n)` model's n=32 prediction
  (2.0) to within 1-4%, the gap explained by fixed per-packet/RTT latency
  `L` diluting a pure-serialization ratio (model: `FCT = L + S*64/(64-n)`,
  `S`=serialization time; 16 MiB's larger `S` is why it tracks closer to 2.0
  than 4 MiB does).

**Verdict for the pinned/SoL-style reference: model holds, cleanly**, once
read at the per-flow level instead of the whole-group median.

## `reps_b8_nscc`: whole-group p50 tracks the averaged-pool model directly

Unlike path_static, NSCC/Freezing sprays each flow across all 32 paths over
its lifetime, so each flow feels something close to the *average* capacity
loss, not a binary hit-or-miss. That average is exactly what `64/(64-n)`
predicts, and the whole-group p50 ratio tracks it closely at every n (16 MiB):

| n | measured p50 ratio | model `64/(64-n)` |
|---|---|---|
| 1 | 1.024 | 1.016 |
| 2 | 1.039 | 1.032 |
| 4 | 1.069 | 1.067 |
| 8 | 1.140 | 1.143 |
| 16 | 1.304 | 1.333 |
| 32 | 1.928 | 2.000 |

(4 MiB: same pattern, slightly more latency-diluted — n=8: 1.136 vs 1.143;
n=32: 1.874 vs 2.000.) Full table: `data/ratio.csv`.

**Pass/fail (per the plan's n=16/32 discriminating points):** both the
path_static degraded-subset ratio and the reps_b8_nscc whole-group ratio land
inside or very near the model band at n=16 and n=32 — **model holds**. n<=4
predicts <7% change (inside seed noise) and is correctly not used for a
claim.

## Diagnostics gate

`rtos`, `fast_loss_per_host`, `freeze_entries_per_host` are **exactly 0**
across every n, both arms, both sizes (`data/diagnostics_path_static.csv`,
`exp30_packet_trimming_en/data/diagnostics.csv`). Confirms exp28/exp30's
established pattern: this degradation regime drives ECN marking, not packet
loss or freeze entry — so the measured FCT ratios are a clean bandwidth
effect, not contaminated by RTO/freeze amplification. ECN-marks-per-host
rise steeply with n in both arms (expected), much higher under NSCC/Freezing
spray than under path_static pinning (spray touches the degraded links from
many more flow-path combinations over the run).

## Out of scope (per plan)

- Kill axis (`-timed_fail_tor_uplinks`) not run here — exp30 Part B's F=24
  cell shows ~30x median FCT against a ~4x bandwidth-loss ideal (RTO/LB
  dominated), not a bandwidth story; would fail proportionality for reasons
  unrelated to lost bandwidth.
- B swept only at 8 for the nscc arm (exp30 Part A: B flat across the A1
  ladder at every n) — stands in for B=1..256.
- Known, inherited gap: trim-on and `-sender_cc_only` without
  `-disable_tor_ecn` (`common30.base_flags`, confirmed `tor_ecn_reenabled`
  on every run) — same call C1/C2 made, kept for direct comparability.

## Files

- `data/ratio.csv` — per-(arm,size,n): p50 ratio, degraded-subset ratio
  (path_static only), both with 95% CI (n=3 seeds), vs `model_ratio`.
- `data/fct_path_static.csv`, `data/diagnostics_path_static.csv` — per-seed
  raw path_static rows.
- `runs/_full_run.log` — final (NSCC) run log, 42/42 ok, 0 FAIL.
