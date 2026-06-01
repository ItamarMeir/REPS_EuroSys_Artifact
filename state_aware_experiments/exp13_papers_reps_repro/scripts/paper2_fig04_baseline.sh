#!/usr/bin/env bash
# Paper 2 Fig 4: Baseline workload — 4 ECMP elephants + 124 sprayed 8 MB.
# 5 CCAs × 3 seeds = 15 runs.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib_common.sh"

for s in $SEEDS; do
    tm="$WL_DIR/paper_baseline_s${s}.cm"
    for cca in $CCAS_P2_FIG4; do
        run_p2 fig04 "$cca" "$s" "$tm"
    done
done
echo "[done] paper2_fig04"
