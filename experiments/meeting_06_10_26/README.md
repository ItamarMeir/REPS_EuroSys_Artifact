# meeting_06_10_26 - buffer-size claims and experiments

Source meeting: 2026-10-06 (Itamar Meir, Gabriel Skalosub, Chen Avin). Transcript-based summary in `plans/meeting_summary_and_findings.md`.

## Status

All items have been run; results sit in each folder's `data/`, `plots/`, `traces/` (gitignored) and `scripts/`.

| Item | State | Where the write-up is |
|---|---|---|
| C1 | Done, 16 MiB. Healthy fabric: the "<= 2 valid EVs" claim does not hold (3-5 valid EVs in 16-18% of backlog rows at B >= 4). With all 32 ToR0 uplinks at 50%: it holds (max 3, 99.98% of rows <= 2). Run for both MPRDMA and NSCC; the NSCC arm was rerun on 2026-10-18 with `-target_q_delay 4.17` (the old 6 us run is kept in `C1/NSCC/_prev_target6us/`). | `C1/RESULTS.md` (numbers there come from the MPRDMA run) and the interactive pages `C1/<CC>/plots/interactive.html` (local, not committed) |
| C1.1 | Done. Is send-time k set by serialization time and ACK jitter? Sweeps link rate 100/200/400/800G plus a path_static counterfactual. No PLAN/RESULTS file; the page is `C1.1/plots/combined.html`. | `C1.1/scripts/` and the page |
| C2 | Data and scripts present; only `PLAN.md` written. Transient partial kill (F=16), B = 1..256. Preliminary reading of `data/c2_drain.csv`: drain time is roughly flat in B (a small drop only at B=256), not growing with B. | `C2/PLAN.md` (no results write-up yet) |
| C3 | Data and scripts present; only `PLAN.md` written. Bursty sender, observed vs predicted valid-EV count at burst boundaries. Preliminary: matches for B=1 (63/63) and mostly for B > 1 (388/486). | `C3/PLAN.md` (no results write-up yet) |
| T1 | Done. FCT scales with lost bandwidth: `path_static` degraded flows run 1.92x (4 MiB) and 1.98x (16 MiB) of baseline vs the 2.0x model. | `T1/RESULTS.md` |

C2 and C3 numbers above are quick readings of the CSVs, not reviewed results.

## Layout

Each experiment has its own folder with `data/`, `plots/`, `scripts/` (and `PLAN.md` / `RESULTS.md` where written). The general plan and meeting findings are in `plans/`; the meeting-to-experiment mapping is in [`../meetings/`](../meetings/).

| Folder | Experiment | Plan |
|---|---|---|
| `C1/` | Claim 1: at backlog only 1-2 valid EVs, so B>2 does not matter | `C1/PLAN.md` |
| `C2/` | Claim 2: in Freezing Mode a larger B drains slower; valid/stale/random split | `C2/PLAN.md` |
| `C3/` | Does claim 1 hold without constant backlog (bursty sender) -- was C4; original C3 ("B up to 256; scaling") deleted, already answered by C2's own B=1..256 ladder | `C3/PLAN.md` |
| `T1/` | Sanity: FCT roughly proportional to lost bandwidth | `T1/PLAN.md` |
| `plans/` | `00_general_plan.md` (table, decided vs discussed, shared metrics); `meeting_summary_and_findings.md` | - |

## Existing evidence reused (not copied here)

- exp30 Part A, trim off: freeze runs under congested degradation (`exp30_concentrated_path_loss/runs/`). Baseline for C2 and T1.
- exp30 Part B, dead links: dead-path freeze and stuck-flow counts. Baseline for C2 and T2 verification.
- exp30_packet_trimming_en: trim on, no RTOs under congestion.
- exp28, exp29: static and transient failure background.
- Event viewer: `experiments/tools/reps_event_viewer.py` (buffer content runtime view, reused for C1 slow-motion).

## Open decisions

1. Shared research repo (no code, text/refs/figures): hosting and collaborator handles. Not created.

## Deleted

- `T2/` (Speed-of-Light oracle as a standing, scenario-dependent LB algorithm) -- deleted 2026-10-11.
  A generic `-load_balancing_algo oracle` covering dead-link / degradation / mixed cases via one
  weighted-round-robin rule was planned but never built. C1/C2/T1 each needed a SoL reference and each
  got a different minimal, scenario-specific construction instead (C1: existing `path_static+constant`
  as-is; C2: a bespoke timed-event ACK-reroute class for its transient partial kill; T1: plain
  `path_static`, sufficient once all of ToR0's uplinks are degraded). No experiment needed the general
  mechanism; building it ahead of a real second use would have been a premature abstraction.
