#!/usr/bin/env bash
# Paper 2 Fig 11: Baseline + 1% random link failures.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib_common.sh"

for s in $SEEDS; do
    tm="$WL_DIR/paper_baseline_s${s}.cm"
    for cca in $CCAS_P2_OTHER; do
        run_p2 fig11 "$cca" "$s" "$tm" -down_ratio 0.01
    done
done
echo "[done] paper2_fig11"
