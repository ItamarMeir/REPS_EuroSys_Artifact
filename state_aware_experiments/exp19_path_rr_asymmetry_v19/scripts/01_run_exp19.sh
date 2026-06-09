#!/usr/bin/env bash
# exp19: PATH_RR path-count asymmetry — one host constrained to 3 of 4 paths.
# Two conditions x 3 seeds = 6 sims.  Each sim also writes:
#   data/exp19_{cond}_seed{S}_queues.csv   (core queue depth, 1 µs samples)
#   data/exp19_{cond}_seed{S}_cwnd.csv     (cwnd trace for host 0 only)
# Idempotent: skips a run if the .out file already exists.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXP_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(cd "$EXP_DIR/../.." && pwd)"
BIN="$REPO_ROOT/htsim/sim/datacenter/htsim_uec"
CM_DIR="$REPO_ROOT/htsim/sim/datacenter/connection_matrices"
DATA_DIR="$EXP_DIR/data"

test -x "$BIN" || { echo "ERROR: binary not found at $BIN"; exit 1; }
mkdir -p "$DATA_DIR"

FLOW_SIZE=268435456
N=16
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
)

run_sim() {
    local COND="$1"
    local SEED="$2"
    local EXTRA=("${@:3}")

    local OUT="$DATA_DIR/exp19_${COND}_${WL_TAG}_seed${SEED}.out"
    local Q_CSV="$DATA_DIR/exp19_${COND}_seed${SEED}_queues.csv"
    local TQ_CSV="$DATA_DIR/exp19_${COND}_seed${SEED}_tor_queues.csv"
    local CWND_CSV="$DATA_DIR/exp19_${COND}_seed${SEED}_cwnd.csv"

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

for SEED in 42 43 44 45 46 47 48 49 50 51; do
    run_sim "baseline"    "$SEED"
    run_sim "constrained" "$SEED" -path_rr_npaths_override "0:3"
done

echo ""
echo "Done. Files in $DATA_DIR:"
ls -lh "$DATA_DIR"
