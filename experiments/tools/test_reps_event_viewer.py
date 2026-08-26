""" Unit tests for reps_event_viewer.py """

import contextlib
import io
import os
import tempfile
import unittest

from reps_event_viewer import (
    EventParseError,
    buffer_is_live,
    build_html,
    diff_slots,
    filter_events,
    load_events,
    main,
    parse_slots,
    truncate_events,
    verify_events,
)

HEADER = (
    "n,time_ns,src_id,event,ev,ev_src,ecn,seqno,fresh,buf_size,frozen_mode,"
    "frozen_ev,head,frozen_head,cwnd_pkts,inflight_pkts,slots\n"
)

# 12 rows covering all 7 event kinds for a single source (max_size = 4 slots).
# Hand-derived to match CircularBufferREPS's real semantics (buffer_reps.cpp):
# add() writes at head then advances head; remove_earliest_fresh() pops at
# (head - fresh) mod max_size; remove_frozen() always invalidates the slot at
# the frozen read pointer (even if already invalid) then advances it; count
# (buf_size) only ever increases via add(), never decremented by a pop.
GOOD_ROWS = [
    "1,0.0,0,SEND,2,random,-1,0,0,0,0,-1,0,0,10,1,0:0:0|0:0:0|0:0:0|0:0:0",
    "2,10.0,0,ACK,2,,0,0,1,1,0,-1,1,0,10,0,2:1:1|0:0:0|0:0:0|0:0:0",
    "3,20.0,0,SEND,2,fresh_pop,-1,1,0,1,0,-1,1,0,10,1,2:0:1|0:0:0|0:0:0|0:0:0",
    "4,30.0,0,ACK,2,,1,1,0,1,0,-1,1,0,10,0,2:0:1|0:0:0|0:0:0|0:0:0",
    "5,31.0,0,NACK,2,,-1,1,0,1,0,-1,1,0,10,1,2:0:1|0:0:0|0:0:0|0:0:0",
    "6,40.0,0,RTX,1,random,-1,1,0,1,0,-1,1,0,10,1,2:0:1|0:0:0|0:0:0|0:0:0",
    "7,45.0,0,RTS,3,random,-1,2,0,1,0,-1,1,0,10,2,2:0:1|0:0:0|0:0:0|0:0:0",
    "8,60.0,0,ACK,1,,0,1,1,2,0,-1,2,0,10,1,2:0:1|1:1:1|0:0:0|0:0:0",
    "9,70.0,0,FREEZE,7,,-1,-1,1,2,1,2,2,0,10,1,2:0:1|1:1:1|0:0:0|0:0:0",
    "10,80.0,0,SEND,2,frozen_pop,-1,3,1,2,1,1,2,1,10,2,2:0:1|1:1:1|0:0:0|0:0:0",
    "11,90.0,0,ACK,1,,0,3,1,2,1,1,2,1,10,1,2:0:1|1:1:1|0:0:0|0:0:0",
    "12,100.0,0,UNFREEZE,-1,,-1,-1,0,0,0,-1,0,0,10,0,0:0:0|0:0:0|0:0:0|0:0:0",
]


def write_csv(path, rows, header=HEADER):
    with open(path, "w", newline="") as f:
        f.write(header)
        for r in rows:
            f.write(r + "\n")


class TestLoadEvents(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "events.csv")
        write_csv(self.path, GOOD_ROWS)

    def test_parses_all_kinds_and_row_count(self):
        events = load_events(self.path)
        self.assertEqual(len(events), 12)
        kinds = {e["event"] for e in events}
        self.assertEqual(
            kinds, {"SEND", "RTX", "RTS", "ACK", "NACK", "FREEZE", "UNFREEZE"}
        )

    def test_slots_parse_to_max_size_triples(self):
        events = load_events(self.path)
        for e in events:
            self.assertEqual(len(e["slots"]), 4)
            for slot in e["slots"]:
                self.assertIn("value", slot)
                self.assertIn("valid", slot)
                self.assertIn("lifetime", slot)


class TestFilters(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmpdir, "events.csv")
        rows = GOOD_ROWS + [
            "13,50.0,1,SEND,0,random,-1,0,0,0,0,-1,0,0,10,1,0:0:0|0:0:0|0:0:0|0:0:0"
        ]
        write_csv(self.path, rows)
        self.events = load_events(self.path)

    def test_time_window(self):
        out = filter_events(self.events, t0=20.0, t1=45.0)
        self.assertTrue(all(20.0 <= e["time_ns"] <= 45.0 for e in out))
        self.assertEqual(len(out), 5)  # rows 3,4,5,6,7 (t=20,30,31,40,45)

    def test_src_filter(self):
        out = filter_events(self.events, srcs=[1])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["src_id"], 1)

    def test_max_events_truncates_and_reports(self):
        out, truncated = truncate_events(self.events, 5)
        self.assertEqual(len(out), 5)
        self.assertTrue(truncated)
        out2, truncated2 = truncate_events(self.events, 1000)
        self.assertEqual(len(out2), len(self.events))
        self.assertFalse(truncated2)


class TestMalformedRows(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _write_and_load(self, rows):
        path = os.path.join(self.tmpdir, "bad.csv")
        write_csv(path, rows)
        return load_events(path)

    def test_short_row_raises_with_line_number(self):
        with self.assertRaises(EventParseError) as ctx:
            self._write_and_load(["1,0.0,0,SEND,2,random"])
        self.assertIn("line 2", str(ctx.exception))

    def test_non_numeric_ev_raises_with_line_number(self):
        rows = [GOOD_ROWS[0].replace(",2,random,", ",notanumber,random,")]
        with self.assertRaises(EventParseError) as ctx:
            self._write_and_load(rows)
        self.assertIn("line 2", str(ctx.exception))
        self.assertIn("ev", str(ctx.exception))

    def test_empty_slots_raises_with_line_number(self):
        rows = [GOOD_ROWS[0].rsplit(",", 1)[0] + ","]
        with self.assertRaises(EventParseError) as ctx:
            self._write_and_load(rows)
        self.assertIn("line 2", str(ctx.exception))
        self.assertIn("empty slots", str(ctx.exception))


class TestDiffSlots(unittest.TestCase):
    def test_pop_and_recycle(self):
        prev = parse_slots("2:1:1|0:0:0|5:1:1|0:0:0", 1)
        cur = parse_slots("2:0:1|0:0:0|5:1:1|0:0:0", 1)
        self.assertEqual(diff_slots(prev, cur), "popped slot 0 (EV 2)")

        cur2 = parse_slots("2:1:1|9:1:1|5:1:1|0:0:0", 1)
        self.assertEqual(diff_slots(prev, cur2), "recycled EV 9 into slot 1")

        self.assertEqual(diff_slots(prev, prev), "unchanged")
        self.assertEqual(diff_slots(None, prev), "initial")


class TestSortOrder(unittest.TestCase):
    def test_same_timestamp_keeps_file_order(self):
        rows = [
            "1,10.0,0,SEND,2,random,-1,0,0,0,0,-1,0,0,10,1,0:0:0",
            "2,10.0,0,ACK,2,,0,0,0,0,0,-1,0,0,10,0,0:0:0",
            "3,10.0,0,SEND,1,random,-1,1,0,0,0,-1,0,0,10,1,0:0:0",
        ]
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "ties.csv")
        write_csv(path, rows, header=HEADER)
        events = load_events(path)
        out, _ = truncate_events(events, 1000)
        self.assertEqual([e["n"] for e in out], [1, 2, 3])


class TestHtmlSelfContained(unittest.TestCase):
    def test_no_external_resources(self):
        events = load_events(
            _fixture_path(GOOD_ROWS)
        )
        html = build_html(events, "fixture.csv")
        for forbidden in ("http://", "https://", "<script src=", '<link rel="stylesheet"'):
            self.assertNotIn(forbidden, html)


class TestVerify(unittest.TestCase):
    def test_good_fixture_passes(self):
        events = load_events(_fixture_path(GOOD_ROWS))
        self.assertEqual(verify_events(events), [])

    def test_bad_fresh_count_fails(self):
        rows = list(GOOD_ROWS)
        # row 2 (ACK) legitimately has fresh=1; corrupt the fresh column to 9.
        rows[1] = rows[1].replace(",2,,0,0,1,1,0,", ",2,,0,0,9,1,0,")
        events = load_events(_fixture_path(rows))
        violations = verify_events(events)
        self.assertTrue(any("fresh=" in v for v in violations))

    def test_frozen_pop_uses_buf_size_modulus(self):
        """remove_frozen() advances head_forzen_mode modulo getSize() (the element
        count), not max_size, so a partially-filled buffer wraps the frozen read
        pointer early. Verifying against max_size would false-fire here."""
        # max_size 4, buf_size 2: frozen pointer wrapped 1 -> 0, so the slot just
        # read is (0 - 1) % 2 == 1, not (0 - 1) % 4 == 3.
        rows = [
            "1,0.0,0,ACK,5,,0,0,1,1,0,-1,1,0,10,0,5:1:1|0:0:0|0:0:0|0:0:0",
            "2,10.0,0,ACK,7,,0,1,2,2,0,-1,2,0,10,0,5:1:1|7:1:1|0:0:0|0:0:0",
            "3,20.0,0,FREEZE,5,,-1,-1,2,2,1,5,2,0,10,1,5:1:1|7:1:1|0:0:0|0:0:0",
            "4,30.0,0,SEND,5,frozen_pop,-1,2,1,2,1,7,2,1,10,1,5:0:1|7:1:1|0:0:0|0:0:0",
            "5,40.0,0,SEND,7,frozen_pop,-1,3,0,2,1,5,2,0,10,2,5:0:1|7:0:1|0:0:0|0:0:0",
        ]
        events = load_events(_fixture_path(rows))
        self.assertEqual(verify_events(events), [])

    def test_buffer_never_populated_skips_geometry_checks(self):
        """Under REPS/ECMP the circular buffer exists but is never populated, so
        every snapshot is all-invalid. Buffer-geometry invariants must be skipped
        rather than reporting the whole trace as broken."""
        rows = [
            "1,0.0,0,SEND,2,random,-1,0,0,0,0,-1,0,0,10,1,0:0:0|0:0:0",
            # ACK ecn=0 that recycles nothing — a violation only if the buffer is live
            "2,10.0,0,ACK,2,,0,0,0,0,0,-1,0,0,10,0,0:0:0|0:0:0",
            "3,20.0,0,SEND,3,fresh_pop,-1,1,0,0,0,-1,0,0,10,1,0:0:0|0:0:0",
        ]
        events = load_events(_fixture_path(rows))
        self.assertFalse(buffer_is_live(events))
        self.assertEqual(verify_events(events), [])

    def test_unfreeze_with_valid_slots_fails(self):
        rows = list(GOOD_ROWS)
        # UNFREEZE row (last) should have all-invalid slots; make one valid
        rows[-1] = rows[-1].replace(
            "0:0:0|0:0:0|0:0:0|0:0:0", "1:1:1|0:0:0|0:0:0|0:0:0"
        )
        events = load_events(_fixture_path(rows))
        violations = verify_events(events)
        self.assertTrue(any("UNFREEZE" in v for v in violations))


class TestCliEdgeCases(unittest.TestCase):
    """main()'s handling of degenerate inputs: these must report cleanly and
    never raise out of main()."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.out = os.path.join(self.tmpdir, "o.html")

    def _run(self, *args):
        buf_out, buf_err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf_out), contextlib.redirect_stderr(buf_err):
            rc = main(list(args))
        return rc, buf_out.getvalue() + buf_err.getvalue()

    def test_missing_file_reports_cleanly(self):
        rc, msg = self._run(os.path.join(self.tmpdir, "nope.csv"), "-o", self.out)
        self.assertEqual(rc, 1)
        self.assertIn("cannot read", msg)
        self.assertNotIn("Traceback", msg)

    def test_header_only_trace(self):
        path = os.path.join(self.tmpdir, "h.csv")
        write_csv(path, [])
        rc, msg = self._run(path, "-o", self.out)
        self.assertEqual(rc, 0)
        self.assertIn("0 events", msg)

    def test_verify_on_empty_trace_says_nothing_to_check(self):
        path = os.path.join(self.tmpdir, "h.csv")
        write_csv(path, [])
        rc, msg = self._run(path, "--verify")
        self.assertEqual(rc, 0)
        self.assertIn("nothing to check", msg)
        # must not claim anything about the LB algorithm from an empty trace
        self.assertNotIn("not a FREEZING trace", msg)

    def test_inverted_time_window_warns(self):
        path = os.path.join(self.tmpdir, "g.csv")
        write_csv(path, GOOD_ROWS)
        rc, msg = self._run(path, "-o", self.out, "--from", "100", "--to", "10")
        self.assertEqual(rc, 0)
        self.assertIn("is after --to", msg)

    def test_messages_are_ascii(self):
        """stdout goes to consoles we do not control (cp1252 on Windows)."""
        path = os.path.join(self.tmpdir, "g.csv")
        write_csv(path, GOOD_ROWS)
        for args in ((path, "--verify"), (path, "-o", self.out)):
            _, msg = self._run(*args)
            msg.encode("ascii")  # raises if a non-ASCII char slipped into a message


def _fixture_path(rows):
    tmpdir = tempfile.mkdtemp()
    path = os.path.join(tmpdir, "fixture.csv")
    write_csv(path, rows)
    return path


# ===== ADDED (reps-fifo-trace) =====
FIFO_HEADER = HEADER.rstrip("\n") + ",fifo\n"

# Plain REPS: circular buffer stays empty, the unbounded _next_pathid FIFO does
# the work. push_back on a clean ACK, pop_front on a fresh_pop draw.
EMPTY_SLOTS = "0:0:0|0:0:0|0:0:0|0:0:0"
FIFO_ROWS = [
    # random draw while the FIFO is empty
    f"1,0.0,0,SEND,5,random,-1,0,0,0,0,-1,0,0,10,1,{EMPTY_SLOTS},",
    # clean ACK appends 5
    f"2,10.0,0,ACK,5,,0,0,0,0,0,-1,0,0,10,0,{EMPTY_SLOTS},5",
    # clean ACK appends 9 at the back
    f"3,15.0,0,ACK,9,,0,1,0,0,0,-1,0,0,10,0,{EMPTY_SLOTS},5|9",
    # fresh_pop takes the front (5), leaving the tail
    f"4,20.0,0,SEND,5,fresh_pop,-1,2,0,0,0,-1,0,0,10,1,{EMPTY_SLOTS},9",
    # ECN-marked ACK recycles nothing, FIFO unchanged
    f"5,25.0,0,ACK,9,,1,2,0,0,0,-1,0,0,10,0,{EMPTY_SLOTS},9",
    # fresh_pop drains it
    f"6,30.0,0,SEND,9,fresh_pop,-1,3,0,0,0,-1,0,0,10,1,{EMPTY_SLOTS},",
]


class TestFifoColumn(unittest.TestCase):
    """The `fifo` column was appended after the first traces were captured, so
    both schema widths must stay readable."""

    def test_legacy_17_column_trace_still_loads(self):
        events = load_events(_fixture_path(GOOD_ROWS))
        self.assertEqual(len(events), 12)
        self.assertTrue(all(e["fifo"] is None for e in events),
                        "absent column must parse as None, not as an empty FIFO")

    def test_fifo_trace_parses_and_verifies(self):
        events = load_events(_fixture_path2(FIFO_ROWS))
        self.assertEqual([len(e["fifo"]) for e in events], [0, 1, 2, 1, 1, 0])
        self.assertEqual(verify_events(events), [])

    def test_dash_means_algorithm_has_no_fifo(self):
        rows = [FIFO_ROWS[0].rsplit(",", 1)[0] + ",-"]
        events = load_events(_fixture_path2(rows))
        self.assertIsNone(events[0]["fifo"],
                          "'-' (no FIFO) must be distinct from '' (empty FIFO)")

    def test_elision_sentinel_preserved(self):
        rows = [FIFO_ROWS[0].rsplit(",", 1)[0] + ",1|2|+7"]
        events = load_events(_fixture_path2(rows))
        self.assertEqual(events[0]["fifo"][-1], {"elided": 7})

    def test_pop_must_take_the_front(self):
        rows = list(FIFO_ROWS)
        rows[3] = rows[3].replace("SEND,5,fresh_pop", "SEND,9,fresh_pop")
        violations = verify_events(load_events(_fixture_path2(rows)))
        self.assertTrue(any("!= FIFO front" in v for v in violations), violations)

    def test_pop_must_not_disturb_the_tail(self):
        rows = list(FIFO_ROWS)
        rows[3] = rows[3].rsplit(",", 1)[0] + ",4"  # tail 9 silently became 4
        violations = verify_events(load_events(_fixture_path2(rows)))
        self.assertTrue(any("tail changed" in v for v in violations), violations)

    def test_ack_must_append_the_acked_ev(self):
        rows = list(FIFO_ROWS)
        rows[2] = rows[2].rsplit(",", 1)[0] + ",5|4"  # acked 9, appended 4
        violations = verify_events(load_events(_fixture_path2(rows)))
        self.assertTrue(any("!= acked EV" in v for v in violations), violations)

    def test_pop_from_empty_fifo_is_a_violation(self):
        rows = list(FIFO_ROWS)
        rows[5] = rows[5].replace("6,30.0", "6,30.0")  # row 6 pops, row 5 FIFO = "9"
        rows[4] = rows[4].rsplit(",", 1)[0] + ","       # ...make it empty instead
        violations = verify_events(load_events(_fixture_path2(rows)))
        self.assertTrue(any("FIFO was empty" in v for v in violations), violations)


def _fixture_path2(rows):
    tmpdir = tempfile.mkdtemp()
    path = os.path.join(tmpdir, "fixture_fifo.csv")
    write_csv(path, rows, header=FIFO_HEADER)
    return path
# ===== END ADDED (reps-fifo-trace) =====


if __name__ == "__main__":
    unittest.main()
