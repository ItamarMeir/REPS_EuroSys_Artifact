#!/usr/bin/env python3
"""Items 1 and 2 of the N sweep on the 16-path fabric, from the event traces (run in the container). ONE traced pass per cell holds hosts 0-15 (all degraded hosts of ToR0) of all four messages
(src_id = message * HOSTS + host), for both arms (REPS = cfg h512_p16g_msgNh_*, god = h512_p16g_msgNhG_*).
For every cell and every message m = 1..4, the degraded host (0-15) with the LARGEST FCT ("max") and the one with the SMALLEST FCT ("best") are taken (FCTs from the stdout, same parsing as e_permessage.py).
Per (cfg, B, seed, msg, role) the flow's transmissions (SEND + RTX) are split by
  phase  w = warmup (message 1 only: sends before the first fresh_pop send, that send excluded), p = everything else
  class  b = 5% uplink (ev % 16 even, SRv6: path j = ToR0 uplink j), g = 95% uplink
  source r = random draw, f = fresh_pop (recycled), o = anything else
and every answer (ACK with ecn 0 / ecn 1, NACK = trim) is attributed to the phase and class of the transmission it answers: the latest transmission of the same (seqno, EV). The answer row carries the EV of the transmitted packet (checked: per flow and EV, answers == transmissions, 1024 of 1024 pairs).
FIXED 2026-11-08: the first version keyed the transmission by seqno alone, so a NACK or ACK that arrived after a retransmission of the same seqno was credited to the class of the retransmission (33% of the NACKs of a lat 16000 cell); the class-specific trim and ECN numbers were wrong at large N.
Columns: <phase><class>_<src> sends; <phase><class>_a0 / _a1 / _nk answers; hist_<phase>_<ev> sends per EV 0..15.
usage: python n_uplink_mech.py <traces dir> <out.csv> <cfg prefix, e.g. h512_p16g_msgNh or h512_p16g_msgNhG> [latency selector, e.g. lat250]"""
import csv, gzip, re, sys
from pathlib import Path
import params as Pm
DIR, OUT, PFX = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
SEL = sys.argv[4] if len(sys.argv) > 4 else ""
csv.field_size_limit(10 ** 8)


def fcts(stdout):
    f = {}
    for l in Path(stdout).read_text(errors="ignore").splitlines():
        mm = re.search(r"flowId (\d+) .*uecSrc (\d+) finished at ([0-9.]+)", l)
        if mm and l.startswith("Flow"):
            f[((int(mm.group(1)) - 1) // Pm.HOSTS, int(mm.group(2)) % Pm.HOSTS)] = float(mm.group(3))
    return f


def new():
    d = {}
    for ph in "wp":
        for c in "bg":
            for s in "rfo":
                d[f"{ph}{c}_{s}"] = 0
            for a in ("a0", "a1", "nk"):
                d[f"{ph}{c}_{a}"] = 0
        for e in range(Pm.P):
            d[f"hist_{ph}_{e}"] = 0
    return d


def scan(trace, want):
    """want: set of src_id; returns {src_id: counters}"""
    out = {sid: new() for sid in want}
    done = {sid: sid >= Pm.HOSTS for sid in want}          # warmup only in message 1 (flow ids below HOSTS)
    last = {sid: {} for sid in want}
    with gzip.open(trace, "rt") as fh:
        for r in csv.DictReader(fh):
            sid = int(r["src_id"])
            if sid not in want:
                continue
            ev, o = r["event"], out[sid]
            if ev in ("SEND", "RTX"):
                e = int(r["ev"]) % Pm.P
                if not done[sid] and ev == "SEND" and r["ev_src"] == "fresh_pop":
                    done[sid] = True
                ph = "p" if done[sid] else "w"
                c = "b" if Pm.is_bad_ev(e) else "g"
                s = {"random": "r", "fresh_pop": "f"}.get(r["ev_src"], "o")
                o[f"{ph}{c}_{s}"] += 1
                o[f"hist_{ph}_{e}"] += 1
                last[sid][(int(r["seqno"]), e)] = (ph, c)
            elif ev in ("ACK", "NACK"):
                k = last[sid].get((int(r["seqno"]), int(r["ev"]) % Pm.P))
                if k is None:
                    continue
                a = "nk" if ev == "NACK" else ("a1" if r["ecn"] == "1" else "a0")
                o[f"{k[0]}{k[1]}_{a}"] += 1
    return out


rows = []
for p in sorted(DIR.glob("*.stdout.txt")):
    mt = re.match(re.escape(PFX) + r"_(lat\d+)_B(\d+)_s(\d+)\.stdout\.txt", p.name)
    if not mt or SEL not in mt.group(1):
        continue
    lat, B, seed = mt.group(1), int(mt.group(2)), int(mt.group(3))
    F = fcts(p)
    want = {}
    for m in range(Pm.MSGS):
        v = {h: t for (mg, h), t in F.items() if mg == m and h < Pm.NH}
        if len(v) < Pm.NH:
            continue
        for role, h in (("max", max(v, key=v.get)), ("best", min(v, key=v.get))):
            want.setdefault(m * Pm.HOSTS + h, (m, [], v))[1].append(role)     # one host can be both roles when all FCTs tie
    res = scan(DIR / f"{PFX}_{lat}_B{B}_s{seed}.csv.gz", set(want))
    for sid, (m, roles, v) in want.items():
        h = sid % Pm.HOSTS
        for role in roles:
            rows.append(dict(cfg=f"{PFX}_{lat}", B=B, seed=seed, msg=m + 1, role=role, host=h, fct=v[h], fct_spread=max(v.values()) - min(v.values()), **res[sid]))
with open(OUT, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
print(len(rows), "rows")
