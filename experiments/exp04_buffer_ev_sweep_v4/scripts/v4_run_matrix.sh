#!/usr/bin/env bash
# v4_run_matrix.sh — exp04 driver
#
# Two-part sweep:
#   Part A: REPS FREEZING buffer size ∈ {1,2,4,8,1024} with full EV domain (paths=16)
#   Part B: EV domain ∈ {1,2,4,8,16} with infinite buffer (buf=1024)
#
# Design matrix per part: 5 values × 2 severities × 4 workloads × 5 seeds = 200 runs
# Total: 400 runs.
#
# Idempotent: skips runs whose run.out already exists.
# Always passes -disable_tor_ecn (mandatory with -sender_cc_only).
# Vanilla FREEZING only (no -state_aware_ecn) — isolates LB mechanism.
#
# Usage: bash v4_run_matrix.sh [--dry-run]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
HTSIM_DIR="${REPO_ROOT}/htsim/sim/datacenter"
HTSIM="${HTSIM_DIR}/htsim_uec"
TOPO="${HTSIM_DIR}/topologies/reps/fat_tree_128_1os_3t_400g.topo"
CM_DIR="${HTSIM_DIR}/connection_matrices"
WORKLOADS_DIR="${REPO_ROOT}/experiments/workloads"
EXP_DIR="${SCRIPT_DIR}/.."
OUT_ROOT="${EXP_DIR}/runs"

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "[dry-run] Printing commands only — no runs will be executed"
fi

# ── Sanity checks ──────────────────────────────────────────────────────────────
if [[ ! -x "${HTSIM}" ]]; then
    echo "ERROR: binary not found at ${HTSIM}" >&2
    echo "  Build with: cd htsim/sim && make -j8 && cd datacenter && make -j8" >&2
    exit 1
fi
if [[ ! -f "${TOPO}" ]]; then
    echo "ERROR: topology not found: ${TOPO}" >&2; exit 1
fi

# ── Design axes ────────────────────────────────────────────────────────────────
BUF_VALUES=(1 2 4 8 1024)     # Part A: buffer sizes (1024 ≈ ∞)
EV_VALUES=(1 2 4 8 16)        # Part B: EV domain sizes
SEVERITIES=(0 4)              # 0 = no failure; 4 = 4 Agg↔Core links failed
SEEDS=(42 43 44 45 46)

# ── Common simulator flags ─────────────────────────────────────────────────────
read -ra COMMON_FLAGS <<< "-sack_threshold 4000 -end 5000 -sender_cc_only -sender_cc_algo nscc -topo ${TOPO} -linkspeed 400000 -ecn 25 76 -q 100 -cwnd 151 -load_balancing_algo freezing -exit_freeze 200000000 -disable_tor_ecn"

# ── TM path helper ─────────────────────────────────────────────────────────────
tm_for_workload() {
    local wname="$1" seed="$2"
    case "${wname}" in
        pureperm_8mb) echo "${CM_DIR}/perm_n128_s8388608.cm" ;;
        composite)    echo "${WORKLOADS_DIR}/composite.cm" ;;
        perm_32mb)    echo "${CM_DIR}/perm_128n_128c_32MB_s${seed}.cm" ;;
        perm_128mb)   echo "${CM_DIR}/perm_128n_128c_128MB_s${seed}.cm" ;;
        *) echo "ERROR: unknown workload ${wname}" >&2; exit 1 ;;
    esac
}

# ── Progress tracking ──────────────────────────────────────────────────────────
total=$(( (${#BUF_VALUES[@]} + ${#EV_VALUES[@]}) * ${#SEVERITIES[@]} * 4 * ${#SEEDS[@]} ))
done_count=0
skip_count=0
start_time=$(date +%s)

# ── Core run function ──────────────────────────────────────────────────────────
run_one() {
    local part="$1"       # partA or partB
    local dim_label="$2"  # "buf" or "ev"
    local dim_val="$3"    # numeric value
    local wname="$4"
    local sev="$5"
    local seed="$6"

    local tm; tm=$(tm_for_workload "${wname}" "${seed}")
    if [[ ! -f "${tm}" ]]; then
        echo "  ERROR: TM not found: ${tm}" >&2; return 1
    fi

    local outdir="${OUT_ROOT}/${part}/${dim_label}${dim_val}/${wname}/sev${sev}/seed${seed}"
    local outfile="${outdir}/run.out"
    local logfile="${outdir}/reps_state.csv"

    # Build CLI array
    local cli=("${HTSIM}" "${COMMON_FLAGS[@]}"
        -tm "${tm}" -seed "${seed}"
        -log_reps_state "${logfile}" -log_reps_state_src 0
    )
    if [[ "${part}" == "partA" ]]; then
        cli+=(-paths 16 -reps_buffer_size "${dim_val}")
    else
        cli+=(-paths "${dim_val}" -reps_buffer_size 1024)
    fi
    if [[ "${sev}" -gt 0 ]]; then
        cli+=(-fail_link_time 50 200)
        for ((i=0; i<sev; i++)); do
            cli+=(-fail_link_target "${i}" "${i}")
        done
    fi

    done_count=$(( done_count + 1 ))

    if "${DRY_RUN}"; then
        echo "[${done_count}/${total}] DRY: ${cli[*]} > ${outfile}"
        return 0
    fi

    # Idempotency: skip if output already exists
    if [[ -f "${outfile}" ]]; then
        skip_count=$(( skip_count + 1 ))
        printf "[%d/%d] SKIP  %s/%s%s/%s/sev%s/seed%s\n" \
            "${done_count}" "${total}" \
            "${part}" "${dim_label}" "${dim_val}" "${wname}" "${sev}" "${seed}"
        return 0
    fi

    mkdir -p "${outdir}"

    local cell_start; cell_start=$(date +%s)
    "${cli[@]}" > "${outfile}" 2>&1
    local rc=$?
    local cell_dur=$(( $(date +%s) - cell_start ))
    local elapsed=$(( $(date +%s) - start_time ))

    # Guard checks
    if ! grep -q "^Flow" "${outfile}" 2>/dev/null; then
        echo "  WARNING: no Flow lines in ${outfile}" >&2
    fi
    if grep -q "enable on tor downlink 1" "${outfile}" 2>/dev/null; then
        echo "  ERROR: 'enable on tor downlink 1' in ${outfile} — -disable_tor_ecn was ineffective!" >&2
    fi

    printf "[%d/%d] %s  %s/%s%s/%s/sev%s/seed%s  rc=%d  cell=%ds  elapsed=%ds\n" \
        "${done_count}" "${total}" \
        "$([ ${rc} -eq 0 ] && echo OK || echo FAIL)" \
        "${part}" "${dim_label}" "${dim_val}" "${wname}" "${sev}" "${seed}" \
        "${rc}" "${cell_dur}" "${elapsed}"
}

# ── Part A: buffer size sweep ──────────────────────────────────────────────────
echo "=== Part A: buffer size sweep  (paths=16, buf ∈ {${BUF_VALUES[*]}}) ==="
for buf in "${BUF_VALUES[@]}"; do
    for wname in pureperm_8mb composite perm_32mb perm_128mb; do
        for sev in "${SEVERITIES[@]}"; do
            for seed in "${SEEDS[@]}"; do
                run_one "partA" "buf" "${buf}" "${wname}" "${sev}" "${seed}"
            done
        done
    done
done

# ── Part B: EV domain sweep ────────────────────────────────────────────────────
echo "=== Part B: EV domain sweep  (buf=1024, ev_domain ∈ {${EV_VALUES[*]}}) ==="
for ev in "${EV_VALUES[@]}"; do
    for wname in pureperm_8mb composite perm_32mb perm_128mb; do
        for sev in "${SEVERITIES[@]}"; do
            for seed in "${SEEDS[@]}"; do
                run_one "partB" "ev" "${ev}" "${wname}" "${sev}" "${seed}"
            done
        done
    done
done

echo "Done. Attempted: ${done_count}  Skipped: ${skip_count}  New runs: $(( done_count - skip_count ))"
echo "Outputs under: ${OUT_ROOT}"
