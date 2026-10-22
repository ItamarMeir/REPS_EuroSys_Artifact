#!/usr/bin/env bash
# E6 follow-up: build data/e6lp/inst from data/e6/inst with LP-optimal rho_max (inst.json rho_max/ideal replaced).
# Inside container ofan-dev. Env: PS, SEEDS, PAR.
set -uo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); EXP=$(dirname "$HERE")
PS=${PS:-"0.5 2"}; SEEDS=${SEEDS:-"1 2 3 4 5 6 7 8 9 10"}; PAR=${PAR:-4}
for p in $PS; do for s in $SEEDS; do echo "$p $s"; done; done | xargs -P "$PAR" -L1 bash -c '
p=$0; s=$1; src='"$EXP"'/data/e6/inst/p${p}_s$s; dst='"$EXP"'/data/e6lp/inst/p${p}_s$s
mkdir -p "$dst"; cp "$src"/fail.txt "$src"/wl.cm "$dst"/
python3 '"$HERE"'/lp_rho.py "$src" >/dev/null
python3 - "$src" "$dst" <<PY
import json,sys
o=json.load(open(sys.argv[1]+"/inst.json")); l=json.load(open(sys.argv[1]+"/inst_lp.json"))
o["rho_max"]=l["rho_max"]; o["ideal_cct_increase_pct"]=l["ideal_cct_increase_pct"]; o["rho_equal"]=l["rho_equal"]
json.dump(o,open(sys.argv[2]+"/inst.json","w"))
PY
echo "$p $s"'
