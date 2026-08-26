#!/usr/bin/env bash
# Fig 6: Pure permutation (128 nodes, 128 flows, 8 MB each)
# CCAs: lswift, mswift, nscc, mnscc  (Swift excluded: paper shows only 4 CCAs in Fig 6)
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib_common.sh"

CCAS_FIG6="lswift mswift nscc mnscc"

for cc in $CCAS_FIG6; do
    for seed in $SEEDS; do
        run_sim "fig6" "$cc" "$seed" "$CM_DIR/perm_128n_128c_8MB_s${seed}.cm"
    done
done
echo "[fig6] Done."
