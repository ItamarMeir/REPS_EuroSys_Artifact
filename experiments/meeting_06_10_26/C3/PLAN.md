# C3: scaling with B up to 256

**Source**: task l.41 (run large buffers up to 256 to check scaling); Gabriel 63:14-63:31 ("to understand the scaling laws; the effect may only show at large sizes").

**Scenario**: same as C2 (exp30 a2, 4 MiB, trim off), B in {64,128,256}, on the same Y axis as the C2 ladder.

**Constraints found in code**:
- `-reps_buffer_size` accepts any integer (`main_uec.cpp:926`); `CircularBufferREPS` has no hard cap.
- `-use_srv6 -paths 32`: only 32 distinct EVs. Entries beyond 32 duplicate EVs, so the buffer above 32 is not independent. Caveat on every B>32 point.
- Trace `slots` field grows linearly with B (`uec.cpp` ~453-460). Comment near `uec.cpp:408` says exp23 went up to 64; verify 256 writes correctly and that the viewer grid (`reps_event_viewer.py` `.buffer-grid`) stays usable.

**Measurements**: as C2 (split, drain metric, FCT). Valid-count distribution as C1 at these B.

**Work**:
1. One short 256-slot trace: confirm slot count and `fresh` are sane.
2. Check the viewer renders 256 cells, or add a summary view instead of a grid.

**Pass / fail**: a clear B-dependent trend in drain or FCT above the seed CI at B>=64 supports Gabriel's scaling idea. No trend = report flat.
