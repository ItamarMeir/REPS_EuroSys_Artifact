#!/bin/bash
# Extraction of the REPS-Bank arm (run in dps-dev, scripts in /kneework16b). usage: bash extract_bank.sh <result dir>   (then docker cp / cat the files to knee_16paths/data/)
# Writes bank_permessage_<arm>.csv, bank_results_<arm>.jsonl, bank_cells_<arm>.csv, bank_check.log (replay checker on seed 42 of every arm and latency, conservation + replay, trace cross-check).
set -e
cd /kneework16b
O=${1:-/k16_bank_out}; mkdir -p $O
for arm in auto tight; do
  R=/k16_bank_$arm
  cp $R/results.jsonl $O/bank_results_$arm.jsonl
  python3 e_permessage.py 512 16 $O/bank_permessage_$arm.csv $R/results.jsonl $R/traces
  nice python3 bank_summary.py $R/traces $O/bank_cells_$arm.csv h512_p16_msgNhBk$arm > /dev/null
done
: > $O/bank_check.log
for arm in auto tight; do
  for L in 250 500 1000 2000 4000 8000 16000; do
    c=h512_p16_msgNhBk${arm}_lat${L}_B8_s42; T=/k16_bank_$arm/traces
    [ -f $T/$c.bank.csv.gz ] || continue
    zcat $T/$c.bank.csv.gz > /tmp/chk_bank.csv
    echo "== $c" >> $O/bank_check.log
    nice python3 /workspace/experiments/tools/bank_log_check.py --log /tmp/chk_bank.csv --stdout $T/$c.stdout.txt --size 8 >> $O/bank_check.log 2>&1 || echo "CHECK_FAILED $c" >> $O/bank_check.log
  done
done
rm -f /tmp/chk_bank.csv
echo EXTRACT_BANK_DONE
