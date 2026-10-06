# exp30_packet_trimming_en -- exp30 rerun with packet trimming enabled

## Purpose

[`exp30_concentrated_path_loss`](../exp30_concentrated_path_loss/) runs every arm with
`-disable_trim`. That flag flips `UecSrc::_trim_disbled = true`, which gates REPS's
freeze-on-RTO entry (`htsim/sim/uec.cpp:4981-4994`) behind an extra RTT bound:

```cpp
if (_trim_disbled && _last_rto_max_rtt < _base_rtt * 1.65) {
    circular_buffer_reps->setFrozenMode(true);   // only path in when trim is DISABLED
    ...
} else if (!_trim_disbled) {
    circular_buffer_reps->setFrozenMode(true);   // unconditional when trim is ENABLED
    ...
}
```

Investigated directly against `exp30_concentrated_path_loss/data/diagnostics.csv`: at Part A
severities n=8/16/32 (sustained 50% degradation on ToR0's uplinks), `_last_rto_max_rtt` stays
above `1.65*_base_rtt` for the whole run, so the freeze gate never opens under
`-disable_trim` -- `freeze_entries_per_host`/`freeze_us_mean` sit at exactly 0 even though
`rto_per_host` climbs into the dozens per host, for every B in the ladder and **both
dual-window arms** (`reps_b8_dual`, `reps_b8_dual_cap`).

This experiment reruns exp30's entire design matrix unchanged except dropping
`-disable_trim`. With trim enabled, the `else if (!_trim_disbled)` branch is unconditional --
gated only on `_load_balancing_algo == FREEZING`, not on CC algo -- so freeze-on-RTO should now
fire correctly at every severity, for the plain B ladder and for both dual-window arms alike.
No C++ change was made or needed; this is purely a flag flip + full rerun to verify that
empirically.

## Design matrix

Byte-identical to `exp30_concentrated_path_loss` (see its README/`common30.py` docstring for
the full Part A/Part B rationale) -- same Part A1 (severity sweep n in {0,1,2,4,8,16,32},
down_ratio 0.5), Part A2 (ratio sweep, n=8 fixed, down_ratio in exp28's RATIOS), Part B (static
real kill, F in {0,1,2,4,8,16,24,31}); same 2 sizes (4 MiB, 16 MiB), same 8 arms
(`reps_b1..b32`, `reps_b8_dual`, `reps_b8_dual_cap`), plus the NSCC buffer sweep
(`reps_b{1,2,4,8,16,32}_nscc`, see below), same 3 seeds (42/43/44), same
`fat_tree_1024_1os_2t_400g` / tornado / `-q 101 -ecn 25 76 -cwnd 151` / `-exit_freeze 200us`.
~1,020 runs total for the MPRDMA/dual matrix; the NSCC sweep adds 756 runs (see below). The only flag difference anywhere in `common30.py::base_flags()` is the
absence of `-disable_trim`.

## NSCC buffer sweep

Meeting 2026-10-06 asked whether NSCC changes the buffer-size picture (NSCC x B was never
tested; it had only been run at B=8 as `reps_b8_nscc`). The sweep adds the rest of the
B ladder under NSCC: `reps_b1_nscc`, `reps_b2_nscc`, `reps_b4_nscc`, `reps_b16_nscc`,
`reps_b32_nscc`. `reps_b8_nscc` was already present. Each NSCC arm uses the same LB/buffer
flags as its MPRDMA counterpart; only `-sender_cc_algo` differs (`nscc` instead of
`mprdma`, see `common30.base_flags`).

Run the NSCC arms only:

```bash
NSCC=reps_b1_nscc,reps_b2_nscc,reps_b4_nscc,reps_b8_nscc,reps_b16_nscc,reps_b32_nscc
MSYS_NO_PATHCONV=1 docker exec reps-artifact-dev bash -lc "cd /workspace/experiments/exp30_packet_trimming_en/scripts &&   python3 run30.py --part a1 --arms $NSCC &&   python3 run30.py --part a2 --arms $NSCC &&   python3 run30.py --part b  --arms $NSCC &&   python3 aggregate30.py && python3 plot30.py && python3 build_interactive.py"
```

Runs are idempotent: finished `stdout.txt` files are skipped, so an interrupted sweep resumes.
Cost: about 36 s per run; 756 runs (252 A1 + 216 A2 + 288 B, minus the existing B=8 cells).
Parts can run in parallel (one container each, 8 cores).

Outputs and legends:

- `data/fct.csv`, `data/diagnostics.csv`: rows carry `cc` (`mprdma` / `nscc` / dual).
- `data/resolvable.csv`: one verdict set per CC. The B comparison is never mixed across CC
  (MPRDMA ladder and NSCC ladder are separate axes; dual-window arms excluded).
- Plots: legends show `REPS B=<b> (MPRDMA)` / `(NSCC)`; NSCC is drawn as filled squares,
  MPRDMA as hollow circles, dual-window as hollow triangles. Colour follows B.
- `interactive.html`: NSCC ladder drawn in magenta, one series per B.

Results: pending the sweep (see the status line below).

**Status:** sweep in progress; results section to be filled once `aggregate30.py` has run on
the complete set.

## Regenerate

```bash
cd htsim/sim && make -j 8 && cd datacenter && make -j 8 && cd ../../..   # if not already built

MSYS_NO_PATHCONV=1 docker run --rm -v "$PWD:/workspace" \
  -w /workspace/experiments/exp30_packet_trimming_en/scripts \
  reps-artifact:latest bash -lc '
    python3 run30.py --part a1 &&
    python3 run30.py --part a2 &&
    python3 run30.py --part b &&
    python3 aggregate30.py &&
    python3 plot30.py &&
    python3 build_interactive.py
  '
```

Idempotent -- `run_one()` skips any cell whose `stdout.txt` already shows a finished run, so
safe to resume after an interruption.

## Results

**Complete: 1,020 runs, 0 failures** (Part A1 336, Part A2 288, Part B 384).

**The freeze-gate hypothesis was only half right -- and the real answer is more interesting
than "the bug is fixed".**

**Part A (degradation, no hard kill): `rto_per_host` is 0 at every severity n >= 1, for every
B and both dual-window arms** -- not just `freeze_entries`/`freeze_us`, as originally expected.
With real packet trimming, an overflowing queue strips the payload and fast-signals via ECN
instead of silently dropping, so a sustained 50% link slowdown produces heavy ECN marking
(`ecn_per_host` > 200 at n=32) but **never times out**. There is nothing left for the RTO-gated
freeze mechanism to catch -- it correctly never engages, not because it's broken, but because
trimming removes the RTOs it depends on. This is the opposite conclusion from the original
exp30 (where `-disable_trim` produced real RTOs that the RTT-bound gate then suppressed) --
here, freeze is moot by design, not blocked by a flag.

**Part B (static real kill, the harder case): freeze-on-RTO fires correctly at every F >= 1,
for every arm including `reps_b8_dual` and `reps_b8_dual_cap`.** `freeze_entries_per_host`
≈ 1.0 and `freeze_us_mean` > 0 starting at F=1, confirming the original hypothesis for the one
case where it actually applies: when a link is fully, permanently dead (not just slow), RTOs
still happen under trimming, and the (now-unconditional) freeze gate catches every one of
them -- dual-window arms included. This is the clean confirmation the `-log_dual_cwnd`-request
was chasing.

**B is still not resolvable on FCT almost everywhere** -- same structural finding as the
original exp30: Part A1/A2 show no CI-separated B ordering at any severity/ratio tested (both
sizes); Part B resolves only at the healthy anchor and a couple of scattered points, the same
narrow-exception pattern as the trim-disabled run. `reps_b1` still gets stuck past `-end` at
high F (16/24/31) in both sizes under trimming too -- that structural issue is independent of
trim mode.

**Takeaway:** trimming changes *which* mechanism handles congestion (ECN vs. RTO-triggered
freeze), not whether B matters -- it still doesn't, on FCT. The freeze-on-RTO path for
dual-window arms works correctly whenever there's an RTO to respond to; this experiment just
revealed that "whenever" is a much narrower window under trimming than exp30's `-disable_trim`
run implied.

Full data: `data/{fct,diagnostics,resolvable}.csv`; interactive dashboard:
`plots/interactive.html`; static plots: `plots/*.png`; raw runs: `runs.tar.gz` (82 MB).
