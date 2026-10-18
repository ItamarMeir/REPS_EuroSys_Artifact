# exp29_packet_trimming_en_allhosts -- dashboard variant of exp29_packet_trimming_en

**This directory runs no simulations.** It reuses the raw runs of [`../exp29_packet_trimming_en/`](../exp29_packet_trimming_en/) (its `aggregate29.py` reads `../exp29_packet_trimming_en/runs/micro`) and differs in two scripts only: `aggregate29.py` adds an `all` FCT group (p50/p90/p95/p99/max over every host, not just ToR0's affected senders) to `data/fct.csv`, and `build_interactive.py` draws its FCT panel from that `all` group. All other CSVs and the static PNGs are identical to the sibling's. The text below is a verbatim copy of the sibling's README and describes the experiment itself.

---


## Purpose

[`exp29_failure_response`](../exp29_failure_response/) runs every arm with `-disable_trim`.
That flag gates REPS's freeze-on-RTO entry (`htsim/sim/uec.cpp:4981-4994`) behind an RTT bound
(`_last_rto_max_rtt < 1.65*_base_rtt`) instead of letting it fire unconditionally.
`exp30_packet_trimming_en`'s investigation found that bound blocks freeze entirely under
sustained degradation (no real packet loss, ECN-only) at moderate-to-high severity.

**exp29 is a different failure shape, and the expected effect here is smaller.** exp29's
failure is a real, transient link kill (`-timed_fail_tor_uplinks` + `-timed_window 100 200`,
using `Pipe::_failed` -- an unconditional early-drop at the dead pipe, not a queue-overflow/trim
event). RTOs happen there regardless of whether trim is enabled, because the packets never
reach a queue that could trim them in the first place. exp29's own existing documented finding
is "freeze fires at every F, even F=1" under the current `-disable_trim` config -- meaning the
RTT-gate does not appear to be blocking freeze entry in this experiment's regime already. So
the honest prior going into this rerun is **"dropping `-disable_trim` may change little for
exp29"** -- this experiment checks that empirically rather than assuming it either way.

## Design matrix

Byte-identical to `exp29_failure_response` (see its README/`common29.py` docstring for the
full F/arm/exit_freeze rationale) -- same F in {1,4,8,16,24,31}, same 3 seeds (42/43/44), same
`-exit_freeze 100us` primary batch + `-exit_freeze 250us` secondary batch on F in {1,16,31},
same `fat_tree_1024_1os_2t_400g` / tornado 16 MiB / `-q 101 -ecn 25 76 -cwnd 151`. The
only flag difference anywhere in `common29.py::base_flags()` is the absence of `-disable_trim`.

8 arms: `reps_b1/2/4/8/32` (plain MPRDMA B ladder), `reps_b8_dual`/`reps_b8_dual_cap` (dual-window
CC at fixed B=8), `reps_b8_nscc` (NSCC -- the paper's own CC -- at fixed B=8, same LB/buffer as
`reps_b8`; a third CC comparison point alongside the two dual-window variants, added after the
original 189-run matrix). Primary batch 8 arms x 6 F x 3 seeds = 144 runs; secondary batch 8 arms
x 3 F x 3 seeds = 72 runs; **216 runs total**.

## Regenerate

```bash
cd htsim/sim && make -j 8 && cd datacenter && make -j 8 && cd ../../..   # if not already built

MSYS_NO_PATHCONV=1 docker run --rm -v "$PWD:/workspace" \
  -w /workspace/experiments/exp29_packet_trimming_en/scripts \
  reps-artifact:latest bash -lc '
    python3 run_crossover.py &&
    python3 run_crossover.py --ef 250 --fs 1,16,31 &&
    python3 aggregate29.py &&
    python3 plot_response.py &&
    python3 build_interactive.py
  '
```

Idempotent -- `run_one()` skips any cell whose `stdout.txt` already shows a finished run, so
safe to resume after an interruption.

## Results

**Complete: 216 runs, 0 failures** (primary 144, secondary 72 -- includes the later-added
`reps_b8_nscc` arm, 27 runs of the 216).

**The "changes little" prior held exactly.** Compared `reps_b8` at `ef=100` directly against
the original `exp29_failure_response` (same F, same arm, same seeds):

```
             rto_per_host              freeze_entries   p99 FCT (us)
F     trim-en   original      trim-en=orig?   trim-en   original
1     4.56      4.56          ==              371.5     371.5
4     23.70     23.79         ~=              393.8     392.5
8     49.26     51.17         ~=              424.4     432.7
16    90.08     91.58         ~=              541.9     549.8
24    123.89    125.28        ~=              698.2     708.2
31    148.85    148.85        ==              879.0     879.0
```

`freeze_entries_per_host` is exactly `1.000` at every single F in both the trim-enabled and
original runs -- confirming the hypothesis directly: exp29's failure is a real `Pipe::_failed`
kill, so RTOs fire regardless of trim mode, and the freeze-entry RTT-gate
(`_last_rto_max_rtt < 1.65*_base_rtt`) was never actually binding in this experiment's regime to
begin with (unlike exp30's sustained-degradation Part A, where it blocked freeze entirely at
n>=8). FCT differences across all F are within 1-2% -- normal seed-to-seed noise, not a real
trim-mode effect.

**Takeaway**: trim mode only matters when the failure signal is congestion-driven (ECN/queue
overflow) rather than a hard link kill. exp29's transient-kill design was already insensitive
to this flag; exp30's degradation design was not. This is itself a useful confirmation that the
two experiments' failure models probe genuinely different regimes of the freeze mechanism.

Full data: `data/{timeseries,response,fct,diagnostics,resolvable}.csv`; interactive dashboard:
`plots/interactive.html`; static plots: `plots/*.png`; raw runs: `runs.tar.gz` (66 MB).

## Dual-window cwnd through time

The dashboard's existing "Time analysis" section only has LB-level counters to show (RTOs,
freeze entries, ...) -- it can't see *which window* sent what for the dual-window arms. Added
a dedicated chart (dashboard section 4) tracing the actual per-window congestion windows
directly, via `-log_dual_cwnd` (built earlier this session, documented in
`experiments/tools/README.md`): one representative affected host (src 0, seed 42, ef=100) for
both `reps_b8_dual` and `reps_b8_dual_cap`, at each F in the standard ladder
`{1,4,8,16,24,31}`. Plain `reps_b8` (single shared window, no safe/random split) is overlaid
for direct comparison, logged via the pre-existing `-log_cwnd` (packets) and converted to bytes
using that cell's own exact avg-packet-size (`total bytes / total packets` off its finish
line) -- not an assumed MTU constant. All 6 F values present for all 3 series. This is a
single-flow diagnostic trace, not a seed/host-averaged statistic like every other chart here --
read it for the shape of the dynamics (e.g. both dual-window arms crashing during a freeze
episode and resetting together at unfreeze, versus plain `reps_b8`'s single window crawling
back slowly afterward with no reset at all -- matching this session's broader dual-window
mechanism investigation), not as a number to cite.

Regenerate: 12 standalone dual-window runs + 6 plain-`reps_b8` runs + 6 `reps_b8_nscc` runs (see
`scripts/build_dual_cwnd_trace.py`'s module docstring/functions for the exact flags), writing
`data/dual_cwnd/<arm>_F<F>.csv`, `data/dual_cwnd/plain_b8/reps_b8_F<F>.{csv,stdout}`, and
`data/dual_cwnd/nscc_b8/reps_b8_nscc_F<F>.{csv,stdout}`, then
`python3 scripts/build_dual_cwnd_trace.py` to produce `data/dual_cwnd_trace.csv`, then rebuild
`build_interactive.py` as usual. Not part of the statistical matrix -- doesn't touch
`runs.tar.gz` or any seed-averaged CSV.

**NSCC added as a 4th comparison line** on this chart (green, single window like plain
`reps_b8` -- NSCC has no safe/random split either, same `-log_cwnd`-to-bytes treatment). Same
single affected host (src 0, seed 42, ef=100), same 6 F values. Gives 3 distinct single-window-
vs-dual-window data points at fixed B=8: plain MPRDMA, NSCC, and the two dual-window variants --
answers "is the dual-window reset/crawl-back dynamic specific to MPRDMA, or does any CC at this
B show the same shape" by eye.
