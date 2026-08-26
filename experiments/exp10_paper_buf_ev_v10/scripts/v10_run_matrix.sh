#!/usr/bin/env bash
# v10_run_matrix.sh — exp10 (paper workloads) parallel runner.
#
# Two-part sweep of vanilla REPS+NSCC on the paper's 4 workloads:
#   Part A: buffer size ∈ {1,2,4,8,1024}  × fixed -paths 65535
#   Part B: -paths     ∈ {32,256,65535}   × fixed -reps_buffer_size 8
#
# Topology: 800 Gbps 3-tier 128-host fat-tree (paper-faithful).
#
# Usage:
#   bash v10_run_matrix.sh --part_a [--jobs N] [--dry-run]
#   bash v10_run_matrix.sh --part_b [--jobs N] [--dry-run]
#
# Output layout:
#   runs/part_{a,b}/{buf|ev}_{N}/{workload}/sev{S}/seed{K}/run.out

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
HTSIM_DIR="${REPO_ROOT}/htsim/sim/datacenter"
HTSIM="${HTSIM_DIR}/htsim_uec"
TOPO="${HTSIM_DIR}/topologies/reps/fat_tree_128_1os_3t_800g.topo"
PAPER_WL_DIR="${REPO_ROOT}/experiments/workloads"
PERM_TM="${HTSIM_DIR}/connection_matrices/perm_n128_s8388608.cm"
EXP_DIR="${SCRIPT_DIR}/.."
OUT_ROOT="${EXP_DIR}/runs"

# ── Args ────────────────────────────────────────────────────────────────────────
PART=""
MAX_JOBS=4
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --part_a)   PART="a" ;;
        --part_b)   PART="b" ;;
        --jobs=*)   MAX_JOBS="${1#--jobs=}" ;;
        --jobs)     shift; MAX_JOBS="$1" ;;
        --dry-run)  DRY_RUN=true ;;
        *) echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
    shift
done

if [[ -z "${PART}" ]]; then
    echo "ERROR: specify --part_a or --part_b" >&2; exit 1
fi
if [[ ! -x "${HTSIM}" ]]; then
    echo "ERROR: binary not found: ${HTSIM}" >&2; exit 1
fi

# ── Design axes ─────────────────────────────────────────────────────────────────
WORKLOADS=(baseline perm hsdp incast32)
SEVERITIES=(0 4)
SEEDS=(42 43 44)

# Part A: sweep buf_size, fixed paths
BUF_VALUES=(1 2 4 8 1024)
FIXED_PATHS=65535

# Part B: sweep paths, fixed buf_size
EV_VALUES=(32 256 65535)
FIXED_BUF=8

# ── Common simulator flags (vanilla REPS+NSCC, 800 G topology) ──────────────────
read -ra COMMON_FLAGS <<< "-sack_threshold 4000 -end 5000 \
-sender_cc_only -sender_cc_algo nscc \
-load_balancing_algo freezing -exit_freeze 200000000 \
-topo ${TOPO} -linkspeed 800000 -ecn 25 76 -q 100 -cwnd 151 \
-disable_tor_ecn"

# ── Workload→TM resolver ────────────────────────────────────────────────────────
tm_path() {
    local workload="$1" seed="$2"
    case "${workload}" in
        baseline) printf '%s/paper_baseline_s%d.cm' "${PAPER_WL_DIR}" "${seed}" ;;
        hsdp)     printf '%s/paper_hsdp_s%d.cm'     "${PAPER_WL_DIR}" "${seed}" ;;
        incast32) printf '%s/paper_incast32_s%d.cm' "${PAPER_WL_DIR}" "${seed}" ;;
        perm)     printf '%s' "${PERM_TM}" ;;
        *) echo "ERROR: unknown workload ${workload}" >&2; exit 1 ;;
    esac
}

# ── Cell builder ────────────────────────────────────────────────────────────────
build_cells_a() {
    for buf in "${BUF_VALUES[@]}"; do
        for wname in "${WORKLOADS[@]}"; do
            for sev in "${SEVERITIES[@]}"; do
                for seed in "${SEEDS[@]}"; do
                    echo "buf_${buf}|${wname}|${sev}|${seed}"
                done
            done
        done
    done
}

build_cells_b() {
    for ev in "${EV_VALUES[@]}"; do
        for wname in "${WORKLOADS[@]}"; do
            for sev in "${SEVERITIES[@]}"; do
                for seed in "${SEEDS[@]}"; do
                    echo "ev_${ev}|${wname}|${sev}|${seed}"
                done
            done
        done
    done
}

mapfile -t CELLS < <( [[ "${PART}" == "a" ]] && build_cells_a || build_cells_b )

total=${#CELLS[@]}
done_count=0
skip_count=0
fail_count=0
start_time=$(date +%s)
active_jobs=0
declare -A job_pids
declare -A job_pids_out

report_job() {
    local pid="$1"
    local label="${job_pids[$pid]}"
    local outfile="${job_pids_out[$pid]}"
    wait "${pid}"
    local rc=$?
    local elapsed=$(( $(date +%s) - start_time ))
    (( done_count++ )) || true
    local status="OK"
    if [[ "${rc}" -ne 0 ]]; then
        (( fail_count++ )) || true
        status="FAIL(rc=${rc})"
    elif ! grep -q "finished at" "${outfile}" 2>/dev/null; then
        (( fail_count++ )) || true
        status="WARN(no flows)"
    fi
    printf "[%d/%d] %s  %s  elapsed=%ds\n" \
        "${done_count}" "${total}" "${status}" "${label}" "${elapsed}"
    unset "job_pids[$pid]"
    unset "job_pids_out[$pid]"
    (( active_jobs-- )) || true
}

run_cell_bg() {
    local axis_tag="$1" wname="$2" sev="$3" seed="$4"
    local label="${axis_tag}/${wname}/sev${sev}/seed${seed}"
    local part_dir="part_${PART}"

    local tm; tm=$(tm_path "${wname}" "${seed}")
    local outdir="${OUT_ROOT}/${part_dir}/${axis_tag}/${wname}/sev${sev}/seed${seed}"
    local outfile="${outdir}/run.out"

    if [[ ! -f "${tm}" ]]; then
        echo "  WARN: TM missing: ${tm}" >&2
        (( fail_count++ )) || true
        (( done_count++ )) || true
        return
    fi

    if [[ -f "${outfile}" ]]; then
        (( skip_count++ )) || true
        (( done_count++ )) || true
        printf "[%d/%d] SKIP  %s\n" "${done_count}" "${total}" "${label}"
        return
    fi

    if "${DRY_RUN}"; then
        printf "DRY: %s  tm=%s\n" "${label}" "${tm}"
        (( done_count++ )) || true
        return
    fi

    mkdir -p "${outdir}"

    local axis_flags=()
    if [[ "${PART}" == "a" ]]; then
        local buf_val="${axis_tag#buf_}"
        axis_flags=(-reps_buffer_size "${buf_val}" -paths "${FIXED_PATHS}")
    else
        local ev_val="${axis_tag#ev_}"
        axis_flags=(-paths "${ev_val}" -reps_buffer_size "${FIXED_BUF}")
    fi

    (
        local cli=("${HTSIM}" "${COMMON_FLAGS[@]}"
            -tm "${tm}" -seed "${seed}"
            "${axis_flags[@]}"
        )
        if [[ "${sev}" -gt 0 ]]; then
            cli+=(-fail_link_time 50 200 -fail_link_target 0 0)
        fi
        "${cli[@]}" > "${outfile}" 2>&1
        local rc=$?
        if grep -q "enable on tor downlink 1" "${outfile}" 2>/dev/null; then
            echo "  ERROR: disable_tor_ecn was ineffective in ${outfile}!" >&2
        fi
        exit "${rc}"
    ) &
    local bg_pid=$!
    job_pids[$bg_pid]="${label}"
    job_pids_out[$bg_pid]="${outfile}"
    (( active_jobs++ )) || true
}

# ── Print header ────────────────────────────────────────────────────────────────
if [[ "${PART}" == "a" ]]; then
    echo "=== exp10 Part A — buffer size sweep (${total} cells, J=${MAX_JOBS}) ==="
    echo "  buf_values: ${BUF_VALUES[*]}"
    echo "  fixed paths: ${FIXED_PATHS}"
else
    echo "=== exp10 Part B — EV domain sweep (${total} cells, J=${MAX_JOBS}) ==="
    echo "  ev_values: ${EV_VALUES[*]}"
    echo "  fixed buf_size: ${FIXED_BUF}"
fi
echo "  workloads: ${WORKLOADS[*]}"
echo "  sev: ${SEVERITIES[*]}"
echo "  seeds: ${SEEDS[*]}"
echo "  topology: ${TOPO##*/}"
echo ""
"${DRY_RUN}" && echo "[dry-run mode]"

# ── Main dispatch loop ──────────────────────────────────────────────────────────
for cell in "${CELLS[@]}"; do
    IFS='|' read -r axis_tag wname sev seed <<< "${cell}"

    while [[ "${active_jobs}" -ge "${MAX_JOBS}" ]]; do
        reaped=false
        for pid in "${!job_pids[@]}"; do
            if ! kill -0 "${pid}" 2>/dev/null; then
                report_job "${pid}"
                reaped=true
                break
            fi
        done
        "${reaped}" || sleep 1
    done

    run_cell_bg "${axis_tag}" "${wname}" "${sev}" "${seed}"
done

# ── Drain ───────────────────────────────────────────────────────────────────────
while [[ "${active_jobs}" -gt 0 ]]; do
    for pid in "${!job_pids[@]}"; do
        if ! kill -0 "${pid}" 2>/dev/null; then
            report_job "${pid}"
            break
        fi
    done
    sleep 1
done

new_runs=$(( done_count - skip_count - fail_count ))
echo ""
echo "Done. Total: ${done_count}  Skipped: ${skip_count}  New: ${new_runs}  Failed: ${fail_count}"
echo "Outputs under: ${OUT_ROOT}/part_${PART}/"
