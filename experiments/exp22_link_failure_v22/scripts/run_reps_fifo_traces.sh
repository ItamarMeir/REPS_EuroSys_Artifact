#!/bin/bash
# One-off: regenerate the plain-REPS event traces for exp21 and exp22 now that
# logRepsEvent emits the `fifo` column (_next_pathid contents). Seed 42, nscc,
# same flags as each experiment's own runner.
set -u
REPO_ROOT="/workspace"
HTSIM="${REPO_ROOT}/htsim/sim/datacenter/htsim_uec"
TOPO="${REPO_ROOT}/htsim/sim/datacenter/topologies/reps/fat_tree_1024_1os_3t_400g.topo"
WL="${REPO_ROOT}/htsim/sim/datacenter/connection_matrices/tornado_n1024_s8388608.cm"
D21="${REPO_ROOT}/experiments/exp21_srv6_buffer_sweep_k16_v21/data"
D22="${REPO_ROOT}/experiments/exp22_link_failure_v22/data"

COMMON=(
    -topo "${TOPO}" -tm "${WL}"
    -paths 64 -sender_cc_only -disable_tor_ecn
    -linkspeed 400000 -hop_latency 0.5 -q 60 -ecn 12 48
    -sack_threshold 4000 -exit_freeze 200000000 -end 90000
    -sender_cc_algo nscc -cwnd 100
    -load_balancing_algo reps -use_srv6 -seed 42
)

# exp21: no link failures.
echo "=== exp21 reps ==="
"${HTSIM}" "${COMMON[@]}" \
    -log_reps_events "${D21}/events_reps_nscc_s42.csv" -log_reps_events_src 0 \
    > "${D21}/run_reps_nscc_s42.out" 2>&1
echo "  exit=$? tor_ecn_bug=$(grep -c 'enable on tor downlink 1' "${D21}/run_reps_nscc_s42.out")"

# exp22: same 51 deterministic agg-core failures as run_exp22.sh.
FAILED_LINKS=$(python3 - <<'PYEOF'
import random
random.seed(0)
valid = [(a, c) for a in range(128) for c in range(64) if c % 8 == a % 8]
for a, c in random.sample(valid, 51):
    print(f"-fail_link_target {a} {c}")
PYEOF
)
FAIL_FLAGS=(-fail_link_time 1 1000000000)
while IFS= read -r line; do
    FAIL_FLAGS+=($line)
done <<< "${FAILED_LINKS}"

echo "=== exp22 reps ==="
"${HTSIM}" "${COMMON[@]}" "${FAIL_FLAGS[@]}" \
    -log_reps_events "${D22}/events_reps_nscc_s42.csv" -log_reps_events_src 0 \
    > "${D22}/run_reps_nscc_s42.out" 2>&1
echo "  exit=$? tor_ecn_bug=$(grep -c 'enable on tor downlink 1' "${D22}/run_reps_nscc_s42.out")"
