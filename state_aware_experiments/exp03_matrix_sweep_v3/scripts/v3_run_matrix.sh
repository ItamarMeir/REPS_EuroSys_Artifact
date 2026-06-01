#!/bin/bash
# v3 design-matrix driver — state-aware NSCC+REPS sweep.
#
# Iterates workloads × severities × modes × seeds and writes outputs under
# <exp03>/runs/. Idempotent: skips cells whose .out file already ends with a
# completion marker.
#
# Paths are resolved relative to this script's location, so the script is
# usable from anywhere as long as the repo layout is intact.

set -u
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${EXP_DIR}/../.." && pwd)"
HTSIM_DIR="${REPO_ROOT}/htsim/sim/datacenter"
HTSIM="${HTSIM_DIR}/htsim_uec"
TOPO="${HTSIM_DIR}/topologies/reps/fat_tree_128_1os_3t_400g.topo"
WORKLOADS_DIR="${REPO_ROOT}/state_aware_experiments/workloads"

OUT_ROOT="${EXP_DIR}/runs"
mkdir -p "${OUT_ROOT}"

# Common simulator flags (workload + seed appended per-cell).
# -disable_tor_ecn is CRITICAL: without it, -sender_cc_only flips
# receiver_driven=false and ECN gets re-enabled on ToR downlinks at
# main_uec.cpp:739. See ../README.md for the methodology lesson.
COMMON_FLAGS=(
  -sack_threshold 4000
  -end 5000
  -paths 65535
  -sender_cc_only
  -sender_cc_algo nscc
  -topo "${TOPO}"
  -linkspeed 400000
  -ecn 25 76
  -q 100
  -cwnd 151
  -load_balancing_algo freezing
  -exit_freeze 200000000
  -disable_tor_ecn
)

# Workload table: NAME -> TM file path
declare -A WORKLOADS=(
  [pureperm]="${HTSIM_DIR}/connection_matrices/perm_n128_s8388608.cm"
  [mice]="${WORKLOADS_DIR}/mice_heavy.cm"
  [elephant]="${WORKLOADS_DIR}/elephant_heavy.cm"
  [composite]="${WORKLOADS_DIR}/composite.cm"
)

SEVERITIES=(0 1 2 4 8)
MODES=(vanilla stateaware)
SEEDS=(20 21 22 23 24)

total=0; done_count=0; skipped=0
start_time=$(date +%s)
for wname in "${!WORKLOADS[@]}"; do
  tm="${WORKLOADS[$wname]}"
  for sev in "${SEVERITIES[@]}"; do
    for mode in "${MODES[@]}"; do
      for seed in "${SEEDS[@]}"; do
        total=$((total+1))
        outdir="${OUT_ROOT}/${wname}/${mode}/sev${sev}"
        mkdir -p "${outdir}"
        outfile="${outdir}/seed${seed}.out"

        if [ -f "${outfile}" ] && tail -1 "${outfile}" 2>/dev/null | grep -q "^Done\|New: 0"; then
          skipped=$((skipped+1))
          continue
        fi

        cli=("${HTSIM}" "${COMMON_FLAGS[@]}" -tm "${tm}" -seed "${seed}")
        if [ "${mode}" = "stateaware" ]; then
          cli+=(-state_aware_ecn)
        fi
        if [ "${sev}" -gt 0 ]; then
          cli+=(-fail_link_time 50 200)
          for ((i=0; i<sev; i++)); do
            cli+=(-fail_link_target "${i}" "${i}")
          done
        fi

        cell_start=$(date +%s)
        "${cli[@]}" > "${outfile}" 2>&1
        rc=$?
        cell_dur=$(( $(date +%s) - cell_start ))
        done_count=$((done_count+1))
        elapsed=$(( $(date +%s) - start_time ))
        echo "[${done_count}/${total}] ${wname}/${mode}/sev${sev}/seed${seed} rc=${rc} cell=${cell_dur}s elapsed=${elapsed}s"
      done
    done
  done
done
echo "DONE. total=${total} ran=${done_count} skipped=${skipped} elapsed_total=$(( $(date +%s) - start_time ))s"
