#!/usr/bin/env bash
# Paper 2 Fig 14: Incast 32 → 1, 8 MB each.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib_common.sh"

for s in $SEEDS; do
    tm="$WL_DIR/paper_incast32_s${s}.cm"
    for cca in $CCAS_P2_OTHER; do
        run_p2 fig14 "$cca" "$s" "$tm"
    done
done
echo "[done] paper2_fig14"
