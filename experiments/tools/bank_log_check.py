#!/usr/bin/env python3
"""Independent replay checker for the REPS-Bank event log (-log_reps_bank) and BANK_STATS lines.

  bank_log_check.py --log bank.csv --stdout run.out --size 8 [--trace events.csv(.gz)] [--inject <kind>]

Replays every bank event against its own ring model (a deque in physical age order; independent of
bank_buffer.h) and checks, per flow:
  * ADD rows: raw_rtt <= target; REJ_RTT rows: raw_rtt > target.
  * OVERWRITE precedes the ADD that caused it, only when the ring is full, and names the oldest slot.
  * EXPIRE: slot is valid, is the first valid slot in age order, age strictly > timer.
  * POP: slot is the first valid slot in age order (so every older one was expired first), age <= timer,
         ev/insert-time match an earlier ADD, and a slot is never popped twice.
  * after a failed pop (EXPIRE rows, no POP) no valid slot remains.
  * timestamps never decrease.
  * BANK_STATS conservation per flow:  acks == no_sample+rej_ecn+rej_rtt+inserted
                                       inserted + valid_at_start == popped+expired+overwritten+valid_at_end
                                       (the bank is per connection: valid_at_start = slots inherited from the previous
                                       flow of the same src_dst; checked against the replay model)
    and the stats counters equal the row counts of the log.
  * with --trace: number of bank_pop SEND/RTX/RTS rows per src_id equals POP rows of that srcaddr
    (only for src_ids present in the trace).
--inject KIND corrupts the log in memory first (negative control); the checker must then FAIL:
  pop_ev | pop_age | drop_add | dup_pop | swap_order | stats | cross_conn
Exit 0 = all checks passed (or, with --inject, 0 only if the corruption was DETECTED -- printed as such).
"""
import argparse, collections, csv, gzip, re, sys


def load_rows(path):
    with open(path, newline="") as f:
        return [dict(r) for r in csv.DictReader(f)]


def parse_stats(stdout):
    out = []
    for ln in open(stdout, errors="replace"):
        if ln.startswith("BANK_STATS"):
            tk = ln.split()
            d = {tk[i]: int(tk[i + 1]) for i in range(1, len(tk) - 1, 2)}
            out.append(d)
    return out


def inject(rows, kind):
    rows = [dict(r) for r in rows]
    idx = lambda k: next(i for i, r in enumerate(rows) if r["kind"] == k)
    if kind == "pop_ev":
        rows[idx("POP")]["ev"] = str(int(rows[idx("POP")]["ev"]) ^ 1)
    elif kind == "pop_age":
        r = rows[idx("POP")]; r["ev_t_ps"] = str(max(0, int(r["ev_t_ps"]) - 10 ** 12))
    elif kind == "drop_add":
        del rows[idx("ADD")]
    elif kind == "dup_pop":
        i = idx("POP"); rows.insert(i + 1, dict(rows[i]))
    elif kind == "cross_conn":
        # attribute one ADD to a different connection: its ring never sees the slot, a later POP of it must then fail
        conns = sorted({r.get("conn", "") for r in rows})
        i = idx("ADD"); rows[i]["conn"] = conns[0] + "_x" if len(conns) < 2 else next(c for c in conns if c != rows[i].get("conn"))
    elif kind == "swap_order":
        pops = [i for i, r in enumerate(rows) if r["kind"] == "POP"]
        a, b = pops[0], pops[1]
        for k in ("ev", "ev_t_ps"):
            rows[a][k], rows[b][k] = rows[b][k], rows[a][k]
    return rows


def check(rows, size, stats, trace_pops):
    err = []
    def bad(m):
        if len(err) < 20: err.append(m)
    model = {}        # flow -> list of [ev, t, valid]
    pend_over = {}    # flow -> (ev, t) awaiting its ADD
    in_expire = {}    # flow -> True if previous row for flow was EXPIRE
    cnt = collections.defaultdict(collections.Counter)
    src_of = {}
    flows_of_conn = {}
    cnt_flow = collections.defaultdict(collections.Counter)   # per flow id (BANK_STATS counters are per flow)
    first_live, last_live = {}, {}
    end_of = {s["flowId"]: s["end_ps"] for s in stats if "end_ps" in s}
    late = collections.Counter()
    last_t = 0
    for n, r in enumerate(rows):
        k, t, flow_id, src, ev = r["kind"], int(r["t_ps"]), int(r["flow"]), int(r["srcaddr"]), int(r["ev"])
        fl = r.get("conn") or flow_id   # the bank is per connection (src_dst); old logs without `conn` key by flow id
        flows_of_conn.setdefault(fl, set()).add(flow_id)
        rtt, tgt, evt = int(r["raw_rtt_ps"]), int(r["target_ps"]), int(r["ev_t_ps"])
        if flow_id in end_of and t > end_of[flow_id]:
            # ACK that reached the flow after it finished (BANK_STATS already printed): it has no tx-bitmap sample, so it
            # can only be NOSAMPLE/REJ_*; it must not touch the bank, and it is excluded from the per-flow counters.
            if k in ("ADD", "POP", "EXPIRE", "OVERWRITE"): bad(f"row {n}: {k} for flow {flow_id} after its finish at {end_of[flow_id]}")
            else: late[k] += 1
            continue
        if n > 0:
            pf = prev_flow; last_live[pf] = sum(1 for s in model[prev_conn] if s[2])
        if t < last_t: bad(f"row {n}: time went backwards")
        last_t = t
        src_of[fl] = src
        dq = model.setdefault(fl, [])
        prev_flow, prev_conn = flow_id, fl
        cnt[fl][k] += 1
        cnt_flow[flow_id][k] += 1
        if flow_id not in first_live: first_live[flow_id] = sum(1 for s in dq if s[2])   # live slots before the flow's first event
        if in_expire.get(fl) and k not in ("EXPIRE", "POP"):
            if any(s[2] for s in dq): bad(f"row {n} flow {fl}: failed pop left a valid slot")
        in_expire[fl] = (k == "EXPIRE")
        if k == "ADD":
            if rtt > tgt: bad(f"row {n}: ADD with raw_rtt {rtt} > target {tgt}")
            if len(dq) == size:
                front = dq.pop(0)
                if front[2] and pend_over.get(fl) != (front[0], front[1]): bad(f"row {n}: ADD overwrote valid slot without OVERWRITE row")
                if not front[2] and fl in pend_over: bad(f"row {n}: OVERWRITE row but oldest slot was not valid")
            elif fl in pend_over: bad(f"row {n}: OVERWRITE while ring not full")
            pend_over.pop(fl, None)
            dq.append([ev, t, True])
        elif k == "OVERWRITE":
            if len(dq) != size: bad(f"row {n}: OVERWRITE while ring not full")
            elif not (dq[0][2] and dq[0][0] == ev and dq[0][1] == evt): bad(f"row {n}: OVERWRITE names {ev}@{evt}, oldest slot is {dq[0]}")
            pend_over[fl] = (ev, evt)
        elif k == "REJ_RTT":
            if rtt <= tgt: bad(f"row {n}: REJ_RTT with raw_rtt {rtt} <= target {tgt}")
        elif k in ("POP", "EXPIRE"):
            first = next((s for s in dq if s[2]), None)
            if first is None: bad(f"row {n}: {k} but no valid slot in model"); continue
            if first[0] != ev or first[1] != evt: bad(f"row {n}: {k} {ev}@{evt} is not the oldest valid slot {first[0]}@{first[1]}"); continue
            age = t - evt
            first[2] = False
            if k == "POP" and age > tgt: bad(f"row {n}: POP age {age} > timer {tgt}")
            if k == "EXPIRE" and age <= tgt: bad(f"row {n}: EXPIRE age {age} <= timer {tgt}")
    if rows: last_live[prev_flow] = sum(1 for s in model[prev_conn] if s[2])
    for fl, dq in model.items():
        if in_expire.get(fl) and any(s[2] for s in dq): bad(f"flow {fl}: failed pop at end left a valid slot")
    # conservation + counters-vs-log
    by_flow = {}
    for s in stats:
        by_flow[s["flowId"]] = s
        if s["acks"] != s["no_sample"] + s["rej_ecn"] + s["rej_rtt"] + s["inserted"]: bad(f"flow {s['flowId']}: ack classification not exhaustive {s}")
        vs = s.get("valid_at_start", 0)
        if s["inserted"] + vs != s["popped"] + s["expired"] + s["overwritten"] + s["valid_at_end"]: bad(f"flow {s['flowId']}: bank conservation broken {s}")
        c = cnt_flow.get(s["flowId"], collections.Counter())
        for key, kind in (("inserted", "ADD"), ("popped", "POP"), ("expired", "EXPIRE"), ("overwritten", "OVERWRITE"),
                          ("rej_ecn", "REJ_ECN"), ("rej_rtt", "REJ_RTT"), ("no_sample", "NOSAMPLE")):
            if c[kind] != s[key]: bad(f"flow {s['flowId']}: stats {key}={s[key]} but log has {c[kind]} {kind} rows")
        if s["flowId"] in first_live and first_live[s["flowId"]] != vs: bad(f"flow {s['flowId']}: model live slots at flow start {first_live[s['flowId']]} != stats valid_at_start {vs}")
        if s["flowId"] in last_live and last_live[s["flowId"]] != s["valid_at_end"]: bad(f"flow {s['flowId']}: model valid_at_end {last_live[s['flowId']]} != stats {s['valid_at_end']}")
    for fl in cnt_flow:
        if fl not in by_flow and stats: bad(f"flow {fl} has log rows but no BANK_STATS line (unfinished flow?)")
    if trace_pops is not None:
        log_pops = collections.Counter()
        for fl, c in cnt.items(): log_pops[src_of[fl]] += c["POP"]
        for src, n in trace_pops.items():
            if log_pops[src] != n: bad(f"srcaddr {src}: trace has {n} bank_pop sends but log has {log_pops[src]} POP rows")
    if late: print("late rows (after flow finish, excluded from per-flow counters): " + " ".join(f"{k}={v}" for k, v in sorted(late.items())))
    return err, sum(len(m) for m in model.values()), cnt


def trace_bank_pops(path):
    op = gzip.open if path.endswith(".gz") else open
    pops = collections.Counter(); srcs = set()
    with op(path, "rt") as f:
        rd = csv.DictReader(f)
        for r in rd:
            srcs.add(int(r["src_id"]))
            if r["event"] in ("SEND", "RTX", "RTS") and r.get("ev_src") == "bank_pop": pops[int(r["src_id"])] += 1
    return {s: pops[s] for s in srcs}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True); ap.add_argument("--stdout", required=True)
    ap.add_argument("--size", type=int, required=True); ap.add_argument("--trace")
    ap.add_argument("--inject", choices=["pop_ev", "pop_age", "drop_add", "dup_pop", "swap_order", "stats", "cross_conn"])
    a = ap.parse_args()
    rows = load_rows(a.log)
    if a.inject and a.inject != "stats": rows = inject(rows, a.inject)
    stats = parse_stats(a.stdout)
    if a.inject == "stats": stats[0]["inserted"] += 1   # corrupt one parsed BANK_STATS counter in memory
    tp = trace_bank_pops(a.trace) if a.trace else None
    err, nslots, cnt = check(rows, a.size, stats, tp)
    tot = collections.Counter()
    for c in cnt.values(): tot.update(c)
    print(f"rows={len(rows)} flows={len(cnt)} stats_lines={len(stats)} " + " ".join(f"{k}={v}" for k, v in sorted(tot.items())))
    if a.inject:
        print(f"inject={a.inject}: " + ("DETECTED (checker failed as it must) " + err[0] if err else "NOT DETECTED -- checker cannot fail!"))
        sys.exit(0 if err else 1)
    for m in err: print("FAIL:", m)
    print("PASS" if not err else f"FAIL ({len(err)}+ problems)")
    sys.exit(1 if err else 0)
