#!/usr/bin/env python3
"""T1 aggregator -- merges path_static (this experiment's own runs/) with
reps_b8_nscc (already aggregated in exp30_packet_trimming_en/data/fct.csv,
no rerun) into one table, computes per-seed paired ratios FCT(n)/FCT(0) and
compares against the bandwidth-loss model FCT(n) ~= L + S*64/(64-n)."""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

SCRIPT_DIR = Path(__file__).resolve().parent
EXP_DIR = SCRIPT_DIR.parent
RUNS = EXP_DIR / "runs"
DATA = EXP_DIR / "data"
EXP30_FCT = EXP_DIR.parent.parent / "exp30_packet_trimming_en" / "data" / "fct.csv"

HOSTS_PER_TOR = 32
END_US = 90000.0

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
    r"(?:\bev_valid\s+(?P<ev_valid>\d+)\b.*?\bev_stale\s+(?P<ev_stale>\d+)\b.*?)?"
    r"\bfast_loss\s+(?P<fast_loss>\d+)\b")


def _ci95(v: np.ndarray) -> float:
    v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    n = len(v)
    if n < 2:
        return 0.0
    return float(sp_stats.t.ppf(0.975, n - 1) * v.std(ddof=1) / np.sqrt(n))


def _cell_key(path: Path):
    # runs/a1/<size>/x<n>_ef<ef>/seed<seed>/path_static/stdout.txt
    part, size, xdir, seeddir, arm = path.parts[-6:-1]
    n = int(xdir.split("_")[0][1:])
    seed = int(seeddir.replace("seed", ""))
    return part, int(size), n, seed, arm


def _flow_rows_path_static() -> tuple[pd.DataFrame, pd.DataFrame]:
    fct_rows, diag_rows = [], []
    for sp in sorted(RUNS.rglob("stdout.txt")):
        part, size, n, seed, arm = _cell_key(sp)
        per = []
        for m in FIN_RE.finditer(sp.read_text(errors="replace")):
            g = m.groupdict()
            src = int(g["src"])
            if src >= HOSTS_PER_TOR:
                continue  # only need the affected group for T1
            per.append(dict(
                src=src, fct_us=float(g["fct"]), rtos=int(g["rtos"]),
                frz=int(g["frz"]), fast_loss=int(g["fast_loss"]),
                ecn=int(g["ecn"])))
        if not per:
            print(f"  WARN 0 affected flows: {sp}")
            continue
        d = pd.DataFrame(per)
        missing = sorted(set(range(HOSTS_PER_TOR)) - set(d.src))
        if missing:
            print(f"  CENSORED {sp}: src {missing}")
            d = pd.concat([d, pd.DataFrame([dict(
                src=s, fct_us=END_US, rtos=0, frz=0, fast_loss=0, ecn=0)
                for s in missing])], ignore_index=True)
        # path_static is a BINARY per-flow split, not a smooth pool: exactly
        # n of the 32 flows are pinned to a degraded uplink and finish at the
        # fully-halved value, the other 32-n finish at the untouched value
        # (verified directly from stdout: two point masses, no values between
        # them). So besides whole-group p50 (confounded below n=16, since the
        # median only crosses groups once the degraded fraction passes half),
        # also report the degraded subset's own mean (= top-n FCTs) -- that
        # is the uncontaminated single-flow bandwidth-loss measurement.
        sorted_fct = np.sort(d.fct_us.values)
        degraded_mean = (float(sorted_fct[-n:].mean()) if n > 0 else np.nan)
        healthy_mean = (float(sorted_fct[:32 - n].mean()) if n < 32 else np.nan)
        fct_rows.append(dict(
            arm="path_static", size=size, n=n, seed=seed,
            p50_fct_us=float(np.percentile(d.fct_us, 50)),
            max_fct_us=float(d.fct_us.max()),
            degraded_subset_mean_us=degraded_mean,
            healthy_subset_mean_us=healthy_mean))
        diag_rows.append(dict(
            arm="path_static", size=size, n=n, seed=seed,
            rto_per_host=float(d.rtos.mean()),
            fast_loss_per_host=float(d.fast_loss.mean()),
            freeze_entries_per_host=float(d.frz.mean()),
            ecn_per_host=float(d.ecn.mean())))
    return pd.DataFrame(fct_rows), pd.DataFrame(diag_rows)


def _nscc_from_exp30() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pull reps_b8_nscc, part a1, group=affected rows straight out of
    exp30_packet_trimming_en's own aggregated fct.csv/diagnostics.csv --
    no rerun. fct.csv there is per-(part,size,x,ef,arm,group) MEAN over
    seeds already, not per-seed -- so build a synthetic 3-row-per-cell
    frame isn't possible; instead carry the already-collapsed mean+CI
    forward directly (n_seed column says how many seeds backed it)."""
    fct = pd.read_csv(EXP30_FCT)
    sub = fct[(fct.part == "a1") & (fct.arm == "reps_b8_nscc") &
              (fct.group == "affected")].copy()
    sub = sub.rename(columns={"x": "n"})
    diag = pd.read_csv(EXP30_FCT.parent / "diagnostics.csv")
    dsub = diag[(diag.part == "a1") & (diag.arm == "reps_b8_nscc") &
                (diag.group == "affected")].copy()
    dsub = dsub.rename(columns={"x": "n"})
    return sub, dsub


def _model_ratio(n: int) -> float:
    return 64.0 / (64.0 - n)


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    ps_fct, ps_diag = _flow_rows_path_static()

    # path_static: per-seed paired ratio maxFCT(n)/maxFCT(0), same seed, same
    # size. For this binary-split arm, whole-group max IS the one degraded
    # flow's own worst case once n>0 (max of 32 values = max of the n
    # degraded ones), so max needs no separate "degraded subset" reading the
    # way p50 did -- one series is already the clean per-flow number.
    rows = []
    for size, g in ps_fct.groupby("size"):
        base = g[g.n == 0].set_index("seed")["max_fct_us"]
        for n, gn in g.groupby("n"):
            ratios = []
            for seed, row in gn.set_index("seed").iterrows():
                if seed in base.index:
                    ratios.append(row["max_fct_us"] / base[seed])
            ratios = np.array(ratios)
            rows.append(dict(
                arm="path_static", size=size, n=n, n_seed=len(ratios),
                max_ratio_mean=float(ratios.mean()) if len(ratios) else np.nan,
                max_ratio_ci=_ci95(ratios),
                model_ratio=_model_ratio(n)))
    ps_ratio = pd.DataFrame(rows)

    # nscc: already-collapsed means (exp30's own aggregator) -- ratio from
    # the collapsed max mean at n vs n=0 (no per-seed pairing available from
    # that file; CI propagated from the two cells' own CIs)
    nscc_fct, nscc_diag = _nscc_from_exp30()
    rows = []
    for size, g in nscc_fct.groupby("size"):
        base = g[g.n == 0]
        if base.empty:
            continue
        base_max = float(base["max_fct_us"].iloc[0])
        base_ci = float(base["max_fct_us_ci"].iloc[0])
        for _, r in g.iterrows():
            ratio = r["max_fct_us"] / base_max
            # propagate CI via linear approx: d(ratio) ~= ratio * sqrt((ci_n/v_n)^2+(ci_0/v_0)^2)
            rel = np.sqrt((r["max_fct_us_ci"] / r["max_fct_us"]) ** 2 +
                          (base_ci / base_max) ** 2) if r["max_fct_us"] > 0 else 0.0
            rows.append(dict(
                arm="reps_b8_nscc", size=size, n=int(r["n"]),
                n_seed=int(r["n_seed"]),
                max_ratio_mean=float(ratio), max_ratio_ci=float(ratio * rel),
                model_ratio=_model_ratio(int(r["n"]))))
    nscc_ratio = pd.DataFrame(rows)

    ratio = pd.concat([ps_ratio, nscc_ratio], ignore_index=True)
    ratio.sort_values(["arm", "size", "n"]).to_csv(DATA / "ratio.csv", index=False)
    ps_fct.sort_values(["size", "n", "seed"]).to_csv(DATA / "fct_path_static.csv", index=False)
    ps_diag.sort_values(["size", "n", "seed"]).to_csv(DATA / "diagnostics_path_static.csv", index=False)

    print(f"ratio.csv: {len(ratio)} rows")
    print(ratio.sort_values(["arm", "size", "n"]).to_string(index=False))

    # diagnostics gate: rtos/fast_loss/freeze should stay ~0 across n
    print("\npath_static diagnostics (mean over seeds, per n/size):")
    dmean = ps_diag.groupby(["size", "n"])[
        ["rto_per_host", "fast_loss_per_host", "freeze_entries_per_host", "ecn_per_host"]
    ].mean().reset_index()
    print(dmean.to_string(index=False))
    print("\nnscc diagnostics (from exp30, affected group, a1):")
    print(nscc_diag[["size", "n", "rto_per_host", "fast_loss_per_host",
                     "freeze_entries_per_host", "ecn_per_host"]]
          .sort_values(["size", "n"]).to_string(index=False))


if __name__ == "__main__":
    main()
