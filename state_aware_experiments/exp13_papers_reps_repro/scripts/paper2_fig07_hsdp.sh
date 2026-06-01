#!/usr/bin/env bash
# Paper 2 Fig 7: HSDP Llama-3 70B ring step.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib_common.sh"

for s in $SEEDS; do
    tm="$WL_DIR/paper_hsdp_s${s}.cm"
    for cca in $CCAS_P2_OTHER; do
        run_p2 fig07 "$cca" "$s" "$tm"
    done
done
echo "[done] paper2_fig07"
