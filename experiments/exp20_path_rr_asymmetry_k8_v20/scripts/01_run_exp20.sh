#!/usr/bin/env bash
# exp20: PATH_RR path-count asymmetry on k=8 fat-tree (128 hosts).
# Two conditions x 10 seeds = 20 sims.  Each sim also writes:
#   data/exp20_{cond}_seed{S}_queues.csv   (agg→core queue depth, 1 µs samples)
#   data/exp20_{cond}_seed{S}_tor_queues.csv (ToR→agg queue depth, 1 µs samples)
#   data/exp20_{cond}_seed{S}_cwnd.csv     (cwnd trace for host 0 only)
# Idempotent: skips a run if the .out file already exists.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXP_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(cd "$EXP_DIR/../.." && pwd)"
BIN="$REPO_ROOT/htsim/sim/datacenter/htsim_uec"
CM_DIR="$REPO_ROOT/htsim/sim/datacenter/connection_matrices"
TOPO_FILE="$REPO_ROOT/htsim/sim/datacenter/topologies/reps/fat_tree_128_1os_3t_400g_paper.topo"
DATA_DIR="$EXP_DIR/data"

test -x "$BIN"       || { echo "ERROR: binary not found at $BIN"; exit 1; }
test -f "$TOPO_FILE" || { echo "ERROR: topology not found: $TOPO_FILE"; exit 1; }
mkdir -p "$DATA_DIR"

FLOW_SIZE=268435456
N=128
WL_TAG="tornado_n${N}_s${FLOW_SIZE}"
TM="$CM_DIR/${WL_TAG}.cm"

test -f "$TM" || { echo "ERROR: workload not found: $TM"; exit 1; }

BASE_FLAGS=(
    -sender_cc_only -disable_tor_ecn
    -cwnd 155 -linkspeed 400000 -hop_latency 0.5
    -q 60 -ecn 12 48 -other_location -paths 65535
    -sack_threshold 4000 -end 20000
    -load_balancing_algo path_rr -path_rr_start_mode src_mod
    -sender_cc_algo nscc
    -topo "$TOPO_FILE"
)

run_sim() {
    local COND="$1"
    local SEED="$2"
    local EXTRA=("${@:3}")

    local OUT="$DATA_DIR/exp20_${COND}_${WL_TAG}_seed${SEED}.out"
    local Q_CSV="$DATA_DIR/exp20_${COND}_seed${SEED}_queues.csv"
    local TQ_CSV="$DATA_DIR/exp20_${COND}_seed${SEED}_tor_queues.csv"
    local CWND_CSV="$DATA_DIR/exp20_${COND}_seed${SEED}_cwnd.csv"

    if [[ -f "$OUT" ]]; then
        echo "SKIP (exists): $(basename $OUT)"
        return
    fi

    echo "RUN: cond=$COND seed=$SEED ${EXTRA[*]:-}"
    "$BIN" "${BASE_FLAGS[@]}" \
        -tm "$TM" -seed "$SEED" \
        "${EXTRA[@]}" \
        -log_core_queues "$Q_CSV" \
        -log_tor_queues  "$TQ_CSV" \
        -log_cwnd "$CWND_CSV" -log_cwnd_src 0 \
        > "$OUT" 2>&1
    echo "  -> $(basename $OUT)"
}

for SEED in 42 43 44 45 46; do
    run_sim "baseline"    "$SEED"
    run_sim "constrained" "$SEED" -path_rr_npaths_override "0:15"
done

echo ""
echo "Done. Files in $DATA_DIR:"
ls -lh "$DATA_DIR"
