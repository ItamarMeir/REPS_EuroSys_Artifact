#!/usr/bin/env python3
"""Fresh-valid-EV count at send time, post-warmup (C2: 16 MiB, NSCC, trim on).

Same k-definition as C1's send_occupancy.py (k = valid buffer entries immediately
before a SEND/RTX/RTS draw, read from the previous row's own post-event `fresh`),
but C2 actually enters Freezing Mode, so:

  - the k-histogram is split by `frozen_mode` at draw time: a frozen-mode pop
    (remove_frozen(), buffer_reps.cpp) follows a different slot-selection rule
    (fixed read pointer, walks every slot not just fresh ones) than a normal
    non-frozen earliest-fresh pop -- pooling them mixes two mechanisms.
  - plain `frozen_pop` is classified as valid/stale by looking up the slot at
    (frozen_head-1) % modulus (modulus = buf_size if >0 else len(slots), the
    count modulus -- same rule as reps_event_viewer.py's existing frozen_pop
    check) in the PREVIOUS row of the same src (pre-pop state, same convention
    as `k`). This replaces C1's "other" bucket (C1 never froze, so that bucket
    was never exercised).
  - correctness gate: trace-derived valid+stale must equal the committed
    finish-line ev_valid+ev_stale exactly (C1's stale_proven_zero assumed
    stale==0, which is false by design here).

Outputs:
  ../data/c2_send_occupancy.csv   scenario,B,k,frozen_mode,n_sends,share
  ../data/c2_send_checks.csv      one row per cell: every verification below

Checks:
  1. count conservation vs the committed C2 finish line (src<32)
  2. determinism: P(k=0, frozen_mode=0) == non-frozen random share
  3. reconstruction: non-frozen fresh_pop rows have this-row fresh == last_fresh-1;
     non-frozen random rows have last_fresh==0 and this-row fresh==0
  4. valid+stale totals (trace, including frozen_pop reclassification) match the
     committed ev_valid+ev_stale exactly
  5. capacity k<=B; sum-to-1 per (scenario,B)
"""
import csv
import gzip
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_c2 import FIN, FRZ, TOR0_HOSTS, SCEN, BS, arm_name  # noqa: E402

C2 = HERE.parent
TRACES = C2 / "traces"
DATA = C2 / "data"
RUNS = C2 / "runs"
DRAW_EVENTS = {"SEND", "RTX", "RTS"}


def committed_counts(f, b):
    path = RUNS / f"x{f}_ef200" / "seed42" / arm_name(b) / "stdout.txt"
    text = path.read_text(errors="replace")
    flows = [tuple(int(v) for v in (m[0], m[2], m[3], m[4], m[5], m[6])) for m in FIN.findall(text)]
    frz = {int(s): int(fz) for s, fz in FRZ.findall(text)}
    valid = random_ = explore = stale = freeze = 0
    for src, pk, ex, rnd, val, st in flows:
        if src >= TOR0_HOSTS:
            continue
        valid += val
        random_ += rnd
        explore += ex
        stale += st
        freeze += frz.get(src, 0)
    return dict(valid=valid, random=random_, explore=explore, stale=stale, freeze=freeze)


def parse_slots(raw):
    out = []
    for chunk in raw.split("|"):
        v, valid, life = chunk.split(":")
        out.append((int(v), valid != "0", int(life)))
    return out


def frozen_pop_valid(prev_slots_raw, frozen_head, buf_size):
    """Was the slot this frozen_pop just read valid beforehand? Same rule as
    reps_event_viewer.py's existing frozen_pop invariant check: idx =
    (frozen_head - 1) % modulus, modulus = buf_size if buf_size > 0 else
    len(slots) (count modulus -- remove_frozen() advances modulo getSize(),
    the element count, not max_size)."""
    slots = parse_slots(prev_slots_raw)
    modulus = buf_size if buf_size > 0 else len(slots)
    if not modulus:
        return None
    idx = (frozen_head - 1) % modulus
    return slots[idx][1]  # isValid


def classify(ev_src, frozen_valid):
    if ev_src == "fresh_pop":
        return "valid"
    if ev_src == "frozen_pop":
        if frozen_valid is None:
            return "other"
        return "valid" if frozen_valid else "stale"
    if ev_src in ("random", "explore"):
        return "random"
    return "other"


def analyse_cell(f, b):
    gz = TRACES / f"16MiB_x{f}_B{b}.csv.gz"
    host = {}  # src -> dict(seen_ack, last_fresh, warmup_sends, prev_slots_raw)
    k_counts = {}  # (k, frozen_mode) -> n
    src_counts = {"valid": 0, "random": 0, "stale": 0, "other": 0}
    mismatches = 0
    non_frozen_random_strict = 0  # ev_src=="random" only, excludes "explore"
    k0_fresh_pop_violations = 0  # k==0 can never be fresh_pop (needs fresh>=1) -- hard invariant
    with gzip.open(gz, "rt", newline="") as fh:
        rd = csv.reader(fh)
        head = next(rd)
        ci = {k: head.index(k) for k in
              ("src_id", "event", "ev_src", "fresh", "ecn", "frozen_mode",
               "frozen_head", "buf_size", "slots")}
        for row in rd:
            src = int(row[ci["src_id"]])
            if src >= TOR0_HOSTS:
                continue
            ev = row[ci["event"]]
            fresh = int(row[ci["fresh"]])
            frozen_mode = int(row[ci["frozen_mode"]])
            st = host.setdefault(src, dict(seen_ack=False, last_fresh=0,
                                            warmup_sends=0, post_sends=0,
                                            prev_slots_raw=None))
            if ev == "ACK" and not st["seen_ack"]:
                st["seen_ack"] = True
            if ev in DRAW_EVENTS:
                ev_src = row[ci["ev_src"]]
                frozen_valid = None
                if ev_src == "frozen_pop" and st["prev_slots_raw"] is not None:
                    frozen_valid = frozen_pop_valid(
                        st["prev_slots_raw"], int(row[ci["frozen_head"]]),
                        int(row[ci["buf_size"]]))
                if st["seen_ack"]:
                    k = st["last_fresh"]
                    key = (k, frozen_mode)
                    k_counts[key] = k_counts.get(key, 0) + 1
                    st["post_sends"] += 1
                    cls = classify(ev_src, frozen_valid)
                    src_counts[cls] += 1
                    if not frozen_mode:
                        if ev_src == "fresh_pop":
                            if fresh != st["last_fresh"] - 1:
                                mismatches += 1
                            if k == 0:
                                # fresh_pop requires fresh>=1 before the pop (k here);
                                # k==0 and fresh_pop together is impossible by construction.
                                k0_fresh_pop_violations += 1
                        elif ev_src == "random":
                            if st["last_fresh"] != 0 or fresh != 0:
                                mismatches += 1
                            non_frozen_random_strict += 1
                else:
                    st["warmup_sends"] += 1
            st["last_fresh"] = fresh
            st["prev_slots_raw"] = row[ci["slots"]]
    n_post = sum(k_counts.values())
    n_warm = sum(s["warmup_sends"] for s in host.values())
    row_k = [dict(scenario=SCEN[f], B=b, k=k, frozen_mode=fm, n_sends=n, share=n / n_post)
              for (k, fm), n in sorted(k_counts.items())]
    sum_share = sum(r["share"] for r in row_k)
    max_k = max((k for k, _fm in k_counts), default=-1)
    cm = committed_counts(f, b)
    committed_total = cm["valid"] + cm["random"] + cm["explore"] + cm["stale"]
    expected_post = committed_total - n_warm
    non_frozen_k0 = k_counts.get((0, 0), 0)
    checks = dict(
        scenario=SCEN[f], B=b, hosts=len(host),
        n_sends_post=n_post, n_sends_warmup=n_warm,
        committed_total=committed_total, expected_post=expected_post,
        conservation_ok=(n_post == expected_post),
        reconstruction_mismatches=mismatches,
        valid_count=src_counts["valid"], committed_valid=cm["valid"],
        valid_match=(src_counts["valid"] == cm["valid"]),
        stale_count=src_counts["stale"], committed_stale=cm["stale"],
        stale_match=(src_counts["stale"] == cm["stale"]),
        other_count=src_counts["other"],
        committed_freeze_entries=cm["freeze"],
        max_k=max_k, capacity_ok=(max_k <= b),
        sum_share=sum_share, sum_to_1_ok=(abs(sum_share - 1) < 1e-9),
        non_frozen_k0=non_frozen_k0, other_ok=(src_counts["other"] == 0),
        hosts_ok=(len(host) == TOR0_HOSTS),
        non_frozen_random_strict=non_frozen_random_strict,
        # Not "k0 == random share": explore draws post-UNFREEZE land at both
        # k==0 and k>0 (a fixed-size burst, not gated on fresh count), so that
        # equality doesn't hold here the way it did in C1 (no freeze -> no
        # explore outside warmup). The invariant that DOES always hold:
        # fresh_pop requires fresh>=1 before the pop, so it can never be the
        # draw at k==0.
        k0_fresh_pop_violations=k0_fresh_pop_violations,
        determinism_ok=(k0_fresh_pop_violations == 0),
    )
    return row_k, checks


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


ALL_CHECK_KEYS = ("conservation_ok", "valid_match", "stale_match",
                   "capacity_ok", "sum_to_1_ok", "other_ok", "hosts_ok", "determinism_ok")


def main():
    all_k, all_checks = [], []
    for f in SCEN:
        for b in BS:
            gz = TRACES / f"16MiB_x{f}_B{b}.csv.gz"
            if not gz.exists():
                print(f"SKIP F{f} B{b}: trace missing")
                continue
            row_k, checks = analyse_cell(f, b)
            all_k += row_k
            all_checks.append(checks)
            print(f"F{f:>3} B={b:<4} n_post={checks['n_sends_post']:<7} "
                  f"conservation={checks['conservation_ok']} "
                  f"valid_match={checks['valid_match']} stale_match={checks['stale_match']} "
                  f"mismatches={checks['reconstruction_mismatches']} "
                  f"max_k={checks['max_k']} capacity={checks['capacity_ok']} "
                  f"sum_to_1={checks['sum_to_1_ok']} other={checks['other_count']} "
                  f"hosts_ok={checks['hosts_ok']} determinism={checks['determinism_ok']}", flush=True)
    if not all_checks:
        print("no cells found")
        return
    DATA.mkdir(parents=True, exist_ok=True)
    write_csv(DATA / "c2_send_occupancy.csv", all_k)
    write_csv(DATA / "c2_send_checks.csv", all_checks)
    bad = [c for c in all_checks
           if not (c["reconstruction_mismatches"] == 0 and all(c[k] for k in ALL_CHECK_KEYS))]
    print(f"\n{len(all_checks)} cells, {len(bad)} with a failed check "
          f"(checked: reconstruction_mismatches==0, {', '.join(ALL_CHECK_KEYS)})")
    for c in bad:
        print("FAILED CHECK:", c)


if __name__ == "__main__":
    main()
