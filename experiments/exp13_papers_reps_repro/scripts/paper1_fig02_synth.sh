#!/usr/bin/env bash
# Paper 1 Fig 2 (left): Synthetic benchmarks — Speedup vs ECMP
# Incast 8:1 / Permutation / Tornado at {4, 8, 16} MiB.
# REPS-only scope: we run REPS (freezing) + ECMP (for ratio denominator).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib_common.sh"

LBS="freezing ecmp"
SIZES="4MB 8MB 16MB"
SEEDS="42 43 44"

for size in $SIZES; do
    for s in $SEEDS; do
        for lb in $LBS; do
            run_p1 fig02_synth "$lb" "$s" "$CM_DIR/perm_128n_128c_${size}_s${s}.cm"
            run_p1 fig02_synth "$lb" "$s" "$CM_DIR/incast_n128_d8_${size}_s${s}.cm"
            run_p1 fig02_synth "$lb" "$s" "$CM_DIR/tornado_n128_${size}_s${s}.cm"
        done
    done
done

echo "[done] fig02_synth"
