#!/usr/bin/env bash
# Run all Paper 2 figure scripts sequentially. Each is idempotent (skip-if-exists).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

start=$(date +%s)
echo "=== Paper 2 reproduction start: $(date -u +%H:%M:%S) ==="

bash "$SCRIPT_DIR/paper2_fig14_incast.sh"      # quickest first
bash "$SCRIPT_DIR/paper2_fig04_baseline.sh"
bash "$SCRIPT_DIR/paper2_fig06_perm.sh"
bash "$SCRIPT_DIR/paper2_fig07_hsdp.sh"
bash "$SCRIPT_DIR/paper2_fig08_250node.sh"
bash "$SCRIPT_DIR/paper2_fig09_16mb.sh"
bash "$SCRIPT_DIR/paper2_fig10_8eleph.sh"
bash "$SCRIPT_DIR/paper2_fig11_failures.sh"
bash "$SCRIPT_DIR/paper2_fig12_pcts.sh"

end=$(date +%s)
echo "=== Paper 2 reproduction end (elapsed $((end-start))s) ==="
