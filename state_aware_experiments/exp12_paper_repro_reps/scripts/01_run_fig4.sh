#!/usr/bin/env bash
# Fig 4: Baseline workload (4 elephant + 124 sprayed 8 MB flows)
# CCAs: swift, lswift, mswift, nscc, mnscc
# Seeds: 42, 43, 44
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib_common.sh"

for cc in $CCAS; do
    for seed in $SEEDS; do
        run_sim "fig4" "$cc" "$seed" "$WL_DIR/paper_baseline_s${seed}.cm"
    done
done
echo "[fig4] Done."
