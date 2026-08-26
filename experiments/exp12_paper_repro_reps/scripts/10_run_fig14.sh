#!/usr/bin/env bash
# Fig 14: Incast workload (32 senders → 1 victim, 8 MB each)
# CCAs: lswift, mswift, nscc, mnscc
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib_common.sh"

CCAS_FIG14="lswift mswift nscc mnscc"

for cc in $CCAS_FIG14; do
    for seed in $SEEDS; do
        run_sim "fig14" "$cc" "$seed" "$WL_DIR/paper_incast32_s${seed}.cm"
    done
done
echo "[fig14] Done."
