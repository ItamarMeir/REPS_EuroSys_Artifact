#!/usr/bin/env bash
# Paper 1 Fig 2 (left) — 3-tier variant.
# Same workload matrix as paper1_fig02_synth.sh but on the 128n 3-tier topology.
# The paper's Fig 2 is ambiguous on tier-count; this companion run lets us
# compare 2-tier vs 3-tier max-FCT speedup ratios.
# Fig tag is "fig02_synth3t" so output files don't collide with the 2-tier set.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib_common.sh"

LBS="freezing ecmp"
SIZES="4MB 8MB 16MB"
SEEDS="42 43 44"

for size in $SIZES; do
    for s in $SEEDS; do
        for lb in $LBS; do
            run_p1_3t fig02_synth3t "$lb" "$s" "$CM_DIR/perm_128n_128c_${size}_s${s}.cm"
            run_p1_3t fig02_synth3t "$lb" "$s" "$CM_DIR/incast_n128_d8_${size}_s${s}.cm"
            run_p1_3t fig02_synth3t "$lb" "$s" "$CM_DIR/tornado_n128_${size}_s${s}.cm"
        done
    done
done

echo "[done] fig02_synth3t"
