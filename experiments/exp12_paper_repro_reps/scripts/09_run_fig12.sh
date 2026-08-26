#!/usr/bin/env bash
# Fig 12: MSwift percentile sweep (P10, P50=median, P90) on baseline workload
# Only MSwift; 3 percentile variants × 3 seeds = 9 runs
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib_common.sh"

PCTS="10 50 90"

for pct in $PCTS; do
    for seed in $SEEDS; do
        run_sim_pct "fig12" "mswift" "$seed" "$WL_DIR/paper_baseline_s${seed}.cm" "$pct"
    done
done
echo "[fig12] Done."
