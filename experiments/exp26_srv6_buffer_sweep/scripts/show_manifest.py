#!/usr/bin/env python3
"""Print the per-run manifest built by _build_manifest() below, grouped by cell.

For every exp26 run: which driver produced it, and the topology / LB / CC /
workload / seed / failure input it actually used (parsed from htsim's own stdout
echo, not reconstructed from the driver source)."""
from __future__ import annotations
import csv, glob, re, sys
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
MANIFEST = EXP / "data" / "run_manifest.csv"
DRIVER = {"fig2": "run_sym.py --figure fig2", "fig4": "run_sym.py --figure fig4",
          "fig6": "run_fig6.py", "fig7": "run_fig7.py", "fig8": "run_fig8.py"}


def build(runs_dir: Path) -> list[dict]:
    rows = []
    for f in sorted(glob.glob(str(runs_dir / "fig*/**/stdout.txt"), recursive=True)):
        rel = Path(f).relative_to(runs_dir).as_posix()
        fig = rel.split("/")[0]
        t = Path(f).read_text(encoding="utf8", errors="replace")
        def g(p, d=""):
            m = re.search(p, t)
            return m.group(1).strip() if m else d
        cc = g(r"sender based algo\s+(\S+)")
        rows.append(dict(
            run=rel[:-len("/stdout.txt")],
            driver=DRIVER[fig],
            topology=g(r"topology input file:\s*\S*/([^/\s]+)\.topo"),
            hosts=g(r"Nodes:\s+(\d+)"),
            paths=g(r"no of paths\s+(\d+)"),
            LB=g(r"Load balancing algorithm set to\s+(\S+)"),
            srv6="yes" if "SRv6 source routing enabled" in t else "no",
            reps_buf=g(r"REPS buffer size set to\s+(\d+)", "-"),
            CC=(f"sender-only {cc}" if "sender based CC enabled ONLY" in t else cc),
            workload=g(r"traffic matrix input file:\s*\S*/([^/\s]+)"),
            cm_flows=g(r"Connections:\s+(\d+)"),
            seed=g(r"random seed\s+(\d+)"),
            failure_input=g(r"Parsing failuregenerator_input file:\s*\S*/([^/\s]+)", "(none)"),
        ))
    return rows


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--build":
        rows = build(EXP / "runs")
        with open(MANIFEST, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader(); w.writerows(rows)
        print(f"{len(rows)} runs -> {MANIFEST}")
        return

    rows = list(csv.DictReader(open(MANIFEST)))
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["run"].rsplit("/", 1)[0], []).append(r)

    hdr = ("group (fig / workload / condition)", "topology", "hosts", "paths",
           "CC", "workload.cm", "seed", "failure_input", "arms (LB)")
    wds = (46, 26, 5, 5, 15, 27, 5, 38, 0)
    print("  ".join(h.ljust(w) for h, w in zip(hdr, wds)))
    print("-" * 210)
    for k, v in groups.items():
        a = v[0]
        arms = sorted(v, key=lambda z: (z["reps_buf"] == "-" and 0
                                        or int(z["reps_buf"]) if z["reps_buf"] != "-" else -1))
        arms = ["ops"] + [f"B={z['reps_buf']}" for z in
                          sorted((z for z in v if z["reps_buf"] != "-"),
                                 key=lambda z: int(z["reps_buf"]))]
        cells = (k, a["topology"], a["hosts"], a["paths"], a["CC"], a["workload"],
                 a["seed"], a["failure_input"], " ".join(arms))
        print("  ".join(str(c).ljust(w) for c, w in zip(cells, wds)))
    print("\nEvery run: -use_srv6, -paths = the topology's distinct physical-path "
          "count.\narm 'ops' = -load_balancing_algo oblivious ; 'B=N' = "
          "-load_balancing_algo freezing -reps_buffer_size N.")


if __name__ == "__main__":
    main()
