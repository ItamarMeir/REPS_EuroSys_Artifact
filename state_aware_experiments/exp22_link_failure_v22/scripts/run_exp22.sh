#!/bin/bash
# exp22: SRv6 buffer-size sweep on K=16 fat tree, tornado 8 MB, 5% link failure.
#
# Identical to exp21 except 5% of core↔agg links are permanently failed.
# Link selection is deterministic (Python random.seed=0), independent of traffic
# seeds 42/43/44, so all algorithm runs face the same degraded topology.
#
# K=16 fat tree has 128 agg (0-127) × 64 core (0-63); valid agg-core pairs
# satisfy core % 8 == agg % 8 (1024 total). 5% = 51 links failed from t=1µs.
#
# Usage:  bash run_exp22.sh
# Idempotent: skips runs whose output file already exists.

set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${EXP_DIR}/../.." && pwd)"
HTSIM="${REPO_ROOT}/htsim/sim/datacenter/htsim_uec"
TOPO="${REPO_ROOT}/htsim/sim/datacenter/topologies/reps/fat_tree_1024_1os_3t_400g.topo"
WL="${REPO_ROOT}/htsim/sim/datacenter/connection_matrices/tornado_n1024_s8388608.cm"
RUNS="${EXP_DIR}/runs"
DATA="${EXP_DIR}/data"

if [ ! -x "${HTSIM}" ]; then
    echo "ERROR: htsim_uec not found at ${HTSIM}"
    echo "Build: cd ${REPO_ROOT}/htsim/sim && make -j8 && cd datacenter && make -j8"
    exit 1
fi
mkdir -p "${RUNS}" "${DATA}"

# ── Generate 51 random valid failed link targets (deterministic, seed=0) ──────
echo "Generating failed link targets (5% of 1024 agg-core links = 51)..."
FAILED_LINKS=$(python3 - <<'PYEOF'
import random
random.seed(0)
# Valid (agg, core) pairs in K=16 fat tree: core % 8 == agg % 8
valid = [(a, c) for a in range(128) for c in range(64) if c % 8 == a % 8]
chosen = random.sample(valid, 51)
for a, c in chosen:
    print(f"-fail_link_target {a} {c}")
PYEOF
)
N_FAILED=$(echo "${FAILED_LINKS}" | wc -l)
echo "  ${N_FAILED} link targets selected"
echo "  First 3: $(echo "${FAILED_LINKS}" | head -3 | tr '\n' ' ')"
echo ""

# ── Algorithm definitions ──────────────────────────────────────────────────
ALGOS=(
    "path_static:-load_balancing_algo path_static"
    "freezing_b1:-load_balancing_algo freezing -reps_buffer_size 1 -use_srv6"
    "freezing_b2:-load_balancing_algo freezing -reps_buffer_size 2 -use_srv6"
    "freezing_b4:-load_balancing_algo freezing -reps_buffer_size 4 -use_srv6"
    "freezing_b8:-load_balancing_algo freezing -reps_buffer_size 8 -use_srv6"
    "freezing_b16:-load_balancing_algo freezing -reps_buffer_size 16 -use_srv6"
    "freezing_b32:-load_balancing_algo freezing -reps_buffer_size 32 -use_srv6"
    "freezing_b64:-load_balancing_algo freezing -reps_buffer_size 64 -use_srv6"
    "reps:-load_balancing_algo reps -use_srv6"
)

CC_MODES=(
    "nscc:-sender_cc_algo nscc -cwnd 100"
    "constant:-sender_cc_algo constant -cwnd 1000"
)

SEEDS=(42 43 44)

# ── Common simulation flags ────────────────────────────────────────────────
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
    # 5% link failure: permanent from t=1µs (recovery at t=10^9µs >> sim end)
    -fail_link_time 1 1000000000
)

# Append all 51 fail_link_target flags
while IFS= read -r line; do
    BASE_FLAGS+=($line)
done <<< "${FAILED_LINKS}"

PASS=0
FAIL=0
SKIP=0
TOTAL_RUNS=$(( ${#ALGOS[@]} * ${#CC_MODES[@]} * ${#SEEDS[@]} ))

echo "========================================================================"
echo " exp22: SRv6 buffer sweep + 5% link failure — K=16 fat tree, tornado 8 MB"
echo " Topology: fat_tree_1024_1os_3t_400g.topo  (1024 hosts, 64 paths/flow)"
echo " Workload: tornado_n1024_s8388608.cm       (8 MB per flow)"
echo " Failures: 51 agg↔core links failed from t=1µs (permanent)"
echo " Design:   ${#ALGOS[@]} algos × ${#CC_MODES[@]} CC modes × ${#SEEDS[@]} seeds = ${TOTAL_RUNS} runs"
echo "========================================================================"
echo ""

RUN_IDX=0
for ALGO_ENTRY in "${ALGOS[@]}"; do
    ALGO_LABEL="${ALGO_ENTRY%%:*}"
    ALGO_FLAGS="${ALGO_ENTRY#*:}"

    for CC_ENTRY in "${CC_MODES[@]}"; do
        CC_LABEL="${CC_ENTRY%%:*}"
        CC_FLAGS="${CC_ENTRY#*:}"

        for SEED in "${SEEDS[@]}"; do
            RUN_IDX=$(( RUN_IDX + 1 ))
            NAME="${ALGO_LABEL}_${CC_LABEL}_s${SEED}"
            OUTFILE="${RUNS}/${NAME}.out"

            # Buffer log for NSCC runs (host 0 only)
            BUF_FLAGS=()
            if [ "${CC_LABEL}" = "nscc" ]; then
                BUF_FLAGS=(
                    -log_reps_state "${DATA}/buf_${ALGO_LABEL}_${CC_LABEL}_s${SEED}.csv"
                    -log_reps_state_src 0
                    -log_buffer_contents
                )
            fi

            if [ -f "${OUTFILE}" ]; then
                echo "[${RUN_IDX}/${TOTAL_RUNS}] SKIP  ${NAME} (output exists)"
                SKIP=$(( SKIP + 1 ))
                continue
            fi

            echo -n "[${RUN_IDX}/${TOTAL_RUNS}] RUN   ${NAME} ... "
            T0=$(date +%s%N)

            # shellcheck disable=SC2086
            "${HTSIM}" "${BASE_FLAGS[@]}" \
                ${ALGO_FLAGS} \
                ${CC_FLAGS} \
                "${BUF_FLAGS[@]}" \
                -seed "${SEED}" \
                > "${OUTFILE}" 2>&1
            RC=$?

            T1=$(date +%s%N)
            ELAPSED_S=$(( (T1 - T0) / 1000000000 ))

            if grep -q "enable on tor downlink 1" "${OUTFILE}"; then
                echo "FAIL  ${NAME}: 'enable on tor downlink 1' detected!"
                FAIL=$(( FAIL + 1 ))
                continue
            fi

            NFLOWS=$(grep -c "finished at" "${OUTFILE}" 2>/dev/null || echo 0)
            if [ "${RC}" -eq 0 ] && [ "${NFLOWS}" -gt 0 ]; then
                echo "done (${ELAPSED_S}s, ${NFLOWS} flows)"
                PASS=$(( PASS + 1 ))
            else
                echo "FAIL  ${NAME}: rc=${RC} flows=${NFLOWS}"
                FAIL=$(( FAIL + 1 ))
            fi
        done
    done
done

echo ""
echo "========================================================================"
echo " Summary: ${PASS} OK  ${FAIL} FAIL  ${SKIP} skipped  (${TOTAL_RUNS} total)"
if [ "${FAIL}" -gt 0 ]; then
    echo " SOME RUNS FAILED — check ${RUNS}/*.out for details"
fi
echo "========================================================================"
