#!/bin/bash
# REPS-Bank arm on the 5/95 16-path sweep: B = 8, bank 8, timer = 1 unloaded RTT; target arms auto and tight (unloaded RTT + 0.5 us, from the pilot floors); 3 seeds (42-44), 7 latencies.
# Run in dps-dev next to run_knee16.py (/kneework16b): docker exec -d dps-dev sh -c 'bash /kneework16b/run_bank16.sh > /k16_bank.log 2>&1'. Resumable. 2 workers up to 4 us, 1 above (the graded sweep shares the 7.8 GB container).
cd /kneework16b
for L in 250 500 1000 2000 4000 8000 16000; do
  W=2; [ $L -gt 4000 ] && W=1
  for arm in auto tight; do
    nice python3 run_knee16.py --out /k16_bank_$arm --cfgs h512_p16_msgNhBk${arm}_lat$L --seeds 42 43 44 --bsmap bsmap_knee16_bank.json --workers $W
  done
done
echo BANK16_DONE
