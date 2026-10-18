#!/usr/bin/env python3
"""C1.1 combined payload: a_i and k distributions across the rate sweep
(REPS = -load_balancing_algo freezing) plus the path_static (collision-free,
reconstructed k) reference. See plan + advisor notes in
c11_pathstatic_compare.py for the reconstruction method and its caveats.
"""
from __future__ import annotations

import json
from pathlib import Path

from c11_pathstatic_compare import (
    load_by_src, per_host_sequences, event_level_k, B_CAP, RUNS, DRAW as DRAW_SET,
)

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"

CELLS = [
    # (dir_name, label, window_bound, fixed_q_note)
    # 100G: fixedq_cwnd90 (fixed Q=101) beats BDP-scaled cwnd36 (lower FCT,
    # ~2785s vs ~2834s, non-window-bound) -- BDP-scaled cwnd36 cell dropped.
    ("100g_fixedq_cwnd90", "REPS 100G (cwnd90, fixed Q=101)", False, True),
    ("200g_cwnd66", "REPS 200G (cwnd66, BDP-scaled Q, window-bound)", True, False),
    ("400g_cwnd127", "REPS 400G (cwnd127)", False, False),
    ("800g_cwnd249", "REPS 800G (cwnd249)", False, False),
]


def hist(values) -> dict:
    c: dict[int, int] = {}
    for v in values:
        c[v] = c.get(v, 0) + 1
    n = len(values)
    return {str(k): v / n for k, v in sorted(c.items())}


def main() -> None:
    out = {"cells": []}
    for dirname, label, window_bound, fixed_q in CELLS:
        path = RUNS / dirname / "events.csv"
        by_src = load_by_src(path)
        seqs = per_host_sequences(by_src)
        a_all = [a for d in seqs.values() for a in d["a"]]
        k_all = [k for d in seqs.values() for k in d["k"]]
        out["cells"].append(dict(
            dir=dirname, label=label, window_bound=window_bound, fixed_q=fixed_q,
            a_hist=hist(a_all), k_hist=hist(k_all),
            n=len(a_all),
        ))
        print(f"{label}: n={len(a_all)} mean_a={sum(a_all)/len(a_all):.3f} "
              f"mean_k={sum(k_all)/len(k_all):.3f}")

    # Gate: event-level k rule vs REPS's own real measured k (full event
    # order, no aggregation, no seed parameter -- k=0 is a hard initial
    # condition). Must be 0 mismatches, including pre-warmup rows, before
    # trusting it on path_static (which has no real k to compare against).
    frz_by_src_raw = load_by_src(RUNS / "400g_cwnd127" / "events.csv")
    n_checked = n_mismatch = 0
    for src, rows in frz_by_src_raw.items():
        rows = sorted(rows, key=lambda r: int(r["n"]))
        pred, _ = event_level_k(rows, B_CAP)
        last_fresh = 0
        measured = []
        for r in rows:
            if r["event"] in DRAW_SET:
                measured.append(last_fresh)
            last_fresh = int(r["fresh"])
        for p, m in zip(pred, measured):
            n_checked += 1
            if p != m:
                n_mismatch += 1

    # path_static: k a REPS buffer WOULD hold if driven by path_static's
    # own ACK stream (counterfactual, not a measurement -- path_static has
    # no real buffer). Post-warmup only, matching every other cell here.
    ps_by_src_raw = load_by_src(RUNS / "400g_pathstatic_cwnd127" / "events.csv")
    ps_a_all, ps_k_all = [], []
    ps_seqs = per_host_sequences(ps_by_src_raw)
    for d in ps_seqs.values():
        ps_a_all += d["a"]
    for src, rows in ps_by_src_raw.items():
        rows = sorted(rows, key=lambda r: int(r["n"]))
        pred, post_warmup = event_level_k(rows, B_CAP)
        ps_k_all += [k for k, pw in zip(pred, post_warmup) if pw]

    out["path_static"] = dict(
        label="path_static 400G -- counterfactual REPS-buffer k under its ACK stream",
        a_hist=hist(ps_a_all), k_hist=hist(ps_k_all),
        gate_mismatches=n_mismatch, gate_checked=n_checked,
        n=len(ps_a_all),
    )
    print(f"path_static: n={len(ps_a_all)} mean_a={sum(ps_a_all)/len(ps_a_all):.3f} "
          f"mean_k_counterfactual={sum(ps_k_all)/len(ps_k_all):.3f} "
          f"gate={n_mismatch}/{n_checked}")

    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "combined.json").write_text(json.dumps(out), encoding="utf-8")
    print("wrote", DATA / "combined.json")


if __name__ == "__main__":
    main()
