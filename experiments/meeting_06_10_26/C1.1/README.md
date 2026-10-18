# C1.1 - is k predictable from serialization time and ACK jitter?

## Question
[C1](../C1/README.md) found that k (valid EVs in the REPS buffer just before a draw) sits at a small stable value when the sender is backlogged. C1.1 asks whether that value can be *predicted* from the link rate: k is a running sum of (clean ACKs per send slot - 1), so it should depend on how often a slot receives two ACKs instead of one. That in turn depends on the send-to-send spacing (the packet serialization time T_s) and on ACK-arrival jitter. The sweep varies T_s by changing the link rate and keeps everything else fixed.

## Setup
- Fabric `fat_tree_1024_1os_2t_{100,200,400,800}g` (same 2-tier shape, link rate varied), tornado, **32 MiB** per flow (>= 40 x BDP at every rate), seed 42, healthy (no failures), REPS = `-load_balancing_algo freezing`, B = 256 (never limiting), `-use_srv6 -paths 32`.
- **Constant congestion control** with cwnd fixed at about 1.25 x the rate's BDP (the empirically found knee at 400G is 127 packets, and the formula reproduces it), so there is no CC reaction noise. Q and the ECN thresholds scale with BDP. `-disable_tor_ecn` is passed here (unlike C1), so the ECN signal is clean.
- Cells (directories under `runs/`, local): `100g_cwnd36`, `200g_cwnd66`, `400g_cwnd127`, `800g_cwnd249` (BDP-scaled), plus fixed-queue checks `100g_fixedq_cwnd{50,90}`, `200g_fixedq_cwnd165`, and a `400g_pathstatic_cwnd127` reference.
- The 100G cell shown is `fixedq_cwnd90` (Q = 101 held at the 400G packet value), because it gave a lower FCT and was not window-bound; the BDP-scaled 100G cwnd 36 cell was dropped to reduce noise. **The 200G cwnd 66 cell is window-bound** (in-flight within about 1 packet of cwnd), so it is not a clean serialization-only reading.
- **path_static reference.** `path_static` pins one path per flow, so there is no REPS buffer and no real k. The page plots a *counterfactual*: the k a buffer would hold if driven by path_static's own ACK stream, computed with the same recursion (k += clean ACK, capped at B; k -= 1 per draw, floored at 0). The recursion was validated against the real measured k at 400G with 0 mismatches over 262,816 rows.

## Results
Distribution of k at send time (post-warmup, ToR0 hosts):

| Cell | k = 1 | k = 2 | k = 3 | k = 4 |
|---|---|---|---|---|
| REPS 100G (fixed Q, cwnd 90) | 7% | 51% | 40% | 1% |
| REPS 200G (cwnd 66, window-bound) | 41% | 46% | 12% | 0.5% |
| REPS 400G (cwnd 127) | 10% | 56% | 33% | 1% |
| REPS 800G (cwnd 249) | 8% | 53% | 38% | 1% |
| path_static 400G (counterfactual) | 0.1% | 10% | **90%** | 0 |

- Across a 8x range of link rate and serialization time (328 ns to 41 ns per packet), the k distribution for non-window-bound cells is almost the same (k mostly 2 or 3, max 4 or 5), so **k is not simply set by serialization time**. The 200G cell differs because it is window-bound.
- The ACK-jitter scale (standard deviation of the per-packet RTT change) is about 520 to 600 ns at every rate, so the ratio jitter / T_s grows from 1.8 (100G) to 12.6 (800G) while k stays put (`data/c11_collapse.csv`). A simple "k is a function of jitter / T_s" model is therefore not supported by this sweep.
- **path_static, which has zero cross-flow collisions, still reconstructs to k = 3 for 90% of draws**, with a_i almost exactly 1. k is an accumulator of deviations from 1 that keeps the level set by an early transient (a reflecting floor at 0 plus one early burst of two clean ACKs) and never drifts back. Real REPS k, in contrast, drifts upward over the flow (mean about 1.9 early to 3.0 late at 400G). The cause of that drift is still open: a growing collision queue is a plausible but unconfirmed explanation (in-flight does not rise monotonically).

## Caveats
- One seed; no confidence intervals.
- The 100G cell uses a different Q policy (fixed Q) than 200G/400G/800G (BDP-scaled), so the rates are not connected by a line and the comparison across rates is indicative only.
- No PLAN or RESULTS file existed; this README and the page's note are the write-up.

## Reproduce
```bash
cd /workspace/experiments/meeting_06_10_26/C1.1/scripts
python3 run_c11.py            # 4 BDP-scaled rates; --fixed-q adds the fixed-queue cells; --anchor runs 400G only
python3 c11_analyze.py        # send-time k, a_i, jitter collapse -> ../data/c11_*.csv
python3 c11_combined.py       # -> ../data/combined.json (rate sweep + path_static counterfactual)
python3 build_combined.py     # -> ../plots/combined.html
```
`c11_pathstatic_compare.py` + `build_pathstatic_compare.py` build the matched-pair page `plots/pathstatic_compare.html` (REPS vs path_static at 400G). `plots/buffer_view_100g_full.html` is a 170 MB interactive buffer view (local only).

## Files
`scripts/common_c11.py` (flags, Q/ECN/cwnd formulas), `run_c11.py`, `c11_analyze.py`, `c11_combined.py`, `c11_pathstatic_compare.py`, `build_*.py`; `data/` (k, a_i histograms, checks, collapse table, JSON payloads); `plots/combined.html` (stacked-bar k and a_i per cell, the main page).
