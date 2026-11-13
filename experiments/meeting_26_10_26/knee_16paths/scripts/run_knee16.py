#!/usr/bin/env python3
"""Runner for knee configs: T3's run_cell with the config table swapped for configs_knee16.json and each config's `extra` flags appended.
Run in the container next to run_t3.py/run_m4.py/configs_knee16.json:
  python3 run_knee.py --out /kneeout --cfgs NAME... --seeds 42 43 44 --bs 2 4 8 --workers 6"""
import argparse, json, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_t3 as r

CFGS = {c["name"]: c for c in json.loads((HERE / "configs_knee16.json").read_text())}
if (HERE / "configs_knee16_q.json").exists():   # queue-depth control configs (make_knee16_q_configs.py)
    CFGS.update({c["name"]: c for c in json.loads((HERE / "configs_knee16_q.json").read_text())})
if (HERE / "configs_knee16_dps.json").exists():   # DPS arm (make_knee16_dps_configs.py): REPS algo replaced by -load_balancing_algo dps
    CFGS.update({c["name"]: c for c in json.loads((HERE / "configs_knee16_dps.json").read_text())})
if (HERE / "configs_knee16_bank.json").exists():   # REPS-Bank arm (make_knee16_bank_configs.py): REPS + -reps_bank, bank log kept next to the traces
    CFGS.update({c["name"]: c for c in json.loads((HERE / "configs_knee16_bank.json").read_text())})
if (HERE / "configs_knee16_bankN.json").exists():  # bank size = N variant (make_knee16_bankN_configs.py)
    CFGS.update({c["name"]: c for c in json.loads((HERE / "configs_knee16_bankN.json").read_text())})
r.CFGS.clear(); r.CFGS.update(CFGS)
_flags = r.flags


def _knee_flags(cfg, B, seed):
    f = _flags(cfg, B, seed) + list(cfg.get("extra", []))
    if "dps" in cfg:                                  # replace the `-load_balancing_algo freezing` of run_m4.flags, do not append a second one
        i = f.index("-load_balancing_algo"); assert f[i + 1] == "freezing"
        f[i + 1] = "dps"
        f += ["-dps_dist"] + [str(a) for a in cfg["dps"]]
    if "bank" in cfg:                                 # REPS-Bank: -reps_bank_target_rtt_us only when the cfg gives one (omitted = NSCC base_rtt + target_Qdelay)
        b = cfg["bank"]
        f += ["-reps_bank", "-reps_bank_size", str(b["size"]), "-reps_bank_timer_us", str(b["timer_us"])]
        if b.get("target_us") is not None: f += ["-reps_bank_target_rtt_us", str(b["target_us"])]
        f += ["-log_reps_bank", f"/tmp/bank_{cfg['name']}_B{B}_s{seed}.csv"]
    return f


r.flags = _knee_flags
_run_cell = r.run_cell


def _run_cell_bank(cell, out):                        # keep the bank log (gzip, next to the trace files); run_t3.run_cell itself is shared and unchanged
    row = _run_cell(cell, out)
    name, B, seed = cell
    src = f"/tmp/bank_{name}_B{B}_s{seed}.csv"
    if "bank" in CFGS[name] and os.path.exists(src):
        td = Path(out) / "traces"; td.mkdir(parents=True, exist_ok=True)
        subprocess.run(["gzip", "-9", "-c", src], stdout=open(td / f"{name}_B{B}_s{seed}.bank.csv.gz", "wb"), check=True)
        os.unlink(src)
    return row


r.run_cell = _run_cell_bank

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/kneeout"); ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seeds", type=int, nargs="*", default=[42]); ap.add_argument("--cfgs", nargs="*", default=list(CFGS))
    ap.add_argument("--bs", type=int, nargs="*", default=r.BS)
    ap.add_argument("--bsmap", default=None, help='JSON {cfg: [B, ...]} overriding --bs per cfg (N sweep: the B range scales with N)')
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    resf = out / "results.jsonl"
    done = {(d["cfg"], d["B"], d["seed"]) for d in map(json.loads, resf.read_text().splitlines())} if resf.exists() else set()
    bsmap = json.loads(Path(a.bsmap).read_text()) if a.bsmap else {}
    jobs = [(c, B, s) for s in a.seeds for c in a.cfgs for B in bsmap.get(c, a.bs) if (c, B, s) not in done]
    print(f"{len(jobs)} cells to run", flush=True)
    def work(c):
        try: return c, r.run_cell(c, out), None
        except Exception as e: return c, None, str(e)
    with ThreadPoolExecutor(a.workers) as ex:
        for c, row, err in ex.map(work, jobs):
            if err: print("FAIL", c, err, flush=True); continue
            with open(resf, "a") as fh: fh.write(json.dumps(row) + "\n")
            print("ok", c, row["fct_max"], row["pct_random"], "rtos", row["rtos"], "frz", row["freeze_entries"], row["secs"], flush=True)
