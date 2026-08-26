#!/usr/bin/env bash
# exp15 large-flow extension: same 4 start modes, PATH_RR + constant CC,
# but with very long flows (64 MiB / 256 MiB / 1 GiB) so the FCT
# overhead from the initial burst is negligible vs total transmission time.
#
# Outputs land in the same data/ directory as 01_run_exp15.sh so the
# existing aggregate_exp15.py + plot_exp15.py pick them up automatically.

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
MODES="zero src_mod dst_mod srcdst_hash"
SEEDS="42 43 44"

# Size (bytes) → -end (µs). Conservative: 3× the 1.78× expected FCT + margin.
declare -A END_TIME
END_TIME[67108864]=10000       # 64 MiB  → optimal ~1345 µs → expected ~2.4 ms  → -end 10 ms
END_TIME[268435456]=20000      # 256 MiB → optimal ~5372 µs → expected ~9.6 ms  → -end 20 ms
END_TIME[1073741824]=60000     # 1 GiB   → optimal ~21477 µs → expected ~38 ms  → -end 60 ms

BASE="-sender_cc_only -disable_tor_ecn
  -topo $TOPO
  -linkspeed 400000 -hop_latency 0.5
  -q 60 -ecn 12 48 -cwnd 90
  -other_location -paths 65535 -sack_threshold 4000
  -load_balancing_algo path_rr
  -sender_cc_algo constant"

for mode in $MODES; do
    for size in "${!END_TIME[@]}"; do
        wl_tag="tornado_n16_s${size}"
        tm="$CM_DIR/${wl_tag}.cm"
        if [[ ! -f "$tm" ]]; then
            echo "ERROR: workload file missing: $tm"
            echo "  Generate with: python3 gen_tornado.py ${wl_tag}.cm 16 16 ${size} 0 42"
            exit 1
        fi
        endtime="${END_TIME[$size]}"
        for seed in $SEEDS; do
            outfile="$DATA_DIR/exp15_${mode}_${wl_tag}_seed${seed}.out"
            if [[ -f "$outfile" ]]; then
                echo "[skip] $(basename "$outfile")"
                continue
            fi
            echo "[run]  mode=${mode} size=${size} seed=${seed} end=${endtime}µs"
            # shellcheck disable=SC2086
            (cd "$REPO_ROOT/htsim/sim/datacenter" && \
             "$BIN" $BASE \
                 -end "$endtime" \
                 -path_rr_start_mode "$mode" \
                 -seed "$seed" \
                 -tm "$tm") \
                > "$outfile" 2>&1
            echo "[done] $(basename "$outfile")"
        done
    done
done

echo ""
echo "Large-flow runs complete. Re-run:"
echo "  python3 $EXP_DIR/aggregate_exp15.py"
echo "  python3 $EXP_DIR/plot_exp15.py"
