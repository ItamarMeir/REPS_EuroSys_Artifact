#!/usr/bin/env bash
# Fig 11: Baseline workload + 1% failed links
# CCAs: lswift, mswift, nscc, mnscc
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib_common.sh"

CCAS_FIG11="lswift mswift nscc mnscc"

for cc in $CCAS_FIG11; do
    for seed in $SEEDS; do
        run_sim "fig11" "$cc" "$seed" "$WL_DIR/paper_baseline_s${seed}.cm" \
            "-down_ratio 0.01"
    done
done
echo "[fig11] Done."
