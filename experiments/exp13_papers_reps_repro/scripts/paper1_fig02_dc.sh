#!/usr/bin/env bash
# Paper 1 Fig 2 (middle): Datacenter traces — Avg FCT vs load level.
# Paper uses WebSearch + Hadoop CDF traces. Available loads: 30/60/90 % (paper plots 40/60/80/100 %; ours overlap at 60).
# We run REPS only (the figure shows multiple LB curves; REPS-only scope produces the REPS line).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib_common.sh"

LBS="freezing"
TRACES="websearch hadoop"
LOADS="30 60 90"
SEEDS="42 43 44"

for trace in $TRACES; do
    for load in $LOADS; do
        for s in $SEEDS; do
            for lb in $LBS; do
                run_p1 fig02_dc "$lb" "$s" "$CM_DIR/cdf_${trace}_l${load}_s${s}.cm"
            done
        done
    done
done

echo "[done] fig02_dc"
