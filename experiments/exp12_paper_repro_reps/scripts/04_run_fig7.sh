#!/usr/bin/env bash
# Fig 7: HSDP ring workload (128 ring flows, 13.7 MB each)
# CCAs: lswift, mswift, nscc, mnscc
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib_common.sh"

CCAS_FIG7="lswift mswift nscc mnscc"

for cc in $CCAS_FIG7; do
    for seed in $SEEDS; do
        run_sim "fig7" "$cc" "$seed" "$WL_DIR/paper_hsdp_s${seed}.cm"
    done
done
echo "[fig7] Done."
