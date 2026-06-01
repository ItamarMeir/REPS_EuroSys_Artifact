#!/usr/bin/env bash
# Run all Paper 1 figure scripts sequentially. Each is idempotent (skip-if-exists).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

start=$(date +%s)
echo "=== Paper 1 reproduction start: $(date -u +%H:%M:%S) ==="

# Phase 0: workload generation (idempotent)
bash "$SCRIPT_DIR/00_gen_workloads.sh"

# Figures (in execution-cost order; cheapest first)
bash "$SCRIPT_DIR/paper1_fig02_synth.sh"
bash "$SCRIPT_DIR/paper1_fig02_dc.sh"
bash "$SCRIPT_DIR/paper1_fig02_ai.sh"
bash "$SCRIPT_DIR/paper1_fig04_asym.sh"
bash "$SCRIPT_DIR/paper1_fig08_extreme.sh"
bash "$SCRIPT_DIR/paper1_fig06_failures.sh"

end=$(date +%s)
echo "=== Paper 1 reproduction end (elapsed $((end-start))s) ==="
