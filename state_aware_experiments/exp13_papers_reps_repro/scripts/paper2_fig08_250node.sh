#!/usr/bin/env bash
# Paper 2 Fig 8: 250-node baseline (scaled). Uses BASE_P2_250 (400 G).
# Workload file names checked first — fixes exp12 L3.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib_common.sh"

for s in $SEEDS; do
    tm="$CM_DIR/perm_250n_250c_8MB_s${s}.cm"
    if [[ ! -f "$tm" ]]; then
        echo "WARN: missing $tm" ; continue
    fi
    for cca in $CCAS_P2_OTHER; do
        run_p2 fig08 "$cca" "$s" "$tm"
    done
done
echo "[done] paper2_fig08"
