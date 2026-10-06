# T2: Speed-of-Light oracle

**Source**: task l.42-43 (add an algorithm that knows the network state and always sends only on links that did not fail, e.g. round-robin over the good ones, to know how much room exists and to reduce noise); Chen 38:19-39:04 (Speed-of-Light, "God mode"); Chen 80:04 ("first find out how much room there is to improve"); Gabriel 85:39 (round-robin over good paths also reduces congestion).

**What it is**: an LB baseline with zero feedback delay and perfect knowledge of which links are dead or slow. It bounds what any buffer policy can reach. Same MPRDMA CC as the B arms, so only path choice differs.

**Rule depends on the scenario** (the meeting's point):

1. **Dead link** (exp30 Part B, `-timed_window`): exclude any path whose route crosses a failed pipe. Round-robin over live paths. Mask fixed for static kill; switches at fail and recover times for timed windows.
2. **Degradation, nothing dead** (exp30 A1/A2, half-speed links): excluding paths is wrong, since all are alive. Use weighted round-robin, weight = min link bitrate on the route. Equal weights would leave nothing to beat under degradation.
3. **Mixed**: exclude dead, weight live paths by min bitrate.

**Implementation, grounded in code**:
- `Route` holds hops as `PacketSink*` (`htsim/sim/route.h`: `at(n)`, `size()`). Source-routed paths are `UecSrc::_paths[]`, built in `htsim/sim/datacenter/main_uec.cpp` ~1790-1815 via `get_bidir_paths` and `new Route(*r, *sink_port)`.
- Dead check: a hop that is a `Pipe` (`htsim/sim/pipe.h`) already has `isFailed()` (`pipe.h:47`). Use `dynamic_cast<Pipe*>(hop)`.
- Speed check: a hop that is a queue has `_bitrate` in `BaseQueue` (`htsim/sim/queue.h:74`), with no public accessor. Add a read-only getter (ADDED banner, MODIFICATIONS row). Path speed = min bitrate over the route's queue hops. Walk the route once at startup and cache per path; re-check liveness on each send, since timed windows change it.
- Path choice: new `nextEntropy_oracle()` (own branch, not inside `nextEntropy_path_rr()`) returning an index into `_paths`. Weighted round-robin with per-path credit: add weight each send, pick highest credit among live paths, subtract the total. Deterministic, so runs reproduce.
- SRv6 caveat: `route_path_idx = ev % _paths.size()` (`uec.cpp` ~4617). The oracle must return the `_paths` index directly, or the mapping must be verified identical. Check in a trace.
- Activation: new CLI `-load_balancing_algo oracle` (own ADDED banner). Must not change `path_rr` behaviour.

**Verification**:
1. Healthy fabric: oracle FCT = `path_rr` FCT within noise.
2. exp30 Part B F=8: count sends per path index; sends on dead paths must be 0.
3. exp30 A1 n=8 (degradation): per-path send histogram matches the bitrate weights.

**Use**: normalization for C1-C4 (FCT / oracle FCT). Also gates SLRU: if oracle FCT is near the best B arm, no replacement policy can gain much.

**Open decision**: does the oracle see the failure schedule in advance, or only current state at send time? Meeting says "knows the network": default = current state at send time, zero delay.
