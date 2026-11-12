#!/usr/bin/env python3
"""Fresh-valid-EV count at send time, post-warmup (16 MiB, seed 42, trim on).

For every SEND/RTX/RTS row (the only rows that carry ev_src -- a real EV draw) at or
after a host's first ACK: k = the number of valid buffer entries IMMEDIATELY BEFORE
this send. k is read from the PREVIOUS row's own `fresh` column for that host (fresh
is logged post-event, so the previous row's post-event value is this row's pre-event
state) -- not from this row's own `fresh`, which is already post-pop.

Warmup ends at a host's first ACK row, in file order (column `n`, the same order the
rows are read in). Only src < 32 (ToR0) is read -- the traces were captured with
-log_reps_events_src 0..31, so that is already everything in the file.

Single streaming pass per trace (gzip.open + csv.reader), O(1) state per host. Traces
are the 18 *.csv.gz already in ../traces/ -- no new simulation is run here.

Outputs:
  ../data/c1_send_occupancy.csv   long format: scenario,B,k,n_sends,share
  ../data/c1_send_checks.csv      one row per cell: every verification below

Checks (see RESULTS.md for the reasoning):
  1. count conservation vs the committed C1 finish line (src<32)
  2. determinism: P(k=0) == post-warmup random share, exactly
  3. reconstruction: fresh_pop rows have this-row fresh == last_fresh-1;
     random rows have last_fresh == 0 and this-row fresh == 0 -- 0 mismatches required
  4. stale == 0, proven from freeze_entries (committed) and frozen_pop row count (trace),
     not assumed
  5. how many hosts had an ECN-marked first ACK (affects the warmup boundary)
"""
import csv
import gzip
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import occupancy as O  # noqa: E402  (BS, SCEN-like x values)
from build_c1 import FIN, TOR0_HOSTS, SIZE  # noqa: E402  (reuse the exact same regex/consts)

CC = "mprdma"  # set from --cc in main()


def arm_name(b):
    return f"reps_b{b}" + ("_nscc" if CC == "nscc" else "")


def cc_label():
    return "MPRDMA" if CC == "mprdma" else "NSCC"


def _dirs():
    c1 = HERE.parent
    return c1 / cc_label() / "traces", c1 / cc_label() / "data"


def load_max_fresh_backlog():
    """scenario-name,B -> max_fresh_backlog, from occupancy.py's independent trace pass.
    Used as a cross-check: every post-warmup send's k is a backlog-state value, so
    max(k) over sends must be <= this (sampled over all rows, not just send rows)."""
    _, data_dir = _dirs()
    out = {}
    with open(data_dir / "c1_occupancy.csv", newline="") as f:
        for r in csv.DictReader(f):
            out[(SCEN[int(r["x"])], int(r["B"]))] = int(r["max_fresh_backlog"])
    return out

RUNS = Path("/workspace/experiments/exp30_packet_trimming_en/runs/a1") \
    if Path("/workspace").exists() else HERE.parent.parent.parent / "exp30_packet_trimming_en" / "runs" / "a1"
SCEN = {0: "healthy", 32: "32 ToR0 uplinks at 50%"}
DRAW_EVENTS = {"SEND", "RTX", "RTS"}
MAX_FRESH_BACKLOG = {}  # set in main(), read in analyse_cell


def committed_counts(x, b):
    """(ev_valid, ev_random, ev_explore, ev_stale, freeze_entries) summed over src<32,
    parsed from the committed C1 stdout -- the same file occupancy.py cross-checked
    against. freeze_entries is parsed separately since FIN (build_c1) doesn't capture it."""
    path = RUNS / str(SIZE) / f"x{x}_ef200" / "seed42" / arm_name(b) / "stdout.txt"
    text = path.read_text(errors="replace")
    # FIN groups: src, fct(float, unused here), packets, explore, random, valid, stale
    flows = []
    for m in FIN.findall(text):
        src, _fct, pk, ex, rnd, val, st = m
        flows.append(tuple(int(v) for v in (src, pk, ex, rnd, val, st)))
    frz_re = re.compile(r"uecSrc (\d+) finished at.*?freeze_entries (\d+)")
    frz = {int(s): int(f) for s, f in frz_re.findall(text)}
    valid = random_ = explore = stale = freeze = 0
    seen = set()
    for src, pk, ex, rnd, val, st in flows:
        if src >= TOR0_HOSTS:
            continue
        valid += val
        random_ += rnd
        explore += ex
        stale += st
        freeze += frz.get(src, 0)
        seen.add(src)
    present = {s for s in frz if s < TOR0_HOSTS}
    assert present >= seen, (
        f"x{x} B{b}: freeze_entries regex matched {len(present)} ToR0 hosts, "
        f"need all {len(seen)} seen in finish lines -- regex likely broken")
    return dict(valid=valid, random=random_, explore=explore, stale=stale, freeze=freeze)


def classify(ev_src):
    if ev_src == "fresh_pop" or ev_src == "frozen_pop_valid":
        return "valid"
    if ev_src == "frozen_pop_stale":
        return "stale"
    if ev_src in ("random", "explore"):
        return "random"
    return "other"  # plain "frozen_pop" (non-dual algo, ambiguous without slot parsing);
    # expected never to occur here since freeze_entries == 0 (trim on, no RTO) -- checked below


def analyse_cell(x, b):
    traces_dir, _ = _dirs()
    gz = traces_dir / f"16MiB_x{x}_B{b}.csv.gz"
    host = {}  # src -> dict(seen_ack, last_fresh, warmup_sends, post_sends)
    k_counts = {}
    src_counts = {"valid": 0, "random": 0, "stale": 0, "other": 0}
    mismatches = 0
    frozen_pop_rows = 0
    ecn_first_ack = 0
    with gzip.open(gz, "rt", newline="") as f:
        rd = csv.reader(f)
        head = next(rd)
        ci = {k: head.index(k) for k in ("src_id", "event", "ev_src", "fresh", "ecn")}
        for row in rd:
            src = int(row[ci["src_id"]])
            if src >= TOR0_HOSTS:
                continue
            ev = row[ci["event"]]
            fresh = int(row[ci["fresh"]])
            st = host.setdefault(src, dict(seen_ack=False, last_fresh=0,
                                            warmup_sends=0, post_sends=0))
            if ev == "ACK" and not st["seen_ack"]:
                st["seen_ack"] = True
                if row[ci["ecn"]] == "1":
                    ecn_first_ack += 1
            if ev in DRAW_EVENTS:
                ev_src = row[ci["ev_src"]]
                if ev_src == "frozen_pop":
                    frozen_pop_rows += 1
                if st["seen_ack"]:
                    k = st["last_fresh"]
                    k_counts[k] = k_counts.get(k, 0) + 1
                    st["post_sends"] += 1
                    cls = classify(ev_src)
                    src_counts[cls] += 1
                    if ev_src == "fresh_pop":
                        if fresh != st["last_fresh"] - 1:
                            mismatches += 1
                    elif ev_src == "random":
                        if st["last_fresh"] != 0 or fresh != 0:
                            mismatches += 1
                else:
                    st["warmup_sends"] += 1
            st["last_fresh"] = fresh
    n_post = sum(k_counts.values())
    n_warm = sum(s["warmup_sends"] for s in host.values())
    row_k = [dict(scenario=SCEN[x], B=b, k=k, n_sends=n, share=n / n_post)
              for k, n in sorted(k_counts.items())]
    sum_share = sum(r["share"] for r in row_k)
    max_k = max(k_counts) if k_counts else -1
    mfb = MAX_FRESH_BACKLOG.get((SCEN[x], b))
    cm = committed_counts(x, b)
    committed_total = cm["valid"] + cm["random"] + cm["explore"] + cm["stale"]
    expected_post = committed_total - n_warm
    checks = dict(
        scenario=SCEN[x], B=b, hosts=len(host),
        n_sends_post=n_post, n_sends_warmup=n_warm,
        committed_total=committed_total, expected_post=expected_post,
        conservation_ok=(n_post == expected_post),
        p_k0=k_counts.get(0, 0) / n_post if n_post else float("nan"),
        random_share=src_counts["random"] / n_post if n_post else float("nan"),
        determinism_ok=(k_counts.get(0, 0) == src_counts["random"]),
        reconstruction_mismatches=mismatches,
        valid_count=src_counts["valid"], committed_valid=cm["valid"],
        valid_match=(src_counts["valid"] == cm["valid"]),
        stale_count=src_counts["stale"], committed_stale=cm["stale"],
        committed_freeze_entries=cm["freeze"],
        frozen_pop_rows_trace=frozen_pop_rows,
        stale_proven_zero=(cm["freeze"] == 0 and frozen_pop_rows == 0 and src_counts["stale"] == 0),
        other_count=src_counts["other"],
        other_ok=(src_counts["other"] == 0),
        hosts_ok=(len(host) == TOR0_HOSTS),
        ecn_first_ack_hosts=ecn_first_ack,
        max_k=max_k, capacity_ok=(max_k <= b),
        sum_share=sum_share, sum_to_1_ok=(abs(sum_share - 1) < 1e-9),
        max_fresh_backlog=mfb, k_le_max_fresh_backlog_ok=(max_k <= mfb if mfb is not None else None),
    )
    return row_k, checks


def write_csv(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


ALL_CHECK_KEYS = (
    "conservation_ok", "determinism_ok", "stale_proven_zero", "valid_match",
    "other_ok", "hosts_ok", "capacity_ok", "sum_to_1_ok", "k_le_max_fresh_backlog_ok",
)


def main():
    global MAX_FRESH_BACKLOG, CC
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--cc", choices=["mprdma", "nscc"], default="mprdma")
    args = ap.parse_args()
    CC = args.cc
    traces_dir, data_dir = _dirs()
    MAX_FRESH_BACKLOG = load_max_fresh_backlog()
    all_k, all_checks = [], []
    for x in (0, 32):
        for b in O.BS:
            gz = traces_dir / f"16MiB_x{x}_B{b}.csv.gz"
            if not gz.exists():
                print(f"SKIP x{x} B{b}: trace missing")
                continue
            row_k, checks = analyse_cell(x, b)
            all_k += row_k
            all_checks.append(checks)
            print(f"x{x:>2} B={b:<4} n_post={checks['n_sends_post']:<7} "
                  f"conservation={checks['conservation_ok']} "
                  f"determinism={checks['determinism_ok']} "
                  f"mismatches={checks['reconstruction_mismatches']} "
                  f"stale_proven_zero={checks['stale_proven_zero']} "
                  f"max_k={checks['max_k']} capacity={checks['capacity_ok']} "
                  f"sum_to_1={checks['sum_to_1_ok']} "
                  f"max_k<=backlog_max={checks['k_le_max_fresh_backlog_ok']}", flush=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    write_csv(data_dir / "c1_send_occupancy.csv", all_k)
    write_csv(data_dir / "c1_send_checks.csv", all_checks)
    bad = [c for c in all_checks
           if not (c["reconstruction_mismatches"] == 0
                    and all(c[k] for k in ALL_CHECK_KEYS))]
    print(f"\n{len(all_checks)} cells, {len(bad)} with a failed check "
          f"(checked: reconstruction_mismatches==0, {', '.join(ALL_CHECK_KEYS)})")
    for c in bad:
        print("FAILED CHECK:", c)


if __name__ == "__main__":
    main()
