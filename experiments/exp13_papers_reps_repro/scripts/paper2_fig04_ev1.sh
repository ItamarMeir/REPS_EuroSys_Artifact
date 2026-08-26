#!/usr/bin/env bash
# Phase D variant: Paper 2 Fig 4 with REPS degenerated to EV=1, buffer=1.
# This makes REPS behave like ECMP for every flow — each flow's 5-tuple
# determines a single static path. Hypothesis: this gives Swift the
# persistent ECMP bottleneck links to collapse on, recovering paper's
# Fig 4 Swift = 1308 % regime.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib_common.sh"

run_ev1() {
    local cca="$1" seed="$2" tm="$3"
    local outfile="$DATA_DIR/p2_fig04ev1_${cca}_s${seed}.out"
    if [[ -f "$outfile" ]]; then
        echo "[skip] $(basename "$outfile")" ; return 0
    fi
    echo "[run-ev1] fig04 $cca s$seed"
    # Strip -paths from BASE_P2_128 and replace with -paths 1; also add -reps_buffer_size 1.
    local base="${BASE_P2_128/-paths 65535/-paths 1 -reps_buffer_size 1}"
    # shellcheck disable=SC2086
    (cd "$REPO_ROOT/htsim/sim/datacenter" && \
     "$BIN" $base -sender_cc_algo "$cca" -seed "$seed" -tm "$tm") > "$outfile" 2>&1
}

for s in $SEEDS; do
    tm="$WL_DIR/paper_baseline_s${s}.cm"
    for cca in $CCAS_P2_FIG4; do
        run_ev1 "$cca" "$s" "$tm"
    done
done
echo "[done] paper2_fig04_ev1"
