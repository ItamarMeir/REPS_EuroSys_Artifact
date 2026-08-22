# tools/ — cross-experiment analysis tools

Unlike `expNN_*/scripts/`, tools here are not tied to one experiment. Currently:
`reps_event_viewer.py` — parses the unified REPS event trace (`-log_reps_events`)
and renders a self-contained interactive HTML viewer.

## Background

`-log_reps_state` (see `state_aware_experiments/RUNNING_EXPERIMENTS.md`) logs one
row per received ACK — it shows how the buffer looked when an ACK arrived, but not
*why* a send drew the EV it drew, what RTX/NACK/RTS did, or when FREEZE/UNFREEZE
happened. `-log_reps_events` fills that gap: one row per SEND/RTX/RTS/ACK/NACK/
FREEZE/UNFREEZE, each carrying a full slot-indexed snapshot of the REPS circular
buffer. `-log_reps_state`'s schema is untouched — this is a new, independent file.

## Generating a trace

```bash
htsim_uec ... \
  -load_balancing_algo freezing -reps_buffer_size 8 \
  -log_reps_events events.csv -log_reps_events_src 0 \
  [-log_reps_events_max 200000] \
  [-log_reps_events_window 20000 40000] # bounds in NANOSECONDS, see below
```

- `-log_reps_events_src <id>` is repeatable. `<id>` is the flow's `_node_num`
  (creation-order index — see `uec.h`), the **same convention** `-log_reps_state_src`
  already uses, *not* necessarily the host address printed in a flow's name
  (`Uec_<src>_<dst>`). If you only know the host address, log a wider range of ids
  and check which node_num produced rows for that host, or omit the src filter and
  rely on `-log_reps_state_src` (the trace falls back to that set when
  `-log_reps_events_src` is never passed; if neither is given, nothing is logged —
  logging every host is a firehose case that isn't supported).
- Never use it with `-sender_cc_only` unless `-disable_tor_ecn` is also passed — see
  CLAUDE.md §"The critical `-disable_tor_ecn` gotcha".

## CSV schema

```
n,time_ns,src_id,event,ev,ev_src,ecn,seqno,fresh,buf_size,frozen_mode,frozen_ev,head,frozen_head,cwnd_pkts,inflight_pkts,slots
```

| column | meaning |
|---|---|
| `n` | global monotonic row counter (shared across sources) — gives a stable total order for rows sharing a timestamp |
| `time_ns` | simulation time in **nanoseconds**. htsim's `eventlist().now()` is picoseconds; this column is `now/1000`, deliberately the same expression the pre-existing `-log_reps_state` log uses for its column (labelled `time_us` there, but holding nanoseconds too), so the two files line up row-for-row. `-log_reps_events_window` takes its bounds in the same unit. |
| `src_id` | flow's `_node_num` |
| `event` | `SEND` \| `RTX` \| `RTS` \| `ACK` \| `NACK` \| `FREEZE` \| `UNFREEZE` |
| `ev` | EV put on the wire (send kinds) or echoed (ACK/NACK); the RTO-triggering EV for FREEZE; `-1` for UNFREEZE |
| `ev_src` | draw provenance. A property of the entropy *draw*, so only `SEND`/`RTX`/`RTS` carry one: `explore` \| `random` \| `fresh_pop` \| `frozen_pop` \| `pxr_random` \| `pxr_pop`. Empty on `ACK`/`NACK`/`FREEZE`/`UNFREEZE`, and on LB algorithms that record no provenance. |
| `ecn` | `1`/`0` on ACK, `-1` otherwise |
| `seqno` | packet sequence number (PSN) — for SEND/RTX/RTS, the packet's own PSN; for ACK/NACK, the PSN it acknowledges/nacks (`-1` for FREEZE/UNFREEZE) |
| `fresh` / `buf_size` | `getNumberFreshEntropies()` / `getSize()` (post-event) |
| `frozen_mode` | `1` if FREEZING's frozen mode is active (post-event) |
| `frozen_ev` | value at the frozen read pointer, `-1` if not frozen |
| `head` / `frozen_head` | circular-buffer write head / frozen-mode read pointer (post-event) |
| `cwnd_pkts` / `inflight_pkts` | congestion window / in-flight, in packets |
| `slots` | `\|`-joined `value:isValid:lifetime` triples, one per buffer slot, index == slot index |

## Viewer

```bash
python reps_event_viewer.py events.csv -o trace.html \
    [--from NS] [--to NS] [--max-events N] [--src ID] [--verify]
```

- `--max-events` (default 5000) caps how many events get embedded in the HTML —
  the viewer warns on stdout if it truncates. Widen `--from`/`--to`/`--src` to
  narrow scope instead of raising the cap for a multi-hundred-thousand-row trace.
- `--from`/`--to` are in nanoseconds, matching the `time_ns` column.
- `--verify` checks the trace invariants (buffer-geometry consistency, pop/draw
  provenance, freeze/unfreeze bookkeeping — see `verify_events()` in
  `reps_event_viewer.py`) and exits non-zero on violation, printing offending
  row numbers. Run this on every new trace before trusting the viewer's output.
  The buffer-geometry invariants only apply to FREEZING / FREEZING_PXR; on a
  trace whose buffer is never populated (REPS, ECMP, PATH_RR, ...) they are
  skipped and `--verify` says so.
- The HTML output is fully self-contained (no CDN, no external CSS/JS) — safe to
  email or drop in OneDrive.

### Viewer UI

- **State panel** — mode badge (NORMAL/FREEZING), sim clock, head/frozenHead/
  fresh/bufSize/cwndPkts/inFlight/frozenEv (changed values pulse).
- **Buffer grid** — one cell per slot; `↑` marks the write head, `fz ↓` marks the
  frozen read pointer when frozen; the slot touched by the current event flashes.
- **PSN cross-reference** — on an ACK/NACK row, a link shows which SEND/RTX row
  put that PSN on the wire (with RTT = ack time − send time) and highlights it in
  the log; click to jump there. The event log also prints `psn=` and `rtt=` inline
  on every ACK/NACK line.
- **Controls** — step, play/pause with speed, seek slider, jump-to-time, per-kind
  filters (Next/Prev skip disabled kinds).
- **Theme** — follows the OS light/dark preference; the *Theme* button forces
  either one (remembered per browser via `localStorage`).
- Keyboard: →/← step, space play/pause, Home/End.

## Regenerating a trace

No trace CSV or rendered HTML is checked in — raw run artefacts don't belong in
the repo (CLAUDE.md § Common pitfalls). Add the flags above to any FREEZING run,
e.g. a 128-host permutation with a few failed Agg↔Core links so the trace
actually contains `FREEZE` and frozen-cycle sends, then:

```bash
python reps_event_viewer.py events.csv --verify
python reps_event_viewer.py events.csv -o trace.html
```

## Tests

```bash
python -m unittest test_reps_event_viewer.py -v
```
