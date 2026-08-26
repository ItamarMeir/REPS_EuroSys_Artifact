#!/usr/bin/env bash
# Paper 1 Fig 8: Extreme failures — Max FCT vs % failed cables.
# 5 sev levels (10/20/30/40/50 %) × workload (16 MB perm) × REPS+OPS × 3 seeds.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib_common.sh"

FAIL_DIR="$REPO_ROOT/htsim/sim/failures_input"
LBS="freezing oblivious"
SEVS="10 20 30 40 50"
SEEDS="42 43 44"

for sev in $SEVS; do
    mode_file="$FAIL_DIR/${sev}_percent_failed_cables.txt"
    if [[ ! -f "$mode_file" ]]; then
        echo "WARN: missing $mode_file"
        continue
    fi
    for s in $SEEDS; do
        wl="$CM_DIR/perm_128n_128c_16MB_s${s}.cm"
        for lb in $LBS; do
            run_p1 "fig08_sev${sev}" "$lb" "$s" "$wl" \
                -failures_input "$mode_file"
        done
    done
done

echo "[done] fig08_extreme"
