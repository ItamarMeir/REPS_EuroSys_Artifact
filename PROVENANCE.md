# PROVENANCE.md — what's original vs what's ours (repo-wide)

Two-layer provenance model:
- **This file** — repo-wide map: which top-level directories/files are the paper's original
  artifact vs our additions.
- [`state_aware_experiments/MODIFICATIONS.md`](state_aware_experiments/MODIFICATIONS.md) —
  line-level detail *within* `htsim/sim/` (every added mechanism, gate flag, and file/line
  location). Don't duplicate that detail here — link to it.

Baseline is the repo's first commit, `e19b8d0` ("first commit", Tommaso Bonato,
2025-09-04) — the paper's original, unmodified artifact as published. Everything landed in
later commits is ours.

---

## Top-level map

| Path | Status | Note |
|---|---|---|
| `htsim/` | `[ORIGINAL]` + additions | See "`htsim/` breakdown" below |
| `artifact_scripts/` | `[ORIGINAL]` | Paper's figure-reproduction scripts. Never modify. |
| `artifact_results/` | `[ORIGINAL]` | Paper's original results. Never modify. |
| `traffic_gen/` | `[ORIGINAL]` | Connection-matrix generator, not used by our experiments. |
| `.github/workflows/c-cpp.yml` | `[ORIGINAL, modified]` | Removed a `make test` step (no `test` Makefile target exists) — CI fix, not a feature. |
| `README.md`, `LICENSE-Transport-WG.txt`, `.gitignore`, `reps_pkg_install.sh`, `requirements.txt` | `[ORIGINAL]` | Present in `e19b8d0`, untouched in kind (may have received minor edits since). |
| `state_aware_experiments/` | `[ADDED]` | Our extension code's experiment harness + all findings. |
| `docs/assets/*.svg` | `[ADDED]` (commit `fd44085`) | Diagrams for `HTSIM_BEGINNERS_GUIDE.md`. |
| `htsim/README.md` | `[ORIGINAL]` (commit `0bd00a6`, author Tommaso Bonato) | Paper author's own htsim fork-lineage doc (Handley → Raiciu/MPTCP → NDP → Correct Networks/Broadcom/EQDS → Ultra Ethernet Consortium → REPS paper), landed 2nd commit, not the 1st — not written by us. |
| `CLAUDE.md`, `CLAUDE.original.md` | `[ADDED]` | This project's agent-guidance docs. |
| `AGENTS.md` | `[ADDED]` | Agent-guidance doc. |
| `HTSIM_BEGINNERS_GUIDE.md` | `[ADDED]` | Fact-checked beginner's guide to the simulator internals. |
| `code-review.md` | `[ADDED]` | Our code-review notes. |
| `Dockerfile`, `docker-compose.yml` | `[ADDED]` | Containerized dev/build environment. |
| `.claude/` | `[ADDED]` | Claude Code project settings. |
| `PROVENANCE.md` (this file) | `[ADDED]` | — |

Not part of the tracked repo (gitignored local scratch — excluded from original-vs-ours
classification entirely): `papers/` (reference PDFs), `output_metrics/globalInfo.csv`,
`.history/` (editor backups).

---

## `htsim/` breakdown

- `htsim/older_scripts/` — `[ORIGINAL]`, untouched.
- `htsim/sim/` — original REPS-paper simulator, with our additions layered in. Full line-level
  inventory: [`state_aware_experiments/MODIFICATIONS.md`](state_aware_experiments/MODIFICATIONS.md).
  Rule of thumb: everything *not* listed there is original/untouched — no original lines were
  ever deleted, every modification is an addition or a wrap (see CLAUDE.md "What has NOT been
  changed").
- `htsim/README.md` — `[ORIGINAL]`, authored by Tommaso Bonato (commit `0bd00a6`, 2025-09-20) —
  landed after the first commit but still paper-author content, not ours. Documents the pre-REPS
  fork lineage (Handley → Raiciu/MPTCP → NDP → Correct Networks/Broadcom/EQDS → Ultra Ethernet
  Consortium) and, in its "Main Changes Introduced by the REPS paper" section, lists
  `uec.cpp`/`uec.h`, `main_uec.cpp`, `fat_tree_topology.*`, `buffer_reps.*`, `failuregenerator.*`
  as *the paper's own* additions over pre-REPS htsim — one layer further back than our own
  additions on top of the REPS paper. Names `buffer_reps.*` as implementing "its circular
  buffer" — no mention of an unbounded variant; corroborates the paper's bounded-8-slot design
  (see `state_aware_experiments/README.md` verification note).

---

## How to verify

```bash
# Original top-level dirs as they shipped in the first commit
git ls-tree -d --name-only e19b8d0

# History of any specific path — empty/short output near the start = original; a later
# first-touch commit = added or modified by us
git log --oneline -- <path>

# Diff any original file against its first-commit version
git diff e19b8d0 -- <path>
```
