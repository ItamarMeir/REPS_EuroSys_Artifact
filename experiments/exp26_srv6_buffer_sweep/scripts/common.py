#!/usr/bin/env python3
"""
Shared config + run helper for exp26.

exp26 re-runs the exact conditions/topologies/seeds of artifact figures 2, 4, 6,
7 and 8, changing ONLY the load-balancing arm set:

  * every run adds ``-use_srv6`` (entropy folded onto an explicit physical path,
    ``ev % _paths.size()``, bypassing per-hop ECMP);
  * every run's ``-paths`` is set to the topology's distinct physical-path count
    (verified against the ``distinct_paths=`` banner, see PATHS below);
  * the LB sweep of each figure is replaced by:
      - ``ops``      : ``-load_balancing_algo oblivious``  (restricted-EV OPS baseline)
      - ``reps_b<B>``: ``-load_balancing_algo freezing -reps_buffer_size <B>``
                       for B = 1,2,4,8,... up to and including n_paths.

Nothing else changes. No ``-smart_filter_*`` flags (smart-filter stays off by
default; ``-reps_buffer_size`` only calls ``CircularBufferREPS::setBufferSize``).

Scripts are written to run inside the WSL Ubuntu environment where the Linux
``htsim_uec`` binary executes; paths below are POSIX.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[3]
DC_DIR = REPO_ROOT / "htsim" / "sim" / "datacenter"
HTSIM = DC_DIR / "htsim_uec"
FAILURES_DIR = REPO_ROOT / "htsim" / "sim" / "failures_input"

EXP_DIR = Path(__file__).resolve().parents[1]
# EXP26_RUNS / EXP26_DATA let a verification run (e.g. inside Docker) write to a
# separate tree without clobbering the primary results.
RUNS_DIR = Path(os.environ.get("EXP26_RUNS", EXP_DIR / "runs"))
DATA_DIR = Path(os.environ.get("EXP26_DATA", EXP_DIR / "data"))
PLOTS_DIR = EXP_DIR / "plots"

# ---------------------------------------------------------------------------
# Distinct physical-path count per topology.
# VERIFIED 2026-08-29 against the `SRv6: <s>-><d> distinct_paths=N` banner
# (htsim main_uec.cpp:1688) with -use_srv6 on each topology.
# ---------------------------------------------------------------------------
PATHS = {
    "fat_tree_32_1os_2t_400g": 4,
    "fat_tree_128_1os_2t_400g": 8,
    "fat_tree_1024_1os_2t_400g": 32,
    "fat_tree_128_1os_3t_400g": 16,
}


def b_ladder(n_paths: int) -> list[int]:
    """[1, 2, 4, 8, ...] powers of two, then n_paths itself."""
    out: list[int] = []
    b = 1
    while b < n_paths:
        out.append(b)
        b *= 2
    out.append(n_paths)
    # dedupe + sort (n_paths may already be a power of two)
    return sorted(set(out))


def arm_lb_flags(arm: str, n_paths: int) -> list[str]:
    """Return the LB/paths/srv6/buffer tokens for an arm id.

    Every arm gets ``-use_srv6`` and ``-paths <n_paths>``.
    """
    common = ["-use_srv6", "-paths", str(n_paths)]
    if arm == "ops":
        return ["-load_balancing_algo", "oblivious", *common]
    if arm.startswith("reps_b"):
        b = int(arm[len("reps_b"):])
        return ["-load_balancing_algo", "freezing", *common,
                "-reps_buffer_size", str(b)]
    raise ValueError(f"unknown arm {arm!r}")


def arms_for(n_paths: int) -> list[str]:
    return ["ops"] + [f"reps_b{b}" for b in b_ladder(n_paths)]


def get_bdp(link_speed_mbps: float, tiers: int, link_delay_ns: float) -> float:
    """Verbatim port of getBDP() from run_failures.py / run_symmetric.py."""
    link_speed = link_speed_mbps / 1000.0
    network_rtt = link_delay_ns * (tiers * 2 * 2) + (tiers * 2 * (4096 * 8 / link_speed))
    return network_rtt * link_speed / 8 / 4096


# ---------------------------------------------------------------------------
# Run helper
# ---------------------------------------------------------------------------
_NOISE = b"Dropping a PKT"


def _filter_stream(proc: subprocess.Popen, fh) -> int:
    """Stream proc.stdout to fh, collapsing the newline-less 'Dropping a PKT'
    spam (htsim prints it per drop with no separator) into a running count.

    Writing that spam verbatim onto the WSL /mnt/c 9p mount is minutes-slow;
    collapsing it keeps stdout.txt small and the aggregator only needs the
    'finished at' lines and banners anyway.
    Returns the number of dropped-packet notices removed.
    """
    carry = b""
    ndrop = 0
    while True:
        chunk = proc.stdout.read(65536)
        if not chunk:
            break
        buf = carry + chunk
        n = buf.count(_NOISE)
        if n:
            ndrop += n
            buf = buf.replace(_NOISE, b"")
        # keep a tail that might be a split 'Dropping a PKT'
        carry = buf[-(len(_NOISE) - 1):]
        fh.write(buf[:len(buf) - len(carry)] if carry else buf)
    if carry:
        fh.write(carry)
    if ndrop:
        fh.write(f"\n[exp26: collapsed {ndrop} 'Dropping a PKT' notices]\n".encode())
    return ndrop


# The repo lives on the WSL /mnt/c 9p mount, where many-small-append I/O
# (-collect_data) and byte-streamed writes are ~100x slower than a Linux fs.
# Run everything against a Linux-local scratch dir, then copy results back.
SCRATCH_ROOT = Path(os.environ.get("EXP26_SCRATCH", "/tmp/exp26_scratch"))

_CM_NODES_RE = re.compile(r"^Nodes:\s+(\d+)\s+Connections:\s+(\d+)", re.MULTILINE)
_TOPO_HOSTS_RE = re.compile(r"fat_tree_(\d+)_")


def cm_nodes_check(txt: str, flags: list[str],
                   expect_cm_nodes: int | None = None) -> str | None:
    """Return a warning string if the connection matrix does not match the topology.

    htsim prints ``Nodes: <N> Connections: <C>`` for the loaded ``-tm`` file and
    the topology's host count is in the ``-topo`` filename
    (``fat_tree_<hosts>_...``). A mismatch means the run used a workload built
    for a different-sized fabric -- exactly the bug that silently made exp26's
    first fig2/fig4 ai runs use 32-rank collectives on 128 hosts.

    ``expect_cm_nodes`` overrides the topology-derived expectation, for the
    panels where the paper deliberately runs a smaller matrix (fig2/fig4 dc uses
    the 32-rank ``*load_ae.cm`` artifact-evaluation matrices on 128 hosts,
    because ``run_dc.py --ae_runs`` defaults to True).
    """
    m = _CM_NODES_RE.search(txt)
    if not m:
        return None
    cm_nodes = int(m.group(1))
    if expect_cm_nodes is None:
        try:
            topo = flags[flags.index("-topo") + 1]
        except (ValueError, IndexError):
            return None
        t = _TOPO_HOSTS_RE.search(str(topo))
        if not t:
            return None
        expect_cm_nodes = int(t.group(1))
    if cm_nodes != expect_cm_nodes:
        return f"cm-nodes={cm_nodes} vs expected={expect_cm_nodes}"
    return None


def run_one(extra_flags: list[str], outfile: Path, *, cwd: Path = DC_DIR,
            timeout_s: int = 36000, save_data_dest: Path | None = None,
            expect_cm_nodes: int | None = None) -> dict:
    """Run htsim_uec with ``extra_flags``, capturing filtered stdout+stderr to
    ``outfile`` (which may live on the slow /mnt/c mount).

    stdout is streamed to a Linux-local temp file first, then moved to
    ``outfile``. If ``save_data_dest`` is given, ``-save_data_folder <local>`` is
    injected and the resulting tree is copied to ``save_data_dest`` afterwards.

    Idempotent: a run whose ``outfile`` already ends with ``Bounced:`` (or has a
    ``finished at`` line) is skipped; an interrupted one is re-run.

    Returns a dict: status, nflows, seconds, tor_ecn_reenabled, ndrop.
    """
    outfile = Path(outfile)
    if outfile.exists() and outfile.stat().st_size > 0:
        head_tail = outfile.read_text(errors="replace")
        if "Bounced:" in head_tail or "finished at" in head_tail:
            return {"status": "skip", "nflows": head_tail.count("finished at"),
                    "seconds": 0.0, "tor_ecn_reenabled": None, "ndrop": None,
                    "cm_warn": cm_nodes_check(head_tail, extra_flags,
                                              expect_cm_nodes)}
        outfile.unlink()  # incomplete / interrupted -> rerun

    outfile.parent.mkdir(parents=True, exist_ok=True)
    SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(dir=SCRATCH_ROOT))
    local_out = scratch / "stdout.txt"

    flags = list(extra_flags)
    if save_data_dest is not None:
        local_sdf = scratch / "raw_output"
        local_sdf.mkdir()
        flags += ["-save_data_folder", str(local_sdf)]

    cmd = [str(HTSIM), *[str(x) for x in flags]]
    t0 = time.time()
    with open(local_out, "wb") as fh:
        proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, bufsize=0)
        try:
            ndrop = _filter_stream(proc, fh)
            rc = proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            proc.kill()
            rc = -9
            ndrop = -1
    dt = time.time() - t0

    shutil.move(str(local_out), str(outfile))
    if save_data_dest is not None:
        if save_data_dest.exists():
            shutil.rmtree(save_data_dest)
        shutil.copytree(scratch / "raw_output", save_data_dest)
    shutil.rmtree(scratch, ignore_errors=True)

    txt = outfile.read_text(errors="replace")
    nflows = txt.count("finished at")
    tor_ecn = "enable on tor downlink 1" in txt
    ok = rc == 0 and nflows > 0
    return {
        "status": "ok" if ok else f"FAIL(rc={rc},flows={nflows})",
        "nflows": nflows,
        "seconds": round(dt, 1),
        "tor_ecn_reenabled": tor_ecn,
        "ndrop": ndrop,
        "cm_warn": cm_nodes_check(txt, extra_flags, expect_cm_nodes),
    }


def emit(idx: int, total: int, name: str, res: dict) -> None:
    tag = res["status"]
    extra = ""
    if res["nflows"] is not None:
        extra = f"  {res['nflows']} flows, {res['seconds']}s"
    if res["tor_ecn_reenabled"]:
        extra += "  [tor-ecn-reenabled]"
    if res.get("cm_warn"):
        extra += f"  *** WRONG CONNECTION MATRIX: {res['cm_warn']} ***"
    print(f"[{idx}/{total}] {tag:<20} {name}{extra}", flush=True)
