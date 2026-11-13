#!/bin/bash
# Extraction of every table the page needs, from the traces / stdout / queue stats of the 16-path sweeps (run in the container, scripts next to this file in /kneework16).
# usage: bash extract.sh <reps out dir> <god out dir> <sol out dir> <result dir> "<latencies, e.g. 250 16000>"
# The result dir is then copied to knee_16paths/data/. Nothing here runs a simulation. Heavy parts run per latency, under nice.
set -e
cd /kneework16
R=$1; G=$2; S=$3; O=$4; LATS=$5
mkdir -p $O
cp $R/results.jsonl $O/n_results.jsonl
cp $G/results.jsonl $O/n_results_god.jsonl
python3 e_permessage.py 512 16 $O/n_permessage.csv $R/results.jsonl $R/traces
python3 e_permessage.py 512 16 $O/n_permessage_god.csv $G/results.jsonl $G/traces
python3 n_mech.py $R/traces $O/n_mech.csv
python3 n_mech_maxhost.py $R/traces $O/n_mech_maxhost.csv
python3 n_sol.py $S/traces $O/n_sol_sim.csv
for L in $LATS; do
  nice python3 n_warmup.py $R/traces $O/n_warm_$L.csv lat$L
  nice python3 n_uplink_mech.py $R/traces $O/n_um_$L.csv h512_p16_msgNh lat$L
  nice python3 n_uplink_mech.py $G/traces $O/n_um_god_$L.csv h512_p16_msgNhG lat$L
done
echo EXTRACT_DONE
