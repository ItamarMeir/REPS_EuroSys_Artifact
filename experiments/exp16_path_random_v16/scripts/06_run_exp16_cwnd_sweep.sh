#!/usr/bin/env bash
# exp16 cwnd sweep: PATH_STATIC+constant at multiple cwnd values to locate BDP.
# BDP = network_max_unloaded_rtt * linkspeed / 8 ≈ 12.5 µs * 400 Gbps / 8 ≈ 150 MTUs.
# cwnd < BDP → sender under-utilises pipe; cwnd ≈ BDP → FCT ≈ optimal; cwnd >> BDP → queue.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
EXP_DIR="$SCRIPT_DIR/.."
BIN="$REPO_ROOT/htsim/sim/datacenter/htsim_uec"
TOPO_DIR="$REPO_ROOT/htsim/sim/datacenter/topologies/reps"
CM_DIR="$REPO_ROOT/htsim/sim/datacenter/connection_matrices"
DATA_DIR="$EXP_DIR/data/cwnd_sweep"

mkdir -p "$DATA_DIR"

if [[ ! -x "$BIN" ]]; then
    echo "ERROR: binary not found: $BIN"; exit 1
fi

TOPO="$TOPO_DIR/fat_tree_16_1os_3t_400g.topo"
SIZE=67108864          # 64 MiB — converged elephant
WL_TAG="tornado_n16_s${SIZE}"
TM="$CM_DIR/${WL_TAG}.cm"
END_TIME=10000         # 10 ms
SEEDS="42 43 44"

# Sweep range: well below BDP (80), at BDP (~150), above BDP (200)
CWNDS="80 100 120 130 140 145 150 155 160 170 200"

BASE="-sender_cc_only -disable_tor_ecn
  -topo $TOPO
  -linkspeed 400000 -hop_latency 0.5
  -q 60 -ecn 12 48
  -other_location -paths 65535 -sack_threshold 4000
  -load_balancing_algo path_static
  -sender_cc_algo constant"

if [[ ! -f "$TM" ]]; then
    echo "ERROR: workload file missing: $TM"; exit 1
fi

for cwnd in $CWNDS; do
    for seed in $SEEDS; do
        outfile="$DATA_DIR/cwnd${cwnd}_${WL_TAG}_seed${seed}.out"
        if [[ -f "$outfile" ]]; then
            echo "[skip] cwnd=${cwnd} seed=${seed}"
            continue
        fi
        echo "[run]  cwnd=${cwnd} seed=${seed}"
        (cd "$REPO_ROOT/htsim/sim/datacenter" && \
         "$BIN" $BASE \
             -cwnd "$cwnd" \
             -end "$END_TIME" \
             -seed "$seed" \
             -tm "$TM") \
            > "$outfile" 2>&1
        echo "[done] cwnd=${cwnd} seed=${seed}"
    done
done

echo ""
echo "Sweep complete. Run:"
echo "  python3 $EXP_DIR/plot_exp16_cwnd_sweep.py"
