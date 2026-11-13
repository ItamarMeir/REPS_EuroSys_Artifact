#!/usr/bin/env python3
"""
Shared pieces of the T1 and T2 pages: the random-EV-draw plot (same B axis and styles as the max-FCT plot),
the draws-vs-FCT-excess correlation plot with within-B and paired statistics, and the cost-model check.
Imported by build_page_t1.py and build_page_t2.py.

Inputs are the aggregated summaries (n_random_post, n_random_degraded, pct_random, pct_overwrite, fct_max) and the
per-seed random-stats cells (for paired differences to B=128, same seeds). Correlations are computed here in
Python and shipped in the payload; the page only displays them.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from plot_common import knee_fct  # noqa: E402

# y metrics of the random-draw plot: key -> (dropdown label, axis title). extra_* are signed (linear axis, no clipping).
RND_METRICS = {
    "pct_random": ("random share (% of sends)", "sends with a random EV (%)"),
    "n_random_post": ("random draws per run", "random-EV draws per run (count)"),
    "n_random_degraded": ("random draws on degraded paths", "random-EV draws on degraded paths per run (count)"),
    "extra_degraded": ("extra random draws on degraded paths vs B=128 (paired)",
                       "extra degraded-path random draws over B=128, same seed (count per run)"),
    "extra_all": ("extra random draws (all) vs B=128 (paired)",
                  "extra random draws over B=128, same seed (count per run)"),
    "pct_overwrite": ("overwrites (%)", "valid-EV overwrites (% of clean ACKs)"),
}
# x options of the correlation plot: key -> (dropdown label, axis title)
CORR_X = {
    "extra_degraded": ("extra random draws on degraded paths vs B=128 (paired)",
                       "extra degraded-path random draws over B=128, same seed (count per run)"),
    "extra_all": ("extra random draws (all) vs B=128 (paired)", "extra random draws over B=128, same seed (count per run)"),
    "n_random_degraded": ("random draws on degraded paths (count)", "random-EV draws on degraded paths per run (count)"),
    "n_random_post": ("all random draws (count)", "random-EV draws per run (count)"),
    "pct_random": ("random share (%)", "sends with a random EV (%)"),
}
EXTRA_SRC = {"extra_degraded": "n_random_degraded", "extra_all": "n_random_post"}
TQ = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447}  # two-sided 95% t, df = n-1 -> index df
TOL_REL = 0.002  # tolerance of the knee rule: 0.2% of the B=128 value


KNEE_NOTE = ("**Knee rule.** B_fct = smallest B such that every larger B has mean max FCT at most B=128's plus a tolerance (or lower); "
             "one-sided, not 'no change at all'. Unpaired (page rule, `plot_common.knee_fct`): tolerance = max(CI of that B, CI of B=128, "
             "0.2% of B=128). Paired (`knee_paired.py`, used for the rings, tiles and callouts): per-seed excess over the same seed's B=128, "
             "tolerance = max(0.2%, 1.96 SE of the paired differences).")


def knee_aside(example: str) -> str:
    return ("The unpaired rule compares means with the CIs of both B and B=128, so a noisy B passes more easily; the paired rule "
            f"removes the seed-to-seed variation shared with B=128. {example} With 3 seeds (T1) or 5 seeds (T2) a move of one grid "
            "step in B_fct is inside the noise, and both knees depend on the tolerance. The tinted strip on the max-FCT plot is the "
            "B=128 side of the unpaired tolerance, max(CI of B=128, 0.2% of B=128), drawn from the B=128 mean upwards. "
            "Random-draw knees B_rand0: the smallest B from which the paired extra draws over B=128 (same seed) stay inside their "
            "95% t-CI of zero for every larger B; that is also tolerance-dependent (wide CI with few seeds lets a B pass).")


def tol_info(s) -> dict:
    """B=128 reference and the B=128 side of the knee tolerance: max(95% CI half-width of the B=128 mean, 0.2% of it)."""
    ref = s.sort_values("B").iloc[-1]
    m, ci = float(ref.fct_max_mean), float(ref.fct_max_ci95) if ref.fct_max_ci95 == ref.fct_max_ci95 else 0.0
    return {"ref": round(m, 3), "ci128": round(ci, 3), "tol": round(max(ci, TOL_REL * m), 3)}


def _f(v):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)


def paired_extra(cells: pd.DataFrame) -> dict:
    """{B: {extra_key: (mean, ci95, n)}}: per-seed difference to B=128 of the same seed, then t-CI over seeds."""
    ref = cells[cells.B == 128].set_index("seed")
    out = {}
    for B, g in cells.groupby("B"):
        g = g.set_index("seed")
        d = {}
        for ek, col in EXTRA_SRC.items():
            diff = (g[col] - ref[col]).dropna()
            n = len(diff)
            if n == 0:
                continue
            sd = diff.std(ddof=1) if n > 1 else 0.0
            d[ek] = (float(diff.mean()), float(TQ.get(n - 1, 2.0) * sd / math.sqrt(n)) if n > 1 else 0.0, n)
        out[int(B)] = d
    return out


def maxhost_series(MH: pd.DataFrame, fail: str, label: str, style: str, bfct, scope: str) -> dict:
    """Random-draw series of the max-FCT host (scope 'max') or of the 32 ToR0 hosts (scope 'all', counts per host), mean and
    t-CI over seeds. The paired extra is the cell minus the B=128 cell of the same seed (for 'max': that cell's own max host)."""
    d = MH[MH.fail == fail]
    pre = "max_" if scope == "max" else "all_"
    norm = 1 if scope == "max" else 32
    v = pd.DataFrame({"B": d.B, "seed": d.seed, "pct_random": d[pre + "pct_random"], "n_random_post": d[pre + "n_random"] / norm,
                      "n_random_degraded": d[pre + "n_random_degraded"] / norm, "pct_overwrite": d[pre + "pct_overwrite"]})
    ref = v[v.B == 128].set_index("seed")
    if scope == "max":      # the SAME host at B=128 of the same seed (columns written by maxhost_stats.py)
        v["extra_all"] = d.max_extra_all_samehost
        v["extra_degraded"] = d.max_extra_degraded_samehost
    else:                   # all 32 ToR0 hosts pooled: the same hosts at B=128, same seed
        v["extra_all"] = v.n_random_post - v.seed.map(ref.n_random_post)
        v["extra_degraded"] = v.n_random_degraded - v.seed.map(ref.n_random_degraded)
    m, kn = {}, []
    for key in RND_METRICS:
        rows = []
        for B, g in v.groupby("B"):
            x = g[key].dropna()
            if len(x) == 0:
                continue
            n = len(x)
            ci = float(TQ.get(n - 1, 2.0) * x.std(ddof=1) / math.sqrt(n)) if n > 1 else 0.0
            y = float(x.mean())
            if key.startswith("extra") or y > 0:
                rows.append({"x": f"B={int(B)}", "y": round(y, 4), "ci": round(ci, 4), "n": n})
            if key == "pct_random":
                kn.append({"B": int(B), "fct_max_mean": 0, "pct_random_mean": y, "pct_random_ci95": ci, "n_seeds": n})
        m[key] = rows
    brand = knee_fct(pd.DataFrame(kn).sort_values("B").reset_index(drop=True), "pct_random", tol_floor=0.10)
    return {"label": label + ("" if scope == "max" else " (avg of 32 ToR0 hosts)"), "style": style, "bfct": bfct, "brand": brand,
            "m": m, "dot": scope == "all", "brand0a": knee_zero(m["extra_all"]) if m["extra_all"] else None,
            "brand0d": knee_zero(m["extra_degraded"]) if m["extra_degraded"] else None}


def knee_zero(rows: list) -> int | None:
    """B_rand0: smallest B from which every larger B has |mean paired extra| <= its 95% CI (extra draws vs B=128, same seed).
    rows: [{x: 'B=..', y, ci}] of an extra_* metric."""
    r = sorted(rows, key=lambda q: int(q["x"][2:]))
    ok = [abs(q["y"]) <= q["ci"] for q in r]
    for i in range(len(r)):
        if all(ok[i:]):
            return int(r[i]["x"][2:])
    return None


def knee_random(s) -> int | None:
    """Knee of the random-share curve with the same one-sided rule as B_fct, tolerance = CI or 10% of the
    B=128 value (the 0.2% floor of the FCT rule is far below the seed spread of a share)."""
    return knee_fct(s.sort_values("B").reset_index(drop=True), "pct_random", tol_floor=0.10)


def rnd_series(s: pd.DataFrame, label: str, style: str, bfct, extra: dict | None = None) -> dict:
    """One config: rows per B for every y metric. Count/share metrics drop NaN and zeros (log axis);
    the paired extra-draw metrics are signed and keep every B."""
    s = s.sort_values("B")
    m = {}
    for key in RND_METRICS:
        rows = []
        if key.startswith("extra"):
            for B in sorted(extra or {}):
                if key in extra[B] and B in set(s.B):
                    y, ci, n = extra[B][key]
                    rows.append({"x": f"B={B}", "y": round(y, 3), "ci": round(ci, 3), "n": n})
        else:
            for r in s.itertuples():
                y, ci = _f(getattr(r, f"{key}_mean")), _f(getattr(r, f"{key}_ci95"))
                if y is None or y <= 0:
                    continue
                rows.append({"x": f"B={int(r.B)}", "y": round(y, 4), "ci": round(ci or 0.0, 4), "n": int(r.n_seeds)})
        m[key] = rows
    return {"label": label, "style": style, "bfct": bfct, "brand": knee_random(s), "m": m,
            "brand0a": knee_zero(m["extra_all"]) if m["extra_all"] else None,
            "brand0d": knee_zero(m["extra_degraded"]) if m["extra_degraded"] else None}


def corr_points(s: pd.DataFrame, label: str, style: str, scope: str = "", extra: dict | None = None) -> dict:
    """Points (config, B) for B < 128: x metrics and the max-FCT excess over this config's B=128 mean."""
    s = s.sort_values("B").set_index("B")
    ref, refci = float(s.loc[128, "fct_max_mean"]), float(s.loc[128, "fct_max_ci95"])
    pts = []
    for B, r in s.iterrows():
        if B >= 128 or B > 64:
            continue
        p = {"B": int(B), "y": round(float(r.fct_max_mean) - ref, 3),
             "yci": round(math.hypot(float(r.fct_max_ci95), refci), 3), "n": int(r.n_seeds)}
        for key in CORR_X:
            if key.startswith("extra"):
                e = (extra or {}).get(int(B), {}).get(key)
                p[key], p[key + "_ci"] = (None, None) if e is None else (round(e[0], 3), round(e[1], 3))
            else:
                v, c = _f(r[f"{key}_mean"]), _f(r[f"{key}_ci95"])
                p[key] = None if v is None else round(v, 3)
                p[key + "_ci"] = None if v is None else round(c or 0.0, 3)
        pts.append(p)
    return {"label": label, "style": style, "scope": scope, "pts": pts}


def _cor(x, y, method):
    if len(x) < 3:
        return None
    a, b = pd.Series(x), pd.Series(y)
    if method == "spearman":  # rank correlation without scipy (average ranks for ties)
        a, b = a.rank(), b.rank()
    v = a.corr(b)
    return None if v != v else round(float(v), 2)


def _stat_pts(q, key):
    xs, ys = [p[key] for p in q], [p["y"] for p in q]
    return {"n": len(q), "pearson": _cor(xs, ys, "pearson"), "spearman": _cor(xs, ys, "spearman")}


def _stat(pts, key, bmin):
    return _stat_pts([p for p in pts if p[key] is not None and p["B"] >= bmin], key)


def corr_stats(series: list[dict]) -> dict:
    """{xkey: {rows, within}}.
    rows: one row per series plus pooled; all = B in 1..64 (B=128 is the reference, excess 0 by construction),
    ge4 = B in 4..64. Pooled over B these are inflated: B drives both axes.
    within: (a) across configs at each fixed B in 4, 5, 6, 8 (n = number of configs with the x metric);
    (b) paired differences, pooled over B >= 4 (x = extra draws vs B=128 of the same seeds)."""
    out = {}
    for key in CORR_X:
        rows = [{"name": s["label"], "all": _stat(s["pts"], key, 1), "ge4": _stat(s["pts"], key, 4)} for s in series]
        pooled = [p for s in series for p in s["pts"]]
        rows.append({"name": "pooled over B", "all": _stat(pooled, key, 1), "ge4": _stat(pooled, key, 4)})
        within = []
        for B in (4, 5, 6, 8):
            q = [p for s in series for p in s["pts"] if p["B"] == B and p[key] is not None]
            within.append({"name": f"across configs at B={B}", **_stat_pts(q, key)})
        within.append({"name": "paired, pooled over B 4-64", **_stat(pooled, key, 4)})
        out[key] = {"rows": rows, "within": within}
    return out


def cost_model(s: pd.DataFrame, label: str, style: str, extra: dict, scope: str = "") -> dict:
    """Predicted FCT excess(B) = slope * extra random draws on degraded paths (paired, vs B=128), slope fitted on the
    B <= 3 cells only (B = 1, 2 on this grid; no B=3 was run), least squares through the origin. Test B >= 4 is
    out of sample. If the config has no degraded-path count at B=1, 2 (T1 r = 0.25, older cells without a trace),
    all random draws are used and the row is flagged."""
    s = s.sort_values("B").set_index("B")
    ref, refci = float(s.loc[128, "fct_max_mean"]), float(s.loc[128, "fct_max_ci95"])
    tol = TOL_REL * ref
    xkey = "extra_degraded" if all(extra.get(B, {}).get("extra_degraded") for B in (1, 2)) else "extra_all"
    fit = [B for B in (1, 2, 3) if B in s.index and extra.get(B, {}).get(xkey)]
    sxy = sum(extra[B][xkey][0] * (float(s.loc[B, "fct_max_mean"]) - ref) for B in fit)
    sxx = sum(extra[B][xkey][0] ** 2 for B in fit)
    slope = sxy / sxx
    rows = []
    for B in sorted(b for b in s.index if b <= 128 and b in extra and xkey in extra[b]):
        x = extra[B][xkey][0]
        rows.append({"x": f"B={B}", "B": int(B), "extra": round(x, 1), "pred": round(slope * x, 3),
                     "meas": round(float(s.loc[B, "fct_max_mean"]) - ref, 3),
                     "ci": round(math.hypot(float(s.loc[B, "fct_max_ci95"]), refci), 3), "n": int(s.loc[B, "n_seeds"]),
                     "fit": B in fit})

    def first_in(key):  # smallest B from which every larger B has excess <= tol
        ok = [r[key] <= tol for r in rows]
        for i in range(len(rows)):
            if all(ok[i:]):
                return rows[i]["B"]
        return None
    return {"label": label, "style": style, "scope": scope, "xkey": xkey, "fit_B": fit, "slope": slope, "tol": round(tol, 3),
            "rows": rows, "b_pred": first_in("pred"), "b_meas": first_in("meas")}


# ---------------------------------------------------------------------------------------------
# Page JS shared by T1 and T2 (uses PC, DATA.bAll). Plots are drawn from arguments, no page state.
# ---------------------------------------------------------------------------------------------
RND_JS = r"""
const RND_META = DATA.rndMeta, CORR_META = DATA.corrMeta;

// random-draw plot: same x axis, styles and knee ring as PC.fctVsB; numbered dashed marks at the max-FCT knees
function drawRnd(id, fnId, series, key, title, bAll) {
  const signed = key.startsWith('extra');
  const traces = [];
  series.forEach(s => {
    const c = PC.color(s.style);
    const tr = PC.lineTrace(s.style, s.m[key], s.label, { noBand: true });
    const line = tr[tr.length - 1];
    if (s.dot) { line.line.dash = 'dot'; tr.forEach(q => { if (q.legendgroup) q.legendgroup += 'dot'; }); }
    line.error_y = { type: 'data', array: s.m[key].map(r => r.ci), visible: true, thickness: 1, width: 3, color: c };
    line.hovertemplate = '%{y:.4g} ±%{customdata[0]:.3g}  (n=%{customdata[1]})';
    traces.push(...tr);
    const kr = s.dot ? null : s.m[key].find(r => r.x === 'B=' + s.bfct);
    if (kr) traces.push({ x: [kr.x], y: [kr.y], type: 'scatter', mode: 'markers', showlegend: false,
      legendgroup: 'g' + s.style + (s.dot ? 'dot' : ''), hovertemplate: 'max-FCT knee B_fct = ' + s.bfct + '<extra></extra>',
      marker: { symbol: 'circle-open', size: 18, color: c, line: { width: 1.4, color: c } } });
  });
  const solid = series.filter(s => !s.dot);
  const knees = [...new Set(solid.map(s => s.bfct).filter(b => b != null))].sort((a, b) => a - b);
  const vm = PC.vmarks(knees.map((b, i) => ({ x: 'B=' + b, n: i + 1 })));
  const t = PC.theme();
  t.shapes = vm.shapes; t.annotations = vm.annotations;
  if (signed) { const z = PC.hline(0, 'B=128 level'); t.shapes = t.shapes.concat(z.shapes); t.annotations = t.annotations.concat(z.annotations); }
  t.xaxis.type = 'category'; t.xaxis.categoryorder = 'array'; t.xaxis.categoryarray = bAll || DATA.bAll;
  t.yaxis.type = signed ? 'linear' : 'log'; t.yaxis.title.text = RND_META[key][1];
  t.hovermode = 'closest';
  PC.draw(id, traces, t, title);
  document.getElementById(fnId).innerHTML = knees.map((b, i) =>
    '<li>max-FCT knee B_fct = ' + b + ': ' + solid.filter(s => s.bfct === b).map(s => s.label).join(', ')
    + '</li>').join('')
    + '<li>Random draws flatten, B_rand0 (paired extra draws vs B=128 inside their 95% CI of zero from this B on), all draws / degraded-path draws: '
    + series.map(s => s.label + ' ' + (s.brand0a ?? '-') + ' / ' + (s.brand0d ?? '-')).join('; ') + '</li>'
    + '<li>Tolerance-dependent alternative, share within 10% of its B=128 value (B_rand): ' + series.map(s => s.label + ' ' + (s.brand ?? '-')).join('; ') + '</li>';
}

// max-FCT plot with the knee tolerance drawn as a shaded band above each config's B=128 mean
function drawFctTol(id, series, title, zoom, fullRange) {
  const lo = Math.min(...series.map(s => s.ref)), hi = Math.max(...series.map(s => s.ref + s.tol));
  PC.fctVsB(id, series, title, { yrange: zoom ? [lo - 3, hi + 22] : fullRange });
  const shapes = [];
  series.forEach(s => {
    const c = PC.color(s.style);
    shapes.push({ type: 'rect', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: s.ref, y1: s.ref + s.tol, line: { width: 0 }, fillcolor: PC.rgba(c, 0.22), layer: 'below' });
    shapes.push({ type: 'line', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: s.ref, y1: s.ref, line: { color: PC.rgba(c, 0.55), width: 1, dash: 'dot' } });
  });
  Plotly.relayout(id, { shapes: shapes });
}
function fillKneeTable(tblId, list) {
  const f = (v, d) => v == null ? '-' : (+v).toFixed(d);
  document.getElementById(tblId).innerHTML =
    '<thead><tr><th>config</th><th>B=128 max FCT (\u00b5s)</th><th>B=128 CI \u00b1</th><th>unpaired tolerance (\u00b5s) = max(CI, 0.2%)</th>'
    + '<th>excess B=5</th><th>B=6</th><th>B=7</th><th>B=8</th><th>B_fct (unpaired, page rule)</th><th>B_fct (paired)</th>'
    + '<th>B_rand0 all draws</th><th>B_rand0 degraded draws</th><th>B_rand (share within 10%)</th></tr></thead><tbody>'
    + list.map(r => `<tr><td>${r.label}</td><td>${f(r.ref, 2)}</td><td>${f(r.ci128, 2)}</td><td>${f(r.tol, 2)}</td>`
      + [5, 6, 7, 8].map(B => `<td>${r.ex[B] == null ? '-' : f(r.ex[B], 2)}</td>`).join('')
      + `<td>${r.bunp ?? '-'}</td><td><b>${r.bfct ?? '-'}</b></td><td>${r.brand0a ?? '-'}</td><td>${r.brand0d ?? '-'}</td><td>${r.brand ?? '-'}</td></tr>`).join('') + '</tbody>';
}

// correlation: x = random draws, y = max-FCT excess over the same config at B=128
function drawCorr(id, tblId, series, xkey, bmin, title) {
  const traces = [];
  series.forEach(s => {
    const q = s.pts.filter(p => p[xkey] != null && p.B >= bmin);
    const c = PC.color(s.style), st = PC.style(s.style);
    const sym = s.scope === 'B' ? st.symbol.replace('-open', '-open-dot') : st.symbol;
    traces.push({ x: q.map(p => p[xkey]), y: q.map(p => p.y), name: s.label, type: 'scatter',
      mode: 'markers+text', legendgroup: 'g' + s.style + s.scope,
      text: q.map(p => p.B <= 8 || bmin > 1 ? 'B=' + p.B : ''), textposition: 'top right', textfont: { size: 9, color: PC.css('--muted') },
      marker: { color: c, symbol: sym, size: 9, line: { color: c, width: 1.8 } },
      error_y: { type: 'data', array: q.map(p => p.yci), visible: true, thickness: 1, width: 3, color: c },
      error_x: { type: 'data', array: q.map(p => p[xkey + '_ci']), visible: true, thickness: 1, width: 3, color: PC.rgba(c, 0.5) },
      customdata: q.map(p => [p.yci, p.n, 'B=' + p.B, p[xkey + '_ci']]),
      hovertemplate: '%{customdata[2]}: x=%{x:.4g} ±%{customdata[3]:.3g}, FCT excess %{y:.3g} ±%{customdata[0]:.3g} us  (n=%{customdata[1]})<extra>' + s.label + '</extra>' });
  });
  const t = PC.theme();
  t.hovermode = 'closest';
  t.xaxis.title.text = CORR_META[xkey][1]; t.xaxis.rangemode = xkey.startsWith('extra') ? 'normal' : 'tozero';
  t.yaxis.title.text = 'max-FCT excess over the same config at B=128 (µs)';
  const z = PC.hline(0, 'B=128 level'); t.shapes = z.shapes; t.annotations = z.annotations;
  PC.draw(id, traces, t, title);
}
function fillCorrTable(tblId, tbl2Id, st) {
  const f = v => v == null ? '-' : v.toFixed(2);
  document.getElementById(tblId).innerHTML =
    '<thead><tr><th>config (pooled over B: inflated, B drives both)</th><th>n (B 1-64)</th><th>Pearson</th><th>Spearman</th>'
    + '<th>n (B 4-64)</th><th>Pearson</th><th>Spearman</th></tr></thead><tbody>'
    + st.rows.map(r => `<tr><td>${r.name}</td><td>${r.all.n}</td><td>${f(r.all.pearson)}</td><td>${f(r.all.spearman)}</td>`
      + `<td>${r.ge4.n}</td><td>${f(r.ge4.pearson)}</td><td>${f(r.ge4.spearman)}</td></tr>`).join('') + '</tbody>';
  document.getElementById(tbl2Id).innerHTML =
    '<thead><tr><th>controls for B</th><th>n</th><th>Pearson</th><th>Spearman</th></tr></thead><tbody>'
    + st.within.map(r => `<tr><td>${r.name}</td><td>${r.n}</td><td>${f(r.pearson)}</td><td>${f(r.spearman)}</td></tr>`).join('') + '</tbody>';
}

// cost-model check: predicted excess = slope * extra degraded draws (fit on B <= 3) vs measured, tolerance band shaded
function drawCost(id, c, bmin, title) {
  const key = c.style, col = PC.color(key), st = PC.style(key);
  const rr = c.rows.filter(r => r.B >= bmin), xs = rr.map(r => r.x);
  const traces = [
    { x: xs, y: rr.map(r => r.pred), name: 'predicted (slope x extra draws)', type: 'scatter', mode: 'lines+markers',
      line: { color: col, width: 2.4, dash: 'dash' }, marker: { color: col, symbol: 'circle', size: 6 },
      customdata: rr.map(r => [0, r.n]), hovertemplate: 'predicted %{y:.3g} us<extra></extra>' },
    { x: xs, y: rr.map(r => r.meas), name: 'measured excess (95% CI)', type: 'scatter', mode: 'lines+markers',
      line: { color: col, width: 2.4 }, marker: { color: col, symbol: st.symbol, size: 9, line: { color: col, width: 1.8 } },
      error_y: { type: 'data', array: rr.map(r => r.ci), visible: true, thickness: 1, width: 3, color: col },
      customdata: rr.map(r => [r.ci, r.n]), hovertemplate: 'measured %{y:.3g} ±%{customdata[0]:.3g} us (n=%{customdata[1]})<extra></extra>' }];
  const t = PC.theme();
  t.hovermode = 'closest';
  t.shapes = [{ type: 'rect', xref: 'paper', x0: 0, x1: 1, yref: 'y', y0: 0, y1: c.tol, line: { width: 0 },
    fillcolor: 'rgba(128,128,128,0.30)' }];
  t.annotations = [{ xref: 'paper', x: 1, y: c.tol, xanchor: 'right', yanchor: 'bottom', showarrow: false,
    text: 'tolerance 0.2% of B=128', font: { size: 10, color: PC.css('--muted') } }];
  t.xaxis.type = 'category'; t.xaxis.categoryorder = 'array'; t.xaxis.categoryarray = DATA.bAll;
  t.yaxis.title.text = 'max-FCT excess over B=128 (µs)';
  PC.draw(id, traces, t, title);
}
function fillCostTable(tblId, list) {
  const f = (v, d) => v == null ? '-' : (+v).toFixed(d);
  const at = (c, B) => c.rows.find(r => r.B === B);
  const hdr = [4, 5, 6, 8].map(B => `<th>B=${B} pred / meas</th>`).join('');
  document.getElementById(tblId).innerHTML =
    '<thead><tr><th>config</th><th>x used</th><th>fit on B</th><th>slope (µs per draw)</th>' + hdr
    + '<th>B in band: predicted</th><th>B in band: measured</th></tr></thead><tbody>'
    + list.map(c => `<tr><td>${c.label}</td><td>${c.xkey === 'extra_degraded' ? 'degraded' : 'all draws'}</td><td>${c.fit_B.join(', ')}</td>`
      + `<td>${(+c.slope).toPrecision(3)}</td>`
      + [4, 5, 6, 8].map(B => { const r = at(c, B); return `<td>${r ? f(r.pred, 1) + ' / ' + f(r.meas, 1) : '-'}</td>`; }).join('')
      + `<td>${c.b_pred ?? '-'}</td><td>${c.b_meas ?? '-'}</td></tr>`).join('') + '</tbody>';
}
"""

META = {
    "rndMeta": {k: list(v) for k, v in RND_METRICS.items()},
    "corrMeta": {k: list(v) for k, v in CORR_X.items()},
}


def fn_list(div: str) -> str:
    """Empty numbered footnote list under a plot; the page JS fills it (it depends on the dropdown)."""
    return f'<ol class="fn" id="{div}"></ol>'
