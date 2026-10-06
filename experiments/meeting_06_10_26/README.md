# meeting_06_10_26 - buffer-size claims and experiments (planned)

Source meeting: 2026-10-06 (Itamar Meir, Gabriel Skalosub, Chen Avin). Transcript-based summary in `plans/meeting_summary_and_findings.md`.

## Status

Planning only. No new simulations have run. Each experiment folder's `data/`, `plots/` and `scripts/` are empty placeholders. Results land here as each experiment finishes, following the layout in `experiments/RUNNING_EXPERIMENTS.md`.

## Layout

Each experiment has its own folder with `PLAN.md`, `data/`, `plots/`, `scripts/`. The general plan and meeting findings are in `plans/`.

| Folder | Experiment | Plan |
|---|---|---|
| `C1/` | Claim 1: at backlog only 1-2 valid EVs, so B>2 does not matter | `C1/PLAN.md` |
| `C2/` | Claim 2: in Freezing Mode a larger B drains slower; valid/stale/random split | `C2/PLAN.md` |
| `C3/` | B up to 256; scaling; 32-path caveat | `C3/PLAN.md` |
| `C4/` | Does claim 1 hold without constant backlog (bursty sender) | `C4/PLAN.md` |
| `T1/` | Sanity: FCT roughly proportional to lost bandwidth | `T1/PLAN.md` |
| `T2/` | Speed-of-Light oracle: scenario-dependent rule, implementation | `T2/PLAN.md` |
| `plans/` | `00_general_plan.md` (table, decided vs discussed, shared metrics); `meeting_summary_and_findings.md` | - |

## Existing evidence reused (not copied here)

- exp30 Part A, trim off: freeze runs under congested degradation (`exp30_concentrated_path_loss/runs/`). Baseline for C2 and T1.
- exp30 Part B, dead links: dead-path freeze and stuck-flow counts. Baseline for C2 and T2 verification.
- exp30_packet_trimming_en: trim on, no RTOs under congestion.
- exp28, exp29: static and transient failure background.
- Event viewer: `experiments/tools/reps_event_viewer.py` (buffer content runtime view, reused for C1 slow-motion).

## Open decisions

1. Shared research repo (no code, text/refs/figures): hosting and collaborator handles. Not created.
2. Whether the oracle sees the failure schedule in advance or only current state at send time (T2).
