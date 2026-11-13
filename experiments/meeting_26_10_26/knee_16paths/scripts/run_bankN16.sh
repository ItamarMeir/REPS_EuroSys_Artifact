#!/bin/bash
# Bank size = N variant, one seed (42): both target arms in parallel (1 worker each), per latency. Run in dps-dev next to run_knee16.py (/kneework16b). Resumable.
cd /kneework16b
for L in 250 500 1000 2000 4000 8000 16000; do
  for arm in auto tight; do
    nice python3 run_knee16.py --out /k16_bankN_$arm --cfgs h512_p16_msgNhBkN${arm}_lat$L --seeds 42 --bsmap bsmap_knee16_bankN.json --workers 1 &
  done
  wait
done
echo BANKN16_DONE
