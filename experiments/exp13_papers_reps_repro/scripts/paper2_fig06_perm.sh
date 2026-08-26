#!/usr/bin/env bash
# Paper 2 Fig 6: Pure permutation — 128 × 8 MB sprayed, no ECMP.
# 4 CCAs (Swift dropped from Fig 4 onwards) × 3 seeds.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib_common.sh"

for s in $SEEDS; do
    tm="$CM_DIR/perm_128n_128c_8MB_s${s}.cm"
    for cca in $CCAS_P2_OTHER; do
        run_p2 fig06 "$cca" "$s" "$tm"
    done
done
echo "[done] paper2_fig06"
