#!/usr/bin/env bash
# run_all.sh — Run all figure scripts sequentially.
# For parallel execution, run individual scripts in background.
set -euo pipefail
SCRIPTS_DIR="$(dirname "${BASH_SOURCE[0]}")"

echo "===== exp12: Paper Repro REPS ====="
echo "Started: $(date)"

bash "$SCRIPTS_DIR/01_run_fig4.sh"
bash "$SCRIPTS_DIR/02_run_fig5c.sh"
bash "$SCRIPTS_DIR/03_run_fig6.sh"
bash "$SCRIPTS_DIR/04_run_fig7.sh"
bash "$SCRIPTS_DIR/05_run_fig8.sh"
bash "$SCRIPTS_DIR/06_run_fig9.sh"
bash "$SCRIPTS_DIR/07_run_fig10.sh"
bash "$SCRIPTS_DIR/08_run_fig11.sh"
bash "$SCRIPTS_DIR/09_run_fig12.sh"
bash "$SCRIPTS_DIR/10_run_fig14.sh"

echo "Finished: $(date)"
echo "Run 'python3 aggregate.py && python3 plot_cct.py && python3 plot_cdf.py' to generate plots."
