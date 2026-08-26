#!/usr/bin/env bash
# Paper 1 Fig 6: Per-failure-mode Speedup vs OPS (REPS only + OPS for ratio).
# 8 failure modes × 3 workloads (Perm 8MB, DC@l60 WebSearch, Ring AllReduce) × 2 LBs × 3 seeds.
# Failure-mode files live in htsim/sim/failures_input/ (relative to working dir).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib_common.sh"

FAIL_DIR="$REPO_ROOT/htsim/sim/failures_input"
LBS="freezing oblivious"      # OPS is the denominator for the speedup ratio
SEEDS="42 43 44"

# (label, failure_file)
declare -A MODES
MODES[1cable]="fail_one_cable.txt"
MODES[1switch]="fail_one_switch.txt"
MODES[1switchcable]="fail_one_switch_one_cable.txt"
MODES[5pct_cables]="5_percent_failed_cables.txt"
MODES[5pct_switches]="5_percent_failed_switches.txt"
MODES[5pct_mixed]="5_percent_failed_switches_and_cables.txt"
MODES[ber_cable]="ber_cable_one_percent.txt"
MODES[ber_switch]="ber_switch_one_percent.txt"

# (label, workload .cm)
declare -A WLS
WLS[perm8]="$CM_DIR/perm_128n_128c_8MB_s__SEED__.cm"
WLS[dc100]="$CM_DIR/cdf_websearch_l90_s__SEED__.cm"   # 90% is closest available to paper's 100%
WLS[ring]="$CM_DIR/exp13_allreduce_ring_n128_4MB.cm"  # produced by fig02_ai.sh

for mode_tag in "${!MODES[@]}"; do
    mode_file="$FAIL_DIR/${MODES[$mode_tag]}"
    if [[ ! -f "$mode_file" ]]; then
        echo "WARN: missing $mode_file"
        continue
    fi
    for wl_tag in "${!WLS[@]}"; do
        wl_template="${WLS[$wl_tag]}"
        for s in $SEEDS; do
            wl="${wl_template//__SEED__/$s}"
            if [[ ! -f "$wl" ]]; then
                echo "WARN: missing $wl (skipping $mode_tag.$wl_tag.s$s)"
                continue
            fi
            for lb in $LBS; do
                run_p1 "fig06_${mode_tag}_${wl_tag}" "$lb" "$s" "$wl" \
                    -failures_input "$mode_file"
            done
        done
    done
done

echo "[done] fig06_failures"
