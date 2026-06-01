#!/usr/bin/env bash
# Paper 2 Fig 4 with REAL per-host mixed LB:
#   - elephant senders (per-seed, determined from .cm) override → ECMP
#   - global LB = OBLIVIOUS (OPS) for the 124 sprayed senders
# This reproduces the paper's "ECMP elephants + OPS sprayed" REGIME using the
# new -host_lb_overrides flag. Compares against the existing OPS-via-threshold
# diagnostic and the default REPS run.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib_common.sh"

# Identify elephant hosts per seed from the .cm files (size = 64 MB)
declare -A ELEPHANTS
for s in 42 43 44; do
    ELEPHANTS[$s]=$(awk '/size 67108864/ {split($1,p,"->"); print p[1]}' \
        "$WL_DIR/paper_baseline_s${s}.cm" | sort -n | uniq | \
        awk '{printf "%s:ecmp,",$1}' | sed 's/,$//')
done

run_mixed() {
    local cca="$1" seed="$2"
    local outfile="$DATA_DIR/p2_fig04mix_${cca}_s${seed}.out"
    if [[ -f "$outfile" ]]; then
        echo "[skip] $(basename "$outfile")" ; return 0
    fi
    local tm="$WL_DIR/paper_baseline_s${seed}.cm"
    local override="${ELEPHANTS[$seed]}"
    echo "[run-mix] $cca s$seed  override=$override"

    # Drop -ecmp_elephant_threshold from BASE_P2_128, set global LB = oblivious,
    # and add per-host override for the 4 elephant senders → ECMP.
    local base="${BASE_P2_128/-ecmp_elephant_threshold 33554432/}"
    # shellcheck disable=SC2086
    (cd "$REPO_ROOT/htsim/sim/datacenter" && \
     "$BIN" $base -load_balancing_algo oblivious -sender_cc_algo "$cca" \
        -seed "$seed" -tm "$tm" \
        -host_lb_overrides "$override") > "$outfile" 2>&1
}

for s in 42 43 44; do
    for cca in swift lswift mswift nscc mnscc; do
        run_mixed "$cca" "$s"
    done
done
echo "[done] paper2_fig04_mixedLB"
