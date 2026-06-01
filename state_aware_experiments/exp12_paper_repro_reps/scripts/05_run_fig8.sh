#!/usr/bin/env bash
# Fig 8: 250-node permutation (400 Gbps topology, 250 flows, 8 MB each)
# Note: only seed 42 matrix available (perm_250n_250c_8MB_s42.cm).
#       Use seed 42 only unless additional CMs are generated.
# CCAs: lswift, mswift, nscc, mnscc
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib_common.sh"

CCAS_FIG8="lswift mswift nscc mnscc"

for cc in $CCAS_FIG8; do
    # Only seed 42 available for 250-node 8 MB
    run_sim "fig8" "$cc" "42" "$CM_DIR/perm_250n_250c_8MB_s42.cm"
done
echo "[fig8] Done. NOTE: only seed 42 available for 250-node 8MB matrix."
