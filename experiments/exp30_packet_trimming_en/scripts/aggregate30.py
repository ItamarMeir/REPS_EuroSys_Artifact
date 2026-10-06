#!/usr/bin/env python3
"""
exp30_packet_trimming_en aggregator -- parse flow-finish lines into tidy CSVs.
(same aggregation logic as exp30_concentrated_path_loss/scripts/aggregate30.py;
trim mode has no effect on flow-finish-line parsing.)

  data/fct.csv         : (part, size, x, ef, arm, group, buf_size,
                          p50/p90/p95/p99/max FCT us + _ci)
  data/diagnostics.csv : (part, size, x, ef, arm, group, buf_size,
                          per-host means: ecn/rto/rts/fast_loss, freeze entries
                          + host fraction + mean freeze us, ev_random/ev_explore,
                          ev_random_rate = (random+explore)/pkt + _ci)
  data/resolvable.csv  : (part, size, x, ef, group, metric, best/worst B + vals
                          + CI, spread, ci_sum, resolvable) -- does any B ordering
                          survive the 95% CI? n=3 seeds (t-mult 4.30).

x = the sweep point: a1 -> # degraded ToR0 uplinks; a2 -> degradation %;
    b  -> # of ToR0's 32 uplinks permanently (statically) killed outright.

group (uniform across parts): affected = senders under ToR0 (src < 32),
unaffected = the rest. Part B used to define "affected" as a single poisoned
source under the old `-fail_src_paths` mechanism; now that Part B is a real
ToR-wide kill (same blast radius as Part A), the grouping is identical.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR = SCRIPT_DIR.parent
RUNS = EXP_DIR / "runs"
DATA = EXP_DIR / "data"
END_US = 90000.0   # -end; an affected flow that never finishes is censored here
#                    (exp26 aggregate.py:31 bias note: dropping it instead biases
#                    the percentiles DOWN, understating exactly the worst arm)

HOSTS_PER_TOR = 32

FIN_RE = re.compile(
    r"Flow\s+\S+\s+flowId\s+\d+\s+uecSrc\s+(?P<src>\d+)\s+finished at\s+(?P<fct>[\d.eE+-]+)\s+"
    r"flowSize\s+\d+\s+total packets\s+(?P<pkts>\d+).*?"
    r"\bRTS\s+(?P<rts>\d+)\b.*?"
    r"\becn_acks\s+(?P<ecn>\d+)\b.*?"
    r"\brtos\s+(?P<rtos>\d+)\b.*?"
    r"\bfreeze_entries\s+(?P<frz>\d+)\b.*?"
    r"\bfreeze_us\s+(?P<frz_us>[\d.eE+-]+).*?"
    r"\bev_explore\s+(?P<ev_explore>\d+)\b.*?"
    r"\bev_random\s+(?P<ev_random>\d+)\b.*?"
    # c1-ev-source-split: optional, so runs made before these counters still parse
    r"(?:\bev_valid\s+(?P<ev_valid>\d+)\b.*?\bev_stale\s+(?P<ev_stale>\d+)\b.*?)?"
    r"\bfast_loss\s+(?P<fast_loss>\d+)\b")

FCT_COLS = ["p50_fct_us", "p90_fct_us", "p95_fct_us", "p99_fct_us", "max_fct_us"]
DIAG_COLS = ["ecn_per_host", "rto_per_host", "rts_per_host", "fast_loss_per_host",
             "freeze_entries_per_host", "freeze_hosts_frac", "freeze_us_mean",
             "ev_random_per_host", "ev_explore_per_host", "ev_random_rate",
             # per-packet EV source split: fractions of all EV draws, sum to 1
             "ev_valid_per_host", "ev_stale_per_host",
             "valid_frac", "random_frac", "stale_frac"]


def _source_split(gg: pd.DataFrame) -> dict:
    """EV-source split for one (run, group). Denominator is ALL EV draws of the
    group: valid + random + stale, so valid_frac + random_frac + stale_frac == 1.
    random = ev_random + ev_explore (explore is counted in ev_explore, not in
    ev_random). NaN when the run predates the c1 counters."""
    out = dict(ev_valid_per_host=np.nan, ev_stale_per_host=np.nan,
               valid_frac=np.nan, random_frac=np.nan, stale_frac=np.nan)
    if gg.ev_valid.isna().any():
        return out
    rnd = gg.ev_random + gg.ev_explore
    total = float((gg.ev_valid + rnd + gg.ev_stale).sum())
    out["ev_valid_per_host"] = float(gg.ev_valid.mean())
    out["ev_stale_per_host"] = float(gg.ev_stale.mean())
    if total > 0:
        out["valid_frac"] = float(gg.ev_valid.sum()) / total
        out["random_frac"] = float(rnd.sum()) / total
        out["stale_frac"] = float(gg.ev_stale.sum()) / total
    return out


def _ci95(v: np.ndarray) -> float:
    v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    n = len(v)
    if n < 2:
        return 0.0
    return float(sp_stats.t.ppf(0.975, n - 1) * v.std(ddof=1) / np.sqrt(n))


def _cell_key(path: Path):
    # runs/<part>/<size>/x<X>_ef<EF>/seed<seed>/<arm>/stdout.txt
    part, size, xdir, seeddir, arm = path.parts[-6:-1]
    x = int(xdir.split("_")[0][1:])
    ef = int(xdir.split("_ef")[1])
    seed = int(seeddir.replace("seed", ""))
    return part, int(size), x, ef, seed, arm


def _buf_size(arm: str) -> int:
    # leading digits after "reps_b" -- tolerates a trailing "_dual" suffix
    # (dual_mprdma_reps CC variant, same buffer size, see common30.base_flags)
    return int(re.match(r"reps_b(\d+)", arm).group(1))


def _cc(arm: str) -> str:
    if arm.endswith("_dual_cap"):
        return "dual_mprdma_reps_cap"
    if arm.endswith("_dual"):
        return "dual_mprdma_reps"
    if arm.endswith("_nscc"):
        return "nscc"
    return "mprdma"


def _group_of(part: str, src: int) -> str:
    return "affected" if src < HOSTS_PER_TOR else "unaffected"


def _collapse(frame: pd.DataFrame, keys: list[str], cols: list[str]) -> pd.DataFrame:
    out = frame.groupby(keys, as_index=False)[cols].mean()
    ci = frame.groupby(keys)[cols].agg(_ci95).reset_index()
    for c in cols:
        out[c + "_ci"] = ci[c].values
    out["n_seed"] = frame.groupby(keys)["seed"].nunique().values
    out["buf_size"] = out["arm"].map(_buf_size)
    out["cc"] = out["arm"].map(_cc)
    return out


def _resolvable(agg: pd.DataFrame, group_keys: list[str],
                metrics: list[str]) -> pd.DataFrame:
    """Best (min-mean) and worst (max-mean) B per metric; resolvable iff the mean
    gap exceeds the sum of the two 95% CI half-widths. All metrics lower-better."""
    rows = []
    for kv, g in agg.groupby(group_keys):
        kv = kv if isinstance(kv, tuple) else (kv,)
        for m in metrics:
            gg = g[g[m].notna()]
            if gg.empty:
                continue
            b = gg.loc[gg[m].idxmin()]
            w = gg.loc[gg[m].idxmax()]
            spread = float(w[m] - b[m])
            ci_sum = float(b[m + "_ci"] + w[m + "_ci"])
            rows.append({**dict(zip(group_keys, kv)), "metric": m,
                         "best_b": int(b.buf_size), "best_val": round(float(b[m]), 3),
                         "best_ci": round(float(b[m + "_ci"]), 3),
                         "worst_b": int(w.buf_size), "worst_val": round(float(w[m]), 3),
                         "worst_ci": round(float(w[m + "_ci"]), 3),
                         "spread": round(spread, 3), "ci_sum": round(ci_sum, 3),
                         "resolvable": bool(spread > ci_sum)})
    return pd.DataFrame(rows)


def _flow_rows(runs: Path):
    fct_rows, diag_rows = [], []
    for sp in sorted(runs.rglob("stdout.txt")):
        part, size, x, ef, seed, arm = _cell_key(sp)
        per = []
        for m in FIN_RE.finditer(sp.read_text(errors="replace")):
            g = m.groupdict()
            src = int(g["src"])
            per.append(dict(
                src=src, group=_group_of(part, src),
                fct_us=float(g["fct"]), pkts=int(g["pkts"]), rts=int(g["rts"]),
                ecn=int(g["ecn"]), rtos=int(g["rtos"]), frz=int(g["frz"]),
                frz_us=float(g["frz_us"]), ev_explore=int(g["ev_explore"]),
                ev_random=int(g["ev_random"]), fast_loss=int(g["fast_loss"]),
                # NaN for runs made before the c1 counters existed
                ev_valid=int(g["ev_valid"]) if g["ev_valid"] is not None else np.nan,
                ev_stale=int(g["ev_stale"]) if g["ev_stale"] is not None else np.nan))
        if not per:
            print(f"  WARN 0 flows: {sp}")
            continue
        d = pd.DataFrame(per)
        present_aff = set(d.loc[d.group == "affected", "src"])
        missing = sorted(set(range(HOSTS_PER_TOR)) - present_aff)
        if missing:
            print(f"  CENSORED {'/'.join(sp.parts[-6:-1])}: ToR0 src {missing} "
                  f"did not finish by {END_US:.0f} us -- FCT censored at -end")
            d = pd.concat([d, pd.DataFrame([dict(
                src=s, group="affected", fct_us=END_US, pkts=1, rts=0, ecn=0,
                rtos=0, frz=0, frz_us=0.0, ev_explore=0, ev_random=0,
                fast_loss=0, ev_valid=0, ev_stale=0) for s in missing])], ignore_index=True)
        for grp, gg in d.groupby("group"):
            fct_rows.append(dict(
                part=part, size=size, x=x, ef=ef, seed=seed, arm=arm, group=grp,
                p50_fct_us=float(np.percentile(gg.fct_us, 50)),
                p90_fct_us=float(np.percentile(gg.fct_us, 90)),
                p95_fct_us=float(np.percentile(gg.fct_us, 95)),
                p99_fct_us=float(np.percentile(gg.fct_us, 99)),
                max_fct_us=float(gg.fct_us.max())))
            diag_rows.append(dict(
                part=part, size=size, x=x, ef=ef, seed=seed, arm=arm, group=grp,
                ecn_per_host=float(gg.ecn.mean()),
                rto_per_host=float(gg.rtos.mean()),
                rts_per_host=float(gg.rts.mean()),
                fast_loss_per_host=float(gg.fast_loss.mean()),
                freeze_entries_per_host=float(gg.frz.mean()),
                freeze_hosts_frac=float((gg.frz > 0).mean()),
                freeze_us_mean=float(gg.frz_us.mean()),
                ev_random_per_host=float(gg.ev_random.mean()),
                ev_explore_per_host=float(gg.ev_explore.mean()),
                ev_random_rate=float((gg.ev_random + gg.ev_explore).sum()
                                     / max(1, gg.pkts.sum())),
                **_source_split(gg)))
    return pd.DataFrame(fct_rows), pd.DataFrame(diag_rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default=str(RUNS))
    args = ap.parse_args()
    runs = Path(args.runs)
    if not any(runs.rglob("stdout.txt")):
        raise SystemExit(f"no stdout.txt under {runs}")

    fct, diag = _flow_rows(runs)
    keys = ["part", "size", "x", "ef", "arm", "group"]
    fct_out = _collapse(fct, keys, FCT_COLS)
    diag_out = _collapse(diag, keys, DIAG_COLS)

    gk = ["part", "size", "x", "ef", "group"]
    fct_metrics = ["p50_fct_us", "p95_fct_us", "p99_fct_us", "max_fct_us"]
    diag_metrics = ["ecn_per_host", "rto_per_host", "freeze_entries_per_host",
                    "freeze_us_mean", "ev_random_per_host", "ev_random_rate"]
    # Buffer-size (B) comparison is done per CC: a B ladder under MPRDMA and a
    # B ladder under NSCC are separate axes. reps_b8_dual / _dual_cap are a
    # different CC mechanism, not B points, so they are excluded (see
    # aggregate29.py's identical note).
    rv_parts = []
    for cc in ("mprdma", "nscc"):
        f_sub = fct_out[(fct_out.group == "affected") & (fct_out.cc == cc)]
        d_sub = diag_out[(diag_out.group == "affected") & (diag_out.cc == cc)]
        r_f = _resolvable(f_sub, gk, fct_metrics)
        r_d = _resolvable(d_sub, gk, diag_metrics)
        r_f["cc"] = cc
        r_d["cc"] = cc
        rv_parts += [r_f, r_d]
    rv = pd.concat(rv_parts, ignore_index=True)

    DATA.mkdir(parents=True, exist_ok=True)
    fct_out.sort_values(keys).to_csv(DATA / "fct.csv", index=False)
    diag_out.sort_values(keys).to_csv(DATA / "diagnostics.csv", index=False)
    rv.sort_values(["cc", "metric", "part", "size", "ef", "x"]).to_csv(
        DATA / "resolvable.csv", index=False)
    print(f"fct.csv         : {len(fct_out)} rows")
    print(f"diagnostics.csv : {len(diag_out)} rows")
    print(f"resolvable.csv  : {len(rv)} rows  (affected group)")

    for cc in ("mprdma", "nscc"):
      for m in fct_metrics:
        for (part, size, ef), sub in rv[(rv.metric == m) & (rv.cc == cc)].groupby(["part", "size", "ef"]):
            yes = sorted(sub.loc[sub.resolvable, "x"].tolist())
            no = sorted(sub.loc[~sub.resolvable, "x"].tolist())
            print(f"  [{cc}] {m:<12} {part} s{size} ef{ef:<3} resolvable x={yes or '-'}   "
                  f"not x={no or '-'}")


if __name__ == "__main__":
    main()
