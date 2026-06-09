#!/usr/bin/env bash
# exp18: PATH_RR start-slot sweep (offset 0, 1, 2) plus PATH_STATIC reference (256 MiB only)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
EXP_DIR="$SCRIPT_DIR/.."
EXP17_DIR="$REPO_ROOT/state_aware_experiments/exp17_cwnd_corrected_v17"
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
SIZE=268435456
END_TIME=20000

BASE="-sender_cc_only -disable_tor_ecn
  -topo $TOPO
  -linkspeed 400000 -hop_latency 0.5
  -q 60 -ecn 12 48 -cwnd $CWND
  -other_location -paths 65535 -sack_threshold 4000"

# === Copy exp17 offset-0 and path_static files into exp18/data ===
echo "Copying exp17 baseline data (off0 and path_static)..."
for f in "$EXP17_DIR/data"/exp17_{path_rr,path_static}_*_tornado_n16_s${SIZE}_seed*.out; do
    if [[ -f "$f" ]]; then
        basename_only=$(basename "$f")
        # Replace "exp17_path_rr" → "exp18_off0", keep rest
        new_name="exp18_${basename_only#exp17_path_rr_}"
        new_name="${new_name#exp17_path_static_}"
        if [[ "$basename_only" == *"path_rr"* ]]; then
            new_name="exp18_off0_${basename_only#exp17_path_rr_}"
        else
            new_name="exp18_path_static_${basename_only#exp17_path_static_}"
        fi
        dst="$DATA_DIR/$new_name"
        if [[ ! -f "$dst" ]]; then
            cp "$f" "$dst"
            echo "[copy] $new_name"
        else
            echo "[skip] $new_name (already present)"
        fi
    fi
done

# === Run offset-1 and offset-2 conditions ===
declare -A LB_ALGO CC_ALGO OFFSET_MODE
LB_ALGO[off1_constant]=path_rr;          CC_ALGO[off1_constant]=constant;  OFFSET_MODE[off1_constant]=src_mod
LB_ALGO[off1_nscc]=path_rr;              CC_ALGO[off1_nscc]=nscc;          OFFSET_MODE[off1_nscc]=src_mod
LB_ALGO[off2_constant]=path_rr;          CC_ALGO[off2_constant]=constant;  OFFSET_MODE[off2_constant]=src_mod2
LB_ALGO[off2_nscc]=path_rr;              CC_ALGO[off2_nscc]=nscc;          OFFSET_MODE[off2_nscc]=src_mod2

CONDITIONS="off1_constant off1_nscc off2_constant off2_nscc"

wl_tag="tornado_n16_s${SIZE}"
tm="$CM_DIR/${wl_tag}.cm"
if [[ ! -f "$tm" ]]; then echo "ERROR: missing $tm"; exit 1; fi

for cond in $CONDITIONS; do
    lb="${LB_ALGO[$cond]}"
    cc="${CC_ALGO[$cond]}"
    offset="${OFFSET_MODE[$cond]}"
    for seed in $SEEDS; do
        outfile="$DATA_DIR/exp18_${cond}_${wl_tag}_seed${seed}.out"
        if [[ -f "$outfile" ]]; then echo "[skip] $(basename "$outfile")"; continue; fi
        echo "[run]  cond=${cond} (offset=$offset) size=${SIZE} seed=${seed}"
        (cd "$REPO_ROOT/htsim/sim/datacenter" && \
         "$BIN" $BASE \
             -load_balancing_algo "$lb" \
             -path_rr_start_mode "$offset" \
             -sender_cc_algo "$cc" \
             -end "$END_TIME" \
             -seed "$seed" \
             -tm "$tm") \
            > "$outfile" 2>&1
        echo "[done] $(basename "$outfile")"
    done
done

echo ""
echo "exp18 runs complete (off0 and path_static copied from exp17). Next:"
echo "  python3 $EXP_DIR/aggregate_exp18.py"
echo "  python3 $EXP_DIR/plot_exp18.py"
