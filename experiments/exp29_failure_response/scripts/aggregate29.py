#!/usr/bin/env python3
"""
exp29 aggregator -- parse per-host window logs + flow-finish lines into tidy CSVs.

  data/timeseries.csv : (F, ef, arm, group, t_us, <metric means over nodes>, ci_*)
  data/response.csv   : (F, ef, arm, group, phase, <window-summed metric/host>, ci_*)
  data/fct.csv        : (F, ef, arm, group, p50/p90/p95/p99/max FCT us, ci_*)
  data/diagnostics.csv: (F, ef, arm, group, exp28-style whole-flow per-host means
                         -- ecn/rto/rts/fast_loss per host, freeze entries + host
                         fraction + mean freeze us, ev_random/ev_explore per host,
                         ev_random_rate = (random+explore draws)/pkt -- + ci_*)
  data/resolvable.csv : (F, ef, group, phase, metric, best_b/worst_b + vals + CI,
                         spread, ci_sum, resolvable) -- the numeric verdict on
                         whether any B ordering survives the 95% CI. n=3 seeds
                         (t-mult 4.30) makes the bands wide; this says plainly
                         where the plotted B differences are real vs noise.

group in {affected, unaffected}. affected = senders under ToR0 = node_num in
[0, HOSTS_PER_TOR). For fat_tree_1024_1os_2t: 1024 / 32 = 32.

phase in {during, recovery}: the RTO->freeze->rotate response splits into a cost
*while the link is down* (100-200 us) and a cost *recovering afterwards*
(200-950 us). B plausibly affects only the second (poisoned-buffer flush), so
they are summed separately.
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
RUNS = EXP_DIR / "runs" / "micro"
DATA = EXP_DIR / "data"

HOSTS_PER_TOR = 32
PHASES = {"during": (100.0, 200.0), "recovery": (200.0, 950.0)}
DELTA_COLS = ["d_rto", "d_freeze_entries", "d_fast_loss",
              "d_ev_random", "d_ev_explore", "d_ecn_acks"]

# finish line -- exp28's metrics-counters fields + the timed-failure `fast_loss`
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
    r"\bfast_loss\s+(?P<fast_loss>\d+)\b")


def _ci95(v: np.ndarray) -> float:
    v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    n = len(v)
    if n < 2:
        return 0.0
    return float(sp_stats.t.ppf(0.975, n - 1) * v.std(ddof=1) / np.sqrt(n))


def _cell_key(path: Path):
    # runs/micro/tornado_F<F>_ef<EF>_s<size>/asymF<F>_seed<seed>/<arm>/<file>
    wl, cond, arm = path.parts[-4], path.parts[-3], path.parts[-2]
    F = int(wl.split("_F")[1].split("_")[0])
    ef = int(wl.split("_ef")[1].split("_")[0])
    seed = int(cond.split("_seed")[1])
    return F, ef, seed, arm


def _buf_size(arm: str) -> int:
    # leading digits after "reps_b" -- tolerates a trailing "_dual" suffix
    # (dual_mprdma_reps CC variant, same buffer size, see common29.base_flags)
    return int(re.match(r"reps_b(\d+)", arm).group(1))


def _cc(arm: str) -> str:
    return "dual_mprdma_reps" if arm.endswith("_dual") else "mprdma"


def _collapse(frame: pd.DataFrame, keys: list[str], cols: list[str]) -> pd.DataFrame:
    out = frame.groupby(keys, as_index=False)[cols].mean()
    ci = frame.groupby(keys)[cols].agg(_ci95).reset_index()
    for c in cols:
        out[c + "_ci"] = ci[c].values
    out["n_seed"] = frame.groupby(keys)["seed"].nunique().values
    out["buf_size"] = out["arm"].map(_buf_size)
    out["cc"] = out["arm"].map(_cc)
    return out


def _resolvable(agg: pd.DataFrame, group_keys: list[str], metrics: list[str],
                phase_label: str = "-") -> pd.DataFrame:
    """For each (group_keys) cell, the best (min-mean) and worst (max-mean) B on
    each metric, and whether their means are separated by more than the sum of
    their 95% CI half-widths. All exp29 metrics here are lower-is-better."""
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
            rows.append({**dict(zip(group_keys, kv)), "phase": phase_label,
                         "metric": m, "best_b": int(b.buf_size),
                         "best_val": round(float(b[m]), 3),
                         "best_ci": round(float(b[m + "_ci"]), 3),
                         "worst_b": int(w.buf_size),
                         "worst_val": round(float(w[m]), 3),
                         "worst_ci": round(float(w[m + "_ci"]), 3),
                         "spread": round(spread, 3),
                         "ci_sum": round(ci_sum, 3),
                         "resolvable": bool(spread > ci_sum)})
    return pd.DataFrame(rows)


def _flow_rows(runs: Path):
    """Per-cell, per-seed: FCT percentiles (fct_rows) and exp28-style whole-flow
    per-host diagnostic means (diag_rows), split affected / unaffected."""
    fct_rows, diag_rows = [], []
    for sp in sorted(runs.rglob("stdout.txt")):
        F, ef, seed, arm = _cell_key(sp)
        per = []
        for m in FIN_RE.finditer(sp.read_text(errors="replace")):
            g = m.groupdict()
            src = int(g["src"])
            per.append(dict(
                src=src, group="affected" if src < HOSTS_PER_TOR else "unaffected",
                fct_us=float(g["fct"]), pkts=int(g["pkts"]), rts=int(g["rts"]),
                ecn=int(g["ecn"]), rtos=int(g["rtos"]), frz=int(g["frz"]),
                frz_us=float(g["frz_us"]), ev_explore=int(g["ev_explore"]),
                ev_random=int(g["ev_random"]), fast_loss=int(g["fast_loss"])))
        if not per:
            print(f"  WARN 0 flows: {sp}")
            continue
        d = pd.DataFrame(per)
        n_aff = int((d.group == "affected").sum())
        if n_aff != HOSTS_PER_TOR:
            print(f"  WARN {sp.parts[-4]}/{sp.parts[-3]}/{sp.parts[-2]}: "
                  f"{n_aff} affected flows matched (expected {HOSTS_PER_TOR}) "
                  f"-- finish-line regex may have under-matched")
        for grp, gg in d.groupby("group"):
            n = len(gg)
            fct_rows.append(dict(
                F=F, ef=ef, seed=seed, arm=arm, group=grp,
                p50_fct_us=float(np.percentile(gg.fct_us, 50)),
                p90_fct_us=float(np.percentile(gg.fct_us, 90)),
                p95_fct_us=float(np.percentile(gg.fct_us, 95)),
                p99_fct_us=float(np.percentile(gg.fct_us, 99)),
                max_fct_us=float(gg.fct_us.max())))
            diag_rows.append(dict(
                F=F, ef=ef, seed=seed, arm=arm, group=grp,
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
                                     / max(1, gg.pkts.sum()))))
    return pd.DataFrame(fct_rows), pd.DataFrame(diag_rows)


def _window_rows(runs: Path):
    ts_rows, ph_rows = [], []
    for w in sorted(runs.rglob("window.csv")):
        F, ef, seed, arm = _cell_key(w)
        df = pd.read_csv(w)
        if df.empty:
            print(f"  WARN empty: {w}")
            continue
        # drop first tick: its deltas span [0, t0] (warmup-cumulative), an outlier
        df = df[df.t_us > df.t_us.min()]
        df["group"] = np.where(df.node < HOSTS_PER_TOR, "affected", "unaffected")

        g = df.groupby(["group", "t_us"], as_index=False)[
            DELTA_COLS + ["frozen_frac"]].mean()
        g["F"], g["ef"], g["seed"], g["arm"] = F, ef, seed, arm
        ts_rows.append(g)

        for phase, (lo, hi) in PHASES.items():
            wdf = df[(df.t_us > lo) & (df.t_us <= hi)]
            if wdf.empty:
                continue
            per_host = wdf.groupby(["group", "node"], as_index=False)[DELTA_COLS].sum()
            ff = wdf.groupby(["group", "node"], as_index=False)["frozen_frac"].mean()
            per_host = per_host.merge(ff, on=["group", "node"])
            s = per_host.groupby("group", as_index=False)[
                DELTA_COLS + ["frozen_frac"]].mean()
            s["F"], s["ef"], s["seed"], s["arm"], s["phase"] = F, ef, seed, arm, phase
            ph_rows.append(s)
    return pd.concat(ts_rows, ignore_index=True), pd.concat(ph_rows, ignore_index=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default=str(RUNS))
    args = ap.parse_args()
    runs = Path(args.runs)
    if not any(runs.rglob("window.csv")):
        raise SystemExit(f"no window.csv under {runs}")

    metric_cols = DELTA_COLS + ["frozen_frac"]
    ts, ph = _window_rows(runs)
    ts_out = _collapse(ts, ["F", "ef", "arm", "group", "t_us"], metric_cols)
    ph_out = _collapse(ph, ["F", "ef", "arm", "group", "phase"], metric_cols)

    fct, diag = _flow_rows(runs)
    fct_cols = ["p50_fct_us", "p90_fct_us", "p95_fct_us", "p99_fct_us", "max_fct_us"]
    fct_out = _collapse(fct, ["F", "ef", "arm", "group"], fct_cols)
    diag_cols = ["ecn_per_host", "rto_per_host", "rts_per_host", "fast_loss_per_host",
                 "freeze_entries_per_host", "freeze_hosts_frac", "freeze_us_mean",
                 "ev_random_per_host", "ev_explore_per_host", "ev_random_rate"]
    diag_out = _collapse(diag, ["F", "ef", "arm", "group"], diag_cols)

    # --- resolvability verdict (affected group only -- the signal of interest) ---
    # cc=="mprdma" only: this is a buffer-size (B) comparison within plain
    # MPRDMA; reps_b8_dual is a different CC mechanism, not another B point,
    # and would otherwise collide with reps_b8 (same buf_size=8) in the groupby.
    fct_metrics = ["p50_fct_us", "p99_fct_us", "max_fct_us"]
    resp_metrics = ["d_rto", "frozen_frac", "d_ev_random"]
    rv_fct = _resolvable(fct_out[(fct_out.group == "affected") & (fct_out.cc == "mprdma")],
                         ["F", "ef", "group"], fct_metrics)
    rv_resp_parts = []
    for ph in PHASES:
        sub = ph_out[(ph_out.group == "affected") & (ph_out.phase == ph)
                      & (ph_out.cc == "mprdma")]
        rv_resp_parts.append(_resolvable(sub, ["F", "ef", "group"],
                                         resp_metrics, phase_label=ph))
    diag_metrics = ["ecn_per_host", "rto_per_host", "freeze_us_mean",
                    "ev_random_per_host", "ev_random_rate"]
    rv_diag = _resolvable(diag_out[(diag_out.group == "affected") & (diag_out.cc == "mprdma")],
                          ["F", "ef", "group"], diag_metrics, phase_label="flow")
    rv = pd.concat([rv_fct] + rv_resp_parts + [rv_diag], ignore_index=True)

    DATA.mkdir(parents=True, exist_ok=True)
    ts_out.sort_values(["F", "ef", "arm", "group", "t_us"]).to_csv(
        DATA / "timeseries.csv", index=False)
    ph_out.sort_values(["F", "ef", "arm", "group", "phase"]).to_csv(
        DATA / "response.csv", index=False)
    fct_out.sort_values(["F", "ef", "arm", "group"]).to_csv(
        DATA / "fct.csv", index=False)
    diag_out.sort_values(["F", "ef", "arm", "group"]).to_csv(
        DATA / "diagnostics.csv", index=False)
    rv.sort_values(["metric", "ef", "F"]).to_csv(DATA / "resolvable.csv", index=False)
    print(f"timeseries.csv : {len(ts_out)} rows")
    print(f"response.csv   : {len(ph_out)} rows")
    print(f"fct.csv        : {len(fct_out)} rows")
    print(f"diagnostics.csv: {len(diag_out)} rows")
    print(f"resolvable.csv : {len(rv)} rows  (ef=100, affected hosts)")
    for m in fct_metrics + resp_metrics + diag_metrics:
        for ph in sorted(rv.loc[rv.metric == m, "phase"].unique()):
            sub = rv[(rv.metric == m) & (rv.ef == 100) & (rv.phase == ph)]
            if sub.empty:
                continue
            yes = sorted(sub.loc[sub.resolvable, "F"].tolist())
            no = sorted(sub.loc[~sub.resolvable, "F"].tolist())
            tag = f"{m} [{ph}]" if ph != "-" else m
            print(f"  {tag:<26} resolvable F={yes or '-'}   not F={no or '-'}")


if __name__ == "__main__":
    main()
