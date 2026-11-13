#!/usr/bin/env python3
"""Queue-depth control of the 16-path N sweep: copies of the REPS and god configs at lat 8000 and 16000 (N = 400, 788) with a larger `-q` (4x = 404 and 8x = 808 packets).
alloc_queue() scales the queue size AND the ECN thresholds of a degraded link by its ratio, so with `-q Q`: 95% links hold 0.95 Q, 5% links 0.05 Q, healthy links Q; the ECN thresholds are
passed explicitly (-ecn 25 76) and do not change with -q. Names end in _lat<L> like the main configs: h512_p16_msgNhq404_lat16000 (REPS), h512_p16_msgNhGq404_lat16000 (god).
usage: python make_knee16_q_configs.py <configs_knee16.json> <out configs_knee16_q.json> <out bsmap_knee16_q.json>"""
import json, sys
src = {c["name"]: c for c in json.loads(open(sys.argv[1]).read())}
out, bsmap = [], {}
for arm, tag in (("h512_p16_msgNh", "h512_p16_msgNhq"), ("h512_p16_msgNhG", "h512_p16_msgNhGq")):
    for L in (8000, 16000):
        for q in (404, 808):
            c = json.loads(json.dumps(src[f"{arm}_lat{L}"]))
            c["name"] = f"{tag}{q}_lat{L}"; c["q"] = q
            c["note"] = f"queue-depth control: -q {q} (baseline 101); ECN thresholds unchanged"
            out.append(c); bsmap[c["name"]] = [32, 256]
open(sys.argv[2], "w").write(json.dumps(out)); open(sys.argv[3], "w").write(json.dumps(bsmap))
print(len(out), "configs")
