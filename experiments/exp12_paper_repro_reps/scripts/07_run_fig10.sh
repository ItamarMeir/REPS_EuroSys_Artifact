#!/usr/bin/env bash
# Fig 10: Baseline with 8 elephant flows (instead of 4)
# CCAs: lswift, mswift, nscc, mnscc
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib_common.sh"

CCAS_FIG10="lswift mswift nscc mnscc"

for cc in $CCAS_FIG10; do
    for seed in $SEEDS; do
        run_sim "fig10" "$cc" "$seed" "$WL_DIR/paper_baseline_8ecmp_s${seed}.cm"
    done
done
echo "[fig10] Done."
