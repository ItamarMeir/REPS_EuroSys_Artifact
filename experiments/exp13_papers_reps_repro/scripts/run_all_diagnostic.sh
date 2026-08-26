#!/usr/bin/env bash
# Phase D diagnostic: 4 cells × 4 CCAs × 3 seeds = 48 runs (~25 min).
# All use paper_baseline_s{42,43,44}.cm. Output goes into diag_* subset of data/.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib_common.sh"

# Diagnostic-specific run helper. Saves under p2_diag_<tag>_<cca>_s<seed>.out.
run_diag() {
    local tag="$1" cca="$2" seed="$3" tm="$4"
    shift 4
    local extra="$*"
    local outfile="$DATA_DIR/p2_diag_${tag}_${cca}_s${seed}.out"
    if [[ -f "$outfile" ]]; then
        echo "[skip] $(basename "$outfile")" ; return 0
    fi
    echo "[diag] $tag $cca s$seed"
    # shellcheck disable=SC2086
    (cd "$REPO_ROOT/htsim/sim/datacenter" && \
     "$BIN" $BASE_P2_128 -sender_cc_algo "$cca" -seed "$seed" -tm "$tm" $extra) \
        > "$outfile" 2>&1
}

CCAS="swift lswift mswift mnscc"

# D2-baseline — repeat Fig 4 with the new MD-fire counter on
for s in $SEEDS; do
    tm="$WL_DIR/paper_baseline_s${s}.cm"
    for cca in $CCAS; do
        run_diag baseline "$cca" "$s" "$tm"
    done
done

# D2-beta-paper — set β = 0.5 (matches paper Table I "mm")
for s in $SEEDS; do
    tm="$WL_DIR/paper_baseline_s${s}.cm"
    for cca in $CCAS; do
        run_diag beta_paper "$cca" "$s" "$tm" -swift_beta 0.5
    done
done

# D2-tightq — drop target_q_delay to 0.5 µs
for s in $SEEDS; do
    tm="$WL_DIR/paper_baseline_s${s}.cm"
    for cca in $CCAS; do
        run_diag tightq "$cca" "$s" "$tm" -target_q_delay 0.5
    done
done

# D2-ops — swap REPS LB for OPS (oblivious)
# Override -load_balancing_algo via -extra arg (placed after BASE_P2_128 so it wins).
for s in $SEEDS; do
    tm="$WL_DIR/paper_baseline_s${s}.cm"
    for cca in $CCAS; do
        run_diag ops "$cca" "$s" "$tm" -load_balancing_algo oblivious
    done
done

echo "[done] diagnostic"
