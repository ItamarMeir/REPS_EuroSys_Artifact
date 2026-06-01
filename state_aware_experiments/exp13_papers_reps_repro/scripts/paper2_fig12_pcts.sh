#!/usr/bin/env bash
# Paper 2 Fig 12: MSwift percentile sweep (P10, P50, P90).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib_common.sh"

for s in $SEEDS; do
    tm="$WL_DIR/paper_baseline_s${s}.cm"
    for pct in 10 50 90; do
        run_p2_pct fig12 "$pct" "$s" "$tm"
    done
done
echo "[done] paper2_fig12"
