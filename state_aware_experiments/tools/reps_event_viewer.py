#!/usr/bin/env python3
"""
reps_event_viewer.py — parse a REPS unified event trace (from htsim's
-log_reps_events) and render a self-contained interactive HTML viewer.

CSV schema (written by UecSrc::logRepsEvent, htsim/sim/uec.cpp):
    n,time_ns,src_id,event,ev,ev_src,ecn,seqno,fresh,buf_size,frozen_mode,
    frozen_ev,head,frozen_head,cwnd_pkts,inflight_pkts,slots

`time_ns` is nanoseconds (htsim's eventlist().now()/1000) — the same expression
the pre-existing -log_reps_state log uses for its (mislabelled) "time_us" column,
so the two files line up row-for-row.

`slots` is a `|`-joined list of `value:isValid:lifetime` triples, one per
circular-buffer slot, index == slot index (post-event snapshot).

Usage:
    python reps_event_viewer.py events.csv -o trace.html \\
        [--from NS] [--to NS] [--max-events N] [--src ID] [--verify]
"""

import argparse
import csv
import html
import json
import sys

EXPECTED_COLUMNS = [
    "n", "time_ns", "src_id", "event", "ev", "ev_src", "ecn", "seqno",
    "fresh", "buf_size", "frozen_mode", "frozen_ev", "head", "frozen_head",
    "cwnd_pkts", "inflight_pkts", "slots",
]

EVENT_KINDS = ["SEND", "RTX", "RTS", "ACK", "NACK", "FREEZE", "UNFREEZE"]

POP_SOURCES = {"fresh_pop", "frozen_pop", "pxr_pop"}
DRAW_SOURCES = {"explore", "random", "pxr_random"}


class EventParseError(ValueError):
    """Raised when a trace row cannot be parsed; message names the line number."""


def _parse_int(value, line_no, column):
    try:
        return int(value)
    except ValueError as exc:
        raise EventParseError(
            f"line {line_no}: invalid integer for column '{column}': {value!r}"
        ) from exc


def _parse_float(value, line_no, column):
    try:
        return float(value)
    except ValueError as exc:
        raise EventParseError(
            f"line {line_no}: invalid float for column '{column}': {value!r}"
        ) from exc


def parse_slots(raw, line_no):
    """Parse the `|`-joined `value:isValid:lifetime` slots field."""
    if raw == "":
        raise EventParseError(f"line {line_no}: empty slots field")
    slots = []
    for i, chunk in enumerate(raw.split("|")):
        parts = chunk.split(":")
        if len(parts) != 3:
            raise EventParseError(
                f"line {line_no}: malformed slot {i} ({chunk!r}), expected value:isValid:lifetime"
            )
        value_s, valid_s, life_s = parts
        slots.append({
            "value": _parse_int(value_s, line_no, f"slots[{i}].value"),
            "valid": _parse_int(valid_s, line_no, f"slots[{i}].isValid") != 0,
            "lifetime": _parse_int(life_s, line_no, f"slots[{i}].lifetime"),
        })
    return slots


def parse_row(row, line_no):
    if len(row) != len(EXPECTED_COLUMNS):
        raise EventParseError(
            f"line {line_no}: expected {len(EXPECTED_COLUMNS)} fields, got {len(row)}"
        )
    d = dict(zip(EXPECTED_COLUMNS, row))
    event = {
        "n": _parse_int(d["n"], line_no, "n"),
        "time_ns": _parse_float(d["time_ns"], line_no, "time_ns"),
        "src_id": _parse_int(d["src_id"], line_no, "src_id"),
        "event": d["event"],
        "ev": _parse_int(d["ev"], line_no, "ev"),
        "ev_src": d["ev_src"],
        "ecn": _parse_int(d["ecn"], line_no, "ecn"),
        "seqno": _parse_int(d["seqno"], line_no, "seqno"),
        "fresh": _parse_int(d["fresh"], line_no, "fresh"),
        "buf_size": _parse_int(d["buf_size"], line_no, "buf_size"),
        "frozen_mode": _parse_int(d["frozen_mode"], line_no, "frozen_mode"),
        "frozen_ev": _parse_int(d["frozen_ev"], line_no, "frozen_ev"),
        "head": _parse_int(d["head"], line_no, "head"),
        "frozen_head": _parse_int(d["frozen_head"], line_no, "frozen_head"),
        "cwnd_pkts": _parse_int(d["cwnd_pkts"], line_no, "cwnd_pkts"),
        "inflight_pkts": _parse_int(d["inflight_pkts"], line_no, "inflight_pkts"),
        "slots": parse_slots(d["slots"], line_no),
    }
    if event["event"] not in EVENT_KINDS:
        raise EventParseError(
            f"line {line_no}: unknown event kind {event['event']!r}"
        )
    return event


def load_events(path):
    """Parse the full trace CSV into a list of event dicts (file order preserved)."""
    events = []
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            return events
        if header != EXPECTED_COLUMNS:
            raise EventParseError(
                f"line 1: unexpected header {header!r}, expected {EXPECTED_COLUMNS!r}"
            )
        for line_no, row in enumerate(reader, start=2):
            if not row:
                continue
            events.append(parse_row(row, line_no))
    return events


def filter_events(events, t0=None, t1=None, srcs=None):
    out = events
    if srcs:
        srcs = set(srcs)
        out = [e for e in out if e["src_id"] in srcs]
    if t0 is not None:
        out = [e for e in out if e["time_ns"] >= t0]
    if t1 is not None:
        out = [e for e in out if e["time_ns"] <= t1]
    return out


def sort_key(e):
    return (e["time_ns"], e["n"])


def truncate_events(events, max_events):
    events = sorted(events, key=sort_key)
    if len(events) <= max_events:
        return events, False
    return events[:max_events], True


def diff_slots(prev_slots, cur_slots):
    """Describe what changed between two consecutive slot snapshots.

    Returns one of: "unchanged", "popped slot <i> (EV <v>)",
    "recycled EV <v> into slot <i>", or a generic "slots changed" fallback.
    """
    if prev_slots is None:
        return "initial"
    if len(prev_slots) != len(cur_slots):
        return "slots changed"

    popped = []
    added = []
    for i, (p, c) in enumerate(zip(prev_slots, cur_slots)):
        if p["valid"] and not c["valid"]:
            popped.append((i, p["value"]))
        elif not p["valid"] and c["valid"]:
            added.append((i, c["value"]))
        elif p["valid"] and c["valid"] and p["value"] != c["value"]:
            popped.append((i, p["value"]))
            added.append((i, c["value"]))

    if not popped and not added:
        return "unchanged"
    if len(popped) == 1 and not added:
        i, v = popped[0]
        return f"popped slot {i} (EV {v})"
    if len(added) == 1 and not popped:
        i, v = added[0]
        return f"recycled EV {v} into slot {i}"
    if len(popped) == 1 and len(added) == 1:
        pi, pv = popped[0]
        ai, av = added[0]
        return f"popped slot {pi} (EV {pv}), recycled EV {av} into slot {ai}"
    return "slots changed"


def buffer_is_live(events):
    """True if the trace ever shows a valid buffer slot.

    The REPS circular buffer is only driven by the FREEZING / FREEZING_PXR load
    balancers. Under REPS, ECMP, PATH_RR etc. `circular_buffer_reps` exists but
    is never populated, so every snapshot is all-invalid and the buffer-geometry
    invariants below do not apply — checking them anyway reports the whole trace
    as broken.
    """
    return any(s["valid"] for e in events for s in e["slots"])


def verify_events(events):
    """Check the trace invariants. Returns a list of violation strings, each
    naming the offending row (`n`).

    Ordering and `fresh` bookkeeping are checked on every trace; the
    buffer-geometry invariants are skipped when the buffer is never populated
    (see buffer_is_live)."""
    violations = []
    events = sorted(events, key=sort_key)
    check_buffer = buffer_is_live(events)

    last_time_by_src = {}
    last_n_by_src = {}
    prev_slots_by_src = {}
    prev_event_by_src = {}

    for e in events:
        src = e["src_id"]
        n = e["n"]

        if src in last_time_by_src and e["time_ns"] < last_time_by_src[src]:
            violations.append(f"row n={n}: time_ns decreased for src {src}")
        last_time_by_src[src] = e["time_ns"]

        if src in last_n_by_src and n <= last_n_by_src[src]:
            violations.append(f"row n={n}: n not strictly increasing for src {src}")
        last_n_by_src[src] = n

        n_valid = sum(1 for s in e["slots"] if s["valid"])
        if e["fresh"] != -1 and e["fresh"] != n_valid:
            violations.append(
                f"row n={n}: fresh={e['fresh']} != count(isValid)={n_valid}"
            )

        prev_slots = prev_slots_by_src.get(src)
        kind, ev_src = e["event"], e["ev_src"]

        if not check_buffer:
            prev_slots_by_src[src] = e["slots"]
            prev_event_by_src[src] = e
            continue

        if kind in ("SEND", "RTX") and ev_src == "frozen_pop":
            # remove_frozen() (buffer_reps.cpp) always sets isValid=false at the
            # slot it reads and unconditionally advances head_forzen_mode, even
            # when that slot was already invalid (the frozen read pointer walks
            # every slot, not just fresh ones). It advances modulo getSize() —
            # the element *count*, not max_size — so the pointer wraps early
            # while the buffer is still filling. Mirror that modulus here, or
            # this check false-fires on every partially-filled buffer.
            modulus = e["buf_size"] if e["buf_size"] > 0 else len(e["slots"])
            ok = False
            if modulus:
                idx = (e["frozen_head"] - 1) % modulus
                slot = e["slots"][idx]
                ok = (not slot["valid"]) and slot["value"] == e["ev"]
            if not ok:
                violations.append(
                    f"row n={n}: {kind} ev_src=frozen_pop but EV {e['ev']} not found "
                    f"invalid at slot (frozen_head-1)%buf_size"
                )
        elif kind in ("SEND", "RTX") and ev_src in POP_SOURCES:
            popped_slot = None
            if prev_slots is not None:
                for i, (p, c) in enumerate(zip(prev_slots, e["slots"])):
                    if p["valid"] and not c["valid"] and p["value"] == e["ev"]:
                        popped_slot = i
                        break
            if popped_slot is None:
                violations.append(
                    f"row n={n}: {kind} ev_src={ev_src} but popped EV {e['ev']} "
                    f"not found invalidated in slots"
                )

        if kind in ("SEND", "RTX") and ev_src in DRAW_SOURCES:
            if prev_slots is not None and prev_slots != e["slots"]:
                violations.append(
                    f"row n={n}: {kind} ev_src={ev_src} but slots snapshot changed"
                )

        if kind == "ACK" and e["ecn"] == 0 and e["frozen_mode"] == 0:
            max_size = len(e["slots"])
            if max_size:
                slot_idx = (e["head"] - 1) % max_size
                slot = e["slots"][slot_idx]
                if not slot["valid"] or slot["value"] != e["ev"]:
                    violations.append(
                        f"row n={n}: ACK ecn=0 EV {e['ev']} not found valid at "
                        f"slot (head-1)%max_size={slot_idx}"
                    )

        if kind == "NACK":
            if prev_slots is not None and prev_slots != e["slots"]:
                violations.append(f"row n={n}: NACK but slots snapshot changed")

        if e["frozen_mode"] == 1:
            max_size = len(e["slots"])
            if max_size and 0 <= e["frozen_head"] < max_size:
                if e["slots"][e["frozen_head"]]["value"] != e["frozen_ev"]:
                    violations.append(
                        f"row n={n}: frozen_mode=1 but frozen_ev={e['frozen_ev']} != "
                        f"slots[frozen_head].value={e['slots'][e['frozen_head']]['value']}"
                    )

        if kind == "UNFREEZE":
            if any(s["valid"] for s in e["slots"]):
                violations.append(f"row n={n}: UNFREEZE but some slots still valid")

        prev_slots_by_src[src] = e["slots"]
        prev_event_by_src[src] = e

    return violations


def build_html(events, source_name):
    """Embed `events` as a JSON literal in a self-contained HTML viewer."""
    payload = json.dumps(events, separators=(",", ":"))
    title = html.escape(f"REPS event trace — {source_name}")
    return HTML_TEMPLATE.replace("__TITLE__", title).replace("__EVENTS_JSON__", payload)


HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>__TITLE__</title>
<style>
:root {
  /* Light palette. Every colour is defined here on bare :root so a token is
     never introduced for the first time inside a media/[data-theme] block. */
  --blue: #2563eb; --green: #16a34a; --orange: #d97706; --red: #dc2626;
  --ink: #0f172a; --muted: #64748b;
  --paper: #f8fafc; --card: #ffffff; --border: #e2e8f0;
  --sunken: #f1f5f9;              /* state tiles / buffer cells */
  --link: #2563eb;
  --flash: #fde68a;               /* "value changed" pulse */
  --cell-empty: #94a3b8;          /* invalid-slot glyph, must stay readable */
  --badge-ok-bg: #dcfce7;   --badge-ok-fg: #14532d;
  --badge-frz-bg: #fee2e2;  --badge-frz-fg: #7f1d1d;
  /* The event log is a dark surface in both themes (matches the reference
     simulator); its own tokens keep it independent of the page theme. */
  --log-bg: #0f172a; --log-fg: #cbd5e1; --log-hover: #1e293b;
  --log-current: #334155; --log-outline: #64748b; --log-match: #38bdf8;
  --mono: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    /* Brighter accents: the light-mode blues/greens fall below contrast on a
       dark ground. Only tokens are redefined — no rules are duplicated. */
    --blue: #60a5fa; --green: #4ade80; --orange: #fbbf24; --red: #f87171;
    --ink: #e5e7eb; --muted: #9ca3af;
    --paper: #0b1220; --card: #131c2e; --border: #2a3650;
    --sunken: #1a2540;
    --link: #7dd3fc;
    --flash: #78500a;
    --cell-empty: #64748b;
    --badge-ok-bg: #14532d;  --badge-ok-fg: #bbf7d0;
    --badge-frz-bg: #7f1d1d; --badge-frz-fg: #fecaca;
    --log-bg: #060b16; --log-fg: #cbd5e1; --log-hover: #16213a;
    --log-current: #2a3a5c; --log-outline: #7c8aa5; --log-match: #38bdf8;
  }
}
:root[data-theme="dark"] {
  --blue: #60a5fa; --green: #4ade80; --orange: #fbbf24; --red: #f87171;
  --ink: #e5e7eb; --muted: #9ca3af;
  --paper: #0b1220; --card: #131c2e; --border: #2a3650;
  --sunken: #1a2540;
  --link: #7dd3fc;
  --flash: #78500a;
  --cell-empty: #64748b;
  --badge-ok-bg: #14532d;  --badge-ok-fg: #bbf7d0;
  --badge-frz-bg: #7f1d1d; --badge-frz-fg: #fecaca;
  --log-bg: #060b16; --log-fg: #cbd5e1; --log-hover: #16213a;
  --log-current: #2a3a5c; --log-outline: #7c8aa5; --log-match: #38bdf8;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--paper); color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 14px;
}
.wrap { display: flex; flex-direction: column; gap: 12px; padding: 16px; max-width: 1200px; margin: 0 auto; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }
h1 { font-size: 16px; margin: 0 0 4px 0; }
.sub { color: var(--muted); font-size: 12px; margin-bottom: 8px; }
.row { display: flex; gap: 16px; flex-wrap: wrap; align-items: center; }
.state-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(90px, 1fr)); gap: 8px; font-family: var(--mono); }
.state-item { background: var(--sunken); border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; }
.state-item .k { font-size: 10px; color: var(--muted); text-transform: uppercase; }
.state-item .v { font-size: 15px; font-weight: 600; }
.state-item.changed { animation: pulse 0.6s ease; }
@keyframes pulse { 0% { background: var(--flash); } 100% { background: var(--sunken); } }
.badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; }
.badge.NORMAL { background: var(--badge-ok-bg); color: var(--badge-ok-fg); }
.badge.FREEZING { background: var(--badge-frz-bg); color: var(--badge-frz-fg); }
.buffer-grid { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; margin-bottom: 22px; }
.cell { position: relative; width: 56px; height: 56px; border: 2px solid var(--border); border-radius: 8px;
  display: flex; align-items: center; justify-content: center; font-family: var(--mono); font-weight: 700;
  font-size: 16px; background: var(--sunken); color: var(--ink); }
.cell.invalid { color: var(--cell-empty); border-style: dashed; background: transparent; }
.cell.head::before { content: "\2191"; position: absolute; top: -18px; left: 50%; transform: translateX(-50%); color: var(--blue); font-weight: 900; }
.cell.frozenhead::after { content: "fz \2193"; position: absolute; bottom: -18px; left: 50%; transform: translateX(-50%);
  color: var(--orange); font-size: 10px; font-weight: 700; }
.cell.flash { box-shadow: 0 0 0 3px var(--accent, var(--blue)); }
.controls { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
button { border: 1px solid var(--border); background: var(--card); color: var(--ink); border-radius: 6px;
  padding: 6px 12px; cursor: pointer; font-size: 13px; }
button:hover { background: var(--sunken); }
input[type=range] { flex: 1; min-width: 120px; accent-color: var(--blue); }
input[type=checkbox] { accent-color: var(--blue); }
input[type=number], input[type=text] { border: 1px solid var(--border); background: var(--sunken);
  color: var(--ink); border-radius: 6px; padding: 4px 8px; width: 110px; }
label.kindfilter { font-size: 12px; display: flex; align-items: center; gap: 3px; }
.log { background: var(--log-bg); color: var(--log-fg); border-radius: 8px; padding: 8px; font-family: var(--mono);
  font-size: 12px; height: 320px; overflow-y: auto; }
.log-row { padding: 3px 6px; border-radius: 4px; cursor: pointer; white-space: pre; }
.log-row:hover { background: var(--log-hover); }
.log-row.current { background: var(--log-current); outline: 1px solid var(--log-outline); }
.log-row.psn-match { outline: 2px solid var(--log-match); }
#psnLink a { color: var(--link); text-decoration: none; }
#psnLink a:hover { text-decoration: underline; }
.tag { display: inline-block; padding: 0 5px; border-radius: 4px; font-weight: 700; margin-right: 6px;
  min-width: 72px; text-align: center; }
.tag-SEND, .tag-RTX, .tag-RTS { background: #1d4ed8; color: #ffffff; }
.tag-ACK { background: #15803d; color: #ffffff; }
.tag-ACK.ecn1, .tag-NACK { background: #b91c1c; color: #ffffff; }
.tag-FREEZE, .tag-UNFREEZE { background: #b45309; color: #ffffff; }
.hint { font-size: 11px; color: var(--muted); }
#btnTheme { margin-left: auto; }
</style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <h1>__TITLE__</h1>
    <div class="sub" id="meta"></div>
    <div class="row">
      <span class="badge" id="modeBadge">NORMAL</span>
      <span id="clock" style="font-family: var(--mono); font-weight: 700;">T+0 ns</span>
      <button id="btnTheme" title="Toggle light / dark">&#9681; Theme</button>
    </div>
    <div class="state-grid" id="stateGrid"></div>
    <div class="buffer-grid" id="bufferGrid"></div>
    <div class="hint" id="psnLink" style="margin-top:8px;"></div>
  </div>

  <div class="card">
    <div class="controls">
      <button id="btnPrev">&#9664; Prev</button>
      <button id="btnPlay">&#9654; Play</button>
      <button id="btnNext">Next &#9654;</button>
      <span class="hint">speed</span>
      <input type="range" id="speed" min="1" max="50" value="10">
      <span class="hint">jump to time (ns)</span>
      <input type="text" id="jumpTime">
      <button id="btnJump">Go</button>
    </div>
    <div class="controls" style="margin-top:6px;">
      <input type="range" id="seek" min="0" max="0" value="0" style="flex:2;">
      <span id="seekLabel" class="hint"></span>
    </div>
    <div class="controls" style="margin-top:6px;" id="kindFilters"></div>
    <div class="hint" style="margin-top:6px;">Keyboard: &#8594;/&#8592; step, space play/pause, Home/End</div>
  </div>

  <div class="card">
    <div class="log" id="eventLog"></div>
  </div>
</div>

<script>
const EVENTS = __EVENTS_JSON__;
// Accent per event kind, expressed as palette tokens so both themes resolve
// them to their own (contrast-checked) values rather than a frozen hex.
const KIND_COLOR = {
  SEND: "var(--blue)", RTX: "var(--blue)", RTS: "var(--blue)",
  ACK: "var(--green)", NACK: "var(--red)",
  FREEZE: "var(--orange)", UNFREEZE: "var(--orange)",
};

let idx = 0;
let playing = false;
let playTimer = null;
let enabledKinds = new Set(["SEND","RTX","RTS","ACK","NACK","FREEZE","UNFREEZE"]);

// ===== ADDED (reps-event-trace): PSN cross-reference index =====
// Maps "<src_id>:<seqno>" -> sorted list of row indices where a SEND/RTX/RTS
// put that PSN on the wire. Lets an ACK/NACK row jump straight to the packet
// send(s) it corresponds to (a PSN can appear more than once if retransmitted).
const psnIndex = {};
EVENTS.forEach((e, i) => {
  if (e.seqno === -1) return;
  if (!["SEND","RTX","RTS"].includes(e.event)) return;
  const key = e.src_id + ":" + e.seqno;
  (psnIndex[key] = psnIndex[key] || []).push(i);
});
function findSendForPsn(e, beforeIdx) {
  if (e.seqno === -1) return null;
  const list = psnIndex[e.src_id + ":" + e.seqno];
  if (!list) return null;
  // most recent send/rtx of this PSN strictly before beforeIdx
  let best = null;
  for (const i of list) { if (i < beforeIdx) best = i; else break; }
  return best;
}
function findSendForAck(e) { return findSendForPsn(e, idx); }
// RTT for an ACK/NACK row: its own timestamp minus the send/rtx row that put
// that PSN on the wire (the row's own position in EVENTS, not the playhead).
function rttForRow(rowIdx) {
  const e = EVENTS[rowIdx];
  if (e.event !== "ACK" && e.event !== "NACK") return null;
  const sendIdx = findSendForPsn(e, rowIdx);
  if (sendIdx === null) return null;
  return e.time_ns - EVENTS[sendIdx].time_ns;
}
// ===== END ADDED (reps-event-trace) =====

const meta = document.getElementById("meta");
meta.textContent = EVENTS.length + " events" +
  (EVENTS.length ? (", t=" + EVENTS[0].time_ns.toFixed(1) + "..." + EVENTS[EVENTS.length-1].time_ns.toFixed(1) + " ns") : "");

const kindFiltersEl = document.getElementById("kindFilters");
["SEND","RTX","RTS","ACK","NACK","FREEZE","UNFREEZE"].forEach(k => {
  const lbl = document.createElement("label");
  lbl.className = "kindfilter";
  const cb = document.createElement("input");
  cb.type = "checkbox"; cb.checked = true; cb.dataset.kind = k;
  cb.addEventListener("change", () => {
    if (cb.checked) enabledKinds.add(k); else enabledKinds.delete(k);
  });
  lbl.appendChild(cb);
  lbl.appendChild(document.createTextNode(k));
  kindFiltersEl.appendChild(lbl);
});

const seek = document.getElementById("seek");
seek.max = Math.max(0, EVENTS.length - 1);
const seekLabel = document.getElementById("seekLabel");

function eventDelta(i) {
  const e = EVENTS[i];
  const prev = i > 0 && EVENTS[i-1].src_id === e.src_id ? EVENTS[i-1].slots : null;
  if (!["SEND","RTX","ACK","NACK"].includes(e.event)) return "";
  if (prev === null) return "initial";
  return diffSlots(prev, e.slots);
}

function diffSlots(prevSlots, curSlots) {
  if (prevSlots.length !== curSlots.length) return "slots changed";
  let popped = [], added = [];
  for (let i = 0; i < prevSlots.length; i++) {
    const p = prevSlots[i], c = curSlots[i];
    if (p.valid && !c.valid) popped.push([i, p.value]);
    else if (!p.valid && c.valid) added.push([i, c.value]);
    else if (p.valid && c.valid && p.value !== c.value) { popped.push([i, p.value]); added.push([i, c.value]); }
  }
  if (!popped.length && !added.length) return "unchanged";
  if (popped.length === 1 && !added.length) return "popped slot " + popped[0][0] + " (EV " + popped[0][1] + ")";
  if (added.length === 1 && !popped.length) return "recycled EV " + added[0][1] + " into slot " + added[0][0];
  if (popped.length === 1 && added.length === 1)
    return "popped slot " + popped[0][0] + " (EV " + popped[0][1] + "), recycled EV " + added[0][1] + " into slot " + added[0][0];
  return "slots changed";
}

function renderState(e, prevE) {
  document.getElementById("clock").textContent =
    "T+" + e.time_ns.toFixed(1) + " ns (" + (e.time_ns / 1000).toFixed(3) + " µs)";
  const badge = document.getElementById("modeBadge");
  badge.textContent = e.frozen_mode ? "FREEZING" : "NORMAL";
  badge.className = "badge " + (e.frozen_mode ? "FREEZING" : "NORMAL");

  const fields = [
    ["head", e.head], ["frozenHead", e.frozen_head], ["fresh", e.fresh],
    ["bufSize", e.buf_size], ["cwndPkts", e.cwnd_pkts], ["inFlight", e.inflight_pkts],
    ["frozenEv", e.frozen_ev],
  ];
  const grid = document.getElementById("stateGrid");
  grid.innerHTML = "";
  fields.forEach(([k, v]) => {
    const div = document.createElement("div");
    div.className = "state-item";
    if (prevE) {
      const pv = {head: prevE.head, frozenHead: prevE.frozen_head, fresh: prevE.fresh,
                  bufSize: prevE.buf_size, cwndPkts: prevE.cwnd_pkts, inFlight: prevE.inflight_pkts,
                  frozenEv: prevE.frozen_ev}[k];
      if (pv !== v) div.className += " changed";
    }
    div.innerHTML = '<div class="k">' + k + '</div><div class="v">' + v + '</div>';
    grid.appendChild(div);
  });

  const bufGrid = document.getElementById("bufferGrid");
  bufGrid.innerHTML = "";
  e.slots.forEach((s, i) => {
    const c = document.createElement("div");
    c.className = "cell" + (s.valid ? "" : " invalid");
    if (i === e.head) c.className += " head";
    if (e.frozen_mode && i === e.frozen_head) c.className += " frozenhead";
    if (["SEND","RTX","ACK","NACK"].includes(e.event) && prevE) {
      const pslot = prevE.slots[i];
      if (pslot && (pslot.valid !== s.valid || pslot.value !== s.value)) {
        c.className += " flash";
        c.style.setProperty("--accent", KIND_COLOR[e.event]);
      }
    }
    c.textContent = s.valid ? s.value : "·";
    bufGrid.appendChild(c);
  });
}

function logRowText(e, delta, rowIdx) {
  const psn = e.seqno !== -1 ? "psn=" + e.seqno : "";
  const rtt = rttForRow(rowIdx);
  const rttStr = rtt !== null ? "rtt=" + rtt.toFixed(1) + "ns" : "";
  // Event name is rendered as the coloured tag, not repeated in the text.
  return e.time_ns.toFixed(1).padStart(11) + " ns  " +
    "ev=" + String(e.ev).padStart(3) + "  " + (e.ev_src || "").padEnd(10) +
    "  " + psn.padEnd(9) + " " + rttStr.padEnd(13) + " " + delta;
}

function renderLog() {
  const logEl = document.getElementById("eventLog");
  logEl.innerHTML = "";
  EVENTS.forEach((e, i) => {
    const row = document.createElement("div");
    row.className = "log-row" + (i === idx ? " current" : "");
    row.dataset.idx = i;
    const tagClass = "tag tag-" + e.event + (e.event === "ACK" && e.ecn === 1 ? " ecn1" : "");
    const delta = eventDelta(i);
    row.innerHTML = '<span class="' + tagClass + '">' + e.event + '</span>' +
      html_escape(logRowText(e, delta, i));
    row.addEventListener("click", () => { idx = i; render(); });
    logEl.appendChild(row);
  });
}

function html_escape(s) {
  const d = document.createElement("div"); d.textContent = s; return d.innerHTML;
}

function render() {
  if (!EVENTS.length) return;
  const e = EVENTS[idx];
  const prevE = idx > 0 ? EVENTS[idx - 1] : null;
  renderState(e, prevE && prevE.src_id === e.src_id ? prevE : null);
  seek.value = idx;
  seekLabel.textContent = (idx + 1) + " / " + EVENTS.length;
  document.querySelectorAll(".log-row.current").forEach(el => el.classList.remove("current"));
  document.querySelectorAll(".log-row.psn-match").forEach(el => el.classList.remove("psn-match"));
  const row = document.querySelector('.log-row[data-idx="' + idx + '"]');
  if (row) { row.classList.add("current"); row.scrollIntoView({block: "nearest"}); }

  // ===== ADDED (reps-event-trace): PSN cross-reference =====
  const psnLink = document.getElementById("psnLink");
  psnLink.innerHTML = "";
  if ((e.event === "ACK" || e.event === "NACK") && e.seqno !== -1) {
    const matchIdx = findSendForAck(e);
    if (matchIdx !== null) {
      const matchRow = document.querySelector('.log-row[data-idx="' + matchIdx + '"]');
      if (matchRow) matchRow.classList.add("psn-match");
      const rtt = e.time_ns - EVENTS[matchIdx].time_ns;
      const link = document.createElement("a");
      link.href = "#";
      link.textContent = (e.event === "ACK" ? "↑ acks" : "↑ refers to") +
        " PSN " + e.seqno + " sent at row " + (matchIdx + 1) + " (t=" +
        EVENTS[matchIdx].time_ns.toFixed(1) + " ns, RTT=" + rtt.toFixed(1) +
        " ns) — click to jump";
      link.addEventListener("click", (ev) => { ev.preventDefault(); idx = matchIdx; render(); });
      psnLink.appendChild(link);
    } else {
      psnLink.textContent = "PSN " + e.seqno + ": no matching SEND/RTX row in this trace";
    }
  }
  // ===== END ADDED (reps-event-trace) =====

}

function stepNext() {
  let i = idx + 1;
  while (i < EVENTS.length && !enabledKinds.has(EVENTS[i].event)) i++;
  if (i < EVENTS.length) { idx = i; render(); } else stopPlay();
}
function stepPrev() {
  let i = idx - 1;
  while (i >= 0 && !enabledKinds.has(EVENTS[i].event)) i--;
  if (i >= 0) { idx = i; render(); }
}

function startPlay() {
  playing = true;
  document.getElementById("btnPlay").textContent = "⏸ Pause";
  const speed = document.getElementById("speed");
  const tick = () => {
    if (!playing) return;
    stepNext();
    if (idx >= EVENTS.length - 1) { stopPlay(); return; }
    playTimer = setTimeout(tick, Math.max(20, 600 - speed.value * 11));
  };
  tick();
}
function stopPlay() {
  playing = false;
  document.getElementById("btnPlay").textContent = "▶ Play";
  clearTimeout(playTimer);
}

document.getElementById("btnNext").addEventListener("click", stepNext);
document.getElementById("btnPrev").addEventListener("click", stepPrev);
document.getElementById("btnPlay").addEventListener("click", () => playing ? stopPlay() : startPlay());
seek.addEventListener("input", () => { idx = parseInt(seek.value, 10); render(); });
document.getElementById("btnJump").addEventListener("click", () => {
  const t = parseFloat(document.getElementById("jumpTime").value);
  if (isNaN(t)) return;
  let best = 0;
  for (let i = 0; i < EVENTS.length; i++) { if (EVENTS[i].time_ns <= t) best = i; else break; }
  idx = best; render();
});
document.addEventListener("keydown", (ev) => {
  if (ev.target.tagName === "INPUT") return;
  if (ev.key === "ArrowRight") stepNext();
  else if (ev.key === "ArrowLeft") stepPrev();
  else if (ev.key === " ") { ev.preventDefault(); playing ? stopPlay() : startPlay(); }
  else if (ev.key === "Home") { idx = 0; render(); }
  else if (ev.key === "End") { idx = EVENTS.length - 1; render(); }
});

// Theme toggle: stamps data-theme on <html> so the [data-theme] blocks win over
// the prefers-color-scheme default in both directions. Wrapped in try/catch —
// localStorage throws outright in some embedding contexts.
const btnTheme = document.getElementById("btnTheme");
function currentTheme() {
  return document.documentElement.getAttribute("data-theme") ||
    (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}
try {
  const saved = localStorage.getItem("repsViewerTheme");
  if (saved === "dark" || saved === "light") document.documentElement.setAttribute("data-theme", saved);
} catch (e) { /* storage unavailable; fall back to the OS preference */ }
btnTheme.addEventListener("click", () => {
  const next = currentTheme() === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  try { localStorage.setItem("repsViewerTheme", next); } catch (e) { /* ignore */ }
});

renderLog();
render();
</script>
</body>
</html>
"""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv_path", help="Path to the REPS event trace CSV")
    parser.add_argument("-o", "--output", default="trace.html", help="Output HTML path")
    parser.add_argument("--from", dest="t0", type=float, default=None, help="Start time (ns)")
    parser.add_argument("--to", dest="t1", type=float, default=None, help="End time (ns)")
    parser.add_argument("--max-events", type=int, default=5000, help="Max events embedded in HTML")
    parser.add_argument("--src", type=int, action="append", default=None, help="Filter to src id (repeatable)")
    parser.add_argument("--verify", action="store_true", help="Run invariant checks and exit non-zero on violation")
    args = parser.parse_args(argv)

    try:
        events = load_events(args.csv_path)
    except EventParseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    events = filter_events(events, t0=args.t0, t1=args.t1, srcs=args.src)

    if args.verify:
        violations = verify_events(events)
        if violations:
            print(f"VERIFY FAILED: {len(violations)} violation(s)", file=sys.stderr)
            for v in violations[:50]:
                print(f"  {v}", file=sys.stderr)
            if len(violations) > 50:
                print(f"  ... and {len(violations) - 50} more", file=sys.stderr)
            return 1
        if buffer_is_live(events):
            print(f"VERIFY OK: {len(events)} events, all invariants pass")
        else:
            print(f"VERIFY OK: {len(events)} events, ordering/fresh invariants pass "
                  f"(buffer never populated — not a FREEZING trace, so "
                  f"buffer-geometry invariants were skipped)")
        return 0

    events, truncated = truncate_events(events, args.max_events)
    if truncated:
        print(f"warning: truncated to {args.max_events} events (use --max-events to change)",
              file=sys.stderr)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(build_html(events, args.csv_path))
    print(f"wrote {args.output} ({len(events)} events)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
