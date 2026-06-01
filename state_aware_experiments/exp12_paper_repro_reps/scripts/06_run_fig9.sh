#!/usr/bin/env bash
# Fig 9: Baseline with 16 MB sprayed flows
# CCAs: lswift, mswift, nscc, mnscc
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib_common.sh"

CCAS_FIG9="lswift mswift nscc mnscc"

for cc in $CCAS_FIG9; do
    for seed in $SEEDS; do
        run_sim "fig9" "$cc" "$seed" "$WL_DIR/paper_baseline_16mb_s${seed}.cm"
    done
done
echo "[fig9] Done."
