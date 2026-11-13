---
name: validate-mechanism
description: Mandatory verification and validation gate for any change under htsim/sim/ (baseline binary, regression, theory-based known-answer checks, negative controls). Called by add-mechanism.
---

A mechanism that runs without error can still measure the wrong thing (rate-const sender: counted only data, ACKs overloaded the degraded links, "matched" cells showed 49% random EV draws instead of ~1%; found only by a small case with a known answer). Verification and validation are required, not optional. No fixed topology, workload or expected number is prescribed: derive expectations from theory for the mechanism at hand.

Results go into a **Verification** subsection of the mechanism's section in `experiments/MODIFICATIONS.md`: each check run, how, result, or an explicit "N/A because ...".

## Tier 0 — baseline binary (BEFORE the first edit)

No stored baseline exists, and after you edit and rebuild nothing is left to diff against.
- In Docker (skill `build-htsim`): `make clean` in `htsim/sim/` and `htsim/sim/datacenter/`, build at current HEAD, copy `htsim_uec` to `.baseline/htsim_uec.pre-<name>` (gitignored; keep it outside the build dirs, which get rebuilt).
- Forgot? Build HEAD from a `git worktree` in Docker.
- Never trust a diff against a binary built without `make clean` (stale `.o` files can fake a regression or hide one).

## Tier 1 — verification (always): did I break anything, is it deterministic

Use `experiments/tools/regress.sh <old> <new> -- <htsim_uec args>` (old vs new flow-finish lines + determinism rerun). Choose cells that exercise the code path you touched, not just any cell.
- Flag absent: flow-finish lines byte-identical to the baseline. If you added always-compiled counters that change the finish line, say so explicitly and show everything else is unchanged.
- Determinism: same command twice gives identical output.
- Where the new path must reduce to a stock path at a trivial setting, require byte-identical output there too.
- Configuration proven from the output, not the command line: no `enable on tor downlink 1`, expected LB line, flow count; invalid or mutually exclusive flag combos hard-error at startup.

## Tier 2 — validation by theory (always): does it do the right thing

1. Define the quantity physically and list every consumer of it (data, retransmissions, ACKs, control packets).
2. **Write the prediction before running**, derived from first principles (serialization time, rate/capacity arithmetic, counting arguments). Show the arithmetic in the entry draft.
3. Run the smallest case whose answer is derivable in closed form (fewest flows/paths, healthy fabric). Choose it for the mechanism at hand.
4. Inputs you cannot derive (base RTT, header overhead, queue sizes, packet size): first look in previous experiments' READMEs and outputs; if absent, run a small simulation to measure them. Record where each number came from.
5. Probe the boundary: sweep below, at and above any threshold the theory predicts. A cliff exactly at nominal capacity means an accounting bug, not physics.
6. Check theoretical twins: cells that theory says are equivalent must look alike.
7. A missed prediction is reported and investigated, not explained away.

## Tier 2b — smoke tests with obvious answers (always, one per flag / mode)

Run the smallest sim whose result is obvious from the definition (one flow, one message, 2-8 EVs, healthy or fully degraded fabric) and measure the quantity the mechanism changes (distribution of draws or paths, per-link packet counts from `-log_queue_stats`, a trim/ECN rate, a closed-form FCT). Write the expected value and its tolerance (binomial CI, chi-square) BEFORE running; the extreme settings (all weight on one class, none on it, inverted) must give the extreme answer. Also run cheap sanity checks on every full cell (flow count, 0 RTOs, queue speeds, `SRv6 source routing enabled` line, trace identities). Results go into the Verification subsection.

## Tier 3 — additional techniques (as applicable)

Look at `experiments/tools/README.md` and the nearest `experiments/MODIFICATIONS.md` entries for existing tools before writing new ones. Techniques with precedent in this repo: self-check invariants or counters printed by the sim; event-trace verification (`experiments/tools/reps_event_viewer.py --verify`); an independent reference implementation that replays a trace and checks each decision; exact-identity replays computed from the event stream; identity reductions to a stock path.

## Tier 4 — negative control (for every new check or invariant)

Deliberately break the code or corrupt the trace and show the check fails. A check that cannot fail proves nothing.

## Tier 5 — isolate and report

At least 3 seeds; single-variable controls measured in the same run as the metric; write "consistent with" unless an intervention shows causation. Suspect the analysis too (start/drain transients, flow-tail effects, before/after off-by-one, symmetric CI whiskers below 0 for counts). When an explanation is disproved, remove it from every README, page and plot note.

## Done

The Verification subsection exists, lists every check, and Tiers 1 and 2 pass. If they do not, the work is not done: report what failed.
