#!/usr/bin/env python3
"""Join the REPS-Bank log (-log_reps_bank) to the REPS event trace (-log_reps_events) and check what the bank logged against
what the trace says happened. bank_log_check.py only checks the bank log against itself; this checks its inputs.

  bank_trace_join.py --bank bank.csv --events events.csv(.gz) [--inject rtt|ecn|popsend|dropsend]

Both logs must come from the SAME run, and the trace must cover the sources you want checked (-log_reps_events_src <node_num>;
node_num = flowId - 1 for the flows of these experiments). Rows of sources that are not in the trace are skipped and counted.

Checks, per traced source:
  * every ACK-derived bank row (ADD / REJ_ECN / REJ_RTT / NOSAMPLE) matches exactly one ACK row of the trace with the same
    srcaddr, the same time (ps) and the same echoed EV;
  * ECN: REJ_ECN <=> that ACK row has ecn=1; ADD and REJ_RTT <=> ecn=0;
  * RTT: for ADD / REJ_ECN / REJ_RTT the logged raw_rtt_ps equals (ACK time - time of the latest SEND/RTX/RTS of the same
    seqno before that ACK) within 1 ps (trace times are printed in ns with 3 decimals);
  * NOSAMPLE: the ACK's seqno was acked before, or never sent in the trace (informational counts);
  * POP rows <-> send rows with ev_src == bank_pop (SEND/RTX/RTS): same srcaddr, same time (ps), same EV, one-to-one both ways;
  * no ADD row for an ACK whose seqno has no SEND/RTX/RTS record (an RTT sample cannot exist without a send).
--inject KIND corrupts the bank log in memory first (negative control); the join must then FAIL.
Exit 0 = all checks passed (with --inject: 0 only if the corruption was detected).
"""
import argparse, collections, csv, gzip, sys


def open_text(path):
    return gzip.open(path, "rt", newline="") if path.endswith(".gz") else open(path, newline="")


def ps(ns_str):
    # time_ns is printed as %.3f of now/1000.0 -> exact picoseconds
    return int(round(float(ns_str) * 1000.0))


def load_trace(path):
    acks = collections.defaultdict(list)                  # (srcaddr, t_ps, ev) -> [row]
    sends = collections.defaultdict(list)                 # (src_id, seqno) -> [(t_ps, kind)] in file order
    bank_sends = collections.defaultdict(list)            # (srcaddr, t_ps, ev) -> [row]
    srcs, node_to_addr, order = set(), {}, 0
    ack_seen = collections.defaultdict(list)              # (src_id, seqno) -> [t_ps] of earlier ACKs
    for r in csv.DictReader(open_text(path)):
        sa, ni, t, k = int(r["srcaddr"]), int(r["src_id"]), ps(r["time_ns"]), r["event"]
        srcs.add(sa); node_to_addr[ni] = sa
        if k in ("SEND", "RTX", "RTS"):
            sends[(ni, int(r["seqno"]))].append((t, k))
            if r["ev_src"] == "bank_pop":
                bank_sends[(sa, t, int(r["ev"]))].append(r)
        elif k == "ACK":
            row = dict(r); row["_t"] = t; row["_ni"] = ni; row["_prior"] = len(ack_seen[(ni, int(r["seqno"]))])
            ack_seen[(ni, int(r["seqno"]))].append(t)
            acks[(sa, t, int(r["ev"]))].append(row)
    return acks, sends, bank_sends, srcs


def inject(rows, kind, srcs):
    rows = [dict(r) for r in rows]
    # corrupt a row of a TRACED source (rows of untraced sources are skipped by the join)
    nxt = lambda k: next(i for i, r in enumerate(rows) if r["kind"] == k and int(r["srcaddr"]) in srcs)
    if kind == "rtt":
        r = rows[nxt("ADD")]; r["raw_rtt_ps"] = str(int(r["raw_rtt_ps"]) + 5000)
    elif kind == "ecn":
        rows[nxt("ADD")]["kind"] = "REJ_ECN"
    elif kind == "popsend":
        r = rows[nxt("POP")]; r["ev"] = str(int(r["ev"]) ^ 1)
    elif kind == "dropsend":
        del rows[nxt("POP")]
    return rows


def check(rows, acks, sends, bank_sends, srcs):
    err = []
    def bad(m):
        if len(err) < 20: err.append(m)
    st = collections.Counter()
    pop_rows = collections.defaultdict(int)
    for n, r in enumerate(rows):
        sa = int(r["srcaddr"])
        if sa not in srcs: st["skipped_untraced_src"] += 1; continue
        k, t, ev, rtt = r["kind"], int(r["t_ps"]), int(r["ev"]), int(r["raw_rtt_ps"])
        if k in ("POP",):
            key = (sa, t, ev); pop_rows[key] += 1
            st["pop_rows_checked"] += 1
            if len(bank_sends.get(key, [])) < pop_rows[key]: bad(f"row {n}: POP ev {ev} at {t} ps has no bank_pop send row in the trace")
            continue
        if k in ("EXPIRE", "OVERWRITE"): continue
        cand = acks.get((sa, t, ev), [])
        if len(cand) != 1:
            bad(f"row {n}: {k} at {t} ps ev {ev}: {len(cand)} matching ACK rows in the trace (expected exactly 1)"); continue
        a = cand[0]; st["ack_rows_joined"] += 1
        ecn = int(a["ecn"])
        if k == "REJ_ECN" and ecn != 1: bad(f"row {n}: REJ_ECN but trace ACK ecn={ecn}")
        if k in ("ADD", "REJ_RTT") and ecn != 0: bad(f"row {n}: {k} but trace ACK ecn={ecn}")
        if k in ("ADD", "REJ_ECN", "REJ_RTT"):
            seq = int(a["seqno"]); sd = [x for x in sends.get((a["_ni"], seq), []) if x[0] <= t]
            if not sd: bad(f"row {n}: {k} for seqno {seq} but no SEND/RTX/RTS record before the ACK"); continue
            expect = t - sd[-1][0]
            if abs(expect - rtt) > 1: bad(f"row {n}: {k} raw_rtt {rtt} != trace ACK-SEND {expect} (seqno {seq})")
            else: st["rtt_exact"] += 1
        else:  # NOSAMPLE
            seq = int(a["seqno"])
            st["nosample_prior_ack" if a["_prior"] > 0 else "nosample_first_ack"] += 1
            if a["_prior"] == 0 and sends.get((a["_ni"], seq)): st["nosample_first_ack_but_sent"] += 1
    for key, lst in bank_sends.items():
        if sa_ok := key[0] in srcs:
            if pop_rows.get(key, 0) != len(lst): bad(f"trace has {len(lst)} bank_pop sends at {key[1]} ps ev {key[2]} src {key[0]} but the bank log has {pop_rows.get(key, 0)} POP rows")
    st["bank_pop_sends_in_trace"] = sum(len(v) for v in bank_sends.values())
    return err, st


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", required=True); ap.add_argument("--events", required=True); ap.add_argument("--inject")
    a = ap.parse_args()
    rows = [dict(r) for r in csv.DictReader(open(a.bank, newline=""))]
    acks, sends, bank_sends, srcs = load_trace(a.events)
    if a.inject: rows = inject(rows, a.inject, srcs)
    err, st = check(rows, acks, sends, bank_sends, srcs)
    print("traced srcaddrs=%d " % len(srcs) + " ".join(f"{k}={v}" for k, v in sorted(st.items())))
    if a.inject:
        print(f"inject={a.inject}: " + ("DETECTED (join failed as it must) " + err[0] if err else "NOT DETECTED -- join cannot fail!"))
        sys.exit(0 if err else 1)
    for m in err: print("FAIL:", m)
    print("PASS" if not err else f"FAIL ({len(err)}+ problems)")
    sys.exit(1 if err else 0)
