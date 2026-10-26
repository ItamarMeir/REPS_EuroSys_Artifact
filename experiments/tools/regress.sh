#!/usr/bin/env bash
# Regression check: old vs new htsim_uec binary on one cell (caller supplies the cell).
#   regress.sh <old_binary> <new_binary> -- <htsim_uec args...>
# Run INSIDE the Docker container (see skill build-htsim). Call once per cell; choose cells
# that exercise the code path you touched, and use paths that exist in the container.
# Passes only if (1) the 'finished at' flow-finish lines of old and new are identical and
# (2) a second run of the new binary reproduces its first run exactly (determinism).
# Each run uses a private scratch cwd so logout.dat is not shared or left in the repo.
# Exit 0 = pass, 1 = flow-finish lines differ, 2 = new binary nondeterministic, 3 = usage / no flows.
set -euo pipefail
[ $# -ge 4 ] && [ "$3" = "--" ] || { sed -n '2,3p' "$0"; exit 3; }
OLD=$(realpath "$1"); NEW=$(realpath "$2"); shift 3
S=$(mktemp -d); trap 'rm -rf "$S"' EXIT
run() { # $1=binary $2=outfile, rest = htsim_uec args
  local bin=$1 out=$2; shift 2
  local d; d=$(mktemp -d -p "$S")
  ( cd "$d" && "$bin" "$@" > "$out.full" 2>&1 ) || { echo "run failed: $bin"; tail -5 "$out.full"; exit 3; }
  grep 'finished at' "$out.full" > "$out" || true
}
run "$OLD" "$S/old.fin" "$@"
run "$NEW" "$S/new.fin" "$@"
run "$NEW" "$S/new2.fin" "$@"
N=$(wc -l < "$S/new.fin")
[ "$N" -gt 0 ] || { echo "no 'finished at' lines: cell does not finish any flow"; exit 3; }
cmp -s "$S/new.fin" "$S/new2.fin" || { echo "NONDETERMINISTIC: new binary differs between two identical runs"; exit 2; }
if ! diff -q "$S/old.fin" "$S/new.fin" > /dev/null; then
  echo "DIFFERENT: $(diff "$S/old.fin" "$S/new.fin" | grep -c '^[<>]') differing flow-finish lines (old '<', new '>'):"
  diff "$S/old.fin" "$S/new.fin" | head -6 | cut -c1-200
  exit 1
fi
echo "IDENTICAL: $N flow-finish lines, new binary deterministic"
