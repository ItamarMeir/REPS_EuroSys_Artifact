#!/usr/bin/env bash
# Paper 1 Fig 4 — 3-tier variant.
# Same workload matrix as paper1_fig04_asym.sh (2 % of ToR uplinks downgraded
# from 400 → 200 Gbps via `-failed 4`) but on the 128n 3-tier topology.
# Both topologies have 128 ToR uplinks (16×8 vs 32×4), so -failed 4 ≈ 3 %
# applies cleanly to both. Fig tag is "fig04_asym3t" so output files don't
# collide with the 2-tier set.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib_common.sh"

LBS="freezing ecmp"
SIZES="4MB 8MB 16MB"
SEEDS="42 43 44"
NUM_DEGRADED=4

for size in $SIZES; do
    for s in $SEEDS; do
        for lb in $LBS; do
            run_p1_3t fig04_asym3t "$lb" "$s" "$CM_DIR/perm_128n_128c_${size}_s${s}.cm" \
                -failed $NUM_DEGRADED
            run_p1_3t fig04_asym3t "$lb" "$s" "$CM_DIR/incast_n128_d8_${size}_s${s}.cm" \
                -failed $NUM_DEGRADED
            run_p1_3t fig04_asym3t "$lb" "$s" "$CM_DIR/tornado_n128_${size}_s${s}.cm" \
                -failed $NUM_DEGRADED
        done
    done
done

echo "[done] fig04_asym3t"
