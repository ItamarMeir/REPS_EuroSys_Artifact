#!/usr/bin/env bash
# exp16 queue logging: sample core-switch queue depths for all 6 conditions.
# Runs each condition at 64 MiB, seed=42, with -log_core_queues.
# Output: data/qlog_<condition>_64mib_seed42.csv

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
EXP_DIR="$SCRIPT_DIR/.."
BIN="$REPO_ROOT/htsim/sim/datacenter/htsim_uec"
TOPO_DIR="$REPO_ROOT/htsim/sim/datacenter/topologies/reps"
CM_DIR="$REPO_ROOT/htsim/sim/datacenter/connection_matrices"
DATA_DIR="$EXP_DIR/data"

mkdir -p "$DATA_DIR"

if [[ ! -x "$BIN" ]]; then
    echo "ERROR: binary not found: $BIN"; exit 1
fi

TOPO="$TOPO_DIR/fat_tree_16_1os_3t_400g.topo"
SIZE=67108864      # 64 MiB
END=10000          # 10 ms
SEED=42
TM="$CM_DIR/tornado_n16_s${SIZE}.cm"

if [[ ! -f "$TM" ]]; then
    echo "ERROR: workload file missing: $TM"; exit 1
fi

BASE="-sender_cc_only -disable_tor_ecn
  -topo $TOPO
  -linkspeed 400000 -hop_latency 0.5
  -q 60 -ecn 12 48 -cwnd 90
  -other_location -paths 65535 -sack_threshold 4000"

declare -a CONDITIONS=( "path_rr_constant" "path_rr_nscc" "freezing_constant" "freezing_nscc" "path_random_constant" "path_random_nscc" )
declare -A LB_ALGO=(
    [path_rr_constant]="path_rr"
    [path_rr_nscc]="path_rr"
    [freezing_constant]="freezing"
    [freezing_nscc]="freezing"
    [path_random_constant]="path_random"
    [path_random_nscc]="path_random"
)
declare -A CC_ALGO=(
    [path_rr_constant]="constant"
    [path_rr_nscc]="nscc"
    [freezing_constant]="constant"
    [freezing_nscc]="nscc"
    [path_random_constant]="constant"
    [path_random_nscc]="nscc"
)

for cond in "${CONDITIONS[@]}"; do
    lb="${LB_ALGO[$cond]}"
    cc="${CC_ALGO[$cond]}"
    qlog="$DATA_DIR/qlog_${cond}_64mib_seed${SEED}.csv"
    outfile="$DATA_DIR/exp16_qlog_${cond}_64mib_seed${SEED}.out"
    if [[ -f "$qlog" ]]; then
        echo "[skip] $qlog"
        continue
    fi
    echo "[run]  cond=${cond} lb=${lb} cc=${cc}"
    (cd "$REPO_ROOT/htsim/sim/datacenter" && \
     "$BIN" $BASE \
         -load_balancing_algo "$lb" \
         -sender_cc_algo "$cc" \
         -end "$END" \
         -seed "$SEED" \
         -tm "$TM" \
         -log_core_queues "$qlog") \
        > "$outfile" 2>&1
    echo "[done] $(wc -l < "$qlog") rows → $qlog"
done

echo ""
echo "Queue logs complete. Next:"
echo "  python3 $EXP_DIR/plot_exp16_queues.py"
