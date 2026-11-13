#!/bin/bash
# Everything the graded page needs, in the container (/kneework16g), after the ladder is done. Sequential, under nice (memory is tight). Result dir /k16g_out, then copied to ../data/.
set -e
cd /kneework16g
O=/k16g_out
bash extract.sh /k16g_reps /k16g_god /k16g_sol $O "250 1000 4000 16000"
bash extract_dps.sh /k16g_dps $O
nice python3 n_bufstate.py /k16g_reps/traces $O/n_bufstate_reps.csv
nice python3 n_bufstate.py /k16g_god/traces $O/n_bufstate_god.csv
nice python3 n_evsends.py /k16g_reps/traces $O/n_evsends_reps.csv
nice python3 n_evsends.py /k16g_god/traces $O/n_evsends_god.csv
bash run_checks.sh > $O/identity_checks_final.log 2>&1 || true
echo EXTRACT_ALL_DONE
