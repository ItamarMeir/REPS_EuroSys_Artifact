#!/usr/bin/env python3
"""
exp31 aggregator -- ring all-reduce CCT + per-step FCT series.

  data/cct.csv        : (scenario, arm, buf_size, cct_us, cct_us_ci, n_flows_mean,
                         censored, cct_pct_of_healthy) -- seed-averaged, 95% t-CI
  data/steps.csv      : (scenario, arm, step, fct_mean_us, fct_p95_us)
                        step = ring-hop index (flowId order in the .cm chain);
                        healthy -> flat, a bad hop -> a spike that recurs.
  data/resolvable.csv : (scenario, best_b, worst_b, spread, ci_sum, resolvable,
                         b1_minus_b2, b1_b2_ci, b2_minus_b4, b2_b4_ci)
                        -- the knee (b1->b2) and the "does bigger B hurt" (b2 vs
                        b4) questions, with CI.

CCT = max over a run's finished-flow `finished at`. If n_flows < 496 (a stalled
ring chain never prints), CCT is CENSORED at END_US -- raw max would under-report
(exp26 aggregate.py flags this bias explicitly).
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

import common31 as C

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR = SCRIPT_DIR.parent
RUNS = EXP_DIR / "runs"
DATA = EXP_DIR / "data"

FIN_RE = re.compile(
    r"Flow\s+\S+\s+flowId\s+(?P<fid>\d+)\s+uecSrc\s+(?P<src>\d+)\s+finished at\s+"
    r"(?P<fct>[\d.eE+-]+)\s+flowSize\s+\d+\s+total packets\s+(?P<pkts>\d+).*?"
    r"\brtos\s+(?P<rtos>\d+)\b.*?\bfreeze_entries\s+(?P<frz>\d+)\b.*?"
    r"\bev_random\s+(?P<ev_random>\d+)\b")


def _ci95(v) -> float:
    v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    n = len(v)
    if n < 2:
        return 0.0
    return float(sp_stats.t.ppf(0.975, n - 1) * v.std(ddof=1) / np.sqrt(n))


def _buf(arm: str) -> int:
    return int(arm.replace("reps_b", ""))


def _run_rows():
    cct_rows, step_rows = [], []
    for sp in sorted(RUNS.rglob("stdout.txt")):
        scenario, seeddir, arm = sp.parts[-4], sp.parts[-3], sp.parts[-2]
        seed = int(seeddir.replace("seed", ""))
        recs = [m.groupdict() for m in FIN_RE.finditer(sp.read_text(errors="replace"))]
        if not recs:
            print(f"  WARN 0 flows: {sp}")
            continue
        d = pd.DataFrame(recs)
        d["fid"] = d.fid.astype(int)
        d["fct"] = d.fct.astype(float)
        d["rtos"] = d.rtos.astype(int)
        n_flows = len(d)
        censored = n_flows < C.N_EXPECTED
        cct = float(C.END_US) if censored else float(d.fct.max())
        cct_rows.append(dict(scenario=scenario, arm=arm, buf_size=_buf(arm),
                             seed=seed, cct_us=cct, n_flows=n_flows,
                             censored=censored, sum_rtos=int(d.rtos.sum())))
        # per-step series: flowId is 1..496 in .cm chain order
        for _, r in d.sort_values("fid").iterrows():
            step_rows.append(dict(scenario=scenario, arm=arm, seed=seed,
                                  step=int(r.fid), fct_us=float(r.fct)))
    return pd.DataFrame(cct_rows), pd.DataFrame(step_rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default=str(RUNS))
    ap.parse_args()
    if not any(RUNS.rglob("stdout.txt")):
        raise SystemExit(f"no stdout.txt under {RUNS}")

    cct, steps = _run_rows()

    # --- cct.csv: seed-collapse ---
    g = cct.groupby(["scenario", "arm", "buf_size"], as_index=False)
    out = g.agg(cct_us=("cct_us", "mean"), n_flows_mean=("n_flows", "mean"),
                censored=("censored", "any"), sum_rtos=("sum_rtos", "mean"),
                n_seed=("seed", "nunique"))
    out["cct_us_ci"] = g["cct_us"].agg(_ci95)["cct_us"].values
    heal = out[out.scenario == "healthy"].set_index("buf_size")["cct_us"]
    out["cct_pct_of_healthy"] = out.apply(
        lambda r: round(100 * r.cct_us / heal.get(r.buf_size, np.nan), 1), axis=1)

    # --- steps.csv: seed-mean per (scenario, arm, step) ---
    st = steps.groupby(["scenario", "arm", "step"], as_index=False).agg(
        fct_mean_us=("fct_us", "mean"), fct_p95_us=("fct_us", lambda x: np.percentile(x, 95)))

    # --- resolvable.csv: per scenario, best/worst B + knee + "bigger hurts" ---
    rv = []
    for scen, gg in out.groupby("scenario"):
        gg = gg.set_index("buf_size")
        b = gg.cct_us.idxmin()
        w = gg.cct_us.idxmax()
        spread = float(gg.cct_us[w] - gg.cct_us[b])
        ci_sum = float(gg.cct_us_ci[b] + gg.cct_us_ci[w])

        def gap(x, y):
            if x not in gg.index or y not in gg.index:
                return (np.nan, np.nan)
            return (float(gg.cct_us[x] - gg.cct_us[y]),
                    float(gg.cct_us_ci[x] + gg.cct_us_ci[y]))
        b1b2, b1b2ci = gap(1, 2)
        b2b4, b2b4ci = gap(2, 4)
        rv.append(dict(scenario=scen, best_b=int(b), best_cct=round(gg.cct_us[b], 1),
                       worst_b=int(w), worst_cct=round(gg.cct_us[w], 1),
                       spread=round(spread, 1), ci_sum=round(ci_sum, 1),
                       resolvable=bool(spread > ci_sum),
                       b1_minus_b2=round(b1b2, 1), b1_b2_ci=round(b1b2ci, 1),
                       b1_b2_resolvable=bool(b1b2 > b1b2ci) if np.isfinite(b1b2) else None,
                       b2_minus_b4=round(b2b4, 1), b2_b4_ci=round(b2b4ci, 1)))
    rvdf = pd.DataFrame(rv)

    DATA.mkdir(parents=True, exist_ok=True)
    out.sort_values(["scenario", "buf_size"]).to_csv(DATA / "cct.csv", index=False)
    st.sort_values(["scenario", "arm", "step"]).to_csv(DATA / "steps.csv", index=False)
    rvdf.sort_values("scenario").to_csv(DATA / "resolvable.csv", index=False)
    print(f"cct.csv        : {len(out)} rows")
    print(f"steps.csv      : {len(st)} rows")
    print(f"resolvable.csv : {len(rvdf)} rows")
    print(rvdf[["scenario", "best_b", "worst_b", "spread", "ci_sum", "resolvable",
                "b1_minus_b2", "b1_b2_ci", "b2_minus_b4"]].to_string(index=False))


if __name__ == "__main__":
    main()
