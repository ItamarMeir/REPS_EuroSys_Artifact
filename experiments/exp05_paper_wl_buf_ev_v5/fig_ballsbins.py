#!/usr/bin/env python3
"""
fig_ballsbins.py — exp05 Part C: balls-in-bins queue size analysis.

Pure Python simulation — no htsim needed.
Extends the paper's fig_13_queue_ballsbins.py with two parameterised sweeps:

  C1  Max queue size vs EV domain  (extends fig_13: EV ∈ {1,2,4,8,16,32,256,65535})
      Models: how many distinct output ports are reachable → more EVs = better spread.

  C2  Max queue size vs buffer size (novel adaptation of fig_13)
      Models: REPS FREEZING buffer B limits the "hot" port set to B entries.
      buf=1  → only 1 effective path  → queue grows as O(n)
      buf=∞  → full port diversity   → minimum achievable queue depth

Provides the analytical backing for the empirical FCT and port-util results from Parts A & B.
"""

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import functools

matplotlib.rcParams['pdf.fonttype'] = 42
matplotlib.rcParams['ps.fonttype'] = 42

SCRIPT_DIR = Path(__file__).resolve().parent
PLOT_DIR   = SCRIPT_DIR / "plots"
PLOT_DIR.mkdir(parents=True, exist_ok=True)

# Paper palette
DARK2 = ['#1b9e77','#d95f02','#7570b3','#e7298a','#66a61e','#e6ab02','#a6761d','#666666']
MARKERS = ['o','s','D','^','v','p','*','X']

plt.rcParams.update({
    'axes.titlesize': 14, 'axes.labelsize': 13,
    'xtick.labelsize': 11, 'ytick.labelsize': 11,
    'legend.fontsize': 11,
})

# ── Simulation parameters (matching fig_13) ────────────────────────────────────
NUM_PHYSICAL_PORTS = 16    # k=8 fat-tree: (k/2)^2 = 16 physical cross-pod paths
ROUNDS      = 1000         # rounds of packet spraying to simulate
TRIALS      = 300          # number of independent trials to average
BATCH_SIZE  = 50           # record max queue every BATCH_SIZE rounds

# ── Core balls-in-bins simulation ─────────────────────────────────────────────
# Network interpretation:
#   - NUM_PHYSICAL_PORTS senders (input ports) each produce 1 packet per round
#   - Packets are sprayed across n_outputs output ports
#   - Each output port drains 1 packet per round (service rate = link rate / n_outputs)
# This matches the paper's fig_13 model where n_inputs == n_outputs == num_ports.
# For our sweeps we fix n_senders = NUM_PHYSICAL_PORTS and vary the output domain.

N_SENDERS = NUM_PHYSICAL_PORTS   # 16 senders (input ports), always fixed

def simulate_balls_in_bins(n_outputs, rounds, batch_size=BATCH_SIZE):
    """
    Standard balls-in-bins:
    - N_SENDERS packets per round, each to a uniformly random output port
    - Each output port drains 1 packet/round
    - n_outputs: size of the output port domain (EV domain or physical paths)
    Returns avg-max queue size sampled every batch_size rounds.
    """
    queues = np.zeros(n_outputs)
    max_sizes = []
    for r in range(rounds):
        ports = np.random.randint(0, n_outputs, size=N_SENDERS)
        np.add.at(queues, ports, 0.99)
        queues = np.maximum(queues - 1, 0)
        if (r + 1) % batch_size == 0:
            max_sizes.append(float(np.max(queues)))
    return max_sizes


def simulate_buffer_constrained(buf_size, n_full_ports, rounds, batch_size=BATCH_SIZE):
    """
    Buffer-constrained balls-in-bins: models REPS FREEZING with buffer size B.

    In steady state the REPS circular buffer holds min(B, n_full_ports) distinct
    entropy values.  Senders can only choose paths drawn from that set, so the
    effective output-port diversity is exactly min(B, n_full_ports).

    We model this by running the standard balls-in-bins simulation with
    n_outputs = min(buf_size, n_full_ports), which is analytically correct:
    restricting the domain to B paths is equivalent to having B physical ports.

    Consequence:
      buf=1  → all N packets go to the same port every round → unbounded growth
      buf=B  → B-bin balls-in-bins → same curve as C1 at EV=B
      buf≥16 → full 16-port diversity → minimum achievable queue depth
    """
    effective = min(buf_size, n_full_ports)
    return simulate_balls_in_bins(effective, rounds, batch_size)


def avg_over_trials(sim_fn, trials=TRIALS):
    results = [sim_fn() for _ in range(trials)]
    return np.mean(results, axis=0)

x_axis = np.linspace(0, ROUNDS, ROUNDS // BATCH_SIZE)

# ══════════════════════════════════════════════════════════════════════════════
# C1: Max queue size vs EV domain  (extends fig_13)
# ══════════════════════════════════════════════════════════════════════════════
print("=== C1: EV domain balls-in-bins ===")

EV_VALUES_C1 = [1, 2, 4, 8, 16, 32, 256, 65535]
EV_LABELS_C1 = ["1 EV", "2 EVs", "4 EVs", "8 EVs",
                 "16 EVs (full)", "32 EVs", "256 EVs", "64K EVs"]

fig = plt.figure(figsize=(8, 3.0))

for i, (ev, label) in enumerate(zip(EV_VALUES_C1, EV_LABELS_C1)):
    effective_ports = min(ev, NUM_PHYSICAL_PORTS)
    fn = functools.partial(simulate_balls_in_bins, effective_ports, ROUNDS, BATCH_SIZE)
    avg = avg_over_trials(fn)
    plt.plot(x_axis, avg,
             label=label,
             color=DARK2[i % len(DARK2)],
             marker=MARKERS[i % len(MARKERS)],
             linewidth=2.2,
             markersize=7.0,
             markevery=int(len(avg) / 5))
    print(f"  EV={ev:6d}  (effective ports={effective_ports:2d})  steady-state max queue ≈ {avg[-1]:.2f}")

plt.xlabel("Balls-into-Bins Round", fontsize=12)
plt.ylabel("Avg. Max Queue Size (Pkts)", fontsize=12)
plt.title(
    f"Queue Size vs EV Domain  ({NUM_PHYSICAL_PORTS} physical output ports)\n"
    "More EVs → smaller max queue → better routing efficiency",
    fontsize=11,
)
plt.legend(ncol=2, loc='upper left', fontsize=10)
plt.grid(True, linestyle=':', linewidth=0.75, alpha=0.75)
plt.tight_layout()
for ext in (".png", ".pdf"):
    fig.savefig(str(PLOT_DIR / ("C1_ballsbins_ev_domain" + ext)), dpi=300, bbox_inches='tight')
plt.close(fig)
print("  Saved C1_ballsbins_ev_domain.png\n")

# ══════════════════════════════════════════════════════════════════════════════
# C2: Max queue size vs buffer size  (novel)
# ══════════════════════════════════════════════════════════════════════════════
print("=== C2: buffer size balls-in-bins ===")

BUF_VALUES_C2 = [1, 2, 4, 8, 16, 1024]
BUF_LABELS_C2 = ["buf=1", "buf=2", "buf=4", "buf=8", "buf=16", "buf=∞"]

fig = plt.figure(figsize=(8, 3.0))

for i, (buf, label) in enumerate(zip(BUF_VALUES_C2, BUF_LABELS_C2)):
    fn = functools.partial(simulate_buffer_constrained,
                           buf, NUM_PHYSICAL_PORTS, ROUNDS, BATCH_SIZE)
    avg = avg_over_trials(fn)
    plt.plot(x_axis, avg,
             label=label,
             color=DARK2[i % len(DARK2)],
             marker=MARKERS[i % len(MARKERS)],
             linewidth=2.2,
             markersize=7.0,
             markevery=int(len(avg) / 5))
    print(f"  buf={buf:4d}  (effective ports={min(buf,NUM_PHYSICAL_PORTS):2d})  "
          f"steady-state max queue ≈ {avg[-1]:.2f}")

plt.xlabel("Balls-into-Bins Round", fontsize=12)
plt.ylabel("Avg. Max Queue Size (Pkts)", fontsize=12)
plt.title(
    f"Queue Size vs REPS Buffer Size  ({NUM_PHYSICAL_PORTS} physical output ports, full EV domain)\n"
    "Larger buffer → more path diversity → lower congestion",
    fontsize=11,
)
plt.legend(ncol=2, loc='upper left', fontsize=10)
plt.grid(True, linestyle=':', linewidth=0.75, alpha=0.75)
plt.tight_layout()
for ext in (".png", ".pdf"):
    fig.savefig(str(PLOT_DIR / ("C2_ballsbins_buf_size" + ext)), dpi=300, bbox_inches='tight')
plt.close(fig)
print("  Saved C2_ballsbins_buf_size.png")

print(f"\nAll Part C plots saved to {PLOT_DIR}")
