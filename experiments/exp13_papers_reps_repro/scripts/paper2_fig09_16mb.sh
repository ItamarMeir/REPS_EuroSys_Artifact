#!/usr/bin/env bash
# Paper 2 Fig 9: Baseline workload with 16 MB messages.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib_common.sh"

for s in $SEEDS; do
    tm="$WL_DIR/paper_baseline_16mb_s${s}.cm"
    for cca in $CCAS_P2_OTHER; do
        run_p2 fig09 "$cca" "$s" "$tm"
    done
done
echo "[done] paper2_fig09"
