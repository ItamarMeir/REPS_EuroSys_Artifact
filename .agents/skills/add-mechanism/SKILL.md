---
name: add-mechanism
description: Implement a new CLI-gated mechanism, algorithm, CC/LB, or logging in htsim/sim/, or change existing behavior; includes mandatory validation and doc updates.
---

Use for any change under `htsim/sim/`. Steps run in order; step 4 is mandatory.

0. **Baseline first.** Before the first edit, run Tier 0 of skill `validate-mechanism` (build and store a pre-change `htsim_uec`).
1. **Design.** Write the expected behavior and a theory-derived prediction (see `validate-mechanism` Tier 2). Gate behind a CLI flag. Additions and wraps only; never delete original lines. Hard-error at startup for invalid or mutually exclusive flag combos. Any `-sender_cc_only` use needs `-disable_tor_ecn`. Read the nearest sections of `experiments/MODIFICATIONS.md` (`grep -n '^### `\[' experiments/MODIFICATIONS.md`) and reuse existing patterns.
2. **Code.** `// ===== ADDED (<name>) =====` banner at every modification site (`// ===== FIX (<name>) =====` for fixes). CLI parsing in `htsim/sim/datacenter/main_uec.cpp`. Mechanism code mostly in `htsim/sim/uec.cpp` / `uec.h`.
3. **Build in Docker** (skill `build-htsim`; `make clean` first).
4. **MANDATORY: invoke skill `validate-mechanism` and complete Tiers 1-5.** Do not skip, shorten, or defer it, and do not write the docs as "done" before it passes.
5. **Docs.**
   - `experiments/MODIFICATIONS.md`: a new `### [ADDED: <name>]` section (gate flag, file / what / gate table, design notes, and the **Verification** subsection from step 4). Use `[FIX: <name>]` with date and banner when changing existing behavior without a new flag. Update the existing section when extending a mechanism. No entry for experiment scripts or analysis code outside `htsim/sim/`.
   - ARCHITECTURE doc under `experiments/` for a new mechanism, linked from the section.
   - `PROVENANCE.md` only if you add top-level files. Lineage row in `experiments/README.md` if an experiment uses the mechanism.
6. **Done** = docs written, Verification subsection present, `validate-mechanism` Tiers 1 and 2 passing. The final report states which checks ran, their results, and which were N/A and why.
