#!/usr/bin/env bash
# exp17: All 10 conditions at cwnd=155 (= BDP knee, full line-rate utilisation).
# exp16 used cwnd=90, which is only 60% of BDP (network_max_unloaded_rtt × link_rate / 8
# ≈ 12.5 µs × 400 Gbps / 8 / 4150 bytes ≈ 150.7 MTUs). cwnd=155 is the empirically
# determined knee where PATH_STATIC+constant FCT first reaches its plateau.

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
SEEDS="42 43 44"
CWND=155

declare -A END_TIME
END_TIME[16777216]=5000
END_TIME[67108864]=10000

BASE="-sender_cc_only -disable_tor_ecn
  -topo $TOPO
  -linkspeed 400000 -hop_latency 0.5
  -q 60 -ecn 12 48 -cwnd $CWND
  -other_location -paths 65535 -sack_threshold 4000"

# ── conditions ──────────────────────────────────────────────────────────────
declare -A LB_ALGO CC_ALGO
LB_ALGO[path_rr_constant]=path_rr;          CC_ALGO[path_rr_constant]=constant
LB_ALGO[path_rr_nscc]=path_rr;              CC_ALGO[path_rr_nscc]=nscc
LB_ALGO[freezing_constant]=freezing;        CC_ALGO[freezing_constant]=constant
LB_ALGO[freezing_nscc]=freezing;            CC_ALGO[freezing_nscc]=nscc
LB_ALGO[path_random_constant]=path_random;  CC_ALGO[path_random_constant]=constant
LB_ALGO[path_random_nscc]=path_random;      CC_ALGO[path_random_nscc]=nscc
LB_ALGO[ops_constant]=oblivious;            CC_ALGO[ops_constant]=constant
LB_ALGO[ops_nscc]=oblivious;               CC_ALGO[ops_nscc]=nscc
LB_ALGO[path_static_constant]=path_static; CC_ALGO[path_static_constant]=constant
LB_ALGO[path_static_nscc]=path_static;     CC_ALGO[path_static_nscc]=nscc

CONDITIONS="path_rr_constant path_rr_nscc
            freezing_constant freezing_nscc
            path_random_constant path_random_nscc
            ops_constant ops_nscc
            path_static_constant path_static_nscc"

for cond in $CONDITIONS; do
    lb="${LB_ALGO[$cond]}"
    cc="${CC_ALGO[$cond]}"
    for size in "${!END_TIME[@]}"; do
        wl_tag="tornado_n16_s${size}"
        tm="$CM_DIR/${wl_tag}.cm"
        if [[ ! -f "$tm" ]]; then echo "ERROR: missing $tm"; exit 1; fi
        endtime="${END_TIME[$size]}"
        for seed in $SEEDS; do
            outfile="$DATA_DIR/exp17_${cond}_${wl_tag}_seed${seed}.out"
            if [[ -f "$outfile" ]]; then echo "[skip] $(basename "$outfile")"; continue; fi
            echo "[run]  cond=${cond} size=${size} seed=${seed}"
            (cd "$REPO_ROOT/htsim/sim/datacenter" && \
             "$BIN" $BASE \
                 -load_balancing_algo "$lb" \
                 -sender_cc_algo "$cc" \
                 -end "$endtime" \
                 -seed "$seed" \
                 -tm "$tm") \
                > "$outfile" 2>&1
            echo "[done] $(basename "$outfile")"
        done
    done
done

echo ""
echo "All runs complete. Next:"
echo "  python3 $EXP_DIR/aggregate_exp17.py"
echo "  python3 $EXP_DIR/plot_exp17.py"
