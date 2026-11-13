# Distribution Packet Spraying (DPS, `-load_balancing_algo dps`)

## Purpose
OPS (`-load_balancing_algo oblivious`) draws every packet's EV uniformly. REPS recycles good EVs from a bounded buffer and falls back to a uniform draw. DPS is the missing comparator: **every packet draws its EV independently from a given distribution over the EV space, with no buffer and no feedback.** It separates two things that "god mode" (`-reps_draw_weights capacity`, REPS buffer + capacity-weighted fallback draws) mixes: the value of knowing a good distribution, and the value of the REPS buffer.

DPS is general: any distribution over the EV index can be given. The 95% / 5% case of the knee_16paths fabric (8 links at 20G, 8 at 380G) is just `capacity`.

## What OPS teaches (and DPS copies)
OPS is `nextEntropy_oblivious() { return rand() % _no_of_paths; }` plus an empty `processEv_oblivious`, selected by a function-pointer pair in the per-host LB dispatch (`uec.cpp`). No state, no init RNG, one `rand()` per packet. DPS has the same skeleton (`nextEntropy_dps`, empty `processEv_dps`). The only addition is a per-source CDF, built lazily at the first draw. **Equal weights take the OPS draw (`rand() % N`), so DPS with a manual uniform distribution is byte-identical to OPS** (checked, see Verification in `MODIFICATIONS.md`).

## Flags
| Flag | Effect |
|---|---|
| `-load_balancing_algo dps` | Selects DPS. Also valid as an entry of `-host_lb_overrides`. Requires `-dps_dist`. |
| `-dps_dist <name> [args]` | The distribution over EV index e = 0..N-1 (N = `-paths`). Normalised internally. |
| `-dps_perm <seed>` | Fixed random relabelling of the EVs (same masses, different EV positions). Uses its own generator, not the libc `rand()` stream. |

`-dps_dist` names (implemented in `htsim/sim/dps_dist.h`, header-only, no htsim dependency):

| Name | Arguments | pmf over e = 0..N-1 |
|---|---|---|
| `uniform` | none | 1/N (OPS) |
| `list` | `w0,w1,..,w{N-1}` | any non-negative weights, length must equal N |
| `file` | path | one weight per whitespace-separated token, count must equal N (for large EV spaces) |
| `capacity` | none | bottleneck speed (Mbit/s) of route `e % P`; needs `-use_srv6`; same rule as `-reps_draw_weights capacity` |
| `normal` | `mu sigma` | probability of the unit bin [e-0.5, e+0.5] under N(mu, sigma), truncated to the EV range |
| `poisson` | `lambda` | e^-lambda lambda^e / e!, truncated |
| `binomial` | `n p` | C(n,e) p^e (1-p)^(n-e), zero above n |
| `geometric` | `p` | p (1-p)^e, truncated |
| `zipf` | `s` | 1/(e+1)^s |

Startup errors (exit 1, before any flow runs): `dps` without `-dps_dist`; `-dps_dist`/`-dps_perm` without `dps`; unknown name; wrong argument count or non-numeric argument; list/file length != `-paths`; negative, NaN or all-zero weights; `capacity` without `-use_srv6`; unreadable file. A bad spec never silently becomes uniform. The one runtime exception: with `capacity`, a source that has 0 or 1 route (e.g. a same-ToR pair) has nothing to weight and draws OPS (`rand() % N`); the first such source prints one `dps_dist capacity: ... nothing to weight` note, later ones are silent.

## Mechanism
- One `rand()` per draw, none at init: `u = rand() / (RAND_MAX + 1.0)`, EV = first index whose CDF exceeds u (zero-mass EVs are never drawn). Uniform weights (exact equality of the raw weights) use `rand() % N`.
- Retransmissions and RTS redraw (they call `nextEntropy` like every other algorithm); DPS never reacts to ACK, ECN, NACK or trimming.
- Weights are fixed at the first draw of a source; they do not follow link swaps or failures (same as god mode). `capacity` differs per source host (a host whose uplinks are all equal gets uniform).
- Under SRv6 the EV is the path (`_paths[ev % P]`). Without SRv6 the EV is only ECMP-hashed by the switches, so a non-uniform pmf over EVs does not give a controlled link share; use `-use_srv6` for link-level claims.
- Trace rows (`-log_reps_events`) carry `ev_src = dps`. The simulator prints one `dps_dist: src <h> <name> pmf p0 p1 ...` line per distinct pmf, so the configuration is provable from stdout.

## Files
`htsim/sim/dps_dist.h` (pmf families, permutation, CDF sampler; pure), `uec.h` / `uec.cpp` (enum `DPS`, `nextEntropy_dps`, `processEv_dps`, `initDps`, `EVSRC_DPS`, statics), `datacenter/main_uec.cpp` (flags, startup checks). Banner: `// ===== ADDED (dps) =====`. Tests: `experiments/tools/dps_dist_test.cpp` (standalone, no simulator), `meeting_26_10_26/knee_16paths/scripts/dps_smoke.py` (simulator).

## Usage (knee_16paths cell)
```
... -use_srv6 -paths 16 -load_balancing_algo dps -dps_dist capacity      # 95% / 5% on the 5/95 fabric
... -load_balancing_algo dps -dps_dist zipf 1.2
... -load_balancing_algo dps -dps_dist list 1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0
... -load_balancing_algo dps -dps_dist normal 8 3 -dps_perm 7
```
`-reps_buffer_size` is accepted and ignored by DPS, so a DPS cell does not depend on B.
