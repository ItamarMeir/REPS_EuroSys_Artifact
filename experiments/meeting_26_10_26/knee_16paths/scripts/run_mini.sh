#!/bin/bash
# Mini-sweep gate of the 16-path study (plan phase 2): 2 latencies x 3 B x 2 seeds, both arms, plus the speed-of-light cells. Run in the container (m23-dev), outputs /k16_mini_*.
cd /kneework16
for arm in msgNh msgNhG; do
  nice python3 run_knee16.py --out /k16_mini_$arm --cfgs h512_p16_${arm}_lat250 h512_p16_${arm}_lat16000 --seeds 42 43 --bsmap bsmap_mini.json --workers 4
done
nice python3 run_knee16.py --out /k16_mini_sol --cfgs h512_p16_sol_lat250 h512_p16_sol1p_lat250 h512_p16_sol_lat16000 h512_p16_sol1p_lat16000 --seeds 42 43 --bsmap bsmap_mini.json --workers 4
echo MINI_DONE
