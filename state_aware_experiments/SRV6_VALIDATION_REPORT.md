# SRv6 Implementation + exp21/exp22 Validation Report

**Date:** 2026-06-17
**Scope:** validate the SRv6 source-routing extension (`-use_srv6`) and the artifacts of
exp21 (`exp21_srv6_buffer_sweep_k16_v21/`) and exp22 (`exp22_link_failure_v22/`).

---

## 1. SRv6 contract (recap)

When `-use_srv6` is set, each `UecSrc` does the following for every packet (data and RTX):

1. **Pre-draw the EV** by calling the LB algo's `nextEntropy()` *before* the route is locked.
2. Cache the EV in `_srv6_pending_ev`.
3. Compute `route_path_idx = ev % _paths.size()` and use `_paths[route_path_idx]` as the
   effective route (skipping per-hop ECMP entirely).
4. After the route is locked, when the second normal `nextEntropy()` dispatch would fire,
   return the cached `_srv6_pending_ev` instead — so the LB state machine advances exactly
   once per packet.

`_paths[]` is populated by `get_bidir_paths(src, dst)` at flow setup (in `main_uec.cpp`),
triggered for every flow that uses `-use_srv6`, regardless of the active LB algo.

EV-to-path mapping for K=16 cross-pod flows (audited below):

```
For pod 0 host 0 → pod 8 host 512:
  64 paths, enumerated Agg-major / Core-minor:
    path[k]: src_agg = k/8, core = (k%8)*8 + k/8, dst_agg = 64 + k/8
  EV → path:   path[ev % 64]
```

Code references: `[ADDED: srv6]` entry in `CLAUDE.md`; pre-draw blocks in `htsim/sim/uec.cpp`
around `sendNewPacket`/`sendRtxPacket`; field `_srv6_pending_ev` in `htsim/sim/uec.h`;
CLI parsing + path-population guard in `htsim/sim/datacenter/main_uec.cpp`.

---

## 2. Implementation audit

| Item | Status |
|------|--------|
| Pre-draw block in `sendNewPacket` and `sendRtxPacket` | identical, EV drawn once per packet |
| `_srv6_pending_ev` cache + post-route dispatch guard | prevents double-advance of LB state |
| `route_path_idx = ev % _paths.size()` | correct; defensive double-modulo is benign |
| Path-population condition in `main_uec.cpp` | triggers `get_bidir_paths` for every `-use_srv6` flow |
| Empty-`_paths` fallback | silently uses the original `route` argument; safe but unlogged |
| RTX path of SRv6 | identical to send path; verified by T9 (RTX moves to surviving path) |

**No code bugs found.** The only behavioural surprise — an empty `_paths` falling back to
the default route argument without logging — is gated upstream by the `main_uec.cpp` path
population condition. Adding a debug warning would harden future refactors but is not
required for correctness.

---

## 3. Test coverage

### 3.1 K=4 test suite (existing — `test_srv6/scripts/run_tests.sh`)

| # | Test | What it pins down |
|---|------|-------------------|
| T0 | FREEZING + SRv6 tornado smoke | binary doesn't crash; flows complete |
| T1 | PATH_RR ± SRv6 FCT equality | SRv6 is transparent to PATH_RR |
| T2 | force `npaths=1`, fail predicted link | EV=0 → (agg=0, core=0) at K=4 |
| T3a/b/c | force `npaths=1`, fail off-path link | failing other (agg,core) doesn't disturb EV=0 |
| T4 | 4-path SRv6, fail each path's link in turn | each EV→path mapping correct |
| T5 | SRv6 vs ECMP under same link failure | confirms SRv6 truly pins traffic |
| T6 | ECMP + SRv6 smoke | orthogonality of SRv6 and LB algo |
| T7 | PATH_RANDOM ± SRv6 FCT equality | transparency to PATH_RANDOM |
| T8 | PATH_STATIC ± SRv6 flow count | transparency to PATH_STATIC |
| T9 | 2-path PATH_RR + SRv6 with one failure | RTX state machine re-advances on retransmit |

**Result:** 17/17 individual PASS lines (13 logical tests).

### 3.2 K=16 micro-tests (new — added in this validation)

| # | Test | Pass criterion | Result |
|---|------|----------------|--------|
| **T10** | PATH_RR + SRv6, single flow 0→512, log host 0 buffer | unique `ack_ev` count = 64, range [0,63] | PASS — 64 EVs in [0,63] |
| **T11** | force `npaths=1`, fail `(agg=0, core=0)` | flow STALLS | PASS — no `finished at` |
| **T12** | force `npaths=1`, fail `(agg=24, core=0)` (pod 3, off-path) | flow COMPLETEs with FCT == baseline | PASS — 33.7232 µs == 33.7232 µs |

T11 + T12 together pin the K=16 mapping: T11 proves the formula's *prediction*
(`EV=0 → (agg=0, core=0)`) is the link that actually carries the traffic; T12 proves the
prediction is *specific* — failing a different (agg, core) does not block EV=0.

**Total test suite result: 21/21 PASS** (17 K=4 + 4 K=16). Run:
`bash state_aware_experiments/test_srv6/scripts/run_tests.sh`

---

## 4. exp21 audit (`exp21_srv6_buffer_sweep_k16_v21/`)

| Item | Status |
|------|--------|
| `runs.tar.gz` *.out file count | 60 (54 expected + 6 stray `*128mib*` runs) |
| 1024 flows per 8 MB *.out | confirmed |
| `enable on tor downlink 1` | not present |
| `-disable_tor_ecn` paired with `-sender_cc_only` | yes |
| `-use_srv6` set for all FREEZING / REPS / ECMP runs | yes |
| `exp21_flows.csv` row count | 57,345 (8 MB rows + 128 MiB rows) |
| Plot scripts filter `workload == "8mb"` | yes — plots are correct |
| Per-host buffer logs `buf_*_s42.csv` | 11 files, **seed 42 only** (`*_b1_*`, `*_b2_*`, `*_freezing_b{1..64}_*`, `*_path_static_*`, `*_reps_*`) |

**Notes**

- The 6 stray `*128mib*` files in `runs.tar.gz` are artifacts of a different workload
  campaign that landed in the same `runs/` directory. They are real but irrelevant. The
  aggregator picks them up (hence the mixed-workload `exp21_flows.csv`), but the plot
  scripts correctly filter by `workload == "8mb"`. **Action for anyone re-running
  `aggregate.py`:** be aware the CSV is mixed and filter explicitly.
- Buffer logging was scoped to **seed 42 only** by the run script. This is intentional
  (point-in-time diagnostics for the buffer-dynamics plots), not an omission. exp22 later
  extended this to all 3 seeds.
- Two extra files `buf_b1_nscc_s42.csv` / `buf_b2_nscc_s42.csv` use older naming
  (no `freezing_` prefix). They predate the rename; the standard `buf_freezing_b*` files
  cover the same configurations.

---

## 5. exp22 audit (`exp22_link_failure_v22/`)

| Item | Status |
|------|--------|
| `runs.tar.gz` *.out file count | 54 (9 algos × 2 CCs × 3 seeds) |
| 1024 flows per 8 MB *.out | confirmed for FREEZING / REPS / ECMP / PATH_RR / PATH_RANDOM |
| PATH_STATIC flows per *.out | 926/1024 — **expected** (greedy oracle pins paths at flow setup; 98 flows are assigned through links the failure set later kills) |
| `enable on tor downlink 1` | not present |
| `-fail_link_time 1 1000000000` + 51 `-fail_link_target` flags | deterministic, `random.seed(0)` |
| `exp22_flows.csv` row count | 54,708 (consistent with PATH_STATIC's 588 expected drops) |
| Per-host buffer logs `buf_*_nscc_s{42,43,44}.csv` | 27/27 ✓ (9 algos × 3 seeds) |

**Note on PATH_STATIC stuck flows:** the greedy edge-load oracle assigns each flow's
fixed path at setup, *before* knowing which links will fail. 98/1024 flows land on a
path that traverses one of the 51 failed links. Those flows cannot reroute. This is the
expected and intended behaviour of PATH_STATIC under topology failures — exp22's CC
modes have no mechanism to override the static assignment. The result is informational
(it shows the cost of static routing under failures); it is not a bug.

---

## 6. Known limitations and follow-ups

- **Empty `_paths` is a silent fallback.** If a future LB addition forgets to extend the
  path-population condition in `main_uec.cpp`, SRv6 will silently route via ECMP for that
  algo. A one-line `cerr` warning on first such packet would harden this.
- **exp21 buffer logging is seed-42-only by design.** The exp21 plots only need one seed
  worth of buffer dynamics; the FCT plots use all three seeds via flow CSV. If future
  buffer-dynamics analysis needs cross-seed averaging, the run script would need
  `-log_reps_state` enabled for seeds 43/44.
- **PATH_STATIC under failures** drops 98/1024 flows; this is documented and expected.

---

## 7. Reproduction commands

```bash
# Run the SRv6 test suite (K=4 + K=16)
bash state_aware_experiments/test_srv6/scripts/run_tests.sh

# Inspect the K=16 reachability buffer log
python3 -c "import pandas as pd; df = pd.read_csv('state_aware_experiments/test_srv6/runs/T10_k16_reachability.csv'); print('unique ack_ev:', df['ack_ev'].nunique(), 'range:', df['ack_ev'].min(), '-', df['ack_ev'].max())"
```

Expected: `21/21 tests passed` and `unique ack_ev: 64 range: 0 - 63`.
