#!/usr/bin/env bash
# Paper 1 Fig 4: Synthetic benchmarks under asymmetric network conditions.
# Paper §4.3.2: 2% of TOR uplinks downgraded from 400 → 200 Gbps.
# Implemented in htsim via "-failed N" (N degraded links, see fat_tree_topology.cpp:863+).
# For 128 hosts × 16 ToR uplinks, 2% ≈ 4 degraded links.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib_common.sh"

LBS="freezing ecmp"
SIZES="4MB 8MB 16MB"
SEEDS="42 43 44"
NUM_DEGRADED=4  # 2% of ~200 ToR uplinks in fat_tree_128_1os_2t

for size in $SIZES; do
    for s in $SEEDS; do
        for lb in $LBS; do
            run_p1 fig04_asym "$lb" "$s" "$CM_DIR/perm_128n_128c_${size}_s${s}.cm" \
                -failed $NUM_DEGRADED
            run_p1 fig04_asym "$lb" "$s" "$CM_DIR/incast_n128_d8_${size}_s${s}.cm" \
                -failed $NUM_DEGRADED
            run_p1 fig04_asym "$lb" "$s" "$CM_DIR/tornado_n128_${size}_s${s}.cm" \
                -failed $NUM_DEGRADED
        done
    done
done

echo "[done] fig04_asym"
