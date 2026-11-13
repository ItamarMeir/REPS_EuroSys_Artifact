#!/bin/bash
# Queue-depth control (README, section Queue-depth control). Run in the container m23-dev:
#   docker exec -d m23-dev sh -c 'bash /kneework16/run_q_control.sh > /k16q_ladder.log 2>&1'
# 8 configs (REPS and god, lat 8000 and 16000, -q 404 and 808) x B 32, 256 x seeds 42, 43 = 32 cells (two seeds: the user asked for a quick test); resumable. Separate output dirs per arm (msgNh is a substring of msgNhG).
cd /kneework16
mkdir -p /k16q_reps /k16q_god
nice python3 run_knee16.py --out /k16q_reps --cfgs $(for L in 8000 16000; do for Q in 404 808; do echo h512_p16_msgNhq${Q}_lat$L; done; done) --seeds 42 43 --bsmap bsmap_knee16_q.json --workers 4
nice python3 run_knee16.py --out /k16q_god --cfgs $(for L in 8000 16000; do for Q in 404 808; do echo h512_p16_msgNhGq${Q}_lat$L; done; done) --seeds 42 43 --bsmap bsmap_knee16_q.json --workers 4
echo Q_LADDER_DONE
