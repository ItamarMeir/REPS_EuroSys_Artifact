#!/usr/bin/env python3
"""Items 1 and 2 of the N-sweep follow-up, from the existing traces (run in the container).
For every cell and every message m = 1..4, the degraded host (0-7) with the LARGEST FCT ("max") and the one with the SMALLEST FCT ("best") are taken (FCTs from the stdout, same parsing as n_mech_maxhost.py).
Message 1 comes from the msgN traces (hosts 0-7 traced), messages 2-4 from the msgNh traces (hosts 0-7 traced; twin run, identical FCTs).
Per (cfg, B, seed, msg, role) the flow's transmissions (SEND + RTX) are split by
  phase  w = warmup (message 1 only: sends before the first fresh_pop send, that send excluded), p = everything else
  class  b = 5% uplink (ev % 8 even, SRv6: path j = ToR0 uplink j), g = 95% uplink
  source r = random draw, f = fresh_pop (recycled), o = anything else
and every answer (ACK with ecn 0 / ecn 1, NACK = trim) is attributed to the phase, class and source of the LATEST transmission of that seqno.
Columns: <phase><class>_<src> sends; <phase><class>_a0 / _a1 / _nk answers; hist_<phase>_<ev> sends per EV 0..7.
usage: python n_uplink_mech.py <msgN dir> <msgNh dir> <out.csv> [cfg_substring]
       python n_uplink_mech.py --god <msgNhG dir> <out.csv> [cfg_substring]   (god-mode cells: ONE trace holds hosts 0-7 of all four messages, cfg h128_p8_msgNhG_*)"""
import csv, gzip, re, sys
from pathlib import Path
GOD = sys.argv[1] == "--god"
if GOD:
    DN = DH = Path(sys.argv[2]); OUT = sys.argv[3]; SEL = sys.argv[4] if len(sys.argv) > 4 else ""
else:
    DN, DH, OUT = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    SEL = sys.argv[4] if len(sys.argv) > 4 else ""
PFX = "h128_p8_msgNhG" if GOD else "h128_p8_msgN"
csv.field_size_limit(10 ** 8)


def fcts(stdout):
    f = {}
    for l in Path(stdout).read_text(errors="ignore").splitlines():
        mm = re.search(r"flowId (\d+) .*uecSrc (\d+) finished at ([0-9.]+)", l)
        if mm and l.startswith("Flow"):
            f[((int(mm.group(1)) - 1) // 128, int(mm.group(2)) % 128)] = float(mm.group(3))
    return f


def new():
    d = {}
    for ph in "wp":
        for c in "bg":
            for s in "rfo":
                d[f"{ph}{c}_{s}"] = 0
            for a in ("a0", "a1", "nk"):
                d[f"{ph}{c}_{a}"] = 0
        for e in range(8):
            d[f"hist_{ph}_{e}"] = 0
    return d


def scan(trace, want, first_msg):
    """want: {src_id: (msg, role)}; returns {src_id: counters}"""
    out = {sid: new() for sid in want}
    done = {sid: sid >= 128 for sid in want}              # warmup only in message 1 (flow ids below 128)
    last = {sid: {} for sid in want}
    with gzip.open(trace, "rt") as fh:
        for r in csv.DictReader(fh):
            sid = int(r["src_id"])
            if sid not in want:
                continue
            ev, o = r["event"], out[sid]
            if ev in ("SEND", "RTX"):
                e = int(r["ev"]) % 8
                if not done[sid] and ev == "SEND" and r["ev_src"] == "fresh_pop":
                    done[sid] = True
                ph = "p" if done[sid] else "w"
                c = "b" if e % 2 == 0 else "g"
                s = {"random": "r", "fresh_pop": "f"}.get(r["ev_src"], "o")
                o[f"{ph}{c}_{s}"] += 1
                o[f"hist_{ph}_{e}"] += 1
                last[sid][int(r["seqno"])] = (ph, c)
            elif ev in ("ACK", "NACK"):
                k = last[sid].get(int(r["seqno"]))
                if k is None:
                    continue
                a = "nk" if ev == "NACK" else ("a1" if r["ecn"] == "1" else "a0")
                o[f"{k[0]}{k[1]}_{a}"] += 1
    return out


rows = []
for p in sorted(DN.glob("*.stdout.txt")):
    mt = re.match(PFX + r"_(lat\d+)_B(\d+)_s(\d+)\.stdout\.txt", p.name)
    if not mt or SEL not in mt.group(1):
        continue
    lat, B, seed = mt.group(1), int(mt.group(2)), int(mt.group(3))
    base = f"{lat}_B{B}_s{seed}"
    fN = fcts(p)
    fH = fcts(DH / f"h128_p8_msgNh_{base}.stdout.txt") if not GOD else fN
    parts = ((True, fN, DN / f"{PFX}_{base}.csv.gz", (0, 1, 2, 3)),) if GOD else ((True, fN, DN / f"h128_p8_msgN_{base}.csv.gz", (0,)), (False, fH, DH / f"h128_p8_msgNh_{base}.csv.gz", (1, 2, 3)))
    for first, F, trace, msgs in parts:
        want = {}
        for m in msgs:
            v = {h: t for (mg, h), t in F.items() if mg == m and h < 8}
            if len(v) < 8:
                continue
            for role, h in (("max", max(v, key=v.get)), ("best", min(v, key=v.get))):
                want.setdefault(m * 128 + h, (m, [], v))[1].append(role)    # one host can be both roles when all FCTs tie
        res = scan(trace, {sid: None for sid in want}, first)
        for sid, (m, roles, v) in want.items():
            h = sid % 128
            for role in roles:
                rows.append(dict(cfg=f"{PFX}_{lat}", B=B, seed=seed, msg=m + 1, role=role, host=h, fct=v[h], fct_spread=max(v.values()) - min(v.values()), **res[sid]))
with open(OUT, "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
print(len(rows), "rows")
