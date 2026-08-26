#!/usr/bin/env bash
# Fig 5c: FCT CDF for baseline workload — REUSES fig4 outputs (same runs).
# No new simulation runs needed; aggregate.py / plot_cdf.py reads fig4_*.out.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib_common.sh"

echo "[fig5c] Fig 5c shares runs with Fig 4.  No new sims needed."
echo "[fig5c] Ensure 01_run_fig4.sh has completed, then run plot_cdf.py --fig 5c"
