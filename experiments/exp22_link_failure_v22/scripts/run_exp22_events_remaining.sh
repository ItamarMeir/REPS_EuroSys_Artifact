#!/bin/bash
# One-off: generate -log_reps_events trace CSVs for exp22 buffer sizes b2,b4,b8,b16,b32
# (b1, b64, reps already done). Seed 42, nscc CC only, mirrors run_exp22.sh flags exactly.
set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${EXP_DIR}/../.." && pwd)"
HTSIM="${REPO_ROOT}/htsim/sim/datacenter/htsim_uec"
TOPO="${REPO_ROOT}/htsim/sim/datacenter/topologies/reps/fat_tree_1024_1os_3t_400g.topo"
WL="${REPO_ROOT}/htsim/sim/datacenter/connection_matrices/tornado_n1024_s8388608.cm"
DATA="${EXP_DIR}/data"

FAILED_LINKS=$(python3 - <<'PYEOF'
import random
random.seed(0)
valid = [(a, c) for a in range(128) for c in range(64) if c % 8 == a % 8]
chosen = random.sample(valid, 51)
for a, c in chosen:
    print(f"-fail_link_target {a} {c}")
PYEOF
)

BASE_FLAGS=(
    -topo "${TOPO}"
    -tm "${WL}"
    -paths 64
    -sender_cc_only
    -disable_tor_ecn
    -linkspeed 400000
    -hop_latency 0.5
    -q 60
    -ecn 12 48
    -sack_threshold 4000
    -exit_freeze 200000000
    -end 90000
    -fail_link_time 1 1000000000
)
while IFS= read -r line; do
    BASE_FLAGS+=($line)
done <<< "${FAILED_LINKS}"

ALGOS=(
    "freezing_b2:-load_balancing_algo freezing -reps_buffer_size 2 -use_srv6"
    "freezing_b4:-load_balancing_algo freezing -reps_buffer_size 4 -use_srv6"
    "freezing_b8:-load_balancing_algo freezing -reps_buffer_size 8 -use_srv6"
    "freezing_b16:-load_balancing_algo freezing -reps_buffer_size 16 -use_srv6"
    "freezing_b32:-load_balancing_algo freezing -reps_buffer_size 32 -use_srv6"
)

for ALGO_ENTRY in "${ALGOS[@]}"; do
    ALGO_LABEL="${ALGO_ENTRY%%:*}"
    ALGO_FLAGS="${ALGO_ENTRY#*:}"
    NAME="${ALGO_LABEL}_nscc_s42"
    echo "=== ${NAME} ==="
    "${HTSIM}" "${BASE_FLAGS[@]}" \
        -sender_cc_algo nscc -cwnd 100 \
        ${ALGO_FLAGS} -seed 42 \
        -log_reps_events "${DATA}/events_${NAME}.csv" \
        -log_reps_events_src 0 \
        > "${DATA}/run_${NAME}.out" 2>&1
    echo "  exit=$? tor_ecn_bug=$(grep -c 'enable on tor downlink 1' "${DATA}/run_${NAME}.out")"
done
