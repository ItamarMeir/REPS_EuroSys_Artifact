#!/usr/bin/env python3
"""Paper-workload regenerator.

Emits five workload families x three seeds = 15 TM files in this directory,
reproducing the workloads from the MSwift/MNSCC paper:
"Congestion Control for Spraying with Congested Paths"
(Gerstein, Silberstein, Keslassy; arXiv:2509.07907).

The paper's pure-permutation workload already exists as
htsim/sim/datacenter/connection_matrices/perm_n128_s8388608.cm
and is referenced (not duplicated) by the README.

Workload IDs (used by class-aware aggregators):
  paper_baseline_s{seed}.cm        ids 1-4   = ECMP elephants (long-lived, 64 MB)
                                   ids 5-128 = sprayed permutation (8 MB)
  paper_baseline_16mb_s{seed}.cm   same layout, sprayed = 16 MB
  paper_baseline_8ecmp_s{seed}.cm  ids 1-8   = ECMP elephants
                                   ids 9-128 = sprayed permutation (8 MB)
  paper_hsdp_s{seed}.cm            ids 1-128 = HSDP ring flows (~13.7 MB each)
  paper_incast32_s{seed}.cm        ids 1-32  = senders -> single victim (8 MB)

ECMP-vs-sprayed caveat: htsim sets `-load_balancing_algo` globally, so all
flows in a single run use the same LB. ECMP-elephant IDs identify the paper's
intent; in practice the elephants become long-lived sprayed elephants
creating equivalent in-network congestion.
"""
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
N    = 128
US   = 1_000_000
SEEDS = [42, 43, 44, 45, 46, 47]

SIZE_8MB  =  8_388_608
SIZE_16MB = 16_777_216
SIZE_64MB = 67_108_864      # long-lived ECMP elephants
SIZE_HSDP = 3344 * 4096     # 13,697,024 B (paper: 3344 packets x 4 KB MTU)


def write_tm(path, flows, n_nodes=None):
    if n_nodes is None:
        n_nodes = N
    with open(path, "w") as fh:
        fh.write(f"Nodes {n_nodes}\nConnections {len(flows)}\n")
        for ln in flows:
            fh.write(ln + "\n")
    print(f"wrote {path}: connections={len(flows)}")


def _avoid_self_loop(perm_list, idx, fallback_pool):
    """If perm_list[idx] would be a self-loop with fallback_pool[idx],
    rotate the destination by 1 (matches gen_composite.py style)."""
    if perm_list[idx] == fallback_pool[idx]:
        return perm_list[(idx + 1) % len(perm_list)]
    return perm_list[idx]


def gen_baseline(seed, n_ecmp=4, sprayed_size=SIZE_8MB, sprayed_start_us=0, n_hosts=None):
    """n_ecmp ECMP elephants + (n_hosts - n_ecmp) sprayed permutation.

    n_hosts: defaults to module N=128. Pass 250 for Fig 8.
    sprayed_start_us: delay (µs) before sprayed flows begin. Default 0 matches
    paper §IV.A's unspecified-but-default-coincident-start. Tested 50 µs
    stagger (H5 in exp13's Fig 4 workload-side investigation); did not close
    the MSwift gap to paper, so default reverted to 0."""
    if n_hosts is None:
        n_hosts = N
    rng = random.Random(seed)
    hosts = list(range(n_hosts))

    ecmp_hosts = rng.sample(hosts, n_ecmp)
    ecmp_dst   = ecmp_hosts[:]; rng.shuffle(ecmp_dst)

    sprayed_hosts = [h for h in hosts if h not in set(ecmp_hosts)]
    sprayed_dst   = sprayed_hosts[:]; rng.shuffle(sprayed_dst)

    flows = []
    fid = 0
    for i, s in enumerate(ecmp_hosts):
        d = _avoid_self_loop(ecmp_dst, i, ecmp_hosts)
        fid += 1
        flows.append(f"{s}->{d} id {fid} start 0 size {SIZE_64MB}")
    sprayed_start_ps = sprayed_start_us * US
    for i, s in enumerate(sprayed_hosts):
        d = _avoid_self_loop(sprayed_dst, i, sprayed_hosts)
        fid += 1
        flows.append(f"{s}->{d} id {fid} start {sprayed_start_ps} size {sprayed_size}")
    return flows


def gen_hsdp(seed):
    """HSDP / Llama-3 70B ring step: logical i -> logical (i+8) mod 128,
    with random server placement (logical->physical permutation)."""
    rng = random.Random(seed)
    physical = list(range(N))
    rng.shuffle(physical)  # logical -> physical mapping
    flows = []
    for logical in range(N):
        s = physical[logical]
        d = physical[(logical + 8) % N]
        flows.append(f"{s}->{d} id {logical + 1} start 0 size {SIZE_HSDP}")
    return flows


def gen_incast32(seed):
    """32 random sources -> 1 random victim, 8 MB each."""
    rng = random.Random(seed)
    victim = rng.randrange(N)
    senders = rng.sample([h for h in range(N) if h != victim], 32)
    return [f"{s}->{victim} id {i + 1} start 0 size {SIZE_8MB}"
            for i, s in enumerate(senders)]


def main():
    for seed in SEEDS:
        write_tm(os.path.join(HERE, f"paper_baseline_s{seed}.cm"),
                 gen_baseline(seed))
        write_tm(os.path.join(HERE, f"paper_baseline_16mb_s{seed}.cm"),
                 gen_baseline(seed, sprayed_size=SIZE_16MB))
        write_tm(os.path.join(HERE, f"paper_baseline_8ecmp_s{seed}.cm"),
                 gen_baseline(seed, n_ecmp=8))
        write_tm(os.path.join(HERE, f"paper_hsdp_s{seed}.cm"),
                 gen_hsdp(seed))
        write_tm(os.path.join(HERE, f"paper_incast32_s{seed}.cm"),
                 gen_incast32(seed))
        # Paper 2 Fig 8: 250-node scaled baseline.
        # Paper §IV.D: "increasing the three-level fat-tree network size from
        # 128 to 250 nodes while keeping four elephants (and 250-4 = 246
        # sprayed flows)."
        write_tm(os.path.join(HERE, f"paper_baseline_250n_s{seed}.cm"),
                 gen_baseline(seed, n_hosts=250),
                 n_nodes=250)


if __name__ == "__main__":
    main()
