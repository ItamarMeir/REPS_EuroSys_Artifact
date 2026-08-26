#!/usr/bin/env bash
# exp16: PATH_RANDOM vs exp14 conditions — elephant flow sizes only
# Runs path_random+constant and path_random+nscc on tornado N=16, 4-ary fat-tree.
# Compare with exp14 data (path_rr+constant, path_rr+nscc, freezing+nscc, freezing+constant).

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
    echo "ERROR: binary not found: $BIN"
    exit 1
fi

TOPO="$TOPO_DIR/fat_tree_16_1os_3t_400g.topo"
SEEDS="42 43 44"

# Elephant flow sizes: 16 MiB, 64 MiB, 256 MiB
# End times: 3× the 1.78× expected FCT + margin
declare -A END_TIME
END_TIME[16777216]=5000       # 16 MiB  → optimal ~336 µs → expected ~600 µs → -end 5 ms
END_TIME[67108864]=10000      # 64 MiB  → optimal ~1345 µs → expected ~2.4 ms → -end 10 ms
END_TIME[268435456]=20000     # 256 MiB → optimal ~5372 µs → expected ~9.6 ms → -end 20 ms

BASE="-sender_cc_only -disable_tor_ecn
  -topo $TOPO
  -linkspeed 400000 -hop_latency 0.5
  -q 60 -ecn 12 48 -cwnd 90
  -other_location -paths 65535 -sack_threshold 4000"

# Conditions: (lb_algo, cc_algo, label)
declare -a LB_ALGOS=(  "path_random" "path_random" )
declare -a CC_ALGOS=(  "constant"    "nscc"        )
declare -a LABELS=(    "path_random_constant" "path_random_nscc" )

for idx in 0 1; do
    lb="${LB_ALGOS[$idx]}"
    cc="${CC_ALGOS[$idx]}"
    label="${LABELS[$idx]}"

    for size in "${!END_TIME[@]}"; do
        wl_tag="tornado_n16_s${size}"
        tm="$CM_DIR/${wl_tag}.cm"
        if [[ ! -f "$tm" ]]; then
            echo "ERROR: workload file missing: $tm"
            exit 1
        fi
        endtime="${END_TIME[$size]}"
        for seed in $SEEDS; do
            outfile="$DATA_DIR/exp16_${label}_${wl_tag}_seed${seed}.out"
            if [[ -f "$outfile" ]]; then
                echo "[skip] $(basename "$outfile")"
                continue
            fi
            echo "[run]  label=${label} size=${size} seed=${seed} end=${endtime}µs"
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
echo "Runs complete. Next:"
echo "  python3 $EXP_DIR/aggregate_exp16.py"
echo "  python3 $EXP_DIR/plot_exp16.py"
