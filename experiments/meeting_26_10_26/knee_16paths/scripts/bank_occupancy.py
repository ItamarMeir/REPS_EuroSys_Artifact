#!/usr/bin/env python3
"""Bank occupancy replay from a -log_reps_bank file: per connection (conn column) valid slots = ADD - OVERWRITE - POP - EXPIRE
(the sim counts OVERWRITE only for valid slots: inserted + valid_at_start == popped + expired + overwritten + valid_at_end).
usage: bank_occupancy.py <size> <bank.csv[.gz]> ; prints max occupancy over all connections and times, the number of connections that reached it,
the cap-hit count (occupancy == size after an ADD), and the max over connections of hosts 0-15 (srcaddr < 16)."""
import csv, gzip, sys, collections
size, path = int(sys.argv[1]), sys.argv[2]
op = gzip.open if path.endswith(".gz") else open
occ = collections.defaultdict(int); mx = collections.defaultdict(int); neg = 0; caphit = 0; srcof = {}
d = {"ADD": 1, "OVERWRITE": -1, "POP": -1, "EXPIRE": -1}
with op(path, "rt", newline="") as f:
    for r in csv.DictReader(f):
        k = d.get(r["kind"])
        if k is None: continue
        c = r["conn"]; srcof[c] = int(r["srcaddr"])
        occ[c] += k
        if occ[c] < 0: neg += 1
        if occ[c] > mx[c]: mx[c] = occ[c]
        if k == 1 and occ[c] == size: caphit += 1
m = max(mx.values()); m16 = max((v for c, v in mx.items() if srcof[c] < 16), default=0)
hist = collections.Counter(mx.values())
print(f"size={size} conns={len(mx)} max_occupancy={m} conns_at_max={sum(1 for v in mx.values() if v == m)} cap_hits={caphit} negative_events={neg} max_hosts0-15={m16} median_conn_max={sorted(mx.values())[len(mx)//2]} final_occ_max={max(occ.values())}")
