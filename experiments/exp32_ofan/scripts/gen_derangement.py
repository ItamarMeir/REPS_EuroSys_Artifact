#!/usr/bin/env python3
"""Inter-pod derangement traffic matrix (paper arXiv 2610.07230 Figs 1,3,4 style).

Random permutation where every host sends exactly 1 flow and receives exactly 1,
and pod(src) != pod(dst) for every flow (pod = host // hosts_per_pod).

Usage: gen_derangement.py <out.cm> <nodes> <hosts_per_pod> <size_bytes> <seed> [perm]
Output format = htsim connection_matrices (same as gen_permutation.py):
  Nodes N / Connections N / "s->d id i start 0 size B".

hosts_per_pod (= topo file "Podsize"):
  fat_tree_16_1os_3t_400g.topo  : 4  (k=4)
  fat_tree_54_1os_3t_400g.topo  : 9  (k=6)
  fat_tree_128_1os_3t_400g.topo : 16 (k=8; check Podsize in the file)
  paper k=12 / 432 hosts        : 36 (no such .topo in the repo; see exp32 README)
"""
import random, sys

def derangement(n, pod, rng):
    # Rejection sampling over random permutations (fine for few hosts per pod / many
    # pods... acceptance ~ exp(-n/(n/pod)) = exp(-pod)); for large pods (e.g. 432/36)
    # fall back to swap repair: swap d[s] with d[t] while both stay inter-pod.
    for _ in range(2000):
        d = list(range(n)); rng.shuffle(d)
        if all(s // pod != d[s] // pod for s in range(n)):
            return d
    d = list(range(n)); rng.shuffle(d)
    for _ in range(1000000):
        bad = [s for s in range(n) if s // pod == d[s] // pod]
        if not bad:
            return d
        s = rng.choice(bad)
        t = rng.randrange(n)
        if t // pod != d[s] // pod and s // pod != d[t] // pod:
            d[s], d[t] = d[t], d[s]
    raise SystemExit("failed to find inter-pod derangement (need >=2 pods, equal-ish sizes)")

def main():
    if len(sys.argv) not in (6, 7):
        sys.exit(__doc__)
    # optional 6th arg "perm": plain random permutation without fixed points (intra-pod allowed)
    plain = len(sys.argv) == 7 and sys.argv[6] == "perm"
    out, n, pod, size, seed = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
    if n % pod or n // pod < 2:
        sys.exit("nodes must be a multiple of hosts_per_pod with >= 2 pods")
    rng = random.Random(seed)
    if plain:
        while True:
            d = list(range(n)); rng.shuffle(d)
            if all(d[s] != s for s in range(n)): break
    else:
        d = derangement(n, pod, rng)
    with open(out, "w", newline="\n") as f:
        f.write("Nodes %d\nConnections %d\n" % (n, n))
        for s in range(n):
            f.write("%d->%d id %d start 0 size %d\n" % (s, d[s], s + 1, size))

if __name__ == "__main__":
    main()
